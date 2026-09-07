from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .db import db, utc_now
from .demo_data import DEMO_CASES, DEMO_CLAIMS, DEMO_DOCUMENTS, DEMO_RELATIONSHIPS, DEMO_WORKSPACES
from .provenance import page_artifact_id, persist_anchor, persist_interpretation
from .registry import register_workspace_claims


def seed_demo() -> None:
    """Load the small no-key snapshot; source PDFs are intentionally not bundled."""
    with db() as conn:
        for workspace in DEMO_WORKSPACES:
            conn.execute(
                "INSERT OR IGNORE INTO workspaces(id,name,description,created_at) VALUES(?,?,?,?)",
                (workspace["id"], workspace["name"], workspace["description"], utc_now()),
            )
        for document in DEMO_DOCUMENTS:
            digest = hashlib.sha256(document["id"].encode()).hexdigest()
            conn.execute(
                """INSERT OR IGNORE INTO documents
                (id,workspace_id,name,publisher,source_url,sha256,page_count,status,parser,quality_score,published_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (document["id"], document["workspace_id"], document["name"], document["publisher"], document["source_url"], digest, document["page_count"], "complete", "recorded-demo", 0.96, document["published_at"], utc_now()),
            )
        for claim in DEMO_CLAIMS:
            created_at = utc_now()
            conn.execute(
                """INSERT OR IGNORE INTO claims
                (id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,period,modality,scope,evidence_json,grounding_status,extraction_status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (claim["id"], claim["workspace_id"], claim["document_id"], claim["subject"], claim["predicate"], claim["raw_value"], claim["normalized_value"], claim["value_type"], claim["unit"], claim["period"], claim["modality"], claim["scope"], json.dumps(claim["evidence"]), "grounded", "accepted", created_at),
            )
            conn.execute("INSERT OR IGNORE INTO claims_fts(claim_id,workspace_id,subject,predicate,raw_value,period,modality,scope) VALUES(?,?,?,?,?,?,?,?)", (claim["id"], claim["workspace_id"], claim["subject"], claim["predicate"], claim["raw_value"], claim["period"] or "", claim["modality"] or "", claim["scope"] or ""))
            evidence = claim["evidence"]
            page = int(evidence.get("pdf_page") or 1)
            page_id = page_artifact_id(claim["document_id"], page)
            conn.execute(
                """INSERT OR IGNORE INTO page_artifacts
                (id,document_id,page_number,width,height,native_text,parser,parser_version,quality_score,quality_flags_json,disposition,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (page_id, claim["document_id"], page, 1200.0, 1600.0, evidence.get("text", ""), "recorded-demo", "recorded-demo-1", 0.96, "[]", "native", created_at),
            )
            anchor_id = persist_anchor(conn, claim["document_id"], evidence)
            conn.execute("INSERT OR IGNORE INTO claim_evidence(claim_id,anchor_id,purpose,created_at) VALUES(?,?,?,?)", (claim["id"], anchor_id, "assertion", created_at))
            persist_interpretation(conn, claim, claim["id"], created_at)
        for relationship in DEMO_RELATIONSHIPS:
            conn.execute(
                """INSERT OR IGNORE INTO relationships
                (id,workspace_id,claim_a,claim_b,relationship_type,reason,dimensions_json,confidence,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (relationship["id"], relationship["workspace_id"], relationship["claim_a"], relationship["claim_b"], relationship["relationship_type"], relationship["reason"], json.dumps(relationship["dimensions"]), relationship["confidence"], utc_now()),
            )
        _seed_facts(conn)
        for case in DEMO_CASES:
            conn.execute("INSERT OR IGNORE INTO changes(id,workspace_id,run_id,kind,summary,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (f"change-{case['id']}", case["workspace_id"], "demo-seed", "demo_case", case["title"], json.dumps(case), utc_now()))
    for workspace in DEMO_WORKSPACES:
        register_workspace_claims(workspace["id"])


def _seed_facts(conn) -> None:
    rows = conn.execute("SELECT id,workspace_id,subject,predicate,normalized_value,raw_value,value_type,unit,period,modality,scope,evidence_json FROM claims ORDER BY id").fetchall()
    for row in rows:
        fact_id = f"fact-{row['id']}"
        status = "SUPPORTED"
        reason = "One grounded source claim is available."
        if row["id"] in {"clm-delhivery-revenue-annual", "clm-delhivery-revenue-presentation"}:
            fact_id, status, reason = "fact-delhivery-revenue-fy24", "CORROBORATED", "Equivalent after crore/million normalization; presentation value is rounded."
        elif row["id"] in {"clm-survey-gdp-fy25", "clm-rbi-gdp-fy25"}:
            fact_id, status, reason = "fact-india-gdp-fy25", "SUPPORTED", "Context-specific data vintages remain visible as separate source claims."
        elif row["id"] in {"clm-rbi-gdp-fy26", "clm-imf-gdp-fy26"}:
            fact_id, status, reason = "fact-india-gdp-fy26", "CONTESTED", "Competing institutional forecasts; strict Trust Gate blocks an unqualified value."
        conn.execute(
            """INSERT OR IGNORE INTO facts
            (id,workspace_id,subject,predicate,normalized_value,display_value,value_type,unit,period,modality,scope,status,reason,evidence_json,revision,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fact_id, row["workspace_id"], row["subject"], row["predicate"], row["normalized_value"], row["raw_value"], row["value_type"], row["unit"], row["period"], row["modality"], row["scope"], status, reason, row["evidence_json"], 1, utc_now()),
        )
