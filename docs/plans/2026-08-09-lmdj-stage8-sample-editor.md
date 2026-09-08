# LMDJ Stage 8 Sample Editor Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Product Build `1.0.22.0 · canary` with a formal Sample mode that imports or replaces bounded PCM16 WAV artifacts, edits per-Pad playback truth, renders a deterministic waveform, and auditions all four trigger modes through the existing Application Facade and realtime Web Runtime.

**Architecture:** Extend Authoring Domain and Project I/O with dual-read `lmdj.project.v1`/`lmdj.project.v2` truth and atomic Sample mutations; extend Project Cooker with deterministic WAV analysis, waveform envelopes, 44.1→48 kHz preparation, and resolved playback values; extend Audio Runtime with fixed-size press/release/preview control messages. Application Facade remains the typed authority for Sample queries and mutations, Web Runtime Platform transports those operations without parsing Project Truth, and Creator owns only selected Pad, viewport, gesture draft, pending action, and render state.

**Tech Stack:** C++20, CMake 3.24+, nlohmann/json, Emscripten `6.0.5`, WasmFS OPFS, fixed `536,870,912`-byte SharedArrayBuffer memory, Wasm AudioWorklet, JavaScript ES modules, React `19.2.8`, TypeScript `7.0.2`, Vite `8.2.1`, Vitest `4.1.10`, Testing Library React `16.3.2`, Playwright `1.62.1`, Python 3.11, JSON Schema 2020-12, Docusaurus Architecture Portal.

## Global Constraints

- The approved design is `docs/design/2026-08-08-lmdj-stage8-sample-editor-design.md`. A conflict returns to design review; implementation must not silently weaken it.
- Execute on `feat/stage8-sample-editor` in `/Users/endaye/Projects/lmdj/.worktrees/stage8-sample-editor`, stacked from Stage 7 commit `4da1cd3dc3b25901427d5dfe924d124404e30f85`. Never implement on `main` or in the Stage 7 worktree.
- Stage 8 development may remain stacked, but its PR cannot merge before `feat/stage7-creator-editor` is merged into `main`. Before version integration, fetch `origin/main`, verify the Stage 7 merge commit is its ancestor, then rebase Stage 8 onto that merged baseline.
- Creator uses Web Runtime Platform and Application Facade only. It must not parse Project JSON, read a Project checkpoint or OPFS directly, decode WAV, or hold a writable Project copy.
- Project Truth reads `lmdj.project.v1` `1.0.0` and `lmdj.project.v2` `2.0.0`; successful Authoring mutation writes v2. Open, inspect, cook, and audition of v1 are read-only projections and do not increment revision.
- Per-Pad playback belongs to the Pad Slot, not the Asset. Unassign, Replace, and Reset produce explicit defaults; one Asset may have distinct playback on multiple Pads.
- Accepted input is RIFF/WAVE integer PCM16, mono/stereo, 44,100 or 48,000 Hz. MIME and filename are hints only; the Core validates bytes. Original bytes and SHA-256 remain the immutable Artifact identity.
- Use the active Web manifest limits as authority: imported WAV bytes `1,048,576`, decoded source frames per Pad `240,000`, prepared float PCM per Bank `67,108,864`, total live prepared PCM `134,217,728`, and fixed Wasm heap `536,870,912`. Do not copy these values into a second host-local policy object.
- Waveform output is a zero-centred mirrored max-absolute envelope derived from Artifact bytes. Cache data, viewport, playhead, active Voice, loop latch, and audition override never enter Project Truth or Runtime Snapshot.
- Runtime audio-thread work remains allocation-free, lock-free, non-blocking, and Project-I/O-free. Changing its fixed SPSC message shape requires explicit unit and stress coverage.
- Every Authoring mutation carries `command_id` and `expected_revision`; there is no auto-rebase, last-write-wins, localStorage command queue, or optimistic success.
- A committed Project followed by failed Cook is reported as saved truth plus stale Runtime. Do not fabricate rollback. Retry Prepare is explicit.
- Blur, hidden visibility, suspend, non-persisted page hide, Host restart, Project reopen, Replace, Reset, or Mute of a sounding Pad stops the applicable active and latched Voices.
- Stage 8 excludes recording, input permission, Take/Pattern authoring, Slice, Stem, Pitch, Reverse, Pan, envelopes, time-stretch, Asset deletion/GC, Undo/Redo, PWA, cloud, account, deployment, and Channel promotion.
- Do not read, write, wrap, translate, or emit retired `lmdj.patch.v1` or `lmdj.materials.v1` data.
- Every implementation Task is one reviewable Conventional Commit. Keep active manifests unchanged until the version-integration Task so intermediate commits retain coherent current truth.
- Before every commit: verify the branch is not `main`; run the Task tests and `scripts/architecture-portal.sh check`; stage only declared files; inspect `git diff --cached --name-status`, `git diff --cached --check`, and the staged diff; commit; inspect `git show --name-status --oneline HEAD`; confirm no Task residue remains.
- This plan authorizes local commits only. Push, PR, merge, tag, tag push, Release, publication, deployment, and Channel promotion each require separate authorization.

## Locked Core Interfaces

### Project Truth and Authoring Commands

`packages/authoring-domain/include/lmdj/domain/project.hpp` gains these exact value types:

```cpp
enum class ProjectContract : std::uint8_t { v1, v2 };
enum class TriggerMode : std::uint8_t {
  one_shot,
  gate,
  loop_gate,
  loop_toggle,
};

struct PadPlayback {
  std::uint64_t trim_start_frame = 0;
  std::optional<std::uint64_t> trim_end_frame = std::nullopt;
  TriggerMode trigger_mode = TriggerMode::one_shot;
  std::int32_t gain_millidb = 0;
  bool muted = false;
  bool operator==(const PadPlayback&) const = default;
};

struct PadSlot {
  PadSlotId id;
  std::optional<foundation::AssetId> asset_id;
  PadPlayback playback;
  bool operator==(const PadSlot&) const = default;
};
```

`ProjectState` gains `ProjectContract contract`. A v1 parser returns `contract == v1` and injects `PadPlayback{}` for all 64 Pads in memory. A successful command returns `contract == v2`; failed or duplicate replay does not create a second migration revision.

`packages/authoring-domain/include/lmdj/domain/commands.hpp` adds:

```cpp
struct ImportAssignSample {
  CommandMeta meta;
  Asset asset;
  PadSlotId slot;
};

struct UpdatePadPlayback {
  CommandMeta meta;
  PadSlotId slot;
  PadPlayback playback;
};

struct ResetPadPlayback {
  CommandMeta meta;
  PadSlotId slot;
};
```

`AssignPad` resets playback to `PadPlayback{}` when unassigning or assigning a different Asset. `ImportAssignSample` inserts the immutable Asset, assigns it, and resets playback in one `apply()` result and one revision.

### Deterministic Audio Analysis and Preparation

`packages/project-cooker/include/lmdj/cooker/sample_analysis.hpp` exports:

```cpp
inline constexpr std::uint32_t kWaveformAlgorithmVersion = 1;

struct WavMetadata {
  std::uint32_t sample_rate;
  std::uint16_t channels;
  std::uint64_t source_frames;
};

struct WaveformRequest {
  std::uint64_t start_frame;
  std::uint64_t end_frame;
  std::uint32_t bucket_count;
};

struct PeakBucket {
  std::uint64_t start_frame;
  std::uint64_t end_frame;
  std::uint16_t peak_magnitude;
};

struct WaveformEnvelope {
  WavMetadata metadata;
  std::uint32_t algorithm_version;
  std::vector<PeakBucket> buckets;
};

foundation::Result<WavMetadata> inspect_wav(
    std::span<const std::byte> bytes);
foundation::Result<WaveformEnvelope> waveform_envelope(
    const PcmSample& sample,
    const WaveformRequest& request);
foundation::Result<std::shared_ptr<const PcmSample>> prepare_runtime_pcm(
    const PcmSample& source);
```

Peak magnitude is `max(abs(sample))` across every channel and source frame in the bucket, with `INT16_MIN` represented as `32768`. Facade queries accept `bucket_count` in `1..512`. For a non-empty window, `frames_per_bucket = ceil((end_frame - start_frame) / bucket_count)`; bucket `i` is `[start_frame + i * frames_per_bucket, min(end_frame, start_frame + (i + 1) * frames_per_bucket))`. The response uses at most `min(bucket_count, end_frame - start_frame)` non-empty buckets. Full-source cache levels are aligned to source frame zero; partial boundary buckets are computed from decoded PCM so a window query never reuses an over-wide peak.

For 44.1 kHz input, prepared output frame `j` samples rational source position `j * 44,100 / 48,000`. Adjacent PCM16 values are linearly interpolated with signed 64-bit integer weights and symmetric nearest-integer rounding; the last source frame is clamped. Prepared frame count and source-boundary mapping are:

```cpp
prepared_frames = ceil(source_frames * 48'000 / source_rate);
runtime_start = floor(source_start * 48'000 / source_rate);
runtime_end = ceil(source_end * 48'000 / source_rate);
```

48 kHz input is copied exactly. The Cooker validates `runtime_start < runtime_end <= prepared_frames` and puts only prepared 48 kHz PCM into the immutable Snapshot.

### Runtime Playback and Preview

`ResolvedPad` gains a complete resolved playback value:

```cpp
struct ResolvedPlayback {
  std::uint32_t start_frame;
  std::uint32_t end_frame;
  domain::TriggerMode trigger_mode;
  float linear_gain;
  bool muted;
};
```

