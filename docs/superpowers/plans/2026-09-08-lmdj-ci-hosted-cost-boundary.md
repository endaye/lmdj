# CI hosted cost boundary

## Objective and authority

Implement the Owner-approved cost audit remediation. Routine Linux testing and
control must use self-hosted infrastructure. The Owner explicitly permits paid
macOS fallback because the self-host is a MacBook that may go offline. Keep
busy-only queueing and never retry a published product failure on hosted Mac.
Commit, push, PR and merge are authorized. Budget changes, releases, publication,
new server purchases and moving deployment secrets to CI users are not.

## Task 1 — move routine control to the existing light pool

Declared files:

- `.github/actionlint.yaml`
- `.github/workflows/ci.yml`
- `.github/workflows/self-test-report.yml`
- `.github/workflows/incremental-completion.yml`
- `.github/workflows/release-audit.yml`
- `.github/workflows/merge-queue.yml`
- `scripts/ci/hosted_runner_policy.json`
- `tests/build/ci_hosted_runner_policy_test.py`
- `tests/build/ci_batch_execution_workflow_test.py`
- `tests/build/ci_runner_fallback_test.py`
- `tests/build/ci_self_test_workflow_test.py`
- `tests/build/ci_self_test_report_workflow_test.py`
- `tests/build/ci_o1_cancel_probe_workflow_test.py`
- `tests/build/ci_workflow_event_graph_test.py`
- `tests/build/ci_workflow_topology_test.py`
- `docs/quality/core-test-policy.md`
- this plan
- `.agents/pitfalls/hosted-allowlist-is-not-zero-cost.md`

Route control with literal existing Contabo general labels. Current read-only
inventory confirms online listeners there and native/web-heavy roles on Netcup.
This reuses a light pool; it does not claim a dedicated reserved control runner.
No change to authentication, scope, durable progress, writer locks, permissions,
test tiers, artifact retention or macOS routing decisions. Remove obsolete
hosted exceptions and add an independent invariant so merely re-adding an
allowlist entry cannot allow routine paid Linux. Keep privileged release/deploy
and the disabled untrusted Preview pilot outside this migration.

Persistent-checkout compatibility: after Actions checkout removes the temporary
`.batch-policy` directory, reuse its missing worktree registration with one
`worktree add --force`, scoped to that exact path. Never prune other worktrees or
override a locked registration. Exercise the real workflow script across two
checkout-clean cycles, including frozen revision identity and lock protection.

Verification: focused routing, hosted-policy, self-test workflow and report
workflow suites; complete `ci_*_test.py` contract discovery; ownership after
staging; actionlint; `scripts/architecture-portal.sh check`; exact-head review.
Remote acceptance: after merge, observe actual controller/relay/audit jobs on
Contabo, and preserve any unobserved leg as a gap. Do not force paid Mac work or
take the MacBook offline just to test fallback; existing selector/failure
contracts cover offline, busy and published failure branches locally. No claim
that billing has recovered until an actual job executes; no promise that an
existing old-revision run changes runner when this PR merges.

## Task 2 — coalesce notifications without dropping evidence

Separate reviewable follow-up, with exact files declared before implementation.
Remove needless PR Review wakeups when authenticated evidence remains discoverable
from main; relay only real product completions, retaining journal recovery and
exact-run authentication. Consider admission-time event predicates before using
cancel-in-progress: cancelling a writer can lose required completion/report
work. Preserve complete commit interval union and terminal/report recovery.
The recovery tick is not a daily product-test schedule; keep a free recovery
path until a replacement is proven rather than removing recovery for savings.

## Acceptance boundaries

Routing tests do not prove live runner availability, account eligibility,
historical invoice refunds or all-hosts-down recovery. Account spending is
checked against future official usage; the latest CSV is historical evidence.
Global zero billing is not an acceptance claim with permitted macOS recovery
and privileged hosted operations. Never increase the budget to make evidence
green, and never clear journal or verification debt as a migration shortcut.

## Version Management

Version impact: none
Reason: CI topology and policy only; no Product, Module, Host or Contract identity.

## Documentation Impact

Documentation impact: none
Reason: quality/governance documentation changes only, no Architecture Portal
pages or product identities change.
