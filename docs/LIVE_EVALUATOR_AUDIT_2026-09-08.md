# Live evaluator audit — 8 September 2026

## Verdict and scope

The live UI has a coherent visual design and real provider-backed ingestion, but
the observed experience does not yet justify claiming that it meets every
challenge requirement or performs better than expected. Correctness, the four
required demonstrations, and trustworthy status reporting matter more than
additional visual polish.

This is a browser-led evaluation of the running application at
`http://localhost:8080`, on code revision `a00a164`, using the Codex internal
browser. All uploads and workflow interactions described here used the UI.
The assignment PDF and README were read separately to establish requirements.
This is not a substitute for a full code, security, or quantitative extraction
audit. No provider configuration or application code was changed for this review.

The live workspace initially contained one synthetic SaaS PDF, two canonical
facts, and no relationships. Extraction/reasoning used the configured NVIDIA
Nemotron model; embeddings were configured at 2048 dimensions; vision was
unconfigured. Provider keys were not displayed or copied into this report.

### Test inputs and runs

| Input | Action | Evidence |
|---|---|---|
| Existing one-page synthetic SaaS update | Inspect facts, source evidence, entity search, Trust Gate | Source explicitly identifies an entity and fiscal period; derived facts lose both. |
| Actual 27-page earnings presentation | Upload through the header control | Accepted; run `run-65a735224021`; parsed 27 pages and reached grounding of 410 candidate claims. |
| Actual 100-page annual-report excerpt | Upload while the first run was active | Accepted; run `run-a25ccea1bc35`; parsed all 100 pages. |
| Existing synthetic PDF again | Repeat upload | Correctly reported that the PDF was already present; document count remained three. |

The new uploads remain test inputs in the live workspace. Final observed run
outcomes and timing are recorded below after the browser pass.

## Prioritized fixes

P1 means resolve before presenting this as a complete evaluator-ready submission.
P2 means a material usability or transparency improvement. P3 means polish.
No P1 below is a claim of a security incident.

