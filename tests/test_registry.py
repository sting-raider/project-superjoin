from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.db import db, init_db, utc_now
from app.registry import (
    _registry_embeddings,
    _resolve_staged,
    conceptual_predicate,
    normalize_claim_frame,
    observe_claim_schema,
    resolve_entity,
    resolve_predicate,
)


def _use_database(path: Path):
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", path)
    object.__setattr__(settings, "upload_dir", path.parent / "uploads")
    init_db()
    with db() as conn:
        conn.execute(
            "INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)",
            ("w", "Generalization", utc_now()),
        )
    return original_database, original_upload


def _restore_database(original_database: Path, original_upload: Path) -> None:
    object.__setattr__(settings, "database_path", original_database)
    object.__setattr__(settings, "upload_dir", original_upload)


def test_unseen_predicate_is_immediately_usable_without_code_change(tmp_path: Path) -> None:
    original_database, original_upload = _use_database(tmp_path / "registry.sqlite3")
    try:
        first = observe_claim_schema(
            "w",
            "Nimbus Cloud",
            "annual_recurring_revenue",
            "money",
            {"text": "Annual recurring revenue reached $42 million."},
        )
        second = resolve_predicate("w", "annual recurring revenue", "money")
        assert first["predicate"]["status"] == "resolved"
        assert first["predicate"]["relation"] == "new"
        assert second["id"] == first["predicate"]["id"]
        assert second["match"] == "exact"
    finally:
        _restore_database(original_database, original_upload)


def test_structured_context_does_not_pollute_predicate_identity() -> None:
    assert conceptual_predicate(
        "estimated_p_l_charge_for_fy27", "FY27", "estimated"
    ) == "p_l_charge"
    assert conceptual_predicate(
        "total_csr_spent_fy2024", "FY2024", "reported"
    ) == "total_csr_spent"
    assert conceptual_predicate(
        "year_over_year_change", "FY2024", "reported"
    ) == "year_over_year_change"


def test_metric_bearing_subject_normalizes_to_entity_metric_frame() -> None:
    assert normalize_claim_frame(
        "Northstar Works furnace utilization FY26",
        "projected at",
        "FY26",
        "projected",
        "Northstar Works",
    ) == ("Northstar Works", "furnace_utilization")
    assert normalize_claim_frame(
        "Nimbus Cloud",
        "annual recurring revenue",
        "FY26",
        "reported",
        "company",
    ) == ("Nimbus Cloud", "annual_recurring_revenue")


def test_legal_suffix_alias_does_not_merge_a_distinct_scope(tmp_path: Path) -> None:
    original_database, original_upload = _use_database(tmp_path / "legal-alias.sqlite3")
    try:
        base = observe_claim_schema("w", "Northstar", "arr", "money")["entity"]
        assert resolve_entity("w", "Northstar Limited")["id"] == base["id"]
        holdings = observe_claim_schema(
            "w", "Northstar Holdings Limited", "arr", "money"
        )["entity"]
        assert holdings["id"] != base["id"]
    finally:
        _restore_database(original_database, original_upload)


def test_embedding_similarity_cannot_confirm_equivalence(monkeypatch, tmp_path: Path) -> None:
    original_database, original_upload = _use_database(tmp_path / "embedding-registry.sqlite3")
    try:
        observe_claim_schema(
            "w", "Nimbus Cloud", "net_revenue_retention", "percentage"
        )["predicate"]
        monkeypatch.setattr(
            "app.registry._embedding_candidates",
            lambda source, candidates, run_id: [
                {**candidates[0], "score": 0.97, "lane": "embedding"}
            ],
        )

        monkeypatch.setattr("app.registry._semantic_resolution", lambda *args: None)
        result = resolve_predicate("w", "customer dollar retention", "percentage")
        assert result["id"] is None
        assert result["status"] == "uncertain"
        assert result["relation"] == "uncertain"
    finally:
        _restore_database(original_database, original_upload)


def test_reordered_predicate_tokens_require_semantic_confirmation(monkeypatch, tmp_path: Path) -> None:
    original_database, original_upload = _use_database(tmp_path / "lexical-registry.sqlite3")
    try:
        observe_claim_schema("w", "Example", "imports_from_exports", "number")
        monkeypatch.setattr("app.registry._embedding_candidates", lambda *args: [])
        monkeypatch.setattr("app.registry._semantic_resolution", lambda *args: None)
        result = resolve_predicate("w", "exports_from_imports", "number")
        assert result["id"] is None
        assert result["relation"] == "uncertain"
    finally:
        _restore_database(original_database, original_upload)


