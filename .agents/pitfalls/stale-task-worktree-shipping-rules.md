---
id: stale-task-worktree-shipping-rules
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/pull/1113
    observed_by: Codex (GPT-6)
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/pull/1126
    observed_by: Codex (GPT-6)
exit: skill:.agents/skills/issue-done/SKILL.md
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

The second occurrence happened when main added the live
`closingIssuesReferences` inspection during L3's review/shipping interval.
The postmerge audit found exactly the intended #1040 closure and retained
#471/#472 open, but that does not prove a premerge inspection.

Absorbed into `issue-done` section 5: refresh and record live-main governance at
the start of the final premerge check pass, and refresh again when further work
delays that pass. The mechanism is a skill step because a gate cannot establish
which instructions an agent actually read. No new required CI check, strict
update rule or protection change is introduced.
