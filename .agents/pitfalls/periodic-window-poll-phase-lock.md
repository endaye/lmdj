---
id: periodic-window-poll-phase-lock
area: creator
status: open
recurrences:
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/pull/2004
    observed_by: Codex coordinator
exit: none
---

# A polling assertion can miss a healthy periodic state for its entire deadline when its steady interval repeatedly samples outside the required window.

## Why

The full Creator proof on `6c69c151` failed the Record-off journey's
`awaitEarlyBar` after Stop had cancelled the queued switch and playback had
restarted. All 32 replay inspections reported playing, no pending switch and
no error, with increasing audio frames. Playwright's default polling intervals
end at one second; the inspections repeatedly missed the first fifth of the
two-second bar until the unchanged 30-second deadline expired. No foreign heavy
producer overlapped the proof's two-second capacity samples.

The failure was in the observation cadence, not evidence that playback stopped.
Changing the helper to a 100 ms interval preserved its predicate, deadline and
every later switch, stopped Record and persisted-Truth journey assertion.

## How to apply

Compare recorded runtime frames, origin, tempo and poll timestamps before
attributing a periodic-window timeout to the product. Use a sampling interval
shorter than the required window; retain the same predicate and deadline.
Preserve the failed trace and verify the complete journey on the corrected
fixture, then run the full required lane on its final committed head.

`exit: none`: a general static gate cannot infer every runtime window and its
effective sampling cadence. Review each periodic helper against its actual
timing evidence; this entry adds no required CI gate.