`gain_millidb` converts once on the control thread with `pow(10.0, millidb / 20000.0)` and is checked for finiteness. `PreparedSampleBank` stores PCM and `ResolvedPlayback` together.

`packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp` adds a trivially-copyable fixed control message:

```cpp
enum class PadControlKind : std::uint8_t {
  press,
  release,
  stop_slot,
  stop_all,
  preview_set,
  preview_clear,
};

struct PadControlEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
  PadControlKind kind;
  cooker::ResolvedPlayback playback;
};

enum class RuntimeVoiceState : std::uint8_t {
  started,
  stopped,
  completed,
};

struct RuntimeVoiceStateEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  RuntimeVoiceState state;
  std::uint64_t runtime_frame;
  std::uint32_t source_frame;
};
```

`enqueue(TriggerEvent)` remains as a compatibility wrapper for a `press` using published playback. New `enqueue_control(PadControlEvent)` is the sole Stage 8 control path. Preview values are session-local fixed-array entries and never mutate a `PreparedSampleBank` or Project. A second fixed SPSC ring carries Voice start/stop/completion edges to the control thread; the Browser interpolates the visual playhead from authoritative `runtime_frame`, `source_frame`, sample rate, and selection bounds, and clears/resynchronizes it on each later edge. It never polls or writes the audio thread.

### Application Facade Sample Surface

The typed `Application` API is authoritative; JSON/C ABI operations delegate to it:

```cpp
struct SampleInspectRequest {
  std::filesystem::path project_path;
  domain::PadSlotId slot;
};

struct SampleInspectResult {
  std::uint64_t project_revision;
  domain::PadSlotId slot;
  std::optional<foundation::AssetId> asset_id;
  domain::PadPlayback playback;
  std::optional<cooker::WavMetadata> metadata;
  std::optional<std::string> waveform_cache_identity;
};

struct SampleWaveformRequest {
  std::filesystem::path project_path;
  domain::PadSlotId slot;
  cooker::WaveformRequest window;
};

struct SampleMutationResult {
  std::uint64_t committed_revision;
  bool runtime_prepare_required;
};

struct SampleUpdateRequest {
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  domain::PadSlotId slot;
  domain::PadPlayback playback;
};

struct SampleResetRequest {
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  domain::PadSlotId slot;
};

struct SampleImportBeginRequest {
  std::string import_token;
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  domain::PadSlotId slot;
  foundation::AssetId asset_id;
  std::uint64_t byte_length;
};

struct SampleImportSession {
  std::string token;
  std::uint64_t expected_bytes;
};

foundation::Result<SampleInspectResult> inspect_sample(
    const SampleInspectRequest& request) const;
foundation::Result<cooker::WaveformEnvelope> query_sample_waveform(
    const SampleWaveformRequest& request);
foundation::Result<SampleImportSession> begin_sample_import(
    const SampleImportBeginRequest& request);
foundation::Result<void> append_sample_import(
    std::string_view token,
    std::uint64_t offset,
    std::span<const std::byte> bytes,
    bool final);
foundation::Result<SampleMutationResult> commit_sample_import(
    std::string_view token);
foundation::Result<void> abort_sample_import(std::string_view token);
foundation::Result<SampleMutationResult> update_sample_pad(
    const SampleUpdateRequest& request);
foundation::Result<SampleMutationResult> reset_sample_pad(
    const SampleResetRequest& request);
```

The Application Facade JSON/C ABI operation names are exactly:

```text
sample.inspect
sample.waveform
sample.import.begin
sample.import.chunk
sample.import.commit
sample.import.abort
sample.update_pad
sample.reset_pad
```

The Web Host protocol additionally exposes Runtime-only operations that do not enter `Application::command()` and are not Authoring Commands:

```text
sample.preview.set
sample.preview.clear
sample.stop
snapshot.retry
```

Import uses existing `1,048,576`-byte bridge sidecars in bounded chunks. `sample.import.commit` acquires the writer lease, revalidates `expected_revision`, validates the complete WAV, atomically publishes Artifact + Asset + Pad defaults + one v2 revision, prepares/publishes the new Snapshot, then deletes staging. Abort, malformed input, conflict, deadline cancellation before publication claim, and pre-commit I/O failure delete or scavenge staging without Project change.

### Browser Runtime Session

`createRuntimeSession()` adds the following Host-neutral methods while retaining every Stage 7 method:

```ts
inspectSample(slot: number): Promise<SampleInspect>;
queryWaveform(request: WaveformQuery): Promise<WaveformEnvelope>;
importAssignSample(file: File, options: SampleImportOptions): Promise<SampleCommit>;
updatePad(request: SampleUpdateRequest): Promise<SampleCommit>;
resetPad(request: SampleResetRequest): Promise<SampleCommit>;
setSamplePreview(slot: number, playback: PadPlayback): Promise<boolean>;
clearSamplePreview(slot: number): Promise<boolean>;
release(slot: number, source: RuntimeTriggerSource): Promise<boolean>;
stopPad(slot: number): Promise<boolean>;
stopAll(): Promise<boolean>;
retryPrepare(patternId: string): Promise<SnapshotPublication>;
subscribeVoiceState(listener: (event: RuntimeVoiceState) => void): () => void;
```

The Runtime Session accepts no Project path. It binds operations to the currently opened Project and returns exact typed error codes. It serializes Sample mutations with Project open/import actions; it does not retry `REVISION_CONFLICT`.

## File Structure

### Contracts, Domain, Persistence

- `contracts/project/lmdj.project.v2.schema.json`: exact-key v2 Project Contract with complete playback on all Pads.
- `tests/fixtures/contracts/project-v2-valid.json`: canonical valid v2 fixture.
- `tests/fixtures/contracts/project-v2-invalid-playback.json`: out-of-range and contradictory playback fixture.
- `packages/authoring-domain/include/lmdj/domain/project.hpp`: contract identity, trigger mode, Pad playback.
- `packages/authoring-domain/include/lmdj/domain/commands.hpp`: import-assign, update, and reset Commands.
- `packages/authoring-domain/src/project.cpp`: default and playback validators.
- `packages/authoring-domain/src/command_handler.cpp`: migration-on-success, one-revision, replay, assignment reset.
- `packages/project-io/include/lmdj/project_io/project_store.hpp`: dual-read/v2-write and atomic Sample byte import.
- `packages/project-io/src/project_store.cpp`: canonical serialization, transaction, recovery, staging cleanup.
- `packages/project-io/include/lmdj/project_io/workspace_cache.hpp` and `src/workspace_cache.cpp`: generated-key derived cache byte store over the existing Native/Web storage abstraction.
- Project I/O native/Web storage tests: identical v1/v2 and cancellation guarantees.

### Analysis, Cooker, Runtime

- `packages/project-cooker/include/lmdj/cooker/sample_analysis.hpp` and `src/sample_analysis.cpp`: strict PCM16 analysis, waveform envelope, deterministic resampling.
- `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`: resolved trim/mode/gain/mute.
- `packages/project-cooker/src/wav_reader.cpp`: 44.1/48 kHz strict decoder.
- `packages/project-cooker/src/project_cooker.cpp`: playback validation and source-to-runtime mapping.
- `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp` and `src/prepared_sample_bank.cpp`: prepared PCM plus per-slot playback.
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp` and `src/realtime_engine.cpp`: fixed Pad control queue, trigger semantics, preview, stop boundaries.

### Facade and Web Runtime Platform

- `packages/application-facade/include/lmdj/facade/application.hpp`: typed Sample DTOs and streaming session methods.
- `packages/application-facade/src/application.cpp`: validation, cache identity/query, atomic command orchestration, privacy-safe envelopes.
- `packages/application-facade/src/c_api.cpp`: unchanged generic C ABI transport with parity coverage for new operations.
- `packages/web-runtime-platform/web/protocol.mjs`: operation allowlist, deadlines, bounded Sample sidecar declarations.
- `packages/web-runtime-platform/src/control_runtime.cpp`: current-Project binding, mutation/runtime two-stage results, preview and stop routing.
- `packages/web-runtime-platform/web/runtime_session.mjs`: typed Sample methods, chunk streaming, cancellation, conflict, Cook-failed behavior.
- `packages/web-runtime-platform/web/input_adapters.mjs`: press/release symmetry without key repeat.

### Creator Host and Proof

- `apps/creator-web/src/runtime/runtime_types.ts`: Sample transport/view types.
- `apps/creator-web/src/runtime/sample_actions.ts`: inspect/query/import/update/reset/retry journeys and response validation.
- `apps/creator-web/src/state/sample_state.ts`: selected Pad, waveform viewport, draft, pending mutation, saved/runtime revisions.
- `apps/creator-web/src/components/sample_surface.tsx`: Sample mode composition.
- `apps/creator-web/src/components/waveform_editor.tsx`: SVG envelope, handles, playhead, zoom/pan/Fit and keyboard control.
- `apps/creator-web/src/components/sample_controls.tsx`: trigger/loop, Volume, Mute, Reset, Replace.
- Existing App, Mode Rail, Pad Surface, state, input, report, styles, unit and browser tests: Stage 8 integration without a second Project model.
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`: packaged Chromium positive Proof and WebKit capability boundary.
- `docs/quality/2026-08-09-stage8-sample-editor-acceptance.md`: automated and manual evidence ledger.

## Documentation Impact

Documentation impact: required

