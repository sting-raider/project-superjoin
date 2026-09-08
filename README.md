# Project SuperJoin

Project SuperJoin is an evidence-first temporal Fact Knowledge Layer for
document-driven financial analysis. It keeps immutable source claims and exact
PDF evidence separate from normalized interpretations, relationships, and
canonical facts. The product is built for an analyst who needs to inspect why
a value exists before downstream software may use it.

## Setup and Run Instructions

```bash
git clone https://github.com/sting-raider/project-superjoin.git
cd project-superjoin
cp .env.example .env
# Add credentials for the OpenAI-compatible services you want to use.
docker compose up --build
```

Open <http://localhost:8080>. A fresh database contains zero workspaces and no
sample facts. Create a workspace in the masthead, add one or several PDFs from
the Sources view, and follow processing in Runs. Workspaces can be deleted.
Sources can be removed from active knowledge and restored in one click; removal
rebuilds current facts while preserving the source record and audit history.

Extraction, reasoning, vision, and embeddings have independent settings for
base URL, API key, model, request path, timeout, concurrency, token limit, and
embedding dimensions. Configure them in `.env` or at runtime in **Configure**.
Runtime keys stay in process memory, are never returned by the API, and
disappear on restart. The US$20 cumulative budget ledger remains persistent.
The **Use this provider for…** action can reuse one endpoint and its in-memory
authentication across explicitly selected compatible roles while preserving
each target role's model, request path, limits, and capability options.

The adapter accepts arbitrary OpenAI-compatible endpoints and model names. It
has no provider or model allowlist. OpenAI, Azure OpenAI, OpenRouter, Together,
Groq, NVIDIA NIM, DeepSeek, Ollama, vLLM, and compatible gateways can be used
through configuration. Azure-style headers and deployment paths, services
without response-format support, and provider-selected embedding dimensions
are configurable. Unsupported capabilities, HTTP 429/5xx responses, retry
attempts, timeouts, truncation, cache use, costs, and dimension mismatches are
visible in run telemetry.

Example chat-role configuration:

```dotenv
EXTRACTION_BASE_URL=https://provider.example/v1
EXTRACTION_API_KEY=replace-locally
EXTRACTION_MODEL=provider/arbitrary-model
EXTRACTION_CHAT_PATH=/chat/completions
EXTRACTION_TIMEOUT_SECONDS=90
EXTRACTION_MAX_OUTPUT_TOKENS=1800
EXTRACTION_CONCURRENCY=4

REASONING_BASE_URL=https://provider.example/v1
REASONING_API_KEY=replace-locally
REASONING_MODEL=provider/arbitrary-model
```

Never commit `.env` or credentials. Provider credentials are required for live
semantic extraction of arbitrary PDFs. LiteParse, selective local OCR,
deterministic normalization, SQLite FTS5, and already-persisted workspaces run
locally. Embeddings and vision remain optional and degrade explicitly to
lexical retrieval or review-required evidence when unconfigured.

The starter PDFs are third-party publications and are not committed while
redistribution permission is unresolved. Prepare a locally supplied corpus
with:

```bash
python scripts/prepare_dataset.py --input <local-archive-or-directory>
```

See `docs/DATASET_REDISTRIBUTION.md` for the publication boundary.

## Video Demo

The project owner will add the final live-product walkthrough link here after
recording it. The repository contains no preloaded workspace, source, fact,
relationship, provider response, or video asset.

## Approach

LiteParse 2.14.4 is the primary local parser after a measured 169-page
comparison. It extracts native text, classified blocks, tables, word geometry,
and complexity signals. Selective OCR runs only for pages with an unusable text
layer; provider vision is reserved for pages local recovery cannot ground.
Every page records parser/version/config identity and quality flags.

Full-document semantic extraction uses bounded page, section, and table
batches. It sends source text once and uses compact deterministic hints as
optional grounding aids. Responses are validated for output-limit truncation,
cached by provider and request identity, and checkpointed for resume. Role-wide
concurrency is globally bounded and adapts to rate limits. Batched registry
embeddings are compared locally, with semantic resolution reserved for truly
ambiguous candidates. New unrelated entities and predicates are created
without code changes or unnecessary model calls.

Immutable claims retain exact evidence anchors. Append-only interpretations add
normalization and registry mappings. Canonical fact families group compatible
claims and preserve alternatives, conflicts, memberships, fact versions, and
review history. Relationship processing compares only relevant candidates for
new claims. Safe provisional results may be shown during processing, while the
Trust Gate permits only committed revisions.

SQLite WAL and FTS5 keep deployment to one container. Optional vectors are
stored with model and dimension metadata and fused with lexical candidates.
The Trust Gate returns `allow`, `block`, `needs_context`, or `needs_review` with
reason codes and evidence. Contested, ambiguous, quarantined, or stale-reviewed
facts never silently become executable values.

Starter-dataset entities, values, pages, IDs, predicates, and expected
relationships are isolated to evaluation metadata. Production modules are
checked for leakage and remain functional when starter artifacts are absent.

## Limitations and Next Steps

Low-resolution scans, handwriting, complex charts, and ambiguous cross-page
tables can remain quarantined. OpenAI-compatible services differ in protocol
details and output quality; the runtime reports these differences rather than
silently switching models. Exact filtered vector scans suit the evaluator-scale
SQLite deployment and are not claimed as a large distributed ANN index.

Relationships are currently stored and presented at immutable claim-pair
granularity. If several passages or editions discuss the same canonical metric,
the Relationship Desk can therefore show several evidence comparisons about
that metric. In the current three-document macroeconomic workspace, the ten
relationships cluster around real GDP growth because that is the fact family
with compatible entities, value types, periods, and contexts across the three
sources. The count describes claim-level comparisons; it should not be read as
ten distinct metrics. The engine deliberately avoids manufacturing links
between superficially similar claims whose periods, units, or meanings are not
comparable.

A useful next refinement is a relationship-family view that groups those raw
edges by canonical entity, predicate, normalized period, modality, and source
pair. The UI could then say, for example, “three reasoning cases from ten
claim-level comparisons,” while retaining every source sentence and page in a
drill-down. A coverage view could also list the metrics shared across sources,
explain why other candidates were not comparable, and distinguish relationship
diversity from evidence volume. Further evaluation should measure relationship
precision and recall across unrelated domains, near-alias predicates, reporting
vintages, and partial-period versus full-period disclosures before changing the
reasoning thresholds.

The measured LiteParse comparison and bounded live latency reports under
`evals/reports/` are development evidence, not a claim of universal corpus
quality. The project owner will record the final live-only walkthrough. Source
agreement does not prove independent truth, and entity/predicate resolution can
still require a reviewer.

## Additional Notes

Git history is intentionally incremental. Every coherent change is checked,
committed, and pushed to `origin/main`. Useful local checks are:

```powershell
python -m pytest -q
python -m ruff check app tests scripts
python -m compileall -q app tests scripts
cd web; npm ci; npm run build
```

`PLAN.md` remains the governing architecture and acceptance plan. The project
name is **Project SuperJoin** throughout; the repository remains
`project-superjoin`.
