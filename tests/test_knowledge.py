import json
from pathlib import Path

from app.config import settings
from app.db import db, init_db, utc_now
from app.knowledge import assess_relationships, compare_claim_pair, rebuild_workspace, resolve_fact


def _claim(**overrides):
    value = {
        "subject": "India",
        "predicate": "real_gdp_growth",
        "period": "FY25",
        "modality": "estimate",
        "value_type": "percentage",
        "normalized_value": "0.064",
        "evidence_json": json.dumps({"text": "first advance estimate"}),
    }
    value.update(overrides)
    return value


def test_vintage_difference_reconciles_instead_of_calling_it_false() -> None:
    relationship, _, _, _ = compare_claim_pair(
        _claim(normalized_value="0.064"),
        _claim(normalized_value="0.065", evidence_json=json.dumps({"text": "second advance estimate"})),
    )
    assert relationship == "RECONCILES"


def test_role_ending_event_supersedes_prior_role() -> None:
    relationship, _, _, _ = compare_claim_pair(
        _claim(subject="Suvir Suren Sujan", predicate="director_role", period="2022-05-14", value_type="semantic", normalized_value="director", evidence_json=json.dumps({"text": "director"})),
        _claim(subject="Suvir Suren Sujan", predicate="director_role", period="2023-08-24", value_type="semantic", normalized_value="ceased", evidence_json=json.dumps({"text": "resigned"})),
    )
    assert relationship == "SUPERSEDES"


def test_live_sqlite_relationship_uses_precision_and_aggregates_evidence(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "knowledge.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", ("d", "w", "source.pdf", "hash", "complete", now))
            for claim_id, value, precision, evidence in (
                ("c1", "81415380000", 2, "Revenue 81,415.38 million"),
                ("c2", "81420000000", 0, "Revenue 8,142 crore"),
            ):
                conn.execute(
                    """INSERT INTO claims
                    (id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,precision,period,modality,scope,evidence_json,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (claim_id, "w", "d", "Delhivery", "revenue_from_services", value, value, "number", "INR", precision, "FY24", "actual", "consolidated", json.dumps({"text": evidence}), now),
                )
                conn.execute("INSERT INTO claims_fts(claim_id,workspace_id,subject,predicate,raw_value,period,modality,scope) VALUES(?,?,?,?,?,?,?,?)", (claim_id, "w", "Delhivery", "revenue_from_services", value, "FY24", "actual", "consolidated"))
        assess_relationships("w")
        rebuild_workspace("w")
        with db() as conn:
            relationship = conn.execute("SELECT relationship_type FROM relationships WHERE workspace_id='w'").fetchone()
        result = resolve_fact("w", "Delhivery", "revenue_from_services", "FY24")
        assert relationship["relationship_type"] == "CORROBORATES"
        assert result["decision"] == "allow"
        assert "CORROBORATED" in result["reason_codes"]
        assert len(result["evidence"]) == 2
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)
