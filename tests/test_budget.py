from __future__ import annotations

from pathlib import Path

from app.budget import reserve, settle, snapshot
from app.config import settings
from app.db import init_db


def test_settlement_is_idempotent(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "budget.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        reservation = reserve(None, "extraction", "test-model", "input-hash", 0.25)
        settle(reservation, 0.10, input_tokens=10, output_tokens=5)
        first = snapshot()
        settle(reservation, 0.10, input_tokens=10, output_tokens=5)
        second = snapshot()
        assert first == second
        assert second["reserved_usd"] == 0
        assert second["spent_usd"] == 0.10
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)
