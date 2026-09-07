from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from .db import db, utc_now
from .normalization import compare_numeric


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def rebuild_workspace(workspace_id: str, run_id: str | None = None) -> None:
    with db() as conn:
        claims = conn.execute("SELECT * FROM claims WHERE workspace_id=? AND extraction_status='accepted' ORDER BY created_at", (workspace_id,)).fetchall()
        for claim in claims:
            fact_id = f"fact-claim-{claim['id']}"
            status = "SUPPORTED"
            reason = "One grounded source claim is available."
            related = conn.execute("SELECT relationship_type,reason FROM relationships WHERE workspace_id=? AND (claim_a=? OR claim_b=?)", (workspace_id, claim["id"], claim["id"])).fetchall()
            types = {row["relationship_type"] for row in related}
            if "CORROBORATES" in types:
                status, reason = "CORROBORATED", next((row["reason"] for row in related if row["relationship_type"] == "CORROBORATES"), reason)
            elif "CONTRADICTS" in types:
                status, reason = "CONTESTED", next((row["reason"] for row in related if row["relationship_type"] == "CONTRADICTS"), reason)
            elif "RECONCILES" in types:
                status, reason = "SUPPORTED", next((row["reason"] for row in related if row["relationship_type"] == "RECONCILES"), reason)
            conn.execute(
                """INSERT INTO facts(id,workspace_id,subject,predicate,normalized_value,display_value,value_type,unit,period,modality,scope,status,reason,evidence_json,revision,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status,reason=excluded.reason,evidence_json=excluded.evidence_json,revision=facts.revision+1,updated_at=excluded.updated_at""",
                (fact_id, workspace_id, claim["subject"], claim["predicate"], claim["normalized_value"], claim["raw_value"], claim["value_type"], claim["unit"], claim["period"], claim["modality"], claim["scope"], status, reason, claim["evidence_json"], 1, utc_now()),
            )
        conn.execute("UPDATE workspaces SET active_revision=active_revision+1 WHERE id=?", (workspace_id,))


def resolve_fact(workspace_id: str, subject: str, predicate: str, period: str | None = None) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM facts WHERE workspace_id=? AND lower(subject)=lower(?) AND lower(predicate)=lower(?) AND (? IS NULL OR period=?) ORDER BY updated_at DESC", (workspace_id, subject, predicate, period, period)).fetchall()
        if not rows:
            return {"decision": "not_found", "safe_to_use": False, "reason_codes": ["NO_MATCH"], "alternatives": []}
        statuses = {row["status"] for row in rows}
        if "CONTESTED" in statuses or len({row["normalized_value"] for row in rows}) > 1:
            return {"decision": "block", "safe_to_use": False, "reason_codes": ["CONTESTED_OR_MULTIPLE"], "alternatives": [_fact_payload(row) for row in rows]}
        row = rows[0]
        return {"decision": "allow", "safe_to_use": True, "fact_version_id": row["id"], "knowledge_revision": row["revision"], "value": row["normalized_value"], "display_value": row["display_value"], "unit": row["unit"], "reason_codes": ["GROUNDED"], "evidence": json.loads(row["evidence_json"])}


def _fact_payload(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "subject": row["subject"], "predicate": row["predicate"], "value": row["normalized_value"], "display_value": row["display_value"], "period": row["period"], "modality": row["modality"], "status": row["status"], "evidence": json.loads(row["evidence_json"])}


def compare_claim_pair(a: Any, b: Any) -> tuple[str, str, dict[str, str], float]:
    dimensions = {
        "subject": "MATCH" if a["subject"].lower() == b["subject"].lower() else "DIFFERENT",
        "predicate": "MATCH" if a["predicate"].lower() == b["predicate"].lower() else "DIFFERENT",
        "period": "MATCH" if a["period"] and a["period"] == b["period"] else "DIFFERENT",
        "modality": "MATCH" if a["modality"] == b["modality"] else "DIFFERENT",
        "value": "UNKNOWN",
    }
    if dimensions["subject"] != "MATCH" or dimensions["predicate"] != "MATCH":
        return "UNRELATED", "Different subject or predicate.", dimensions, 0.88
    if a["value_type"] in {"money", "number", "percentage"} and b["value_type"] in {"money", "number", "percentage"}:
        dimensions["value"] = compare_numeric(a["normalized_value"], b["normalized_value"])
    elif a["normalized_value"] == b["normalized_value"]:
        dimensions["value"] = "equal"
    if a["period"] != b["period"]:
        return "UNRELATED", "The claims apply to different periods.", dimensions, 0.93
    if dimensions["value"] in {"equal", "rounding-compatible"}:
        return "CORROBORATES", "Values are equivalent after deterministic normalization.", dimensions, 0.96
    if a["modality"] != b["modality"]:
        return "RECONCILES", "The claims use different modalities or data vintages.", dimensions, 0.86
    return "CONTRADICTS", "Same subject, predicate, period, and modality with incompatible values.", dimensions, 0.84

