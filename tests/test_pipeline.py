from pathlib import Path

from app.config import settings
from app.db import db, init_db
from app.parser import ParsedPage
from app.pipeline import (
    _claim_id,
    _deterministically_normalized,
    _model_extract,
    build_extraction_batches,
)
from app.providers import ProviderResult


def test_claim_identity_is_stable_and_workspace_scoped() -> None:
    item = {"subject": "India", "predicate": "real_gdp_growth", "raw_value": "6.5%", "period": "FY26", "modality": "forecast", "scope": None}
    evidence = {"pdf_page": 3, "text": "India real GDP growth is projected at 6.5% in FY26."}
    first = _claim_id("india-macro", "doc-a", item, evidence)
    second = _claim_id("india-macro", "doc-a", item, evidence)
    other_workspace = _claim_id("delhivery", "doc-a", item, evidence)
    assert first == second
    assert first != other_workspace


def test_malformed_extraction_gets_one_budgeted_repair(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "pipeline.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    calls = []
    candidate = {"subject": "Delhivery", "predicate": "revenue", "raw_value": "100 million", "evidence": {"text": "Revenue was 100 million in FY24."}}
    repaired_claim = {**candidate, "normalized_value": "100000000", "value_type": "money", "unit": "USD", "period": "FY24", "modality": "actual", "scope": "consolidated"}

    def fake_chat(role, system, user, model=None, max_output_tokens=1200):
        calls.append((role, system, user, model, max_output_tokens))
        if len(calls) == 1:
            return ProviderResult(data="malformed", model=model or "fake", estimated_cost=0.001)
        return ProviderResult(data={"claims": [repaired_claim]}, model=model or "fake", estimated_cost=0.001)

    try:
        init_db()
        monkeypatch.setattr("app.pipeline.structured_chat", fake_chat)
        result = _model_extract([candidate], "source.pdf", None, [{"pdf_page": 1, "text": candidate["evidence"]["text"]}])
        assert result == [repaired_claim]
        assert len(calls) == 2
        with db() as conn:
            statuses = [row["status"] for row in conn.execute("SELECT status FROM model_calls ORDER BY created_at").fetchall()]
        assert statuses == ["complete", "complete"]
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_extraction_batches_cover_useful_claims_after_page_twenty_four() -> None:
    pages = [
        ParsedPage(
            index=index,
            width=1000,
            height=1000,
            text=f"Section {index + 1}: operational metric is {index + 1}%.",
            words=[],
            quality_score=0.9,
            flags=[],
        )
        for index in range(40)
    ]
    batches = build_extraction_batches(pages, [])
    covered = {
        page["pdf_page"]
        for batch in batches
        for page in batch.pages
    }
    assert covered == set(range(1, 41))
    assert any(batch.page_start <= 37 <= batch.page_end for batch in batches)
    assert all(len({page["pdf_page"] for page in batch.pages}) <= settings.extraction_batch_pages for batch in batches)
    assert all(sum(len(page["text"]) for page in batch.pages) <= settings.extraction_batch_chars for batch in batches)


def test_model_numeric_normalization_is_recomputed_deterministically() -> None:
    model_claim = {
        "raw_value": "$42 million",
        "normalized_value": "42",
        "value_type": "money",
        "unit": "widgets",
    }
    normalized = _deterministically_normalized(model_claim)
    assert normalized["normalized_value"] == "42000000"
    assert normalized["value_type"] == "money"
    assert normalized["unit"] == "USD"
    assert normalized["normalization_trace"] == ["parse-number", "scale:million"]
