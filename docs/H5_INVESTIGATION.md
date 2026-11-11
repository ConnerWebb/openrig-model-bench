# Harness failure investigation — h5

The previous failures mixed model implementation mistakes, authored-test mistakes, tool formatting and harness defects. A passing small addition-tool compatibility probe did not predict full guarded workflow success. Historical failures remain preserved; none has been converted to a pass.

## Confirmed interface and controller defects

- File reads and shell output were serialized as JSON text, double-escaping source and CSV data. Their model-facing replies now use actual text; structured broker details remain archived.
- Public examples showed driver encodings without the exact driver or raw input files. Agents now receive read-only PUBLIC_DRIVER.py/cpp and public-inputs, plus an explanation of the C++ buffer copy mutation. No contract, oracle, hidden input or expected output was relaxed. Python stdlib unittest requirements are explicit; pytest is unavailable.
- A controller race could throw on a failed stage before the advertised three-attempt repair loop finished. Failed/unfinished stages now return bounded retry feedback. Closed assignments still require exact hashes and native ownership.
- An agent could finish its text turn without closing its assignment, clearing its timer and leaving a twenty-minute controller wait. A fenced settled-turn record now triggers a bounded failed stage. It does not fabricate completion or automatically accept code.
- Late deadline callbacks now verify assignment identity before and after broker access. A stale turn cannot abort a later assignment.
- The advertised absolute workspace path did not work in broker/shell tools. Only the exact current project path now aliases the same /work mount; read-only public files remain protected and host home stays unavailable.
- Authored-test aggregation could show exit zero despite a negative signal exit elsewhere. Per-file results and the first nonzero exit are retained. Duplicate Python test basenames are discovered in separate processes. Both Python and C++ saved tests run when present, within a shared 120-second budget. Zero discovered tests still fail.

## Transport and context findings

Qwen3-Coder 30B sometimes printed a complete native `<function=...>...</function></tool_call>` block as text rather than emitting an OpenAI tool call. Both minimal native and OpenAI probes worked, so this depended on the full prompt/workflow. The experimental proxy now normalizes exactly one complete function-only response, only for a currently offered function with valid required parameter types. Extra prose, unknown functions, duplicates, malformed/truncated blocks, output-cap endings and incomplete streams are not repaired. The proxy never executes tools; the original guarded broker remains authoritative. Original and delivered streams are saved separately, with normalization flagged in metrics.

A Qwen3.5 run reached 32,127 prompt tokens plus 641 completion tokens: the complete 32K allocation. Tool/history accumulation could therefore consume response headroom. h5 bounds the model-view history to 48,000 UTF-8 bytes including tool definitions, pins system/current instructions and retains complete recent tool exchanges. Older exchanges or oversized historic outputs may be omitted or marked as shortened. Original sessions and requests remain intact, and the exact upstream request and context-policy metrics are archived. The runtime still allocates 32K tokens; **48KB is a deterministic byte budget, not an exact token count or a new 32K long-context benchmark**. Direct API context/concurrency diagnostics bypass this rolling-history policy.

Five GLM HTTP500 transport events were preserved. Replaying the first exact request against the same isolated runtime completed, so the original error was not deterministically reproduced. Runtime versions were not upgraded. h5 preserves upstream error bodies and records request failures; it does not assume every GLM failure was infrastructure or silently grant unlimited retries.

Saved request and response evidence confirmed non-GPT reasoning was already disabled. GPT-OSS retains low reasoning. No reasoning-policy change was made on speculation.

## Scope, validation and reruns

All 95 Python/controller/guard/socket-level regression checks passed, plus extension loading/protocol checks. Coverage includes all 15 known-good fixed tasks, sanitizer controls, wrong-owner/forged/stale receipts, path isolation, read-only aliases, preserved source escapes, malformed tool rejection, complete streaming delivery, context pairing and the three-attempt failure path.

New ids end in `-h5`. The guarded Coder-Next reference baseline is rerun before candidate ranking. Every eligible model then receives the same Python CSV/C++ buffer pair at seed42, including previous passes as controls, before the broader suite. Remaining previously affected Coder-Next tasks, all task/seed repetitions, roles, teams and parallel profiles remain scheduled. Interrupted pre-repair work is labeled and excluded from scores. New results are not pooled with h4.

