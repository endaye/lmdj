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

Its regression coverage over the four real recurrences is
[`tests/build/ci_pr_body_lint_test.py`](../../tests/build/ci_pr_body_lint_test.py).
The lint reads the body only, so it cannot see a closing directive added later
through the GitHub web editor: after every merge that intentionally preserves an
Issue, still query that Issue's live state, and if it was closed, reopen it and
record why.
