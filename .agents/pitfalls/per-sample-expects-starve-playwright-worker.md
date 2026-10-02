---
id: per-sample-expects-starve-playwright-worker
area: web-host
status: open
recurrences:
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/issues/1672
    observed_by: kimi-code-k3
exit: none
---

# An expect() per PCM frame in a Playwright journey starves the worker past its own test timeout

## Why

A Playwright `expect()` builds a full matcher per call. Looping it over every
sample of a recorded WAV (millions of frames on both channels) keeps the test
worker at 100% CPU for tens of minutes. Meanwhile the trace screencast of the
still-playing page keeps queuing frames the worker cannot drain, and the
test's own `setTimeout` timer starves behind the flood — the run wedges
indefinitely instead of failing, so the red gate never even reports. The
defect class is invisible in review because the assertion reads as strict;
its cost is what kills the lane. This cannot be derived from product code:
the journey is the gate.

## How to apply

Assertions over bulk PCM reduce to a scalar in plain JavaScript first, then
expect once: a peak, a count above a threshold, a first-index. The reduction
must happen in the worker, in one pass with early exit where the fact allows
it — never one matcher per element. Any new Playwright assertion over an
array larger than a few hundred entries should be written as
`expect(reduced).toBe(...)`; the metronome silence leg
(`creator_web_metronome.spec.mjs`) is the reference shape. No eligible
mechanism exists yet (`exit: none`): the violation is a style property of
arbitrary spec code, so the exit is reviewer/journey-author discipline until
a lint rule is admitted.
