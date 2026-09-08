---
id: stale-premise-gets-implemented
area: core
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/995#discussion_r0
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/995
    observed_by: Claude Code (Opus 5)
exit: none
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
73 today. A Task branching from that plan would have implemented Task 1 as a
no-op or a duplicate entry. The plan had stated the re-resolution rule one
section earlier.

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

## How to apply

- **Re-resolve findings, not only line numbers.** When re-checking a document
  against a moved `main`, re-check every claim of the form "X is missing", "Y
  is outstanding", "Z is not yet done" — not just the coordinates. Those are
  the sentences that expire.
- Before implementing a Task from a plan, verify the Task's *premise* against
  the tree you are branching from, not only its file list. If the defect it
  names is already fixed, the Task is delivered; say so in the plan rather than
  implementing it into a no-op.
- Write an absence claim with its frame attached — "absent at `<sha>`" — so a
  later reader can see what would invalidate it. A bare "this is missing" is
  undated evidence.
- When a Pull Request merges while your document is in review, re-read your own
  document against it. Ask specifically: *did that change make anything I wrote
  false, as opposed to merely moved?*
- Restate a closed finding as history with the SHA that closed it, and mark the
  Task delivered with an explicit instruction not to repeat it. Deleting it
  loses the sequence; leaving it live gets it built twice.

`exit: none` at recurrence 2, with [#1010](https://github.com/endaye/lmdj/issues/1010)
opened per the ledger contract. No eligible mechanism exists: the check that
would catch this — "a document's claims about the tree still hold" — is not
mechanically decidable, because those claims are prose and the tree has no
representation to compare them against. #1010 records the three shapes worth
evaluating, of which a re-resolution step in `issue-done` is the likeliest, and
notes that a skill step nobody performs is the same failure one layer up.
