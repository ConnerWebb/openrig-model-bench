# Reference workflow qualification trials completed
2026-11-11 06:59:51 CST

All10 planned1/2/4/5/6-agent integration-reference workflow trials have finished under h5.4. They start from supplied known-correct source and use Coder-Next throughout. These are workflow diagnostics, not scored model coding trials or mixed-model-team results.

| Language | Agents | Result | Minutes | Attempts |
|---|---:|---|---:|---:|
| cpp | 1 | PASS | 0.57 | 1 |
| cpp | 2 | PASS | 1.72 | 1 |
| cpp | 4 | FAIL | 15.99 | 3 |
| cpp | 5 | FAIL | 38.35 | 3 |
| cpp | 6 | PASS | 6.87 | 1 |
| python | 1 | PASS | 0.54 | 1 |
| python | 2 | PASS | 0.92 | 1 |
| python | 4 | PASS | 4.25 | 1 |
| python | 5 | PASS | 4.66 | 1 |
| python | 6 | PASS | 4.61 | 1 |

Python reference trials passed at1,2,4,5,6 agents. C++ passed at1,2,6 agents and failed at4/5. The separate earlier3-seat CSV/Buffer baselines also passed; those use different task fixtures and are not merged into the integration table.
The C++4-agent failure included generated tester code missing include paths and later misreading expected/driver data. The5-agent trial had fixed partial-module normal/ASan passes but failing model-authored tests. These outcomes do not establish a controller, model-source correctness, or production fault. The6-agent case verified scoped parallel developers, integration, test author, reviewer and lead completion without a manual reminder. Failed exploratory topologies remain recorded and later scored configurations can still be attempted with explicit warnings.

## Coding results and continuation
Completed solo totals: **Python 13/16; C++ 12/17** accepted. Qualifiers, probes, interruptions and older revisions are excluded. Models have unequal task coverage at this point; the shared screening pair remains the equal-work comparison.
New Coder-Next C++ binary-parser and LRU-cache tasks passed on first attempts. Earlier CSV/statistics and seed43 Python-queue failures remain preserved. No passing rerun has overwritten those failures.
Current task: `solo-next-py-expression-s42-h5.4`. The full per-model task/seed sweep is running; unfinished work is excluded from scores. Team/model combinations and parallel processing remain later phases of the finite plan.

## Health and preservation
Heartbeat age at capture: 0.6s. Both owned services remain active. No resource guards/monitor failures or recurrent compaction-budget errors were observed. Expected bounded client-disconnect entries remain archived separately.
Production unchanged: True. Verified 120 older result hashes; 0 changed.
No healthy trial, model answer, authored test, live harness or production setting was altered. The independent approximately15-minute Git backup and hourly checks continue.
