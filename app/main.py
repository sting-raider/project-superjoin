from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .budget import snapshot as budget_snapshot
from .config import settings
from .db import db, init_db, row_to_dict, rows_to_dicts, utc_now
from .knowledge import assess_relationships, rebuild_workspace, resolve_fact, set_document_archived
from .pipeline import process_document
from .providers import ProviderError, available, probe, public_endpoint
from .retrieval import create_embedding_space, embed_claim, search_claims
from .runtime_settings import (
    ProviderConnectionCopy,
    ProviderRoleUpdate,
    apply_provider_update,
    copy_provider_connection,
    provider_presets,
)


def startup() -> None:
    init_db()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup()
    yield


app = FastAPI(
    title="Project SuperJoin",
    version="0.1.0",
    description="Evidence-first temporal fact knowledge layer",
    lifespan=lifespan,
)


def _workspace_or_default(workspace_id: str | None) -> str:
    if workspace_id:
        return workspace_id
    with db() as conn:
        row = conn.execute("SELECT id FROM workspaces ORDER BY created_at,id LIMIT 1").fetchone()
    if not row:
        raise HTTPException(404, "No workspace is available")
    return str(row["id"])


def _public_endpoint(value: str) -> str:
    """Compatibility wrapper for the shared endpoint redaction helper."""

    return public_endpoint(value)


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    with db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "project": "Project SuperJoin", "provider_configured": available()}


@app.get("/api/v1/workspaces")
def workspaces() -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM workspaces ORDER BY name").fetchall()
    return {"items": rows_to_dicts(rows)}


