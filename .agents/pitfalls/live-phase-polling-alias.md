---
id: live-phase-polling-alias
area: creator
status: open
recurrences:
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/pull/2001
    observed_by: Codex primary and remaining_decision_inventory
exit: none
---

# A default poll can repeatedly miss a live periodic phase window while the audio clock advances normally.

## Why

At the frozen `21f28e0` complete Creator run, Perform Launch and Sequence
Record-off/reselection each timed out after 32 successful transport checks.
The real clock advanced at approximately 48 kHz, 120 BPM, with no pending
switch or error. Their 400 ms early-window predicate was correct, but
Playwright 1.62.1 default intervals settled at one second. Samples alternated
outside the first fifth of each two-second bar; waiting longer would not
remove that sampling alias. The exact receipts and both failure traces were
retained and reduced, rather than attributed to load or a stalled engine.

## How to apply

For a live phase predicate, inspect actual frame/origin/BPM responses and
callback/wait timings from the failing trace. Calculate the period and window,
then check the installed framework's polling intervals. Use an explicit
cadence below the window, accounting for measured request cost; retain the
original deadline, predicate, far-side assertions and complete journey.
Do not force the native clock, widen the window, skip later transitions, or
use a lucky rerun or environment correlation as the causal proof.

`exit: none`: determining a future predicate's period, window and request
cost requires source and actual timing judgment. The two targeted cadence
repairs do not enforce that judgment for every future observation; no generic
threshold or gate is introduced.
