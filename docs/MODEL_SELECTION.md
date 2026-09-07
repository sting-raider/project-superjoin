# Model selection record

The provider comparison harness is `scripts/benchmark_models.py`. It uses the
same bounded inputs and the durable US$20 budget ledger as application calls,
records endpoint/model/latency/cost metadata, and validates structured claims
or the requested 768-dimensional vector length.

The reference candidates remain configuration values until a local endpoint is
available:

- Extraction: `gemini-3.5-flash-lite` versus `gemini-3.8-flash`.
- Embeddings: `gemini-embedding-001` versus the currently supported
  `gemini-embedding-2` option at 768 dimensions.

With no credentials the harness writes an explicit `skipped` report and makes
no network request. It is incorrect to call those candidates benchmarked
until the same development fixture has live results for quality, grounding,
latency, dimensionality, and cost. The runtime still works in recorded demo
mode through deterministic extraction and lexical retrieval.
