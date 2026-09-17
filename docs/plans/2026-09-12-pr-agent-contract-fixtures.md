# PR-Agent cutover CI contract fixture repairs

## Defect and scope

PR #1241 CI Contract run 34630800512 exposed three independent fixture/ledger
defects: a recurrence recorded in local time instead of the run's UTC date,
an absorbed historical pitfall pointing at a retired Grok CLI test, and a
real-Git input fixture assuming the machine defaults to an initial `main`
branch. Its Contabo runner defaults to `master`.

Use the occurrence's UTC date, point the historical exit at the active test
that prevents the retired review route returning, and explicitly initialize
the real-Git fixture's branch. Preserve the historical failed run. Do not
change product behavior, lane selection, gates, providers, or budgets.

## Declared files

- `tests/build/ci_pr_agent_input_test.py`
- `.agents/pitfalls/runner-account-check-misses-service-mounts.md`
- `.agents/pitfalls/grok-strict-sandbox-github-hosted-socket.md`
- `docs/plans/2026-09-12-pr-agent-contract-fixtures.md`

## Verification

Reproduce the original ledger failures with `ci_pitfall_ledger_test.py` and
the real-Git checkout failure with `ci_pr_agent_input_test.py` while supplying
`init.defaultBranch=master` through Git's process-local config environment.
After repair, run the ledger test and the complete input tests with both
`master` and `main` defaults. Run `ci_pr_review_workflow_test.py` to verify the
replacement exit mechanism and `ci_change_scope_test.py` for lane ownership.
No test, threshold, or gate is removed. Obtain independent current-head review
and inspect the new PR's CI Contract result; local fixture checks alone do not
retroactively turn the old failed run green.

## Documentation impact

Documentation impact: none — test setup and internal historical pitfall
references only; no portal-facing behavior or documented product fact changes.

## Version Management

Version impact: none — CI fixture and ledger metadata corrections only; no
Product Build, module, provider, host, or Contract identity change.
