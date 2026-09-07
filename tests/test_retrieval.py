from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import retrieval
from app.config import settings
from app.db import db, init_db, utc_now
from app.providers import ProviderError, ProviderResult


def test_query_embedding_is_cached_and_fused_with_fts(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "retrieval.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    calls = []

    def fake_embed(text: str, model: str | None = None) -> ProviderResult:
        calls.append((text, model))
        return ProviderResult(data={"data": [{"embedding": [3.0, 4.0]}]}, model=model or "fake", estimated_cost=0.001)

    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", ("d", "w", "source.pdf", "hash", "complete", now))
            conn.execute("INSERT INTO claims(id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("c", "w", "d", "Delhivery", "revenue", "100", "100", "number", json.dumps({"text": "Revenue was 100."}), now))
            conn.execute("INSERT INTO claims_fts(claim_id,workspace_id,subject,predicate,raw_value,period,modality,scope) VALUES(?,?,?,?,?,?,?,?)", ("c", "w", "Delhivery", "revenue", "100", "", "", ""))
            conn.execute("INSERT INTO embedding_spaces(id,workspace_id,provider,model,dimensions,template_version,status,created_at) VALUES(?,?,?,?,?,?,?,?)", ("space", "w", "fake", "embed-v1", 2, "identity-v1", "active", now))
            conn.execute("INSERT INTO embeddings(id,space_id,claim_id,content_hash,vector_json,created_at) VALUES(?,?,?,?,?,?)", ("e", "space", "c", "claim-hash", json.dumps([0.6, 0.8]), now))
        monkeypatch.setattr(retrieval, "available", lambda role=None: role in {None, "embedding"})
        monkeypatch.setattr(retrieval, "embed", fake_embed)

        first = retrieval.search_claims("w", "revenue", space_id="space")
        second = retrieval.search_claims("w", "revenue", space_id="space")

        assert first["lanes"]["lexical"] == 1
        assert first["lanes"]["dense"] == 1
        assert first["embedding_available"] is True
        assert second["lanes"]["hybrid"] == 1
        assert len(calls) == 1
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_embedding_dimension_mismatch_is_explicit_and_does_not_publish_vector(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "dimension.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", ("d", "w", "source.pdf", "hash", "complete", now))
            conn.execute("INSERT INTO claims(id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("c", "w", "d", "Nimbus", "arr", "$42m", "42000000", "money", json.dumps({"text": "ARR reached $42m."}), now))
            conn.execute("INSERT INTO embedding_spaces(id,workspace_id,provider,model,dimensions,template_version,status,created_at) VALUES(?,?,?,?,?,?,?,?)", ("space", "w", "fake", "arbitrary-embed", 3, "identity-v1", "active", now))
        monkeypatch.setattr(retrieval, "available", lambda role=None: role in {None, "embedding"})
        monkeypatch.setattr(retrieval, "embed", lambda *_args, **_kwargs: ProviderResult(data={"data": [{"embedding": [1.0, 2.0]}]}, model="arbitrary-embed", estimated_cost=0.001))
        with pytest.raises(ValueError, match="dimension mismatch"):
            retrieval.embed_claim("c", "space")
        with db() as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()["n"] == 0
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_search_keeps_lexical_results_and_surfaces_provider_failure(monkeypatch, tmp_path: Path) -> None:
    original_database = settings.database_path
    original_upload = settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "provider-error.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        init_db()
        now = utc_now()
        with db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", ("w", "Workspace", now))
            conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,created_at) VALUES(?,?,?,?,?,?)", ("d", "w", "source.pdf", "hash", "complete", now))
            conn.execute("INSERT INTO claims(id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", ("c", "w", "d", "Nimbus", "arr", "$42m", "42000000", "money", json.dumps({"text": "ARR reached $42m."}), now))
            conn.execute("INSERT INTO claims_fts(claim_id,workspace_id,subject,predicate,raw_value,period,modality,scope) VALUES(?,?,?,?,?,?,?,?)", ("c", "w", "Nimbus", "arr", "$42m", "", "", ""))
            conn.execute("INSERT INTO embedding_spaces(id,workspace_id,provider,model,dimensions,template_version,status,created_at) VALUES(?,?,?,?,?,?,?,?)", ("space", "w", "fake", "arbitrary-embed", 2, "identity-v1", "active", now))
            conn.execute("INSERT INTO embeddings(id,space_id,claim_id,content_hash,vector_json,created_at) VALUES(?,?,?,?,?,?)", ("e", "space", "c", "claim-hash", json.dumps([1.0, 0.0]), now))
        monkeypatch.setattr(retrieval, "available", lambda role=None: role in {None, "embedding"})
        monkeypatch.setattr(retrieval, "embed", lambda *_args, **_kwargs: (_ for _ in ()).throw(ProviderError("embedding endpoint unavailable")))
        result = retrieval.search_claims("w", "arr")
        assert result["lanes"]["lexical"] == 1
        assert result["embedding_available"] is False
        assert "embedding endpoint unavailable" in result["embedding_error"]
    finally:
        object.__setattr__(settings, "database_path", original_database)
        object.__setattr__(settings, "upload_dir", original_upload)
