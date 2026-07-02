# LMDJ Web Prototype 0702 Spec

Date: 2026-07-02
Status: written spec for review
Primary audience: internal product and engineering team

## 1. Purpose

This prototype defines an end-to-end web demo for the three core LMDJ links:

1. Generate music from a prompt.
2. Convert the generated music into a playable patch package.
3. Use MIDI-derived visual note cues to guide the user to perform the patch.

The goal is team alignment, not a polished investor page. The page should make the real system boundaries visible: prompt parameters, pipeline stages, generated package artifacts, Playable Patch construction, keyboard mapping, runtime behavior, and failure states.

## 2. Product Stance

V1 should prove the actual workflow:

```text
Prompt parameters
  -> live song-pipeline generation
  -> samples + chart.mid + lanes.json + report.json
  -> Playable Patch object
  -> Z X N M guided performance runtime
```

The prototype must not hide pipeline uncertainty. If generation or pipeline processing fails, the page stops and shows the failure. Static packages are allowed only as development fixtures and tests. They are not part of the main user path and must not auto-replace a failed live run.

## 3. Source Projects

The prototype sits under:

```text
/Users/jiafenggao/Desktop/root/Jiafeng/[05] ongoing projects 同步/Coding/LMDJ/webdemo0702/
```

It integrates with:

- `lmdj-song-pipeline`: live generation, source separation, loop finding, slicing, MIDI chart creation, validation, package output.
- `LMDJ/lmdj-pad-rhythm`: existing browser rhythm runtime concepts, MIDI parsing, sample playback, falling notes, timing judgment, replay.
- `LMDJ/docs/knowledge-base`: Playable Patch language and product principles.

## 4. V1 Modules

### 4.1 Prompt Builder

Prompt Builder collects reproducible generation parameters:

- `prompt`
- `bpm`
- `style`
- `duration`
- `seed`

Submission should create a real backend task. The task is equivalent to:

```bash
song-pipeline gen --bpm <bpm> --style "<style/prompt>" --seconds <duration> --seed <seed> --run
```

The backend should preserve the raw `prompt` and `style` fields for metadata, then construct the generation text deterministically. A simple V1 rule is:

```text
generation_style = "<style>, <prompt>"
```

The UI should show:

- submitted parameters
- `song_id`
- task start time
- current task state

The interface can be developer-facing. It does not need consumer-level simplification in V1.

### 4.2 Pipeline Monitor

Pipeline Monitor shows the live job lifecycle. Minimum states:

- `queued`
- `generating`
- `separating_stems`
- `finding_loop`
- `slicing_samples`
- `building_midi`
- `validating`
- `passed`
- `rejected`
- `failed`

If the existing pipeline API cannot emit every granular state immediately, V1 may approximate by polling `status.json` and displaying the best available coarse state, but the frontend state model should reserve these stages.

Debug information should be visible because this prototype is for team alignment:

- error message
- log excerpt or log link
- `report.status`
- `report.score`
- `report.threshold`
- `report.attempts`
- elapsed time

### 4.3 Patch Inspector

Patch Inspector turns the raw pipeline package into a Playable Patch view. It should display both engineering artifacts and the product object they imply.

Required package artifacts:

- `samples/*.wav`
- `chart.mid`
- `lanes.json`
- `report.json`
- `loop_preview.wav`
- `render_preview.wav`
- optional `status.json`

Required visible fields:

- package status
- `bpm`
- `loop_seconds`
- sample count
- MIDI note count
- lane list
- lane `kind`
- lane `pitch`
- lane sample path
- validation score
- attempts

Patch Inspector should label the result as a Playable Patch, not only as a file package. In V1, the Playable Patch object can be an in-memory normalized object derived from `lanes.json`, `chart.mid`, and `report.json`.

### 4.4 Performance Runtime

Performance Runtime reads the Playable Patch and creates a guided performance surface.

Required behavior:

- Load `chart.mid`.
- Load lane definitions from `lanes.json`.
- Load samples through the lane sample paths.
- Map playable lanes to fixed keys `Z X N M`.
- Render falling MIDI notes for playable lanes.
- Auto-trigger background lanes.
- Judge user input as `perfect`, `good`, or `miss`.
- Track hit rate, combo, misses, and triggered sample count.
- Record the take and allow replay.

The runtime can reuse the conceptual shape of `lmdj-pad-rhythm`, but V1 must adapt it from fixed local assets to a pipeline package.

