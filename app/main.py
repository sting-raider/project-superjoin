from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .budget import snapshot as budget_snapshot
from .config import settings
from .db import db, init_db, row_to_dict, rows_to_dicts, utc_now
from .demo_data import DEMO_CASES
from .knowledge import resolve_fact
from .pipeline import process_document
from .retrieval import search_claims
from .seed import seed_demo

app = FastAPI(title="Project SuperJoin", version="0.1.0", description="Evidence-first temporal fact knowledge layer")


@app.on_event("startup")
def startup() -> None:
    init_db()
    if settings.demo_mode:
        seed_demo()


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    with db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "project": "Project SuperJoin", "demo_mode": settings.demo_mode, "provider_configured": bool(settings.ai_base_url and settings.ai_api_key)}


@app.get("/api/v1/workspaces")
def workspaces() -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM workspaces ORDER BY name").fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/overview")
def overview(workspace_id: str = "delhivery") -> dict[str, Any]:
    with db() as conn:
        workspace = row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone())
        if not workspace:
            raise HTTPException(404, "Workspace not found")
        counts = {}
        for table in ("documents", "claims", "facts", "relationships", "changes"):
            counts[table] = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE workspace_id=?", (workspace_id,)).fetchone()["count"]
        status_rows = conn.execute("SELECT status,COUNT(*) AS count FROM facts WHERE workspace_id=? GROUP BY status", (workspace_id,)).fetchall()
        latest = conn.execute("SELECT * FROM changes WHERE workspace_id=? ORDER BY created_at DESC LIMIT 8", (workspace_id,)).fetchall()
    return {"workspace": workspace, "counts": counts, "statuses": {row["status"]: row["count"] for row in status_rows}, "latest_changes": rows_to_dicts(latest), "demo": settings.demo_mode}


