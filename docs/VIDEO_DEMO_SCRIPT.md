# Project SuperJoin video runbook

The final submission video is planned for 2:55. Record the application at
`http://localhost:8080` after `docker compose up --build`; use the bundled
recorded replay for the no-key path and label it as replay. Do not show a live
provider key, terminal environment, or source-derived page content whose
redistribution permission is not recorded in
[`DATASET_REDISTRIBUTION.md`](DATASET_REDISTRIBUTION.md).

| Time | Screen action and narration |
|---|---|
| 0:00–0:12 | Introduce Project SuperJoin and select the two workspaces. |
| 0:12–0:32 | Upload a permitted PDF or show the recorded checkpoint; state whether processing is live or replayed. |
| 0:32–0:47 | Open Knowledge Diff and show that unchanged documents were reused. |
| 0:47–1:12 | Open the corroboration case and inspect both evidence anchors, unit scaling, and precision. |
| 1:12–1:37 | Open the forecast conflict, compare its qualifications, and show the strict Trust Gate block. |
| 1:37–2:02 | Open the data-vintage reconciliation and show the supporting footnote. |
| 2:02–2:24 | Show the native extraction failure, visual-review state, and quarantine outcome. |
| 2:24–2:43 | Show the semantic timeline, evolving predicate registry, and append-only review record. |
| 2:43–2:55 | Open Settings, state that the demo needs no key, and show the machine-consumable resolver result. |

Use browser zoom and a readable pointer, capture captions for every narrated
state, and keep the final export at or below three minutes. If clips are
recorded separately, concatenate them with a short FFmpeg concat list and
verify duration with `ffprobe` before publication. Publish the finished file as
a release asset rather than adding a large binary to normal Git history, and
link the release URL from the README only after the release asset and its
visible evidence have passed the rights preflight.

