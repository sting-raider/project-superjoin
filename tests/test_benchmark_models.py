from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from benchmark_models import _score_claims, _summaries


def test_synthetic_claim_scoring_is_domain_neutral_and_grounded() -> None:
    row = {
        "text": "Nimbus Cloud ARR was $42 million in FY2026.",
        "expected_claims": [
            {
                "subject": "Nimbus Cloud",
                "predicate": "annual_recurring_revenue",
                "raw_value": "$42 million",
                "normalized_value": "42000000",
                "period": "FY2026",
            }
        ],
    }
    claims = [
        {
            "subject": "Nimbus Cloud",
            "predicate": "annual_recurring_revenue",
            "raw_value": "$42 million",
            "normalized_value": "42000000",
            "period": "FY2026",
            "evidence": {"text": row["text"], "pdf_page": 2},
        }
    ]

    scored = _score_claims(claims, row)

    assert scored["expected_claim_recall"] == 1.0
    assert scored["grounded_claim_precision"] == 1.0
    assert scored["matched_expected_indices"] == [0]


def test_model_summaries_separate_contract_quality_and_cost() -> None:
    rows = [
        {
            "model": "acme/arbitrary-model",
            "valid": True,
            "claim_count": 2,
            "expected_claim_count": 2,
            "matched_claim_count": 1,
            "grounded_claim_count": 2,
            "estimated_cost": 0.001,
            "attempts": 2,
            "provider_latency_ms": 120,
        },
        {
            "model": "acme/arbitrary-model",
            "valid": False,
            "claim_count": 0,
            "expected_claim_count": 1,
            "matched_claim_count": 0,
            "grounded_claim_count": 0,
            "estimated_cost": 0.0,
            "attempts": 1,
            "provider_latency_ms": 80,
        },
    ]

    summary = _summaries(["acme/arbitrary-model"], rows)["acme/arbitrary-model"]

    assert summary["contract_pass_rate"] == 0.5
    assert summary["expected_claim_recall"] == 0.3333
    assert summary["grounded_claim_precision"] == 1.0
    assert summary["total_attempts"] == 3
    assert summary["total_estimated_cost"] == 0.001