## 5. Page Flow

The page is a linear three-step workflow.

### Step 1: Prompt To Music

The user enters prompt parameters and starts a real generation task. The page transitions to monitoring only after task creation succeeds.

Success output:

- `song_id`
- backend task state
- persisted generation parameters

Failure output:

- submitted parameters
- error message
- backend response, if available

### Step 2: Music To Playable Patch

The page monitors the pipeline until it reaches `passed`, `rejected`, or `failed`.

On `passed`, the page loads the package and shows Patch Inspector.

On `rejected`, the page stops before Performance Runtime and displays:

- score
- threshold
- attempts
- package artifacts that exist
- reason for rejection, if available

On `failed`, the page stops and displays:

- current stage
- error
- logs or debug details

No automatic fallback is allowed.

### Step 3: MIDI Guided Performance

The page starts runtime only after the package contract passes validation. The user plays with `Z X N M`.

At the end of the performance, the page displays:

- hit rate
- max combo
- miss count
- triggered sample count
- replay button
- restart or new generation button

## 6. Package Contract

The pipeline package is the frontend input contract:

```text
output/{song_id}/
  samples/*.wav
  chart.mid
  lanes.json
  report.json
  loop_preview.wav
  render_preview.wav
  status.json   optional
```

The frontend must read `lanes.json` before interpreting MIDI notes. It must not infer lane order from filenames.

### 6.1 `lanes.json`

`lanes.json` is the source of truth for lane-to-sample mapping.

Expected shape:

```json
{
  "bpm": 85.0,
  "bars": 4,
  "loop_seconds": 11.3081,
  "lanes": [
    {
      "lane": 0,
      "name": "kick",
      "kind": "drum",
      "pitch": 36,
      "sample": "samples/kick.wav"
    }
  ]
}
```

The frontend should support lane kinds:

- `drum`
- `long`
- `loop`

Unknown lane kinds should be visible in Patch Inspector and treated as non-playable unless explicitly mapped.

### 6.2 `chart.mid`

`chart.mid` provides timed note events. Every MIDI pitch used by the chart must exist in `lanes.json`.

Invalid cases:

- chart pitch missing from `lanes.json`
- note start time outside the loop duration in a way the runtime cannot handle
- missing or unreadable MIDI file

Any invalid case blocks Performance Runtime and shows an invalid package state.

### 6.3 `report.json`

`report.json` provides quality and debugging context.

Expected fields:

- `song_id`
- `status`
- `score`
- `threshold`
- `bpm`
- `loop_start_sec`
- `loop_seconds`
- `n_samples`
- `n_notes`
- `lanes`
- `attempts`
- `elapsed_sec`

Missing non-critical fields should display as unavailable. Missing `report.status` should block runtime. Missing `report.lanes` should not block runtime because `lanes.json` is the authoritative lane source.

## 7. Playable Patch Normalization

The frontend should normalize the package into a runtime object:

```json
{
  "id": "song_id",
  "title": "Generated patch",
  "mode": "performance",
  "intent": {
    "prompt": "...",
    "bpm": 85,
    "style": "...",
    "duration": 30,
    "seed": 42
  },
  "materials": {
    "samples": [],
    "loopPreview": "loop_preview.wav",
    "renderPreview": "render_preview.wav"
  },
  "sound": {
    "lanes": [],
    "chart": "chart.mid"
  },
  "ui": {
    "playableKeys": ["Z", "X", "N", "M"]
  },
  "runtime": {
    "bpm": 85,
    "loopSeconds": 11.3081,
    "score": 0.7635
  }
}
```

This object does not need to be saved to disk in V1, but the structure should be visible enough that the team can see how raw pipeline files become a LMDJ Playable Patch.

## 8. Z X N M Mapping

V1 fixed playable keys:

```text
Z X N M
```

Mapping rule:

1. Read `lanes.json.lanes`.
2. Pick up to four playable lanes.
3. Prefer lanes with `kind = drum`.
4. Then include `kind = long` or `kind = loop` by lane order.
5. Map selected lanes to `Z`, `X`, `N`, `M` in selected order.
6. Treat unselected lanes as background lanes.

Runtime behavior:

- Playable lane notes render as falling notes.
- Background lane notes auto-trigger their samples at the scheduled time.
- If fewer than four playable lanes exist, disable unused pads.
- If more than four lanes exist, Patch Inspector should show which lanes are playable and which are background.

