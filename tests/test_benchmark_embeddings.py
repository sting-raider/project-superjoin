from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from benchmark_embeddings import retrieval_metrics


def test_retrieval_metrics_measure_same_group_candidates() -> None:
    rows = [
        {"id": "a1", "group": "revenue", "text": "recurring revenue"},
        {"id": "a2", "group": "revenue", "text": "subscription sales"},
        {"id": "b1", "group": "capacity", "text": "factory capacity"},
        {"id": "b2", "group": "capacity", "text": "production capability"},
    ]
    vectors = {
        "a1": [1.0, 0.0],
        "a2": [0.99, 0.01],
        "b1": [0.0, 1.0],
        "b2": [0.01, 0.99],
    }

    metrics = retrieval_metrics(rows, vectors)

    assert metrics["queries"] == 4
    assert metrics["candidate_count"] == 4
    assert metrics["recall_at_1"] == 1.0
    assert metrics["recall_at_3"] == 1.0
    assert metrics["recall_at_10"] == 1.0
    assert metrics["mean_reciprocal_rank"] == 1.0
