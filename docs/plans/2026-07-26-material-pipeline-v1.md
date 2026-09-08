# Material Pipeline V1 Implementation Plan

> **Execution rule:** Implement this plan task by task with tests first. Keep
> `lmdj.materials.v1` internal to the Worker/Patchify boundary; API and Web must
> continue to consume only `patch.json` and export metadata.

**Goal:** Add an explicitly selectable, deterministic `materials-v1` creator
pipeline that produces up to 16 quality-gated materials in fixed slots, maps
them to `lmdj.patch.v1`, and preserves the legacy pipeline as the default.

**Architecture:** `packages/core-models` owns the material model, validation,
canonical serialization, and JSON Schema. The Audio Worker creates canonical
Timing and Material artifacts from original audio plus four canonical stems.
Patchify detects a Material Package and performs a pure fixed-slot conversion,
including deterministic MIDI. `CreatorPipelineRunner` orchestrates separation,
extraction, and Patchify while reporting stages. Web playback implements the
Phrase exclusive group from Patch behavior without reading `materials.json`.

**Tech stack:** Python 3.12, dataclasses, jsonschema, numpy/scipy/soundfile/
librosa, pretty_midi, FastAPI, React 19, TypeScript, Web Audio, Vitest.

## Global constraints

- Product code belongs under `packages/`, `workers/`, and `apps/`; do not edit
  the frozen reference demo.
- `lmdj.patch.v1` remains the only browser/API playback contract.
- Fixed slots are `Kick A, Snare A, Hat A, Percussion A, Bass A, Melody A,
  Vocal A, Phrase A, Kick B, Snare B, Hat B, Percussion B, Bass B, Melody B,
  Vocal B, Phrase B`.
- B cannot exist without the same-role A and must reference it with
  `variant_of`.
- Missing or rejected candidates produce explicit Empty slot decisions; they
  are never compacted or replaced with lower-quality material.
- All thresholds and DSP constants live in a versioned extraction config.
- `LMDJ_PIPELINE=legacy` remains the default. `materials-v1` failure is terminal
  for that Job and must never invoke legacy fallback.
- Canonical identities exclude Job IDs, timestamps, absolute paths, and
  filesystem ordering.
- Release/default-promotion evidence is documented honestly. Physical MIDI,
  fixed-corpus blind listening, and Ableton smoke are not claimed unless run.

---

### Task 1: Add the `lmdj.materials.v1` contract

**Files:**

- Create: `packages/core-models/lmdj_core_models/materials.py`
- Create:
  `packages/core-models/lmdj_core_models/schemas/lmdj.materials.v1.schema.json`
- Modify: `packages/core-models/lmdj_core_models/__init__.py`
- Create: `packages/core-models/tests/test_materials.py`
- Modify: `packages/core-models/tests/test_schema.py`

**Step 1: Write failing model and invariant tests**

Cover:

- canonical happy-path serialization and digest stability;
- schema identity and safe relative artifact/audio paths;
- accepted material count `1..16`;
- unique material IDs and slot indices;
- exact `slot_decisions` coverage of `0..15`;
- accepted/empty decision consistency;
- event references and `0 <= step < length_steps`;
- fixed role/source/kind/variant for each slot;
- B requires and references same-role A;
- one-shot only from `drums`;
- Vocal only from `vocals`;
- Phrase only from `original`, with `full_mix_exclusive`;
- stable empty reason-code enumeration.

Run:

```bash
packages/core-models/.venv/bin/python -m pytest \
  packages/core-models/tests/test_materials.py \
  packages/core-models/tests/test_schema.py -q
```

Expected: fail because the material contract does not exist.

**Step 2: Implement immutable material models**

Provide typed value objects for:

- `MaterialSource`;
- `MaterialProvenance`;
- `MaterialTiming`;
- `MaterialPlayback`;
- `MaterialQuality`;
- `Material`;
- `MaterialEvent`;
- `MaterialPattern`;
- `SlotDecision`;
- `MaterialPackage`.