Affected portal routes: `/`, `/core/overview/`, `/core/modules/authoring-domain/`, `/core/modules/project-io/`, `/core/modules/project-cooker/`, `/core/modules/audio-runtime/`, `/core/modules/application-facade/`, `/core/modules/web-runtime-platform/`, `/hosts/overview/`, `/hosts/creator-web/`, `/contracts/project/`, `/platform/web-runtime/`, `/platform/input/`, `/platform/storage/`, `/assembly/lmdj/`, `/operations/testing-and-proof/`, and `/operations/version-and-release/`, plus their source diagrams and generated current outputs.

Update `docs/prd/decision-log.md` with the approved Stage 8 parameter/ownership decisions. Remove the resolved “Sampler Edit 第一版最小参数集” row from `docs/prd/open-questions.md`. Record Stage 8B Pad Capture as a named, unimplemented, unversioned future stage. Documentation must distinguish design approval, implementation, immutable canary snapshot, automated Proof, manual hearing/touch evidence, physical pass, Beta, Stable, and release.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

The live merged baseline at Task 12 integration is Product Build `1.0.20.0`.
The target remains a new minor Build because Stage 8 adds Product behavior and
a Project Contract. Patch-only Host targets below were advanced from this live
baseline after the earlier planned identities were consumed by merged Stage 6
hardening builds.

| Identity | Current stacked baseline | Planned target | API | Reason |
| --- | --- | --- | --- | --- |
| Product Build | `1.0.20.0` | `1.0.22.0` | n/a | New Project Contract and complete Sample mode. |
| `lmdj.project.v1` | `1.0.0` | unchanged | n/a | Legacy read/import remains supported. |
| `lmdj.project.v2` | absent | `2.0.0` | n/a | Complete per-Pad playback and forward migration. |
| `authoring-domain` | `0.1.1` | `0.2.0` | stays 1 | New Project value and Commands. |
| `project-io` | `0.5.4` | `0.6.0` | stays 1 | Dual-read/v2-write and atomic Sample transaction. |
| `project-cooker` | `0.2.1` | `0.3.0` | stays 1 | Analysis, waveform, resampling, resolved playback. |
| `audio-runtime` | `0.4.1` | `0.5.0` | stays 1 | Trigger modes, preview, stop controls. |
| `application-facade` | `1.3.5` | `1.4.0` | stays 2 | Typed Sample query/mutation surface. |
| `web-runtime-platform` | `0.2.1` | `0.3.0` | stays 1 | Typed Sample transport and audition lifecycle. |
| `creator-web` | `1.1.2` | `1.2.0` | stays 1 | Enables formal Sample mode. |
| `web-runtime-host` | `1.2.8` | `1.2.9` | stays 1 | Exact Platform dependency propagation only. |
| `core-cli` | `1.0.11` | `1.0.12` | stays 2 | Exact Facade dependency propagation only. |
| `core-mcp` | `1.1.8` | `1.1.9` | stays 2 | Exact Facade dependency/Python identity propagation only. |
| `native-test-host` | `1.0.9` | `1.0.10` | stays 1 | Exact Facade dependency and parity coverage. |
| `lmdj.project-bundle.v1` | `1.0.0` | unchanged | n/a | Imports v1 only; Stage 8 adds no bundle export. |
| `lmdj.error.v1` | `1.0.0` | unchanged | n/a | Existing typed errors are sufficient. |

- Before writing any identity, fetch and read merged `origin/main`, `products/lmdj/version.json`, all affected manifests, and the immutable snapshot inventory. If any planned identity was consumed, revise this table and every downstream reference to the next legal identity before editing files.
- Regenerate `products/lmdj/assembly.lock.json` only with `python3 scripts/version.py lock`; never hand-edit it.
- From a clean committed source boundary run `scripts/architecture-portal.sh version 1.0.22.0 canary`. The immutable snapshot is a separate commit from current-truth integration.
- Future tag text is `lmdj-v1.0.22.0`; tag creation and push are outside this plan's local authorization.
- Rollback is a forward-compatible corrective build that retains v2 readers and Core behavior while disabling faulty Creator mutation entry. Never overwrite migrated workspaces with a `1.0.20.0` artifact or downgrade v2 truth to v1.

---

### Task 1: Add Project v2 and per-Pad playback to Authoring Domain

**Files:**
- Create: `contracts/project/lmdj.project.v2.schema.json`
- Create: `tests/fixtures/contracts/project-v2-valid.json`
- Create: `tests/fixtures/contracts/project-v2-invalid-playback.json`
- Modify: `packages/authoring-domain/include/lmdj/domain/project.hpp`
- Modify: `packages/authoring-domain/include/lmdj/domain/commands.hpp`
- Modify: `packages/authoring-domain/src/project.cpp`
- Modify: `packages/authoring-domain/src/command_handler.cpp`
- Modify: `tests/core/domain/project_test.cpp`
- Modify: `tests/core/domain/command_handler_test.cpp`
- Modify: `tests/conformance/schema_contract_test.py`
- Modify: `tests/conformance/json_schema_test.py`

**Interfaces:**
- Consumes: existing `CommandMeta`, `PadSlotId`, `Asset`, and exact-key v1 schema rules.
- Produces: `ProjectContract`, `TriggerMode`, `PadPlayback`, `ImportAssignSample`, `UpdatePadPlayback`, and `ResetPadPlayback` exactly as locked above.

- [ ] **Step 1: Write failing Contract and domain tests**

```cpp
const auto initial = lmdj::domain::create_project(project_id, 120).value();
LMDJ_CHECK(initial.contract == lmdj::domain::ProjectContract::v1);
LMDJ_CHECK(initial.banks[0][0].playback == lmdj::domain::PadPlayback{});

const auto updated = lmdj::domain::apply(initial, UpdatePadPlayback{
    {command_id, 0}, {0, 0}, {10, 90, TriggerMode::loop_gate, -1200, false}}, {}).value();
LMDJ_CHECK(updated.state.contract == ProjectContract::v2);
LMDJ_CHECK(updated.state.revision == 1);
LMDJ_CHECK(updated.state.banks[0][0].playback.trim_start_frame == 10);
```

Add exact positive tests for all four trigger modes, gain endpoints `-60000` and `6000`, nullable End, independent Pads sharing one Asset, assignment reset, duplicate replay, and one-revision import-assign. Add negative tests for out-of-range gain, zero-length resolved selection, invalid enum input, missing Asset, and stale revision.

- [ ] **Step 2: Run the focused tests and confirm they fail for absent v2 types/schema**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'domain\.(project|command_handler)|contract\.schema_validator' --output-on-failure
python3 tests/conformance/json_schema_test.py
```

Expected: compile failure for the new C++ types and schema failure because `lmdj.project.v2` is absent.

- [ ] **Step 3: Implement the exact v2 schema and domain values**

Use exact keys on every v2 Pad and playback object. Keep `trim_end_frame` nullable, require `gain_millidb` in `[-60000, 6000]`, and enumerate only `one_shot`, `gate`, `loop_gate`, `loop_toggle`. Domain validation checks shape/ranges that do not need decoded Artifact metadata; Facade/Cooker later resolve `trim_end_frame` against frame count.

- [ ] **Step 4: Implement migration-on-success command semantics**

Make `apply()` copy the state, validate expected revision first, apply exactly one mutation, set `contract = v2`, and increment once. Replay returns the recorded outcome without a second revision. `AssignPad`, `ImportAssignSample`, and `ResetPadPlayback` install `PadPlayback{}` at their specified reset boundaries.

- [ ] **Step 5: Run Task 1 verification**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'domain\.(project|command_handler)|contract\.schema_validator' --output-on-failure
python3 tests/conformance/json_schema_test.py
scripts/architecture-portal.sh check
```

Expected: all selected tests and Portal check pass; active manifests still describe the Stage 7 build.

- [ ] **Step 6: Commit Task 1**

```bash
git add contracts/project/lmdj.project.v2.schema.json \
  tests/fixtures/contracts/project-v2-valid.json \
  tests/fixtures/contracts/project-v2-invalid-playback.json \
  packages/authoring-domain/include/lmdj/domain/project.hpp \
  packages/authoring-domain/include/lmdj/domain/commands.hpp \
  packages/authoring-domain/src/project.cpp \
  packages/authoring-domain/src/command_handler.cpp \
  tests/core/domain/project_test.cpp \
  tests/core/domain/command_handler_test.cpp \
  tests/conformance/schema_contract_test.py \
  tests/conformance/json_schema_test.py
git commit -m "feat(project): define per-pad playback truth"
```

### Task 2: Persist v1 input and atomic v2 Sample mutations

**Files:**
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Create: `packages/project-io/include/lmdj/project_io/workspace_cache.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Create: `packages/project-io/src/workspace_cache.cpp`
- Modify: `packages/project-io/CMakeLists.txt`
- Modify: `packages/project-io/src/native/storage_platform.cpp`
- Modify: `packages/project-io/src/web/storage_platform.cpp`
- Modify: `packages/project-io/src/web/library_opfs_storage.js`
- Modify: `packages/project-io/src/testing_hooks.hpp`
- Modify: `tests/core/project_io/project_store_test.cpp`
- Modify: `tests/core/project_io/fault_matrix_test.cpp`
- Modify: `tests/core/project_io/storage_platform_contract_test.cpp`
- Modify: `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- Modify: `tests/platform/web/project_io/project_io_web_faults.mjs`

**Interfaces:**
- Consumes: Task 1 `ProjectState.contract` and Sample Commands.
- Produces: dual-read canonical persistence, `ProjectStore::import_assign_sample_bytes()` with one Project transaction, and a generated-key `WorkspaceCacheStore` for derived bytes outside Project Truth.

