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
application exposes `/api/v1/health`, `/api/v1/facts`, `/api/v1/search`, the
POST `/api/v1/resolve` Trust Gate contract, archive/reactivate document
mutations, and read/export routes for documents, claims, fact history, JSON,
CSV, and XLSX.

The sidebar's **Start recorded replay** action opens a real two-document demo
checkpoint. **Continue recorded replay** adds the recorded third document and
runs registry resolution, relationship assessment, and canonical publication
again. The UI labels this as “Recorded model outputs; no API calls.” Reset
clears only the demo workspaces, keeps any live workspace intact, and restores
the full recorded snapshot. Original provider timing/cost is shown as
unavailable when it was not part of the permitted recording; replay timing is
measured locally.
The Runs view still shows the recorded lifecycle events and an explicit
zero-call telemetry disclosure, so offline replay does not look like a live
provider run.

To process a never-seen PDF, provide an OpenAI-compatible endpoint in a local
`.env` (see `.env.example`) and restart Compose. Extraction, reasoning, vision,
and embedding roles are configured independently, including endpoint, model,
timeout, output budget, and embedding task settings. Secrets are read from the
environment and are never returned by the Settings API; the Settings screen
shows only nonsecret capability metadata.

The adapter is configuration-only and has no provider or model allowlist. The
same variables work with OpenAI, Azure OpenAI, OpenRouter, Together, Groq,
Ollama, vLLM, or another endpoint that exposes compatible chat and embedding
routes. Set `*_BASE_URL`, `*_API_KEY` (optional for local services), and the
role model. Role paths and auth headers are configurable for deployments such
as Azure (`*_AUTH_HEADER=api-key`, empty `*_AUTH_SCHEME`, and a deployment
`*_CHAT_PATH`). Set `*_STRUCTURED_OUTPUT_MODE=none` for endpoints that do not
implement response-format hints, and set `EMBEDDING_INCLUDE_DIMENSIONS=false`
when an embedding service chooses dimensions server-side. Provider errors,
missing models, unsupported response formats, and vector dimension mismatches
remain visible in run telemetry and search responses.

For example, NVIDIA NIM can be used for extraction without changing code:

```dotenv
EXTRACTION_BASE_URL=https://integrate.api.nvidia.com/v1
EXTRACTION_API_KEY=${NVIDIA_API_KEY}
EXTRACTION_MODEL=nvidia/nemotron-3-super-120b-a12b
EXTRACTION_STRUCTURED_OUTPUT_MODE=json_object
# Optional endpoint fields remain configuration, not provider logic.
EXTRACTION_EXTRA_BODY_JSON={"chat_template_kwargs":{"enable_thinking":false}}
```

Keep the key in the local environment; the placeholder above is documentation
only and is never committed.
Transient HTTP 429/5xx and connection/timeout failures use the configured
`AI_RETRY_ATTEMPTS` and `AI_RETRY_BACKOFF_SECONDS` policy (including
`Retry-After` when supplied); the final provider error is retained when retries
are exhausted. The budget ledger
reserves the configured retry envelope and records the attempts actually used,
so retries cannot silently exceed the cumulative cap. Cache fingerprints also
include the nonsecret endpoint/path/model identity, so changing providers does
not replay another endpoint's response.

The current paid development route uses DeepSeek V4 Flash for extraction and
reasoning through the same generic settings:

```dotenv
EXTRACTION_BASE_URL=https://api.deepseek.com
EXTRACTION_MODEL=deepseek-v4-flash
EXTRACTION_API_KEY=${DEEPSEEK_API_KEY}
EXTRACTION_EXTRA_BODY_JSON={"thinking":{"type":"disabled"}}
REASONING_BASE_URL=https://api.deepseek.com
REASONING_MODEL=deepseek-v4-flash
REASONING_API_KEY=${DEEPSEEK_API_KEY}
REASONING_EXTRA_BODY_JSON={"thinking":{"type":"disabled"}}
```

The 1-page, 27-page, and 100-page live runs completed in 2.321, 50.529, and
326.626 aggregate processing seconds respectively. The 100-page run preserved
60 successful checkpoints across eight interrupted responses, then resumed the
remaining batches and published 118 grounded claims with evidence through page
100. These figures include a provider change and are documented separately from
the architecture-only latency work in
[`live_latency_deepseek_2026-09-08.json`](evals/reports/live_latency_deepseek_2026-09-08.json).

The starter PDFs are third-party publications and are not committed while
redistribution permission is unresolved. Use
`python scripts/prepare_dataset.py --input <local-archive-or-directory>` to
prepare a local corpus and validate hashes/page counts. See
`docs/DATASET_REDISTRIBUTION.md` before publishing any source-derived asset.

## Video Demo

The optional Playwright recorder now produces a captioned local walkthrough of
the real no-key UI; a 29.6-second MP4 passed the duration and stream preflight.
The intended final walkthrough covers the four assignment cases, the evidence
inspector, Knowledge Diff, Trust Gate, and the no-key setup. Replay timing and
any recorded provider output are labeled as replay rather than presented as
live model work. The recorder's `--redact-source` mode masks source names,
values, evidence text, and provider outputs before the first page paint for a
rights-safe public walkthrough. Reproducible capture steps are in
[`docs/VIDEO_DEMO_SCRIPT.md`](docs/VIDEO_DEMO_SCRIPT.md); the public release
link is the [public redacted walkthrough](https://github.com/sting-raider/project-superjoin/releases/download/demo-video-v1/project-superjoin-public.mp4).

## Approach

The ingestion pipeline parses each page, records parser/version and quality
flags, creates stable evidence anchors, extracts source claims, and writes
versioned interpretations. Deterministic normalization handles units, Indian
number scales, percentages, ranges, bounds, fiscal periods, and data-vintage
qualifiers. A bounded exact-context relationship lane identifies corroboration,
contradiction, reconciliation, and temporal supersedence. SQLite FTS5 provides
lexical retrieval; optional provider embeddings are stored with model and
dimension metadata. When an active space has vectors, a normal search query
gets one budgeted, cached embedding and is fused with lexical candidates
through reciprocal rank fusion; absent or failed embedding capability falls
back to clearly labeled lexical results.

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
source PDFs. The parser comparison and bounded NVIDIA NIM extraction/embedding
selection reports are included as measured development evidence; they use
small synthetic or locally supplied inputs and do not claim full-corpus quality.
A broader provider comparison and source-cleared video require additional
external inputs. The published redacted walkthrough exercises the production
registry, relationship, and canonical fact publication stages without
pretending to be a live model run.

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

The Docker runtime installs the pinned Python set in `requirements.lock`; the
web build uses the committed `web/package-lock.json`.
