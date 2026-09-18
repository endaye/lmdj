---
id: assertion-observed-after-a-later-transition
area: product
status: open
recurrences:
  - date: 2026-09-18
    occurrence: https://github.com/endaye/lmdj/issues/1513
    observed_by: Claude Code (Opus 5)
exit: none
---

# An acceptance leg that observes its far side only after a *later* transition passes while the transition it names is broken; the observation point must sit between the transition and the next one.

## Why

[`acceptance-journey-truncation`](acceptance-journey-truncation.md) covers a
journey cut short. This is the opposite shape: the journey is complete, every
leg is present, and the assertion still cannot see the defect — because it
reads state that a *downstream* transition also produces.

Ledger leg T-L6 of the Pattern transport physical acceptance asserted that
"second-pass Pad hits overlay the first pass; the first-pass events remain
audible and intact **after commit and reload**". The overlay merge does happen,
so the leg passed. What it could not see is that nothing was merged or
published until Record was switched off: what you played into one pass was
inaudible for the whole of the next one. The leg named the overdub transition
but observed only the commit that follows it, and the commit was never broken.
The defect (#1513) survived the leg and was found by an operator's ears, not by
the acceptance criteria written to gate exactly that behavior.

The root cause is not in the product code and no regression test expresses it:
it is where the observation is taken. An end-state assertion is cheap to write
and reads as rigorous, and it silently delegates its verdict to whichever later
step also establishes that state.

## How to apply

For every leg, ask: *which transitions, other than this one, would also make
this assertion true?* If any would, the assertion is not gating this leg. Move
the observation to the window between this transition and the next one, and
say so in the leg text — "on the next pass, **without leaving Record**" rather
than "after commit and reload".

Steady-state and continuous behaviors need an observation while the state is
still held, not after it ends. When a leg's far side is genuinely only visible
later, keep it and add a second leg that observes the interval; do not let the
later observation stand in for both. Reopening, reloading and committing are
far sides of their own transitions, never of the one before them.

This remains `open` with `exit: none`: whether an assertion is uniquely
satisfied by its own transition is a judgment about the specification's
meaning, not a property any check can decide from the repository.