This mapping is a frontend V1 strategy. It should not require changing pipeline pitch conventions.

## 9. Timing And Judgement

The runtime should use an audio-clock-aligned timing source.

Suggested V1 windows, inherited from the existing rhythm prototype:

- `perfect`: within about +/- 108 ms
- `good`: within about +/- 216 ms
- `miss`: later than the good window after the note passes

Falling notes should be readable and forgiving. This prototype proves guided performance, not competitive difficulty.

## 10. Error Handling

### 10.1 Generation Failure

Stop before pipeline inspection. Show:

- generation parameters
- current state
- error message
- retry action

### 10.2 Pipeline Rejected

Stop before Performance Runtime. Show:

- score
- threshold
- attempts
- candidate window details if available
- generated artifacts that exist

### 10.3 Pipeline Failed

Stop at Pipeline Monitor. Show:

- failed stage
- error message
- log excerpt or log link
- retry action

### 10.4 Invalid Package

Stop before runtime. Show:

- missing file list
- unknown MIDI pitches
- sample load failures
- JSON parse errors

### 10.5 Audio Unlock Failure

Stop at runtime start. Show that the browser needs a user gesture to start audio.

## 11. Static Fixtures

Static packages are allowed only for development and tests.

Allowed uses:

- package contract tests
- runtime development without waiting for Demucs or MusicGen
- screenshot and layout QA

Not allowed in the main V1 path:

- automatic fallback after live failure
- pretending a fixture is a fresh prompt result
- hiding rejected or failed pipeline output

## 12. API Requirements

The current `song-pipeline` API supports upload-based jobs. The web prototype needs prompt-generation jobs as well.

Recommended minimal API surface:

```http
GET /health
POST /songs/generate
GET /songs/{song_id}
GET /songs/{song_id}/package
```

`POST /songs/generate` request:

```json
{
  "prompt": "warm lofi groove for late night coding",
  "bpm": 85,
  "style": "lofi hiphop beat",
  "duration": 30,
  "seed": 42
}
```

Response:

```json
{
  "song_id": "gen_85bpm_42",
  "state": "queued"
}
```

Polling response:

```json
{
  "song_id": "gen_85bpm_42",
  "state": "validating",
  "stage": "validating",
  "report": null,
  "error": null
}
```

For V1, if granular backend stage events are not available, the API may return coarse states while the frontend still reserves the full state model.

## 13. Testing Checklist

### 13.1 API Health

- [ ] `/health` returns ok.
- [ ] Generation task can be submitted.
- [ ] Task can be polled by `song_id`.
- [ ] Passed task exposes a downloadable package.
- [ ] Failed task exposes error details.

### 13.2 Package Contract

- [ ] `lanes.json` parses.
- [ ] `report.json` parses.
- [ ] Every lane sample exists.
- [ ] Every MIDI pitch exists in `lanes.json`.
- [ ] Unsupported lane kinds do not crash the page.
- [ ] Rejected report blocks runtime.

### 13.3 Runtime Contract

- [ ] `Z X N M` map to selected playable lanes.
- [ ] Fewer than four playable lanes disables unused pads.
- [ ] More than four lanes marks unselected lanes as background.
- [ ] Background notes auto-play.
- [ ] Playable notes render as falling notes.
- [ ] Sample decode failures show package errors.

### 13.4 Performance Contract

- [ ] User hits produce sample playback.
- [ ] Correct hits mark `perfect` or `good`.
- [ ] Late notes mark `miss`.
- [ ] Hit rate, combo, misses, and triggered sample count update.
- [ ] Finished take can replay.

## 14. Non-Goals

- No investor landing page.
- No account system.
- No patch marketplace.
- No full DAW timeline.
- No automatic fixture fallback.
- No hardware MIDI input in V1.
- No mobile-first touch performance surface in V1.
- No claim that all generated outputs are commercially safe.

## 15. Open Implementation Questions

These should be resolved during implementation planning:

1. Whether `webdemo0702` is a new standalone Vite app or an adaptation of `lmdj-pad-rhythm`.
2. Whether the pipeline API should stream stage logs or write richer `status.json` snapshots.
3. Whether generated prompt metadata should be stored in package output or only in frontend state.
4. Whether the runtime should play one loop or repeat the loop for a fixed number of rounds.
5. Whether long/loop lanes should be playable by default when there are fewer than four drum lanes.
