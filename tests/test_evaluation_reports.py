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
