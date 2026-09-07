# Optimistic merge workflow cutover (T5a)

Status: local preparation only. This diff does not authorize remote activation.
Design authority: `../specs/2026-09-07-lmdj-ci-capacity-redesign.md`.
Coordination authority: `2026-09-07-lmdj-ci-capacity-redesign.md`, T5a/O1/O2.

## Task boundary

One Conventional Commit: `feat(ci): separate optimistic PR merges from self-tests`.
Branch: `feat/ci-optimistic-merge-cutover`, isolated worktree from `origin/main`.
Preparation is temporarily stacked on T4 head
`f27f7e3d3b24e8ee19cea48eb0ef1a5cb1f7d4af` (PR #764); its implementation is
inherited, not copied into T5a. After T4 merges, rebase only the T5a change onto
the new canonical main. The pre-stack staged/unstaged backup is retained as
stash `402094ee30ea6c7b6fc4e9bfc09638a0dc94c211` until the owner accepts cleanup.

Declared files:

- `.github/workflows/ci.yml`
- `.github/workflows/core-nightly.yml`
- `.github/workflows/merge-queue.yml`
- `.github/workflows/advisory-review-liveness.yml`
- `.github/workflows/pr-review.yml` (T4 implementation inherited from the stack base)
- `tests/build/ci_self_test_workflow_test.py`
- `tests/build/ci_workflow_topology_test.py`
- `tests/build/ci_merge_queue_workflow_test.py`
- `tests/build/ci_claude_review_workflow_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `scripts/ci/self_test_history.py` (existing `scripts/ci/` full rule)
- `tests/build/ci_self_test_history_test.py` (existing `tests/build/ci_` rule)
- this plan

## Implementation

Core CI no longer subscribes to PR or ordinary main push events. Daily 16:00
UTC and empty manual dispatch select the existing complete 16-suite policy,
including same-batch TSan and Release stress. The event SHA is immutable even
when the event waits and main moves; a manual request may select another exact
main-history target. Both control and target remain verified against main.

Each run has independent admission, so a delayed older event cannot replace a
newer pending target, and an explicit node/candidate request cannot be replaced
by a routine schedule. Native-heavy locks and their finite platform queue limit
remain unchanged. This deliberately retains all admitted routine requests
rather than implementing lossy latest-pending coalescing. A complete trusted
same-target/same-policy conclusion permits only routine schedule deduplication;
the lookup examines up to 20 completed runs for each supported event. An absent,
expired, untrusted or unreadable record runs tests rather than claiming a skip.
The read has a 90-second wall budget. Simultaneously admitted same-target runs
may both resolve before either has a complete verdict; this first cutover does
not claim global in-flight deduplication. It preserves explicit requests and
honest evidence, while the existing native-heavy queue bounds execution.
an explicit request always obtains a new observation. No inherited rerun jobs
are accepted: request a new dispatch with the same target.

The independent PR Review entry takes over automatic reviews in the same diff
that disables the old entry. Its manual-rollout variable gate is removed in
code, so activation requires no separate repository-variable mutation. The old
queue stops accepting labels or watchdog
ticks; its remaining manual entry reports retirement and authorizes nothing.
Already running old-revision workers are not stopped by editing YAML: O2 must
inventory and individually resolve those tickets. Nightly's duplicate 19:00
UTC cron and the legacy 21:00 review-liveness cron are retired; reusable stress
jobs and manual diagnostics remain. Existing real scope/gate jobs used by the
old release consumer remain; there are no fake successful required contexts.

## Verification

- Full `ci_*_test.py` contracts; updated event/admission assertions, actual
  resolver shell execution, complete policy/job mapping and target checkouts.
- Release CI evidence regression; T7 independently owns new release consumption.
- Pinned actionlint with only the existing exact `concurrency.queue` exception.
- Staged ownership check and `git diff --cached --check`.
- `scripts/architecture-portal.sh check`, serialized with other portal builds.

Mock API and shell tests cannot prove GitHub scheduling, checkout, artifact
retention or Issue side effects. O1 real fixed-target batch/report/review
journeys remain required; no local result checks those boxes.

Local stack verification: `python3 -S -m unittest discover -s tests/build -p
'ci_*_test.py'` passed 855 tests; staged ownership passed 66 tests and pinned
actionlint passed with only the existing exact queue-schema exception. Portal
verification is deliberately pending while T5b owns the shared build resource;
no final T5a commit or remote cutover is claimed.

## O2 activation runbook

This is a runbook, not evidence O2 ran. At the root agent's read-only
observation, protection still required `core (ubuntu-latest)`,
`core (macos-latest)` and `PR Gate`, each from Actions App ID `15368`, with
`strict: true`; rulesets were empty. Re-read at the actual window: these are
not timeless configuration claims.

1. Root verifies O1 acceptance, T7 candidate readiness, T5b readiness, a bounded
   window and rollback owner; inventory every old ticket and live protection.
2. Obtain the independent O2 protection authorization. Back up rules/protection;
   stop old admission and individually hand off or finish existing tickets.
3. Verify legacy required Core/PR Gate contexts removed and strict disabled,
   retaining PR/conflict/conversation protections. Do not synthesize green jobs.
4. Root ships T5a then T5b inside that same window. Confirm only PR Review
   responds to new PR heads and ordinary main pushes do not launch Core CI.
5. Verify the next admitted self-test and independent reporter identities.
   If the paired cutover cannot complete, restore the recorded prior protection
   and workflow configuration; never leave an unattended partial cutover.

### Minimal protection patch and exact rollback

Before mutation, retain timestamped raw responses for `branches/main/protection`,
`branches/main/protection/required_status_checks`, and `rulesets`. Record the
current main and both cutover PR heads. Preserve the original required-check
payload fields `strict`, `contexts`, and `checks` (including every `app_id`)
as the exact rollback payload; do not reconstruct them from job display names.

The only authorized status-check delta is equivalent to this projection of
that fresh payload:

```jq
def retired: . == "core (ubuntu-latest)" or
             . == "core (macos-latest)" or . == "PR Gate";
{strict: false,
 contexts: [.contexts[] | select(retired | not)],
 checks: [.checks[] | select(.context | retired | not)]}
```

Check both representations agree before applying it. If any named context has
an unexpected App ID, the two representations disagree, a new ruleset applies,
or any unrelated protection drifted, stop and reconcile rather than guessing.
Apply only through `PATCH /repos/endaye/lmdj/branches/main/protection/required_status_checks`;
do not replace the entire branch protection object. Immediately re-read and
compare the three-field result to the intended payload; all other protection
fields must equal the backup. In particular, PR and conversation requirements
and admin-enforcement settings are not part of this change.

Rollback uses that same endpoint with the retained exact original three-field
payload, followed by a fresh equality check of `strict`, `contexts` and each
`checks` context/App ID pair, plus confirmation unrelated protections remain
unchanged. If workflow rollback is also necessary, restore the recorded prior
workflow revision through the separately authorized reviewable revert; do not
claim restored contexts alone make retired PR jobs run again. A failed API
read/write is an unresolved operation, never success or resource absence.

### Existing work inventory and stop conditions

At the earlier read-only observation, queue run `34124685951` was in progress
and `34125278624` pending, although no open PR remained: these were tails of
PRs the user had manually merged. Their status must be refreshed in the window.
Do not infer new authorization from an old pending run or an extant label.
Record for each live item its run/attempt, original authorized head, live PR
state, ticket and owner-selected disposition (finish, stop, or manual handoff).
Record old Core CI/Nightly runs separately; editing a trigger does not cancel
an already created run, and a current run retains its original workflow code.

Stop before protection mutation on missing O1/T7 evidence, an unresolved ticket,
missing paired T5b readiness, or uncertain rollback ownership. After mutation,
stop and invoke the agreed rollback if T5a then T5b cannot land in the agreed
window, either head changes without re-verification, new PRs still trigger
product full tests, the independent review is not active, or verification reads
fail. No unattended overnight mixed state is an acceptable completion.

No step here authorizes releases, host mutations, workflow dispatches or
cancelling another operator's run. The implementation agent makes no remote writes.

## Version Management

Version impact: none — CI routing changes no Product, Module, Provider or Contract identity.

## Documentation impact

Documentation impact: none — T5b owns the current portal/governance changes in
the same O2 window. T5a must not remain on main overnight without T5b.

Pitfall impact: none — timing and pending replacement constraints are explicitly
tested and recorded here; no new external platform failure is asserted.

Platform basis: GitHub documents a single-pending default, a finite 100-pending
`queue: max`, and ordering by actual wait time rather than dispatch time in
[concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
The design therefore does not infer target freshness from queue order. The
[schedule event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
also warns schedules may be delayed or dropped; the independent reporter can
detect a missing batch only when Actions itself executes the reporter.
