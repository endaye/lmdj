---
id: local-audio-proof-inherits-output-device
area: web-host
status: open
recurrences:
  - date: 2026-09-30
    occurrence: https://github.com/endaye/lmdj/issues/1696
    observed_by: claude-opus-5-5
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/issues/1730
    observed_by: claude-opus-5-5
exit: none
---

# A local browser audio proof runs on whatever output device the machine has selected, so a timing flake can follow the headphones rather than the load, and green reruns on another device prove nothing.

## Why

#1696: on 2026-09-30 Creator journeys intermittently failed their
`Audio running` assertion, three times between 16:24 and 16:50 and again at
18:28. 218 later runs passed, which read as "not reproducible". The coreaudiod
log showed why: the default output was a pair of Bluetooth (A2DP) headphones
from 15:56 to 17:23 and again after 17:57, and the built-in speaker from 17:23
to 17:57, which is exactly when the 218 green runs happened. Playwright's
Chromium renders to the real CoreAudio default device, and nothing in the
harness pins or records which one.

A cold A2DP start took 170 to 900 ms that day. Chromium also restarted the
running destination once the AudioWorklet module was ready, so each activation
paid two cold starts inside the one-second activation budget, and the slow
tail crossed it. The link also stays warm for a few seconds after IO stops:
back-to-back `--repeat-each` runs about 2 s apart used a median 136 ms of the
budget, while runs with a 10 s idle gap used 732 to 838 ms. A tight repro loop
therefore measures a different path from the journey, which idles before it
activates.

The Creator shows `Audio inactive` after activation lands in
`restart-required` with `HOST_TIMEOUT`, which looks like a silent refusal. The
real code was in the diagnostics region of the retained trace.

## How to apply

- When a local browser audio journey flakes on timing, record the default
  output device (`system_profiler SPAudioDataType`). Then query coreaudiod
  around the failure with
  `/usr/bin/log show --start ... --end ... --predicate 'process == "coreaudiod"'`.
  `XPC START MESSAGE SENT` followed by `Signaling audio start condition` is
  one cold Bluetooth start. `IO Stopped Context ... after 512 frames` followed
  immediately by `IOWorkLoopInit` is a destination restart.
- Count green reruns as evidence only after confirming they ran on the same
  output device. Reproduce with the idle gap the journey has, not a warm-link
  loop.
- Read the failing trace's diagnostics `error_code` before calling an
  activation failure a refusal. See
  [`blind-search-reads-as-absence`](blind-search-reads-as-absence.md).

No mechanism exits this entry. The harness cannot choose the machine's output
device, and substituting a fake output would stop the proofs exercising the
real output path.

It recurred on 2026-10-01: three `creator` journeys failed within 14:10–14:13
+0800 while coreaudiod logged 17 cold Bluetooth starts, and an immediate
re-run on the built-in speakers passed with no Bluetooth start logged. The
second recurrence escalates to
[#1730](https://github.com/endaye/lmdj/issues/1730), which asks the local
audio lanes to record and flag the default output device. The entry stays open
until that mechanism lands.
