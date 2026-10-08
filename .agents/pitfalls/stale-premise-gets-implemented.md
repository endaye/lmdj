---
id: stale-premise-gets-implemented
area: core
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/978
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/995#discussion_r3960687318
    observed_by: Claude Code (Opus 5)
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A stale coordinate fails loudly; a stale premise gets implemented

## Why

A line number that has moved points at the wrong line, and the next reader sees
that instantly. A *finding* that has expired — "this operation is missing",
"this Task is outstanding", "this assertion does not exist" — still reads as
actionable, and the next reader acts on it. Nothing about a stale premise
announces itself, which is why it survives the re-resolution that catches
coordinates.

This is not
[`blind-search-reads-as-absence`](blind-search-reads-as-absence.md). There the
search could never have distinguished present from absent, so the finding was
never evidence. Here the search was sound and the finding was correct when it
was made. It expired because the tree moved.

Two occurrences in one session, both on #799's byte path.

**One.** A reviewer's assertion was reported as absent from `origin/main` and
present only on two unmerged branches. That was true at `968c4062` and false at
`b5d8ca93` — and `b5d8ca93` was the merge of the very Pull Request that added
it, and was named as the baseline in the same message that called it absent.
Fifteen line-number coordinates were re-resolved at that move; the conclusion
drawn from them was not, because a conclusion does not look like a coordinate.

**Two, and worse.** An implementation plan's §2.7 described the Web Host as
unable to dispatch `soundset.audition`, and its Task 1 was scoped to fix that.
Both were accurate when written. #999 then merged as `45756035` and closed the
gap, and the plan went to review still describing it as live, still instructing
a Task to fix it, and still saying the operation array grows 72 → 74 when it is
73 at that revision. A Task branching from that plan would have implemented
Task 1 as a no-op or a duplicate entry. The plan had stated the re-resolution
rule one section earlier.

The asymmetry that makes this class expensive:

- **Absence claims have no natural expiry check.** A presence claim is
  falsified by looking; an absence claim is falsified only by the commit that
  adds the thing, and nobody re-runs it.
- **The document is trusted more the more careful it looks.** Both occurrences
  were in artefacts full of verified coordinates. The surrounding rigour is
  what makes the one unverified sentence credible.
- **The window is the review latency.** Anything that merges between drafting
  and review can invalidate a premise, and long-lived documents — plans,
  pitfalls, Issue bodies — have the longest windows.

**This entry's own first citation was an instance of it.** The recurrence above
was originally recorded as `pull/995#discussion_r0`. GitHub review anchors are
`discussion_r<numeric-id>`; `r0` is a placeholder, so the link rendered as a
precise citation and resolved to the top of a Pull Request. The ledger lint's
`OCCURRENCE` pattern accepted it, because that expression validates the shape of
a URL and not whether it points at anything — the same distinction that let
`ISO_DATE` accept `9999-13-99` until #1002 parsed the date before comparing it.

So the citation documenting the defect contained the defect, and the gate that
should have caught it could not express the question. It was found by review,
recovered from a dropped artefact, and is recorded here rather than quietly
repaired, because an entry that hides its own instance is worth less than one
that carries it.

## How to apply

Run [`issue-done` §0](../skills/issue-done/SKILL.md#0-resolve-task-premises-before-editing)
before implementing a Task, and repeat its affected dispositions when relevant
main changes land. Preserve fulfilled findings with their delivering SHA and
stop duplicate implementation; refreshing coordinates alone is insufficient.

Recurrence 2 was escalated through
[#1010](https://github.com/endaye/lmdj/issues/1010). Its exit is now the skill's
required pre-edit premise resolution and relevant-main refresh. The skill
description exposes the implementation trigger before its body is loaded.
This remains a reading of prose against current source and delivery history,
not a mechanically decidable CI gate. Both original recurrences and their
citation history above remain evidence; absorbing them adds no new occurrence.
