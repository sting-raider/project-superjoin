import json
from pathlib import Path

from app.config import settings
from app.db import db, init_db, utc_now
from app.knowledge import assess_relationships, compare_claim_pair, rebuild_workspace, resolve_fact
from app.providers import ProviderResult


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


def test_same_explicit_context_does_not_infer_a_hidden_vintage() -> None:
    relationship, _, _, _ = compare_claim_pair(
        _claim(normalized_value="0.064"),
        _claim(normalized_value="0.065", evidence_json=json.dumps({"text": "second advance estimate"})),
    )
    assert relationship == "CONTRADICTS"


def test_temporal_semantic_change_abstains_for_reasoning_lane() -> None:
    relationship, _, _, _ = compare_claim_pair(
        _claim(subject="Suvir Suren Sujan", predicate="director_role", period="2022-05-14", value_type="semantic", normalized_value="director", evidence_json=json.dumps({"text": "director"})),
        _claim(subject="Suvir Suren Sujan", predicate="director_role", period="2023-08-24", value_type="semantic", normalized_value="ceased", evidence_json=json.dumps({"text": "resigned"})),
    )
    assert relationship == "UNRELATED"


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


def test_visual_only_evidence_requires_review(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "visual.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        evidence = json.dumps([{"kind": "visual-region", "precision": "visual-region", "text": "A chart value"}])
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute("INSERT INTO facts(id,workspace_id,subject,predicate,normalized_value,display_value,value_type,unit,period,modality,scope,status,reason,evidence_json,revision,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("f", "w", "India", "real_gdp_growth", "0.065", "6.5%", "percentage", "%", "FY26", "forecast", "India", "SUPPORTED", "Visual extraction needs review.", evidence, 1, now))
            conn.execute("INSERT INTO fact_versions(id,fact_id,revision,normalized_value,display_value,status,reason,knowledge_revision,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("f-v1", "f", 1, "0.065", "6.5%", "SUPPORTED", "Visual extraction needs review.", 1, evidence, now))
        result = resolve_fact("w", "India", "real_gdp_growth", "FY26")
        assert result["decision"] == "needs_review"
        assert result["safe_to_use"] is False
        assert "VISUAL_EVIDENCE_REQUIRES_REVIEW" in result["reason_codes"]
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_known_at_revision_returns_historical_fact_version(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "history.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        old_evidence = json.dumps([{"text": "First report: 6.4%", "precision": "page-only"}])
        new_evidence = json.dumps([{"text": "Restated report: 6.5%", "precision": "page-only"}])
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,active_revision,created_at) VALUES(?,?,?,?)", ("w", "Workspace", 2, now))
            conn.execute("INSERT INTO facts(id,workspace_id,subject,predicate,normalized_value,display_value,value_type,unit,period,modality,scope,status,reason,evidence_json,revision,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("f", "w", "India", "real_gdp_growth", "0.065", "6.5%", "percentage", "%", "FY25", "estimate", "India", "SUPPORTED", "Latest", new_evidence, 2, now))
            conn.execute("INSERT INTO fact_versions(id,fact_id,revision,normalized_value,display_value,status,reason,knowledge_revision,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("f-v1", "f", 1, "0.064", "6.4%", "SUPPORTED", "First", 1, old_evidence, now))
            conn.execute("INSERT INTO fact_versions(id,fact_id,revision,normalized_value,display_value,status,reason,knowledge_revision,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("f-v2", "f", 2, "0.065", "6.5%", "SUPPORTED", "Latest", 2, new_evidence, now))
        historical = resolve_fact("w", "India", "real_gdp_growth", "FY25", known_at_revision=1)
        current = resolve_fact("w", "India", "real_gdp_growth", "FY25")
        assert historical["decision"] == "allow"
        assert historical["fact_version_id"] == "f-v1"
        assert historical["value"] == "0.064"
        assert current["fact_version_id"] == "f-v2"
        assert current["value"] == "0.065"
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_reasoning_role_can_resolve_deterministic_context_abstention(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "reasoning.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    calls = []
    try:
        init_db()
        now = utc_now()
        evidence = json.dumps({"text": "The FY25 first advance estimate is 6.4%."})
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", ("d", "w", "source.pdf", "hash", "complete", now))
            for claim_id, period, value in (("c1", "FY25", "0.064"), ("c2", "FY26", "0.065")):
                conn.execute("INSERT INTO claims(id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,period,modality,scope,evidence_json,extraction_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (claim_id, "w", "d", "India", "real_gdp_growth", value, value, "percentage", "%", period, "estimate", "India", evidence, "accepted", now))
        monkeypatch.setattr("app.knowledge.available", lambda role=None: role == "reasoning")

        def fake_chat(role, system, user, model=None, max_output_tokens=1200):
            calls.append((role, user))
            return ProviderResult(data={"relationship_type": "RECONCILES", "reason": "The claims refer to adjacent fiscal periods and should remain contextual.", "dimensions": {"period": "DIFFERENT"}, "confidence": 0.8, "evidence_claim_ids": ["c1", "c2"]}, model=model or "fake", estimated_cost=0.001)

        monkeypatch.setattr("app.knowledge.structured_chat", fake_chat)
        inserted = assess_relationships("w")
        with db() as conn:
            relationship = conn.execute("SELECT relationship_type,reason FROM relationships WHERE workspace_id='w'").fetchone()
        assert inserted == 1
        assert relationship["relationship_type"] == "RECONCILES"
        assert len(calls) == 1
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)