Expose fixed slot descriptors and reason codes as shared constants. Keep
construction ergonomic, but put cross-record invariants in one
`validate_material_package()` function so loaders and producers share exactly
the same checks.

**Step 3: Implement canonical serialization and identity input**

Add:

- deterministic `to_dict()` ordering;
- canonical JSON bytes (`UTF-8`, sorted keys, compact separators);
- a `canonical_identity_bytes()` representation containing canonical timing,
  accepted materials, pattern events, and extraction config version.

The identity representation must not contain timestamps, Job paths, or the
final `patch_id`.

**Step 4: Add and validate the JSON Schema**

The schema should catch structural/type/enum failures. Python validation adds
the relational invariants that JSON Schema cannot express clearly. Include the
schema through the existing `schemas/*.json` package-data rule.

**Step 5: Run focused and package tests**

```bash
packages/core-models/.venv/bin/python -m pytest \
  packages/core-models/tests -q
```

Expected: all pass.

---

### Task 2: Add Material Package loading and fixed-slot Patchify

**Files:**

- Create: `packages/patchify/lmdj_patchify/material_loader.py`
- Create: `packages/patchify/lmdj_patchify/material_mapper.py`
- Create: `packages/patchify/lmdj_patchify/material_midi.py`
- Modify: `packages/patchify/lmdj_patchify/patchify.py`
- Modify: `packages/patchify/lmdj_patchify/cli.py`
- Create:
  `packages/patchify/tests/fixtures/material-package/materials.json`
- Create:
  `packages/patchify/tests/fixtures/material-package/timing.json`
- Create fixture WAV assets under:
  `packages/patchify/tests/fixtures/material-package/samples/`
- Create: `packages/patchify/tests/test_material_loader.py`
- Create: `packages/patchify/tests/test_material_patchify.py`
- Modify: `packages/patchify/tests/test_patchify.py`

**Step 1: Add a realistic deterministic fixture and failing tests**

The fixture contains accepted A materials, at least one valid B, a Phrase with
exclusive behavior, explicit Empty decisions, and pattern events. Tests assert:

- safe loading rooted at the package directory;
- schema plus relational validation;
- referenced files must exist and remain within the package;
- no `lanes.json` or pre-existing `chart.mid` is required;
- all 16 Patch pads retain their fixed index/name;
- accepted slots contain exactly one Element and live action;
- Empty slots use `action: "empty"`;
- Phrase behavior carries `exclusive_group: "full_mix_exclusive"`;
- Material events become Notes;
- MIDI is generated from those same events;
- repeated conversion is byte-stable and yields the same `patch_id`;
- existing legacy fixtures remain byte-compatible.

Use MIDI pitches `36 + slot_index` as the deterministic internal chart mapping;
Patch consumers still identify pads by slot/index and do not infer semantics
from pitch.

**Step 2: Implement strict Material loading**

Detect `materials.json` before selecting the loader. Parse through the shared
model/schema validation and resolve each relative path with package-root
confinement. Treat unreferenced accepted material, missing asset, traversal,
invalid decisions, or zero materials as contract errors.

**Step 3: Implement direct Material-to-Patch mapping**

Map solely by `slot_index`; do not infer role from filenames. Create:

- one Element per accepted Material;
- `trigger_element` live Pads for accepted slots;
- Empty Pads for empty decisions;
- one primary Pattern;
- one Scene covering all 16 slots.

Write playback details into Element/Pad behavior in a forward-compatible open
metadata object while retaining the frozen `lmdj.patch.v1` shape.

**Step 4: Generate deterministic chart MIDI**

Emit one MIDI track, fixed resolution/tempo from Material Timing, deterministic
event ordering, fixed note duration, and velocity from the canonical pattern.
The generated MIDI is an output, never an input to this path.

**Step 5: Derive the Material-path patch identity**

Use:

```text
{source_id}-{sha256(material_package.canonical_identity_bytes())[:8]}
```

