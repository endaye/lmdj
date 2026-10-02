# Sample tone parity acceptance ledger

Date: 2026-10-02. Task: [#1667](https://github.com/endaye/lmdj/issues/1667)
(Sample tone parity: attack/release, tone, 3-band EQ), plan
`docs/plans/2026-09-30-creator-sample-parity.md` Tasks 17–19. The Core half
landed in #1780.

**Status: automated rows are recorded below; every hearing row is not run.**
This ledger records what was actually established and what was not. It is not
a release record, allocates no Product Build, and a green automated run here
does not stand in for a hearing row.

## 1. What the parameters are

The four optional `lmdj.project.v5` `5.2.0` playback keys and their ranges are
fixed by `docs/prd/decisions/2026-09-30-sample-playback-and-tone-parity.md`:

- `attack_ms` (0..2000) and `release_ms` (0..4000), linear ramps never shorter
  than the 2 ms declick;
- `tone` (−100..+100): a low-pass below centre, a high-pass above it, bypassed
  within ±2;
- `eq`: an optional low and high band (`shelf` or `cut`) and a mid bell.

An omitted key or band is its default, which is today's behaviour. How a voice
ends and which stops play the release are fixed by
`docs/prd/decisions/2026-10-02-sample-voice-endings-and-stops.md`.

## 2. Five paths, automated

Each path names the test that owns it and the far-side fact it asserts.

| Path | Owner | Far-side assertion |
| --- | --- | --- |
| normal | `creator_web_sample_editor.spec.mjs` tone journey | Attack, Release, Tone, a held EQ key run on the high band, a 37-step key run that makes the low band a cut, and a pointer drag on the mid band each commit exactly one revision; `sample.inspect` returns the exact playback |
| cancelled | same journey | Escape mid-drag on Tone, and Escape during an EQ key step, send `sample.preview.set` then `sample.preview.clear` and no `sample.update_pad`; the readouts return to the committed values; revision and playback unchanged |
| refused | same journey; `control_runtime_test.cpp`; `sample_surface_test.cpp`; `protocol.test.mjs`; `runtime_session.test.mjs` | a mid `q_milli` of 10 001 → `HOST_PROTOCOL_MISMATCH`; a stale revision → `REVISION_CONFLICT` with exact details; every envelope, tone and band bound is refused at each layer, including 64-bit values that would wrap to valid ones if narrowed first; revision unchanged in every case |
| failed | same journey | a commit failure manufactured at the transport seam shows `Creator could not change this sound.`, and Attack keeps its committed `120 ms`; the Runtime never receives that request, so this proves only the Creator's handling |
| reopened | same journey | after reload the remembered Project reopens, `sample.inspect` equals the committed playback, and the controls read `120 ms`, `900 ms`, `LP 40`, a low cut at 100 Hz and a high shelf at 8.00 kHz +1.0 dB |

Signal-level rows:

| Fact | Owner |
| --- | --- |
| tone −100 leaves a ~495 Hz sawtooth hit in the recorded master output at least 20 dB below the same sample on an untouched Pad, and still sounding | `creator_web_perform.spec.mjs` tone −100 test |
| a filtered voice ends without a step, at a release and at its sample's end | `realtime_engine_test.cpp` (PR #1780) |
| realtime and offline renders of the envelope, tone and EQ agree within one PCM16 step, including different filter flush cadences | `voice_dsp_parity_test.cpp` (PR #1780) |
| tone, shelf, cut and bell responses, and flushing to exact zero | `voice_dsp_test.cpp` (PR #1780) |

## 3. Hearing rows

None of these rows has been run. Each needs a person listening on the named
device through the deployed Build; record the Build, output route and level.

| Row | macOS Chrome | macOS Safari | iPad Air M3 Safari |
| --- | --- | --- | --- |
| A long Attack fades the hit in; a short one keeps its transient | not run | not run | not run |
| A long Release rings on after a gate Pad is let go; Stop silences at once | not run | not run | not run |
| Tone LP darkens and HP thins the sound; Off is unchanged | not run | not run | not run |
| Each EQ band moves the sound where its pole sits; a cut removes the lows / highs | not run | not run | not run |
| A filtered Pad ends without a click | not run | not run | not run |
| Preview while dragging matches the committed sound | not run | not run | not run |

## 4. Not covered

- Cardputer: the Cardputer build compiles the voice DSP out (#1780), and
  Runtime Content v1 refuses a non-neutral voice DSP block, so the tone keys do
  not reach the device.
- No remote CI, merge, tag, Release, deployment or Channel promotion is proven
  by this ledger.
