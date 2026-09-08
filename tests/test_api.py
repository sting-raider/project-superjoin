import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.db import db, utc_now
from app.main import _public_endpoint, app


def test_public_endpoint_redacts_url_credentials_and_query() -> None:
    assert _public_endpoint("https://user:secret@example.test/v1?api_key=hidden#fragment") == "https://example.test/v1"
    assert _public_endpoint("http://[::1]:11434/v1?token=hidden") == "http://[::1]:11434/v1"
    assert _public_endpoint("/openai/deployments/model/chat/completions?api-version=hidden") == "/openai/deployments/model/chat/completions"


def test_fresh_runtime_is_empty_until_a_workspace_is_created(tmp_path: Path) -> None:
    original_db, original_upload = settings.database_path, settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "empty.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/health").status_code == 200
            assert client.get("/api/v1/workspaces").json()["items"] == []
            assert client.get("/api/v1/overview").status_code == 404

            created = client.post(
                "/api/v1/workspaces",
                json={"name": "Unseen SaaS Review", "description": "A fresh corpus"},
            )
            assert created.status_code == 201
            workspace_id = created.json()["id"]
            assert client.get(f"/api/v1/workspaces/{workspace_id}").json()["counts"] == {
                "documents": 0, "claims": 0, "facts": 0, "relationships": 0,
                "changes": 0, "grounded_claims": 0,
            }
            with db() as conn:
                assert conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='demo_replay_state'"
                ).fetchone() is None
    finally:
        object.__setattr__(settings, "database_path", original_db)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_workspace_create_slugifies_and_rejects_duplicate(tmp_path: Path) -> None:
    original_db = settings.database_path
    object.__setattr__(settings, "database_path", tmp_path / "workspace.sqlite3")
    try:
        with TestClient(app) as client:
            name = f"New Advisory Corpus {uuid.uuid4().hex[:8]}"
            created = client.post("/api/v1/workspaces", json={"name": name, "description": "test"})
            assert created.status_code == 201
            assert created.json()["id"].startswith("new-advisory-corpus-")
            assert client.post("/api/v1/workspaces", json={"name": name}).status_code == 409
    finally:
        object.__setattr__(settings, "database_path", original_db)


def test_upload_rejects_non_pdf_signature(tmp_path: Path) -> None:
    original_db, original_upload = settings.database_path, settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "upload.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        with TestClient(app) as client:
            workspace_id = client.post("/api/v1/workspaces", json={"name": "Upload Review"}).json()["id"]
            response = client.post(
                "/api/v1/documents",
                files={"file": ("notes.pdf", b"not a pdf", "application/pdf")},
                data={"workspace_id": workspace_id},
            )
            assert response.status_code == 400
    finally:
        object.__setattr__(settings, "database_path", original_db)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_settings_exposes_nonsecret_independent_role_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["project"] == "Project SuperJoin"
    assert set(payload["roles"]) == {"extraction", "reasoning", "vision", "embeddings"}
    assert all("api_key" not in role for role in payload["roles"].values())
    assert payload["roles"]["embeddings"]["dimensions"] > 0


def test_runtime_settings_update_never_returns_or_persists_api_key(tmp_path: Path) -> None:
    original_db = settings.database_path
    original = settings.extraction_base_url, settings.extraction_api_key, settings.extraction_model
    object.__setattr__(settings, "database_path", tmp_path / "settings.sqlite3")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/settings/extraction",
                json={"base_url": "http://localhost:11434/v1", "api_key": "memory-only-secret", "model": "arbitrary/local-model"},
            )
            assert response.status_code == 200
            assert "memory-only-secret" not in response.text
            with db() as conn:
                serialized = " ".join(str(row[0]) for row in conn.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall())
            assert "memory-only-secret" not in serialized
    finally:
        object.__setattr__(settings, "database_path", original_db)
        object.__setattr__(settings, "extraction_base_url", original[0])
        object.__setattr__(settings, "extraction_api_key", original[1])
        object.__setattr__(settings, "extraction_model", original[2])


def test_run_model_calls_surface_nonsecret_telemetry(tmp_path: Path) -> None:
    original_db = settings.database_path
    object.__setattr__(settings, "database_path", tmp_path / "telemetry.sqlite3")
    try:
        with TestClient(app) as client:
            workspace_id = client.post("/api/v1/workspaces", json={"name": "Telemetry"}).json()["id"]
            run_id = f"telemetry-{uuid.uuid4().hex[:8]}"
            now = utc_now()
            with db() as conn:
                conn.execute(
                    "INSERT INTO runs(id,workspace_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (run_id, workspace_id, "live", "complete", 100, "Complete", now, now),
                )
                conn.execute(
                    """INSERT INTO model_calls
                    (id,run_id,role,model,input_hash,status,input_tokens,output_tokens,
                     estimated_cost,latency_ms,attempts,cache_hit,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"call-{uuid.uuid4().hex[:8]}", run_id, "extraction", "acme/arbitrary-model", "hash", "complete", 12, 8, 0.0001, 321, 2, 0, now),
                )
            response = client.get(f"/api/v1/runs/{run_id}/model-calls")
        assert response.status_code == 200
        assert response.json()["items"][0]["model"] == "acme/arbitrary-model"
        assert "api_key" not in response.text
    finally:
        object.__setattr__(settings, "database_path", original_db)


def test_fact_search_reports_total_statuses_and_pages_server_side(tmp_path: Path) -> None:
    original_db = settings.database_path
    object.__setattr__(settings, "database_path", tmp_path / "facts.sqlite3")
    try:
        with TestClient(app) as client:
            workspace_id = client.post("/api/v1/workspaces", json={"name": "Search Desk"}).json()["id"]
            now = utc_now()
            with db() as conn:
                for index, status in enumerate(("SUPPORTED", "CONTESTED", "SUPPORTED")):
                    conn.execute(
                        """INSERT INTO facts
                        (id,workspace_id,subject,predicate,normalized_value,display_value,
                        value_type,status,reason,evidence_json,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            f"fact-{index}", workspace_id, f"Northstar {index}",
                            "annual_recurring_revenue", str(index), f"${index}m", "money",
                            status, "Grounded test fact", "[]", now,
                        ),
                    )
            response = client.get(
                "/api/v1/facts",
                params={"workspace_id": workspace_id, "q": "Northstar", "status": "SUPPORTED", "limit": 1, "offset": 1},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["total"] == 2
        assert payload["offset"] == 1
        assert payload["statuses"] == ["CONTESTED", "SUPPORTED"]
    finally:
        object.__setattr__(settings, "database_path", original_db)
