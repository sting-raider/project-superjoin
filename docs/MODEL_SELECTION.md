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

The reference candidates remain optional benchmark inputs until a local
endpoint is available. They do not constrain runtime provider or model choice:

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
