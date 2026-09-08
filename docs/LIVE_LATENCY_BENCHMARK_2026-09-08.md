# Live PDF latency benchmark — 2026-09-08

The same 1-page, 27-page, and 100-page PDFs were run against the configured
NVIDIA NIM profile before and after the latency correction. The after runs use
the production pipeline, real HTTP calls, durable checkpoints, and the generic
OpenAI-compatible adapter. Credentials are excluded from all artifacts.

| Input | Before | After | Wall-time change | Logical-call change | Result |
|---|---:|---:|---:|---:|---|
| 1 page | 30.968 s / 4 calls | 3.053 s / 2 calls | 10.14x faster | 2.0x fewer | Complete, 2 grounded claims |
| 27 pages | >=2,004.748 s / 1,693 calls | 145.617 s / 21 calls | >=13.77x faster | 80.62x fewer | Complete after one checkpoint resume, 35 grounded claims |
| 100 pages | 4,061.039 s / 1,892 calls | 1,718.600 s / 276 calls | 2.36x faster | 6.86x fewer | Complete after throttling recovery, 140 grounded claims |

“After” time is the sum of processing time across every attempt needed to
reach a committed result. It does not discard failed attempts. Logical calls
count non-cache model-call records; HTTP attempts also include transport
retries within those calls.

The main changes were:

- full source text appears once per extraction request;
- deterministic hints are deduplicated, ranked, and capped at 16 small locator
  records instead of becoming model facts;
- three-page / 12,000-character batches request at most four claims under a
  2,400-token output ceiling;
- output-limit truncation is detected from `finish_reason` and cannot publish;
- extraction uses one globally bounded worker pool with adaptive retry and
  durable per-batch checkpoints;
- unresolved entity and predicate embeddings are batched and compared locally;
- semantic schema resolution is limited to four genuinely ambiguous candidates
  per ingestion;
- relationship candidates and semantic reviews are bounded around new claims;
- grounded provisional claims are visible during processing but remain
  ineligible for Trust Gate until atomic publication;
- stage counters, model calls, HTTP attempts, heartbeats, elapsed time, and ETA
  are recorded during the run.

The 100-page result did not achieve the requested order-of-magnitude wall-time
or actual-call reduction. The provider returned sustained HTTP 429 responses:
201 failed logical extraction calls expanded the chain to 511 HTTP attempts.
The pipeline retained completed work and ultimately published all 68 extraction
checkpoints. With a provider that accepts each bounded batch once, its intended
call graph is 68 extraction calls plus at most six registry calls, but that is
a projection and is not reported as measured performance.

Quality checks were deliberately general rather than starter-case tuned. The
1-page SaaS document retained its entity and fiscal-period context. The
27-page document produced 35 accepted claims across 13 pages, including page
25. The 100-page document produced 140 accepted claims across 58 pages and
grounded evidence through page 100, including previously unseen predicates in
the final 20 pages. No starter entity, predicate, value, page number, or case ID
was introduced into production logic.

Raw measurements are in
[`live_latency_after_2026-09-08.json`](../evals/reports/live_latency_after_2026-09-08.json)
and the frozen baseline is in
[`live_latency_baseline_2026-09-08.json`](../evals/reports/live_latency_baseline_2026-09-08.json).