def test_semantic_narrower_result_creates_a_distinct_predicate(monkeypatch, tmp_path: Path) -> None:
    original_database, original_upload = _use_database(tmp_path / "semantic-registry.sqlite3")
    try:
        broad = observe_claim_schema(
            "w", "Foundry Group", "manufacturing_capacity", "number"
        )["predicate"]
        monkeypatch.setattr("app.registry._embedding_candidates", lambda *args: [])
        monkeypatch.setattr(
            "app.registry._semantic_resolution",
            lambda workspace_id, kind, source, candidates, value_kind, run_id: {
                "id": broad["id"],
                "key": source,
                "canonical_name": source,
                "status": "new",
                "match": "semantic",
                "relation": "narrower",
                "value_kind": value_kind,
                "reason": "This measurement is scoped to one production line.",
            },
        )
        result = observe_claim_schema(
            "w", "Foundry Group", "manufacturing_line_capacity", "number"
        )["predicate"]
        assert result["status"] == "resolved"
        assert result["relation"] == "narrower"
        assert result["id"] != broad["id"]
        with db() as conn:
            decision = conn.execute(
                "SELECT action,target_id FROM registry_decisions WHERE kind='predicate' AND source_key='manufacturing_line_capacity' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        assert decision["action"] == "narrower"
        assert decision["target_id"] == broad["id"]
    finally:
        _restore_database(original_database, original_upload)


def test_registry_embeddings_batch_missing_strings_in_one_call(
    monkeypatch, tmp_path: Path
) -> None:
    original_database, original_upload = _use_database(tmp_path / "batch.sqlite3")
    calls: list[list[str]] = []
    try:
        monkeypatch.setattr("app.registry.available", lambda role=None: role == "embedding")

        def fake_embed(texts, model=None):
            calls.append(texts)
            return type(
                "Result",
                (),
                {
                    "data": {
                        "data": [
                            {"index": index, "embedding": [float(index + 1), 1.0]}
                            for index, _ in enumerate(texts)
                        ]
                    },
                    "estimated_cost": 0.001,
                    "input_tokens": 4,
                    "output_tokens": 0,
                    "latency_ms": 10,
                    "attempts": 1,
                },
            )()

        monkeypatch.setattr("app.registry.embed", fake_embed)
        vectors = _registry_embeddings(["Nimbus Cloud", "ARR", "Nimbus Cloud"], None)

        assert calls == [["Nimbus Cloud", "ARR"]]
        assert set(vectors) == {"Nimbus Cloud", "ARR"}
        assert all(round(sum(value * value for value in vector), 6) == 1 for vector in vectors.values())
    finally:
        _restore_database(original_database, original_upload)


def test_unrelated_concept_is_created_without_semantic_round_trip(
    monkeypatch, tmp_path: Path
) -> None:
    original_database, original_upload = _use_database(tmp_path / "unrelated.sqlite3")
    try:
        observe_claim_schema("w", "Example", "manufacturing_capacity", "number")
        monkeypatch.setattr("app.registry._embedding_candidates", lambda *args: [])
        monkeypatch.setattr(
            "app.registry._semantic_resolution",
            lambda *args: (_ for _ in ()).throw(
                AssertionError("semantic resolver called for unrelated concept")
            ),
        )

        result = resolve_predicate("w", "employee_churn_rate", "percentage")

        assert result["status"] == "new"
        assert result["relation"] == "new"
    finally:
        _restore_database(original_database, original_upload)


def test_ingestion_semantic_budget_preserves_excess_ambiguity_as_distinct(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.registry._embedding_candidates", lambda *args: [])
    monkeypatch.setattr(
        "app.registry._semantic_resolution",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("semantic resolver exceeded ingestion budget")
        ),
    )

    result = _resolve_staged(
        "w",
        "predicate",
        "manufacturing_line_capacity",
        [{"id": "predicate-capacity", "label": "manufacturing_capacity"}],
        "run",
        "number",
        semantic_budget=[0],
    )

    assert result["status"] == "new"
    assert result["match"] == "semantic_budget_deferred"
