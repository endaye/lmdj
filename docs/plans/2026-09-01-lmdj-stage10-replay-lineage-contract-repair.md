# LMDJ Stage 10 Replay and Lineage Contract Repair Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist exact resample Lineage and Performance recording revisions in
Project v4, then deliver deterministic begin-time replay and quota-safe resample
commit through the locked Stage 10 Facade surface.

**Architecture:** Task 1 (#516) extends Project Truth and the existing D1
transaction so Lineage is part of the same Asset/Pad/revision atomic boundary.
Task 2 (#431) keeps resolution in Project Cooker, injects a replay controller
into Application Facade, and delegates all mutation to D1; Runtime receives only
an immutable projection and never receives a Project path or mutable Project.

**Tech Stack:** C++20, nlohmann/json, JSON Schema, CMake/CTest, Python contract
tests, Project Store managed storage, existing integer transport ticks.

## Global Constraints

- New code must not read, write, translate, or emit retired
  `lmdj.patch.v1` or `lmdj.materials.v1` contracts.
- Project v4 Asset JSON always contains `lineage`; ordinary imports, Capture,
  and v3-migrated Assets encode it as `null`.
- The only Stage 10 non-null Lineage variant is the exact RLC-D2
  `asset_artifact + resample` object; every nested object uses exact keys.
- `Performance.recording_revision` is the `expected_revision` accepted by
  `performance.record.begin` and is immutable thereafter.
- `performance.resample.commit` keeps its locked request shape. The new
  `AssetId` is the `command_id` UUID value in the AssetId type namespace.
- Resample range is `[start_frame, end_frame)` in 48 kHz stereo source frames.
- Resample commit uses the existing D1 Bank/generation quota, staging,
  recovery, receipt, and collision path; no Job, Attempt, or offline FX render
  is added.
- Replay resolution freezes one current Project revision and produces an
  immutable projection with no path, store, journal, Host callback, or mutable
  Project.
- One `playing` replay is allowed per Application Facade instance. Busy begin
  returns `INVALID_ARGUMENT` with exact details
  `{ "active_replay_id": "00000000-0000-4000-8000-000000000001" }`, where
  the value is the actual active lowercase canonical replay UUID.
- Replay `status` is read-only. Runtime progression alone advances cursor.
- Natural end, explicit stop, and Runtime apply failure publish terminal state
  only after neutral reset acknowledgement; reset-pending follows RLC-D9.
- Cancel is pre-commit only: no Core call means no Asset, Pad, revision, or
  receipt change. Once accepted, resample commit is atomic.
- Version impact: no new allocation. Existing targets remain Project Contract
  `4.0.0`, authoring-domain `2.0.0`, project-io `2.0.0`, project-cooker `1.1.0`,
  application-facade `3.0.0`, and Product Build `1.0.41.0`.
- Documentation impact: none for #516 and #431 because neither changes active
  manifests or Portal current truth. Stage 10 Task 10 (#436) owns Portal and
  Product Assembly integration; Task 11 (#438) owns the immutable snapshot.
- Never lower a coverage floor. New test executables must be added to the root
  coverage target list.

---

### Task 1: Persist the Replay/Resample Contract Prerequisite

**Issue:** #516. Hard dependencies: #430, #498, #499, and merged design/plan
PR #515.

**Files:**

- Modify: `contracts/project/lmdj.project.v4.schema.json`
- Modify: `packages/authoring-domain/include/lmdj/domain/project.hpp`
- Modify: `packages/authoring-domain/src/project.cpp`
- Modify: `packages/authoring-domain/src/migration.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/fixtures/contracts/project-v4-valid.json`
- Modify: `tests/fixtures/contracts/project-v4-invalid-event.json`
- Modify: `tests/fixtures/contracts/project-v3-to-v4-migration.json`
- Modify: `tests/conformance/schema_contract_test.py`
- Modify: `tests/core/domain/performance_test.cpp`
- Modify: `tests/core/domain/migration_v4_test.cpp`
- Modify: `tests/core/project_io/project_store_test.cpp`
- Modify: `tests/core/project_io/performance_lifecycle_test.cpp`
- Modify: `tests/core/project_io/fault_matrix_test.cpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify:
  `docs/design/2026-08-31-lmdj-stage12-candidate-adoption-lineage-design.md`

**Interfaces:**

- Consumes: existing `domain::Asset`, `domain::Performance`,
  `ProjectStore::ImportAssignSampleBytesRequest`, v3→v4 migration, D1 staging
  and receipt machinery.
- Produces:

```cpp
struct AssetArtifactLineageSource {
  std::string artifact_sha256;
  std::uint64_t project_revision{};
  bool operator==(const AssetArtifactLineageSource&) const = default;
};

struct ResampleFrameRange {
  std::uint64_t start_frame{};
  std::uint64_t end_frame{};
  bool operator==(const ResampleFrameRange&) const = default;
};

struct ResampleLineageDerivation {
  ResampleFrameRange range;
  PerformanceId performance_id;
  bool operator==(const ResampleLineageDerivation&) const = default;
};

struct AssetLineage {
  AssetArtifactLineageSource source;
  ResampleLineageDerivation derivation;
  bool operator==(const AssetLineage&) const = default;
};

foundation::Result<void> validate_asset_lineage(const AssetLineage& lineage);
nlohmann::json asset_lineage_json(const AssetLineage& lineage);
foundation::Result<AssetLineage> asset_lineage_from_json(
    const nlohmann::json& input);
```

- `domain::Asset` gains `std::optional<AssetLineage> lineage`.
- `domain::Performance` gains `std::uint64_t recording_revision` immediately
  before `recording_artifact`.
- `ImportAssignSampleBytesRequest` gains a trailing
  `std::optional<domain::AssetLineage> lineage = std::nullopt`; existing
  ordinary/Capture callers remain source-compatible.

- [ ] **Step 1: Write the schema and fixture RED cases**

Add exact `$defs` for `asset_artifact_lineage_source`,
`resample_frame_range`, `resample_lineage_derivation`, and `asset_lineage`.
Change the v4 Asset and Performance required keys to:

```json
"asset_artifact_lineage_source": {
  "type": "object",
  "required": ["kind", "artifact_sha256", "project_revision"],
  "properties": {
    "kind": { "const": "asset_artifact" },
    "artifact_sha256": {
      "type": "string",
      "pattern": "^[0-9a-f]{64}$"
    },
    "project_revision": { "type": "integer", "minimum": 0 }
  },
  "additionalProperties": false
},
"resample_frame_range": {
  "type": "object",
  "required": ["start_frame", "end_frame"],
  "properties": {
    "start_frame": { "type": "integer", "minimum": 0 },
    "end_frame": { "type": "integer", "minimum": 0 }
  },
  "additionalProperties": false
},
"resample_lineage_derivation": {
  "type": "object",
  "required": ["kind", "range", "performance_id"],
  "properties": {
    "kind": { "const": "resample" },
    "range": { "$ref": "#/$defs/resample_frame_range" },
    "performance_id": { "$ref": "#/$defs/uuid" }
  },
  "additionalProperties": false
},
"asset_lineage": {
  "type": "object",
  "required": ["source", "derivation"],
  "properties": {
    "source": { "$ref": "#/$defs/asset_artifact_lineage_source" },
    "derivation": { "$ref": "#/$defs/resample_lineage_derivation" }
  },
  "additionalProperties": false
},
"asset": {
  "required": ["asset_id", "artifact", "lineage"],
  "properties": {
    "asset_id": { "$ref": "#/$defs/uuid" },
    "artifact": { "$ref": "#/$defs/artifact_ref" },
    "lineage": {
      "oneOf": [
        { "$ref": "#/$defs/asset_lineage" },
        { "type": "null" }
      ]
    }
  },
  "additionalProperties": false
},
"performance": {
  "required": [
    "performance_id", "name", "created_bpm", "recording_revision",
    "recording_artifact", "events"
  ],
  "properties": {
    "recording_revision": { "type": "integer", "minimum": 0 }
  }
}
```

Add `recording_revision` as a required non-negative integer on every v4
Performance. Before updating the valid fixtures, add Python mutations proving
schema rejection of missing/extra Lineage keys, uppercase or short SHA-256,
malformed Performance UUID, and missing/negative recording revision. The
cross-field `start_frame < end_frame` rule belongs to domain validation because
JSON Schema cannot compare sibling integer values.

- [ ] **Step 2: Run the contract tests and verify RED**

Run:

```bash
python3 tests/conformance/schema_contract_test.py
```

Expected: FAIL because the current valid v4 fixtures lack the newly required
fields; no unrelated Contract failure is accepted as the RED signal.

- [ ] **Step 3: Add the typed domain model and validation**

Update all valid v4 fixtures with `lineage: null` and `recording_revision`.
Then move the `PerformanceId` strong type declaration above `Asset`, add the
types from **Interfaces**, and update the aggregates:

```cpp
struct Asset {
  foundation::AssetId id;
  foundation::ArtifactRef artifact;
  std::optional<AssetLineage> lineage;
  bool operator==(const Asset&) const = default;
};

struct Performance {
  PerformanceId id;
  std::string name;
  std::uint16_t created_bpm;
  std::uint64_t recording_revision{};
  std::optional<foundation::ArtifactRef> recording_artifact;
  std::vector<PerformanceEvent> events;
  bool operator==(const Performance&) const = default;
};
```

`validate_asset_lineage` must require a lowercase 64-hex source digest, a
lowercase canonical Performance UUID, and
`start_frame < end_frame`. `validate_performance` must accept every u64
recording revision and keep all existing name/BPM/artifact/event checks.
`asset_lineage_from_json` must reject every key set other than the exact RLC-D2
shape.

- [ ] **Step 4: Add domain tests and verify GREEN locally**

In `performance_test.cpp`, cover a valid Lineage, every invalid field above,
JSON round-trip, ordinary `null` Asset Lineage, and an arbitrary valid u64
recording revision. Build and run the domain Performance suite:

```bash
cmake --build --preset dev --target \
  lmdj_domain_performance_tests
ctest --preset dev -R '^domain.performance$'
```

Expected: PASS.

- [ ] **Step 5: Make v3→v4 migration explicit and total**

For every v3 Asset object, require its legacy exact shape and add
`lineage: null`; then add the existing 16 null Pattern slots and empty
Performance array:

```cpp
for (auto& asset : project_v4.at("assets")) {
  if (!asset.is_object() || asset.contains("lineage")) {
    return foundation::Result<nlohmann::json>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_project,
            "a v3-declared Asset must not carry v4 Lineage",
        });
  }
  asset["lineage"] = nullptr;
}
```

Update `migration_v4_test.cpp` and the Python golden-vector loop so only these
differences are allowed: contract v4, Asset `lineage: null`, 16 null Pattern
slots, and empty Performances. Explicitly prove v3 input carrying a Lineage
key fails closed. Build and run `lmdj_domain_migration_v4_tests`; expect
`domain.migration_v4` PASS.

- [ ] **Step 6: Persist and parse v4 Lineage and recording revision**

In `project_store.cpp`, serialize Asset `lineage` only when the persisted
contract is v4; v1–v3 retain their existing Asset JSON shape. Parse Asset keys
according to the declared contract. Extend `performance_value_json` and
`parse_performance` with `recording_revision`, and do the same for the
Performance snapshot codec in `sequence_journal.cpp`.

New v4 output must be exactly:

```cpp
encoded_asset["lineage"] = asset.lineage.has_value()
    ? domain::asset_lineage_json(*asset.lineage)
    : nlohmann::json(nullptr);

encoded_performance["recording_revision"] =
    performance.recording_revision;
```

Update Application Facade's `project.inspect` projection with the same v4-only
Asset field and Performance field. Do not add `recording_revision` to the
already locked `performance.list` or `performance.inspect` result shapes.

- [ ] **Step 7: Bind recording revision to `record.begin`**

When `begin_performance_draft` constructs the new draft, set:

```cpp
domain::Performance draft{
    request.performance_id,
    "Untitled Performance",
    loaded.state.bpm,
    request.meta.expected_revision,
    std::nullopt,
    {},
};
```

Add lifecycle assertions proving begin at revision `N` persists
`recording_revision == N`; flush, rebase, stop, save, bind, reload, and
recovery apply never change it. Exact begin retry must return the original
draft and revision.

- [ ] **Step 8: Extend D1 request and transaction identity**

Append Lineage to `ImportAssignSampleBytesRequest` and construct the durable
command as:

```cpp
const PersistedCommand command = domain::ImportAssignSample{
    request.meta,
    domain::Asset{request.asset_id, artifact, request.lineage},
    request.slot,
};
```

New `ImportAsset`/`ImportAssignSample` transaction JSON always emits a
`lineage` member. The parser must accept legacy `{id, artifact}` records as
`null` and new `{id, artifact, lineage}` records, rejecting every other shape.
Canonical command fingerprinting and replay comparison must use the parsed
typed Lineage so same command ID/different Lineage is a collision. Reject a
non-null Lineage when the loaded Project is not v4.

- [ ] **Step 9: Prove D1 atomicity, legacy replay, and fault recovery**

Add `project_store_test.cpp` cases for ordinary null Lineage, exact derived
Lineage round-trip, legacy transaction replay, same-command exact replay, and
same-command/different-Lineage collision. Add `fault_matrix_test.cpp` cases at
every existing import/assign staging and commit fault point. After each
failure/reopen assert the complete far side:

```cpp
LMDJ_CHECK(after.state.revision == before.state.revision);
LMDJ_CHECK(!after.state.assets.contains(derived_asset_id));
LMDJ_CHECK(after.state.banks.at(bank).at(pad).asset_id == old_asset_id);
LMDJ_CHECK(after.state.assets == before.state.assets);
```

For recoverable post-commit faults, assert the one recovered Asset contains
the exact Lineage, the Pad points to it, the receipt revision is `N + 1`, and
no second Artifact or revision appears.

- [ ] **Step 10: Resolve Stage 12's persistence question**

Change S12L-Q1 to resolved: Lineage lives in `lmdj.project.v4` Asset truth and
Stage 12 reuses `Asset.lineage`. Update its Contract/version text so Stage 12
does not allocate another Project field or a second Lineage model. Preserve
all Candidate/Attempt rules.

- [ ] **Step 11: Run Task 1 focused and full verification**

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --preset dev -R \
  '^(domain.performance|domain.migration_v4|project_io.project_store|project_io.performance_lifecycle|project_io.fault_matrix|facade.application|contract.schemas)$'
scripts/core.sh test dev full
scripts/core.sh coverage check
scripts/architecture-portal.sh check
```

Expected: every command PASS; coverage remains at or above every current floor.

- [ ] **Step 12: Ship Task 1 as one review unit**

Follow `.agents/skills/issue-done/SKILL.md`. Stage only the Task 1 files,
inspect `git diff --cached --check`, then commit:

```bash
git commit -m \
  "feat(project): persist resample lineage and recording revision (fixes #516)"
```

Push, open the PR with the exact Version/Documentation impact declarations,
wait for all required CI, squash-merge, verify merged-tree equivalence, and
clean the Task 1 worktree before starting Task 2.

---

### Task 2: Add Replay Resolution and Resample Commit

**Issue:** #431. Hard dependencies: #430, #498, and merged #516.

**Files:**

- Create:
  `packages/project-cooker/include/lmdj/cooker/performance_replay.hpp`
- Create: `packages/project-cooker/src/performance_replay.cpp`
- Create: `packages/project-cooker/include/lmdj/cooker/wav_selection.hpp`
- Create: `packages/project-cooker/src/wav_selection.cpp`
- Modify: `packages/project-cooker/CMakeLists.txt`
- Create:
  `packages/application-facade/include/lmdj/facade/performance_replay.hpp`
- Create: `packages/application-facade/src/performance_replay.cpp`
- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/src/c_api.cpp`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `apps/core-cli/src/main.cpp`
- Modify: `apps/native-host/src/main.cpp`
- Modify: `packages/web-runtime-platform/src/bridge.cpp`
- Modify: `packages/web-runtime-platform/test/control_runtime_test.cpp`
- Modify: `packages/web-runtime-platform/test/realtime_session_test.cpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/failure_contract_test.cpp`
- Modify: `tests/core/facade/sample_surface_test.cpp`
- Modify: `tests/core/facade/sequence_surface_test.cpp`
- Modify: `tests/core/facade/performance_session_test.cpp`
- Modify: `tests/core/facade/performance_gesture_admission_test.cpp`
- Modify: `tests/core/facade/performance_operation_contract_test.cpp`
- Modify: `tests/core/facade/web_runtime_limits_test.cpp`
- Create: `tests/core/cooker/performance_replay_projection_test.cpp`
- Create: `tests/core/cooker/wav_selection_test.cpp`
- Create: `tests/core/facade/performance_replay_test.cpp`
- Create: `tests/core/facade/resample_performance_test.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Project Cooker produces:

```cpp
struct PerformanceReplayBoundary {
  std::uint64_t offset_tick{};
  domain::PerformanceEvent event;
};

struct PerformanceReplayProjection {
  domain::PerformanceId performance_id;
  std::uint64_t resolved_revision{};
  std::uint16_t bpm{};
  bool quantize_enabled{};
  std::uint8_t swing_percent{};
  std::array<std::optional<ResolvedPad>, 64> pads;
  std::array<std::shared_ptr<const RuntimeSnapshot>, 16> patterns;
  std::vector<PerformanceReplayBoundary> boundaries;
  std::uint64_t event_count{};
};

foundation::Result<std::shared_ptr<const PerformanceReplayProjection>>
cook_performance_replay(
    const domain::ProjectState& project,
    const domain::PerformanceId& performance_id,
    ArtifactResolver resolve);

foundation::Result<std::vector<std::byte>> select_pcm16_stereo_wav(
    std::span<const std::byte> source,
    std::uint64_t start_frame,
    std::uint64_t end_frame);
```

- Application Facade produces:

```cpp
struct ReplayIdTag;
using ReplayId = foundation::StrongId<ReplayIdTag>;

enum class ReplayState : std::uint8_t { playing, stopped, complete };

struct ReplayRuntimeStatus {
  ReplayState state{ReplayState::playing};
  std::uint64_t event_cursor{};
  std::uint64_t event_count{};
  std::uint64_t resolved_revision{};
};

class PerformanceReplayController {
 public:
  virtual ~PerformanceReplayController() = default;
  virtual foundation::Result<ReplayRuntimeStatus> begin(
      const ReplayId& replay_id,
      std::shared_ptr<const cooker::PerformanceReplayProjection> projection) = 0;
  virtual foundation::Result<ReplayRuntimeStatus> status(
      const ReplayId& replay_id) const = 0;
  virtual foundation::Result<ReplayRuntimeStatus> stop(
      const ReplayId& replay_id) = 0;
};

class PerformanceReplayRuntimeSink {
 public:
  virtual ~PerformanceReplayRuntimeSink() = default;
  virtual foundation::Result<void> apply_pad_hit(
      const cooker::ResolvedPad& pad,
      std::uint64_t duration_tick,
      std::uint8_t velocity) = 0;
  virtual foundation::Result<void> apply_pattern_launch(
      std::shared_ptr<const cooker::RuntimeSnapshot> pattern) = 0;
  virtual foundation::Result<void> apply_fx_gesture(
      audio::FxGesture gesture) = 0;
  virtual foundation::Result<void> reset_neutral() = 0;
};
```

- `ReferencePerformanceReplayController` implements the interface against a
  `PerformanceReplayRuntimeSink`. Its concrete-only
  `advance_to(std::uint64_t elapsed_tick)` is the deterministic progression
  driver used by tests; Facade never calls it from `status`.
- Construct it with
  `ReferencePerformanceReplayController(std::shared_ptr<PerformanceReplayRuntimeSink>)`.
  A null Pattern slot is a controller-side silent gap and does not call
  `apply_pattern_launch`.
- `ApplicationConfig` gains a required
  `std::shared_ptr<PerformanceReplayController> performance_replay_controller`.
  Existing Hosts explicitly inject `make_unavailable_performance_replay_controller()`
  until Tasks 6/7 connect their Runtime; no constructor silently substitutes a
  controller.

- [ ] **Step 1: Write Project Cooker projection RED tests**

Build a v4 Project with all 64 Pad positions represented, two occupied Pattern
slots, one empty slot, and a Performance containing equal-tick Pad/Pattern/FX/
HOLD events. Assert:

```cpp
LMDJ_CHECK(projection->resolved_revision == revision_r);
LMDJ_CHECK(projection->pads.at(global_slot).has_value());
LMDJ_CHECK(projection->patterns.at(moved_slot)->pattern_id == pattern_id);
LMDJ_CHECK(projection->patterns.at(empty_slot) == nullptr);
LMDJ_CHECK(projection->boundaries.front().offset_tick == 0);
LMDJ_CHECK(projection->boundaries == canonical_expected_boundaries);
```

Mutate the source Project after cooking and prove the projection remains
byte-for-byte/equality stable. A second cook must reflect the new revision,
replacement Pad sound, moved Pattern, and null gap.

- [ ] **Step 2: Implement immutable replay projection**

Add `performance_replay.hpp/.cpp`. Resolve every assigned Pad through the
existing verified `ArtifactResolver`, prepare immutable playback/material,
and cook each occupied Pattern slot at the same Project revision. Normalize
the canonical event stream to stable offsets from its first event tick; an
empty stream has zero boundaries. Reject a missing Performance before
allocating a projection. Do not retain resolver, path, Project, or store.

- [ ] **Step 3: Write WAV selection RED tests**

Create a known PCM16 48 kHz stereo WAV and assert exact samples and header for
`[start_frame, end_frame)`. Add rejection cases for zero-length/reversed/out-of-
bounds ranges, mono, non-48-kHz, non-PCM16, malformed RIFF chunks, and trailing
length mismatch. The source byte vector must remain unchanged.

- [ ] **Step 4: Implement deterministic WAV selection**

Add `wav_selection.hpp/.cpp`. Reuse `decode_wav`, require exactly PCM16 48 kHz
stereo input, copy only selected interleaved samples, and encode a canonical
44-byte PCM RIFF header followed by little-endian samples. Check all frame,
sample, byte, RIFF-size, and u32 overflows before allocation.

- [ ] **Step 5: Build and run the Cooker suites**

Add both source files and test executables to Project Cooker CMake. Run:

```bash
cmake --build --preset dev --target \
  lmdj_project_cooker_performance_replay_tests \
  lmdj_project_cooker_wav_selection_tests
ctest --preset dev -R \
  '^(cooker.performance_replay|cooker.wav_selection)$'
```

Expected: PASS.

- [ ] **Step 6: Write reference-controller lifecycle RED tests**

In `performance_replay_test.cpp`, retain the concrete reference controller so
the test can call `advance_to`. Use a recording Runtime sink and cover:

- begin returns `playing`, cursor 0, fixed revision and event count;
- equal-tick events apply in canonical order and cursor moves only after sink
  acknowledgement;
- Pattern null gap advances cursor without changing the sink's active Pattern;
- `status` calls do not apply events or retry reset;
- last event triggers neutral reset and then `complete`;
- an empty event stream resets immediately and completes;
- explicit stop resets then publishes `stopped`;
- apply failure chooses target `stopped`, freezes cursor and enters
  reset-pending;
- first reset failure leaves public state `playing`; repeated status is fixed;
- each stop retries reset, does not consume request identity on failure, and a
  successful retry publishes the originally chosen terminal state.

- [ ] **Step 7: Implement the controller boundary and reference controller**

Add `performance_replay.hpp/.cpp`. The Runtime sink has explicit methods for
resolved Pad hit, occupied Pattern launch, the existing tick-free
`audio::FxGesture` (including HOLD on/off), and `reset_neutral()`; a null
Pattern gap advances without a sink call.
`advance_to` applies every boundary with
`offset_tick <= elapsed_tick`; update cursor only after success. Store an
internal reset-pending target (`stopped` for apply failure) without adding a
public Replay state. Provide an
unavailable controller whose three methods return the existing precise Runtime
unavailable error; existing Hosts inject it explicitly until their Stage 10
Tasks connect audio.

- [ ] **Step 8: Register exact Facade operations and required injection**

Add `performance.replay.begin`, `performance.replay.stop`,
`performance.replay.status`, and `performance.resample.commit` to the existing
strict operation table with the locked command/query kinds. Update
`performance_operation_contract_test.cpp` so the exact set includes all 23
Stage 10 operations and rejects wrong method, missing keys, extra keys, and
malformed UUIDs.

Add the required controller member to `ApplicationConfig`; constructor rejects
null with a stable message. Update every listed Application construction site
to inject either the reference/fake controller used by its test or the explicit
unavailable controller. No default or implicit fallback is allowed.

- [ ] **Step 9: Implement Facade replay identity and idempotency**

On begin, load current Project once, cook the immutable projection, then call
controller begin. Store per-Facade identity
`replay_id -> {project_path, performance_id}` and the single active replay ID.
Do not create identity if load/cook/controller begin fails. Enforce:

```cpp
if (active_replay_id && *active_replay_id != requested_id) {
  return Error{ErrorCode::invalid_argument,
               "a Performance replay is already playing",
               {{"active_replay_id", active_replay_id->value()}}};
}
```

Same ID/same path+Performance returns current status; same ID/different payload
is collision. Stop receipts are keyed by request ID and replay ID. Consume a
request ID only after controller stop succeeds. A different request ID against
terminal replay returns current terminal status with `replayed: false` and does
not reset again. Status only calls controller status. Once the active replay is
terminal, clear the per-instance `active_replay_id` so a different replay ID
may begin while retaining old identity/receipt records for retries.

- [ ] **Step 10: Prove fixed revision and per-Facade exclusion**

Add Facade tests that begin on R, then use a second Application/ProjectStore
writer to replace a Pad, move/clear Pattern slots, delete the Performance, and
advance revision. Retained controller projection must stay on R; a new begin
after terminal state must resolve the new current truth. Two different Facade
instances may replay concurrently; one Facade instance rejects a second
playing ID with exact `{active_replay_id}` details.

- [ ] **Step 11: Write resample RED and far-side tests**

In `resample_performance_test.cpp`, construct a managed recording Artifact and
saved Performance. Cover exact request/result keys, deterministic
`AssetId{command_id.value()}`, selected samples, target Pad, and persisted
Lineage fields. Exercise exact retry and collisions for changed Performance,
range, target, and Lineage source revision.

For missing/unverified/mismatched recording, invalid ranges, occupied/quota
failure, and cancel-before-commit, capture and compare the complete far side:
Project JSON, revision, Asset map, Pad assignment, managed Artifact inventory,
and receipt inventory. `BANK_QUOTA_EXHAUSTED` details must match D1 exactly.

- [ ] **Step 12: Implement resample strictly through D1**

The handler must:

```cpp
const auto performance_iterator = project.performances.find(performance_id);
if (performance_iterator == project.performances.end()) {
  return error_envelope(foundation::Error{
      foundation::ErrorCode::not_found,
      "Performance does not exist",
  });
}
const auto& performance = performance_iterator->second;
const auto bytes = projects.read_artifact(path, *performance.recording_artifact);
const auto selected = cooker::select_pcm16_stereo_wav(
    bytes.value(), source_start_frame, source_end_frame);
const domain::AssetLineage lineage{
    {performance.recording_artifact->sha256,
     performance.recording_revision},
    {{source_start_frame, source_end_frame}, performance.id},
};
const auto committed = projects.import_assign_sample_bytes(
    path,
    {meta, target_slot, foundation::AssetId{meta.command_id.value()},
     "audio/wav", selected.value(), std::nullopt, lineage});
```

Return existing `SampleMutationResult` fields plus `performance_id`. Do not
write any file, Asset, Pad, receipt, or revision outside D1. Do not add a
cancel operation, Job, Attempt, or offline renderer call.

- [ ] **Step 13: Wire coverage and run Task 2 focused tests**

Add all four new test targets to their package CMake files and to
`lmdj_coverage_targets` in root `CMakeLists.txt`. Run:

```bash
cmake --build --preset dev --target \
  lmdj_project_cooker_performance_replay_tests \
  lmdj_project_cooker_wav_selection_tests \
  lmdj_facade_performance_replay_tests \
  lmdj_facade_resample_performance_tests
ctest --preset dev -R \
  '^(cooker.performance_replay|cooker.wav_selection|facade.performance_replay|facade.resample_performance|facade.performance_operation_contract)$'
```

Expected: PASS.

- [ ] **Step 14: Run Task 2 full verification**

Run:

```bash
scripts/core.sh test dev full
scripts/core.sh coverage check
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
```

Expected: every command PASS, no coverage floor reduction, no active-boundary
violation, and no Project mutation in any replay-only test.

- [ ] **Step 15: Ship Task 2 as one review unit**

Follow `.agents/skills/issue-done/SKILL.md`. Stage only the Task 2 files,
inspect the staged file list and `git diff --cached --check`, then commit:

```bash
git commit -m \
  "feat(facade): add Performance replay and resample commit (fixes #431)"
```

Push, open the PR with Version impact and Documentation impact declarations,
wait for every required lane including coverage and ASAN/stress, squash-merge,
verify the exact merged tree, close #431, and clean the worktree/branch. Only
then may Stage 10 Task 6 (#432) begin.

## Version Management

Version impact: no new allocation.

Both Tasks land before Stage 10 Task 10 enables the v4 writer and published
module versions. They consume the already locked targets:

- `lmdj.project.v4` Contract `4.0.0`;
- authoring-domain `2.0.0`;
- project-io `2.0.0`;
- project-cooker `1.1.0`;
- application-facade `3.0.0`;
- Product Build `1.0.41.0`.

Before #436 allocates or publishes identities, rerun its fresh allocation
audit. If any identity has become occupied, stop and refresh the Stage 10
allocation rather than changing it inside #516 or #431.

## Documentation Impact

Documentation impact: none for #516 and #431.

#516 updates retained Stage 12 design authority only to resolve S12L-Q1;
neither Task changes active manifests, Assembly, Product Build, or Portal
current pages. Stage 10 Task 10 (#436) must declare required Portal routes and
source diagrams in its own PR, and Task 11 (#438) freezes the immutable
snapshot.

## Execution Order

```text
PR #515 (this design + plan)
  -> Issue #516 isolated worktree / one commit / PR / merge / cleanup
  -> rebase fresh Task 5 worktree on merged main
  -> Issue #431 one commit / PR / merge / cleanup
  -> Stage 10 Task 6 (#432)
```

Execute the approved plan inline in the current session under repository `AGENTS.md`;
the user has already instructed the agent to begin development automatically
after spec and plan completion. Do not dispatch subagents unless the user later
requests delegation.
