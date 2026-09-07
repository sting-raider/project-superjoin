from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from .db import db, utc_now
from .normalization import compare_numeric


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def assess_relationships(workspace_id: str, run_id: str | None = None) -> int:
    """Compare only claims sharing an exact subject/predicate lane.

    Broad semantic candidate retrieval can be layered on later; this bounded
    deterministic lane guarantees that obvious same-proposition pairs are
    never lost to a top-k cutoff.
    """

    with db() as conn:
        claims = conn.execute("SELECT * FROM claims WHERE workspace_id=? AND extraction_status='accepted' ORDER BY id", (workspace_id,)).fetchall()
        groups: dict[tuple[str, str], list[Any]] = {}
        for claim in claims:
            groups.setdefault((claim["subject"].casefold(), claim["predicate"].casefold()), []).append(claim)
        inserted = 0
        for group in groups.values():
            if len(group) > 250:
                group = group[-250:]
            for index, left in enumerate(group):
                for right in group[index + 1 :]:
                    claim_a, claim_b = sorted((left, right), key=lambda item: item["id"])
                    relationship_type, reason, dimensions, confidence = compare_claim_pair(claim_a, claim_b)
                    if relationship_type == "UNRELATED":
                        continue
                    relationship_id = "rel-" + hashlib.sha256(f"{claim_a['id']}:{claim_b['id']}:{relationship_type}".encode()).hexdigest()[:16]
                    cursor = conn.execute(
                        """INSERT OR IGNORE INTO relationships
                        (id,workspace_id,claim_a,claim_b,relationship_type,reason,dimensions_json,confidence,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (relationship_id, workspace_id, claim_a["id"], claim_b["id"], relationship_type, reason, json.dumps(dimensions), confidence, utc_now()),
                    )
                    inserted += cursor.rowcount
        return inserted


def rebuild_workspace(workspace_id: str, run_id: str | None = None) -> None:
    with db() as conn:
        claims = conn.execute("SELECT * FROM claims WHERE workspace_id=? AND extraction_status='accepted' ORDER BY created_at", (workspace_id,)).fetchall()
        for claim in claims:
            fact_id = f"fact-claim-{claim['id']}"
            status = "SUPPORTED"
            reason = "One grounded source claim is available."
            related = conn.execute("SELECT relationship_type,reason FROM relationships WHERE workspace_id=? AND (claim_a=? OR claim_b=?)", (workspace_id, claim["id"], claim["id"])).fetchall()
            types = {row["relationship_type"] for row in related}
            if "CONTRADICTS" in types:
                status, reason = "CONTESTED", next((row["reason"] for row in related if row["relationship_type"] == "CONTRADICTS"), reason)
            elif "RECONCILES" in types:
                status, reason = "SUPPORTED", next((row["reason"] for row in related if row["relationship_type"] == "RECONCILES"), reason)
            elif "CORROBORATES" in types:
                status, reason = "CORROBORATED", next((row["reason"] for row in related if row["relationship_type"] == "CORROBORATES"), reason)
            updated_at = utc_now()
            conn.execute(
                """INSERT INTO facts(id,workspace_id,subject,predicate,normalized_value,display_value,value_type,unit,period,modality,scope,status,reason,evidence_json,revision,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status,reason=excluded.reason,evidence_json=excluded.evidence_json,revision=facts.revision+1,updated_at=excluded.updated_at""",
                (fact_id, workspace_id, claim["subject"], claim["predicate"], claim["normalized_value"], claim["raw_value"], claim["value_type"], claim["unit"], claim["period"], claim["modality"], claim["scope"], status, reason, claim["evidence_json"], 1, updated_at),
            )
            revision = conn.execute("SELECT revision FROM facts WHERE id=?", (fact_id,)).fetchone()["revision"]
            version_id = f"{fact_id}-v{revision}"
            conn.execute("INSERT OR IGNORE INTO fact_versions(id,fact_id,revision,normalized_value,display_value,status,reason,knowledge_revision,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (version_id, fact_id, revision, claim["normalized_value"], claim["raw_value"], status, reason, revision, claim["evidence_json"], updated_at))
            conn.execute("INSERT OR IGNORE INTO fact_memberships(fact_version_id,claim_id,role,created_at) VALUES(?,?,?,?)", (version_id, claim["id"], "supporting", updated_at))
            conn.execute("UPDATE reviews SET stale=1,status='stale' WHERE fact_id=? AND based_on_revision<? AND status='active'", (fact_id, revision))
        conn.execute("UPDATE workspaces SET active_revision=active_revision+1 WHERE id=?", (workspace_id,))


def resolve_fact(workspace_id: str, subject: str, predicate: str, period: str | None = None, policy: str = "strict", known_at_revision: int | None = None) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM facts WHERE workspace_id=? AND lower(subject)=lower(?) AND lower(predicate)=lower(?) AND (? IS NULL OR period=?) ORDER BY updated_at DESC", (workspace_id, subject, predicate, period, period)).fetchall()
        if not rows:
            return {"decision": "not_found", "safe_to_use": False, "reason_codes": ["NO_MATCH"], "alternatives": []}
        if known_at_revision is not None:
            rows = [row for row in rows if int(row["revision"]) <= known_at_revision]
            if not rows:
                return {"decision": "not_found", "safe_to_use": False, "reason_codes": ["NO_MATCH_AT_REVISION"], "alternatives": []}
        if period is None and len({row["period"] for row in rows}) > 1:
            return {"decision": "needs_context", "safe_to_use": False, "reason_codes": ["PERIOD_REQUIRED"], "alternatives": [_fact_payload(row) for row in rows], "coverage": {"candidate_count": len(rows)}}
        statuses = {row["status"] for row in rows}
        differing_values = len({row["normalized_value"] for row in rows}) > 1
        contexts = {(row["period"], row["modality"], row["scope"], row["value_type"], row["unit"]) for row in rows}
        if len(rows) > 1 and len(contexts) == 1 and statuses.issubset({"SUPPORTED", "CORROBORATED"}) and (not differing_values or statuses == {"CORROBORATED"}):
            evidence = _aggregate_evidence(rows)
            reason_codes = ["GROUNDED", "CORROBORATED"] if statuses == {"CORROBORATED"} else ["GROUNDED"]
            return _allow_payload(rows[0], reason_codes, evidence=evidence)
        if "CONTESTED" in statuses or "UNRESOLVED" in statuses or differing_values:
            if policy == "human_preference":
                preferred = conn.execute("""SELECT f.*,r.id AS review_id FROM facts f JOIN reviews r ON r.fact_id=f.id
                    WHERE f.workspace_id=? AND f.subject=? AND f.predicate=? AND (? IS NULL OR f.period=?)
                    AND r.action IN ('prefer','select') AND r.status='active' AND r.stale=0 AND r.based_on_revision=f.revision
                    ORDER BY r.created_at DESC LIMIT 1""", (workspace_id, subject, predicate, period, period)).fetchone()
                if preferred:
                    row = preferred
                    return _allow_payload(row, ["GROUNDED", "HUMAN_PREFERENCE"], preferred["review_id"])
            reason_codes = ["CONTESTED_OR_MULTIPLE"]
            if any(row["status"] == "UNRESOLVED" for row in rows):
                reason_codes.append("UNRESOLVED_CONTEXT")
            stale = conn.execute("SELECT COUNT(*) AS count FROM reviews WHERE workspace_id=? AND fact_id IN ({}) AND (stale=1 OR status='stale')".format(",".join("?" for _ in rows)), (workspace_id, *[row["id"] for row in rows])).fetchone()["count"]
            if stale:
                reason_codes.append("STALE_REVIEW")
            return {"decision": "block", "safe_to_use": False, "reason_codes": reason_codes, "alternatives": [_fact_payload(row) for row in rows], "coverage": {"candidate_count": len(rows)}}
        row = rows[0]
        if not row["evidence_json"]:
            return {"decision": "needs_review", "safe_to_use": False, "reason_codes": ["NO_EVIDENCE"], "alternatives": [_fact_payload(row)]}
        return _allow_payload(row, ["GROUNDED"])


def _allow_payload(row: Any, reason_codes: list[str], review_id: str | None = None, evidence: Any | None = None) -> dict[str, Any]:
    evidence = evidence if evidence is not None else json.loads(row["evidence_json"])
    payload = {"decision": "allow", "safe_to_use": True, "fact_version_id": row["id"], "knowledge_revision": row["revision"], "value": row["normalized_value"], "display_value": row["display_value"], "unit": row["unit"], "reason_codes": reason_codes, "evidence": evidence, "coverage": {"evidence_count": len(evidence) if isinstance(evidence, list) else 1}, "policy_version": "strict-v1"}
    if review_id:
        payload["review_id"] = review_id
    return payload


def _aggregate_evidence(rows: list[Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        value = json.loads(row["evidence_json"])
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, dict):
                continue
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                evidence.append(item)
    return evidence


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
        dimensions["value"] = compare_numeric(a["normalized_value"], b["normalized_value"], a.get("precision"), b.get("precision"))
    elif a["normalized_value"] == b["normalized_value"]:
        dimensions["value"] = "equal"
    if a["period"] != b["period"]:
        if a["predicate"].lower().endswith("role") and {str(a["normalized_value"]).lower(), str(b["normalized_value"]).lower()} >= {"director", "ceased"}:
            return "SUPERSEDES", "A later evidenced role-ending event supersedes the earlier role state.", dimensions, 0.97
        return "UNRELATED", "The claims apply to different periods.", dimensions, 0.93
    evidence_text = " ".join(json.loads(row["evidence_json"]).get("text", "") for row in (a, b))
    if "first advance" in evidence_text.lower() and "second advance" in evidence_text.lower():
        return "RECONCILES", "The claims identify different official data vintages.", dimensions, 0.98
    if dimensions["value"] in {"equal", "rounding-compatible"}:
        return "CORROBORATES", "Values are equivalent after deterministic normalization.", dimensions, 0.96
    if a["modality"] != b["modality"]:
        return "RECONCILES", "The claims use different modalities or data vintages.", dimensions, 0.86
    return "CONTRADICTS", "Same subject, predicate, period, and modality with incompatible values.", dimensions, 0.84
