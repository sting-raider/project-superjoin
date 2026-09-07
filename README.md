# Project SuperJoin

Project SuperJoin is an evidence-first temporal Fact Knowledge Layer for
document-driven financial analysis. It keeps immutable source claims and exact
PDF evidence separate from normalized interpretations, relationships, and
canonical facts. The interface is designed for an analyst who needs to see why
a value is present before allowing downstream software to use it.

## Setup and Run Instructions

The no-key recorded demo runs with one container and one persistent volume:

```bash
git clone https://github.com/sting-raider/project-superjoin.git
cd project-superjoin
docker compose up --build
```

Open <http://localhost:8080>. No `.env` file, database server, GPU, model
download, or runtime API key is required for the bundled demo snapshot. The
application exposes `/api/v1/health`, `/api/v1/facts`, `/api/v1/search`, and
the POST `/api/v1/resolve` Trust Gate contract.

To process a never-seen PDF, provide an OpenAI-compatible endpoint in a local
`.env` (see `.env.example`) and restart Compose. Extraction, reasoning, vision,
and embedding roles are configured independently. Secrets are read from the
environment and are never returned by the Settings API.

The starter PDFs are third-party publications and are not committed while
redistribution permission is unresolved. Use
`python scripts/prepare_dataset.py --input <local-archive-or-directory>` to
prepare a local corpus and validate hashes/page counts. See
`docs/DATASET_REDISTRIBUTION.md` before publishing any source-derived asset.

## Video Demo

Video: pending final recording. The intended 2:55 walkthrough covers the four
assignment cases, the evidence inspector, Knowledge Diff, Trust Gate, and the
no-key setup. Replay timing and any recorded provider output will be labeled
as replay rather than presented as live model work.

## Approach

The ingestion pipeline parses each page, records parser/version and quality
flags, creates stable evidence anchors, extracts source claims, and writes
versioned interpretations. Deterministic normalization handles units, Indian
number scales, percentages, ranges, bounds, fiscal periods, and data-vintage
qualifiers. A bounded exact-context relationship lane identifies corroboration,
contradiction, reconciliation, and temporal supersedence. SQLite FTS5 provides
lexical retrieval; optional provider embeddings are stored with model and
dimension metadata and fused with lexical candidates through reciprocal rank
fusion.

The Trust Gate is conservative by construction. Contested, context-ambiguous,
quarantined, or stale-reviewed facts do not silently become executable values.
An explicit human-preference policy can be used only with an append-only,
revision-bound review record. Document text is untrusted content: prompt-like
instructions are retained for inspection and cannot change provider settings,
verification state, or budget policy.

The four recorded assignment cases are available from the Required cases view:

1. Delhivery FY24 service-revenue corroboration after crore/million scaling.
2. RBI versus IMF FY26 forecast conflict with preserved assumptions.
3. FY25 GDP first- versus second-advance-estimate reconciliation.
4. IMF image-dominant cover as an observed native-extraction failure.

The architecture, parser decision record, dataset audit, security boundary, and
evaluation schema live under `docs/`, `datasets/`, and `evals/`. `PLAN.md` is
the governing implementation and acceptance plan.

## Limitations and Next Steps

The repository currently ships a compact recorded demo rather than third-party
source PDFs. A full six-document, 511-page source-verified parser benchmark,
live extraction/embedding model comparison, and final video require the local
starter archive and optional provider credentials. The parser harness records
these as explicit inputs; it does not claim unrun comparisons passed.

Low-resolution scans, handwriting, complex charts, and ambiguous cross-page
tables can remain quarantined. Filtered vector search is an exact bounded scan
over the active embedding space, not a claim of sublinear ANN performance.
Source agreement is not proof of independent verification. The review workflow
serves a local single reviewer rather than an enterprise collaboration team.

## Additional Notes

Git history is intentionally incremental. Each coherent implementation slice
is tested, committed, and pushed to `origin/main` so the evolution remains
auditable. The runtime uses SQLite WAL mode, a persistent budget ledger with a
US$20 cap, request-fingerprint caching, resumable run records, and a single
container to keep setup simple.

Useful local checks:

```powershell
python -m pytest -q
python -m compileall -q app tests scripts
cd web; npm run build
```

The project name is **Project SuperJoin** throughout the product. The
repository name remains `project-superjoin`.
