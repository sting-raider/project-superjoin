from __future__ import annotations

from pathlib import Path

from app import providers
from app.config import settings
from app.db import db, init_db
from app.seed import (
    advance_replay,
    clear_demo_workspace_data,
    replay_status,
    seed_demo,
    start_replay,
)


def test_demo_relationships_are_replayed_through_generic_engine(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "demo.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        seed_demo()
        with db() as conn:
            relationships = conn.execute(
                "SELECT id,relationship_type FROM relationships ORDER BY relationship_type,id"
            ).fetchall()
        assert {row["relationship_type"] for row in relationships} == {
            "CORROBORATES",
            "CONTRADICTS",
            "RECONCILES",
            "SUPERSEDES",
        }
        assert not {row["id"] for row in relationships} & {
            "rel-revenue-corroborates",
            "rel-gdp-forecast",
            "rel-gdp-vintage",
            "rel-director-supersedes",
        }
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_recorded_replay_uses_scoped_checkpoint_and_preserves_live_workspace(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "replay.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        with db() as conn:
            conn.execute(
                "INSERT INTO workspaces(id,name,description,created_at) VALUES(?,?,?,?)",
                ("live-workspace", "Live workspace", "must survive demo reset", "2026-01-01T00:00:00+00:00"),
            )
        baseline = start_replay()
        assert baseline["stage"] == "baseline_ready"
        assert baseline["recorded"] is True
        with db() as conn:
            documents = conn.execute("SELECT id FROM documents WHERE workspace_id='delhivery' ORDER BY id").fetchall()
        assert [row["id"] for row in documents] == ["delhivery-annual", "delhivery-prospectus"]

        replayed = advance_replay()
        assert replayed["stage"] == "replayed"
        assert replayed["model_calls"] == 0
        assert replayed["replay_cost_usd"] == 0.0
        with db() as conn:
            documents = conn.execute("SELECT id FROM documents WHERE workspace_id='delhivery' ORDER BY id").fetchall()
            relationship_types = {row["relationship_type"] for row in conn.execute("SELECT relationship_type FROM relationships WHERE workspace_id='delhivery'").fetchall()}
            live = conn.execute("SELECT name FROM workspaces WHERE id='live-workspace'").fetchone()
        assert [row["id"] for row in documents] == ["delhivery-annual", "delhivery-presentation", "delhivery-prospectus"]
        assert "CORROBORATES" in relationship_types
        assert live["name"] == "Live workspace"

        clear_demo_workspace_data()
        assert replay_status()["stage"] == "ready"
        with db() as conn:
            assert conn.execute("SELECT 1 FROM workspaces WHERE id='live-workspace'").fetchone()
            assert conn.execute("SELECT COUNT(*) AS count FROM documents WHERE workspace_id='delhivery'").fetchone()["count"] == 0
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_recorded_replay_is_offline_safe_without_provider_requests(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "offline-replay.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")

    def network_must_not_run(*_args, **_kwargs):
        raise AssertionError("recorded replay attempted a network request")

    try:
        init_db()
        monkeypatch.setattr(providers.urllib.request, "urlopen", network_must_not_run)
        baseline = start_replay()
        replayed = advance_replay()
        assert baseline["recorded"] is True
        assert replayed["stage"] == "replayed"
        assert replayed["model_calls"] == 0
        assert replayed["replay_cost_usd"] == 0.0
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)
