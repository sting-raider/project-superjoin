from pathlib import Path

from app import pipeline
from app.config import settings
from app.db import db, init_db, utc_now
from app.parser import ParsedDocument, ParsedPage
from app.pipeline import (
    ExtractionBatch,
    _claim_id,
    _deterministically_normalized,
    _extract_document_batches,
    _insert_claims,
    _model_extract,
    _RunCancelled,
    _validated_grounded_claims,
    _vision_extract_page,
    build_extraction_batches,
    compact_candidate_hints,
    process_document,
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
        assert result == [
            {**repaired_claim, "evidence": {**repaired_claim["evidence"], "pdf_page": 1}}
        ]
        assert len(calls) == 2
        with db() as conn:
            statuses = [row["status"] for row in conn.execute("SELECT status FROM model_calls ORDER BY created_at").fetchall()]
        assert statuses == ["complete", "complete"]
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_candidate_hints_are_compact_and_do_not_repeat_evidence() -> None:
    evidence_text = "Annual recurring revenue reached $42 million in FY26."
    candidate = {
        "subject": "Document subject",
        "predicate": "annual_recurring_revenue",
        "raw_value": "$42 million",
        "value_type": "money",
        "period": "FY26",
        "evidence": {"pdf_page": 7, "text": evidence_text, "start": 10, "end": 45},
    }

    hints = compact_candidate_hints([candidate, candidate], limit=10)

    assert hints == [
        {
            "page": 7,
            "label": "annual_recurring_revenue",
            "value": "$42 million",
            "value_type": "money",
            "start": 10,
            "end": 45,
            "period": "FY26",
        }
    ]
    assert evidence_text not in str(hints)


def test_flat_provider_evidence_is_canonicalized_before_grounding() -> None:
    text = "Orion Works operated at 83% utilization during FY2026."
    items = [
        {
            "subject": "Orion Works",
            "predicate": "capacity_utilization",
            "raw_value": "83%",
            "value_type": "percentage",
            "unit": "%",
            "period": "FY2026",
            "modality": "actual",
            "scope": "manufacturing",
            "evidence": text,
            "pdf_page": 31,
        }
    ]

    claims = _validated_grounded_claims(
        items, [], [{"pdf_page": 31, "text": text}]
    )

    assert claims[0]["evidence"] == {"text": text, "pdf_page": 31}


def test_truncated_extraction_is_not_published_as_deterministic_hints(
    monkeypatch, tmp_path: Path
) -> None:
    original_database = settings.database_path
    object.__setattr__(settings, "database_path", tmp_path / "truncated.sqlite3")
    candidate = {
        "subject": "Document subject",
        "predicate": "annual_recurring_revenue",
        "raw_value": "$42 million",
        "value_type": "money",
        "evidence": {"pdf_page": 1, "text": "ARR reached $42 million."},
    }
    try:
        init_db()
        monkeypatch.setattr(
            "app.pipeline.structured_chat",
            lambda *args, **kwargs: ProviderResult(
                data={"claims": [candidate]},
                model="fake",
                output_tokens=1200,
                finish_reason="length",
            ),
        )
        batch = ExtractionBatch(
            index=0,
            pages=[{"pdf_page": 1, "section": 0, "start": 0, "text": "ARR reached $42 million."}],
            candidates=[candidate],
        )
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES('w','W',?)", (now,))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES('d','w','x.pdf','h','processing',?)", (now,))
            conn.execute(
                """INSERT INTO page_artifacts
                (id,document_id,page_number,width,height,native_text,parser,
                parser_version,quality_score,created_at)
                VALUES('page-d-1','d',1,100,100,'ARR reached $42 million.',
                'test','1',1.0,?)""",
                (now,),
            )
            conn.execute("INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES('r','w','d','live','processing',0,'',?,?)", (now, now))

        claims = _extract_document_batches([batch], "x.pdf", "r", "d")

        assert claims == []
        with db() as conn:
            checkpoint = conn.execute(
                "SELECT status,error,claim_count FROM extraction_batches WHERE run_id='r'"
            ).fetchone()
        assert checkpoint["status"] == "failed"
        assert "truncated" in checkpoint["error"].lower()
        assert checkpoint["claim_count"] == 0
    finally:
        object.__setattr__(settings, "database_path", original_database)


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