| ID | Priority | Verified observation and reproduction | Required fix and acceptance test |
|---|---|---|---|
| E01 | P1 | Open Facts for the existing SaaS PDF: both rows use `Document subject`, although the evidence names Nimbus Cloud. | Resolve explicit subjects from source context; retain uncertainty for genuinely ambiguous subjects. A new entity must be searchable and must not collapse into a shared placeholder family. |
| E02 | P1 | The same PDF explicitly says FY26, but both facts show no period and mode `unknown`. | Preserve fiscal-period labels and inherited sentence context. Do not invent a precise fiscal calendar when unknown; show the label and uncertainty. Test both direct period mentions and “same period.” |
| E03 | P1 | Open Trust Gate and submit its prefilled subject/predicate with the blank period: `NOT_FOUND / NO_MATCH`, although that exact fact appears in Facts. | Fix the UI/API contract for identity and optional context. Use canonical selections, distinguish omitted period from an empty string, and test UI-selected facts end to end. Root cause was not established by this browser pass. |
| E04 | P1 | Required cases displays “Four evaluator-ready paths” but no cases or explanation. Overview also has an empty assignment-case panel. | Provide the four required examples with source evidence and reasoning, or explicitly show which cases are unavailable and how to obtain them. Keep case bookmarks as metadata; do not manufacture relationships to fill the page. |
| E05 | P1 | Earnings-run telemetry shows multiple failed extraction and registry calls. Successful extraction entries show about 32,000 input tokens and exactly 1,200 output tokens. | Investigate actual failure classes and truncation before claiming extraction quality. Tune bounded batches/output limits generically; report accepted/rejected claims and failed batches. Matching the output limit is a warning signal, not proof of the failure cause. |
| E06 | P1 | Runs stayed at “Parsing PDF pages / 5%” while telemetry already contained extraction and registry activity. Refreshed state later showed grounding. | Make progress reflect the actual stage, completed/total batches, last heartbeat, and current activity. Verify automatic updates against a run that lasts several minutes. |
| E07 | P1 | Telemetry renders `FAILED`, zero tokens, and a dash for latency without the actual reason or a repair action. | Surface sanitized error code/message, failed batch/page range, retry history, and resumable actions. Distinguish transport success from validated structured extraction. |
| E08 | P1 | Overview in live mode says `recorded-demo`; it shows one reconciliation while the workspace has zero relationships. Its “latest diff” claim count grows with total source claims. | Derive every diff metric and mode label from the selected committed run/revision. Empty history must show zero/empty states. Test a new live workspace and each incremental upload. |
| E09 | P1 | Both context-poor SaaS facts display `SUPPORTED`; the evidence inspector calls the monetary interpretation `eligible`. | Explain what support establishes, and make machine eligibility depend on required entity/context validation. The observed Trust Gate blocked with `NO_MATCH`; unsafe executable output was not demonstrated. |
| E10 | P1 | Vision is unconfigured while the overall sidebar says provider-backed processing is enabled without qualifying PDF type. | Clearly expose per-document unsupported scan/chart capability before or during ingestion. Configure a suitable vision provider when available; retain explicit partial/quarantined results otherwise. Image-only extraction was not tested in this pass. |
| E11 | P2 | Search `Nimbus` returns zero; `retention` returns one result. | Search source-backed entity aliases and expose the retrieval path. Validate semantic/paraphrase retrieval through the UI, not only the API. The browser observation alone does not prove which search algorithm is used. |
| E12 | P2 | The apparent “All statuses” dropdown does nothing when clicked. DOM exposes a generic container, not a select/button. | Implement a real accessible status filter with counts and a clear/reset action; test filtering contested and supported facts. |
| E13 | P2 | Fact evidence shows an opaque document ID and a whole-page quotation, with no direct source-page link in that inspector. Source-page links exist only in Documents. | Show readable document names and direct source navigation beside each claim. Add exact highlights where coordinates are supported, and explain page-only precision otherwise. |
| E14 | P2 | The annual-report inspector presents a long page list without page search/jump controls; publication and printed-page metadata are blank in inspected entries. | Add page jump/search and compact navigation. Extract or expose uncertainty in publication/page metadata; keep PDF page numbers authoritative. |
| E15 | P2 | Review queue is a dropdown of ordinary supported facts rather than an evidence-led conflict queue. Selecting “Prefer for a named use” adds no named-use field or alternative selection. | Show the competing values and sources, review reasons, current revision, and explicit use scope. Require the relevant fields before recording preference; verify stale decisions and revocation. |
| E16 | P2 | Trust Gate requires hand-entered strings, has no visible historical-revision input, and calls its output “signed-off JSON.” | Add a “Resolve” action from a fact, structured context selection, historical revision support, and plain decision wording. Do not imply human sign-off where none occurred. |
| E17 | P2 | Overview reports 100% evidence coverage while hundreds of candidate claims are being grounded and only two canonical facts exist. | Separate candidate, accepted, rejected, published, and pending counts; define the coverage denominator. Do not let a percentage imply complete extraction quality. |
| E18 | P2 | Reload from Runs returns to Overview; navigation does not change the URL. | Make major screens and selected facts/runs linkable and preserve state across reload/back navigation. |
| E19 | P2 | Workspace selector exposes only the existing workspace with no visible creation action. | Add a simple create/select workflow so an evaluator can isolate unrelated PDF collections. Confirm isolation without setup through a separate API client. |
| E20 | P2 | Settings clearly reports capability/configuration, but offers no provider health probe or practical recovery action. | Keep secrets server-side; add a bounded capability test with explicit cost/error output and copyable configuration guidance. Editable credential fields are not required. |
| E21 | P3 | Escape does not dismiss the evidence inspector. Upload labels and the fake filter have weak control semantics. | Add keyboard dismissal, focus management, and semantic upload/filter controls; verify keyboard-only navigation. |
| E22 | P3 | Large hero, repeated promotional copy, and sparse empty panels occupy substantial space above the useful data. | Prioritize active runs, facts, failures, and next actions in the working UI. Preserve the green palette and clear visual hierarchy. |
| E23 | P2 | Reopening Settings briefly displayed all providers offline, `RECORDED DEMO MODE`, and a full $20 budget before the real live settings arrived. | Render an explicit loading state; do not present fabricated defaults as runtime facts. Verify slow and failed settings requests. |

## Browser-dependent or unverified findings

- **Original PDF viewing:** clicking a document's Open page link created a new
  internal-browser tab that became blank. The inspected link correctly contained
  `#page=24` for page 24. This may be an internal-browser PDF/download limitation;
  it is not proof of a broken file endpoint. Test in supported browsers and
  provide an embedded viewer or an explicit download fallback.
- **JSON export:** clicking Export JSON produced no visible feedback, and the
  browser download event timed out after ten seconds. No console error appeared.
  Successful export and exported-file integrity remain unverified; reproduce in
  Chrome and provide a visible success/error state.
- No new out-of-domain fixture was generated during this pass. The SaaS case
  was an existing real live output, not a fresh generation in this evaluation.
- Cross-document correctness, semantic discovery beyond page 24, scan fallback,
  review revocation/staleness, historical Trust Gate, and no-key demo startup
  require additional end-to-end verification. Accepting/parsing 100 pages is
  not equivalent to validating useful extraction across all 100 pages.
