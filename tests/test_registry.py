from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.db import db, init_db, utc_now
from app.registry import observe_claim_schema, resolve_predicate


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
