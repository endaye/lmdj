---
id: github-closing-keyword-negation
area: docs-governance
status: open
recurrences:
  - date: 2026-08-31
    occurrence: https://github.com/endaye/lmdj/pull/493
    observed_by: Codex
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/477
    observed_by: Codex GPT-5
exit: none
---

# A negated GitHub closing keyword can still close the referenced Issue when the Pull Request merges.

## Why

Corrective PRs #493, #494, and #495 intended to keep their design Issues open
because implementation-plan acceptance remained outstanding. Their bodies used
sentences of the form "does not close" followed by an Issue reference. GitHub
treated those references as closing directives and closed #464, #467, and #471
when the PRs merged, despite the surrounding negation. The Issues had to be
reopened explicitly after the merged-state audit.

This is external parser behavior, not a product invariant visible in repository
code. No deterministic repository gate covers GitHub's complete keyword parser,
so the first occurrence remains open with no mechanical exit.

## How to apply

For partial work, use the exact positive form `Relates to #<number>` and do not
place `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`,
`resolves`, or `resolved` immediately before an Issue reference, even inside a
negated sentence. After every merge that intentionally preserves an Issue,
query that Issue's live state; if it was closed, reopen it and record why.

The second recurrence is escalated in
[#578](https://github.com/endaye/lmdj/issues/578). Until that Issue lands a
durable skill or gate exit, every partial-delivery merge still requires the
live post-merge Issue-state audit above.
