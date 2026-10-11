# Required check results before dependent operations

Task: [#2031](https://github.com/endaye/lmdj/issues/2031).
Integration base: `a5bc444be23edf4d4d14378e3ff60c3c8bf037fc`.
Branch: `docs/required-check-result-stop`, in an isolated worktree.

## Premise disposition

At the refreshed base, `issue-done` already requires staged inspection before
commit and body validation before PR creation. The declaration validator already
rejects a missing bare `Reason:` line. Those mechanisms exist and are retained.

The caller nevertheless continued after two actual required-check failures in
the K1 integration attempt on 2026-10-11 UTC: declaration check exit 1 at
22:53:18, precommit inspection exit 1 at 22:53:23, then local commit exit 0.
The recorder correctly propagates each child's return code. The calling shell's
literal argv and final outer exit were not retained; neither an outer success
nor a swallowed child failure is established. The failed inspection's original
stdin expression is also unavailable and is not reconstructed.

The author retained the preliminary local object, corrected the declaration and
inspection, and created a replacement commit. Both commits have the same tree.
The original negative and corrected receipts remain external evidence; this
Task does not amend the K1 24-file product cut or replace its verification.

The existing absorbed `documentation-impact-means-portal-pages` pitfall covers
the same declaration error and bypassed result. Its skill exit needs an explicit
reminder to read actual required-check terminal results before each dependent
operation. Its current body-check guidance also still suggests interrupting lane
execution instead of the existing declaration-only command. These two process
gaps remain outstanding. No product or concurrency decision is required.

## Declared files

- `.agents/pitfalls/documentation-impact-means-portal-pages.md`
- `.agents/skills/issue-done/SKILL.md`
- `docs/plans/2026-10-12-required-check-result-stop.md`

One Conventional Commit repairs the existing skill exit and records one real
recurrence in the same shipping cycle. This Task changes no product source,
validator, hook, lane selector, protection, test deadline or coverage floor.

## Implementation

1. Append the 2026-10-11 occurrence with the actual Issue URL and
   `observed_by: unknown`: this recorder reviewed the event but cannot self-report
   being its original author. Keep the entry absorbed with its existing exit.
2. In `issue-done` sections 3 and 4, require reading each required prerequisite's
   actual terminal exit before the dependent operation. Nonzero, signal or
   missing terminal status prevents that operation. Preserve advisory checks as
   advisory; do not create a universal new gate.
3. Align current pitfall guidance with `--declaration-only --pr-body` and the
   active docs-site path. Preserve the historical Why section and its old site
   names rather than rewriting earlier observations.

## Verification and acceptance

- `python3 tests/build/ci_pitfall_ledger_test.py`: validates recurrence metadata,
  date, URL and the existing skill exit; it does not prove agent compliance.
- After staging exactly the declared paths,
  `python3 tests/build/ci_change_scope_test.py`: checks the new plan's explicit
  ownership and top-level admission.
- Inspect the complete three-file diff, staged paths and
  `git diff --cached --check`; read each actual exit before committing.
- `python3 tests/build/ci_pr_body_lint.py --body-file BODY` and
  `scripts/local-ci.sh --declaration-only --pr-body BODY`: validate the exact
  reviewable PR body before its publication; no lane or Portal pass is implied.
- On the clean committed head, record the original complete canonical lane
  selection. Preserve every applicable obligation from the user's supplied
  AGENTS instructions; deferred complete checks remain explicitly unverified.
- Obtain independent current-head review, resolve findings and conversations,
  inspect live protection/conflicts and use expected-head squash protection.

Baseline and changed-check receipts are stored outside tracked source. Failed
checks remain recorded and prevent their dependent operations. Fixing a check
requires its actual successful rerun and any affected dependent verification.
No new test or mechanical gate is added for this agent-procedure change.

## Version Management

Version impact: none — only agent procedure, operational memory and a plan
change; no Product, Module, Host, Provider, Contract or Assembly identity changes.

## Documentation impact

Documentation impact: none
Reason: no Portal architecture, product behavior, source identity, tooling or
diagram changes. The current Portal's owner-review attestation reference remains
accurate; this Task changes neither its format nor its review boundary.

## Remaining boundaries

K1 product validation, other Desktop Final tasks, physical interaction and
hearing acceptance, version allocation and snapshots retain their separate
obligations. This Task starts no Release, deployment or cleanup.