`ProjectStore::import_assign_sample_bytes()` accepts the request below and executes `ImportAssignSample` in the same publication transaction as immutable Artifact creation:

```cpp
struct ImportAssignSampleBytesRequest {
  domain::CommandMeta meta;
  domain::PadSlotId slot;
  foundation::AssetId asset_id;
  std::string media_type;
  std::span<const std::byte> bytes;
};
```

`WorkspaceCacheStore::read(key)` returns optional bytes, `write(key, bytes)` atomically replaces one generated entry, and `remove(key)` deletes one generated entry. Keys must match `[a-z0-9][a-z0-9._/-]{0,254}` with no empty, dot, or traversal segments; callers use Artifact hashes and algorithm identities, never user filenames.

- [ ] **Step 1: Write failing dual-read and migration tests**

```cpp
const auto opened = store.load(v1_project).value();
LMDJ_CHECK(opened.contract == ProjectContract::v1);
LMDJ_CHECK(read_manifest_bytes(v1_project) == original_manifest);

const auto committed = store.execute(v1_project, UpdatePadPlayback{
    {command_id, opened.revision}, {0, 0}, PadPlayback{}}).value();
LMDJ_CHECK(committed.state.contract == ProjectContract::v2);
LMDJ_CHECK(committed.state.revision == opened.revision + 1);
LMDJ_CHECK(parse_manifest(v1_project).at("contract") == "lmdj.project.v2");
```

Cover recovery from old/new checkpoints, exact-key rejection, v2 round trip, no write on load, duplicate command replay, conflict, lease failure, replace failure, and crash points before/after manifest publication.

- [ ] **Step 2: Write failing atomic import-assign fault tests**

Inject failure after staging, Artifact creation, event preparation, and manifest preparation. At every pre-publication failure assert original manifest bytes, revision, Pad assignment, and Asset map are unchanged; orphan staging is removed by bounded startup scavenging.

- [ ] **Step 3: Run the focused persistence tests and confirm failure**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'project_io\.(project_store|fault_matrix|storage_platform)' --output-on-failure
```

Expected: v2 parsing/writing and atomic Sample import assertions fail.

- [ ] **Step 4: Implement canonical v1/v2 codecs and one-transaction import**

Dispatch parsing by exact `contract`. Encode v1 only for untouched v1 state; encode v2 after any successful Authoring mutation. Reuse the existing manifest/event/checkpoint transaction and immutable Artifact publication. The new import method verifies expected revision inside the held writer lease and never calls public `import_artifact()` followed by a second `execute()`.

- [ ] **Step 5: Implement bounded Sample staging and scavenging on Native/Web storage**

Use generated token directories under the validated Workspace staging root. Reject traversal, symlink, wrong offset, over-limit bytes, duplicate finalization, and token reuse. Cleanup enumerates only generated names and removes only incomplete entries older than the configured bounded age.

- [ ] **Step 6: Implement the generated-key Workspace cache store**

Route read/write/remove through `ProjectStoragePlatform`; validate the cache root and every generated segment before I/O. Atomic replacement must not require or acquire a Project writer lease. Corrupt/missing cache bytes return a cache miss to Facade after bounded removal and never become Project errors.

- [ ] **Step 7: Run Task 2 verification**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'project_io\.(project_store|fault_matrix|storage_platform)' --output-on-failure
bash scripts/web-toolchain-conformance.sh test
scripts/architecture-portal.sh check
```

Expected: Native and Web persistence contracts pass with no v1 open-side write.

- [ ] **Step 8: Commit Task 2**

```bash
git add -- packages/project-io/include/lmdj/project_io/project_store.hpp \
  packages/project-io/include/lmdj/project_io/workspace_cache.hpp \
  packages/project-io/src/project_store.cpp \
  packages/project-io/src/workspace_cache.cpp packages/project-io/CMakeLists.txt \
  packages/project-io/src/native/storage_platform.cpp \
  packages/project-io/src/web/storage_platform.cpp \
  packages/project-io/src/web/library_opfs_storage.js \
  packages/project-io/src/testing_hooks.hpp \
  tests/core/project_io/project_store_test.cpp \
  tests/core/project_io/fault_matrix_test.cpp \
  tests/core/project_io/storage_platform_contract_test.cpp \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs \
  tests/platform/web/project_io/project_io_web_faults.mjs
git commit -m "feat(project-io): migrate sample mutations atomically"
```

### Task 3: Add strict WAV analysis, waveform envelopes, and deterministic preparation

**Files:**
- Create: `packages/project-cooker/include/lmdj/cooker/sample_analysis.hpp`
- Create: `packages/project-cooker/src/sample_analysis.cpp`
- Modify: `packages/project-cooker/CMakeLists.txt`
- Modify: `packages/project-cooker/include/lmdj/cooker/wav_reader.hpp`
- Modify: `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`
- Modify: `packages/project-cooker/src/wav_reader.cpp`
- Modify: `packages/project-cooker/src/project_cooker.cpp`
- Modify: `tests/fixtures/audio/make_fixtures.py`
- Modify: `tests/fixtures/audio/hashes.json`
- Create: `tests/fixtures/audio/mono-44100.wav`
- Create: `tests/core/cooker/sample_analysis_test.cpp`
- Modify: `tests/core/cooker/project_cooker_test.cpp`
- Modify: `tests/core/cooker/determinism_matrix_test.cpp`

**Interfaces:**
- Consumes: Task 1 playback values and existing `PcmSample`/Artifact resolver.
- Produces: locked analysis API, deterministic prepared PCM, and `ResolvedPlayback` in Runtime Snapshot.

- [ ] **Step 1: Generate and lock deterministic fixtures**

Extend the existing fixture generator with mono/stereo 44.1/48 kHz impulses, ramps, `INT16_MIN`, malformed duplicate chunks, incorrect byte rate/block align, unsupported rate/bits/float, and over-limit declarations. Record SHA-256 in `hashes.json`; do not hand-edit binary fixtures.

- [ ] **Step 2: Write failing analysis and golden-vector tests**

```cpp
const auto envelope = waveform_envelope(*decoded, {0, 8, 4}).value();
LMDJ_CHECK(envelope.algorithm_version == 1);
LMDJ_CHECK(envelope.buckets == std::vector<PeakBucket>({
    {0, 2, 32768}, {2, 4, 8192}, {4, 6, 4096}, {6, 8, 0}}));

const auto prepared = prepare_runtime_pcm(*mono_44100).value();
LMDJ_CHECK(prepared->sample_rate == 48'000);
LMDJ_CHECK(prepared->interleaved == expected_integer_linear_vector);
```

Test stereo max-abs folding, exact bucket coverage, invalid/oversized windows, deterministic repeated output, 48 kHz byte-equivalent PCM, and the locked floor/ceil trim mapping.

- [ ] **Step 3: Run focused Cooker tests and confirm failure**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'cooker\.(sample_analysis|project|determinism_matrix)' --output-on-failure
```

Expected: the new target/API is absent and existing decoder rejects 44.1 kHz.

- [ ] **Step 4: Implement strict decode, envelope, and integer-rational preparation**

Keep RIFF/fmt/data exact validation in one parser path. `inspect_wav`, `waveform_envelope`, and `prepare_runtime_pcm` consume that decoded result; do not add a second WAV parser. Use checked 64-bit multiplication/addition before allocation and return `UNSUPPORTED_AUDIO` for format rejection.

- [ ] **Step 5: Resolve playback into the immutable Runtime Snapshot**

Cook validates assigned Pad selection against source frames, prepares 48 kHz PCM once per Artifact SHA, maps trim boundaries, converts gain, and copies mode/mute. Pattern Events continue to reference only `PadSlotId`.

- [ ] **Step 6: Run Task 3 verification**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'cooker\.(sample_analysis|project|determinism_matrix)' --output-on-failure
scripts/architecture-portal.sh check
```

Expected: all exact golden vectors and repeated determinism runs pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add -- packages/project-cooker/include/lmdj/cooker/sample_analysis.hpp \
  packages/project-cooker/src/sample_analysis.cpp \
  packages/project-cooker/CMakeLists.txt \
  packages/project-cooker/include/lmdj/cooker/wav_reader.hpp \
  packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp \
  packages/project-cooker/src/wav_reader.cpp \
  packages/project-cooker/src/project_cooker.cpp \
  tests/fixtures/audio/make_fixtures.py tests/fixtures/audio/hashes.json \
  tests/fixtures/audio/mono-44100.wav \
  tests/core/cooker/sample_analysis_test.cpp \
  tests/core/cooker/project_cooker_test.cpp \
  tests/core/cooker/determinism_matrix_test.cpp
git commit -m "feat(cooker): prepare sample playback deterministically"
```

### Task 4: Implement realtime trigger modes and audition controls

**Files:**
- Modify: `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/src/prepared_sample_bank.cpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `packages/audio-runtime/src/offline_renderer.cpp`
- Modify: `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- Modify: `tests/core/audio/prepared_sample_bank_test.cpp`
- Modify: `tests/core/audio/realtime_engine_test.cpp`
- Modify: `tests/core/audio/realtime_engine_stress_test.cpp`
- Modify: `tests/core/audio/offline_renderer_test.cpp`
- Modify: `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
- Modify: `tests/platform/web/audio/realtime_failure.spec.mjs`