def test_completed_extraction_batch_is_reused_without_provider_call(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "checkpoint.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    calls: list[str] = []
    batch = ExtractionBatch(
        index=0,
        pages=[{"pdf_page": 1, "section": 0, "start": 0, "text": "ARR reached $42 million."}],
        candidates=[],
    )
    extracted = [{
        "subject": "Nimbus Cloud",
        "predicate": "annual_recurring_revenue",
        "raw_value": "$42 million",
        "evidence": {"pdf_page": 1, "text": "ARR reached $42 million."},
    }]
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute(
                "INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)",
                ("d", "w", "source.pdf", "hash", "processing", now),
            )
            conn.execute(
                "INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("r", "w", "d", "live", "processing", 0, "Extracting", now, now),
            )

        def fake_extract(*args, **kwargs):
            calls.append("called")
            return extracted

        monkeypatch.setattr("app.pipeline._model_extract", fake_extract)
        first = _extract_document_batches([batch], "source.pdf", "r", "d")
        second = _extract_document_batches([batch], "source.pdf", "r", "d")
        assert first == second == extracted
        assert calls == ["called"]
        with db() as conn:
            row = conn.execute(
                "SELECT status,claim_count,response_json FROM extraction_batches WHERE document_id='d'"
            ).fetchone()
        assert row["status"] == "complete"
        assert row["claim_count"] == 1
        assert '"annual_recurring_revenue"' in row["response_json"]
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_completed_batches_publish_provisional_claims_before_commit(
    monkeypatch, tmp_path: Path
) -> None:
    original_database = settings.database_path
    object.__setattr__(settings, "database_path", tmp_path / "provisional.sqlite3")
    extracted = [
        {
            "subject": "Nimbus Cloud",
            "predicate": "annual_recurring_revenue",
            "raw_value": "$42 million",
            "value_type": "money",
            "unit": "USD",
            "period": "FY26",
            "evidence": {"pdf_page": 1, "text": "ARR reached $42 million."},
        }
    ]
    batch = ExtractionBatch(
        index=0,
        pages=[{"pdf_page": 1, "section": 0, "start": 0, "text": "ARR reached $42 million."}],
        candidates=[],
    )
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES('w','W',?)", (now,))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES('d','w','x.pdf','h','processing',?)", (now,))
            conn.execute(
                """INSERT INTO page_artifacts
                (id,document_id,page_number,width,height,native_text,parser,
                parser_version,quality_score,created_at)
                VALUES('page-d-1','d',1,100,100,'ARR reached $42 million.',
                'test','1',1.0,?)""",
                (now,),
            )
            conn.execute("INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES('r','w','d','live','processing',0,'',?,?)", (now, now))
        monkeypatch.setattr("app.pipeline._model_extract", lambda *args: extracted)

        claims = _extract_document_batches([batch], "x.pdf", "r", "d", "w")

        assert claims == extracted
        with db() as conn:
            provisional = conn.execute(
                "SELECT run_id,extraction_status FROM claims WHERE document_id='d'"
            ).fetchone()
            facts = conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
        assert dict(provisional) == {"run_id": "r", "extraction_status": "provisional"}
        assert facts == 0

        assert _insert_claims("w", "d", "r", extracted) == 1
        with db() as conn:
            status = conn.execute(
                "SELECT extraction_status FROM claims WHERE document_id='d'"
            ).fetchone()["extraction_status"]
        assert status == "accepted"
    finally:
        object.__setattr__(settings, "database_path", original_database)


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


def test_no_key_visual_fallback_does_not_render(monkeypatch) -> None:
    monkeypatch.setattr("app.pipeline.available", lambda role=None: False)
    monkeypatch.setattr(
        "app.pipeline._record_run_notice", lambda *args, **kwargs: None
    )

    def render_must_not_run(*args, **kwargs):
        raise AssertionError("renderer ran without a configured vision provider")

    monkeypatch.setattr("app.pipeline._render_page", render_must_not_run)
    assert _vision_extract_page(b"pdf", 0, "source.pdf", "run") == []


