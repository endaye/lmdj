# Reconcile wakeups before the approved first version baseline

## Scope and declared files

Follow the approved baseline adoption with a narrow historical-wakeup policy.
An authenticated successful auto/bootstrap result strictly before the adopted
first version baseline becomes a durable `historical` observation, not an
ignored source, a delivery plan or progress. Retain its complete source and
the complete adopted receipt. Prove both revisions on the observed main
first-parent chain and retain existing verdict authentication before deciding.
Only the initial adopted version pointer with null site/formal progress is
eligible; arbitrary or later progress does not authorize historical disposal.
The baseline target itself still plans normally with an empty version interval
and full first-site bootstrap floor. Failed/missing/no-test and explicit
candidate results keep their existing non-planning semantics.

Declared files:

- `tools/canary/planning.py`
- `tools/canary/planning_journal.py`
- `tools/canary/planning_entry.py`
- `tests/build/ci_canary_planning_entry_test.py`
- `tests/build/ci_canary_planning_journal_test.py`
- this plan and `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

The bounded discovery entry persists one complete observation at a time; it
never rewinds or resets the scheduler. Historical observations occupy neither
active nor pending. Uncertain writes must finish their frozen intent before
discovery proceeds. Changed receipt/progress/source and malformed evidence
remain fail-closed, not reasons to skip a record. No automatic readiness,
workflow, live journal, infrastructure, version, release or deployment changes.

## Verification

Lowest tier: real temporary Git plus actual authenticated Runtime/Journal HTTP
fixtures. First reproduce the pre-baseline discovery failure. Then exercise
adopt → historical observation → fresh OS-process recovery → next result plan
→ idle, with far-side complete source/receipt, progress and scheduler byte
assertions. Preserve failure/debt, all site bootstrap floors and all version
interval commits. Inject unknown intent/blob/complete outcomes and restore the
original observation without duplicate POST. Test baseline equality, absent or
altered receipt, changed progress, corrupt historical verdict and slot safety.
Fixtures do not prove actual Actions permissions, remote scheduling, storage
activation, deployment or provider execution.

Run planning and complete canary discovery, CI-contract discovery, staged new
file ownership, Portal check and version verification. Record any inherited
failure without lowering a floor or suppressing a test. Ship through
`issue-done` with exact-head review; no new required merge gate.

## Local evidence

- The new historical entry regression first failed in the existing reverse
  version interval collector, before implementation.
- Complete canary discovery: 319 tests pass, including actual CLI/new-process
  discovery/recovery and unchanged scheduler failure/debt bytes.
- Complete CI-contract discovery: 2,224 tests, one inherited ledger failure:
  `snapshot-page-pin-only-fires-at-freeze.md` declares unknown `area: docs`.
  [Issue #1078](https://github.com/endaye/lmdj/issues/1078) retains that defect;
  the entry and validator match this Task's main baseline. This is not full-CI
  green. Pinned actionlint 1.7.12 was supplied to the YAML semantic regression,
  without an optional-parser skip; no workflow or shell step is changed.
- Staged ownership: all 66 tests pass, including the new plan's exact tracked
  inventory. Product version tests and active version verification pass.
- Portal: locked clean install, 114 tests, production build and all 44 routes
  and internal links pass. Only this worktree's six pristine flattened symbolic
  links were restored using command-local Git configuration, following the
  existing worktree pitfall; no shared setting or tracked link changed.

No new pitfall: the new policy is guarded by direct Runtime/Journal regressions;
the inherited ledger defect remains with its existing Issue. No live API write,
backlog reconciliation, automatic activation or delivery evidence is claimed.

## Version Management

Version impact: none

Reason: internal planning reconciliation only; no active identity or allocation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/testing-and-proof/

Reason: document historical observation and recovery semantics and the remaining
automatic activation boundary. No architectural source diagram changes.
