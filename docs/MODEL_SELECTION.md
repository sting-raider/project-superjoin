# Model selection record

The provider comparison harness is `scripts/benchmark_models.py`. It uses the
same bounded inputs and the durable US$20 budget ledger as application calls,
records endpoint/model/latency/cost metadata, and validates structured claims
or the configured embedding dimension for the selected endpoint.

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

## NVIDIA NIM synthetic extraction comparison

The provider-neutral benchmark was rerun with the same production extraction
boundary over `evals/fixtures/provider_selection.jsonl`: three synthetic,
out-of-domain cases covering SaaS metrics, manufacturing capacity, and an
executive appointment. Expected claims are evaluation annotations only; they
are never sent to the provider. A claim counts as accepted for scoring only
when its JSON envelope, `evidence.text`, and positive `evidence.pdf_page` pass
the production grounding contract.

| Model | Contract pass rate | Expected claim recall | Grounded precision | Mean provider latency | Estimated cost |
|---|---:|---:|---:|---:|---:|
| `nvidia/nemotron-3-super-120b-a12b` | 1.0000 | 0.5000 | 1.0000 | 13,853.67 ms | US$0.001784 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 1.0000 | 0.0000 | n/a | 35,471.67 ms | US$0.002729 |

The current development extraction selection is `nvidia/nemotron-3-super-120b-a12b` because it is faster, cheaper, and the only candidate with accepted recall on this split. The split is intentionally small and does not establish the Section 13 release targets; missed manufacturing and executive matches remain visible in the report. The machine-readable result is `evals/reports/extraction-model-selection-nim.json`.

## NVIDIA NIM embedding compatibility and retrieval comparison

`scripts/benchmark_embeddings.py` embeds eight synthetic paraphrase pairs and
measures dense Candidate Recall@1/3/10/20 and mean reciprocal rank after
excluding each query itself. The selected development model
`nvidia/nemotron-3-embed-1b` returned eight valid vectors at its native 2048
dimensions, with Recall@1 0.375, Recall@3 0.75, Recall@10 1.0, Recall@20 1.0,
and MRR 0.5771. The configured 768-dimensional hint is therefore disabled for
this endpoint (`EMBEDDING_INCLUDE_DIMENSIONS=false`) and the embedding space
records 2048 dimensions. A comparison alias returned HTTP 410 end-of-life for
all eight requests, so it is rejected on endpoint compatibility before any
quality comparison. The no-key demo keeps lexical retrieval available when no
embedding role is configured.

The full result is `evals/reports/embedding-model-selection-nim.json`; it
contains only aggregate telemetry, dimensions, errors, and retrieval metrics,
not source text or credentials. These synthetic metrics guide the current
development configuration and are not a claim of full-corpus quality.
