from __future__ import annotations

import re
import uuid
from typing import Any

from .db import db, utc_now


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _name_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


def _predicate_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "unknown_predicate"


def observe_claim_schema(workspace_id: str, subject: str, predicate: str, value_kind: str = "text", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Register a claim's vocabulary without forcing semantic merges."""

    entity = resolve_entity(workspace_id, subject)
    pred = resolve_predicate(workspace_id, predicate, value_kind=value_kind)
    with db() as conn:
        if entity["status"] == "new":
            entity_id = _id("entity")
            conn.execute("INSERT INTO entities(id,workspace_id,canonical_name,entity_type,status,created_at) VALUES(?,?,?,?,?,?)", (entity_id, workspace_id, subject.strip(), "unknown", "active", utc_now()))
            entity = {**entity, "id": entity_id, "status": "resolved"}
        if pred["status"] == "new":
            predicate_id = _id("predicate")
            conn.execute("INSERT INTO predicates(id,workspace_id,key,definition,value_kind,status,created_at) VALUES(?,?,?,?,?,?,?)", (predicate_id, workspace_id, pred["key"], "Observed predicate; definition requires evidence or review.", value_kind, "active", utc_now()))
            pred = {**pred, "id": predicate_id, "status": "resolved"}
        if evidence:
            conn.execute("INSERT INTO entity_aliases(id,entity_id,alias,scope,evidence_json,status,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(entity_id,alias,scope) DO NOTHING", (_id("alias"), entity["id"], subject.strip(), None, _json(evidence), "confirmed", utc_now()))
            conn.execute("INSERT INTO predicate_aliases(id,predicate_id,alias,relation,evidence_json,status,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(predicate_id,alias) DO NOTHING", (_id("palias"), pred["id"], predicate.strip(), "equivalent", _json(evidence), "confirmed", utc_now()))
    return {"entity": entity, "predicate": pred}


def register_workspace_claims(workspace_id: str) -> int:
    with db() as conn:
        rows = conn.execute("SELECT subject,predicate,value_type,evidence_json FROM claims WHERE workspace_id=? AND extraction_status='accepted'", (workspace_id,)).fetchall()
    for row in rows:
        import json

        observe_claim_schema(workspace_id, row["subject"], row["predicate"], row["value_type"], json.loads(row["evidence_json"]))
    return len(rows)


def resolve_entity(workspace_id: str, name: str) -> dict[str, Any]:
    key = _name_key(name)
    with db() as conn:
        rows = conn.execute("SELECT * FROM entities WHERE workspace_id=? ORDER BY created_at", (workspace_id,)).fetchall()
        for row in rows:
            if _name_key(row["canonical_name"]) == key:
                return {"id": row["id"], "canonical_name": row["canonical_name"], "status": "resolved", "match": "exact"}
        aliases = conn.execute("SELECT ea.*,e.canonical_name FROM entity_aliases ea JOIN entities e ON e.id=ea.entity_id WHERE e.workspace_id=?", (workspace_id,)).fetchall()
        for row in aliases:
            if _name_key(row["alias"]) == key and row["status"] == "confirmed":
                return {"id": row["entity_id"], "canonical_name": row["canonical_name"], "status": "resolved", "match": "alias"}
    return {"id": None, "canonical_name": name, "status": "new", "match": None}


def resolve_predicate(workspace_id: str, predicate: str, value_kind: str = "text") -> dict[str, Any]:
    key = _predicate_key(predicate)
    with db() as conn:
        row = conn.execute("SELECT * FROM predicates WHERE workspace_id=? AND key=?", (workspace_id, key)).fetchone()
        if row:
            return {"id": row["id"], "key": row["key"], "status": "resolved", "match": "exact", "value_kind": row["value_kind"]}
        alias = conn.execute("SELECT pa.*,p.key FROM predicate_aliases pa JOIN predicates p ON p.id=pa.predicate_id WHERE p.workspace_id=? AND lower(pa.alias)=lower(?) AND pa.relation='equivalent' AND pa.status='confirmed'", (workspace_id, predicate)).fetchone()
        if alias:
            return {"id": alias["predicate_id"], "key": alias["key"], "status": "resolved", "match": "alias", "value_kind": value_kind}
    return {"id": None, "key": key, "status": "new", "match": None, "value_kind": value_kind}


def _json(value: Any) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False)
