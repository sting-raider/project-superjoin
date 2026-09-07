from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from .config import settings
from .db import db, utc_now


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Reservation:
    id: str
    amount: float


def estimate_cost(input_chars: int, max_output_tokens: int = 1200) -> float:
    """Conservative estimate used before a paid request is dispatched."""

    input_tokens = max(1, input_chars // 4)
    return round((input_tokens / 1_000_000) * settings.ai_input_price_per_million + (max_output_tokens / 1_000_000) * settings.ai_output_price_per_million, 6)


def reserve(run_id: str | None, role: str, model: str, input_hash: str, amount: float) -> Reservation:
    amount = max(0.0, float(amount))
    reservation_id = f"reservation-{uuid.uuid4().hex[:12]}"
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        ledger = conn.execute("SELECT limit_usd,reserved_usd,spent_usd FROM budget_ledger WHERE id=1").fetchone()
        if not ledger or ledger["reserved_usd"] + ledger["spent_usd"] + amount > ledger["limit_usd"] + 1e-9:
            raise BudgetExceeded(f"AI budget exhausted; requested reservation ${amount:.6f}")
        conn.execute("UPDATE budget_ledger SET reserved_usd=reserved_usd+?,updated_at=? WHERE id=1", (amount, utc_now()))
        conn.execute(
            "INSERT INTO model_calls(id,run_id,role,model,input_hash,status,reserved_usd,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (reservation_id, run_id, role, model, input_hash, "reserved", amount, utc_now()),
        )
    return Reservation(reservation_id, amount)


def settle(reservation: Reservation, actual_cost: float, *, status: str = "complete", input_tokens: int | None = None, output_tokens: int | None = None, latency_ms: int | None = None, cache_hit: bool = False) -> None:
    actual_cost = max(0.0, float(actual_cost))
    with db() as conn:
        row = conn.execute("SELECT reserved_usd,status FROM model_calls WHERE id=?", (reservation.id,)).fetchone()
        # Provider retries and background completion callbacks can race. A reservation
        # may be settled only once; completed/failed rows are already accounted for.
        if row is None or row["status"] != "reserved":
            return
        reserved = float(row["reserved_usd"])
        ledger = conn.execute("SELECT limit_usd,reserved_usd,spent_usd FROM budget_ledger WHERE id=1").fetchone()
        if not ledger:
            return
        spendable = max(0.0, float(ledger["limit_usd"]) - float(ledger["spent_usd"]) - max(0.0, float(ledger["reserved_usd"]) - reserved))
        accounted_cost = min(actual_cost, spendable)
        final_status = "budget_capped" if actual_cost > accounted_cost + 1e-9 and status == "complete" else status
        conn.execute("UPDATE budget_ledger SET reserved_usd=MAX(0,reserved_usd-?),spent_usd=spent_usd+?,updated_at=? WHERE id=1", (reserved, accounted_cost, utc_now()))
        conn.execute("UPDATE model_calls SET status=?,reserved_usd=0,estimated_cost=?,input_tokens=?,output_tokens=?,latency_ms=?,cache_hit=? WHERE id=?", (final_status, accounted_cost, input_tokens, output_tokens, latency_ms, int(cache_hit), reservation.id))


def snapshot() -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM budget_ledger WHERE id=1").fetchone()
    if not row:
        return {"limit_usd": settings.ai_budget_usd, "reserved_usd": 0.0, "spent_usd": 0.0, "remaining_usd": settings.ai_budget_usd}
    return {"limit_usd": row["limit_usd"], "reserved_usd": row["reserved_usd"], "spent_usd": row["spent_usd"], "remaining_usd": max(0.0, row["limit_usd"] - row["reserved_usd"] - row["spent_usd"])}
