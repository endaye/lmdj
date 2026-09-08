# O1 C2 manual cancellation diagnostic wiring

Status: local implementation Task; actual GitHub cancellation remains unverified.

## Boundary and files

This Task depends on the merged C2 adapter and adds only its manual entry and a
bounded diagnostic waiter. It does not switch automatic CI triggers or release
policy. Root separately owns the reviewed fixed claim-storage migration;
neither initialization nor cancellation is authorized by this implementation.
The isolated branch is `feat/ci-o1-cancel-probe-wiring`, based on actual merged
`e7fc6959134a434a95a5cbfc8e755ff9b18efede`; both the adapter and fixed claim-role
assignment are present. Root separately initialized that role; this Task does
not repeat initialization or infer a tested baseline from the empty checkpoint.

Declared files:

- `.github/workflows/self-test-report.yml`
- `scripts/ci/hosted_runner_policy.json`
- `tests/build/ci_o1_cancel_probe_workflow_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `tests/build/ci_o1_claim_probe_workflow_test.py`
- `tests/build/ci_self_test_report_workflow_test.py`
- this plan

The existing four-file execution source registry already includes
`self-test-report.yml`; no source path is added. The diagnostic waiter is not a
product job and is deliberately absent from product job/suite aliases. Its
hosted inventory entry records its control-plane purpose, not test coverage.

## Implementation

Add exclusive `cancel-probe`, using `journal_config` and `probe_request`. Reject
mixed scheduler, reporter and legacy inputs. Pass raw JSON through environment
and private files to the actual adapter CLI; do not interpolate JSON as code.
Use the existing exact-main/first-attempt controller and short writer lock.

Only a successful CLI invocation with a strictly closed ready record may emit
`diagnostic_ready=true`. Validate boolean type, exact schema/status, complete
identity keys, actual run/attempt/control, fixed claim issue/epoch, request ID
and journal digest. Disabled records emit no ready output; malformed, missing,
error, unknown-status or nonzero CLI results fail without readiness. No
action/request/executor output or controller artifact is produced by C2.

An independent hosted waiter requires controller success, the dedicated ready
output, manual operation, main and first attempt. It holds no writer lock,
checkout, secret/token environment, write permission, retry or `always()`.
It waits 285 seconds within a five-minute job budget, then fails naturally;
timeout is not cancellation success. It never runs a product command.

## Verification and acceptance legs

Lowest-tier tests execute the actual inline workflow Python and actual CLI
against real Runtime/journal fixtures, not an invented command interface.
They cover disabled/error/no-ready, successful durable claim then ready,
closed identity mutations and mixed inputs. Existing workflow contracts retain
scheduler/report/artifact exclusions and all original executor outputs.

Run targeted workflow and adapter tests, hosted inventory tests, full CI Python
discovery, actionlint, staged ownership and final docs_static checks. Run Portal
check honestly; missing dependencies are failures, not verification passes.

Remote acceptance remains a separate authorized journey: verify new storage and
exact main/run/attempt; verify durable full claim and waiter in progress with no
product jobs; root separately authorizes ordinary cancellation of only that
parent run; observe actual terminal `cancelled`; ordinary fresh settlement must
record all 16 missing suites/debts without invented product failures; replay
must preserve the whole state. Local fixture cancellation is not GitHub
cancellation, and a natural timeout is an unexercised cancellation leg.

No force cancellation, runner permission changes, workflow Actions-write grant,
production run cancellation, release operation or automatic retry is included.

## Version Management

Version impact: none
Reason: internal manual diagnostic entry, no versioned product or Contract change.

## Documentation Impact

Documentation impact: none
Reason: isolated pre-cutover acceptance tooling, not a change to current product
behavior, Portal routes, identities or the automatic CI policy.

## Verification results

The existing exact workflow inventory also needs the fourth diagnostic job;
the authorized seventh file changes only that list, retaining all legacy
reporter and spending-policy assertions. The shared writer-lock count is five
mutually exclusive controller steps, not five concurrent writers.

Local results: 10 C2 workflow tests, 19 runtime workflow tests, 9 C1 workflow
tests, 7 A/B workflow tests and 6 hosted inventory tests passed. Complete CI
Python discovery passed 1,539 tests with no skips. Actionlint 1.7.12 passed
with only the already unsupported `queue` concurrency key compatibility
exemption. Staged ownership passed all 66 tests; the seven declared files and
staged whitespace check passed. The initial complete run correctly rejected
the stale three-job inventory; the final run includes the explicit fourth job.

Portal check actually ran 57 tests: 54 passed, and three failed because `glob`,
`gray-matter` and `cheerio` are unavailable in the isolated worktree. Subsequent
Portal stages did not run. Final committed-range classification/docs_static are
verified before shipping, not inferred from an empty pre-commit range. This
plan does not certify remote C2 or O2.
