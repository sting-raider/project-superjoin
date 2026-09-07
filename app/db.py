from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  active_revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL,
  publisher TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  sha256 TEXT NOT NULL,
  page_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',
  parser TEXT NOT NULL DEFAULT 'pending',
  quality_score REAL,
  published_at TEXT,
  stored_path TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(workspace_id, sha256)
);
CREATE INDEX IF NOT EXISTS idx_documents_workspace_status ON documents(workspace_id, status);
CREATE TABLE IF NOT EXISTS page_artifacts (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  page_number INTEGER NOT NULL,
  printed_label TEXT,
  width REAL NOT NULL,
  height REAL NOT NULL,
  rotation INTEGER NOT NULL DEFAULT 0,
  native_text TEXT NOT NULL DEFAULT '',
  parser TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  quality_score REAL NOT NULL,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  disposition TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  UNIQUE(document_id, page_number)
);
CREATE INDEX IF NOT EXISTS idx_page_artifacts_document ON page_artifacts(document_id, page_number);
CREATE TABLE IF NOT EXISTS evidence_anchors (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  page_artifact_id TEXT REFERENCES page_artifacts(id),
  pdf_page INTEGER NOT NULL,
  printed_page TEXT,
  kind TEXT NOT NULL DEFAULT 'text',
  text TEXT NOT NULL,
  start_offset INTEGER,
  end_offset INTEGER,
  bbox_json TEXT,
  precision TEXT NOT NULL DEFAULT 'page-only',
  parser TEXT,
  anchor_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(document_id, anchor_hash)
);
CREATE INDEX IF NOT EXISTS idx_evidence_anchors_document_page ON evidence_anchors(document_id, pdf_page);
CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  document_id TEXT NOT NULL REFERENCES documents(id),
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  raw_value TEXT NOT NULL,
  normalized_value TEXT,
  value_type TEXT NOT NULL DEFAULT 'text',
  unit TEXT,
  period TEXT,
  modality TEXT,
  scope TEXT,
  evidence_json TEXT NOT NULL,
  grounding_status TEXT NOT NULL DEFAULT 'grounded',
  extraction_status TEXT NOT NULL DEFAULT 'accepted',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_workspace_context ON claims(workspace_id, subject, predicate, period, modality);
CREATE TABLE IF NOT EXISTS claim_evidence (
  claim_id TEXT NOT NULL REFERENCES claims(id),
  anchor_id TEXT NOT NULL REFERENCES evidence_anchors(id),
  purpose TEXT NOT NULL DEFAULT 'assertion',
  created_at TEXT NOT NULL,
  PRIMARY KEY(claim_id, anchor_id, purpose)
);
CREATE TABLE IF NOT EXISTS claim_interpretations (
  id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims(id),
  version INTEGER NOT NULL,
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  normalized_value TEXT,
  value_type TEXT NOT NULL,
  unit TEXT,
  period TEXT,
  modality TEXT,
  scope TEXT,
  normalization_trace_json TEXT NOT NULL DEFAULT '[]',
  entity_status TEXT NOT NULL DEFAULT 'unresolved',
  predicate_status TEXT NOT NULL DEFAULT 'unresolved',
  eligibility TEXT NOT NULL DEFAULT 'eligible',
  created_at TEXT NOT NULL,
  UNIQUE(claim_id, version)
);
CREATE INDEX IF NOT EXISTS idx_claim_interpretations_claim ON claim_interpretations(claim_id, version DESC);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  canonical_name TEXT NOT NULL,
  entity_type TEXT NOT NULL DEFAULT 'unknown',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  UNIQUE(workspace_id, canonical_name)
);
CREATE TABLE IF NOT EXISTS entity_aliases (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL REFERENCES entities(id),
  alias TEXT NOT NULL,
  scope TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'proposed',
  created_at TEXT NOT NULL,
  UNIQUE(entity_id, alias, scope)
);
CREATE TABLE IF NOT EXISTS predicates (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  key TEXT NOT NULL,
  definition TEXT NOT NULL DEFAULT '',
  value_kind TEXT NOT NULL DEFAULT 'text',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  UNIQUE(workspace_id, key)
);
CREATE TABLE IF NOT EXISTS predicate_aliases (
  id TEXT PRIMARY KEY,
  predicate_id TEXT NOT NULL REFERENCES predicates(id),
  alias TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'equivalent',
  evidence_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'proposed',
  created_at TEXT NOT NULL,
  UNIQUE(predicate_id, alias)
);
CREATE TABLE IF NOT EXISTS registry_decisions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  kind TEXT NOT NULL,
  source_key TEXT NOT NULL,
  target_id TEXT,
  action TEXT NOT NULL,
  rationale TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  normalized_value TEXT,
  display_value TEXT NOT NULL,
  value_type TEXT NOT NULL DEFAULT 'text',
  unit TEXT,
  period TEXT,
  modality TEXT,
  scope TEXT,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_workspace_context ON facts(workspace_id, subject, predicate, period, status);
