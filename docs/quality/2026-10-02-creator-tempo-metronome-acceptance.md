# Tempo/Swing direct control and metronome acceptance ledger

Date: 2026-10-02. Task: [#1672](https://github.com/endaye/lmdj/issues/1672)
(direct tempo and swing control, tap tempo and a metronome), plan
`docs/plans/2026-10-02-creator-tempo-metronome.md` Tasks T1–T4, decision
`docs/prd/decisions/2026-10-02-creator-tempo-metronome.md`.

**Status: automated rows are recorded below; every hearing row is not run.**
This ledger records what was actually established and what was not. It is not
a release record, allocates no Product Build, and a green automated run here
does not stand in for a hearing row or a device-lifecycle acceptance.

## 1. What the parameters are

`lmdj.project.v5` carries `bpm` (integer 40–240) and
`sequence_settings {quantize_enabled, swing_percent 50–75}`; New Project boots
at 120 BPM. The metronome switch is not in the Contract: it is a per-device
monitoring preference in the IndexedDB Host settings store (`metronome.v1`,
default off), per the 2026-10-02 decision item 6.

Documented effective boundaries (decision item 3):

- stopped: a committed change applies immediately;
- playing, BPM: the current Pattern republishes and the new tempo activates at
  the next bar boundary of the old tempo (`pattern_publication.activation_frame`);
- Swing/Quantize: record-time baked into subsequently recorded events
  (2026-08-23 decision); already-recorded events never move;
- recording the Pattern transport: Tempo/Swing/Quantize changes are refused
  (`HOST_STATE_INVALID`), and the metronome stays toggleable and audible;
- metronome alignment: a constant error of at most about two render quanta
  (≈5 ms at 48 kHz), no per-beat drift, re-anchored on every engine epoch.

## 2. Five paths, automated

Each path names the test that owns it and the far-side fact it asserts.

| Path | Owner | Far-side assertion |
| --- | --- | --- |
| normal | `creator_web_sequence.spec.mjs` direct-controls journey; `creator_web_metronome.spec.mjs` | drag-release commits exactly one `sequence.settings.update` (payload asserted) and one revision, `project.inspect` carries the value; step and TAP commit immediately; a playing commit's `activation_frame` is `> origin_frame` and a whole number of old-tempo bars after it; metronome click events have inter-click `contextTime` deltas of 60/bpm (±10%) with every 4th beat accented |
| cancelled | same journeys; `sequence_surface.test.tsx`; `value_slider.test.tsx` | Escape mid-drag sends nothing, no revision moves, the control falls back to the committed value; toggling the metronome off mid-play stops the click flow and cancels every unsounded click |
| refused | same journeys | while recording, all seven Tempo/Swing controls are disabled with the reason shown, and a raw `sequence.settings.update` send is refused `HOST_STATE_INVALID` with Truth unchanged; the metronome toggle stays enabled and clicks keep flowing, and Record-off leaves Pattern events untouched |
| failed | `creator_web_sequence.spec.mjs` direct-controls journey; `sequence_surface.test.tsx` | an injected `HOST_TIMEOUT` surfaces the code in an alert; Truth, revision and the readout keep the committed value; the step base resyncs to committed truth |
| reopened | `creator_web_hardware_layout.spec.mjs`; `creator_web_metronome.spec.mjs` | after reload the committed bpm/swing survive in Truth and on the controls, an uncommitted preview is gone; the metronome preference reads back from IndexedDB (`aria-pressed` and stored value agree), and a fresh browser profile defaults to off |

Signal-level rows:

| Fact | Owner |
| --- | --- |
| a metronome-on Perform recording with no Pad triggers is digital silence on both channels, while a witness sample in the same session records real signal | `creator_web_metronome.spec.mjs` silence + witness legs |
| the click never reaches the master tap (it connects only to `context.destination`) | `metronome_click.test.ts`; the silence leg above |
| beat frames use the engine's own ceiling formula (`tick_boundary_frame`), so click cadence and engine scheduling cannot drift apart | `metronome_scheduler.test.ts` |
| within one engine epoch the anchor converts engine frames to context seconds exactly (identity mapping, heartbeat wrap, re-anchor across epochs) | `audio_clock.test.ts`; `runtime_session.test.mjs` `sampleAudioClock` tests |
| rapid step clicks accumulate one revision per click from the last requested value | `sequence_surface.test.tsx` rapid-step and failure-resync tests |

## 3. Hearing rows

None of these rows has been run. Each needs a person listening on the named
device through the deployed Build; record the Build, output route and level.
Automation above measures schedule times and captured PCM; it cannot judge
how the click sits against the Pattern, how it sounds, or how the controls
feel.

| Row | macOS Chrome | macOS Safari | iPad Air M3 Safari |
| --- | --- | --- | --- |
| a BPM drag is heard from the next bar while playing | not run | not run | not run |
| the metronome sits on the beat against a playing Pattern (the ≈5 ms constant bound is inaudible as a flam) | not run | not run | not run |
| the metronome is heard while recording and is absent from the recorded Performance | not run | not run | not run |
| accent vs. normal clicks are distinguishable | not run | not run | not run |
| Tap Tempo at a played rhythm lands on the intended BPM | not run | not run | not run |

## 4. Not covered

- Swing never changes the playback of recorded events (record-time bake is the
  standing 2026-08-23 decision); Koala-style playback groove is a listed parity
  deviation, not delivered here.
- Tempo/Swing changes while recording stay refused; relaxing the recording
  fence touches the Facade's recording timing authority and is a later
  question (decision item 5).
- A fresh device profile cannot be distinguished from a new Project on the
  same device for a per-device preference; the default-off row uses a fresh
  browser profile.
- The leg-5 journey asserts default-off on a fresh profile and persistence
  across a reload; cross-device behaviour does not exist (per-device store).
- Physical touch ergonomics (drag feel, TAP on a touch screen) and real
  Safari are not exercised; the WebKit capability boundary stays explicit.
- No remote CI, merge, tag, Release, deployment or Channel promotion is
  proven by this ledger.
