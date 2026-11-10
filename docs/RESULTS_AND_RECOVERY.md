# Results and recovery

Each campaign lives under `results/<campaign-id>/`. `SNAPSHOT.json` states when it was exported, which records are covered, which cases remain in progress, and any export errors. The live run may be ahead of GitHub by the backup interval or a network outage.

`cases/<directory>/result.json` preserves the recorded result. The directory name is retained because an archived interrupted directory may share its internal case ID with a later attempt. `CASE-INDEX.json` lists them all without merging failures and interruptions into later scores.

`artifacts/cases/*.tar.gz` contains completed case workspaces, required source, saved tests, test receipts, native queue evidence and available agent session histories. Workspace binaries are retained when present, but external compiler caches, credentials and agent auth/settings are omitted. Each bundle contains `EXPORT-MANIFEST.json` with source/stored hashes and any omissions or credential redactions. Do not assume that a sanitized/incomplete export reproduces an original artifact hash: inspect that ledger.

`artifacts/transport/*.tar.gz` groups finished model HTTP streams by UUID. These preserve request bodies, raw response streams and timing records. `artifacts/evidence/` preserves qualifications, baseline replay, repair comparisons, operator snapshots and later parallel phases.

Telemetry is stored as compressed append-only chunks under `telemetry/<log-name>/`. Read `INDEX.json` in order by byte offset, decompress each listed chunk, and concatenate. Each chunk ends on a full newline and has original/stored hashes. Do not concatenate chunks from different campaigns.

## After a machine loss

1. Clone the private repository. Confirm the latest GitHub commit and `SNAPSHOT.json`; inspect `export_errors` and the backup coverage timestamp.
2. Verify suite hashes with `python3 -m benchmarks.run verify`. Verify archive hashes using Git and each internal export ledger. Keep the repository's oracles outside candidate workspaces.
3. Read the result index to recover completed progress, including failures. Extract relevant case archives into a **new recovery directory**, inspecting member paths and refusing absolute paths, traversal paths and links. Never execute archived candidate code directly; use the isolated grader.
4. Reacquire model weights separately using recorded tags and manifest/layer digests from `configs/models.json`. Some tags are local aliases; their names alone are not enough to guarantee matching weights. Restore the documented toolchains for comparable measurements.
5. Reconfigure a new test-only OpenRig/Ollama environment. Archived harness versions retain full orchestration source, but their historical absolute paths must be adapted. Native databases, live tmux sessions, model weights and machine credentials are not restored from this Git repository. Local full-state backups, when available, are the route for restoring native state.
6. Resume only after verifying completed cells against the recovered evidence. An active task at the last snapshot is incomplete and should be preserved as such, then rerun in a fresh workspace. Do not overwrite recovered attempts or a running production instance.

This is an off-machine archive of tests and experimental evidence, not a full operating-system image or a zero-loss transaction log. If GitHub is unavailable, pending local commits remain and the backup retries without stopping the campaign.
