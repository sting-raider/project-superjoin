import json
from pathlib import Path

from app.config import settings
from app.db import db, init_db, utc_now
from app.knowledge import (
    _relationship_pairs,
    assess_relationships,
    compare_claim_pair,
    rebuild_workspace,
    resolve_fact,
)
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
        _claim(
            normalized_value="0.064",
            evidence_json=json.dumps({"text": "published estimate"}),
        ),
        _claim(
            normalized_value="0.065",
            evidence_json=json.dumps({"text": "published estimate"}),
        ),
    )
    assert relationship == "CONTRADICTS"


def test_equivalent_fiscal_labels_and_modalities_corroborate_unseen_metric() -> None:
    relationship, _, dimensions, _ = compare_claim_pair(
        _claim(subject="Nimbus Cloud", predicate="net_revenue_retention", period="FY26", modality="asserted", normalized_value="1.12"),
        _claim(subject="Nimbus Cloud", predicate="net_revenue_retention", period="FY2026", modality="actual", normalized_value="1.12"),
    )
    assert relationship == "CORROBORATES"
    assert dimensions["period"] == "MATCH"
    assert dimensions["modality"] == "MATCH"


def test_missing_semantic_normalizations_never_create_false_corroboration() -> None:
    relationship, _, dimensions, _ = compare_claim_pair(
        _claim(subject="Northstar Manufacturing", predicate="appointed_executive", period="FY2026", modality="reported", value_type="semantic", normalized_value=None),
        _claim(subject="Northstar Manufacturing", predicate="appointed_executive", period="FY2026", modality="reported", value_type="semantic", normalized_value=None),
    )
    assert relationship == "CONTRADICTS"
    assert dimensions["value"] == "UNKNOWN"


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
            for document_id in ("d1", "d2"):
                conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", (document_id, "w", f"{document_id}.pdf", document_id, "complete", now))
            for claim_id, document_id, value, precision, evidence in (
                ("c1", "d1", "81415380000", 2, "Revenue 81,415.38 million"),
                ("c2", "d2", "81420000000", 0, "Revenue 8,142 crore"),
            ):
                conn.execute(
                    """INSERT INTO claims
                    (id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,precision,period,modality,scope,evidence_json,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (claim_id, "w", document_id, "Delhivery", "revenue_from_services", value, value, "number", "INR", precision, "FY24", "actual", "consolidated", json.dumps({"text": evidence}), now),
                )
                conn.execute("INSERT INTO claims_fts(claim_id,workspace_id,subject,predicate,raw_value,period,modality,scope) VALUES(?,?,?,?,?,?,?,?)", (claim_id, "w", "Delhivery", "revenue_from_services", value, "FY24", "actual", "consolidated"))
        assess_relationships("w")
        assert assess_relationships("w") == 0
        rebuild_workspace("w")
        with db() as conn:
            relationship = conn.execute("SELECT relationship_type FROM relationships WHERE workspace_id='w'").fetchone()
            facts = conn.execute("SELECT id FROM facts WHERE workspace_id='w' AND active=1").fetchall()
            memberships = conn.execute("SELECT claim_id FROM fact_memberships").fetchall()
        result = resolve_fact("w", "Delhivery", "revenue_from_services", "FY24")
        assert relationship["relationship_type"] == "CORROBORATES"
        assert len(facts) == 1
        assert {row["claim_id"] for row in memberships} == {"c1", "c2"}
        assert result["decision"] == "allow"
        assert "CORROBORATED" in result["reason_codes"]
        assert len(result["evidence"]) == 2
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_conflicting_unseen_metric_is_one_fact_family_with_alternatives(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "fact-family.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            for document_id in ("d1", "d2"):
                conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", (document_id, "w", f"{document_id}.pdf", document_id, "complete", now))
            for claim_id, document_id, value in (("c1", "d1", "0.028"), ("c2", "d2", "0.031")):
                evidence = json.dumps({"text": f"Gross customer churn was {value}."})
                conn.execute(
                    """INSERT INTO claims
                    (id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,period,modality,scope,evidence_json,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (claim_id, "w", document_id, "Nimbus Cloud", "gross_customer_churn", value, value, "percentage", "%", "FY2026", "actual", "consolidated", evidence, now),
                )
        assess_relationships("w")
        rebuild_workspace("w")
        with db() as conn:
            facts = conn.execute("SELECT * FROM facts WHERE workspace_id='w' AND active=1").fetchall()
            alternatives = json.loads(facts[0]["alternatives_json"])
            memberships = conn.execute("SELECT role FROM fact_memberships").fetchall()
        decision = resolve_fact("w", "Nimbus Cloud", "gross_customer_churn", "FY2026")
        assert len(facts) == 1
        assert facts[0]["status"] == "CONTESTED"
        assert {item["normalized_value"] for item in alternatives} == {"0.028", "0.031"}
        assert {row["role"] for row in memberships} == {"supporting", "alternative"}
        assert decision["decision"] == "block"
        assert len(decision["alternatives"][0]["claim_alternatives"]) == 2
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_confirmed_registry_aliases_share_reasoning_and_fact_family(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "alias-family.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            for document_id in ("d1", "d2"):
                conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", (document_id, "w", f"{document_id}.pdf", document_id, "complete", now))
            conn.execute("INSERT INTO entities(id,workspace_id,canonical_name,created_at) VALUES(?,?,?,?)", ("entity-acme", "w", "Acme Corporation", now))
            conn.execute("INSERT INTO predicates(id,workspace_id,key,value_kind,created_at) VALUES(?,?,?,?,?)", ("predicate-arr", "w", "annual_recurring_revenue", "money", now))
            for index, (subject, predicate) in enumerate((("Acme Corp.", "ARR"), ("ACME Corporation", "annual recurring revenue")), start=1):
                claim_id = f"c{index}"
                evidence = json.dumps({"text": f"{subject} {predicate} was $10 million."})
                conn.execute(
                    """INSERT INTO claims
                    (id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,period,modality,scope,evidence_json,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (claim_id, "w", f"d{index}", subject, predicate, "$10 million", "10000000" if index == 1 else "10", "money", "USD", "FY2026", "actual", "consolidated", evidence, now),
                )
                conn.execute(
                    """INSERT INTO claim_interpretations
                    (id,claim_id,version,subject,predicate,normalized_value,value_type,unit,period,modality,scope,entity_status,predicate_status,eligibility,entity_id,predicate_id,entity_relation,predicate_relation,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"i{index}", claim_id, 1, subject, predicate, "10000000", "money", "USD", "FY2026", "actual", "consolidated", "resolved", "resolved", "eligible", "entity-acme", "predicate-arr", "equivalent", "equivalent", now),
                )
        assess_relationships("w")
        rebuild_workspace("w")
        with db() as conn:
            relationship = conn.execute("SELECT relationship_type FROM relationships").fetchone()
            facts = conn.execute("SELECT subject,predicate FROM facts WHERE active=1").fetchall()
        assert relationship["relationship_type"] == "CORROBORATES"
        assert [(row["subject"], row["predicate"]) for row in facts] == [
            ("Acme Corporation", "annual_recurring_revenue")
        ]
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
            for document_id in ("d1", "d2"):
                conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", (document_id, "w", f"{document_id}.pdf", document_id, "complete", now))
            for claim_id, document_id, period, value in (("c1", "d1", "FY25", "0.064"), ("c2", "d2", "FY26", "0.065")):
                conn.execute("INSERT INTO claims(id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,period,modality,scope,evidence_json,extraction_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (claim_id, "w", document_id, "India", "real_gdp_growth", value, value, "percentage", "%", period, "estimate", "India", evidence, "accepted", now))
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


def test_temporal_status_change_is_a_semantic_review_candidate() -> None:
    from app.knowledge import _needs_semantic_relationship_review

    appointed = {
        "value_type": "semantic",
        "evidence_json": json.dumps({"text": "Morgan Lee was appointed as COO."}),
    }
    resigned = {
        "value_type": "semantic",
        "evidence_json": json.dumps({"text": "Morgan Lee resigned with effect from 1 June."}),
    }

    assert _needs_semantic_relationship_review(appointed, resigned, "UNRELATED")


def test_incremental_relationships_only_rank_prior_documents() -> None:
    new = {
        "id": "new",
        "document_id": "new-doc",
        "period": "FY26",
        "modality": "forecast",
        "normalized_value": "0.06",
        "unit": "%",
    }
    same_document = {**new, "id": "new-2"}
    prior = [
        {
            **new,
            "id": f"old-{index}",
            "document_id": f"old-doc-{index}",
            "period": "FY26" if index < 2 else "FY25",
            "created_at": f"2026-01-{index + 1:02d}",
        }
        for index in range(20)
    ]

    pairs = _relationship_pairs([new, same_document, *prior], "new-doc")

    assert len(pairs) == settings.relationship_candidate_limit * 2
    assert all(left["document_id"] == "new-doc" for left, _ in pairs)
    assert all(right["document_id"] != "new-doc" for _, right in pairs)
    assert {right["id"] for _, right in pairs[:2]} == {"old-0", "old-1"}


def _synthetic_comparison_claim(**overrides):
    claim = {
        "subject": "Northstar Works",
        "predicate": "furnace_utilization",
        "period": "FY26",
        "modality": "forecast",
        "value_type": "percentage",
        "normalized_value": "0.82",
        "precision": 2,
        "evidence_json": json.dumps({"text": "Utilization is forecast at 82 percent."}),
    }
    claim.update(overrides)
    return claim


def test_independent_same_period_forecasts_with_different_values_compete() -> None:
    relationship, reason, dimensions, _ = compare_claim_pair(
        _synthetic_comparison_claim(normalized_value="0.82"),
        _synthetic_comparison_claim(normalized_value="0.79"),
    )
    assert relationship == "CONTRADICTS"
    assert dimensions["period"] == "MATCH"
    assert "neither forecast" in reason.casefold()


def test_same_period_estimate_vintages_reconcile() -> None:
    relationship, reason, _, _ = compare_claim_pair(
        _synthetic_comparison_claim(modality="first_estimate", normalized_value="0.82"),
        _synthetic_comparison_claim(modality="revised_estimate", normalized_value="0.84"),
    )
    assert relationship == "RECONCILES"
    assert "first_estimate" in reason
    assert "revised_estimate" in reason


def test_different_fiscal_periods_do_not_compete() -> None:
    relationship, _, dimensions, _ = compare_claim_pair(
        _synthetic_comparison_claim(period="FY26", normalized_value="0.82"),
        _synthetic_comparison_claim(period="FY2026/27", normalized_value="0.79"),
    )
    assert relationship == "UNRELATED"
    assert dimensions["period"] == "DIFFERENT"


def test_forecast_and_historical_value_do_not_blindly_contradict() -> None:
    relationship, _, _, _ = compare_claim_pair(
        _synthetic_comparison_claim(modality="forecast", normalized_value="0.82"),
        _synthetic_comparison_claim(
            modality="reported",
            normalized_value="0.79",
            evidence_json=json.dumps({"text": "Utilization was 79 percent."}),
        ),
    )
    assert relationship == "UNCERTAIN"


def test_candidate_ranking_retains_closest_context_among_broad_topic_rows() -> None:
    current = {
        **_synthetic_comparison_claim(),
        "id": "current",
        "document_id": "new-document",
        "unit": "%",
        "created_at": "2026-09-01",
    }
    closest = {
        **current,
        "id": "closest",
        "document_id": "closest-document",
        "normalized_value": "0.79",
    }
    broad_rows = [
        {
            **current,
            "id": f"broad-{index}",
            "document_id": f"broad-document-{index}",
            "period": f"FY{40 + index}",
            "modality": "reported",
            "unit": "units",
            "created_at": f"2026-08-{index + 1:02d}",
        }
        for index in range(20)
    ]
    pairs = _relationship_pairs([current, *broad_rows, closest], "new-document")
    assert pairs[0][1]["id"] == "closest"
