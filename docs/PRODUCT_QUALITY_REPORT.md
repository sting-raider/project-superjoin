# Product quality and correctness report

Date: 2026-09-09  
Release branch: `main`

## Outcome

The evaluator-facing pass repaired the live product without adding starter-specific
rules or bundled content. A clean image starts with zero workspaces and no
configured providers. The configured local instance retains the user's three
uploaded PDFs and now publishes one real cross-document corroboration from 289
grounded claims and 278 active fact families.

## Root causes and repairs

| Observed failure | Root cause | Repair |
|---|---|---|
| Supported fact inspector had no evidence | Fact detail rediscovered claims by raw subject/predicate equality after canonicalization | Follow `fact_version` → `fact_memberships` → claims → anchors/documents |
| Period appeared inside predicate identity | Provider predicate text was registered without removing qualifiers already held in structured context | Canonicalize conceptual predicate before registry resolution; preserve period and modality separately |
| Zero useful cross-document relationships | `FY24`/`FY2024`, modality synonyms, and table scales split or distorted comparisons | Normalize period/modality in interpretations and combine raw cell value with its declared unit/scale |
| False same-document relationships | Repeated rows and multi-valued predicates were compared as independent evidence | Require relationship pairs to come from different source documents; abstain on unresolved semantic values |
| Fact search/filter was incomplete | The browser filtered a limited initial result set and displayed a decorative status control | Debounced server query with real status vocabulary, total count, limit, and offset |
| Diff, Review, Trust Gate, and telemetry were confusing or stale | Display-first controls lacked drill-down, queue semantics, selector context, or refresh behavior | Real Diff detail, review-needed queue with revocation, canonical fact selector, result card, and live telemetry polling |

## Live validation

The repaired three-document workspace produced:

- 3 documents, 289 immutable grounded claims, and 278 active fact families.
- 1 cross-document `CORROBORATES` relationship.
- Annual-report value `₹81,415.38 million` and presentation value `8,142`
  with declared `INR crore` compare as `rounding-compatible` after deterministic
  normalization.
- Relationship dimensions report matching subject, predicate, period, and
  modality.
- Published fact evidence coverage is 100% in the current workspace.

This is diagnostic evidence from the user's local corpus. Production code does
not contain its names, values, pages, IDs, or expected outcome.

## Verification

- 119 pytest tests passed.
- Ruff and Python compilation passed.
- Vite production build passed.
- Clean Docker image health check passed.
- A direct clean-image run returned zero workspaces, all four provider roles
  unconfigured, and no API-key field in the Settings response.
- Anti-leakage, provider, provenance, security, and source-management suites passed.
- Five document prompt-injection cases passed with zero strict Trust Gate false allows.
- Release-artifact audit found no tracked or historical source PDFs/videos and no generated runtime storage.
- Credential-pattern scans found zero matches in tracked files, Git patch history,
  the SQLite database, and container logs.

## Visual and interaction QA

The live site was operated in a browser across Briefing, Facts, Sources,
Relationships, Knowledge Diff, Review, Trust Gate, Runs, Configure, and both
evidence inspectors. Search, status filtering, row drill-down, Trust Gate
resolution, telemetry expansion, workspace controls, and source controls were
exercised. Screenshots were captured at 1440×900 for every repaired surface,
with additional Briefing checks at 1366×768 and 1920×1080. They remain local and
untracked because they contain metadata from user-supplied documents.

## Known limits

- The current three-document corpus contains one extracted cross-document
  overlap. Additional contradictions, contextual reconciliations, and
  supersedence will appear only when extraction produces comparable grounded
  claims; the product does not fabricate them.
- Complex charts, low-resolution scans, handwriting, and some cross-page tables
  can still require visual extraction or human review.
- A provider can return semantically weak claims. Evidence inspection, explicit
  uncertainty, evaluation fixtures, and the Trust Gate limit the effect, but do
  not make model output infallible.
- The local review interface targets one evaluator rather than concurrent
  enterprise reviewers.

## Commits in this pass

- `37bf49e` — resolve fact evidence through published memberships
- `43829af` — separate predicate context from canonical identity
- `02a5572` — expose complete evidence desk query context
- `254b9b3` — make evidence desk controls and inspectors operational
- `7ee822d` — normalize fact context before relationship reasoning
- `ced21e5` — restrict evidence relationships to independent sources
- `8527e85` — make registry evolution order deterministic
- `df176c4` — normalize table values with declared scale units
- `53b6180` — publish canonical values from current interpretations
- `2fb7e04` — preserve parsed relationship and diff details
- `c2997b9` — record live relationship root cause and validation
- `9795593` — balance sparse editorial card grids
