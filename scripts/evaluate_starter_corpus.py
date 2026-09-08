"""Run the locally prepared starter corpus through the production pipeline.

This evaluation-only utility may read starter metadata. Production modules do
not import it, and source PDFs remain under the ignored data directory.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.db import db, init_db, utc_now
from app.pipeline import process_document
from app.providers import available

ROOT = Path(__file__).resolve().parents[1]


def _evidence_page(value: str) -> int | None:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return int(parsed.get("pdf_page")) if isinstance(parsed, dict) and parsed.get("pdf_page") else None


def evaluate(
    prepared_path: Path,
    source_manifest_path: Path,
    case_reference_path: Path,
    database_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    case_reference = json.loads(case_reference_path.read_text(encoding="utf-8"))
    if not prepared.get("verified"):
        raise SystemExit("Prepared manifest is not verified")
    if database_path.exists():
        raise SystemExit("Evaluation database already exists; choose a new --database path to preserve prior results and budget accounting")
    object.__setattr__(settings, "database_path", database_path)
    object.__setattr__(settings, "upload_dir", database_path.parent / "uploads-eval")
    init_db()
    source_by_id = {item["id"]: item for item in source_manifest["documents"]}
    workspace_ids = sorted({item["workspace_id"] for item in source_manifest["documents"]})
    with db() as conn:
        for workspace_id in workspace_ids:
            conn.execute(
                "INSERT INTO workspaces(id,name,description,created_at) VALUES(?,?,?,?)",
                (workspace_id, workspace_id.replace("-", " ").title(), "Local corpus evaluation", utc_now()),
            )
    document_results = []
    started = time.perf_counter()
    for prepared_document in prepared["documents"]:
        metadata = source_by_id[prepared_document["id"]]
        path = Path(prepared_document["path"])
        run_id = f"eval-{metadata['id']}"
        with db() as conn:
            conn.execute(
                """INSERT INTO documents
                (id,workspace_id,name,publisher,source_url,sha256,status,stored_path,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    metadata["id"], metadata["workspace_id"], metadata["title"],
                    metadata["publisher"], metadata["source_url"], prepared_document["sha256"],
                    "queued", str(path), utc_now(),
                ),
            )
            conn.execute(
                "INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, metadata["workspace_id"], metadata["id"], "corpus-eval", "queued", 0, "Queued", utc_now(), utc_now()),
            )
        document_started = time.perf_counter()
        process_document(run_id, metadata["id"], metadata["workspace_id"], path.read_bytes(), metadata["title"])
        with db() as conn:
            run = dict(conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
            counts = {
                "pages": conn.execute("SELECT COUNT(*) AS n FROM page_artifacts WHERE document_id=?", (metadata["id"],)).fetchone()["n"],
                "accepted_claims": conn.execute("SELECT COUNT(*) AS n FROM claims WHERE document_id=? AND extraction_status='accepted'", (metadata["id"],)).fetchone()["n"],
                "quarantined_claims": conn.execute("SELECT COUNT(*) AS n FROM claims WHERE document_id=? AND extraction_status='quarantined'", (metadata["id"],)).fetchone()["n"],
                "visual_review_pages": conn.execute("SELECT COUNT(*) AS n FROM page_artifacts WHERE document_id=? AND disposition='visual-review'", (metadata["id"],)).fetchone()["n"],
                "extraction_batches": conn.execute("SELECT COUNT(*) AS n FROM extraction_batches WHERE document_id=?", (metadata["id"],)).fetchone()["n"],
            }
        document_results.append(
            {
                "document_id": metadata["id"],
                "sha256": prepared_document["sha256"],
                "status": run["status"],
                "message": run["message"],
                "duration_seconds": round(time.perf_counter() - document_started, 3),
                **counts,
            }
        )
    expected_results, matched_claim_ids = _measure_expected_claims(
        case_reference.get("claims", [])
    )
    relationship_results = _measure_expected_relationships(
        case_reference.get("relationships", []), matched_claim_ids
    )
    with db() as conn:
        totals = {
            "documents": conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"],
            "pages": conn.execute("SELECT COUNT(*) AS n FROM page_artifacts").fetchone()["n"],
            "accepted_claims": conn.execute("SELECT COUNT(*) AS n FROM claims WHERE extraction_status='accepted'").fetchone()["n"],
            "quarantined_claims": conn.execute("SELECT COUNT(*) AS n FROM claims WHERE extraction_status='quarantined'").fetchone()["n"],
            "active_fact_families": conn.execute("SELECT COUNT(*) AS n FROM facts WHERE active=1").fetchone()["n"],
            "relationships": conn.execute("SELECT COUNT(*) AS n FROM relationships").fetchone()["n"],
            "visual_review_pages": conn.execute("SELECT COUNT(*) AS n FROM page_artifacts WHERE disposition='visual-review'").fetchone()["n"],
        }
        call_rows = conn.execute(
            "SELECT role,status,attempts,estimated_cost,latency_ms FROM model_calls"
        ).fetchall()
    provider_telemetry: dict[str, dict[str, Any]] = {}
    for row in call_rows:
        lane = provider_telemetry.setdefault(
            row["role"],
            {
                "calls": 0,
                "complete": 0,
                "failed": 0,
                "attempts": 0,
                "estimated_cost_usd": 0.0,
                "latency_ms": 0,
            },
        )
        lane["calls"] += 1
        lane["complete"] += int(row["status"] == "complete")
        lane["failed"] += int(row["status"] not in {"complete", "cache_hit"})
        lane["attempts"] += max(1, int(row["attempts"] or 1))
        lane["estimated_cost_usd"] += float(row["estimated_cost"] or 0.0)
        lane["latency_ms"] += int(row["latency_ms"] or 0)
    for lane in provider_telemetry.values():
        lane["estimated_cost_usd"] = round(lane["estimated_cost_usd"], 6)
    unavailable = [
        role
        for role in ("extraction", "reasoning", "vision", "embedding")
        if not available(role)
    ]
    exact_claims = sum(item["exact_match"] for item in expected_results)
    result = {
        "report_version": "1.0",
        "project": "Project SuperJoin",
        "kind": "starter-corpus-production-pipeline",
        "code_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "reference_kind": case_reference.get("reference_kind", "evaluation-only reference"),
        "generated_at": utc_now(),
        "provider_roles": {role: available(role) for role in ("extraction", "reasoning", "vision", "embedding")},
        "provider_models": {
            "extraction": settings.extraction_model,
            "reasoning": settings.reasoning_model,
            "vision": settings.vision_model,
            "embedding": settings.embedding_model,
        },
        "provider_telemetry": provider_telemetry,
        "mode": "live-provider" if available("extraction") else "offline-generic-fallback",
        "anti_leakage": "Starter metadata is read only after production processing for measurement.",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "totals": totals,
        "documents": document_results,
        "expected_claims": {
            "exact_matches": exact_claims,
            "total": len(expected_results),
            "recall": round(exact_claims / len(expected_results), 4) if expected_results else None,
            "items": expected_results,
        },
        "expected_relationships": relationship_results,
        "limitations": [
            f"The {role} provider role was not configured; dependent work remains unavailable or deterministic-only."
            for role in unavailable
        ]
        + ([
            "Offline deterministic hints are intentionally not a substitute for open-schema semantic extraction."
        ] if not available("extraction") else [])
        + ([
            "Relationship results use deterministic comparison only because the reasoning role was not configured."
        ] if not available("reasoning") else [])
        + ([
            "Visual pages remain in review because the configured extraction model is not a vision capability."
        ] if not available("vision") else [])
        + ([
            "Dense retrieval and registry embedding candidates were not evaluated because the embedding role was not configured."
        ] if not available("embedding") else []),
    }
    result["limitations"] = [item for item in result["limitations"] if item]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _measure_expected_claims(
    expected_claims: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    results = []
    matched: dict[str, str] = {}
    with db() as conn:
        for expected in expected_claims:
            rows = conn.execute(
                "SELECT id,subject,predicate,normalized_value,period,evidence_json FROM claims WHERE document_id=?",
                (expected["document_id"],),
            ).fetchall()
            exact = next(
                (
                    row for row in rows
                    if row["subject"].casefold() == expected["subject"].casefold()
                    and row["predicate"].casefold() == expected["predicate"].casefold()
                    and str(row["normalized_value"]) == str(expected["normalized_value"])
                    and row["period"] == expected["period"]
                    and _evidence_page(row["evidence_json"]) == expected["pdf_page"]
                ),
                None,
            )
            value_page = any(
                str(row["normalized_value"]) == str(expected["normalized_value"])
                and _evidence_page(row["evidence_json"]) == expected["pdf_page"]
                for row in rows
            )
            if exact:
                matched[expected["id"]] = exact["id"]
            results.append(
                {
                    "expected_id": expected["id"],
                    "document_id": expected["document_id"],
                    "pdf_page": expected["pdf_page"],
                    "exact_match": bool(exact),
                    "value_and_page_match": value_page,
                    "matched_claim_id": exact["id"] if exact else None,
                }
            )
    return results, matched


def _measure_expected_relationships(
    expected_relationships: list[dict[str, Any]], matched_claim_ids: dict[str, str]
) -> dict[str, Any]:
    items = []
    with db() as conn:
        for expected in expected_relationships:
            left = matched_claim_ids.get(expected["claim_a"])
            right = matched_claim_ids.get(expected["claim_b"])
            row = None
            if left and right:
                row = conn.execute(
                    "SELECT relationship_type FROM relationships WHERE (claim_a=? AND claim_b=?) OR (claim_a=? AND claim_b=?)",
                    (left, right, right, left),
                ).fetchone()
            items.append(
                {
                    "expected_id": expected["id"],
                    "expected_type": expected["relationship_type"],
                    "actual_type": row["relationship_type"] if row else None,
                    "match": bool(row and row["relationship_type"] == expected["relationship_type"]),
                }
            )
    matches = sum(item["match"] for item in items)
    return {"matches": matches, "total": len(items), "accuracy": round(matches / len(items), 4) if items else None, "items": items}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=ROOT / "data" / "starter" / "prepared-manifest.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "datasets" / "starter" / "manifest.json")
    parser.add_argument(
        "--reference",
        type=Path,
        default=ROOT / "evals" / "fixtures" / "starter_case_reference.json",
    )
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "starter-corpus-eval.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "evals" / "reports" / "starter-corpus-e2e.json")
    args = parser.parse_args()
    print(
        json.dumps(
            evaluate(
                args.prepared,
                args.manifest,
                args.reference,
                args.database,
                args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
