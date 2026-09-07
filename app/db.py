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
    for key in ("evidence_json", "details_json", "dimensions_json"):
        if key in item:
            try:
                item[key[:-5]] = json.loads(item.pop(key))
            except (json.JSONDecodeError, TypeError):
                item[key[:-5]] = []
    return item


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]

