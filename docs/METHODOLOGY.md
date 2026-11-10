# What the experiment measures

The main outcome is independently accepted development tasks per measured wall-clock hour, alongside pass rates. Token rate is diagnostic. Python and C++ are never merged into a single coding score.

The main campaign uses 32K context, a 4096-token per-response output cap, temperatures/seeds and supported sampling settings recorded in `configs/benchmark.json`. Source fixtures and oracles are versioned. Context/slot API diagnostics use separate profiles and are not scored as guarded teamwork. Agent count, distinct model count, loaded-model count, and inference slots are different quantities.

Compatibility probes establish only the particular tool exchange they exercise. Passing an addition-tool probe does not prove successful full-agent tool formatting, stage handoff, or code generation. Later failures must retain those distinctions. Some C++ test-author trials repeatedly reached the output cap without producing a usable tool call. They are workflow/output-limit failures, not proof that the fixed integration source was incorrect.

Every acceptance receipt is tied to an artifact hash and assignment. A test author's own assertion can be wrong; external tests remain authoritative. The archived authored-test runner's aggregate exit field can be misleading when combining a negative signal exit and successful runs: use its `passed` field and individual run records, not the maximum exit number alone.

Inspect actual attempt counts. Historical controller terminal-failure timing can end a case before every nominal repair attempt is used; these records are provisional workflow evidence and should not establish a final cross-model superiority claim. Qualifier fixtures sometimes start from known-correct source and measure orchestration only. They must stay out of coding rankings.

Memory telemetry samples whole-system/shared GPU consumption. Do not add UMA VRAM/GTT counters as independent physical RAM. Existing swap occupancy differs from new swap-in/out. Overlapping job durations do not equal machine wall time; use complete parallel-batch elapsed time for machine throughput.

The schedule now gives compatible models one common Python/C++ task pair before the longer remaining repetitions. These are existing matrix cells with unchanged checks and settings; they are not substitute tasks. The full six-family/three-seed tracks, role probes, team matrices, parallel diagnostics and stability run remain scheduled.

The frozen histories intentionally preserve unsuccessful setup and earlier runner versions. Do not silently substitute a passing rerun for a failure or pool different runner revisions. This finite repeated-family study does not establish broad unseen-domain capability.