CREATE TABLE IF NOT EXISTS fact_versions (
  id TEXT PRIMARY KEY,
  fact_id TEXT NOT NULL REFERENCES facts(id),
  revision INTEGER NOT NULL,
  normalized_value TEXT,
  display_value TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  knowledge_revision INTEGER NOT NULL,
  effective_from TEXT,
  effective_to TEXT,
  evidence_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  UNIQUE(fact_id, revision)
);
CREATE TABLE IF NOT EXISTS fact_memberships (
  fact_version_id TEXT NOT NULL REFERENCES fact_versions(id),
  claim_id TEXT NOT NULL REFERENCES claims(id),
  role TEXT NOT NULL DEFAULT 'supporting',
  created_at TEXT NOT NULL,
  PRIMARY KEY(fact_version_id, claim_id, role)
);
CREATE TABLE IF NOT EXISTS relationships (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  claim_a TEXT NOT NULL REFERENCES claims(id),
  claim_b TEXT NOT NULL REFERENCES claims(id),
  relationship_type TEXT NOT NULL,
  reason TEXT NOT NULL,
  dimensions_json TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(claim_a, claim_b, relationship_type)
);
CREATE TABLE IF NOT EXISTS changes (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  run_id TEXT,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id),
  event_type TEXT NOT NULL,
  progress INTEGER NOT NULL,
  message TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, id);
CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  fact_id TEXT NOT NULL REFERENCES facts(id),
  action TEXT NOT NULL,
  rationale TEXT NOT NULL,
  based_on_revision INTEGER NOT NULL,
  stale INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_calls (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES runs(id),
  role TEXT NOT NULL,
  model TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  estimated_cost REAL NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budget_ledger (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  limit_usd REAL NOT NULL,
  reserved_usd REAL NOT NULL DEFAULT 0,
  spent_usd REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embedding_spaces (
  id TEXT PRIMARY KEY,
  workspace_id TEXT REFERENCES workspaces(id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  template_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'building',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES embedding_spaces(id),
  claim_id TEXT REFERENCES claims(id),
  content_hash TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(space_id, claim_id)
);
CREATE TABLE IF NOT EXISTS model_profiles (
  id TEXT PRIMARY KEY,
  role TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER,
  capability_json TEXT NOT NULL DEFAULT '{}',
  benchmark_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_runs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  config_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'planned',
  created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
  claim_id UNINDEXED,
  workspace_id UNINDEXED,
  subject,
  predicate,
  raw_value,
  period,
  modality,
  scope
);
"""


def connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO budget_ledger(id, limit_usd, updated_at) VALUES(1, ?, ?)",
            (settings.ai_budget_usd, utc_now()),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key in (
        "evidence_json",
        "details_json",
        "dimensions_json",
        "quality_flags_json",
        "normalization_trace_json",
        "capability_json",
        "benchmark_json",
        "config_json",
        "metrics_json",
        "vector_json",
    ):
        if key in item:
            try:
                item[key[:-5]] = json.loads(item.pop(key))
            except (json.JSONDecodeError, TypeError):
                item[key[:-5]] = []
    return item


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]
