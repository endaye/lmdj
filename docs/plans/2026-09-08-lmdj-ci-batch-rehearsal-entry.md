# Manual incremental rehearsal entry

Manual entry implemented on the merged real batch runtime CLI and reusable
Core CI executor. This document does not record a successful remote rehearsal.

## Declared files

- `.github/workflows/self-test-report.yml`
- `tests/build/ci_self_test_report_workflow_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `scripts/ci/hosted_runner_policy.json`
- This plan.

## Boundary

Add explicit manual init/reconcile/settle operations to the existing reporter's
permission boundary. No new permission: the controller inherits the same
contents/actions read and issues write grant already used by the reporter.
Product execution receives only contents/actions read and the existing explicit
runner-read secret, never broad secret inheritance or issue authority.

The shared writer lock moves from workflow to the two short writer jobs. The
reusable product job never owns it. Controller code checks out exact GITHUB_SHA
with complete history; runtime independently proves main/control/run identity.
An isolated journal's exact configuration is an explicit input. Initialization
never creates an Issue or claims an already-tested/healthy baseline. Settle
cannot admit or execute, including recovery of a previous incomplete claim.

The existing Core CI completion subscription, daily product sweep, daily
missing-batch alert and legacy manual report remain unchanged for this Task.
There is no push or automatic incremental completion/tick trigger yet. Operators
explicitly reconcile or settle the isolated journal during O1. T5 owns the
simultaneous trigger and current documentation cutover after O1 passes.

## Verification

Test writer-lock ownership, exact trusted checkout, manual-only admission,
settle non-execution, runtime CLI argument preservation and one-use execute
output passed unchanged to the local reusable workflow. Run complete CI
contracts, ownership after staging, and pinned actionlint with only the existing
queue-key compatibility exemption after both prerequisites merge.

On runtime merge `2f9ce089ecf664aedd58a22a79142df50b829ff2`, complete CI
discovery passed 1297 tests with no skips. The ten new workflow tests include
passing actual request/executor outputs through the real execution adapter;
the subprocess runtime remains a fixture and proves no GitHub side effects.
Pinned actionlint 1.7.12 passed with only its existing unsupported concurrency
queue-key syntax exemption. `scripts/architecture-portal.sh check` was attempted:
54 tests passed and three failed because this isolated worktree lacks `glob`
and `cheerio` dependencies; no Portal pass or build is claimed. This Task does
not change Portal files. Staged ownership is verified separately before commit.

Actual platform permissions, reusable caller context/job names, initialization,
none/focused/full, coalescing, terminal recovery and report replay remain O1
acceptance gaps. Local workflow contracts do not discharge those journeys.

## Documentation Impact

Documentation impact: none

Reason: Isolated explicit rehearsal only; current automatic product testing and
Portal operational facts are unchanged. T5 updates the current Portal routes.

## Version Management

Version impact: none

Reason: No Product Build, tag, release, deployment or Channel operation.

Pitfall impact: none pending final review; existing short-lock and synthetic
platform evidence guidance applied.
