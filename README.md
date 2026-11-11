# OpenRig model benchmark

Private, versioned Python/C++ coding tests and preserved local-model results for the Framework Desktop Ryzen AI Max+ 395, 128 GB RAM, Fedora 44.

This repository backs up the experiment. It is **not the live campaign directory**. Its backup process reads completed artifacts without restarting inference, changing production settings, or running another model. New snapshots are committed and pushed approximately every 15 minutes while this campaign is active. Failed pushes retain local commits and retry.

## Current results

- [Latest uploaded report](results/openrig-programming-20261109-235342/status/RESULTS.txt)
- [Snapshot coverage and current task](results/openrig-programming-20261109-235342/SNAPSHOT.json)
- [All completed case records, including failures and interruptions](results/openrig-programming-20261109-235342/CASE-INDEX.json)
- [Individual result records](results/openrig-programming-20261109-235342/cases)
- [Source, test evidence and agent histories](results/openrig-programming-20261109-235342/artifacts/cases)
- [Exact model requests, streamed responses and timings](results/openrig-programming-20261109-235342/artifacts/transport)
- [Searchable per-request timing index](results/openrig-programming-20261109-235342/STREAM-INDEX.json)
- [Memory and event timelines](results/openrig-programming-20261109-235342/telemetry)
- [Baseline, qualification, repair and comparison evidence](results/openrig-programming-20261109-235342/artifacts/evidence)

Results are preliminary while the campaign runs. Python and C++ scores stay separate. Tool compatibility, harness qualification, interrupted attempts, and different harness versions are not pooled into coding rankings. A workflow failure does not automatically establish that the implementation itself is wrong. Read each result's attempts, limits and evidence.

The current isolated campaign uses revision **h5**, addressing confirmed harness issues. [Investigation, changes and limitations](docs/H5_INVESTIGATION.md). Historical h4 results and the h4 grader remain preserved; use `--suite h4` to reproduce those checks. Fresh h5 results are reported separately.

## Reusable tests

The pinned `h5` suite contains six core task families per language plus three integration/partial-work fixtures. [Contracts, reference solutions, drivers and seeded oracles](benchmarks/suites/h5) are copied byte-for-byte from the deployed harness. [SHA-256 manifest](benchmarks/suites/h5/MANIFEST.json) detects accidental edits.

```sh
python3 -m benchmarks.run verify
python3 -m benchmarks.run list
python3 -m benchmarks.run materialize py-csv workspaces/my-candidate
```

Implement the task in the materialized directory, save standard-library `unittest` tests and `README.md`, then grade it **on an isolated Linux operator machine**:

```sh
python3 -m benchmarks.run check py-csv workspaces/my-candidate \
  --private --seed 1042 --output local-results/my-candidate-001
```

For C++, run normal and separate sanitizer modes with new output directories. Use `--mode asan` for ASan/UBSan and `--mode tsan` for the threaded queue. The original baseline used Python 3.14, Clang 22, C++20, GNU bfd linker, bubblewrap and systemd user scopes. [Recorded versions](configs/toolchains.json) and [sampling/model settings](configs/benchmark.json) are preserved.

The standalone grader reuses the original fixed functional checker and authored-test runner. It **does not simulate an OpenRig team** or supply native review/finalizer receipts. The [archived guarded harnesses](archive/harness) preserve that orchestration code and its history; those deployment scripts have historical machine paths and require operator configuration before reuse. None are launched automatically by cloning this repository.

This repository contains reference answers and private acceptance checks. Keep it outside scored agents' workspaces. Give agents only materialized projects; the grader mounts their projects in isolation and keeps its oracle outside them.

## Extend and recover

- [Add new test families or suite versions](docs/ADDING_TESTS.md)
- [Result layout, preservation limits and recovery](docs/RESULTS_AND_RECOVERY.md)
- [Methodology and interpretation](docs/METHODOLOGY.md)
- [Backup operation](docs/BACKUP.md)

Run the lightweight repository checks without using the GPU:

```sh
python3 -m unittest discover -s tests -v
```

Model weights, credentials, agent authentication/settings, production configuration, and native SQLite state are excluded. They are not needed to read results or reuse test definitions. Local full-state backups remain separate. No license is granted to third-party runtimes or model weights by this repository.
