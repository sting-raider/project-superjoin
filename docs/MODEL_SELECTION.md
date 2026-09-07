# Model selection record

The provider comparison harness is `scripts/benchmark_models.py`. It uses the
same bounded inputs and the durable US$20 budget ledger as application calls,
records endpoint/model/latency/cost metadata, and validates structured claims
or the requested 768-dimensional vector length.

The harness checks the role-specific endpoint (`EXTRACTION_*` or
`EMBEDDING_*`) and never assumes that a shared `AI_BASE_URL` is present. A
shared URL/key remains a convenience fallback for local setup, while explicit
role values can point at different compatible services. The runtime records
nonsecret timeout, output-token, concurrency, structured-output, and embedding
task settings in `/api/v1/settings` so a run can be reproduced without
exposing credentials.

The research reference candidates below remain optional benchmark inputs until
a local endpoint is available. They are documentation-only historical labels;
they do not constrain runtime provider or model choice, and they are never
defaults or an allowlist:

- Extraction: `gemini-3.5-flash-lite` versus `gemini-3.8-flash`.
- Embeddings: `gemini-embedding-001` versus the currently supported
  `gemini-embedding-2` option at 768 dimensions.

With no credentials the harness writes an explicit `skipped` report and makes
no network request. It is incorrect to call those candidates benchmarked
until the same development fixture has live results for quality, grounding,
latency, dimensionality, and cost. The runtime still works in recorded demo
mode through deterministic extraction and lexical retrieval. Any model string
accepted by the configured endpoint is valid; compatibility failures are
recorded as provider errors rather than converted into a hidden fallback.
Transient 429/5xx and connection/timeout failures use bounded, configurable
exponential backoff and honor a provider `Retry-After` value; retries remain
inside the same explicit budgeted request and never switch providers
implicitly.

## NVIDIA NIM live compatibility run

On 2026-09-08, the six locally supplied starter PDFs were processed through
the generic extraction lane using NVIDIA NIM model
`nvidia/nemotron-3-super-120b-a12b` at
`https://integrate.api.nvidia.com/v1`. The run covered 511 pages and 103
bounded extraction batches, published 9,362 accepted claims and 14 quarantined
claims, and recorded 193 extraction calls (174 complete, 19 failed) with
US$2.056295 estimated spend under the project ledger. Four of the ten
diagnostic values matched value and page; exact diagnostic claim recall was
0/10, so this is an honest compatibility/coverage result rather than a claim
that the model was selected as the reference extractor.

The reasoning, vision, and embedding roles were intentionally unconfigured.
Relationships therefore used deterministic comparison only, image-dominant
pages remained in visual review, and dense retrieval was not evaluated. The
full machine-readable report is
`evals/reports/starter-corpus-e2e-nim.json`; it contains nonsecret model and
telemetry metadata but no API key or copied page text.