- Pricing figures below are application-reported ledger values, not independently
  verified provider invoices or proof of cumulative spend across older volumes.

## What worked

- The live application loaded without a key-entry step or browser-console errors.
- All nine navigation screens opened and were visually coherent.
- Both actual PDF uploads were accepted through the UI, and parsed page counts
  matched the files. Other screens remained usable during processing.
- Duplicate detection gave a clear message and avoided an extra document.
- The existing monetary claim normalized millions to base units and retained a
  source quote and PDF page reference.
- Literal predicate search worked; no-match search had a useful empty state.
- Review rejected an empty rationale with a clear validation message.
- Trust Gate did not return an executable value for its failed query.
- Settings concealed keys and separated extraction, reasoning, vision, and
  embeddings; telemetry exposed real provider activity and a remaining budget.
- Knowledge Diff listed the two existing committed new-fact events with run IDs.

## Challenge traceability

| Assignment expectation | Browser-led verdict |
|---|---|
| Runs and accepts new PDFs through UI/API | UI upload verified; fresh end-to-end publication still under observation. Clean clone setup not retested. |
| Meaningful numerical or semantic facts | Numerical values exist, but missing subjects/periods materially reduce usefulness. New semantic quality not yet demonstrated. |
| Every fact links to PDF evidence | Existing facts have source ID, quote, and page; direct fact-to-PDF navigation and precision need improvement. |
| Corroboration, contradiction, contextual reconciliation | Not demonstrated in the live workspace during this pass. Do not award a pass from feature labels alone. |
| Four examples, including an honest failure | Live Required cases page is empty. Telemetry failures exist but are not explained as an evaluator-ready case. |
| Generalization beyond starter documents | Existing SaaS output proves some non-starter numerical discovery, but loses basic context. Broad generalization remains unproven. |
| Large PDFs / many PDFs | Two uploads and 100-page parsing verified; completion latency and quality need validation. |
| Dynamic schema | New SaaS predicate names are visible; semantic registry quality remains unverified. |
| Incremental ingestion | Uploads preserve the original facts; final relationships/history must be checked after publication. |
| README sections, meaningful Git, <=3-minute video | README has the requested sections and a reported 29.6-second redacted video. Video content was not watched here; masking evidence creates a submission risk if the required cases cannot be judged. Meaningful history was not re-audited. |

## Recommended repair order

1. Correct entity/period extraction and validate structured outputs on small,
   unseen PDFs; preserve uncertainty without losing explicit source context.
2. Repair the UI-to-Trust-Gate contract and require validated context for use.
3. Diagnose failed/truncated batches and bound end-to-end processing latency;
   expose failure reasons, true progress, and resumability.
4. Validate cross-document grouping and all four required examples through live
   runs; record failures honestly and keep production starter-blind.
5. Replace misleading dashboard/diff metrics and wire real search/filter/review
   controls with source navigation.
6. Recheck the final video, no-key experience, exports, keyboard accessibility,
   and clean-clone instructions. Only then add further cosmetic refinement.

## Final run observations

At approximately 03:10 UTC, about ten minutes after the presentation upload and
eight minutes after the annual-report upload:

- Presentation run remained **PROCESSING / 60%**, “Grounding 410 candidate
  claims.” A recent telemetry snapshot showed **121 entries: 109 complete,
  11 failed, one reserved**, zero cache hits, and **$0.0876** reported spend.
- Annual-report run remained **PROCESSING / 24%**, “Parsed 100 pages.” A recent
  telemetry snapshot showed **30 extraction entries**, 28 complete and two
  reserved, zero cache hits, and **$0.3540** reported spend. All 28 completed
  entries displayed exactly **1,200 output tokens**, the configured limit.
  Several entries reported two attempts.
- The latest Settings observation reported **$19.4791 remaining** in the local
  budget ledger. Telemetry and budget snapshots were taken at different times
  while calls continued, so they are not a reconciled accounting statement.
- Neither fresh upload had reached verified completion by the cutoff. The last
  inspected Facts screen still contained only the two original SaaS facts.
  No fresh cross-document relationship was validated. The run states were
  checked again after a full browser reload.
- Both runs were left active under the existing cap, with the Runs screen open.
  The reported elapsed times are observation bounds, not final benchmarks.
  There was no claim of an actual backend deadlock: provider telemetry continued
  to accumulate even when stage percentages remained unchanged.

**Evaluator judgment:** do not mark the full live acceptance checklist passed
on this evidence. First reproduce and repair the correctness and observability
gaps, then finish the two runs and inspect their source-backed results. The
prior successful two-fact smoke test was insufficient to establish that the
complete assignment works on realistic PDFs.
