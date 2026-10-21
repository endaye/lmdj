---
id: live-phase-polling-alias
area: creator
status: open
recurrences:
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/pull/2001
    observed_by: Codex primary and remaining_decision_inventory
  - date: 2026-10-18
    occurrence: https://github.com/endaye/lmdj/issues/2231
    observed_by: Codex primary
  - date: 2026-10-21
    occurrence: https://github.com/endaye/lmdj/pull/2384
    observed_by: Codex primary
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

## Second recurrence and escalation

At the #2231 producer checkpoint `bca06427`, real clicks were 0.5s apart,
lasted 40ms, and the analyser covered 2048/48000s. Default polling missed them;
20ms observation retained the >0.001 predicate, 35s deadline and full journey.
A read-only negative control aligned observation to the gap and sampled every
two click periods. While 71 real clicks played and the audio clock advanced
34.181333s, all 35 observations were zero at phases 0.258667–0.440000s after a
click; the original assertion failed. Fresh ordinary observation passed both
complete normal and actual-render-fault journeys (38.5s). No audio clock, product
packet, gain, threshold or timeout was changed to produce this evidence.

Escalation: [#2382](https://github.com/endaye/lmdj/issues/2382) tracks absorbing
the period/window/request-cost judgment into the formal verification skill.
Keep this entry open until that mechanism actually lands. No deterministic
generic cadence gate is claimed. Original failures and all control traces
remain retained; a later pass does not erase the missed-window evidence.

## Stereo one-shot observation recurrence

During #2384 main integration, both initial signal predicates failed with the
default backoff. The retained trace sampled actual left-only output at context
14.448s and right-only output at 15.456s; the second journey sampled left-only
at 14.005333s and a decaying left with full right at 15.013333s. The two
one-second voices start asynchronously, so their shared steady interval can
fall between those one-second polls. Native input latency remains separately
under investigation in #2395; two unchanged-package passes do not explain it.
The signal observer now uses the existing 20ms meter-observation cadence with
the same 35s deadline, exact Native start identities, 50ms steady bound and
literal PCM assertions. Both complete journeys passed. Keep #2382 as the
existing escalation and retain all failures; no environment cause is claimed.
