from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from typing import Any

import numpy as np

from .budget import BudgetExceeded, estimate_cost, reserve, settle
from .config import settings
from .db import db, rows_to_dicts, utc_now
from .providers import ProviderError, available, embed, provider_identity


def lexical_claims(workspace_id: str, query: str, limit: int = 30) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    safe = " ".join(token for token in re.findall(r"[A-Za-z0-9_]+", query) if token.upper() not in {"OR", "AND", "NOT"})
    if not safe:
        return []
    with db() as conn:
        rows = conn.execute("""SELECT c.*,bm25(claims_fts) AS rank FROM claims_fts
            JOIN claims c ON c.id=claims_fts.claim_id
            WHERE claims_fts.workspace_id=? AND claims_fts MATCH ? ORDER BY rank LIMIT ?""", (workspace_id, safe, max(1, min(limit, 100)))).fetchall()
    return rows_to_dicts(rows)


def identity_text(claim: dict[str, Any]) -> str:
    return " | ".join(str(claim.get(key) or "") for key in ("subject", "predicate", "period", "modality", "scope"))


def evidence_text(claim: dict[str, Any]) -> str:
    return identity_text(claim) + " | " + str(claim.get("raw_value") or "")


def reciprocal_rank_fusion(lanes: list[list[dict[str, Any]]], key: str = "id", k: int = 60, limit: int = 20) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    records: dict[str, dict[str, Any]] = {}
    for lane in lanes:
        for rank, item in enumerate(lane, start=1):
            identifier = str(item.get(key))
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (k + rank)
            records[identifier] = item
    ordered = sorted(scores, key=lambda identifier: scores[identifier], reverse=True)[:limit]
    return [{**records[identifier], "retrieval_score": round(scores[identifier], 6)} for identifier in ordered]