def test_cancelled_run_cannot_publish_claims(tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "cancel.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    claim = {
        "subject": "Nimbus Cloud",
        "predicate": "annual_recurring_revenue",
        "raw_value": "$42 million",
        "value_type": "money",
        "unit": "USD",
        "evidence": {"pdf_page": 1, "text": "ARR reached $42 million."},
    }
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute(
                "INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)",
                ("d", "w", "source.pdf", "hash", "processing", now),
            )
            conn.execute(
                "INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("r", "w", "d", "live", "cancel_requested", 50, "Cancellation requested", now, now),
            )
        try:
            _insert_claims("w", "d", "r", [claim])
        except _RunCancelled:
            pass
        else:
            raise AssertionError("cancelled publication unexpectedly succeeded")
        with db() as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"] == 0
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_cancellation_during_extraction_stops_before_publication(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "cancel-extract.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    parsed = ParsedDocument(
        pages=[ParsedPage(0, 1000, 1000, "ARR reached $42 million.", [], 0.95, [])],
        sha256="hash",
        parser="test-parser",
        parser_version="1",
    )
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute(
                "INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)",
                ("d", "w", "source.pdf", "hash", "queued", now),
            )
            conn.execute(
                "INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("r", "w", "d", "live", "queued", 0, "Queued", now, now),
            )
        monkeypatch.setattr("app.pipeline.parse_pdf", lambda data: parsed)
        monkeypatch.setattr("app.pipeline.available", lambda role=None: role == "extraction")

        def cancel_after_extraction(*args, **kwargs):
            with db() as conn:
                conn.execute("UPDATE runs SET status='cancel_requested' WHERE id='r'")
            return []

        monkeypatch.setattr("app.pipeline._model_extract", cancel_after_extraction)
        process_document("r", "d", "w", b"%PDF-test", "source.pdf")
        with db() as conn:
            run = conn.execute("SELECT status FROM runs WHERE id='r'").fetchone()
            document = conn.execute("SELECT status FROM documents WHERE id='d'").fetchone()
            claims = conn.execute("SELECT COUNT(*) AS n FROM claims WHERE document_id='d'").fetchone()
        assert run["status"] == "cancelled"
        assert document["status"] == "cancelled"
        assert claims["n"] == 0
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_failed_publication_resumes_from_completed_extraction_checkpoint(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "resume.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    parsed = ParsedDocument(
        pages=[ParsedPage(0, 1000, 1000, "Nimbus Cloud ARR reached $42 million in FY26.", [], 0.95, [])],
        sha256="hash",
        parser="test-parser",
        parser_version="1",
    )
    extracted = [{
        "subject": "Nimbus Cloud",
        "predicate": "annual_recurring_revenue",
        "raw_value": "$42 million",
        "value_type": "money",
        "unit": "USD",
        "period": "FY26",
        "modality": "actual",
        "scope": "company",
        "evidence": {"pdf_page": 1, "text": "Nimbus Cloud ARR reached $42 million in FY26."},
    }]
    calls: list[str] = []
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", ("d", "w", "source.pdf", "hash", "queued", now))
            for run_id in ("r1", "r2"):
                conn.execute("INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (run_id, "w", "d", "live", "queued", 0, "Queued", now, now))
        monkeypatch.setattr("app.pipeline.parse_pdf", lambda _data: parsed)
        monkeypatch.setattr("app.pipeline.available", lambda role=None: role == "extraction")

        def fake_extract(*args, **kwargs):
            calls.append("provider")
            return extracted

        monkeypatch.setattr("app.pipeline._model_extract", fake_extract)
        original_insert = pipeline._insert_claims
        monkeypatch.setattr("app.pipeline._insert_claims", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated publication crash")))
        process_document("r1", "d", "w", b"%PDF-resume", "source.pdf")
        with db() as conn:
            assert conn.execute("SELECT status FROM runs WHERE id='r1'").fetchone()["status"] == "failed"
            assert conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM extraction_batches WHERE status='complete'").fetchone()["n"] == 1

        monkeypatch.setattr("app.pipeline._insert_claims", original_insert)
        process_document("r2", "d", "w", b"%PDF-resume", "source.pdf")
        with db() as conn:
            assert conn.execute("SELECT status FROM runs WHERE id='r2'").fetchone()["status"] == "complete"
            assert conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"] == 1
        assert calls == ["provider"]
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)
