---
id: fixed-audio-window-races-browser-gesture
area: creator
status: open
recurrences:
  - date: 2026-10-18
    occurrence: https://github.com/endaye/lmdj/actions/runs/39096858553
    observed_by: Claude Code (Opus 5.5)
exit: none
---

# A packaged browser proof that asserts PCM at a fixed audio frame after a Playwright gesture passes on a quiet machine and fails on a loaded one, because the gesture's arrival at the engine follows the wall clock while the audio clock runs free.

## Why

The COUNT-IN UI journey in `creator_web_metronome.spec.mjs` held Pad A01
(`loop_gate`) across S, released it after several awaited UI checks, and then
required the product planes to be exactly silent at the first JS metronome
click, one beat after S. That beat sits 0.5 s after S at 120 BPM and 1.5 s at
40 BPM. The proof passed 20/20 on a quiet M1. The 2026-10-18 main batch failed
both scenarios on a Linux runner. The release itself was correct: the product
went silent after the release on every run. Its arrival depended on load. With
other agents running heavy jobs on the M1, the `keyup` landed 0.6–1.2 s after
S, sometimes after beat 1 itself. The release then took another 27 ms to
0.7 s to silence the output. In 3 of 6 unchanged runs the window caught the
held voice. Before #2362 the tree failed the same way, so the batch's newest
commits looked guilty but did not cause it.

`free-running-audio-driver-frame-count` is the native sibling: there a dispatch
renders frames for as long as it runs on the wall clock. Here a browser gesture
competes with an `AudioContext` that never waits.

## How to apply

- When a later window must see the effect of a UI gesture, first observe that
  effect in the captured PCM, for example sustained exact silence after a
  release. Then select the first window after it. Do not assume the gesture
  lands before a fixed musical frame.
- Keep the window assertion exact. Do not stretch a deadline or drop the leg.
  Pass a timeout to the observation so that an effect that never happens still
  fails with a named message.
- Size any fixed PCM/capture buffer for the latest window the selection can
  pick. Do not size it for the earliest one.
- Before attributing such a failure to the newest commits, record the gesture
  frame and the onset/offset runs from the observer. Then rerun the same check
  on the parent commit.

`exit: none`: no deterministic check can decide whether an assertion depends on
the timing of a host-side gesture. That is a judgement about the assertion.