def cosine_candidates(workspace_id: str, query_vector: list[float], limit: int = 30, space_id: str | None = None) -> list[dict[str, Any]]:
    vector = np.asarray(query_vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return []
    with db() as conn:
        params: list[Any] = [workspace_id]
        clause = "c.workspace_id=?"
        if space_id:
            clause += " AND e.space_id=?"
            params.append(space_id)
        rows = conn.execute(f"SELECT c.*,e.vector_json,e.space_id FROM embeddings e JOIN claims c ON c.id=e.claim_id WHERE {clause}", params).fetchall()
    scored: list[dict[str, Any]] = []
    for row in rows:
        try:
            candidate = np.asarray(json.loads(row["vector_json"]), dtype=np.float32)
            if candidate.shape != vector.shape:
                continue
            candidate_norm = np.linalg.norm(candidate)
            if candidate_norm == 0:
                continue
            item = dict(row)
            item.pop("vector_json", None)
            item["retrieval_score"] = float(np.dot(vector, candidate) / (norm * candidate_norm))
            scored.append(item)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return sorted(scored, key=lambda item: item["retrieval_score"], reverse=True)[:limit]


def search_claims(workspace_id: str, query: str, limit: int = 20, query_vector: list[float] | None = None, space_id: str | None = None) -> dict[str, Any]:
    embedding_error = None
    if query_vector is None:
        try:
            query_vector = embed_query(workspace_id, query, space_id)
        except (BudgetExceeded, ProviderError, ValueError) as exc:
            embedding_error = str(exc)
    lexical = lexical_claims(workspace_id, query, min(30, limit * 2))
    dense = cosine_candidates(workspace_id, query_vector, min(30, limit * 2), space_id=space_id) if query_vector else []
    fused = reciprocal_rank_fusion([lane for lane in (lexical, dense) if lane], limit=limit) if dense else lexical[:limit]
    return {"items": fused, "lanes": {"lexical": len(lexical), "dense": len(dense), "hybrid": len(fused)}, "embedding_available": bool(dense), "embedding_error": embedding_error}


def create_embedding_space(workspace_id: str | None = None, model: str | None = None, template_version: str = "identity-v1") -> str:
    space_id = f"space-{uuid.uuid4().hex[:12]}"
    with db() as conn:
        conn.execute("INSERT INTO embedding_spaces(id,workspace_id,provider,model,dimensions,template_version,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (space_id, workspace_id, settings.embedding_base_url or "offline", model or settings.embedding_model, settings.embedding_dimensions, template_version, "active", utc_now()))
    return space_id


def embed_claim(claim_id: str, space_id: str) -> dict[str, Any]:
    if not available("embedding"):
        raise ProviderError("No embedding provider configured")
    with db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        space = conn.execute("SELECT * FROM embedding_spaces WHERE id=?", (space_id,)).fetchone()
    if not claim or not space:
        raise ValueError("claim or embedding space not found")
    text = identity_text(dict(claim)) + "\n" + evidence_text(dict(claim))
    content_hash = hashlib.sha256((provider_identity("embedding", space["model"]) + "\n" + text).encode("utf-8")).hexdigest()
    with db() as conn:
        cached = conn.execute("SELECT dimensions,content_hash FROM embeddings e JOIN embedding_spaces s ON s.id=e.space_id WHERE e.space_id=? AND e.claim_id=?", (space_id, claim_id)).fetchone()
    if cached and cached["content_hash"] == content_hash:
        return {"claim_id": claim_id, "space_id": space_id, "dimensions": cached["dimensions"], "content_hash": content_hash, "cached": True}
    reservation = None
    try:
        reservation = reserve(
            None,
            "embedding",
            space["model"],
            content_hash,
            estimate_cost(len(text), 32),
            request_chars=len(text),
        )
        result = embed(text, space["model"])
        vector = _extract_vector(result.data)
    except (BudgetExceeded, ProviderError, ValueError) as exc:
        if reservation:
            settle(reservation, 0.0, status="failed", attempts=getattr(exc, "attempts", 1))
        raise
    if len(vector) != int(space["dimensions"]):
        if reservation:
            settle(reservation, 0.0, status="failed", input_tokens=result.input_tokens, output_tokens=result.output_tokens, latency_ms=result.latency_ms, attempts=result.attempts)
        raise ValueError(f"embedding dimension mismatch: expected {space['dimensions']}, got {len(vector)}")
    if reservation:
        settle(reservation, result.estimated_cost, input_tokens=result.input_tokens, output_tokens=result.output_tokens, latency_ms=result.latency_ms, attempts=result.attempts)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    vector = [float(value / norm) for value in vector]
    with db() as conn:
        conn.execute("INSERT INTO embeddings(id,space_id,claim_id,content_hash,vector_json,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(space_id,claim_id) DO UPDATE SET content_hash=excluded.content_hash,vector_json=excluded.vector_json,created_at=excluded.created_at", (f"embedding-{uuid.uuid4().hex[:12]}", space_id, claim_id, content_hash, json.dumps(vector), utc_now()))
    return {"claim_id": claim_id, "space_id": space_id, "dimensions": len(vector), "content_hash": content_hash}


def embed_query(workspace_id: str, query: str, space_id: str | None = None) -> list[float] | None:
    """Embed a search query only when an active compatible index exists."""

    if not query.strip() or not available("embedding"):
        return None
    with db() as conn:
        if space_id:
            space = conn.execute("SELECT * FROM embedding_spaces WHERE id=? AND (workspace_id=? OR workspace_id IS NULL) AND status='active'", (space_id, workspace_id)).fetchone()
        else:
            space = conn.execute("SELECT * FROM embedding_spaces WHERE status='active' AND (workspace_id=? OR workspace_id IS NULL) ORDER BY workspace_id IS NULL,created_at DESC LIMIT 1", (workspace_id,)).fetchone()
        if not space or not conn.execute("SELECT 1 FROM embeddings e JOIN claims c ON c.id=e.claim_id WHERE e.space_id=? AND c.workspace_id=? LIMIT 1", (space["id"], workspace_id)).fetchone():
            return None
    digest = hashlib.sha256(f"query-v1:{space['id']}:{provider_identity('embedding', space['model'])}:{query}".encode()).hexdigest()
    with db() as conn:
        cached = conn.execute("SELECT response_json FROM model_cache WHERE role='embedding-query' AND model=? AND input_hash=?", (space["model"], digest)).fetchone()
    if cached:
        return _extract_vector(json.loads(cached["response_json"]))
    reservation = None
    try:
        reservation = reserve(
            None,
            "embedding-query",
            space["model"],
            digest,
            estimate_cost(len(query), 32),
            request_chars=len(query),
        )
        result = embed(query, space["model"])
        vector = _extract_vector(result.data)
        if len(vector) != int(space["dimensions"]):
            raise ValueError(f"embedding dimension mismatch: expected {space['dimensions']}, got {len(vector)}")
    except (BudgetExceeded, ProviderError, ValueError) as exc:
        if reservation:
            settle(reservation, 0.0, status="failed", attempts=getattr(exc, "attempts", 1))
        raise
    if reservation:
        settle(reservation, result.estimated_cost, input_tokens=result.input_tokens, output_tokens=result.output_tokens, latency_ms=result.latency_ms, attempts=result.attempts)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    vector = [float(value / norm) for value in vector]
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO model_cache(id,role,model,input_hash,response_json,estimated_cost,created_at) VALUES(?,?,?,?,?,?,?)", (f"cache-{uuid.uuid4().hex[:12]}", "embedding-query", result.model, digest, json.dumps(vector), result.estimated_cost, utc_now()))
    return vector


def _extract_vector(data: Any) -> list[float]:
    if isinstance(data, dict):
        rows = data.get("data") or data.get("embeddings")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            data = rows[0].get("embedding")
        elif isinstance(rows, list):
            data = rows[0]
    if not isinstance(data, list) or not all(isinstance(value, (int, float)) for value in data):
        raise ValueError("provider returned no embedding vector")
    return [float(value) for value in data]
