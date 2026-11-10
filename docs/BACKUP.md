# Backup operation

The independent backup service reads the live campaign and writes only to this separate checkout. It does not import the live controller, call inference, launch models, stop agents, acquire their job locks, or change production settings.

It runs with low CPU/IO priority and a memory limit. Approximately every 15 minutes it:

1. Copies stable completed result records and immutable case/transport bundles.
2. Adds complete newline-delimited telemetry chunks and current status/diagnostic evidence.
3. Commits only the generated `results/` tree and pushes normally to `main`. It never force-pushes or deletes source evidence.

Credential files are excluded. Common credential token/private-key patterns are redacted if encountered in exported artifacts, and archive ledgers record any changes. No broad home-directory or runtime-state upload is performed. There is no claim that pattern scanning can identify every conceivable secret; explicit exclusions and the narrow campaign source are the primary controls.

Source directory, repository path and authentication remain in local service configuration, not in a committed credential file. Git uses the already signed-in GitHub account. Backup status is written to the ignored `.local-backup/status.json`. A failed network push retains local commits for retry. Export errors are recorded in the uploaded snapshot rather than hidden.

The service performs a final export after campaign completion and disables its own future startup. It remains independent of the benchmark service, so a backup failure does not interrupt tests.

For a different campaign, explicitly configure a new sidecar pointing to its output directory. The tool refuses overlapping repository/source trees. Run a one-time export with:

```sh
python3 tools/snapshot.py --source /path/to/campaign --repo /path/to/this/checkout
```

After reviewing the export, `tools/live_backup.py --once` can commit and push it. That command requires a configured private Git remote. Repository checks use temporary synthetic campaigns and do not run inference.
