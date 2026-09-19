---
id: gate-job-conclusion-is-not-lane-verdict
area: ci-release
status: open
recurrences:
  - date: 2026-09-19
    occurrence: https://github.com/endaye/lmdj/actions/runs/35419357786
    observed_by: Claude Code (Fable 5.1)
exit: none
---

# A `continue-on-error` gate job's `success` is not the lane's verdict; read the adjudication job.

## Why

`macOS gates (primary)` runs every step with `continue-on-error: true` and
publishes step outcomes for the separate adjudication jobs `core (macos-latest)`
and `core-asan-macos`. Its own conclusion therefore says only that it reached
the end. On 2026-09-18 four consecutive "green" 11–14 minute primary jobs had
actually ended `scripts/core.sh proof` in 660 ms on a Product Build identity
mismatch; the adjudication jobs were red. Reading the gate job's conclusion
produced the wrong baseline ("the proof used to take 14 minutes"), and the real
finding — the proof had never run to completion since the release ctest entries
grew from 13 to 70 registrations — surfaced only from the leftover
`build/core/proof-failures/<run>/proof.log` in the runner workspace after the
first genuinely complete proof timed out.

## How to apply

When a lane is split into a gate job and an adjudication job, the adjudication
job's conclusion is the lane verdict; treat the gate job's conclusion as
"finished", never as "passed". Before quoting a historical duration as a
baseline, confirm from the step log that the measured step ran to its own end
(`##[end-action ...outcome=success]` and the step's final artifact), not merely
that the job ended green. A cancelled job's log is often unavailable; the
self-hosted runner's workspace retains `proof-failures/` and
`Testing/Temporary/LastTest.log` from the orphaned process and is the better
source for what actually ran. No deterministic gate fits: the shape is a
reading error over existing evidence, so this stays open with `exit: none`.
