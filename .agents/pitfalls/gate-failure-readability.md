---
id: gate-failure-readability
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-15
    occurrence: https://github.com/endaye/lmdj/pull/148
    observed_by: unknown
  - date: 2026-08-15
    occurrence: https://github.com/endaye/lmdj/pull/149
    observed_by: unknown
  - date: 2026-08-15
    occurrence: https://github.com/endaye/lmdj/pull/150
    observed_by: unknown
  - date: 2026-08-18
    occurrence: https://github.com/endaye/lmdj/pull/183
    observed_by: unknown
  - date: 2026-08-20
    occurrence: https://github.com/endaye/lmdj/pull/218
    observed_by: unknown
  - date: 2026-08-21
    occurrence: https://github.com/endaye/lmdj/pull/227
    observed_by: unknown
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/pull/319
    observed_by: Codex
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A gate that fails without naming the violated invariant and its remedy costs more to diagnose than it saves, and gets patched one message at a time.

## Why

A fail-closed check is only as useful as what it tells the next reader. Seven
Pull Requests over eleven days did nothing but make existing release and Portal
failures legible: name the failing projection (#148), surface the validation
command detail (#149), keep the whole failure reason readable (#150), make a
provenance failure name its remedy (#183), name an existing squash witness
error (#218), surface exact-target audit detail (#227), and retain the sanitized
subprocess reason when local release preparation fails after #319. Each was
written as a one-off repair of one message, so the next new gate repeated the
omission.

The invariant is not mechanically decidable — no test can judge whether prose
is actionable — so it exits to guidance at the point where a gate is authored
rather than to a gate of its own.

## How to apply

Before adding or changing any fail-closed check, write its failure message to
contain both parts required by
[`docs/governance/pitfall-ledger.md`](../../docs/governance/pitfall-ledger.md):
`why` (the violated invariant and why the observed state violates it) and
`remedy` (the concrete action or command that corrects it). A bare assertion, a
generic invalid-state string, or a file path with no rule named does not
satisfy the rule. Read your own message as someone who has never seen the check.