**Interfaces:**
- Consumes: Task 3 `ResolvedPlayback` and prepared 48 kHz mono/stereo input.
- Produces: fixed `PadControlEvent` queue and exact one-shot/gate/loop-gate/loop-toggle behavior.

- [ ] **Step 1: Write failing mode and gain tests**

For each mode render deterministic blocks and assert cursor/voice behavior: one-shot ignores release; gate stops on release; loop-gate wraps inside `[start,end)` and stops on release; loop-toggle stops only on its next press. Selecting another Pad does not stop a latched loop-toggle Voice. Assert mute produces no Voice, gain scales PCM, selection never reads outside bounds, and Voice start/stop/completion edges carry the exact slot, sequence, Runtime frame, and source frame needed by active indicators and playhead interpolation.

Extend offline rendering assertions so Pattern-triggered Pads use the same trim, gain, and mute values from `ResolvedPlayback`; offline Pattern rendering treats each Pattern Event as a one-shot start and does not invent persisted gate-release or loop-latch events.

- [ ] **Step 2: Write failing preview and lifecycle tests**

Set a preview with a shorter trim and lower gain, trigger, clear it, and prove the next trigger uses published playback. Assert queue overflow rejects preview, `stop_slot` stops only the target, `stop_all` clears ordinary and latched Voices, and control/Voice-state ring overflow fails closed under the documented telemetry policy.

- [ ] **Step 3: Run tests and confirm failure**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'audio\.(prepared_sample_bank|realtime_engine)' --output-on-failure
```

Expected: release/loop/preview APIs are absent.

- [ ] **Step 4: Implement fixed prepared values and control messages**

Keep vectors and ownership on the control side. The audio callback reads fixed arrays and trivially-copyable messages only. A Voice snapshots effective playback at press time, so clearing a draft does not mutate an already-rendering Voice; explicit `stop_slot` handles Replace/Reset/Mute boundaries.

- [ ] **Step 5: Run unit, browser audio, and explicit stress verification**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'audio\.(prepared_sample_bank|realtime_engine)' --output-on-failure
scripts/core.sh test dev stress
bash scripts/web-runtime-host.sh test
scripts/architecture-portal.sh check
```

Expected: component and stress tiers pass with zero queue/data-race regressions.

- [ ] **Step 6: Commit Task 4**

```bash
git add -- packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp \
  packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp \
  packages/audio-runtime/src/prepared_sample_bank.cpp \
  packages/audio-runtime/src/realtime_engine.cpp \
  packages/audio-runtime/src/offline_renderer.cpp \
  packages/audio-runtime/src/web/realtime_audio_worklet.cpp \
  tests/core/audio/prepared_sample_bank_test.cpp \
  tests/core/audio/realtime_engine_test.cpp \
  tests/core/audio/realtime_engine_stress_test.cpp \
  tests/core/audio/offline_renderer_test.cpp \
  tests/platform/web/audio/realtime_audio_worklet.spec.mjs \
  tests/platform/web/audio/realtime_failure.spec.mjs
git commit -m "feat(audio): add sample trigger and preview controls"
```

### Task 5: Expose typed Sample queries and mutations through Application Facade

**Files:**
- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/src/c_api.cpp`
- Modify: `packages/application-facade/src/testing_hooks.hpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/c_api_test.cpp`
- Modify: `tests/core/facade/c_api_stress_test.cpp`
- Modify: `tests/host/cli_test.py`
- Modify: `tests/host/mcp_stdio_test.py`
- Modify: `tests/host/mcp_facade_parity_test.py`
- Modify: `tests/host/native_host_test.py`
- Modify: `tests/host/native_host_source_boundary_test.py`

**Interfaces:**
- Consumes: Tasks 2–3 Project transaction and analysis APIs.
- Produces: locked typed Sample DTOs, JSON operations, staging lifecycle, and C ABI parity.

- [ ] **Step 1: Write failing typed Facade tests**

```cpp
const auto inspected = application.inspect_sample({project, {0, 0}}).value();
LMDJ_CHECK(inspected.project_revision == 0);
LMDJ_CHECK(inspected.playback == PadPlayback{});

const auto updated = application.update_sample_pad({
    project, {command_id, 0}, {0, 0}, playback}).value();
LMDJ_CHECK(updated.committed_revision == 1);
```

Cover v1 inspect-without-write, waveform cache miss/hit identity, import/replace/reset, duplicate/revision conflict, missing Asset, invalid selection, staging abort/scavenge, and saved-revision/Cook-failed separation.

- [ ] **Step 2: Write C ABI exact-shape and privacy tests**

Send every `sample.*` operation through `lmdj_core_request`; reject unknown keys, invalid UTF-8, invalid UUID/slot/revision, excessive bucket/window/sidecar sizes, filename/path fields, and raw bytes in JSON. Assert public errors contain code and bounded approved details only.

- [ ] **Step 3: Run focused Facade/Host parity tests and confirm failure**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'facade\.(application|c_api)' --output-on-failure
python3 tests/host/mcp_facade_parity_test.py
```

Expected: Sample operations are rejected as unknown.

- [ ] **Step 4: Implement typed methods first, then JSON delegation**

Typed methods resolve the Pad and Artifact, validate metadata through Cooker, use Project I/O for authoritative mutation, and return DTOs. JSON handlers only parse exact input, call typed methods, and serialize the result. C ABI remains the existing generic request function; do not export operation-specific C symbols.

- [ ] **Step 5: Implement bounded derived waveform cache**

Cache key is `sha256/algorithm-version/max-abs-mirror/frames-per-bucket`; cache records include source metadata and bucket count. Store under validated Workspace cache, never Project. Reject corrupt/mismatched entries and rebuild deterministically; cache write failure may degrade to computed response but cannot fail or mutate Project truth.

- [ ] **Step 6: Run Task 5 verification**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'facade\.(application|c_api)|host\.(cli|mcp|native)' --output-on-failure
python3 tests/host/mcp_facade_parity_test.py
scripts/architecture-portal.sh check
```

Expected: typed and C ABI paths return equivalent Sample results; Hosts remain Facade-only.

- [ ] **Step 7: Commit Task 5**

```bash
git add -- packages/application-facade/include/lmdj/facade/application.hpp \
  packages/application-facade/src/application.cpp \
  packages/application-facade/src/c_api.cpp \
  packages/application-facade/src/testing_hooks.hpp \
  tests/core/facade/application_test.cpp tests/core/facade/c_api_test.cpp \
  tests/core/facade/c_api_stress_test.cpp tests/host/cli_test.py \
  tests/host/mcp_stdio_test.py tests/host/mcp_facade_parity_test.py \
  tests/host/native_host_test.py \
  tests/host/native_host_source_boundary_test.py
git commit -m "feat(facade): expose atomic sample editing"
```

### Task 6: Extend Web Control Runtime and protocol for Sample editing

**Files:**
- Modify: `packages/web-runtime-platform/web/protocol.mjs`
- Modify: `packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`
- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/src/bridge.cpp`
- Modify: `packages/web-runtime-platform/src/web-runtime-pre.js`
- Modify: `packages/web-runtime-platform/test/protocol.test.mjs`
- Modify: `packages/web-runtime-platform/test/control_runtime_test.cpp`
- Modify: `packages/web-runtime-platform/test/realtime_session_test.cpp`
- Modify: `packages/web-runtime-platform/test/source_boundary_test.py`

**Interfaces:**
- Consumes: Task 4 realtime controls and Task 5 Facade operations.
- Produces: validated Host protocol and authoritative current-Project binding for every Sample operation.

- [ ] **Step 1: Write failing protocol allowlist and exact-payload tests**

Add all locked operations to `HOST_OPERATIONS`. Assert `sample.import.chunk` accepts one verified sidecar up to `MAX_ASSET_BYTES`, JSON never contains sample bytes, and project deadlines apply to mutation/query while preview/stop use the short deadline.

- [ ] **Step 2: Write failing Control Runtime journeys**

Open a real v1 fixture, inspect without migration, stream a WAV, commit to one v2 revision, publish a Snapshot, query waveform, preview trim, update on release, inject conflict, inject Cook failure, retry Prepare, Reset, stop latched audio, and observe Voice state notifications. Assert the Host never accepts a browser-supplied Project path.

- [ ] **Step 3: Run focused Platform tests and confirm failure**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'host\.web_(control_runtime|realtime_session)' --output-on-failure
node --test packages/web-runtime-platform/test/protocol.test.mjs
```

Expected: protocol rejects new operations and Control Runtime has no routes.

- [ ] **Step 4: Implement current-session dispatch and two-stage mutation results**

Bind Sample calls to `retained_project_path`, current Project/Pattern identity, and held writer lifecycle. A mutation response contains `committed_revision`, `runtime_revision`, `runtime_published`, and optional normalized `snapshot_error`. On Cook failure keep old bank/generation and return saved truth explicitly.

- [ ] **Step 5: Route fixed preview/release/stop controls**

Validate complete playback payloads, flatten slots only after range checks, and call `enqueue_control`. Queue-full or unavailable Runtime fails closed; it never becomes a Project mutation or fake Voice outcome.

- [ ] **Step 6: Run Task 6 verification**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'host\.web_(control_runtime|realtime_session)' --output-on-failure
node --test packages/web-runtime-platform/test/protocol.test.mjs
python3 packages/web-runtime-platform/test/source_boundary_test.py
scripts/architecture-portal.sh check
```

Expected: all protocol, control, source-boundary, deadline, and lifecycle tests pass.

- [ ] **Step 7: Commit Task 6**

