from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app import budget
from app.budget import estimate_cost, reserve, settle, snapshot
from app.config import settings
from app.db import db, init_db


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


def test_settlement_cannot_exceed_configured_cap(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "cap.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        spent = reserve(None, "extraction", "test-model", "spent-hash", 19.9)
        settle(spent, 19.9)
        reservation = reserve(None, "extraction", "test-model", "cap-hash", 0.1)
        settle(reservation, 2.0)
        result = snapshot()
        assert result["reserved_usd"] == 0
        assert result["spent_usd"] == result["limit_usd"]
        with db() as conn:
            row = conn.execute("SELECT status,estimated_cost FROM model_calls WHERE id=?", (reservation.id,)).fetchone()
        assert row["status"] == "budget_capped"
        assert abs(row["estimated_cost"] - 0.1) < 1e-9
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_estimate_cost_reserves_configured_retry_envelope(monkeypatch) -> None:
    configured = replace(
        settings,
        provider_retry_attempts=3,
        ai_input_price_per_million=1.0,
        ai_output_price_per_million=1.0,
    )
    monkeypatch.setattr(budget, "settings", configured)
    assert estimate_cost(4000, 1000) == 0.006