Write `patch.json` and `chart.mid` atomically. Keep the legacy hash and loader
unchanged.

**Step 6: Run Patchify regression**

```bash
packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q
scripts/dev.sh smoke
```

Expected: Material and legacy tests pass; the legacy smoke result remains
unchanged.

---

### Task 3: Implement deterministic Timing and Material extraction

**Files:**

- Create: `workers/audio/lmdj_audio_worker/materials/__init__.py`
- Create: `workers/audio/lmdj_audio_worker/materials/config.py`
- Create: `workers/audio/lmdj_audio_worker/materials/timing.py`
- Create: `workers/audio/lmdj_audio_worker/materials/audio.py`
- Create: `workers/audio/lmdj_audio_worker/materials/extractor.py`
- Create: `workers/audio/lmdj_audio_worker/materials/package_writer.py`
- Create fixture audio under:
  `workers/audio/tests/fixtures/materials/`
- Create: `workers/audio/tests/materials/test_config.py`
- Create: `workers/audio/tests/materials/test_timing.py`
- Create: `workers/audio/tests/materials/test_extractor.py`
- Create: `workers/audio/tests/materials/test_determinism.py`

**Step 1: Define a versioned extraction configuration**

Centralize:

- quality threshold `0.70`;
- B difference threshold `0.25`;
- one-shot duration `80..600 ms`;
- loop candidates of one and two bars;
- silence, clipping, leakage, crossfade, onset, classification, and scoring
  constants;
- deterministic algorithm/config version identifiers.

Tests must fail if a producer uses an undeclared threshold.

**Step 2: Implement canonical Timing analysis**

Decode original input, normalize representation, detect beats, apply explicit
tempo range correction, select a deterministic principal window, and write
`timing.json` with:

- BPM/confidence;
- beats and bar boundaries;
- time signature;
- 16th-note grid;
- primary window;
- optional alternate windows;
- analyzer version.

Tie-breaking must use time/index ordering, not set/directory ordering. Add
tests for one-bar/two-bar boundaries and repeated output equality.

**Step 3: Implement audio safety helpers**

Provide deterministic decode/write, silence/clipping checks, DC removal, safe
normalization, short fades, equal-power loop crossfade, spectral bands,
centroid, transient features, and stable WAV output. Keep filesystem paths out
of scoring.

**Step 4: Implement drum candidate extraction**

- Detect onsets in the primary-window drums stem.
- Extract bounded one-shots.
- Classify candidates as kick/snare/hat/percussion using declared features.
- Apply hard gates, calculate quality, and select A by score then source time.
- Select B only when quality and normalized difference pass.
- Convert rejected/missing roles to stable Empty reasons.

Tests cover four A roles, B accepted/rejected, low quality, duration, and
silence.

**Step 5: Implement stem loop extraction**

For Bass, Melody, and Vocal:

- read only their canonical stem (`bass`, `other`, `vocals`);
- evaluate Timing-provided one/two-bar windows;
- apply hard gates and boundary/timing/energy/leakage/representativeness score;
- select A and a distinct B deterministically;
- crossfade only the accepted audio;
- never merge missing Vocal into Melody.

Tests cover aligned loop lengths, silent Vocal, invalid boundaries, and B
difference.

**Step 6: Implement original-mix Phrase extraction**

Select Phrase A/B from original audio windows, assign
`full_mix_exclusive`, and leave Phrase B empty when it is not distinct.

**Step 7: Produce Pattern events and the validated package**

Assign drum onsets to accepted same-role A/B prototypes; trigger accepted
Bass/Melody/Vocal A at step zero; leave B loops and Phrases manual. Write only
accepted WAV assets, then validate the full package before atomically replacing
`materials.json`.

Zero accepted materials is an error. Fewer than six, no Vocal, and no B are
valid without review warnings.

**Step 8: Verify determinism and Worker regression**

Run the same fixture three times and compare canonical `materials.json`, sample
SHA-256 values, events, and decisions.

