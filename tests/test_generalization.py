from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import ClassVar

from app import pipeline, providers
from app.config import settings
from app.db import db, init_db, utc_now
from app.parser import ParsedDocument, ParsedPage
from app.pipeline import process_document
from app.providers import ProviderResult


def test_unseen_domains_and_late_pages_flow_through_live_pipeline(
    monkeypatch, tmp_path: Path
) -> None:
    fixture = json.loads(
        (Path(__file__).parents[1] / "evals" / "fixtures" / "out_of_domain_claims.json")
        .read_text(encoding="utf-8")
    )
    pages = []
    for index in range(36):
        text = fixture["pages"].get(str(index + 1), "No material assertions on this page.")
        pages.append(ParsedPage(index, 1000, 1000, text, [], 0.95, []))
    parsed = ParsedDocument(
        pages=pages,
        sha256=hashlib.sha256(b"synthetic-pdf").hexdigest(),
        parser="test-parser",
        parser_version="1",
    )
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "generalization.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute(
                "INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)",
                ("unseen", "Unseen Domains", now),
            )
            conn.execute(
                "INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)",
                ("doc", "unseen", "mixed-industries.pdf", "hash", "queued", now),
            )
            conn.execute(
                "INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("run", "unseen", "doc", "live", "queued", 0, "Queued", now, now),
            )
        monkeypatch.setattr("app.pipeline.parse_pdf", lambda data: parsed)
        monkeypatch.setattr("app.pipeline.available", lambda role=None: role == "extraction")

        def fake_extractor(role, system, user, model=None, max_output_tokens=1200):
            claims = [
                claim
                for claim in fixture["claims"]
                if claim["evidence"]["text"] in user
            ]
            return ProviderResult(data={"claims": claims}, model=model or "fake", estimated_cost=0)

        monkeypatch.setattr("app.pipeline.structured_chat", fake_extractor)
        process_document("run", "doc", "unseen", b"synthetic-pdf", "mixed-industries.pdf")
        with db() as conn:
            run = conn.execute("SELECT status FROM runs WHERE id='run'").fetchone()
            claims = conn.execute(
                "SELECT predicate FROM claims WHERE workspace_id='unseen' AND extraction_status='accepted'"
            ).fetchall()
            late_anchor = conn.execute(
                "SELECT pdf_page FROM evidence_anchors WHERE document_id='doc' AND pdf_page=33"
            ).fetchone()
            checkpoints = conn.execute(
                "SELECT page_start,page_end,status FROM extraction_batches WHERE document_id='doc' ORDER BY batch_index"
            ).fetchall()
            predicates = conn.execute(
                "SELECT key FROM predicates WHERE workspace_id='unseen'"
            ).fetchall()
        expected = {claim["predicate"] for claim in fixture["claims"]}
        assert run["status"] == "complete"
        assert expected.issubset({row["predicate"] for row in claims})
        assert expected.issubset({row["key"] for row in predicates})
        assert late_anchor["pdf_page"] == 33
        assert checkpoints[0]["page_start"] == 1
        assert checkpoints[-1]["page_end"] == 36
        assert all(row["status"] == "complete" for row in checkpoints)
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_never_seen_pdf_uses_configured_arbitrary_openai_compatible_endpoint(monkeypatch, tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        requests: ClassVar[list[dict]] = []

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self.__class__.requests.append({"path": self.path, "model": payload.get("model"), "auth": self.headers.get("Authorization")})
            body = json.dumps({
                "id": "fake-chat",
                "choices": [{"message": {"content": json.dumps({"claims": [{
                    "subject": "Nimbus Cloud",
                    "predicate": "annual_recurring_revenue",
                    "raw_value": "$42 million",
                    "value_type": "money",
                    "unit": "USD",
                    "period": "FY26",
                    "modality": "actual",
                    "scope": "company",
                    "evidence": {"pdf_page": 1, "text": "Nimbus Cloud ARR reached $42 million in FY26."},
                }]})}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 16},
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_database = settings.database_path
    original_upload = settings.upload_dir
    configured = replace(
        settings,
        database_path=tmp_path / "never-seen.sqlite3",
        upload_dir=tmp_path / "uploads",
        extraction_base_url=f"http://127.0.0.1:{server.server_port}/v1",
        extraction_api_key="fake-key",
        extraction_model="acme/arbitrary-extractor",
        extraction_timeout_seconds=5,
    )
    monkeypatch.setattr(pipeline, "settings", configured)
    monkeypatch.setattr(providers, "settings", configured)
    monkeypatch.setattr(pipeline, "available", lambda role=None: role == "extraction")
    object.__setattr__(settings, "database_path", configured.database_path)
    object.__setattr__(settings, "upload_dir", configured.upload_dir)
    parsed = ParsedDocument(
        pages=[ParsedPage(0, 1000, 1000, "Nimbus Cloud ARR reached $42 million in FY26.", [], 0.95, [])],
        sha256=hashlib.sha256(b"never-seen").hexdigest(),
        parser="test-parser",
        parser_version="1",
    )
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("never-seen", "Never Seen", now))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", ("doc", "never-seen", "nimbus.pdf", "never-seen", "queued", now))
            conn.execute("INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", ("run", "never-seen", "doc", "live", "queued", 0, "Queued", now, now))
        monkeypatch.setattr(pipeline, "parse_pdf", lambda _data: parsed)
        process_document("run", "doc", "never-seen", b"%PDF-never-seen", "nimbus.pdf")
        with db() as conn:
            run = conn.execute("SELECT status FROM runs WHERE id='run'").fetchone()
            claim = conn.execute("SELECT predicate,normalized_value FROM claims WHERE document_id='doc'").fetchone()
        assert run["status"] == "complete"
        assert claim["predicate"] == "annual_recurring_revenue"
        assert claim["normalized_value"] == "42000000"
        assert Handler.requests
        assert Handler.requests[0]["path"] == "/v1/chat/completions"
        assert Handler.requests[0]["model"] == "acme/arbitrary-extractor"
        assert Handler.requests[0]["auth"] == "Bearer fake-key"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)
