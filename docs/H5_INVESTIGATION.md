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
