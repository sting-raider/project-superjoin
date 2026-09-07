from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_starter_reports_account_for_all_six_documents_and_pages() -> None:
    report = json.loads((ROOT / "evals" / "reports" / "starter-corpus-e2e-generalized.json").read_text(encoding="utf-8"))
    documents = report["documents"]
    assert report["totals"]["documents"] == 6
    assert report["totals"]["pages"] == 511
    assert len(documents) == 6
    assert sum(item["pages"] for item in documents) == 511
    assert all(item["status"] == "complete" for item in documents)
    assert all(item["pages"] > 0 for item in documents)
    assert "Starter metadata" in report["anti_leakage"]


def test_parser_comparison_is_six_document_and_licensing_aware() -> None:
    report = json.loads((ROOT / "evals" / "reports" / "parser-six-document.json").read_text(encoding="utf-8"))
    assert len(report["files"]) == 6
    assert report["decision"]["runtime_primary"] == "pdfplumber"
    assert "licens" in report["decision"]["reason"].casefold()
    assert all(len(item["results"]) >= 2 for item in report["files"])


def test_synthetic_gold_report_measures_offline_generalization_honestly() -> None:
    report = json.loads((ROOT / "evals" / "reports" / "gold-offline-generalization.json").read_text(encoding="utf-8"))
    assert report["source_kind"].startswith("synthetic")
    assert report["gold_records"] == 6
    assert report["metrics"]["numeric_value_page_recall"] == 1.0
    assert report["metrics"]["grounding_precision_on_value_page_matches"] == 1.0
    assert report["metrics"]["late_page_batched"] is True
    assert report["metrics"]["semantic_provider_required"] == 1
    assert report["coverage"]["max_source_page"] == 33
    assert any("not a live-model" in item for item in report["limitations"])


def test_model_benchmark_skip_reports_are_role_specific_and_keyless_local_safe() -> None:
    for name in ("extraction-model-benchmark.json", "embedding-model-benchmark.json"):
        report = json.loads((ROOT / "evals" / "reports" / name).read_text(encoding="utf-8"))
        assert report["status"] == "skipped"
        assert "role base URL and model" in report["reason"]
        assert "API key is optional" in report["reason"]
        assert "AI_BASE_URL and AI_API_KEY" not in report["reason"]


def test_live_nim_report_preserves_role_limitations_and_call_telemetry() -> None:
    report_path = ROOT / "evals" / "reports" / "starter-corpus-e2e-nim.json"
    if not report_path.exists():
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "live-provider"
    assert report["provider_roles"]["extraction"] is True
    assert report["provider_roles"]["reasoning"] is False
    assert report["provider_roles"]["vision"] is False
    assert report["provider_roles"]["embedding"] is False
    assert report["provider_models"]["extraction"]
    extraction = report["provider_telemetry"]["extraction"]
    assert extraction["calls"] > 0
    assert extraction["attempts"] >= extraction["calls"]
    assert any("reasoning provider role was not configured" in item for item in report["limitations"])
    assert any("Visual pages remain in review" in item for item in report["limitations"])
    assert any("Dense retrieval" in item for item in report["limitations"])


def test_live_nim_model_benchmark_records_nonsecret_compatible_contract() -> None:
    report_path = ROOT / "evals" / "reports" / "extraction-model-benchmark-nim.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "complete"
    assert report["role"] == "extraction"
    assert report["candidates"] == ["nvidia/nemotron-3-super-120b-a12b"]
    assert report["cases"] == 1
    assert len(report["results"]) == 1
    result = report["results"][0]
    assert result["valid"] is True
    assert result["model"] == report["candidates"][0]
    assert result["endpoint"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert result["attempts"] >= 1
    assert result["provider_latency_ms"] >= 0
    assert "nvapi" not in report_path.read_text(encoding="utf-8").casefold()
