---
id: free-running-audio-driver-frame-count
area: web-host
status: open
recurrences:
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1802
    observed_by: Claude Code (Opus 5.5)
exit: none
---

# A test that wraps a blocking dispatch in `ContinuousAudioDriver` renders as many frames as that dispatch takes, so any later assertion on frame-dependent voice state passes in dev and fails under a sanitizer or on a loaded host.

## Why

`ContinuousAudioDriver` (`packages/web-runtime-platform/test/control_runtime_test.cpp`)
renders 128-frame callbacks on its own thread for as long as it lives. Tests
use it around `pad.delete`, `history.undo` and similar dispatches, because their
Bank publication waits for an acknowledgement that only rendering produces. The
number of frames it renders is therefore the dispatch's wall-clock duration,
not a test step.

On #1802 the pad-delete test held a replay's Pad hit for 96,000 frames on a
192,000-frame sample, then asserted that the hit was still sounding after the
delete. In the dev build the delete returned within a few thousand frames. Under
macOS ASan the driver rendered about 238,000 frames during the same delete, so
the hit had already ended by itself. Every dev run passed, and only the
`core_macos` lane's asan stage failed. More hold or a longer sample would only
move the threshold: CI load stretches the dispatch further.

## How to apply

- Inside a `ContinuousAudioDriver` block, assert only facts that do not depend
  on how many frames elapse: response fields, Truth, publication counts.
- When a test must observe voices or other frame-dependent engine state after
  a dispatch that needs a Bank acknowledgement, set the fake coordinator's
  `render_on_acknowledgement_poll`. Each acknowledgement poll then renders one
  callback, so the frame count follows the poll count instead of the wall clock.
- Before trusting such a test, run it once in the asan build
  (`build/core/asan/bin/...`) as well as dev.

`exit: none`: whether a test's assertion depends on elapsed frames is a
judgement about the assertion, and no deterministic check can decide it.
