---
id: wait-already-true-before-action
area: web-host
status: open
recurrences:
  - date: 2026-11-02
    occurrence: https://github.com/endaye/lmdj/issues/2528
    observed_by: Claude Code (Claude Opus 5.5)
exit: none
---

# A wait whose condition already holds before the action proves nothing about the action.

## Why

A browser journey often follows a click with `toBeEnabled` or `toBeVisible` on
a control and treats that as "the action finished". When the condition was
already true before the click, the wait returns at once. The journey then races
the work it claims to have waited for. Two outcomes are possible: the next step
cancels that work silently and the leg passes with no far side, or the work
finishes first and its UI blocks the next step until a timeout. In #2528 the
Creator deployment journey waited for `Replace Sample` to be enabled after
`Confirm replace`. That button never disables during the long-source decode.
Navigating to `Sequence` usually unmounted the Sample surface and discarded the
decode, so the journey passed without replacing anything. When the decode won,
the `Pad A01 Long Source` dialog blocked `Sequence` for 300 s.

## How to apply

For each wait that follows an action, ask whether its condition was already
true before the action. If it was, wait instead for a surface the action itself
produces (here the Long Source dialog), drive it to completion (Commit
selection), and wait for its completion signal (the dialog closing only on a
committed outcome). Mutation check: make the action a no-op or keep its
completion from landing, and the journey must fail at that wait. Stays `open`
with `exit: none`, because whether a condition predates its action is not
decidable from the test text alone. See also
[`cumulative-evidence-log-last-entry-wait`](cumulative-evidence-log-last-entry-wait.md).