```bash
workers/audio/.venv/bin/python -m pytest \
  workers/audio/tests/materials -q
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
```

Expected: all pass.

---

### Task 4: Add `CreatorPipelineRunner`, explicit selection, and stage/export integration

**Files:**

- Create: `workers/audio/lmdj_audio_worker/creator_runner.py`
- Modify: `workers/audio/lmdj_audio_worker/runner.py`
- Modify: `workers/audio/lmdj_audio_worker/job.py`
- Modify: `workers/audio/lmdj_audio_worker/status.py`
- Modify: `workers/audio/lmdj_audio_worker/export_source.py`
- Modify: `workers/audio/lmdj_audio_worker/cli.py`
- Create: `workers/audio/tests/test_creator_runner.py`
- Modify: `workers/audio/tests/test_job.py`
- Modify: `workers/audio/tests/test_export_source.py`
- Modify: `apps/api/lmdj_api/app.py`
- Modify: `apps/api/lmdj_api/export_builder.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/tests/test_app.py`
- Modify: `apps/api/tests/test_export_builder.py`

**Step 1: Write failing orchestration tests**

Use fake separator/timing/extractor/Patchify components to assert:

- exact stages `queued → separating → extracting → patchifying → completed`;
- status files remain valid at every transition;
- canonical four-stem validation occurs before extraction;
- pipeline provenance is stored with the Job/package;
- `materials-v1` exceptions produce `failed` and never call legacy;
- `legacy` behavior and state sequence remain compatible;
- an unknown `LMDJ_PIPELINE` value fails application startup/configuration;
- selection is captured for each new Job, not re-read mid-run.

**Step 2: Implement `CreatorPipelineRunner`**

Orchestrate:

1. canonical Timing analysis from original audio;
2. configured Separator execution and four-stem validation;
3. Material extraction/package validation;
4. return the Material Package directory for Patchify.

Inject components so unit tests do not require a model checkpoint. Keep the
real separator chosen through the existing registry/runner protocol.

**Step 3: Add stage-aware Worker execution**

Extend the runner boundary with an optional stage callback or a dedicated
stage-aware protocol. `process_job()` owns status persistence and Patchify;
the runner only reports when separation is complete and extraction starts.
Legacy runners continue to work without synthetic `extracting`.

**Step 4: Add explicit pipeline configuration**

Resolve once during API application construction:

```text
legacy       -> DemoPipelineRunner
materials-v1 -> CreatorPipelineRunner
```

Default to `legacy`. Reject all other values. Store the chosen identifier in
Job provenance/status before execution.

**Step 5: Extend Export Source without exposing Material truth**

Export inventory may list actual Timing, Stems, Samples, chart MIDI, music
information, and provenance. Do not add a public route that serves
`materials.json`; do not make the export builder derive Patch behavior from it.

**Step 6: Run Worker/API regressions**

```bash
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
apps/api/.venv/bin/python -m pytest apps/api/tests -q
```

Expected: all pass.

---

### Task 5: Implement Web Phrase-exclusive playback

**Files:**

- Modify: `apps/web/src/engine/AudioEngine.ts`
- Modify: `apps/web/src/engine/AudioEngine.test.ts`
- Modify: `apps/web/src/test/fakes.ts`
- Modify: `apps/web/src/ui/useEngine.ts`
- Modify: `apps/web/src/ui/ProcessingPanel.tsx`
- Modify: `apps/web/src/ui/ProcessingPanel.test.tsx`
- Modify related Patch/Pad tests only if the open behavior typing requires it.

**Step 1: Write failing playback tests**

Assert:

- a Phrase source loops and stops every active ordinary source;
- triggering any ordinary material stops active
  `full_mix_exclusive` sources;
- retriggering the same loop replaces its earlier source;
- one-shots may overlap ordinary loops;
- Empty, missing audio, and reserved actions remain no-op;
- engine stop/patch replacement stops all active sources;
- `extracting` has a known progress label.

**Step 2: Track active Web Audio sources**

