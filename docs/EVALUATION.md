# Evaluation and evidence status

## Full-corpus offline baseline

`evals/reports/starter-corpus-e2e.json` records a run at `6f06ee5` over the
locally supplied six-PDF archive: 511 pages, 1,646.668 seconds, 19,551 accepted
numeric hints, and 21 quarantined hints. Exact matches against the existing
demo case reference were **0/10 claims and 0/4 relationships**. This is a failed
case-recovery baseline, not a claim-quality result. The diagnostic reference
is not independently annotated gold, and provider roles were all unavailable.

After the generic evidence-grounding, resumable batch, and open-vocabulary
hint corrections, the same archive was rerun at `e16b47c` and is recorded in
`evals/reports/starter-corpus-e2e-generalized.json`: 511 pages in 998.379
seconds, 14,607 accepted claims, 20 quarantined claims, 7,843 active fact
families, and 55,751 relationships. The offline run still recovered **0/10
exact claim cases and 0/4 relationships**; four GDP cases matched value and
page only. That result is retained as an honest no-provider limitation rather
than being tuned with starter-specific rules. The parser preflight produced
14,627 open-vocabulary numeric hints, and visual review remained recorded for
six pages.

Reproduce with `python scripts/evaluate_starter_corpus.py --database data/new-corpus-eval.sqlite3`
after preparing the local archive. The runner refuses to overwrite an existing
database. PDFs, page text, and the evaluation database remain local under
`data/`; the report contains aggregate measurements and case metadata only.
Live provider quality, a production-generated demo snapshot, and independently
verified gold annotations remain outstanding.

Project SuperJoin keeps evaluation inputs and reports under `evals/`. Reports distinguish a measured result, an offline check, and a skipped check. A skipped live benchmark is never presented as a model-quality claim.

## Gold contract

`evals/gold/README.md` defines the JSONL contract for a source-backed case. Each case identifies the workspace, document/page anchors, expected subject and predicate, normalized value/context, and the expected relationship or Trust Gate behavior. Synthetic contradiction cases are marked synthetic and are not described as starter-dataset evidence.

The useful unit of measurement is a claim or relationship case, not an arbitrary model token. The planned metrics are:

- claim precision, recall, and F1 over accepted atomic claims;
- numeric exact/rounding-compatible/context accuracy;
- evidence grounding precision (the cited text or region supports the value and qualifiers);
- relationship conclusion accuracy, with abstention reported separately;
- Trust Gate false-allow count and false-block/context-needed count;
- entity and predicate mapping accuracy;
- candidate Recall@10 and Recall@20 for dense-only and hybrid retrieval;
- latency, provider calls, tokens, and estimated cost by stage.

Every metric report includes its denominator, split, prompt/model version, parser version, and whether the run used live provider calls. A missing denominator is a report defect.

## Current reproducible checks

- `python scripts/run_security_eval.py` produces `evals/reports/security-offline.json`. The named prompt-injection fixture currently has five cases, zero strict false-allows, and retains suspicious content for inspection.
- `python scripts/benchmark_parsers.py ...` produces `evals/reports/parser-smoke.json`. The available local smoke uses the two-page assignment PDF and records native character/word counts and timing for pdfplumber, PyMuPDF, and pypdfium2 rendering. It is explicitly a smoke comparison, not the six-document/511-page benchmark.
- `python scripts/benchmark_models.py --role extraction` and `--role embedding` produce reports with `status: skipped` when no provider endpoint/key is configured. They record the candidate models and comparison contract without inventing quality, cost, or compatibility results.
- The application test suite covers normalization, API contracts, security fixtures, Trust Gate policy, review staleness, retrieval lanes, and demo seed behavior. CI repeats lint, compile, pytest, and the Vite build.

## What remains external

The full starter-corpus parser comparison, live extraction comparison, live embedding comparison, and 1,000-page/50,000-claim synthetic performance run require either the source-verified starter archive or a configured provider. They are bounded, reproducible harnesses rather than hidden assumptions. The README explains how to supply the archive locally without redistributing PDFs whose rights have not been audited.
