# Stage 8B Real Microphone Capture Evidence — 1.0.23.0

## Evidence boundary

This record converts exactly one physical row: **macOS Chrome — real
microphone capture, commit and playback hearing**, listed as
`deferred / unverified` in
[`2026-08-16-stage8b-pad-capture-acceptance.md`](../quality/2026-08-16-stage8b-pad-capture-acceptance.md)
and as M1 in
[`2026-08-17-manual-verification-todo.md`](../quality/2026-08-17-manual-verification-todo.md).

It does not claim external audio interface input, Safari, iPadOS, physical
MIDI, pointer, touch, lifecycle, latency, long-session stability, or any
Family L row. It claims no push, Pull Request, merge, tag, Release,
deployment, publication or Channel promotion.

| Field | Value |
| --- | --- |
| Product Build / Channel | `1.0.23.0` / `canary` |
| Tested source revision | `801fa450ff78971f97e6da585a74de12ee2084ee` |
| Creator / Platform / compatible Formal Host | `1.3.0` / `0.3.0` / `1.2.9` |
| Protocol version | `1` |
| Creator host manifest SHA-256 | `633e2c6fbb8d8088e5b5bf9de21077eea39fc778c7743c0aa7152576baa34615` |
| Assembly Lock SHA-256 | `7925f907ff99db949a00d36ffb1c6e872fc71a044c35c7133fba26a2fda614fa` |
| Emscripten identity | `6.0.5`, emsdk `dfb9d1a46c3bb8f52e1e6324be23123b9d73c190` |
| Host OS | macOS `26.6.1` (`25G76`), Darwin `25.6.0`, arm64 |
| Browser | Google Chrome `151.0.7922.138` |
| Surface under test | packaged distribution `build/web/creator/dist`, served by `scripts/creator-web.sh serve` on `http://127.0.0.1:4175` |
| Response headers observed | `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`, `Cross-Origin-Resource-Policy: same-origin`, `Cache-Control: no-store` |
| Input device | AirPods Pro microphone, wired to the MacBook as the system default input |
| Observer | endaye, 2026-08-17 |

The packaged distribution was used deliberately rather than a dev path, so the
distribution CSP and the same-origin content-hashed capture worklet (S8B-D12)
were exercised as shipped.

The Project under test was a locally generated fixture bundle: `project.create`
at 120 BPM, one imported `tests/fixtures/audio/kick.wav` Asset, Bank A Pads 1–4
assigned, one committed Take and Pattern. Pads A5 and above were left empty so
recording did not go through the replacement confirmation. The fixture is not a
repository artifact and is not required to reproduce the result; any Project
with an empty Pad is sufficient.

## Result

`PASS` — all five hearing criteria confirmed by endaye on Pad A6 (normal level)
and Pad A7 (deliberately hot level).

| # | Criterion | Failure class it excludes | Result |
| --- | --- | --- | --- |
| 1 | The committed Pad plays back audible sound | silence — a wired-but-dead capture path | `PASS` |
| 2 | Playback pitch and duration match the source | sample-rate error between the device and the 48 kHz PCM16 encode | `PASS` |
| 3 | The source sits where expected in the stereo field | channel swap or a dropped channel | `PASS` |
| 4 | Playback is free of clicks, gaps and dropouts | buffer or worklet boundary defects | `PASS` |
| 5 | A deliberately loud take is loud but not distorted | clipping in the float→PCM16 conversion | `PASS` |

Criterion 2 carries extra weight on this hardware: the AirPods Pro input runs
below 48 kHz while the Creator pins `new AudioContext({sampleRate: 48_000})`
(`capture_controller.ts:118`), so the resample path was under test and produced
no audible pitch or speed error. Criterion 5 was tested with
`autoGainControl: false` in force (`capture_controller.ts:62`), so the hot take
reached the encoder without browser gain reduction; the observation was "loud
and clean, no distortion".

Automation cannot reach any of these five. The Chromium fake device replays a
synthetic tone, which proves wiring and can never demonstrate audible
correctness.

## Behaviour confirmed by a human for the first time

- **Blur stops capture and retains the buffer.** A take was interrupted by the
  window losing focus at 14.9 s; capture stopped, the buffer survived intact
  into the trimming phase, and the panel displayed
  `Recording stopped: the window lost focus.`
  (`CAPTURE_BLUR_STOP_MESSAGE`). This is the S8B design, previously only
  asserted by the packaged Chromium journey.
