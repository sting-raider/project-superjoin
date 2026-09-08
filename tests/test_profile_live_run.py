from __future__ import annotations

import sqlite3

from scripts.profile_live_run import profile_run


def test_profile_live_run_aggregates_network_calls_and_elapsed_time() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE runs(id TEXT,workspace_id TEXT,document_id TEXT,mode TEXT,status TEXT,
          progress INTEGER,message TEXT,created_at TEXT,updated_at TEXT);
        CREATE TABLE model_calls(run_id TEXT,role TEXT,status TEXT,input_tokens INTEGER,
          output_tokens INTEGER,latency_ms INTEGER,attempts INTEGER,cache_hit INTEGER,
          estimated_cost REAL);
        CREATE TABLE extraction_batches(run_id TEXT,status TEXT,claim_count INTEGER,
          page_start INTEGER,page_end INTEGER);
        CREATE TABLE documents(id TEXT,page_count INTEGER,status TEXT);
        CREATE TABLE claims(document_id TEXT);
        INSERT INTO runs VALUES('r','w','d','live','complete',100,'Complete',
          '2026-01-01T00:00:00+00:00','2026-01-01T00:00:02.500000+00:00');
        INSERT INTO documents VALUES('d',1,'complete');
        INSERT INTO claims VALUES('d');
        INSERT INTO model_calls VALUES('r','extraction','complete',100,20,500,1,0,0.1);
        INSERT INTO model_calls VALUES('r','extraction','cache_hit',0,0,0,1,1,0);
        INSERT INTO extraction_batches VALUES('r','complete',1,1,1);
        """
    )

    report = profile_run(conn, "r")

    assert report["observed_elapsed_seconds"] == 2.5
    assert report["network_calls"] == 1
    assert report["persisted_claims"] == 1
    assert report["extraction"]["completed"] == 1
