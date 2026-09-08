# T4d — Fixed-target execution adapter

Status: internal adapter, not a workflow cutover. Depends on merged T1/T3/T4a.

## Declared Files

- `scripts/ci/batch_execution.py`
- `tests/build/ci_batch_execution_test.py`
- This plan.

## Behavior

Translate an authenticated frozen scheduler request and its admitted executor
into fixed-target suite/lane outputs. Independently check actual checkout,
run/attempt, complete Git ancestry and interval. This does not authenticate a
journal or admit a request: the controller must persist admission and claim
before exposing its request to the test DAG. Recovery bookkeeping claims must
never call the execution path.

Every target and main identity must be a commit object, not a tag object that
Git ancestry commands silently peel. Real temporary-repository regressions for
explicit candidate and main tag objects failed before the object-type check.
These local fixture tags are not repository release operations.

Convert the final DAG needs context to selected-only observations using the
unchanged complete self-test inventory, then the new batch verdict protocol.
Unselected skips are omitted, not credited; unexpected executed unselected
product jobs are rejected. Missing selected jobs retain debt. Workflow job
aliases and dependencies are explicit trusted adapter inputs, not model data.

The CLI reads closed JSON and writes compact outputs; it does not dispatch,
write GitHub, change triggers or generate old full-release evidence.

## Verification

Lowest tier: Python adapter tests and real temporary Git repositories.

- `python3 tests/build/ci_batch_execution_test.py`
- `python3 tests/build/ci_batch_verdict_test.py`
- `python3 tests/build/ci_incremental_batch_test.py`
- `python3 tests/build/ci_test_scope_test.py`
- staged `python3 tests/build/ci_change_scope_test.py`
- `git diff --cached --check`

Tests cover exact checkout/executor, full history and first-parent intervals,
missing selected results, unselected execution, needs aliases and CLI artifacts.
Actual GitHub DAG scheduling, artifact provenance and the single writer lock
remain integration/O1 acceptance gaps, not passes claimed by local tests.

## Documentation Impact

Documentation impact: none
Reason: unused internal adapter and Task record only; no current Portal behavior
or projected identity changes. Workflow cutover owns its required Portal update.

## Version Management

Version impact: none
Reason: internal CI schema only; no Product Build, release or deployment action.

Pitfall impact: none — existing identity, ownership and journey guidance applied;
no new process incident is claimed by planned adapter tests.
