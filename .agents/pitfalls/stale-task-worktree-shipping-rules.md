---
id: stale-task-worktree-shipping-rules
area: ci-release
status: open
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/pull/1113
    observed_by: Codex (GPT-6)
exit: none
---

# A task worktree can retain shipping instructions that live main has replaced.

## Why

During L1, parallel work added the authenticated review-eligibility helper and
owner-attestation format on main. The implementation branch retained the older
shipping skill. The agent verified independent review, Task tests, conflicts,
conversations and protection, but used the older Markdown takeover procedure
and merged without the newly required helper. Discovering the rule after merge
does not retroactively establish pre-merge eligibility.

## How to apply

Before shipping, fetch main and compare its governance and shipping-skill paths
with the versions actually read for the Task. Follow live rules and run the
trusted current helper; a non-conflicting Task need not rebase merely to read
them. Preserve genuine independent-review evidence and report a missed check
honestly; do not invent prior eligibility or a waiver.

This first occurrence remains open. No automated gate can establish which
instructions an agent actually read; no new required check or protection change
is introduced here. A future skill-level absorption can make the fresh-source
inspection step explicit.