@app.get("/api/v1/documents")
def documents(workspace_id: str = "delhivery") -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM documents WHERE workspace_id=? ORDER BY published_at DESC, name", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.post("/api/v1/documents", status_code=202)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), workspace_id: str = Form("delhivery")) -> dict[str, Any]:  # noqa: B008
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF file")
    data = await file.read()
    if not data.startswith(b"%PDF-"):
        raise HTTPException(400, "The uploaded file is not a PDF")
    if len(data) > settings.max_pdf_mb * 1024 * 1024:
        raise HTTPException(413, f"PDF exceeds the {settings.max_pdf_mb} MB limit")
    digest = hashlib.sha256(data).hexdigest()
    document_id = f"doc-{digest[:12]}"
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    settings.ensure_dirs()
    stored = settings.upload_dir / f"{document_id}.pdf"
    stored.write_bytes(data)
    with db() as conn:
        if not conn.execute("SELECT 1 FROM workspaces WHERE id=?", (workspace_id,)).fetchone():
            raise HTTPException(404, "Workspace not found")
        existing = conn.execute("SELECT * FROM documents WHERE workspace_id=? AND sha256=?", (workspace_id, digest)).fetchone()
        if existing:
            return {"document": row_to_dict(existing), "run": None, "deduplicated": True}
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
        conn.execute("INSERT INTO runs(id,workspace_id,mode,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (new_run_id, document["workspace_id"], "retry", "queued", 0, "Retry queued", utc_now(), utc_now()))
        data = Path(document["stored_path"]).read_bytes()
    background_tasks.add_task(process_document, new_run_id, document["id"], document["workspace_id"], data, document["name"])
    return {"run_id": new_run_id, "document_id": document["id"]}


@app.get("/api/v1/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    async def events():
        last = None
        for _ in range(120):
            with db() as conn:
                row = row_to_dict(conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
            if row and row != last:
                last = row
                yield f"data: {json.dumps(row)}\n\n"
            if row and row.get("status") in {"complete", "failed"}:
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/v1/facts")
def facts(workspace_id: str = "delhivery", q: str = "", status: str | None = None, limit: int = 200) -> dict[str, Any]:
    with db() as conn:
        params: list[Any] = [workspace_id]
        clauses = ["workspace_id=?"]
        if q:
            query = "*" + q.replace("*", "") + "*"
            rows = conn.execute("SELECT claim_id FROM claims_fts WHERE workspace_id=? AND claims_fts MATCH ? LIMIT ?", (workspace_id, query, limit)).fetchall()
            claim_ids = [row["claim_id"] for row in rows]
            if claim_ids:
                clauses.append("(subject LIKE ? OR predicate LIKE ? OR display_value LIKE ? OR id IN (SELECT 'fact-claim-' || id FROM claims WHERE id IN (" + ",".join("?" for _ in claim_ids) + ")))" )
                params.extend([f"%{q}%", f"%{q}%", f"%{q}%", *claim_ids])
            else:
                clauses.append("(subject LIKE ? OR predicate LIKE ? OR display_value LIKE ?)")
                params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        if status:
            clauses.append("status=?")
            params.append(status)
        params.append(max(1, min(limit, 500)))
        rows = conn.execute(f"SELECT * FROM facts WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?", params).fetchall()
    return {"items": rows_to_dicts(rows), "count": len(rows)}


@app.get("/api/v1/search")
def search(workspace_id: str = "delhivery", q: str = "", limit: int = 20) -> dict[str, Any]:
    if not q.strip():
        return {"items": [], "lanes": {"lexical": 0, "dense": 0, "hybrid": 0}, "embedding_available": False}
    return search_claims(workspace_id, q, max(1, min(limit, 100)))


@app.get("/api/v1/facts/{fact_id}")
def fact(fact_id: str) -> dict[str, Any]:
    with db() as conn:
        item = row_to_dict(conn.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone())
        if not item:
            raise HTTPException(404, "Fact not found")
        claims = rows_to_dicts(conn.execute("SELECT * FROM claims WHERE workspace_id=? AND subject=? AND predicate=? AND (period=? OR ? IS NULL)", (item["workspace_id"], item["subject"], item["predicate"], item["period"], item["period"])).fetchall())
        relationships = rows_to_dicts(conn.execute("SELECT * FROM relationships WHERE workspace_id=? AND (claim_a IN (SELECT id FROM claims WHERE subject=? AND predicate=?) OR claim_b IN (SELECT id FROM claims WHERE subject=? AND predicate=?))", (item["workspace_id"], item["subject"], item["predicate"], item["subject"], item["predicate"])).fetchall())
        anchors = rows_to_dicts(conn.execute("""SELECT ea.*,ce.claim_id,ce.purpose
            FROM evidence_anchors ea JOIN claim_evidence ce ON ce.anchor_id=ea.id
            WHERE ce.claim_id IN (SELECT id FROM claims WHERE workspace_id=? AND subject=? AND predicate=? AND (period=? OR ? IS NULL))
            ORDER BY ea.pdf_page,ea.id""", (item["workspace_id"], item["subject"], item["predicate"], item["period"], item["period"])).fetchall())
        interpretations = rows_to_dicts(conn.execute("SELECT * FROM claim_interpretations WHERE claim_id IN (SELECT id FROM claims WHERE workspace_id=? AND subject=? AND predicate=? AND (period=? OR ? IS NULL)) ORDER BY created_at", (item["workspace_id"], item["subject"], item["predicate"], item["period"], item["period"])).fetchall())
    return {"fact": item, "claims": claims, "anchors": anchors, "interpretations": interpretations, "relationships": relationships}


@app.get("/api/v1/relationships")
def relationships(workspace_id: str = "delhivery", relationship_type: str | None = None) -> dict[str, Any]:
    with db() as conn:
        if relationship_type:
            rows = conn.execute("SELECT * FROM relationships WHERE workspace_id=? AND relationship_type=? ORDER BY created_at DESC", (workspace_id, relationship_type.upper())).fetchall()
        else:
            rows = conn.execute("SELECT * FROM relationships WHERE workspace_id=? ORDER BY created_at DESC", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/entities")
def entities(workspace_id: str = "delhivery") -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM entities WHERE workspace_id=? ORDER BY canonical_name", (workspace_id,)).fetchall()
        aliases = conn.execute("SELECT ea.* FROM entity_aliases ea JOIN entities e ON e.id=ea.entity_id WHERE e.workspace_id=? ORDER BY ea.alias", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows), "aliases": rows_to_dicts(aliases)}


@app.get("/api/v1/predicates")
def predicates(workspace_id: str = "delhivery") -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM predicates WHERE workspace_id=? ORDER BY key", (workspace_id,)).fetchall()
        aliases = conn.execute("SELECT pa.* FROM predicate_aliases pa JOIN predicates p ON p.id=pa.predicate_id WHERE p.workspace_id=? ORDER BY pa.alias", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows), "aliases": rows_to_dicts(aliases)}


@app.get("/api/v1/budget")
def budget() -> dict[str, Any]:
    return budget_snapshot()


@app.get("/api/v1/changes")
def changes(workspace_id: str = "delhivery") -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM changes WHERE workspace_id=? ORDER BY created_at DESC LIMIT 100", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/cases")
def cases() -> dict[str, Any]:
    return {"items": DEMO_CASES}


def _resolve_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = str(payload.get("workspace_id") or "delhivery")
    subject = str(payload.get("subject") or "")
    predicate = str(payload.get("predicate") or "")
    period = payload.get("period")
    policy = str(payload.get("policy") or "strict")
    known_at_revision = payload.get("known_at_revision")
    if not subject or not predicate:
        raise HTTPException(400, "subject and predicate are required")
    return {"query": {"workspace_id": workspace_id, "subject": subject, "predicate": predicate, "period": period, "policy": policy, "known_at_revision": known_at_revision}, **resolve_fact(workspace_id, subject, predicate, period, policy, known_at_revision)}


@app.get("/api/v1/resolve")
def resolve(workspace_id: str = "delhivery", subject: str = "", predicate: str = "", period: str | None = None, policy: str = "strict", known_at_revision: int | None = None) -> dict[str, Any]:
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
def reviews(workspace_id: str = "delhivery", include_stale: bool = True) -> dict[str, Any]:
    with db() as conn:
        if include_stale:
            rows = conn.execute("SELECT * FROM reviews WHERE workspace_id=? ORDER BY created_at DESC", (workspace_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM reviews WHERE workspace_id=? AND stale=0 AND status='active' ORDER BY created_at DESC", (workspace_id,)).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.get("/api/v1/settings")
def settings_view() -> dict[str, Any]:
    return {"project": "Project SuperJoin", "demo_mode": settings.demo_mode, "provider_configured": bool(settings.ai_base_url and settings.ai_api_key), "roles": {"extraction": settings.extraction_model, "reasoning": settings.reasoning_model, "vision": settings.vision_model, "embeddings": settings.embedding_model}, "embedding_dimensions": settings.embedding_dimensions, "budget": budget_snapshot()}


@app.post("/api/v1/demo/reset")
def reset_demo() -> dict[str, str]:
    with db() as conn:
        for table in ("reviews", "fact_memberships", "fact_versions", "claim_evidence", "claim_interpretations", "changes", "relationships", "facts", "claims_fts", "claims", "evidence_anchors", "page_artifacts", "documents", "run_events", "runs"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("UPDATE workspaces SET active_revision=1")
    seed_demo()
    return {"status": "reset"}


web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
if web_dist.exists():
    app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    path = web_dist / "index.html"
    if path.exists():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Project SuperJoin</h1><p>Frontend has not been built yet.</p>")
