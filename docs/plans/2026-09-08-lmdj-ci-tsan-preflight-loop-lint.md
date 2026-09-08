# TSan preflight loop diagnostic and lint repair

## Task and declared files

One narrow CI Task on `fix/ci-tsan-preflight-loop-lint`, based on
`e41daeab` (including the newer main scope-policy and governance changes).

- `.github/workflows/core-nightly.yml`
- `tests/build/ci_nightly_workflow_test.py`
- `.agents/pitfalls/optional-linter-dependency-silently-absent.md`
- `docs/plans/2026-09-08-lmdj-ci-tsan-preflight-loop-lint.md`

## Actual failure and repair

Run [34175405275, job 101904005023](https://github.com/endaye/lmdj/actions/runs/34175405275/job/101904005023)
checked out exact `fe043fd3a2a06dfbca4088cc59e0e8ef6997f336`.
At 01:06:22 UTC on 2026-09-08 its checksum-verified actionlint 1.7.12
failed before the Python contract suite: ShellCheck reported SC2034 for the
unused `attempt` variable in `core-nightly.yml`'s TSan prerequisite loop.
This was not a failed Python test or evidence of a TSan runtime failure.

Print the actual startup index immediately before each mandatory start. Keep
all ten starts, each 10-second timeout, compiler flags, runner, permissions,
infrastructure output and first-failure exit unchanged. Do not disable lint,
retry a failing start, classify this historical CI failure as a pass, or cancel
and restart the running batch.

## Verification

Lowest-tier behavioral tests execute the actual extracted shell preflight with
the existing strict compiler/probe fixture. The new regression covers successful
starts 1–10, first-start failure and tenth-start failure; the far side checks
the exact logged sequence, actual start count, infrastructure flag and whether
the build boundary was reached. This does not prove the real host can run TSan.

- Baseline nightly workflow tests: 15 passed.
- Before the fix, the new regression failed all three subcases with no startup
  sequence, and actual actionlint with ShellCheck enabled reproduced SC2034.
- After the fix: all 16 nightly workflow tests passed, including all three
  new sequence subcases and the existing shell-output-to-verdict debt journey.
- Full repository actionlint 1.7.12 with explicit ShellCheck 0.9.0: passed.
- `LMDJ_ACTIONLINT=/tmp/lmdj-t2-shipping.MTX7q1/actionlint python3 -m unittest
  discover -s tests/build -p 'ci_*test.py'`: 1658 tests passed in 40.647 seconds,
  no skips. This Python command remains distinct from the full lint invocation.
- Staged `python3 tests/build/ci_change_scope_test.py`: 66 passed.
- Full lint command: `/tmp/lmdj-t2-shipping.MTX7q1/actionlint
  -shellcheck=/tmp/lmdj-shellcheck-lint.cxa20X/extracted/usr/bin/shellcheck
  -ignore 'unexpected key "queue" for "concurrency" section'`.

The earlier local 1657-test Python run did not cover this lint failure. Local
ShellCheck was absent, and the PR-review semantic-parser regression explicitly
disables shell checking. For this Task, Ubuntu package `shellcheck=0.9.0-1`
was downloaded and extracted into an isolated temporary directory; actionlint
is invoked with its explicit executable path, not optional PATH discovery.
Only the existing exact `concurrency.queue` parser-compatibility exception is
used. No new warning suppression, project dependency or lockfile change.

## Version Management

Version impact: none — the change is CI diagnostics only; no Product, Module,
Provider, Host or Contract identity changes.

## Documentation Impact

Documentation impact: none — no portal page, diagram, tooling, projected
identity or documented product source fact changes. Portal verification is not
required by the current Task-scoped policy; this is not a portal PASS claim.

## Pitfall Impact

Pitfall impact: new `optional-linter-dependency-silently-absent` — first observed
tool-availability mismatch, open with no general enforcement mechanism. The
source defect itself is covered by the regression; this Task does not expand
into redesigning every local lint entry point.

## Delivery boundaries

Commit, push and PR are authorized. Root reviews the exact head and handles
merge. No product tests, remote dispatch, cancellation, Issue mutation, cleanup,
release or deployment belongs to this Task. Live CI execution after merge remains
unverified until a later ordinary batch actually reaches this workflow.