Extend the minimal source contract with `stop()` and loop support. Track active
sources by Element and exclusive group, remove ended nodes, and tolerate
already-stopped browser nodes. Read behavior only from validated Patch data.

**Step 3: Implement bidirectional Phrase exclusivity**

- Phrase trigger: stop all ordinary active nodes, then start the Phrase loop.
- Ordinary trigger: stop the `full_mix_exclusive` group, then start the
  ordinary one-shot/loop.
- Missing or undecodable Element: preserve the existing safe warning/no-op.

**Step 4: Run Web contract/test/build**

```bash
cd apps/web
npm test
npm run check-contract
npm run build
```

Expected: all pass.

---

### Task 6: Document implementation/release boundaries and verify the slice

**Files:**

- Modify: `docs/superpowers/2026-07-10-status-and-backlog.md`
- Modify: `docs/prd/decision-log.md`
- Create:
  `docs/superpowers/evidence/2026-07-26-material-pipeline-v1.md`

**Step 1: Record the contract and rollout decision**

Document:

- `lmdj.materials.v1` is internal;
- fixed slots and A/B rule;
- canonical identity inputs;
- explicit pipeline selection;
- default remains `legacy`;
- no silent fallback;
- default promotion is a later release decision.

**Step 2: Record machine-verifiable evidence**

Include exact commands/results for:

- core-models;
- Patchify plus legacy smoke;
- Worker;
- API;
- Web tests/contract/build;
- deterministic fixture repeated three times;
- a real local materials-v1 Job using a small deterministic test input.

Clearly mark fixed-corpus blind listening, physical MIDI controllers, and
Ableton Live smoke as **not run / release gate open**.

**Step 3: Run the full local regression**

```bash
packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q
packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
apps/api/.venv/bin/python -m pytest apps/api/tests -q
cd apps/web && npm test && npm run check-contract && npm run build
scripts/dev.sh smoke
```

Expected: all pass.

**Step 4: Inspect and commit the isolated Material slice**

Stage only this plan's files, inspect the diff and file list, then create one
Conventional Commit:

```text
feat(pipeline): add material pipeline v1
```

Do not push, merge, deploy, or promote the default pipeline.

---

### Task 7: Integrate with the queue-productionization slice

Perform this task only after the Material slice is independently green.

**Step 1: Create a fresh integration branch/worktree**

Branch from current `origin/main`, then apply the verified queue and Material
commits. Keep the two source branches intact.

**Step 2: Reconcile shared Worker/API/Web surfaces**

Expected intersections:

- durable queue-created initial status plus pipeline provenance;
- `interrupted` and `extracting` state unions;
- stage-aware execution inside the single FIFO worker;
- App upload recovery/task queue plus Processing UI labels;
- API construction/config tests.

The queue owns scheduling/capacity/idempotency/recovery. The Material pipeline
owns creator stage transitions and artifact production. Do not weaken either
contract to resolve a merge conflict.

**Step 3: Add integration-only tests**

Cover:

- two `materials-v1` submissions remain FIFO and report queue positions;
- queued position changes when the first job enters `extracting`;
- restart marks the active Material job `interrupted`;
- idempotency returns the original Material job;
- Material failure is terminal and does not invoke legacy;
- a completed Material job loads only its Patch in Web and obeys Phrase
  exclusivity.

**Step 4: Run the complete regression and real browser acceptance**

Run all Task 6 commands, then exercise:

- multiple uploads;
- capacity and queue position;
- refresh recovery;
- duplicate idempotency;
- interrupted restart;
- visible `extracting`;
- 16 fixed pads with real Empty positions;
- ordinary ↔ Phrase bidirectional exclusivity;
- export inventory including real Timing/Stems/Samples/MIDI.

**Step 5: Commit the final integration version**

Commit only integration-resolution/tests/evidence files if the two feature
commits apply cleanly. Use a separate Conventional Commit such as:

```text
test(integration): verify queued material pipeline
```

No push, PR, merge, deployment, or default promotion is authorized by this
plan.