```bash
git add -- packages/web-runtime-platform/web/protocol.mjs \
  packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp \
  packages/web-runtime-platform/src/control_runtime.cpp \
  packages/web-runtime-platform/src/bridge.cpp \
  packages/web-runtime-platform/src/web-runtime-pre.js \
  packages/web-runtime-platform/test/protocol.test.mjs \
  packages/web-runtime-platform/test/control_runtime_test.cpp \
  packages/web-runtime-platform/test/realtime_session_test.cpp \
  packages/web-runtime-platform/test/source_boundary_test.py
git commit -m "feat(web-runtime): transport sample editing safely"
```

### Task 7: Add typed Runtime Session Sample journeys and lifecycle cleanup

**Files:**
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/input_adapters.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `packages/web-runtime-platform/test/input_adapters.test.mjs`
- Modify: `packages/web-runtime-platform/test/state_machine.test.mjs`

**Interfaces:**
- Consumes: Task 6 Host operations.
- Produces: the locked Browser Runtime Session methods, serialized mutation lane, and release/stop lifecycle.

- [ ] **Step 1: Write failing Runtime Session tests**

Use the injected transport to assert exact envelopes and ordering for inspect, waveform, chunked import/abort, update, reset, preview set/clear, release, stop, retry, and Voice state subscription. Test picker abort before begin, AbortSignal during chunking, mutation conflict without retry, and `COOK_FAILED` with saved/runtime revisions.

- [ ] **Step 2: Write failing release and cleanup tests**

Assert key repeat does not press again, pointerup/keyup emits release, pointercancel/Escape clears preview without mutation, and blur/visibility/suspend/page lifecycle calls `stopAll()` once per adverse edge.

- [ ] **Step 3: Run Node tests and confirm failure**

```bash
node --test packages/web-runtime-platform/test/runtime_session.test.mjs \
  packages/web-runtime-platform/test/input_adapters.test.mjs \
  packages/web-runtime-platform/test/state_machine.test.mjs
```

Expected: methods and release transport are absent.

- [ ] **Step 4: Implement bounded import and serialized mutation ownership**

Generate token/command/Asset UUIDs with injected crypto; stream `File.slice()` chunks; attach AbortSignal; call abort exactly once on cancellation/failure after begin. Reuse the existing serialized Project action tail so open/import/sample mutations cannot overlap on stale revision.

- [ ] **Step 5: Implement preview and lifecycle cleanup**

Track active preview slots in a bounded Set of 64. Clearing is idempotent. Any terminal/adverse lifecycle first clears pressed inputs and previews, then sends `stopAll`, then follows existing suspend/close state transitions.

- [ ] **Step 6: Run Task 7 verification**

```bash
node --test packages/web-runtime-platform/test/*.test.mjs
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'host\.web_' --output-on-failure
scripts/architecture-portal.sh check
```

Expected: all Platform Node/native tests pass without regressing Stage 7 Project/trigger journeys.

- [ ] **Step 7: Commit Task 7**

```bash
git add -- packages/web-runtime-platform/web/runtime_session.mjs \
  packages/web-runtime-platform/web/input_adapters.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  packages/web-runtime-platform/test/input_adapters.test.mjs \
  packages/web-runtime-platform/test/state_machine.test.mjs
git commit -m "feat(web-runtime): add sample session journeys"
```

### Task 8: Add Creator Sample state and validated actions

**Files:**
- Create: `apps/creator-web/src/state/sample_state.ts`
- Create: `apps/creator-web/src/runtime/sample_actions.ts`
- Create: `apps/creator-web/test/sample_state.test.ts`
- Create: `apps/creator-web/test/sample_actions.test.ts`
- Modify: `apps/creator-web/src/runtime/runtime_types.ts`
- Modify: `apps/creator-web/src/state/creator_state.ts`
- Modify: `apps/creator-web/src/state/view_model.ts`
- Modify: `apps/creator-web/src/runtime/input_controller.ts`
- Modify: `apps/creator-web/test/input_controller.test.ts`

**Interfaces:**
- Consumes: Task 7 Runtime Session methods.
- Produces: Creator-owned render/draft state with no writable Project document.

- [ ] **Step 1: Write failing reducer and response-validation tests**

```ts
const draft = beginSampleDraft(savedSample, 42);
const moved = updateSampleDraft(draft, {trimStartFrame: 120});
expect(moved.baseRevision).toBe(42);
expect(moved.proposed.trimStartFrame).toBe(120);
expect(moved.dirty).toBe(true);
```

Cover selected Pad, v1 default projection, v2 inspect, waveform window, viewport Fit/zoom/pan bounds, discrete mutation pending state, saved/runtime revision split, conflict refresh, Cook failure, and cancellation. Reject extra/missing keys, invalid modes, unsafe integers, unbounded buckets, raw Project documents, paths, filenames, and sample bytes.

- [ ] **Step 2: Run Creator unit tests and confirm failure**

```bash
npm --prefix apps/creator-web test -- --run sample_state sample_actions input_controller
```

Expected: Sample modules/types are absent.

- [ ] **Step 3: Implement orthogonal state and action journeys**

Store only `SampleInspect`, `WaveformEnvelope`, selected slot, viewport, gesture draft, pending action, bounded Voice/playhead render state, last error, saved revision, and runtime revision. `commitDraft` sends one complete playback at release; conflict clears preview, re-inspects, and exposes “Project changed; review and try again” without replay.

- [ ] **Step 4: Make input release mode-aware**

Assigned Pad press still selects and triggers. Gate/loop-gate release calls `session.release`; one-shot release only clears visual pressed state; loop-toggle second press stops. Empty Pad selection is surfaced to the App for file picking rather than treated as disabled audio input.

- [ ] **Step 5: Run Task 8 verification**

```bash
npm --prefix apps/creator-web test -- --run
python3 packages/web-runtime-platform/test/source_boundary_test.py
scripts/architecture-portal.sh check
```

Expected: Creator unit suite passes and no Project parser/storage import appears in Creator source.

- [ ] **Step 6: Commit Task 8**

```bash
git add -- apps/creator-web/src/state/sample_state.ts \
  apps/creator-web/src/runtime/sample_actions.ts \
  apps/creator-web/test/sample_state.test.ts \
  apps/creator-web/test/sample_actions.test.ts \
  apps/creator-web/src/runtime/runtime_types.ts \
  apps/creator-web/src/state/creator_state.ts \
  apps/creator-web/src/state/view_model.ts \
  apps/creator-web/src/runtime/input_controller.ts \
  apps/creator-web/test/input_controller.test.ts
git commit -m "feat(creator): model sample editing state"
```

### Task 9: Build the accessible waveform editor and Sample controls

**Files:**
- Create: `apps/creator-web/src/components/waveform_editor.tsx`
- Create: `apps/creator-web/src/components/sample_controls.tsx`
- Create: `apps/creator-web/src/components/sample_surface.tsx`
- Create: `apps/creator-web/test/waveform_editor.test.tsx`
- Create: `apps/creator-web/test/sample_controls.test.tsx`
- Modify: `apps/creator-web/src/components/mode_rail.tsx`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/styles.css`
- Modify: `apps/creator-web/test/workspace_shell.test.tsx`

**Interfaces:**
- Consumes: Task 8 state/actions.
- Produces: enabled Sample mode, mirrored waveform, complete controls, and Desktop/Tablet layout.

- [ ] **Step 1: Write failing component accessibility tests**

Assert Sample mode is enabled and keyboard reachable; Project/Sequence/Perform state remains correct; waveform SVG path mirrors peaks around a zero line; Start/End handles and numeric inputs expose Pad/time labels; every Pad/handle/toggle/confirm action has at least 44 px hit target in computed CSS.

- [ ] **Step 2: Write failing interaction tests**

Exercise pointer drag preview without mutation, one release commit, Escape/pointercancel/unmount cancellation, Arrow one-frame increment, Shift+Arrow nearest 10 ms increment, non-crossing handles, Zoom In/Out/Fit, pan bounds, Loop label switching One Shot↔Hold, Mute, Volume step `0.1`, Reset confirmation, and suspended-audio edit copy.

- [ ] **Step 3: Run component tests and confirm failure**

```bash
npm --prefix apps/creator-web test -- --run waveform_editor sample_controls workspace_shell
```

Expected: Sample components are absent and Sample mode remains disabled.

- [ ] **Step 4: Implement waveform SVG and controls**

Build the SVG only from validated integer peak buckets. Use one path mirrored above/below centre, separate dim masks outside selection, visible handles/playhead, and focusable HTML controls for every pointer gesture. Viewport state remains local and never calls a mutation action.

- [ ] **Step 5: Compose the fixed Sample layout**

Order content as selected Pad metadata/Replace, waveform, controls/Reset, Bank selector, complete 4×4 Pads. Desktop uses labeled Rail; Tablet uses icons with accessible names. Do not hide Pads in a carousel.

- [ ] **Step 6: Run Task 9 verification**

```bash
npm --prefix apps/creator-web test -- --run
npm --prefix apps/creator-web run build
scripts/architecture-portal.sh check
```

Expected: unit/accessibility tests and production TypeScript build pass.

- [ ] **Step 7: Commit Task 9**

```bash
git add -- apps/creator-web/src/components/waveform_editor.tsx \
  apps/creator-web/src/components/sample_controls.tsx \
  apps/creator-web/src/components/sample_surface.tsx \
  apps/creator-web/test/waveform_editor.test.tsx \
  apps/creator-web/test/sample_controls.test.tsx \
  apps/creator-web/src/components/mode_rail.tsx \
  apps/creator-web/src/app.tsx apps/creator-web/src/styles.css \
  apps/creator-web/test/workspace_shell.test.tsx
