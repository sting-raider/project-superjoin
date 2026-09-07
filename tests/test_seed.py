from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.db import db, init_db
from app.seed import seed_demo


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
