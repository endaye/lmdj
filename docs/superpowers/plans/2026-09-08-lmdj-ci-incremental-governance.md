# Incremental CI governance alignment

Date: 2026-09-08
Baseline: `16e822775d6357861ba37e5a93314ab8995e5d61`.
Status: local governance preparation; no automatic T5 trigger activation.

## Task and declared files

One documentation Task aligns current instructions with the approved
[incremental batch design](../specs/2026-09-08-lmdj-ci-incremental-batches.md)
without implying that its automatic entrypoints are already enabled.

Exactly eight files:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/governance/git-workflow.md`
- `docs/governance/github-work-management.md`
- `docs/quality/core-test-policy.md`
- `.agents/skills/issue-done/SKILL.md`
- `.agents/skills/issue-list/SKILL.md`
- `docs/superpowers/plans/2026-09-08-lmdj-ci-incremental-governance.md`

No workflow, runtime, release skill, version policy, release-pipeline spec,
Portal release/testing page or historical document is modified. Portal and
automatic trigger cutover remain separately owned T5 work. No remote write,
dispatch, cancellation, initialization or release belongs to this Task.

## Behavior and boundaries

Separate already-current PR review/conflict/conversation protection from the
pending incremental automatic trigger switch. Remove the old daily product-test
requirement, not real verification obligations. Preserve the actual legacy
reporter's scan/retention and daily-missing behavior as explicitly transitional
facts until its trigger is retired in the authorized window.

The target selects the complete first-parent interval and conservative
floor union authenticated review scope union eligible debt, including consumers
and rename/delete/revert. None is narrowly safe explanatory documentation, not
all Markdown. Coalesce new main changes without cancelling active work; persist
request/claim and result before progress. Keep progress, health, failed tests
and unexecuted debt distinct. Preserve bounded recovery and honest missing
evidence, current writer permissions and durable outbox unknown-write handling.

Manual exact-candidate full stays separate from focused/none and from release
authorization. Retain the authoritative sixteen-suite inventory, all platform
and stress coverage, floors, timing budgets, native capacity locks and historical
incident facts. No assertion or product test is weakened.

Skill-creator is used only for narrow edits of the two existing skills and
their quick validation; no new generic workflow, resources or permissions.
Issue-done and issue-list authority boundaries remain unchanged.

## Verification

Lowest-tier existing regressions:

- `ci_issue_done_skill_test.py` (staged ownership and final classification).
- `ci_github_work_management_test.py` (Issue/PR durable authority).
- `ci_pr_body_lint_test.py` (safe Issue relation vocabulary).
- `ci_workflow_topology_test.py` and `ci_toolchain_pin_test.py`
  (documented selection/toolchain invariants).
- Both skill-creator `quick_validate.py` invocations.
- `cmp AGENTS.md CLAUDE.md`, staged ownership, whitespace and full diff review.

Run complete CI discovery with pinned actionlint as regression evidence.
Run the precommit Architecture Portal check and record missing dependencies
honestly; do not infer a pass for downstream stages that did not execute.
No new source-wording gate is introduced: the existing behavioral/ownership
contracts remain the relevant checks, not a new daily-word blacklist.

## Version Management

Version impact: none — governance and skill prose do not allocate or modify
Product, Module, Provider, Host, Assembly or Contract identities.

## Documentation Impact

Documentation impact: none — no Architecture Portal pages or projected
identities change. The separate T5 switch still owes its required Portal
testing/release updates; this preparation does not discharge that obligation.

Pitfall impact: none — existing authorization, honest external evidence and
complete-journey guidance is retained; no new platform incident was observed.

## Local verification results

- Targeted existing suites: 10 + 6 + 14 + 46 + 4 = 80 passed.
- Both existing skills passed skill-creator quick validation; AGENTS/CLAUDE
  are byte-identical.
- Complete CI discovery with pinned actionlint: 1514 passed, no skips.
- Staged ownership: 66 passed; staged whitespace and declared-file list checked.
- Precommit Portal check: exit 1, 57 initial Node tests / 54 passed / 3 failures
  from missing `glob`, `gray-matter`, `cheerio`; later stages not reached.
  No Portal pass or dependency repair is claimed.

These local checks do not prove automatic T5 activation or hosted fault/cancel
acceptance. The local commit remains held for independent review; no remote
shipping or controlled operation is performed by this Task.
