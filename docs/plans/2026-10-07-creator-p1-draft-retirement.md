# Retire the superseded P1 integration draft

## Task

PR #1741 remains a conflicting draft at
`281ec612af78d17bd295bed1696892d258e5c272`. Its product-source paths have
successors on main: #1722, #1731, #1732, #1737, #1738, #1739 and #1740;
#1848 integrates the Build 87 software delivery. Retire this draft after
preserving its remaining operational knowledge, rather than merging the old
integration tree into the current product.

Declared files:

- `.agents/pitfalls/background-proof-inherits-ignored-signals.md`
- `.agents/pitfalls/playwright-evaluation-grants-user-activation.md`
- `.agents/pitfalls/review-archive-exceeds-authentication-budget.md`
- `docs/plans/2026-10-07-creator-p1-draft-retirement.md`

Restore both entries from the draft, preserving their historical content and
observer attribution; normalize the Playwright area to the current `creator`
label namespace (`creator-web` is not a repository label). The Playwright
entry repairs the existing Capture/System plan references and points to the
current packaged cold-touch test. Deduplicate the archive-budget occurrence
into the existing entry, retain original dates and observer attribution, and
point its absorbed status at the already-landed #1825 mechanism. No new failure
is claimed by recovering historical evidence.

## Verification

Run `python3 tests/build/ci_pitfall_ledger_test.py` and the focused
`ci_review_wait_test.py` archive-budget/current-inventory cases plus
`ci_pr_review_workflow_test.py` separate-diagnostics case. Inspect the current
cold-touch test's enforcing assertions and verify both existing plan references
resolve. After staging the new files, run
`python3 tests/build/ci_change_scope_test.py` to verify tracked ownership.
Validate the PR body with `ci_pr_body_lint.py`, declaration-only and exact-head
batch-evidence checks. Obtain authenticated current-head independent review,
inspect live conversations/protection, and squash-merge with a head guard.

## Retirement boundary

After this Task merges, explain the successor PRs and recovered records in
#1741 and close it as superseded. Preserve its branch, remote worktree and Git
history: historical plans and Build 77 snapshots differ from current main, so
full patch retention is not established. Keep physical acceptance follow-ups
#1851–#1854 open. This Task performs no release or deployment.

## Version Management

Version impact: none
Reason: only historical process knowledge and retirement planning change; no
Product, Module, Host, Provider or Contract identity changes.

## Documentation Impact

Documentation impact: none
Reason: the Task changes the pitfall ledger and a historical plan, without
changing Architecture Portal pages, source facts or projected identities.

## Pitfall Impact

Restore two historical entries and deduplicate one historical recurrence into
`review-archive-exceeds-authentication-budget`. The enforcing mechanisms already
exist; no new gate or product test is introduced.
