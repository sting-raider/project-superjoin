from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable

from .config import settings
from .db import db, utc_now
from .demo_data import (
    DEMO_CASES,
    DEMO_CLAIMS,
    DEMO_DOCUMENTS,
    DEMO_RELATIONSHIPS,
    DEMO_REPLAY,
    DEMO_WORKSPACES,
)
from .knowledge import assess_relationships, rebuild_workspace, relationship_cache_fingerprint
from .provenance import page_artifact_id, persist_anchor, persist_interpretation
from .registry import register_workspace_claims


def _selected_demo_rows(document_ids: Iterable[str] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    selected = set(document_ids) if document_ids is not None else {row["id"] for row in DEMO_DOCUMENTS}
    documents = [row for row in DEMO_DOCUMENTS if row["id"] in selected]
    claims = [row for row in DEMO_CLAIMS if row["document_id"] in selected]
    workspace_ids = {row["workspace_id"] for row in documents}
    workspaces = [row for row in DEMO_WORKSPACES if row["id"] in workspace_ids]
    return workspaces, documents, claims


def seed_demo(document_ids: Iterable[str] | None = None) -> None:
    """Load recorded rows, then run the normal registry/reasoning pipeline."""

    workspaces, documents, claims = _selected_demo_rows(document_ids)
    if not workspaces:
        return
    with db() as conn:
        for workspace in workspaces:
            conn.execute(
                "INSERT OR IGNORE INTO workspaces(id,name,description,created_at) VALUES(?,?,?,?)",
                (workspace["id"], workspace["name"], workspace["description"], utc_now()),
            )
        for document in documents:
            digest = hashlib.sha256(document["id"].encode()).hexdigest()
            conn.execute(
                """INSERT OR IGNORE INTO documents
                (id,workspace_id,name,publisher,source_url,sha256,page_count,status,parser,quality_score,published_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (document["id"], document["workspace_id"], document["name"], document["publisher"], document["source_url"], digest, document["page_count"], "complete", "recorded-demo", 0.96, document["published_at"], utc_now()),
            )
        for claim in claims:
            created_at = utc_now()
            conn.execute(
                """INSERT OR IGNORE INTO claims
                (id,workspace_id,document_id,subject,predicate,raw_value,normalized_value,value_type,unit,precision,period,modality,scope,evidence_json,grounding_status,extraction_status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (claim["id"], claim["workspace_id"], claim["document_id"], claim["subject"], claim["predicate"], claim["raw_value"], claim["normalized_value"], claim["value_type"], claim["unit"], claim.get("precision"), claim["period"], claim["modality"], claim["scope"], json.dumps(claim["evidence"]), "grounded", "accepted", created_at),
            )
            conn.execute(
                "UPDATE claims SET precision=? WHERE id=? AND precision IS NULL",
                (claim.get("precision"), claim["id"]),
            )
            conn.execute("INSERT OR IGNORE INTO claims_fts(claim_id,workspace_id,subject,predicate,raw_value,period,modality,scope) VALUES(?,?,?,?,?,?,?,?)", (claim["id"], claim["workspace_id"], claim["subject"], claim["predicate"], claim["raw_value"], claim["period"] or "", claim["modality"] or "", claim["scope"] or ""))
            evidence = claim["evidence"]
            page = int(evidence.get("pdf_page") or 1)
            page_id = page_artifact_id(claim["document_id"], page)
            conn.execute(
                """INSERT OR IGNORE INTO page_artifacts
                (id,document_id,page_number,width,height,native_text,parser,parser_version,quality_score,quality_flags_json,disposition,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (page_id, claim["document_id"], page, 1200.0, 1600.0, evidence.get("text", ""), "recorded-demo", "recorded-demo-1", 0.96, "[]", "native", created_at),
            )
            anchor_id = persist_anchor(conn, claim["document_id"], evidence)
            conn.execute("INSERT OR IGNORE INTO claim_evidence(claim_id,anchor_id,purpose,created_at) VALUES(?,?,?,?)", (claim["id"], anchor_id, "assertion", created_at))
            persist_interpretation(conn, claim, claim["id"], created_at)
        demo_claim_ids = [claim["id"] for claim in claims]
        if demo_claim_ids:
            placeholders = ",".join("?" for _ in demo_claim_ids)
            conn.execute(
                f"DELETE FROM relationships WHERE claim_a IN ({placeholders}) OR claim_b IN ({placeholders})",
                (*demo_claim_ids, *demo_claim_ids),
            )
        for case in DEMO_CASES:
            if case["workspace_id"] in {row["id"] for row in workspaces}:
                conn.execute("INSERT OR IGNORE INTO changes(id,workspace_id,run_id,kind,summary,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (f"change-{case['id']}", case["workspace_id"], "demo-seed", "demo_case", case["title"], json.dumps(case), utc_now()))
    for workspace in workspaces:
        register_workspace_claims(workspace["id"])
        _seed_recorded_reasoning_outputs(workspace["id"])
        assess_relationships(workspace["id"])
        rebuild_workspace(workspace["id"], advance_revision=False)


def clear_demo_workspace_data(workspace_ids: Iterable[str] | None = None) -> None:
    """Clear only the recorded demo sandbox, preserving live workspaces."""

    selected = set(workspace_ids) if workspace_ids is not None else {row["id"] for row in DEMO_WORKSPACES}
    if not selected:
        return
    placeholders = ",".join("?" for _ in selected)
    params = tuple(sorted(selected))
    with db() as conn:
        documents = [row["id"] for row in conn.execute(f"SELECT id FROM documents WHERE workspace_id IN ({placeholders})", params).fetchall()]
        claims = [row["id"] for row in conn.execute(f"SELECT id FROM claims WHERE workspace_id IN ({placeholders})", params).fetchall()]
        facts = [row["id"] for row in conn.execute(f"SELECT id FROM facts WHERE workspace_id IN ({placeholders})", params).fetchall()]
        versions = [row["id"] for row in conn.execute(f"SELECT id FROM fact_versions WHERE fact_id IN ({','.join('?' for _ in facts)})", tuple(facts)).fetchall()] if facts else []
        runs = [row["id"] for row in conn.execute(f"SELECT id FROM runs WHERE workspace_id IN ({placeholders})", params).fetchall()]
        spaces = [row["id"] for row in conn.execute(f"SELECT id FROM embedding_spaces WHERE workspace_id IN ({placeholders})", params).fetchall()]
        entities = [row["id"] for row in conn.execute(f"SELECT id FROM entities WHERE workspace_id IN ({placeholders})", params).fetchall()]
        predicates = [row["id"] for row in conn.execute(f"SELECT id FROM predicates WHERE workspace_id IN ({placeholders})", params).fetchall()]

        if facts:
            fact_placeholders = ",".join("?" for _ in facts)
            conn.execute(f"DELETE FROM reviews WHERE fact_id IN ({fact_placeholders})", tuple(facts))
        if versions:
            version_placeholders = ",".join("?" for _ in versions)
            conn.execute(f"DELETE FROM fact_memberships WHERE fact_version_id IN ({version_placeholders})", tuple(versions))
            conn.execute(f"DELETE FROM fact_versions WHERE id IN ({version_placeholders})", tuple(versions))
        conn.execute(f"DELETE FROM relationships WHERE workspace_id IN ({placeholders})", params)
        conn.execute(f"DELETE FROM facts WHERE workspace_id IN ({placeholders})", params)
        if claims:
            claim_placeholders = ",".join("?" for _ in claims)
            conn.execute(f"DELETE FROM claim_evidence WHERE claim_id IN ({claim_placeholders})", tuple(claims))
            conn.execute(f"DELETE FROM claim_interpretations WHERE claim_id IN ({claim_placeholders})", tuple(claims))
            conn.execute(f"DELETE FROM claims_fts WHERE workspace_id IN ({placeholders})", params)
            conn.execute(f"DELETE FROM claims WHERE id IN ({claim_placeholders})", tuple(claims))
        if documents:
            document_placeholders = ",".join("?" for _ in documents)
            conn.execute(f"DELETE FROM evidence_anchors WHERE document_id IN ({document_placeholders})", tuple(documents))
            conn.execute(f"DELETE FROM page_artifacts WHERE document_id IN ({document_placeholders})", tuple(documents))
            conn.execute(f"DELETE FROM extraction_batches WHERE document_id IN ({document_placeholders})", tuple(documents))
        if runs:
            run_placeholders = ",".join("?" for _ in runs)
            conn.execute(f"DELETE FROM model_calls WHERE run_id IN ({run_placeholders})", tuple(runs))
            conn.execute(f"DELETE FROM run_events WHERE run_id IN ({run_placeholders})", tuple(runs))
        conn.execute(f"DELETE FROM runs WHERE workspace_id IN ({placeholders})", params)
        if entities:
            entity_placeholders = ",".join("?" for _ in entities)
            conn.execute(f"DELETE FROM entity_aliases WHERE entity_id IN ({entity_placeholders})", tuple(entities))
            conn.execute(f"DELETE FROM entities WHERE id IN ({entity_placeholders})", tuple(entities))
        if predicates:
            predicate_placeholders = ",".join("?" for _ in predicates)
            conn.execute(f"DELETE FROM predicate_aliases WHERE predicate_id IN ({predicate_placeholders})", tuple(predicates))
            conn.execute(f"DELETE FROM predicates WHERE id IN ({predicate_placeholders})", tuple(predicates))
        conn.execute(f"DELETE FROM registry_decisions WHERE workspace_id IN ({placeholders})", params)
        if spaces:
            space_placeholders = ",".join("?" for _ in spaces)
            conn.execute(f"DELETE FROM embeddings WHERE space_id IN ({space_placeholders})", tuple(spaces))
            conn.execute(f"DELETE FROM embedding_spaces WHERE id IN ({space_placeholders})", tuple(spaces))
        conn.execute(f"DELETE FROM changes WHERE workspace_id IN ({placeholders})", params)
        conn.execute(f"DELETE FROM demo_replay_state WHERE workspace_id IN ({placeholders})", params)
        if documents:
            document_placeholders = ",".join("?" for _ in documents)
            conn.execute(f"DELETE FROM documents WHERE id IN ({document_placeholders})", tuple(documents))
        conn.execute(f"UPDATE workspaces SET active_revision=1 WHERE id IN ({placeholders})", params)


def replay_status() -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM demo_replay_state WHERE id=?", (DEMO_REPLAY["id"],)).fetchone()
    if not row:
        return {"stage": "ready", "recorded": True, "model_calls": 0}
    payload = dict(row)
    for key in ("baseline_document_ids_json", "added_document_ids_json"):
        payload[key.removesuffix("_json")] = json.loads(payload.pop(key) or "[]")
    payload["recorded"] = True
    return payload


def start_replay() -> dict:
    started = time.perf_counter()
    workspace_id = DEMO_REPLAY["workspace_id"]
    clear_demo_workspace_data({workspace_id})
    seed_demo(DEMO_REPLAY["baseline_document_ids"])
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _write_replay_state("baseline_ready", elapsed_ms, None, "The authentic two-document checkpoint is ready.")
    return replay_status()


def advance_replay() -> dict:
    started = time.perf_counter()
    seed_demo([*DEMO_REPLAY["baseline_document_ids"], *DEMO_REPLAY["added_document_ids"]])
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _write_replay_state("replayed", elapsed_ms, 0.0, "Recorded model outputs; no API calls.")
    return replay_status()


def _write_replay_state(stage: str, elapsed_ms: float, cost_usd: float | None, limitation: str | None) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO demo_replay_state
            (id,workspace_id,stage,baseline_document_ids_json,added_document_ids_json,original_runtime_ms,original_cost_usd,replay_runtime_ms,replay_cost_usd,model_calls,limitation,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET stage=excluded.stage,
              baseline_document_ids_json=excluded.baseline_document_ids_json,
              added_document_ids_json=excluded.added_document_ids_json,
              original_runtime_ms=excluded.original_runtime_ms,
              original_cost_usd=excluded.original_cost_usd,
              replay_runtime_ms=excluded.replay_runtime_ms,
              replay_cost_usd=excluded.replay_cost_usd,
              model_calls=excluded.model_calls,
              limitation=excluded.limitation,
              updated_at=excluded.updated_at""",
            (
                DEMO_REPLAY["id"],
                DEMO_REPLAY["workspace_id"],
                stage,
                json.dumps(DEMO_REPLAY["baseline_document_ids"]),
                json.dumps(DEMO_REPLAY["added_document_ids"]),
                DEMO_REPLAY["original_runtime_ms"],
                DEMO_REPLAY["original_cost_usd"],
                elapsed_ms,
                cost_usd,
                0,
                limitation,
                utc_now(),
            ),
        )


def _seed_recorded_reasoning_outputs(workspace_id: str) -> None:
    """Load recorded semantic responses into the normal reasoning cache."""

    with db() as conn:
        for relationship in DEMO_RELATIONSHIPS:
            if relationship["workspace_id"] != workspace_id:
                continue
            rows = [
                conn.execute(
                    "SELECT * FROM claims WHERE id=? AND workspace_id=?",
                    (claim_id, workspace_id),
                ).fetchone()
                for claim_id in (relationship["claim_a"], relationship["claim_b"])
            ]
            if any(row is None for row in rows):
                continue
            left, right = sorted((dict(rows[0]), dict(rows[1])), key=lambda item: item["id"])
            response = {
                "relationship_type": relationship["relationship_type"],
                "reason": relationship["reason"],
                "dimensions": relationship["dimensions"],
                "confidence": relationship["confidence"],
                "evidence_claim_ids": [left["id"], right["id"]],
            }
            # A persistent demo volume may contain a recording written with a
            # previous model name. Remove both stable-ID and old fingerprint
            # rows before refreshing the provider-neutral replay entry.
            digest = relationship_cache_fingerprint(left, right)
            conn.execute(
                "DELETE FROM model_cache WHERE id=? OR (role=? AND model=? AND input_hash=?)",
                (f"demo-reasoning-{relationship['id']}", "reasoning", settings.reasoning_model, digest),
            )
            conn.execute(
                """INSERT INTO model_cache
                (id,role,model,input_hash,response_json,estimated_cost,created_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(role,model,input_hash) DO UPDATE SET
                  response_json=excluded.response_json,
                  estimated_cost=excluded.estimated_cost""",
                (
                    f"demo-reasoning-{relationship['id']}",
                    "reasoning",
                    settings.reasoning_model,
                        digest,
                    json.dumps(response, ensure_ascii=False),
                    0.0,
                    utc_now(),
                ),
            )
