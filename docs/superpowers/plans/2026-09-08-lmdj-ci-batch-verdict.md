# T4a — Scoped Batch Verdict Protocol

Status: pure local protocol only; no workflow trigger, reporter or release
consumer changes. Depends on T1's current `ScopePolicy` and selection schema.

## Declared Files

- `scripts/ci/batch_verdict.py`
- `tests/build/ci_batch_verdict_test.py`
- This plan.

## Protocol

`build(policy, identity, selection, observations)` returns new-schema evidence.
`validate(document, policy, expected_identity, expected_selection)` reconstructs
the whole result from retained original observations and trusted inputs.
`scheduler_outcomes(document, policy, expected_identity, expected_selection)`
validates first, then returns only selected suite outcomes for T3.

Identity binds request ID/kind, base/target/control SHA, T1 policy digest and the
admitted executor run/attempt, not the possibly older request-submission run.
An auto request must have a baseline; bootstrap/node/candidate may omit one but
require full selection. Every attempt is exactly 1. Caller verifies actual run
identity, trusted control and terminal status independently; neither matching
hashes nor internally consistent observations provide authentication.

Reuse `self_test.aggregate` with the complete unchanged inventory to classify
observed jobs, including canonical macOS alternatives. If no observations exist,
use its same per-suite judge with an empty job map: selected jobs are genuinely
missing, never fake successes. Every report still enumerates all 16 suites;
unselected suites are `not-selected`, not pass. None is `not-required` and has
no scheduler outcomes. Wrong run/target/attempt, unknown jobs/suites, duplicate
jobs and ill-typed fields reject with why/remedy diagnostics. The input adapter
passes selected-suite observations only, never unselected job skips.

Within a suite, test failure and unexecuted jobs can coexist. Preserve both a
real `failures` job list and `verification_debt`; the scheduler projection gives
debt precedence (infrastructure/cancelled/missing/blocked), while reporting keeps
the actual failure. Do not infer issue closure from a later pass. A successful
fallback with failed evidence upload is not a reusable pass. Original observation
documents remain in the new verdict for deterministic consumer replay.

This schema is deliberately distinct from complete self-test v1, even for a
full selection. Existing complete/candidate consumers must reject it. This Task
does not enable a new source of release authority; manual full evidence remains
on the existing independently authenticated path.

## Verification

Run `python3 tests/build/ci_batch_verdict_test.py`, the existing self-test and
scope suites, then staged `ci_change_scope_test.py` ownership verification.
No new required check or threshold change is introduced.

Tests cover typed observations, exact identity/scope, full inventory and stress,
macOS alternatives, missing/blocked/cancelled/infra debt, mixed failure+missing,
none/not-selected, semantic replay after tampering+rehashing, and rejection by
the unchanged complete evidence validator. These are protocol tests, not proof
that any real platform jobs ran. T4b/O1 must connect actual needs/API projections,
result journal persistence, failure reporting and candidate isolation; no remote
acceptance leg is claimed by this Task.

## Documentation Impact

Documentation impact: none — unwired internal evidence protocol; no Portal
page, current behavior or projected source identity changes.

## Version Management

Version impact: none — internal CI schema only; no product/module/host/provider
or product Contract version and no publication action.

Pitfall impact: none — prior ledger guidance retained; planned protocol fault
tests are not production incident recurrences.
