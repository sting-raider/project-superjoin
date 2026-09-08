# Requirement traceability

The table maps the approved plan to the implemented review surface. File names are intentionally concrete so an evaluator can move from a requirement to the behavior that demonstrates it.

| Requirement | Implementation surface | Verification/demo path |
|---|---|---|
| Immutable claims and exact provenance | `source_claims`, `claim_evidence`, `page_artifacts`, `evidence_anchors`; `app/provenance.py` | Evidence inspector and fact detail endpoints |
| Numerical and semantic facts | `app/parser.py`, `app/normalization.py`, `app/pipeline.py` | Normalization and out-of-domain generalization tests |
| Starter-blind arbitrary-PDF extraction | Full-document bounded batches, open-vocabulary hints, semantic model lane, derived leakage scan in `tests/test_anti_leakage.py` | Out-of-domain SaaS/manufacturing/executive fixture; corrected six-PDF offline report |
| Deterministic normalization | `app/normalization.py` | `tests/test_normalization.py` |
| Temporal reasoning | `parse_period`, interval/modality fields, `app/knowledge.py` | FY25 vintage reconciliation and director supersedence cases |
| Corroboration/contradiction/reconciliation/supersedence | `relationships`, `compare_claim_pair` | Dynamic Relationships view and relationship tests |
| Entity and predicate evolution | `app/registry.py`, `entities`, `predicates`, alias/decision tables | Registry endpoints and unseen-domain fixtures |
| Incremental ingestion | content hash deduplication, durable `runs`, `run_events`, checkpoints | Upload/retry/cancel/history routes |
| Knowledge Diff | `knowledge_changes`, `/api/v1/changes` | Changes view and change publication tests |
| Human review and stale safety | `reviews`, review/revoke endpoints, fact-version checks | Review view; `tests/test_api.py` review flow |
| Trust Gate | `resolve_fact`, `/api/v1/resolve` | Strict block, human-preference policy, and inspector panel |
| Large/many PDF path | disk-backed upload, configurable 100 MB/2,000 page limits, page routing | Document upload contract; corpus preparation script |
| Native plus visual fallback | parser quality flags, rendered page fallback, `page_artifacts` dispositions | IMF image-only-cover case, parser docs, and the Documents evidence inspector |
| Hybrid retrieval | FTS5 lexical lane, optional stored embeddings, reciprocal rank fusion | `/api/v1/search` metadata and retrieval tests |
| Measured provider selection | `scripts/benchmark_models.py`, `scripts/benchmark_embeddings.py`, synthetic selection fixtures and reports | NIM extraction contract/grounding comparison; embedding dimensions and Recall@1/3/10/20 report |
| Provider isolation and budget | role settings, arbitrary OpenAI-compatible transport, response cache, reservations/settlement, model-call ledger | Non-Gemini fake endpoint test; Settings screen; budget endpoint |
| Prompt-injection safety | `app/security.py`, untrusted prompt boundaries, quarantine status | Five-case offline security report |
| Superjoin-inspired UI | `web/src/styles.css`, `web/src/main.jsx` | Forest/green palette, facts table, document/page evidence inspector, evidence/trust side panel |
| Evaluation and observability | `evals/`, `docs/EVALUATION.md`, run events, `/api/v1/runs/{run_id}/model-calls`, health/budget endpoints, Runs telemetry disclosure | CI and reproducible scripts; per-run role/status/token/latency/retry/cache/spend inspection |
| Empty-start live runtime | `Dockerfile`, `compose.yaml`, workspace/source APIs, README | Fresh volume has zero workspaces; create, upload, restart, and verify persistence |
| Workspace and source control | Workspace create/delete; source batch upload, archive/reactivate; canonical rebuild | Sources UI and `tests/test_workspace_source_management.py` |

## Explicitly bounded claims

The repository does not claim full-corpus live model quality from the bounded synthetic selection reports, does not claim the full 511-page parser benchmark without the source-verified archive, and does not redistribute starter PDFs before a rights audit. Those boundaries are part of the evidence-first behavior and are reflected in PLAN.md and the reports.
