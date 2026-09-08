from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _elapsed_seconds(start: str, end: str) -> float:
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 3)


def profile_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    run = conn.execute(
        """SELECT id,workspace_id,document_id,mode,status,progress,message,
        created_at,updated_at FROM runs WHERE id=?""",
        (run_id,),
    ).fetchone()
    if run is None:
        raise ValueError(f"Run not found: {run_id}")
    call_rows = conn.execute(
        """SELECT role,status,COUNT(*) AS calls,
        SUM(COALESCE(request_chars,0)) AS request_chars,
        SUM(COALESCE(input_tokens,0)) AS input_tokens,
        SUM(COALESCE(output_tokens,0)) AS output_tokens,
        SUM(COALESCE(latency_ms,0)) AS provider_latency_ms,
        SUM(COALESCE(attempts,1)) AS attempts,
        SUM(COALESCE(cache_hit,0)) AS cache_hits,
        ROUND(SUM(COALESCE(estimated_cost,0)),6) AS estimated_cost_usd
        FROM model_calls WHERE run_id=? GROUP BY role,status ORDER BY role,status""",
        (run_id,),
    ).fetchall()
    batch = conn.execute(
        """SELECT COUNT(*) AS batches,
        SUM(CASE WHEN status='complete' THEN 1 ELSE 0 END) AS completed,
        SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
        SUM(claim_count) AS extracted_claims,
        SUM(page_end-page_start+1) AS page_spans
        FROM extraction_batches WHERE run_id=?""",
        (run_id,),
    ).fetchone()
    document = conn.execute(
        "SELECT page_count,status FROM documents WHERE id=?", (run["document_id"],)
    ).fetchone()
    claims = conn.execute(
        """SELECT COUNT(*) AS count,
        SUM(CASE WHEN extraction_status='accepted' THEN 1 ELSE 0 END) AS accepted,
        SUM(CASE WHEN extraction_status='provisional' THEN 1 ELSE 0 END) AS provisional
        FROM claims WHERE document_id=?""",
        (run["document_id"],),
    ).fetchone()
    stages = []
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_stage_timings'"
    ).fetchone():
        stages = [
            dict(row)
            for row in conn.execute(
                """SELECT stage,duration_ms,current_count,total_count,counters_json
                FROM run_stage_timings WHERE run_id=? ORDER BY started_at,stage""",
                (run_id,),
            ).fetchall()
        ]
        for stage in stages:
            try:
                stage["counters"] = json.loads(stage.pop("counters_json") or "{}")
            except json.JSONDecodeError:
                stage["counters"] = {}
    return {
        "run": dict(run),
        "observed_elapsed_seconds": _elapsed_seconds(run["created_at"], run["updated_at"]),
        "document": dict(document) if document else None,
        "model_calls": [dict(row) for row in call_rows],
        "extraction": dict(batch) if batch else {},
        "claims": {key: int(claims[key] or 0) for key in claims},
        "persisted_claims": int(claims["count"] or 0),
        "stages": stages,
        "network_calls": sum(
            int(row["calls"])
            for row in call_rows
            if row["status"] not in {"cache_hit", "reserved"}
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile recorded Project SuperJoin runs")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with sqlite3.connect(args.database) as conn:
        report = {
            "schema_version": "1.0",
            "database": str(args.database),
            "runs": [profile_run(conn, run_id) for run_id in args.run_ids],
        }
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
