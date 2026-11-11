# h5.3 — Qwen tool batches and complete sanitizer feedback

The user authorized repairing Qwen3-Coder tool-call handling and incomplete ASan feedback, then rerunning affected tests while preserving the campaign and leaving production unchanged. An hourly check in the current Codex chat was also explicitly requested and created. It reviews progress, fixes isolated runner issues, preserves evidence and keeps GitHub synced. The independent fifteen-minute Git backup remains separate.

## Qwen3-Coder failure and fix

All three saved h5.2 C++ responses printed five complete native function blocks: get_task, claim_task, ls, read TASK.txt and read PUBLIC_CASES.json. The previous fallback accepted one complete block only, so those responses produced no executable calls. This was workflow compatibility failure, not a measured C++ implementation failure.

The new fallback atomically validates an entire batch of1..8 complete blocks against the tools currently offered in that request and their exact parameter schemas. It preserves call order and creates distinct OpenAI tool ids/indices. If any block is unknown, malformed, missing a required parameter, mixed with prose, truncated, capped or incomplete, no partial batch is normalized. The proxy still executes nothing. Original and delivered streams, normalization count and timings remain archived.

All tools in this experimental profile declare sequential execution through the installed Pi runtime's supported per-tool setting. This is necessary because the runtime normally permits parallel tool calls. Dependent write/append/check/finish actions now run in order. Actual broker ownership, assignment fencing, role scopes, source hashes, receipts, budgets and closure rules remain authoritative. Native structured batches use the same ordering policy. Parallel agents and inference-slot experiments remain distinct and scheduled.

An installed-Pi-agent integration test used delayed writes to verify ordering and a deliberately queued post-closure write to verify that guarded closure aborts the remaining batch. All three actual saved Qwen batches were replayed through the converter and produced the five expected ordered, uniquely identified calls. Atomic rejection of bad trailing blocks and fragmented socket delivery were also tested.

## ASan failure and fix

The controller previously overwrote the normal result's aggregate passed flag when an ASan/TSan build failed, but returned the normal rows to the model. Qwen3.5's Buffer passed normal tests while its instrumented build returned190 in newly resized bytes that should be zero. The model received a failed normal summary with an empty failures list.

A verification suite now retains each required mode separately. Public run_tests runs normal and ASan/UBSan for C++; threaded queues additionally require TSan. If an earlier mode fails, later modes are explicitly marked not run. Python uses normal checks. Public-mode failures provide the public inputs/expected/actual data and compiler/runtime diagnostics. Saved authored tests are still mandatory and are reported separately. Completion receipts require all required fixed modes plus authored tests to pass for the exact artifact and assignment.

Independent private acceptance and finalizer acceptance use the same per-mode representation, retaining input/expected redaction. The failed mode, counts and diagnostic rows now survive into developer repair feedback. Passing normal results are not rewritten to impersonate an ASan result. Every raw mode report and aggregate suite is saved. No private oracle or contract was weakened.

The old faulty Qwen3.5 artifact was replayed read-only: normal passed, ASan failed, and the new feedback contained the actual public ASan failures. Its source hash remained unchanged. A known-correct Buffer passed both modes; simulated TSan/compilation failures confirmed mode-specific diagnostics and skipped-mode reporting. These are operator verification results, not new model coding scores.

## Fresh reruns and preservation

New ids end in `-h5.3`; h5.2 results are retained and compared separately. Targeted order is Qwen3-Coder C++ Buffer, Qwen3.5 35B C++ Buffer, Coder-Next Python/C++ controls, an explicitly seeded Qwen3.5 ASan repair probe, then Qwen3-Coder Python CSV. The repair probe starts from the model's preserved faulty source/tests without operator corrections; it is excluded from solo coding rankings. All remaining model/task/seed, team and parallel phases continue afterward.

All121 Python/guard/socket/targeted regression checks passed, plus extension and installed-Pi execution checks. The new constructor/probe scheduling also passed the general regression checks. Task catalog and seeded acceptance oracles are byte-identical to previous revisions. Model weights, sampling, seeds,32K runtime allocation and4096-token response limit remain unchanged. The interface, ordered tool policy and public sanitizer workload define a distinct revision, so timings and outcomes must not be pooled across versions.

The old C++ queue trial finished before the switch; the next active h5.2 trial was checkpointed and preserved as interrupted. Local full-state checkpoint: `before-h53-tool-asan-fix-1794372782242915420` under the existing campaign backup root. Previous private service, wrapper and revision metadata are in `repairs/h5.3/previous-*`. Production services/settings, selected fleets and Gremlin Garden were checked against the preserved baseline and were not changed.

Restore only the private benchmark if rollback is needed: checkpoint/stop the private campaign, restore its previous service/wrapper/active-revision files, reload user service definitions and start the private campaign. Preserve new results before rollback. The originals in repairs/h5 restore the earlier h4 experimental runner; each later repair folder preserves its immediate predecessor. No model is automatically promoted to production.

The standalone grader continues to run the explicitly requested --mode; run normal, asan and applicable tsan checks separately. Full guarded public/acceptance suites are exercised by the archived runtime and native cases. Keep reference/oracle code and this repository outside scored agents' workspaces.