git commit -m "feat(creator): build the sample editor surface"
```

### Task 10: Complete Pad import, Replace, lifecycle, and evidence behavior

**Files:**
- Modify: `apps/creator-web/src/components/pad_surface.tsx`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/runtime/runtime_context.tsx`
- Modify: `apps/creator-web/src/report/acceptance_report.ts`
- Modify: `apps/creator-web/test/audio_lifecycle.test.tsx`
- Modify: `apps/creator-web/test/runtime_context.test.tsx`
- Modify: `apps/creator-web/test/acceptance_report.test.ts`
- Modify: `apps/creator-web/test/workspace_shell.test.tsx`
- Modify: `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`

**Interfaces:**
- Consumes: Tasks 7–9 Session/actions/UI.
- Produces: end-to-end file/pad/lifecycle interaction and privacy-safe report evidence.

- [ ] **Step 1: Write failing import/Replace tests**

Test empty Pad click opens an accept-filtered picker, cancellation is a no-op, drag/drop uses identical validation, assigned Pad requests confirmation containing escaped bounded display name and reset warning, cancel preserves revision, confirm stops the Pad then atomically replaces it, unsupported audio keeps selection and shows accepted format.

- [ ] **Step 2: Write failing lifecycle and stale-runtime tests**

Assert Replace/Mute/Reset stop sounding target Pad; blur/hidden/suspend/restart/reopen stop all including loop-toggle; audio suspended permits commit and shows “Activate Audio to preview”; Cook failure renders “Saved at revision N; Runtime is still revision N-1” with Retry Prepare.

- [ ] **Step 3: Write failing privacy report tests**

The report may include Product/Host/Platform/Contract identities, Project/Runtime revisions, operation outcomes, trigger-mode coverage, and capability rows. Assert it excludes `File.name`, absolute/OPFS paths, Project JSON, waveform buckets, and audio bytes.

- [ ] **Step 4: Run focused Creator/browser tests and confirm failure**

```bash
npm --prefix apps/creator-web test -- --run
npm --prefix tests/platform/web test -- creator_web_accessibility.spec.mjs creator_web_lifecycle.spec.mjs --project=chromium
```

Expected: import/Replace and Stage 8 lifecycle assertions fail.

- [ ] **Step 5: Implement file, Pad, and lifecycle ownership**

Use one hidden picker owned by Sample Surface and one confirmation dialog at a time. Serialize against existing Project actions. Escape/unmount aborts active Sample staging and clears preview. Source display name is truncated/escaped render state only and is dropped after the operation.

- [ ] **Step 6: Run Task 10 verification**

```bash
npm --prefix apps/creator-web test -- --run
npm --prefix tests/platform/web test -- creator_web_accessibility.spec.mjs creator_web_lifecycle.spec.mjs --project=chromium
scripts/architecture-portal.sh check
```

Expected: Creator lifecycle and accessibility suites pass with no privacy leak.

- [ ] **Step 7: Commit Task 10**

```bash
git add -- apps/creator-web/src/components/pad_surface.tsx \
  apps/creator-web/src/app.tsx \
  apps/creator-web/src/runtime/runtime_context.tsx \
  apps/creator-web/src/report/acceptance_report.ts \
  apps/creator-web/test/audio_lifecycle.test.tsx \
  apps/creator-web/test/runtime_context.test.tsx \
  apps/creator-web/test/acceptance_report.test.ts \
  apps/creator-web/test/workspace_shell.test.tsx \
  tests/platform/web/creator/creator_web_accessibility.spec.mjs \
  tests/platform/web/creator/creator_web_lifecycle.spec.mjs
git commit -m "feat(creator): complete sample file and lifecycle flows"
```

### Task 11: Add packaged Sample Editor Proof and CI ownership

**Files:**
- Create: `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- Modify: `tests/platform/web/playwright.config.mjs`
- Modify: `scripts/creator-web.sh`
- Modify: `apps/creator-web/tools/package.py`
- Modify: `apps/creator-web/test/package_test.py`
- Modify: `apps/creator-web/test/server_test.py`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/quality/2026-08-09-stage8-sample-editor-acceptance.md`

**Interfaces:**
- Consumes: complete packaged Stage 8 vertical slice.
- Produces: real-Facade packaged proof and truthful evidence ledger.

- [ ] **Step 1: Write failing package and Proof contract tests**

Require packaged Creator output to include the Stage 8 UI and same-build Runtime assets but no fixture-only Project parser, raw source map, debug path, alternate audio engine, or retired Contract. Make `scripts/creator-web.sh proof` select the Sample Editor spec as a required lane.

- [ ] **Step 2: Implement the packaged Chromium journey**

The test must: import/open v1 without migration; import valid WAV into empty Pad; observe one v2 revision/defaults; verify content-derived mirrored waveform; zoom/Fit; commit trim once; exercise four modes/Volume/Mute/Reset; cancel then confirm Replace; inject unsupported WAV/conflict/Cook failure; retry Prepare; reload/reopen; and prove no duplicate import.

- [ ] **Step 3: Implement WebKit capability-boundary evidence**

Record actual preflight/Host capability result and fail on protocol/privacy errors. Do not translate WebKit automation into physical hearing, latency, or touch evidence.

- [ ] **Step 4: Run Proof and confirm the new lane fails before wiring**

```bash
scripts/creator-web.sh test
scripts/creator-web.sh proof
```

Expected: the new required packaged Sample journey is not yet selected or packaged.

- [ ] **Step 5: Wire packaging, proof selection, CI, and acceptance rows**

Keep automated rows distinct from manual Chrome hearing, physical touch, Safari physical boundary, and five Stage 6 physical rows. Initial manual/physical cells read `deferred / unverified`; they do not block canary implementation merge but block physical-pass, Beta, and Stable.

- [ ] **Step 6: Run Task 11 verification**

```bash
scripts/creator-web.sh test
scripts/creator-web.sh proof
python3 apps/creator-web/test/package_test.py
python3 apps/creator-web/test/server_test.py
python3 tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
```

Expected: packaged Chromium positive Proof and WebKit boundary pass; acceptance document remains truthful about manual evidence.

- [ ] **Step 7: Commit Task 11**

```bash
git add tests/platform/web/creator/creator_web_sample_editor.spec.mjs \
  tests/platform/web/playwright.config.mjs scripts/creator-web.sh \
  apps/creator-web/tools/package.py apps/creator-web/test/package_test.py \
  apps/creator-web/test/server_test.py .github/workflows/ci.yml \
  docs/quality/2026-08-09-stage8-sample-editor-acceptance.md
git commit -m "test(creator): prove the packaged sample editor"
```

### Task 12: Integrate versions, Product Assembly, PRD decisions, and Portal current truth

