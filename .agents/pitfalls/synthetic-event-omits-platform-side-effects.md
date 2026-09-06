---
id: synthetic-event-omits-platform-side-effects
area: product
status: absorbed
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/issues/738
    observed_by: claude-fable-5-1
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A synthetic stand-in for a platform gesture proves only what the stand-in does; the real gesture's other side effects go untested

## Why

This is not [`acceptance-journey-truncation`](acceptance-journey-truncation.md).
That entry is about legs a journey never walks. Here the leg was walked, the
far-side observables were asserted, and the test was still blind.

The Creator journey `ordinary Sample focus loss keeps the retained trim dialog
visible` drives focus loss with `window.dispatchEvent(new Event("blur"))`. That
reproduces exactly one of the two things a real macOS Safari focus loss does:
it fires `blur`, so the capture panel stops recording and retains the take, and
the journey's assertions about the retained waveform, the stop reason and
Commit/Discard all pass honestly. It does not interrupt the AudioContext, which
a real focus loss also does, so the Web Runtime never reports audio recovery.

The Sample surface cleared its capture target on audio recovery, unmounting the
panel and discarding the take. The journey stayed green through `1.0.41.0` and
`1.0.42.0` while the defect shipped twice, and it was a physical macOS Safari
acceptance attempt that found it (#738), after an earlier attempt had already
burned on a different half of the same expected behaviour (#625).

The general shape: a synthetic event carries the name of a platform gesture but
not its consequences. The assertion is then scoped to the stand-in, while the
test's title claims the gesture.

## How to apply

When a test substitutes a synthetic event, a stubbed device, or a forced state
transition for something a real platform does, write down what the real thing
does to the system under test — every observable side effect, not only the one
the test is named after — and then either reproduce each of them in the same
test, or record the unreproduced ones as an explicit acceptance gap next to the
test. `blur` and `visibilitychange` on a page that owns an AudioContext, a
media device, a wake lock or a storage handle are the recurring examples: the
window event is the easy half, and the resource interruption is the half that
carries the defects.

Where reproducing a side effect would need a seam that must not exist in the
packaged product, gate that half at the layer that can reach it — a component
test over the state transition — and name that companion gate in a comment on
the packaged journey, so the next reader cannot mistake one for both.
