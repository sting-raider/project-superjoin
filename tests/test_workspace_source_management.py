import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.db import db, utc_now
from app.knowledge import rebuild_workspace
from app.main import app


def _insert_source(workspace_id: str, document_id: str, value: str) -> None:
    now = utc_now()
    evidence = {
        "document_id": document_id,
        "pdf_page": 1,
        "text": f"Northstar ARR was {value} in FY26.",
        "precision": "page-only",
    }
    with db() as conn:
        conn.execute(
            """INSERT INTO documents
            (id,workspace_id,name,sha256,page_count,status,parser,quality_score,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (document_id, workspace_id, f"{document_id}.pdf", uuid.uuid4().hex, 1, "complete", "liteparse", 1.0, now),
        )
        conn.execute(
            """INSERT INTO claims
            (id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,
             value_type,unit,precision,period,modality,scope,evidence_json,
             grounding_status,extraction_status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"claim-{document_id}", workspace_id, document_id, "Northstar Cloud",
                "annual recurring revenue", value, "125000000", "money", "USD", 0,
                "FY26", "actual", "company", json.dumps(evidence), "grounded", "accepted", now,
            ),
        )


def test_source_remove_and_restore_rebuilds_active_knowledge(tmp_path: Path) -> None:
    original_db, original_upload = settings.database_path, settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "sources.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        with TestClient(app) as client:
            created = client.post("/api/v1/workspaces", json={"name": "Northstar Review"})
            workspace_id = created.json()["id"]
            _insert_source(workspace_id, "source-board", "$125 million")
            _insert_source(workspace_id, "source-filing", "$125m")
            rebuild_workspace(workspace_id)

            removed = client.post("/api/v1/documents/source-board/archive")
            assert removed.status_code == 200
            assert removed.json()["document"]["status"] == "archived"
            archived_revision = removed.json()["revision"]
            repeated = client.post("/api/v1/documents/source-board/archive")
            assert repeated.json()["changed"] is False
            assert repeated.json()["revision"] == archived_revision
            with db() as conn:
                assert conn.execute(
                    "SELECT extraction_status FROM claims WHERE document_id='source-board'"
                ).fetchone()[0] == "archived"
                active_evidence = json.loads(conn.execute(
                    "SELECT evidence_json FROM facts WHERE workspace_id=? AND active=1",
                    (workspace_id,),
                ).fetchone()[0])
            assert {item["document_id"] for item in active_evidence} == {"source-filing"}
            overview = client.get(
                "/api/v1/overview", params={"workspace_id": workspace_id}
            ).json()
            assert overview["counts"]["grounded_claims"] == 1

            restored = client.post("/api/v1/documents/source-board/reactivate")
            assert restored.status_code == 200
            assert restored.json()["document"]["status"] == "complete"
            with db() as conn:
                active_evidence = json.loads(conn.execute(
                    "SELECT evidence_json FROM facts WHERE workspace_id=? AND active=1",
                    (workspace_id,),
                ).fetchone()[0])
            assert {item["document_id"] for item in active_evidence} == {"source-board", "source-filing"}
    finally:
        object.__setattr__(settings, "database_path", original_db)
        object.__setattr__(settings, "upload_dir", original_upload)


def test_workspace_delete_removes_its_local_source_file(tmp_path: Path) -> None:
    original_db, original_upload = settings.database_path, settings.upload_dir
    object.__setattr__(settings, "database_path", tmp_path / "workspace-delete.sqlite3")
    object.__setattr__(settings, "upload_dir", tmp_path / "uploads")
    try:
        with TestClient(app) as client:
            workspace = client.post("/api/v1/workspaces", json={"name": "Temporary Review"}).json()
            settings.ensure_dirs()
            stored = settings.upload_dir / "temporary.pdf"
            stored.write_bytes(b"%PDF-1.4\n")
            with db() as conn:
                conn.execute(
                    """INSERT INTO documents
                    (id,workspace_id,name,sha256,status,stored_path,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    ("temporary-source", workspace["id"], "temporary.pdf", uuid.uuid4().hex, "complete", str(stored), utc_now()),
                )

            deleted = client.delete(f"/api/v1/workspaces/{workspace['id']}")
            assert deleted.status_code == 200
            assert not stored.exists()
            assert all(item["id"] != workspace["id"] for item in client.get("/api/v1/workspaces").json()["items"])
    finally:
        object.__setattr__(settings, "database_path", original_db)
        object.__setattr__(settings, "upload_dir", original_upload)