**Files:**
- Modify: `packages/authoring-domain/module.json`
- Modify: `packages/project-io/module.json`
- Modify: `packages/project-cooker/module.json`
- Modify: `packages/audio-runtime/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `apps/creator-web/module.json`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `apps/native-test-host/module.json`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Regenerate: `products/lmdj/assembly.lock.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `docs/prd/decision-log.md`
- Modify: `docs/prd/open-questions.md`
- Modify: `apps/architecture-portal/docs/overview/index.mdx`
- Modify: `apps/architecture-portal/docs/core/overview.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/authoring-domain.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-io.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-cooker.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/audio-runtime.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Modify: `apps/architecture-portal/docs/hosts/overview.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/contracts/project.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/platform/input.mdx`
- Modify: `apps/architecture-portal/docs/platform/storage.mdx`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/diagrams/application-facade.architecture.json`
- Modify: `apps/architecture-portal/diagrams/audio-runtime.architecture.json`
- Modify: `apps/architecture-portal/diagrams/authoring-domain.architecture.json`
- Modify: `apps/architecture-portal/diagrams/lmdj-core.architecture.json`
- Modify: `apps/architecture-portal/diagrams/lmdj-product.architecture.json`
- Modify: `apps/architecture-portal/diagrams/project-cooker.architecture.json`
- Modify: `apps/architecture-portal/diagrams/project-io.architecture.json`
- Modify: `apps/architecture-portal/diagrams/web-runtime-platform.architecture.json`
- Regenerate: matching `apps/architecture-portal/static/diagrams/*.{svg,html}` for those eight diagram sources
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/module_graph_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `tests/core/facade/assembly_loader_test.cpp`
- Modify: `apps/creator-web/test/package_test.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `tests/host/cli_test.py`
- Modify: `tests/host/mcp_stdio_test.py`
- Modify: `tests/host/native_host_test.py`

**Interfaces:**
- Consumes: completed Tasks 1–11 and merged Stage 7 `main` baseline.
- Produces: coherent `1.0.22.0 · canary` current truth; no immutable snapshot yet.

- [ ] **Step 1: Revalidate the integration gate before editing**

```bash
git fetch origin main
git merge-base --is-ancestor origin/feat/stage7-creator-editor origin/main
git rebase origin/main
git status --short --branch
python3 scripts/version.py verify --version-file products/lmdj/version.json
```

Expected: Stage 7 is an ancestor of `origin/main`, rebase completes cleanly, and the worktree is clean. If the ancestor check is false, stop before version edits; functional commits may remain stacked but version integration must wait.

- [ ] **Step 2: Re-read live identities and revise planned targets if occupied**

```bash
jq . products/lmdj/version.json
find packages apps -name module.json -print0 | xargs -0 jq -r '[.module // .host // .id // input_filename, .version] | @tsv'
ls apps/architecture-portal/versioned_metadata
```

Expected: `1.0.22.0` and every planned component target are unused. If not, update this plan's Version Management table and use the next legal identities consistently.

- [ ] **Step 3: Update manifests and regenerate Assembly lock**

Add both Project Contracts to Assembly, update exact dependency propagation, and run:

```bash
python3 scripts/version.py lock
python3 scripts/version.py verify --version-file products/lmdj/version.json
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/module_graph_test.py
```

- [ ] **Step 4: Update PRD and Portal current truth**

Record S8-D1 through S8-D13 as approved outcomes, remove only the resolved Sampler Edit parameter row, preserve unrelated open questions, and record Stage 8B as unimplemented/unversioned. Update source diagrams and generate their SVG/HTML outputs with the repository script; do not hand-edit generated diagrams.

- [ ] **Step 5: Run current-truth verification**

```bash
npm --prefix apps/architecture-portal run check:current
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
scripts/core.sh test dev full
scripts/creator-web.sh test
scripts/creator-web.sh proof
```

Expected: all current manifests, source diagrams, Host packages, and functional suites agree on `1.0.22.0`; full excludes stress by policy.

- [ ] **Step 6: Commit Task 12**

Stage the explicit manifest, Assembly, PRD, Portal current source/generated files, and identity tests listed above only, inspect the staged name list, then:

```bash
git diff --name-only | sort
git add -- packages/authoring-domain/module.json packages/project-io/module.json \
  packages/project-cooker/module.json packages/audio-runtime/module.json \
  packages/application-facade/module.json \
  packages/web-runtime-platform/module.json apps/creator-web/module.json \
  apps/web-runtime-host/module.json apps/core-cli/module.json \
  apps/core-mcp/module.json apps/core-mcp/pyproject.toml \
  apps/core-mcp/lmdj_core_mcp/__init__.py apps/native-test-host/module.json \
  products/lmdj/version.json products/lmdj/assembly.json \
  products/lmdj/assembly.lock.json products/lmdj/src/compiled_assembly.cpp \
  docs/prd/decision-log.md docs/prd/open-questions.md \
  apps/architecture-portal/docs/overview/index.mdx \
  apps/architecture-portal/docs/core/overview.mdx \
  apps/architecture-portal/docs/core/modules/{authoring-domain,project-io,project-cooker,audio-runtime,application-facade,web-runtime-platform}.mdx \
  apps/architecture-portal/docs/hosts/{overview,creator-web}.mdx \
  apps/architecture-portal/docs/contracts/project.mdx \
  apps/architecture-portal/docs/platform/{web-runtime,input,storage}.mdx \
  apps/architecture-portal/docs/assembly/lmdj.mdx \
  apps/architecture-portal/docs/operations/{testing-and-proof,version-and-release}.mdx \
  apps/architecture-portal/diagrams/{application-facade,audio-runtime,authoring-domain,lmdj-core,lmdj-product,project-cooker,project-io,web-runtime-platform}.architecture.json \
  apps/architecture-portal/static/diagrams/{application-facade,audio-runtime,authoring-domain,lmdj-core,lmdj-product,project-cooker,project-io,web-runtime-platform}.{svg,html} \
  tests/build/version_test.py tests/conformance/module_graph_test.py \
  tests/conformance/version_lock_test.py \
  tests/core/facade/assembly_loader_test.cpp \
  apps/creator-web/test/package_test.py \
  apps/web-runtime-host/test/package_test.py tests/host/cli_test.py \
  tests/host/mcp_stdio_test.py tests/host/native_host_test.py
git diff --cached --name-status
git commit -m "feat(product): allocate stage 8 sample editor candidate"
```

### Task 13: Freeze the immutable `1.0.22.0 · canary` Portal snapshot

**Files:**
- Modify: `apps/architecture-portal/versions.json`
- Create: `apps/architecture-portal/versioned_docs/version-1.0.22.0/**`
- Create: `apps/architecture-portal/versioned_sidebars/version-1.0.22.0-sidebars.json`
- Create: `apps/architecture-portal/versioned_metadata/version-1.0.22.0.json`
- Create: `apps/architecture-portal/static/versions/1.0.22.0/**`

**Interfaces:**
- Consumes: clean committed Task 12 source boundary.
- Produces: immutable canary architecture snapshot tied to that revision.

- [ ] **Step 1: Confirm the source boundary is clean**

```bash
git status --short
git log -1 --oneline
```

Expected: no output from status and HEAD is Task 12.

- [ ] **Step 2: Generate the immutable snapshot**

```bash
scripts/architecture-portal.sh version 1.0.22.0 canary
```

Expected: exactly one new version namespace; older versioned files are byte-for-byte untouched.

- [ ] **Step 3: Verify the full Portal**

```bash
scripts/architecture-portal.sh check
git diff --check
```

Expected: current and every immutable version pass.

- [ ] **Step 4: Commit Task 13**

```bash
git add apps/architecture-portal/versions.json \
  apps/architecture-portal/versioned_docs/version-1.0.22.0 \
  apps/architecture-portal/versioned_sidebars/version-1.0.22.0-sidebars.json \
  apps/architecture-portal/versioned_metadata/version-1.0.22.0.json \
  apps/architecture-portal/static/versions/1.0.22.0
git commit -m "docs(product): freeze stage 8 canary architecture snapshot"
```

### Task 14: Record final automated acceptance and clean-source Proof

**Files:**
- Modify: `docs/quality/2026-08-09-stage8-sample-editor-acceptance.md`

**Interfaces:**
- Consumes: immutable Task 13 candidate.
- Produces: reproducible command/result ledger without upgrading physical evidence.

- [ ] **Step 1: Run the complete clean-source gate**

```bash
git status --short
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev full
scripts/core.sh test dev stress
scripts/core.sh coverage check
scripts/core.sh proof
scripts/creator-web.sh test
scripts/creator-web.sh proof
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
```

Expected: clean initial status and every required command exits zero. Record exact command, UTC/local timestamp, Git revision, selected test counts, and artifact/report hashes.

- [ ] **Step 2: Audit prohibited boundaries**

```bash
rg -n 'lmdj\.(patch|materials)\.v1' packages apps providers products contracts workers
rg -n 'JSON\.parse|project\.json|manifest\.json|navigator\.storage' apps/creator-web/src
find . -name '*.map' -path '*creator*' -o -name '*.map' -path '*web-runtime*'
```

Expected: no active retired-Contract usage, no Creator Project/storage parser, and no packaged source maps. Document any expected test/document reference separately from active source.

- [ ] **Step 3: Update acceptance rows without overstating evidence**

Mark automated Core/Facade/Runtime/Creator/Chromium/WebKit-boundary/Portal rows with evidence. Keep Chrome hearing, physical touch, Safari physical behavior, and the five Stage 6 physical rows as `deferred / unverified` until their required real-device sessions occur. Stage 8B remains out of scope.

- [ ] **Step 4: Commit the acceptance record**

```bash
git add docs/quality/2026-08-09-stage8-sample-editor-acceptance.md
git commit -m "docs(quality): bind stage 8 sample editor proof"
```

- [ ] **Step 5: Re-run final revision-sensitive checks**

```bash
scripts/core.sh proof
scripts/creator-web.sh proof
scripts/architecture-portal.sh check
git status --short --branch
```

Expected: all pass and the branch is clean.

## Requirement-to-Task Coverage

| Design requirement | Tasks |
| --- | --- |
| v1 read-only projection, first mutation v2, one revision | 1, 2, 5, 6 |
| Per-Pad independent playback and defaults | 1, 2, 3, 8 |
| PCM16 mono/stereo 44.1/48 validation and immutable bytes | 2, 3, 5 |
| Deterministic waveform and cache | 3, 5, 8, 9 |
| Source trim, gain, mute, four trigger modes | 3, 4, 6, 7 |
| Draft preview and release-time commit | 4, 6, 7, 8, 9 |
| Atomic import/Replace and cancellation | 2, 5, 6, 7, 10 |
| Revision conflict and saved/runtime split | 5, 6, 7, 8, 10 |
| Desktop/Tablet, keyboard, pointer, touch targets | 8, 9, 10, 11 |
| Stop active/latched Voices on lifecycle boundaries | 4, 7, 10 |
| Privacy, bounds, no Host parser/fallback | 5, 6, 8, 10, 11, 14 |
| Product identities, PRD, Portal current truth/snapshot | 12, 13 |
| Automated and truthful manual/physical acceptance | 11, 14 |
| Stage 8B/Stage 9/non-goal boundaries | Global Constraints, 12, 14 |

## Pull Request and Completion Boundary

- Keep the Stage 8 branch stacked until Stage 7 is in `main`; do not mark it merge-ready while the ancestor gate fails.
- Before any push/PR request, rebase onto merged `origin/main`, rerun Task 14 revision-sensitive gates, and verify the declared PR base is `main`.
- The PR must declare `Documentation impact: required` with the routes above and `Version impact: Product 1.0.22.0; new lmdj.project.v2 2.0.0; affected Module/Host versions as verified at integration time`.
- Automated green plus immutable canary snapshot permits implementation review only. It does not claim physical-pass, Beta, Stable, release, publication, or deployment.
- Do not create or push `lmdj-v1.0.22.0`, merge the PR, publish artifacts, deploy a Host, or promote a Channel without separate authorization.
