# Harness investigation and fresh-rerun checkpoint
2026-11-10 18:53:33 CST

Current isolated revision: **h5.2**. Production unchanged: **True**. This is an ongoing campaign, not a completed cross-model ranking.

## What caused failures
Confirmed runner defects included escaped source/log replies, confusing driver encodings, terminal-stage retry races, unclosed-turn waits, malformed function-call transport, accumulating context, duplicate test discovery/aggregate exit reporting, and oversized test logs being returned as broken tools. Models also made real code, compilation and authored-test mistakes; those remain failures. Five historical GLM HTTP500 events were preserved; the first exact-request replay completed, so the runtime failure was not deterministically reproduced.

## Repairs and validation
- Readable source, command and test-log replies; fixed-public and authored-test verdicts separated.
- Read-only exact public drivers/raw inputs, explicit unittest instructions and small write/append support.
- Fenced stage retries and completion; strict complete-call compatibility normalization; bounded rolling history with original and upstream requests archived.
- Saved Python tests with duplicate basenames are discovered independently; saved Python and C++ tests both run. Nonzero and signal exits retain failed verdicts.
- Bounded UTF-8 broker replies retain verdicts and preserve complete oversized results separately. Actual2.1MB failing report projected to8.8KB without changing its failed verdict.
- **99 harness checks, extension protocol checks and11 repository checks passed.** Frozen catalog/oracles are unchanged from h4; weights, sampling,32K runtime allocation and4096-token response cap are retained. Prompt/interface/history changes define a separate revision.

## Guarded reference handoffs (not coding scores)
| Language | Outcome | Minutes | Attempts |
|---|---|---:|---:|
| cpp | PASS | 1.44 | 1 |
| python | PASS | 2.04 | 1 |

These supplied known-correct fixtures verify developer/reviewer/finalizer ownership, independent acceptance and completion without reminders.

## Fresh candidate coding results
| Model | Language/task | Outcome | Minutes | Attempts |
|---|---|---|---:|---:|
| next | cpp / cpp-buffer | PASS | 1.28 | 1 |
| next | python / py-csv | PASS | 1.48 | 1 |

Current task: `solo-coder30-py-csv-s42-h5.2`. Qualified candidates: next, coder30, devstral, q35, q9, q27q4, q27q8, glm, nemo, q122, gpt120, gpt20. Tiny is a protocol control; Gemma is ineligible for these guarded tool tasks.
Fresh Python and C++ candidate results remain separate. Prior accepted h5.1 Python CSV work is preserved as historical evidence, not reused as h5.2 success. Interrupted diagnostic trials are preserved and excluded from coding scores.
The campaign continues the common task pair across all eligible models, then remaining affected tasks, full task/seed repetitions, role/team combinations and parallel diagnostics. No model is promoted to production.

## Preservation and recovery
All 76 pre-investigation result files were checked: 0 changed. Previous frozen harnesses, source/test artifacts, histories, native proofs, raw/upstream/delivered streams, errors and telemetry remain preserved.
Full local checkpoints: `/home/cow/Documents/Codex/Backups/openrig-programming/20261109-235342`. Latest pre-log-limit checkpoint: `before-bounded-reply-repair-1794357755133075760`.
Direct original h4 rollback instructions: `repairs/h5.2/LOCAL-RESTORE.txt` locally, using originals in `repairs/h5/previous-*`. Intermediate prior unit/wrapper/revision files are also retained in each repair folder.
GitHub exports exclude weights, credentials, production state and native SQLite; local full-state checkpoints remain separate. The independent backup continues approximately every15minutes, retaining local commits on upload failures.

[Detailed investigation and revision history](../../../docs/H5_INVESTIGATION.md)
