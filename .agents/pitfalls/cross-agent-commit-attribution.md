---
id: cross-agent-commit-attribution
area: docs-governance
status: absorbed
recurrences:
  - date: 2026-08-25
    occurrence: https://github.com/endaye/lmdj/pull/314
    observed_by: claude-opus-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# Git metadata cannot say which agent session produced a commit, so any attribution inferred from it is unreliable and two agents can assert contradictory histories of the same SHA.

## Why

Concurrent sessions run under the same Git identity, and a task branch also
accumulates commits made outside any session — a branch updated through the
GitHub web interface records `GitHub <noreply@github.com>` as committer while
keeping the human as author. Nothing in the commit records the agent.

Observed on 2026-08-25 while shipping this ledger: two concurrent Claude Code
sessions gave contradictory accounts of the same four commits on
`docs/pitfall-ledger-contract`. Each reconstructed history from commit metadata
and reached a different, confidently stated answer; both were partly wrong. The
metadata that finally separated the cases was incidental — a cherry-picked
commit had an author date 2m49s earlier than its committer date, while the two
branch updates had `GitHub` as committer — and none of it identified an agent.

This matters beyond credit. `observed_by` exists to answer whether pitfalls
recur across models. An `observed_by` derived from Git metadata measures
nothing, and would silently poison the only cross-agent evidence this ledger
collects.

## How to apply

State `observed_by` from your own record of what you did, at the moment you
write the entry. Do not read it off `git log`, the Pull Request author, or the
branch's Git identity. When you cannot state it first-hand — seeding an entry
from history, or recording an occurrence someone else hit — write `unknown`.
`unknown` is a truthful reading; a plausible guess is a fabricated one.

When two sessions disagree about who did what, do not settle it from metadata.
Each session's own transcript is the only first-hand evidence, and neither can
audit the other's.
