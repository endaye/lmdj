# Daily Task verification obligation

Relates to #1996. The owner requests small ordinary checks and complete release
verification. Refreshed main and this worktree base are
`deb95de722b845d708371e90bcac138ae5e25e01`.

## Premises and sequencing

The current shipping procedure requires every selected `batch_only` lane to run
in full locally before merge. That makes an otherwise advisory full classifier
a universal local merge gate. A quick command cannot remove this obligation.
The published Task requirement and full candidate verification already provide
separate, suitable boundaries; retain both and remove the blanket lane receipt.

This is an independently reviewable policy prerequisite for the execution work
in #2011. It introduces no unimplemented command, changes no automatic trigger,
and makes no quick or full result into release authority. The execution PR
still has to verify its own Task, risk boundaries and current head before merge.
The policy PR itself follows the current live procedure, including its selected
batch-only Deploy Contract evidence. It does not waive its own checks.

## Task

One Conventional Commit owns exactly:

- `AGENTS.md` and byte-identical `CLAUDE.md`
- `.agents/skills/issue-done/SKILL.md`
- `docs/governance/git-workflow.md`
- `.github/pull_request_template.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- this plan

Ordinary verification records the Task's concrete commands, covered defect/risk
and outcome in the PR. Use the lowest tier that covers the affected behavior;
persistence/recovery and concurrent lifetime changes retain owning integration,
restart or stress tests. A declared acceptance journey keeps every transition.
No blanket complete lane receipt or invented accepted-risk statement is needed
merely because a lane is absent from the PR workflow. Deferred full verification
stays unverified, with known failures and debt visible. Exact candidate/full
requests retain the complete inventory. Current-head independent review,
conflict checks and conversation protection remain required.

Keep the legacy `--batch-evidence-only` checker available for explicit full
receipt audits. It remains strict when invoked; it is no longer an ordinary
merge prerequisite after this policy is merged. Do not change branch protection.

## Verification

Run existing shipping-skill and scope tests, staged path ownership, byte equality
of the instruction copies, and the complete Portal check. Run the selected
Deploy Contract lane on the committed policy head for the live premerge rule;
record its actual input-bound receipt. Validate documentation impact, obtain
independent exact-head review and use protected expected-head squash merge.
No new policy-literal test or required status is introduced.

Task checks: 10 shipping-skill tests and 77 staged ownership tests pass;
AGENTS/CLAUDE are byte-identical; the complete Portal check passes all 50 routes.
The source checkpoint below precedes the committed-head Deploy Contract receipt;
this Task is not merge-ready until that receipt and independent review pass.

## Version Management

Version impact: none — verification procedure only; no product identities change.

## Documentation impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