The test contracts, seeded oracles, weights, sampling, 4096-token output cap and 32K runtime allocation remain fixed. The agent-facing prompt, tools and rolling-history policy changed, so h5 is a distinct experimental revision. Model-written incorrect assertions, compilation errors, invalid API semantics, deadlocks or failure to follow valid tools remain real failures requiring fresh evidence.

Only private campaign services and wrappers changed. Production Ollama/OpenRig/ComfyUI, selected fleets and Gremlin Garden were verified against the saved baseline. The previous private unit/wrapper, active revision metadata, full local checkpoint and hashes of every pre-h5 case result were preserved. No automatic production promotion is configured.

Rollback is an operator action: stop only this private campaign, preserve its new state, restore the saved previous campaign service and pi wrapper, restore previous active-revision metadata, reload user units and start the private service. This resumes the old experimental runner; it does not fix its known faults or erase h5. Do not run archived launch scripts against production. Machine-specific rollback files and full native-state backups remain local; credentials and native SQLite state are intentionally not uploaded.

## h5.1 follow-up from the live qualification trial

The initial h5 qualification was preserved and interrupted for a second harness fix. The agent changed a passing reference implementation and wrote incorrect expected values and quoted CSV tests. It also attempted an oversized write that hit the 4096-token response cap. No successful coding result was claimed. The newly repaired controller did advance to a second attempt without the previous twenty-minute unclosed-turn wait, providing live evidence that the repair-loop fix works.

That trial exposed remaining escaped, duplicated authored-test logs in the `run_tests` reply. h5.1 delivers readable log text once per saved test and explicitly separates the fixed-public verdict from the authored-test verdict. Full structured evidence remains in the control archive. Chunk guidance now recommends small write/append calls. Source, tool, ownership and completion guards are retained.

The workflow-only baseline in h5.1 verifies read-only supplied known-correct source and tests, then performs the native developer/reviewer/finalizer handoff. This isolates orchestration qualification from a model rewriting its reference fixture. **It is not a coding score, and it does not demonstrate from-scratch coding ability.** Scored candidate tasks still start from the original incomplete fixtures and require model-authored implementation, tests and README, three bounded attempts, private acceptance and applicable sanitizers. Larger exploratory qualification topologies retain their separately documented module/test-author operations.

Current fresh candidate ids end in `-h5.1`; h4, h5 and h5.1 stay separate. The same 95 regression checks and updated extension protocol/log/reference-role checks passed again before candidate testing. Both older immutable harnesses and the interrupted h5 trial remain available. The preceding experimental service/wrapper/revision files were preserved again under `repairs/h5.1`; the pre-follow-up full local checkpoint is `before-h5-log-format-repair-1794356781731623162`. Restoring h4 directly still uses the originals preserved in `repairs/h5`.

## h5.2: a real oversized test-log transport failure

A model-created `test_driver.cpp` copied the interactive public C++ driver and ran without its required stdin. The program emitted a large array and exited153 (file-output limit). That saved test is invalid and must be repaired by the model; public functional checks on its Buffer implementation had passed. However, the resulting authored-test report was roughly2.1MB, exceeding the extension's200,000-character child-output limit. The reply became “Tool broker unavailable” instead of reporting the actual failing saved test. This was an additional harness defect.

h5.2 caps model-facing broker results at100,000 UTF-8 bytes. Normal replies are unchanged. Oversized results are summarized with explicit omission markers while retaining verdicts, exit codes and next actions. The complete original result is preserved in a separate `oversize-tool-*.json` control record before delivery. Actual source/test receipts and acceptance decisions use the full original result. UTF-8 output avoids inflating Unicode into repeated JSON escapes. Replaying the actual saved2,108,593-byte report produced an8,768-byte projection with the same failed verdict; the original was retained unchanged.

Four added automated checks cover large Unicode logs, unchanged ordinary replies, nested failed values, and the complete broker CLI envelope plus original-evidence preservation. **All99 harness checks passed**, plus extension checks and repository validation. The interrupted h5.1 C++ trial is preserved and excluded from model scores. Its completed fresh Python CSV trial remains a historical h5.1 PASS (2.88minutes, first attempt), not a new h5.2 score.

Fresh current ids end in `-h5.2`. Both reference handoffs and all candidate task pairs are rerun under this revision, then the remaining scheduled campaign continues. Previous unit/wrapper/revision files are in `repairs/h5.2`; the full pre-fix local checkpoint is `before-bounded-reply-repair-1794357755133075760`. To return directly to the original h4 experimental runner, use the originals in `repairs/h5`. Production remains outside these changes.