- **The 5 s commit clamp holds against a longer buffer.** That 14.9 s capture
  committed as a Sample whose editor reported Start `0 s` and End `5 s`,
  matching `COMMIT_MAX_FRAMES` (240,000 frames) and the manifest
  `decoded_frames_per_pad`. The browser journeys assert the clamp against short
  fixtures; this is the first time it was observed clamping a buffer several
  times its size.

## Findings

Four findings surfaced during the session. All were reproduced and measured
before being recorded; none is fixed here, and each needs its own plan.

### F1. The capture panel has no styling and opens below the fold

`.capture-panel` has no rule in `apps/creator-web/src/styles.css`. The panel
renders as an unstyled flow element at the end of the Sample surface, after the
Pad grid, with no scroll-into-view and no focus move. Measured headlessly at
1440×900: panel box `y ≈ 790`, height `157`, document height `983`. In a real
Chrome window, whose viewport is shorter than the OS screen, the panel and its
`Record into Pad N` button land entirely below the fold.

Observed consequence: the operator pressed `Record Sample`, saw the button grey
out — correct, it is guarded by `captureSlot !== null` in
`sample_surface.tsx:633` — and concluded nothing had happened.

### F2. Stop is pushed off screen when recording starts

Same root cause. Entering the `recording` phase adds the level meter and the
waveform canvas, growing the panel from 157 px to 277 px measured, all of it
downward. The `Stop` button moves further below the fold and the page does not
scroll to follow it. The operator could not stop the take and it ran until the
window lost focus.

### F3. `DUPLICATE_ID` presents as a fatal error with no way out

Re-importing a bundle whose local Project has since diverged fails with
`DUPLICATE_ID`, which `error_panel.tsx:36` renders under the heading
`Creator unavailable` as "The Project conflicts with existing local data.",
with no recovery control — only `PROJECT_BUSY` and `HOST_RESTART_REQUIRED` are
given one.

Reproduced deterministically:

| Case | Outcome |
| --- | --- |
| Re-import an unmodified bundle whose local copy still matches | succeeds silently |
| Re-import after a committed capture advanced the local Project | `DUPLICATE_ID` |

No data is lost and the way out is one click away: `Open local` remains enabled
and opens the diverged Project correctly (verified: revision 7, 5 assigned
Pads, 2 Assets, Pad A5 assigned), and a plain reload also clears the error.
The defect is the presentation and the missing recovery affordance.

### F4. A silent default input commits silence with no indication

`capture_controller.ts:62` requests `{audio: {echoCancellation: false,
noiseSuppression: false, autoGainControl: false}}` with no `deviceId`, so
capture always follows the OS default input. The Creator shows no device
identity and offers no picker — the picker's absence is a **declared** scope
boundary for this Build, recorded on the `hosts/creator-web` portal page, so
F4 is not that omission.

What the session added is its physical consequence, which automation cannot
produce: when the default input silently changes, `getUserMedia` succeeds, the
stream carries digital silence, and the Creator commits a full 5 s of silence
onto a Pad with no input-level gate, no silence detection and no warning at any
point. The operator's only signal is the level meter, which F1 and F2 keep off
screen.

This needs a product decision, not just a fix: whether Pad Capture gets a
device picker, a visible input identity, an input-level gate before commit, or
some combination. It should not be settled inside an implementation Task.

## Environment note, not a product defect

The first take recorded pure silence. The cause was macOS Continuity routing
the system default input to a nearby iPhone while AirPods Pro were connected to
the MacBook; the iPhone microphone was not the intended source. Disconnecting
the iPhone restored the expected input and every subsequent take carried audio.

This is an environment condition and is **not** counted as a capture-chain
defect. It is recorded because it is what exposed F4, and because it is a
realistic failure mode for any macOS operator repeating this row.

## Commands used

```bash
npm --prefix apps/creator-web ci
scripts/creator-web.sh configure
scripts/creator-web.sh build
scripts/creator-web.sh package
scripts/creator-web.sh serve --port 4175
```

Headless measurements for F1–F3 were taken with Playwright against the same
served distribution; they are diagnostic support for the findings, not part of
the hearing evidence, which is human observation only.

## External state

| Transition | Status |
| --- | --- |
| Push | not performed at the time of writing |
| Pull Request | not created at the time of writing |
| Merge | not authorised / not performed |
| Product tag or GitHub Release | not authorised / not created |
| Deployment or publication | not authorised / not performed |
| Channel promotion | not authorised / not performed |
