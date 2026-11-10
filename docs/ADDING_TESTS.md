# Add tests without changing old comparisons

1. Copy `benchmarks/suites/h4` into a new version directory, such as `h5`. Never edit an already measured suite in place.
2. Add the task contract, starter files, reference implementation and fixed input/output driver to the new `catalog.py`. Use a unique task ID and the correct language. State API behavior, malformed-input rules, concurrency semantics, dependencies and resource limits explicitly.
3. Add deterministic public and private cases in the new `cases.py`. Cover boundary cases and regressions with an external oracle. Avoid deriving expected answers from the candidate implementation. Private seeds and cases remain on the operator side.
4. Demonstrate that a known-good implementation passes and deliberately broken implementations fail. Include relevant ASan/UBSan and separate TSan checks for C++. Test harness transport/permission failures separately from code correctness.
5. Update the new suite's revision constant and generate a new `MANIFEST.json` with its name, provenance and SHA-256 for `catalog.py`, `cases.py`, and `common.py`. Set each hash from the exact file bytes. Commit the suite before running candidates. `python3 -m benchmarks.run --suite h5 verify` must pass.
6. Add tests in `tests/` for the new fixture generation and regression behavior. Update the sampling/task plan under `configs/` and record compiler/interpreter/runtime versions. Use fresh candidate workspaces and output directories.

The CLI discovers task definitions from the selected suite. Adding a family to the archived OpenRig campaign matrix also requires an explicit operator-side scheduling and module-integration update; it is not enough to add an extra agent to a rig file. Keep new controller versions outside production and qualify them before scoring.

Use three seeds for repeated comparisons and retain failures, timeouts and interrupted work. Report per-family and per-language results. A smaller two-task model screen is not equivalent to the full six-family, three-seed track.
