# Sample playback parity acceptance ledger

Date: 2026-10-01. Task: [#1666](https://github.com/endaye/lmdj/issues/1666)
(Sample playback parity: reverse, pitch, pan, loop modes), plan
`docs/plans/2026-09-30-creator-sample-parity.md` Tasks 9–11.

**Status: automated rows are recorded below; every hearing row is not run.**
This ledger records what was actually established and what was not. It is not
a release record, allocates no Product Build, and a green automated run here
does not stand in for a hearing row.

## 1. What the parameters are

The six optional `lmdj.project.v5` `5.1.0` playback keys and their ranges are
fixed by `docs/prd/decisions/2026-09-30-sample-playback-and-tone-parity.md`:
`reverse`, `pitch_cents` (−2400..+2400, varispeed), `pan` (−100..+100,
equal-power), `loop_mode` (`forward` | `ping_pong`), `loop_start_frame` and
`loop_crossfade_frames` (forward only, at most half the loop). An omitted key
is its default, which is today's behaviour.

## 2. Five paths, automated

Each path names the test that owns it and the far-side fact it asserts.

| Path | Owner | Far-side assertion |
| --- | --- | --- |
| normal | `creator_web_sample_editor.spec.mjs` parity journey | each control (Reverse, Pitch, Pan, Loop, Loop start, Crossfade, Ping-pong) commits exactly one revision; `sample.inspect` returns the exact playback, including omission of default keys and the crossfade cleared by Ping-pong |
| cancelled | same journey | Escape mid-drag sends `sample.preview.set` then `sample.preview.clear`, no `sample.update_pad`; revision and playback unchanged |
| refused | same journey; `control_runtime_test.cpp`; `sample_surface_test.cpp` | `pan: 101` → `HOST_PROTOCOL_MISMATCH`; stale revision → `REVISION_CONFLICT` with exact details; a loop point past the source → `INVALID_ARGUMENT`; revision unchanged in every case |
| failed | same journey | a commit failure manufactured at the transport seam shows `Sample operation failed`, and Reverse keeps its committed `aria-pressed` value; the Runtime never receives that request, so this proves only the Creator's handling |
| reopened | same journey | after reload the remembered Project reopens, `sample.inspect` equals the committed playback, and the controls read `+3.5 st`, `L100`, Ping-pong pressed and loop start `0.025` s |

Signal-level rows:

| Fact | Owner |
| --- | --- |
| pan −100 leaves the right channel of the recorded master output exactly 0 while the left carries the hit | `creator_web_perform.spec.mjs` hard-left pan test |
| a preview's `pitch_cents` reaches the voice (a 200-frame one-shot an octave up ends inside 120 frames, at 0 cents it does not) | `control_runtime_test.cpp` |
| realtime and offline output of one kernel voice agree within 1 LSB | `voice_dsp_parity_test.cpp` (PR #1717) |
| reverse, pitch, ping-pong, loop point, crossfade and pan facts of the kernel | `voice_dsp_test.cpp` (PR #1717) |

## 3. Hearing rows

None of these rows has been run. Each needs a person listening on the named
device through the deployed Build; record the Build, output route and level.

| Row | macOS Chrome | macOS Safari | iPad Air M3 Safari |
| --- | --- | --- | --- |
| Reverse plays the selection backwards | not run | not run | not run |
| Pitch +12 / −12 st is an octave up / down and changes duration | not run | not run | not run |
| Pan L100 / R100 is heard from one side only | not run | not run | not run |
| Ping-pong loop turns at both ends without a click | not run | not run | not run |
| Forward loop from a loop point, crossfade 0 vs. 20 ms | not run | not run | not run |
| Preview while dragging matches the committed sound | not run | not run | not run |

A seam click reported on a short loop must be replayed before it is
classified: open pitfall `short-loop-hearing-misclassification`. Tell the
listener the loop duration and repeats per second, and record both the first
observation and any correction.

## 4. Not covered

- Cardputer: Runtime Content v1 refuses a non-neutral voice DSP block, so the
  parity keys do not reach the device; a follow-up Issue owns that.
- Tone parity (#1667: attack/release, tone, EQ) is a later Task.
- No remote CI, merge, tag, Release, deployment or Channel promotion is proven
  by this ledger.
