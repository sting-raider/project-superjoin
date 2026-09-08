"""Measure the provider-free synthetic gold contract without mutating the app database.

The fixture is deliberately out of domain for the starter corpus.  This runner
measures the deterministic hint and normalization lane only; semantic extraction
is reported as provider-required instead of being silently treated as a miss or
as a successful model result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from app.parser import ParsedPage, candidate_claims
from app.pipeline import build_extraction_batches

ROOT = Path(__file__).resolve().parents[1]


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _load_gold(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for record in records:
        if record.get("kind") != "claim":
            raise ValueError(f"Unsupported gold record kind: {record.get('kind')}")
        if not (record.get("annotation") or {}).get("synthetic"):
            raise ValueError("This offline runner accepts only explicitly synthetic records")
    return records


def evaluate(gold_path: Path, fixture_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    gold = _load_gold(gold_path)
    pages_by_number = {int(number): str(text) for number, text in fixture["pages"].items()}
    pages = [
        ParsedPage(
            index,
            1000,
            1000,
            pages_by_number.get(index + 1, "No material assertions on this page."),
            [],
            0.95,
            [],
        )
        for index in range(max(pages_by_number))
    ]
    candidates = [candidate for page in pages for candidate in candidate_claims(page)]
    batches = build_extraction_batches(pages, candidates)
    numeric_gold = [record for record in gold if (record["annotation"].get("value_type") or "").casefold() != "semantic"]
    semantic_gold = [record for record in gold if (record["annotation"].get("value_type") or "").casefold() == "semantic"]
    matched: list[dict[str, Any]] = []
    for record in numeric_gold:
        annotation = record["annotation"]
        page_number = int(record["source"]["pdf_page"])
        candidates_for_claim = [
            candidate
            for candidate in candidates
            if int((candidate.get("evidence") or {}).get("pdf_page") or 0) == page_number
            and str(candidate.get("normalized_value")) == str(annotation.get("normalized_value"))
        ]
        predicate_match = any(candidate.get("predicate") == annotation.get("predicate") for candidate in candidates_for_claim)
        grounded = any(
            _compact(record["source"].get("text")) in _compact((candidate.get("evidence") or {}).get("text"))
            for candidate in candidates_for_claim
        )
        matched.append(
            {
                "record_id": record["record_id"],
                "page": page_number,
                "value_page_match": bool(candidates_for_claim),
                "predicate_match": predicate_match,
                "grounded": grounded,
                "candidate_predicates": sorted({str(candidate.get("predicate")) for candidate in candidates_for_claim}),
            }
        )
    value_page_matches = sum(item["value_page_match"] for item in matched)
    predicate_matches = sum(item["predicate_match"] for item in matched)
    grounded_matches = sum(item["grounded"] for item in matched)
    max_page = max(pages_by_number)
    return {
        "report_version": "1.0",
        "project": "Project SuperJoin",
        "suite": "synthetic-out-of-domain-gold-v1",
        "source_kind": "synthetic fixture; no starter documents or starter-case metadata",
        "gold_records": len(gold),
        "numeric_records": len(numeric_gold),
        "semantic_records": len(semantic_gold),
        "metrics": {
            "numeric_value_page_recall": round(value_page_matches / len(numeric_gold), 4) if numeric_gold else None,
            "numeric_predicate_accuracy": round(predicate_matches / len(numeric_gold), 4) if numeric_gold else None,
            "grounding_precision_on_value_page_matches": round(grounded_matches / value_page_matches, 4) if value_page_matches else None,
            "semantic_provider_required": len(semantic_gold),
            "late_page_batched": max_page > 24 and any(batch.page_start <= max_page <= batch.page_end for batch in batches),
        },
        "coverage": {
            "fixture_pages": len(pages),
            "source_pages_with_assertions": len(pages_by_number),
            "max_source_page": max_page,
            "extraction_batches": len(batches),
            "batch_page_ranges": [[batch.page_start, batch.page_end] for batch in batches],
        },
        "cases": matched,
        "limitations": [
            "No extraction, reasoning, vision, or embedding provider was used.",
            "The semantic executive-role record is intentionally reported as provider-required.",
            "Deterministic hints measure value/evidence coverage; predicate naming remains an open-schema model responsibility.",
            "This synthetic development split is not a live-model or starter-corpus quality claim.",
        ],
        "duration_seconds": round(time.perf_counter() - started, 4),
        "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=ROOT / "evals" / "gold" / "out_of_domain.jsonl")
    parser.add_argument("--fixture", type=Path, default=ROOT / "evals" / "fixtures" / "out_of_domain_claims.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evals" / "reports" / "gold-offline-generalization.json")
    args = parser.parse_args()
    report = evaluate(args.gold, args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["metrics"]["numeric_value_page_recall"] != 1.0 or report["metrics"]["grounding_precision_on_value_page_matches"] != 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