@app.post("/api/v1/workspaces", status_code=201)
def create_workspace(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    requested_id = str(payload.get("id") or "").strip().lower()
    workspace_id = re.sub(r"[^a-z0-9]+", "-", requested_id or name.casefold()).strip("-")[:48]
    if not workspace_id:
        raise HTTPException(400, "name must contain a usable workspace identifier")
    description = str(payload.get("description") or "").strip()
    with db() as conn:
        if conn.execute("SELECT 1 FROM workspaces WHERE id=?", (workspace_id,)).fetchone():
            raise HTTPException(409, "Workspace id already exists")
        conn.execute("INSERT INTO workspaces(id,name,description,created_at) VALUES(?,?,?,?)", (workspace_id, name, description, utc_now()))
        row = conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
    return row_to_dict(row) or {"id": workspace_id, "name": name}


@app.delete("/api/v1/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str) -> dict[str, Any]:
    """Delete one local workspace after the UI obtains explicit confirmation."""

    with db() as conn:
        workspace = conn.execute(
            "SELECT id,name FROM workspaces WHERE id=?", (workspace_id,)
        ).fetchone()
        if not workspace:
            raise HTTPException(404, "Workspace not found")
        active = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE workspace_id=? AND status IN ('queued','processing')",
            (workspace_id,),
        ).fetchone()[0]
        if active:
            raise HTTPException(409, "Cancel or finish active runs before deleting this workspace")
        stored_paths = [
            str(row[0])
            for row in conn.execute(
                "SELECT stored_path FROM documents WHERE workspace_id=? AND stored_path IS NOT NULL",
                (workspace_id,),
            ).fetchall()
        ]
        claim_ids = "SELECT id FROM claims WHERE workspace_id=?"
        fact_ids = "SELECT id FROM facts WHERE workspace_id=?"
        fact_version_ids = f"SELECT id FROM fact_versions WHERE fact_id IN ({fact_ids})"
        document_ids = "SELECT id FROM documents WHERE workspace_id=?"
        run_ids = "SELECT id FROM runs WHERE workspace_id=?"
        space_ids = "SELECT id FROM embedding_spaces WHERE workspace_id=?"
        entity_ids = "SELECT id FROM entities WHERE workspace_id=?"
        predicate_ids = "SELECT id FROM predicates WHERE workspace_id=?"
        conn.execute("DELETE FROM claims_fts WHERE workspace_id=?", (workspace_id,))
        conn.execute(
            f"DELETE FROM embeddings WHERE claim_id IN ({claim_ids}) OR space_id IN ({space_ids})",
            (workspace_id, workspace_id),
        )
        conn.execute(
            f"DELETE FROM fact_memberships WHERE claim_id IN ({claim_ids}) OR fact_version_id IN ({fact_version_ids})",
            (workspace_id, workspace_id),
        )
        conn.execute("DELETE FROM reviews WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM relationships WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM changes WHERE workspace_id=?", (workspace_id,))
        conn.execute(
            f"DELETE FROM entity_aliases WHERE entity_id IN ({entity_ids})", (workspace_id,)
        )
        conn.execute(
            f"DELETE FROM predicate_aliases WHERE predicate_id IN ({predicate_ids})",
            (workspace_id,),
        )
        conn.execute("DELETE FROM registry_decisions WHERE workspace_id=?", (workspace_id,))
        conn.execute(
            f"DELETE FROM claim_interpretations WHERE claim_id IN ({claim_ids})",
            (workspace_id,),
        )
        conn.execute(
            f"DELETE FROM fact_versions WHERE fact_id IN ({fact_ids})", (workspace_id,)
        )
        conn.execute("DELETE FROM facts WHERE workspace_id=?", (workspace_id,))
        conn.execute(
            f"DELETE FROM claim_evidence WHERE claim_id IN ({claim_ids})",
            (workspace_id,),
        )
        conn.execute(
            f"DELETE FROM extraction_batches WHERE document_id IN ({document_ids})",
            (workspace_id,),
        )
        conn.execute(
            f"DELETE FROM model_calls WHERE run_id IN ({run_ids})", (workspace_id,)
        )
        conn.execute(
            f"DELETE FROM run_stage_timings WHERE run_id IN ({run_ids})", (workspace_id,)
        )
        conn.execute(f"DELETE FROM run_events WHERE run_id IN ({run_ids})", (workspace_id,))
        conn.execute("DELETE FROM runs WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM claims WHERE workspace_id=?", (workspace_id,))
        conn.execute(
            f"DELETE FROM evidence_anchors WHERE document_id IN ({document_ids})",
            (workspace_id,),
        )
        conn.execute(
            f"DELETE FROM page_artifacts WHERE document_id IN ({document_ids})",
            (workspace_id,),
        )
        conn.execute("DELETE FROM documents WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM embedding_spaces WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM entities WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM predicates WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
    root = settings.upload_dir.resolve()
    for stored_path in stored_paths:
        path = Path(stored_path).resolve()
        if path.is_relative_to(root) and path.is_file():
            path.unlink()
    return {"status": "deleted", "id": workspace_id, "name": workspace["name"]}


@app.get("/api/v1/workspaces/{workspace_id}")
def workspace_detail(workspace_id: str) -> dict[str, Any]:
    return overview(workspace_id)


@app.get("/api/v1/overview")
def overview(workspace_id: str | None = None) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        workspace = row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone())
        if not workspace:
            raise HTTPException(404, "Workspace not found")
        counts = {}
        for table in ("documents", "claims", "facts", "relationships", "changes"):
            fact_filter = " AND active=1" if table == "facts" else ""
            counts[table] = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE workspace_id=?{fact_filter}", (workspace_id,)).fetchone()["count"]
        status_rows = conn.execute("SELECT status,COUNT(*) AS count FROM facts WHERE workspace_id=? AND active=1 GROUP BY status", (workspace_id,)).fetchall()
        latest = conn.execute("SELECT * FROM changes WHERE workspace_id=? ORDER BY created_at DESC LIMIT 8", (workspace_id,)).fetchall()
        grounded = conn.execute(
            """SELECT COUNT(*) FROM claims c JOIN documents d ON d.id=c.document_id
            WHERE c.workspace_id=? AND c.grounding_status='grounded'
              AND c.extraction_status='accepted' AND d.status<>'archived'""",
            (workspace_id,),
        ).fetchone()[0]
        relationship_rows = conn.execute(
            "SELECT relationship_type,COUNT(*) AS count FROM relationships WHERE workspace_id=? GROUP BY relationship_type",
            (workspace_id,),
        ).fetchall()
    return {
        "workspace": workspace,
        "counts": {**counts, "grounded_claims": grounded},
        "statuses": {row["status"]: row["count"] for row in status_rows},
        "relationship_types": {
            row["relationship_type"]: row["count"] for row in relationship_rows
        },
        "latest_changes": rows_to_dicts(latest),
    }


@app.get("/api/v1/documents")
def documents(workspace_id: str | None = None) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        rows = conn.execute("SELECT * FROM documents WHERE workspace_id=? ORDER BY published_at DESC, name", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/documents/{document_id}/file")
def document_file(document_id: str) -> FileResponse:
    with db() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if not row or not row["stored_path"]:
        raise HTTPException(404, "Stored PDF not found")
    root = settings.upload_dir.resolve()
    path = Path(row["stored_path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Stored PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=Path(row["name"]).name)


@app.get("/api/v1/documents/{document_id}")
def document_detail(document_id: str) -> dict[str, Any]:
    with db() as conn:
        document = row_to_dict(conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone())
        if not document:
            raise HTTPException(404, "Document not found")
        pages = rows_to_dicts(conn.execute("SELECT * FROM page_artifacts WHERE document_id=? ORDER BY page_number", (document_id,)).fetchall())
    return {"document": document, "pages": pages}


@app.post("/api/v1/documents/{document_id}/archive")
def archive_document(document_id: str) -> dict[str, Any]:
    try:
        result = set_document_archived(document_id, True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if result["changed"]:
        assess_relationships(result["workspace_id"])
        rebuild_workspace(result["workspace_id"], advance_revision=False)
    return result


@app.post("/api/v1/documents/{document_id}/reactivate")
def reactivate_document(document_id: str) -> dict[str, Any]:
    try:
        result = set_document_archived(document_id, False)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if result["changed"]:
        assess_relationships(result["workspace_id"])
        rebuild_workspace(result["workspace_id"], advance_revision=False)
    return result


@app.post("/api/v1/documents", status_code=202)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), workspace_id: str | None = Form(None)) -> dict[str, Any]:  # noqa: B008
    workspace_id = _workspace_or_default(workspace_id)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF file")
    max_bytes = settings.max_pdf_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"PDF exceeds the {settings.max_pdf_mb} MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF-"):
        raise HTTPException(400, "The uploaded file is not a PDF")
    digest = hashlib.sha256(data).hexdigest()
    settings.ensure_dirs()
    with db() as conn:
        if not conn.execute("SELECT 1 FROM workspaces WHERE id=?", (workspace_id,)).fetchone():
            raise HTTPException(404, "Workspace not found")
        existing = conn.execute("SELECT * FROM documents WHERE workspace_id=? AND sha256=?", (workspace_id, digest)).fetchone()
        if existing:
            return {"document": row_to_dict(existing), "run": None, "deduplicated": True}
        document_id = f"doc-{hashlib.sha256(f'{workspace_id}:{digest}'.encode()).hexdigest()[:20]}"
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        stored = settings.upload_dir / f"{document_id}.pdf"
        stored.write_bytes(data)
        conn.execute("INSERT INTO documents(id,workspace_id,name,sha256,status,stored_path,created_at) VALUES(?,?,?,?,?,?,?)", (document_id, workspace_id, file.filename, digest, "queued", str(stored), utc_now()))
        conn.execute("INSERT INTO runs(id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (run_id, workspace_id, document_id, "live", "queued", 0, "Queued", utc_now(), utc_now()))
    background_tasks.add_task(process_document, run_id, document_id, workspace_id, data, file.filename)
    return {"document_id": document_id, "run_id": run_id, "deduplicated": False}


@app.get("/api/v1/runs/{run_id}")
def run(run_id: str) -> dict[str, Any]:
    with db() as conn:
        item = row_to_dict(conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
    if not item:
        raise HTTPException(404, "Run not found")
    return item


@app.get("/api/v1/runs/{run_id}/model-calls")
def run_model_calls(run_id: str) -> dict[str, Any]:
    """Return nonsecret model-call telemetry for one run."""

    with db() as conn:
        if not conn.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone():
            raise HTTPException(404, "Run not found")
        rows = conn.execute(
            """SELECT id,role,model,status,request_chars,input_tokens,output_tokens,
            estimated_cost,latency_ms,attempts,cache_hit,created_at
            FROM model_calls WHERE run_id=? ORDER BY created_at,id""",
            (run_id,),
        ).fetchall()
    return {"run_id": run_id, "items": rows_to_dicts(rows)}


@app.get("/api/v1/runs/{run_id}/stages")
def run_stages(run_id: str) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_stage_timings WHERE run_id=? ORDER BY started_at,stage",
            (run_id,),
        ).fetchall()
    return {"run_id": run_id, "items": rows_to_dicts(rows)}


@app.get("/api/v1/runs/{run_id}/provisional-claims")
def provisional_claims(run_id: str) -> dict[str, Any]:
    with db() as conn:
        run = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Run not found")
        rows = conn.execute(
            """SELECT id,document_id,subject,predicate,raw_value,normalized_value,
            value_type,unit,period,modality,scope,evidence_json,grounding_status,
            extraction_status,created_at FROM claims
            WHERE run_id=? AND extraction_status='provisional' ORDER BY created_at,id""",
            (run_id,),
        ).fetchall()
    return {
        "run_id": run_id,
        "committed": False,
        "trust_gate_eligible": False,
        "items": rows_to_dicts(rows),
    }


@app.get("/api/v1/runs")
def runs(workspace_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        rows = conn.execute("SELECT * FROM runs WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?", (workspace_id, max(1, min(limit, 200)))).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/runs/{run_id}/events/history")
def run_event_history(run_id: str, after_id: int = 0) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM run_events WHERE run_id=? AND id>? ORDER BY id LIMIT 500", (run_id, after_id)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.post("/api/v1/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, Any]:
    with db() as conn:
        item = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Run not found")
        if item["status"] not in {"queued", "processing", "cancel_requested"}:
            return {"run_id": run_id, "status": item["status"]}
        conn.execute("UPDATE runs SET status='cancel_requested',message='Cancellation requested',updated_at=? WHERE id=?", (utc_now(), run_id))
    return {"run_id": run_id, "status": "cancel_requested"}


@app.post("/api/v1/runs/{run_id}/retry", status_code=202)
def retry_run(run_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT r.workspace_id,r.document_id,d.name,d.stored_path FROM runs r JOIN documents d ON d.id=r.document_id WHERE r.id=?", (run_id,)).fetchone()
        if not row or not row["stored_path"]:
            raise HTTPException(404, "Stored document for retry not found")
        document = conn.execute("SELECT * FROM documents WHERE id=?", (row["document_id"],)).fetchone()
        if not document:
            raise HTTPException(404, "Document not found")
        new_run_id = f"run-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """INSERT INTO runs
            (id,workspace_id,document_id,mode,status,progress,message,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                new_run_id,
                document["workspace_id"],
                document["id"],
                "retry",
                "queued",
                0,
                "Retry queued",
                utc_now(),
                utc_now(),
            ),
        )
        data = Path(document["stored_path"]).read_bytes()
    background_tasks.add_task(process_document, new_run_id, document["id"], document["workspace_id"], data, document["name"])
    return {"run_id": new_run_id, "document_id": document["id"]}


@app.post("/api/v1/runs/{run_id}/resume", status_code=202)
def resume_run(run_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    return retry_run(run_id, background_tasks)


@app.get("/api/v1/runs/{run_id}/events")
async def run_events(run_id: str, after_id: int = 0) -> StreamingResponse:
    async def events():
        last_event_id = max(0, after_id)
        for _ in range(120):
            with db() as conn:
                row = row_to_dict(conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
                event_rows = rows_to_dicts(conn.execute("SELECT * FROM run_events WHERE run_id=? AND id>? ORDER BY id LIMIT 500", (run_id, last_event_id)).fetchall())
            if not row:
                return
            for event in event_rows:
                last_event_id = int(event["id"])
                yield f"id: {last_event_id}\ndata: {json.dumps(event)}\n\n"
            if row.get("status") in {"complete", "failed", "cancelled"} and not event_rows:
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/v1/facts")
def facts(
    workspace_id: str | None = None,
    q: str = "",
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        params: list[Any] = [workspace_id]
        clauses = ["workspace_id=?", "active=1"]
        if q:
            query = " ".join(re.findall(r"[A-Za-z0-9_]+", q))
            rows = conn.execute("SELECT claim_id FROM claims_fts WHERE workspace_id=? AND claims_fts MATCH ? LIMIT ?", (workspace_id, query, limit)).fetchall() if query else []
            claim_ids = [row["claim_id"] for row in rows]
            if claim_ids:
                clauses.append("(subject LIKE ? OR predicate LIKE ? OR display_value LIKE ? OR id IN (SELECT fv.fact_id FROM fact_versions fv JOIN fact_memberships fm ON fm.fact_version_id=fv.id WHERE fm.claim_id IN (" + ",".join("?" for _ in claim_ids) + ")))" )
                params.extend([f"%{q}%", f"%{q}%", f"%{q}%", *claim_ids])
            else:
                clauses.append("(subject LIKE ? OR predicate LIKE ? OR display_value LIKE ?)")
                params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        if status:
            clauses.append("status=?")
            params.append(status)
        where = " AND ".join(clauses)
        total = int(conn.execute(f"SELECT COUNT(*) FROM facts WHERE {where}", params).fetchone()[0])
        statuses = [
            row["status"]
            for row in conn.execute(
                "SELECT DISTINCT status FROM facts WHERE workspace_id=? AND active=1 ORDER BY status",
                (workspace_id,),
            ).fetchall()
        ]
        page_size = max(1, min(limit, 500))
        page_offset = max(0, offset)
        rows = conn.execute(
            f"SELECT * FROM facts WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (*params, page_size, page_offset),
        ).fetchall()
    return {
        "items": rows_to_dicts(rows),
        "count": len(rows),
        "total": total,
        "limit": page_size,
        "offset": page_offset,
        "statuses": statuses,
    }


@app.get("/api/v1/search")
def search(workspace_id: str | None = None, q: str = "", limit: int = 20, space_id: str | None = None) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    if not q.strip():
        return {"items": [], "lanes": {"lexical": 0, "dense": 0, "hybrid": 0}, "embedding_available": False, "embedding_error": None}
    return search_claims(workspace_id, q, max(1, min(limit, 100)), space_id=space_id)


@app.get("/api/v1/facts/{fact_id}")
def fact(fact_id: str) -> dict[str, Any]:
    with db() as conn:
        item = row_to_dict(conn.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone())
        if not item:
            raise HTTPException(404, "Fact not found")
        # Canonical names can differ from immutable source mentions. Memberships
        # in the published version are the authority for this fact's provenance.
        members = """SELECT fm.claim_id FROM fact_memberships fm
            JOIN fact_versions fv ON fv.id=fm.fact_version_id
            WHERE fv.fact_id=? AND fv.revision=?"""
        params = (fact_id, item["revision"])
        claims = rows_to_dicts(conn.execute(
            f"SELECT * FROM claims WHERE id IN ({members}) ORDER BY created_at,id", params
        ).fetchall())
        relationships = rows_to_dicts(conn.execute(
            f"""SELECT * FROM relationships WHERE workspace_id=?
            AND (claim_a IN ({members}) OR claim_b IN ({members}))
            ORDER BY created_at,id""", (item["workspace_id"], *params, *params)
        ).fetchall())
        anchors = rows_to_dicts(conn.execute(
            f"""SELECT ea.*,ce.claim_id,ce.purpose,d.name AS document_name,
            d.publisher,d.status AS document_status,c.grounding_status,c.extraction_status
            FROM evidence_anchors ea JOIN claim_evidence ce ON ce.anchor_id=ea.id
            JOIN documents d ON d.id=ea.document_id JOIN claims c ON c.id=ce.claim_id
            WHERE ce.claim_id IN ({members}) ORDER BY ea.pdf_page,ea.id,ce.claim_id""", params
        ).fetchall())
        interpretations = rows_to_dicts(conn.execute(
            f"""SELECT * FROM claim_interpretations WHERE claim_id IN ({members})
            ORDER BY created_at,id""", params
        ).fetchall())
        for anchor in anchors:
            anchor["pdf_url"] = f"/api/v1/documents/{anchor['document_id']}/file#page={anchor['pdf_page']}"
    return {"fact": item, "claims": claims, "anchors": anchors,
            "interpretations": interpretations, "relationships": relationships,
            "evidence_unavailable_reason": None if anchors else
            "No source evidence anchors are linked to this published fact version."}


@app.get("/api/v1/facts/{fact_id}/history")
def fact_history(fact_id: str) -> dict[str, Any]:
    with db() as conn:
        if not conn.execute("SELECT 1 FROM facts WHERE id=?", (fact_id,)).fetchone():
            raise HTTPException(404, "Fact not found")
        rows = conn.execute("SELECT * FROM fact_versions WHERE fact_id=? ORDER BY revision DESC", (fact_id,)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/claims/{claim_id}")
def claim_detail(claim_id: str) -> dict[str, Any]:
    with db() as conn:
        claim = row_to_dict(conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone())
        if not claim:
            raise HTTPException(404, "Claim not found")
        anchors = rows_to_dicts(conn.execute("SELECT ea.*,ce.purpose FROM evidence_anchors ea JOIN claim_evidence ce ON ce.anchor_id=ea.id WHERE ce.claim_id=? ORDER BY ea.pdf_page,ea.id", (claim_id,)).fetchall())
        interpretations = rows_to_dicts(conn.execute("SELECT * FROM claim_interpretations WHERE claim_id=? ORDER BY version DESC", (claim_id,)).fetchall())
        relationships = rows_to_dicts(conn.execute("SELECT * FROM relationships WHERE claim_a=? OR claim_b=? ORDER BY created_at DESC", (claim_id, claim_id)).fetchall())
    return {"claim": claim, "anchors": anchors, "interpretations": interpretations, "relationships": relationships}


@app.get("/api/v1/relationships")
def relationships(workspace_id: str | None = None, relationship_type: str | None = None) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        clauses = ["r.workspace_id=?"]
        params: list[Any] = [workspace_id]
        if relationship_type:
            clauses.append("r.relationship_type=?")
            params.append(relationship_type.upper())
        rows = conn.execute(
            f"""SELECT r.*,
            ca.subject AS subject_a,ca.predicate AS predicate_a,ca.raw_value AS value_a,
            ca.period AS period_a,ca.modality AS modality_a,da.name AS document_a,
            cb.subject AS subject_b,cb.predicate AS predicate_b,cb.raw_value AS value_b,
            cb.period AS period_b,cb.modality AS modality_b,db.name AS document_b
            FROM relationships r
            JOIN claims ca ON ca.id=r.claim_a JOIN documents da ON da.id=ca.document_id
            JOIN claims cb ON cb.id=r.claim_b JOIN documents db ON db.id=cb.document_id
            WHERE {' AND '.join(clauses)} ORDER BY r.created_at DESC""",
            params,
        ).fetchall()
    items = rows_to_dicts(rows)
    return {"items": items, "count": len(items)}


@app.get("/api/v1/entities")
def entities(workspace_id: str | None = None) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        rows = conn.execute("SELECT * FROM entities WHERE workspace_id=? ORDER BY canonical_name", (workspace_id,)).fetchall()
        aliases = conn.execute("SELECT ea.* FROM entity_aliases ea JOIN entities e ON e.id=ea.entity_id WHERE e.workspace_id=? ORDER BY ea.alias", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows), "aliases": rows_to_dicts(aliases)}


@app.get("/api/v1/predicates")
def predicates(workspace_id: str | None = None) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        rows = conn.execute("SELECT * FROM predicates WHERE workspace_id=? ORDER BY key", (workspace_id,)).fetchall()
        aliases = conn.execute("SELECT pa.* FROM predicate_aliases pa JOIN predicates p ON p.id=pa.predicate_id WHERE p.workspace_id=? ORDER BY pa.alias", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows), "aliases": rows_to_dicts(aliases)}


@app.get("/api/v1/budget")
def budget() -> dict[str, Any]:
    return budget_snapshot()


@app.post("/api/v1/embeddings/spaces")
def create_embeddings_space(payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = payload.get("workspace_id")
    model = payload.get("model")
    template_version = str(payload.get("template_version") or "identity-v1")
    if workspace_id:
        with db() as conn:
            if not conn.execute("SELECT 1 FROM workspaces WHERE id=?", (workspace_id,)).fetchone():
                raise HTTPException(404, "Workspace not found")
    space_id = create_embedding_space(workspace_id, model, template_version)
    with db() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM embedding_spaces WHERE id=?", (space_id,)).fetchone())
    return row or {"id": space_id}


@app.post("/api/v1/embeddings/{claim_id}")
def embed_claim_endpoint(claim_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    space_id = str(payload.get("space_id") or "")
    if not space_id:
        raise HTTPException(400, "space_id is required")
    try:
        return embed_claim(claim_id, space_id)
    except (ValueError, ProviderError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/v1/changes")
def changes(workspace_id: str | None = None) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        rows = conn.execute(
            """SELECT c.*,r.document_id,d.name AS document_name,r.status AS run_status
            FROM changes c LEFT JOIN runs r ON r.id=c.run_id
            LEFT JOIN documents d ON d.id=COALESCE(r.document_id,json_extract(c.details_json,'$.document_id'))
            WHERE c.workspace_id=? ORDER BY c.created_at DESC LIMIT 100""",
            (workspace_id,),
        ).fetchall()
    items = rows_to_dicts(rows)
    return {"items": items, "count": len(items)}


@app.get("/api/v1/exports/facts")
def export_facts(workspace_id: str | None = None, format: str = "json") -> Response:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM facts WHERE workspace_id=? AND active=1 ORDER BY subject,predicate,period", (workspace_id,)).fetchall())
    normalized_format = format.casefold()
    if normalized_format == "json":
        return JSONResponse(rows)
    fields = ["id", "subject", "predicate", "normalized_value", "display_value", "value_type", "unit", "period", "modality", "scope", "status", "reason", "revision"]
    if normalized_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: _export_cell(key, row.get(key)) for key in fields} for row in rows)
        return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=project-superjoin-facts.csv"})
    if normalized_format == "xlsx":
        try:
            from openpyxl import Workbook
        except ImportError as exc:  # pragma: no cover - dependency is bundled in the image
            raise HTTPException(503, "XLSX export dependency is unavailable") from exc
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Facts"
        sheet.append(fields)
        for row in rows:
            sheet.append([_export_cell(key, row.get(key)) for key in fields])
        stream = io.BytesIO()
        workbook.save(stream)
        return Response(stream.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=project-superjoin-facts.xlsx"})
    raise HTTPException(400, "format must be json, csv, or xlsx")


def _export_cell(key: str, value: Any) -> Any:
    """Neutralize formula-like source text while preserving decimal strings."""

    if not isinstance(value, str) or key in {"normalized_value", "revision"}:
        return value
    if value.startswith(("=", "+", "@")):
        return "'" + value
    return value


def _resolve_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = _workspace_or_default(payload.get("workspace_id"))
    subject = str(payload.get("subject") or "")
    predicate = str(payload.get("predicate") or "")
    period = payload.get("period")
    policy = str(payload.get("policy") or "strict")
    known_at_revision = payload.get("known_at_revision")
    if not subject or not predicate:
        raise HTTPException(400, "subject and predicate are required")
    return {"query": {"workspace_id": workspace_id, "subject": subject, "predicate": predicate, "period": period, "policy": policy, "known_at_revision": known_at_revision}, **resolve_fact(workspace_id, subject, predicate, period, policy, known_at_revision)}


@app.get("/api/v1/resolve")
def resolve(workspace_id: str | None = None, subject: str = "", predicate: str = "", period: str | None = None, policy: str = "strict", known_at_revision: int | None = None) -> dict[str, Any]:
    return _resolve_payload({"workspace_id": workspace_id, "subject": subject, "predicate": predicate, "period": period, "policy": policy, "known_at_revision": known_at_revision})


@app.post("/api/v1/resolve")
def resolve_post(payload: dict[str, Any]) -> dict[str, Any]:
    return _resolve_payload(payload)


@app.post("/api/v1/reviews")
def create_review(payload: dict[str, Any]) -> dict[str, Any]:
    required = {"workspace_id", "fact_id", "action", "rationale"}
    if not required.issubset(payload):
        raise HTTPException(400, "workspace_id, fact_id, action, and rationale are required")
    allowed_actions = {"keep_unresolved", "prefer", "select", "confirm_context", "invalidate", "revoke"}
    if payload["action"] not in allowed_actions:
        raise HTTPException(400, f"action must be one of {sorted(allowed_actions)}")
    with db() as conn:
        fact_row = conn.execute("SELECT revision FROM facts WHERE id=? AND workspace_id=?", (payload["fact_id"], payload["workspace_id"])).fetchone()
        if not fact_row:
            raise HTTPException(404, "Fact not found")
        based_on_revision = int(payload.get("based_on_revision", fact_row["revision"]))
        if based_on_revision != fact_row["revision"]:
            raise HTTPException(409, "Review is based on a stale fact revision")
        review_id = f"review-{uuid.uuid4().hex[:12]}"
        status = "revoked" if payload["action"] == "revoke" else "active"
        conn.execute("INSERT INTO reviews(id,workspace_id,fact_id,action,rationale,based_on_revision,status,revokes_review_id,decision_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (review_id, payload["workspace_id"], payload["fact_id"], payload["action"], payload["rationale"], based_on_revision, status, payload.get("revokes_review_id"), json.dumps(payload.get("decision", {})), utc_now()))
        if payload["action"] == "revoke" and payload.get("revokes_review_id"):
            conn.execute("UPDATE reviews SET status='revoked',revoked_at=? WHERE id=? AND workspace_id=?", (utc_now(), payload["revokes_review_id"], payload["workspace_id"]))
    return {"id": review_id, "status": "recorded"}


@app.get("/api/v1/reviews")
def reviews(workspace_id: str | None = None, include_stale: bool = True) -> dict[str, Any]:
    workspace_id = _workspace_or_default(workspace_id)
    with db() as conn:
        if include_stale:
            rows = conn.execute("SELECT * FROM reviews WHERE workspace_id=? ORDER BY created_at DESC", (workspace_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM reviews WHERE workspace_id=? AND stale=0 AND status='active' ORDER BY created_at DESC", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/settings")
def settings_view() -> dict[str, Any]:
    roles = {
        "extraction": {"model": settings.extraction_model, "configured": available("extraction"), "base_url": _public_endpoint(settings.extraction_base_url), "key_configured": bool(settings.extraction_api_key), "auth_header": settings.extraction_auth_header, "auth_scheme": settings.extraction_auth_scheme, "send_model": settings.extraction_send_model, "chat_path": _public_endpoint(settings.extraction_chat_path), "timeout_seconds": settings.extraction_timeout_seconds, "max_output_tokens": settings.extraction_max_output_tokens, "concurrency": settings.extraction_concurrency, "structured_output_mode": settings.extraction_structured_output_mode},
        "reasoning": {"model": settings.reasoning_model, "configured": available("reasoning"), "base_url": _public_endpoint(settings.reasoning_base_url), "key_configured": bool(settings.reasoning_api_key), "auth_header": settings.reasoning_auth_header, "auth_scheme": settings.reasoning_auth_scheme, "send_model": settings.reasoning_send_model, "chat_path": _public_endpoint(settings.reasoning_chat_path), "timeout_seconds": settings.reasoning_timeout_seconds, "max_output_tokens": settings.reasoning_max_output_tokens, "concurrency": settings.reasoning_concurrency, "structured_output_mode": settings.reasoning_structured_output_mode},
        "vision": {"model": settings.vision_model, "configured": available("vision"), "base_url": _public_endpoint(settings.vision_base_url), "key_configured": bool(settings.vision_api_key), "auth_header": settings.vision_auth_header, "auth_scheme": settings.vision_auth_scheme, "send_model": settings.vision_send_model, "chat_path": _public_endpoint(settings.vision_chat_path), "timeout_seconds": settings.vision_timeout_seconds, "max_output_tokens": settings.vision_max_output_tokens, "concurrency": settings.vision_concurrency, "structured_output_mode": settings.vision_structured_output_mode},
        "embeddings": {"model": settings.embedding_model, "configured": available("embedding"), "base_url": _public_endpoint(settings.embedding_base_url), "key_configured": bool(settings.embedding_api_key), "auth_header": settings.embedding_auth_header, "auth_scheme": settings.embedding_auth_scheme, "send_model": settings.embedding_send_model, "embedding_path": _public_endpoint(settings.embedding_path), "timeout_seconds": settings.embedding_timeout_seconds, "concurrency": settings.embedding_concurrency, "task_type": settings.embedding_task_type, "dimensions": settings.embedding_dimensions, "include_dimensions": settings.embedding_include_dimensions},
    }
    return {
        "project": "Project SuperJoin",
        "provider_configured": available(),
        "roles": roles,
        "configured_roles": {name: role["configured"] for name, role in roles.items()},
        "embedding_dimensions": settings.embedding_dimensions,
        "provider_retry": {
            "attempts": settings.provider_retry_attempts,
            "backoff_seconds": settings.provider_retry_backoff_seconds,
        },
        "parser": {
            "backend": settings.parser_backend,
            "local_ocr_enabled": settings.local_ocr_enabled,
            "timeout_seconds": settings.parser_timeout_seconds,
        },
        "presets": provider_presets(),
        "budget": budget_snapshot(),
    }


@app.post("/api/v1/settings/{role}")
def update_provider_settings(role: str, update: ProviderRoleUpdate) -> dict[str, Any]:
    with db() as conn:
        active = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status IN ('queued','processing')"
        ).fetchone()[0]
    if active:
        raise HTTPException(
            409,
            "Provider settings cannot change while an ingestion run is active",
        )
    try:
        apply_provider_update(role, update)
    except ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    return settings_view()


@app.post("/api/v1/settings/actions/copy-provider")
def copy_provider_settings(request: ProviderConnectionCopy) -> dict[str, Any]:
    with db() as conn:
        active = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status IN ('queued','processing')"
        ).fetchone()[0]
    if active:
        raise HTTPException(
            409,
            "Provider settings cannot change while an ingestion run is active",
        )
    try:
        copy_provider_connection(request)
    except ProviderError as exc:
        raise HTTPException(400, str(exc)) from exc
    return settings_view()


@app.post("/api/v1/settings/{role}/test")
def test_provider_settings(role: str) -> dict[str, Any]:
    try:
        return probe(role)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
if web_dist.exists():
    app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    path = web_dist / "index.html"
    if path.exists():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Project SuperJoin</h1><p>Frontend has not been built yet.</p>")
