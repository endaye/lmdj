---
id: github-closing-keyword-negation
area: docs-governance
status: absorbed
recurrences:
  - date: 2026-08-31
    occurrence: https://github.com/endaye/lmdj/pull/493
    observed_by: Codex
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/477
    observed_by: Codex GPT-5
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/pull/1121
    observed_by: Codex gpt-5.6-luna (implementation); Codex coordinator (review)
exit: gate:tests/build/ci_pr_body_lint_test.py
---

# A negated GitHub closing keyword can still close the referenced Issue when the Pull Request merges.

## Why

Corrective PRs #493, #494, and #495 intended to keep their design Issues open
because implementation-plan acceptance remained outstanding. Their bodies used
sentences of the form "does not close" followed by an Issue reference. GitHub
treated those references as closing directives and closed #464, #467, and #471
when the PRs merged, despite the surrounding negation. The Issues had to be
reopened explicitly after the merged-state audit.

The 2026-09-03 audit found the same class on PR #477, whose body said it
delivered "the design half only" of #466 and then wrote "does not close #466".
#466 closed on merge and had to be reopened, because its fixture and
report-tooling acceptance was still outstanding. That second recurrence was
escalated as [#578](https://github.com/endaye/lmdj/issues/578).

This is external parser behavior, not a product invariant visible in repository
code, and no gate can cover GitHub's complete keyword parser. What is settled,
mechanically decidable and deterministic is the contradiction inside the body
the author controls: a closing keyword bound to an adjacent negation, and an
Issue named both as a retained relation and in a closing directive. That much
graduates to a gate under `docs/governance/pitfall-ledger.md`; judging whether
prose *means* partial delivery does not, and the lint never tries.

## How to apply

For partial work, use the exact positive form `Relates to #<number>` and do not
place `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`,
`resolves`, or `resolved` immediately before an Issue reference, even inside a
negated sentence. Keep `Closes #<number>` for the delivery that completes every
acceptance item of that Issue.

Before `gh pr create`, run the deterministic check the shipping flow mandates in
[`.agents/skills/issue-done/SKILL.md`](../skills/issue-done/SKILL.md) §4:

```bash
python3 tests/build/ci_pr_body_lint.py --body-file <pr-body-file>
```

Its regression tests cover the deterministic subset of four historical
recurrences; they do not emulate GitHub's complete external parser or replace
the live relation inspection. The UTC 2026-09-09 recurrence was PR #1121: its
non-adjacent negation passed the existing lint, but GitHub still emitted a
ClosedEvent with PR1121 as the closer for #666. The coordinator reopened #666
and recorded the recovery at
https://github.com/endaye/lmdj/issues/666#issuecomment-5606083941.

The regression coverage over the four historical fixtures is
[`tests/build/ci_pr_body_lint_test.py`](../../tests/build/ci_pr_body_lint_test.py).
The lint reads the body only, so it cannot see a closing directive added later
through the GitHub web editor: after every merge that intentionally preserves an
Issue, still query that Issue's live state, and if it was closed, reopen it and
record why. The PR #1121 recurrence adds a second boundary: before a guarded
merge, the shipping skill must inspect the complete paginated live
`closingIssuesReferences` connection and compare it with every explicitly
retained/deferred Issue in the body. If GitHub reports an unintended closing
relation, the premerge check fails with `why: live parser relation contradicts
the retained/deferred Issue` and `remedy: remove the closing directive, rerun
the body lint, and re-query until the relation is absent`; this is external
parser inspection in the skill, not a fuzzy-prose or new required-CI gate.
