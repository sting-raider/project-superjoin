"""Measure compatible embedding dimensions and candidate recall on a synthetic set."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.budget import BudgetExceeded, estimate_cost, reserve, settle
from app.config import settings
from app.db import init_db
from app.providers import ProviderError, available, embed, input_hash
from app.retrieval import _extract_vector


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("embedding benchmark input is empty")
    for row in rows:
        if not row.get("id") or not row.get("group") or not row.get("text"):
            raise ValueError("each embedding benchmark row needs id, group, and text")
    return rows


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def retrieval_metrics(rows: list[dict[str, Any]], vectors: dict[str, list[float]]) -> dict[str, Any]:
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        groups[str(row["group"])].add(str(row["id"]))
    queries = [row for row in rows if row["id"] in vectors]
    recalls: dict[str, list[bool]] = {"1": [], "3": [], "10": [], "20": []}
    reciprocal_ranks: list[float] = []
    for query in queries:
        query_id = str(query["id"])
        candidates = [
            (candidate_id, _cosine(vectors[query_id], candidate_vector))
            for candidate_id, candidate_vector in vectors.items()
            if candidate_id != query_id
        ]
        ranked = [
            candidate_id
            for candidate_id, _score in sorted(candidates, key=lambda item: item[1], reverse=True)
        ]
        relevant = groups[str(query["group"])] - {query_id}
        first_rank = next(
            (rank for rank, candidate_id in enumerate(ranked, start=1) if candidate_id in relevant),
            None,
        )
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        for cutoff, hits in recalls.items():
            hits.append(bool(relevant.intersection(ranked[: int(cutoff)])))
    return {
        "queries": len(queries),
        "candidate_count": len(vectors),
        "recall_at_1": round(sum(recalls["1"]) / len(recalls["1"]), 4) if recalls["1"] else None,
        "recall_at_3": round(sum(recalls["3"]) / len(recalls["3"]), 4) if recalls["3"] else None,
        "recall_at_10": round(sum(recalls["10"]) / len(recalls["10"]), 4) if recalls["10"] else None,
        "recall_at_20": round(sum(recalls["20"]) / len(recalls["20"]), 4) if recalls["20"] else None,
        "mean_reciprocal_rank": (
            round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4)
            if reciprocal_ranks
            else None
        ),
    }


def benchmark(models: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not available("embedding"):
        return {
            "status": "skipped",
            "reason": (
                "embedding provider is not configured: a role base URL and model are required; "
                "an API key is optional for local OpenAI-compatible endpoints"
            ),
            "role": "embedding",
            "candidates": models,
            "cases": len(rows),
        }
    init_db()
    reports: list[dict[str, Any]] = []
    for model in models:
        vectors: dict[str, list[float]] = {}
        errors: list[dict[str, str]] = []
        calls = 0
        attempts = 0
        total_cost = 0.0
        total_latency = 0
        dimensions: set[int] = set()
        for row in rows:
            text = str(row["text"])
            digest = input_hash(
                "embedding-benchmark-v1", model, str(row["id"]), text
            )
            reservation = None
            started = time.perf_counter()
            try:
                reservation = reserve(
                    None,
                    "embedding",
                    model,
                    digest,
                    estimate_cost(len(text), 32),
                )
                response = embed(text, model)
                calls += 1
                attempts += response.attempts
                vector = _extract_vector(response.data)
                total_cost += response.estimated_cost
                dimensions.add(len(vector))
                if len(vector) != settings.embedding_dimensions:
                    raise ValueError(
                        f"embedding dimension mismatch: expected {settings.embedding_dimensions}, got {len(vector)}"
                    )
                vectors[str(row["id"])] = vector
                settle(
                    reservation,
                    response.estimated_cost,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    latency_ms=response.latency_ms,
                    attempts=response.attempts,
                )
            except (BudgetExceeded, ProviderError, ValueError) as exc:
                if reservation:
                    settle(reservation, 0.0, status="failed", attempts=getattr(exc, "attempts", 1))
                errors.append({"case": str(row["id"]), "error": str(exc)})
            total_latency += int((time.perf_counter() - started) * 1000)
        metrics = retrieval_metrics(rows, vectors) if vectors else retrieval_metrics(rows, {})
        reports.append(
            {
                "model": model,
                "status": "complete" if not errors else "partial",
                "expected_dimensions": settings.embedding_dimensions,
                "observed_dimensions": sorted(dimensions),
                "valid_vectors": len(vectors),
                "calls": calls,
                "attempts": attempts,
                "total_estimated_cost": round(total_cost, 6),
                "total_provider_latency_ms": total_latency,
                "errors": errors,
                "retrieval": metrics,
            }
        )
    return {
        "status": "complete",
        "role": "embedding",
        "candidates": models,
        "cases": len(rows),
        "results": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = benchmark(args.models, _load_rows(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
