# LMDJ 5B Formal Native Realtime Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, assemble, package, and physically validate a formal Headless Native Host that prepares real Project Snapshots through Application Facade, publishes 64 Pad Sample Banks safely to CoreAudio, and records actual starts through a lock-free Capture Ring into recoverable Takes.

**Architecture:** Project Cooker produces one immutable Snapshot containing all assigned Pads and current Pattern events; Application Facade exposes typed in-process Host methods without changing its JSON/C ABI. Audio Runtime converts the Snapshot off-thread, publishes one of four fixed Bank Slots at an audio callback boundary, and mirrors successful voice starts into an audio-to-writer SPSC Capture Ring; `apps/native-test-host` owns the serialized Facade control plane, the sole Trigger producer, the background journal writer, and the Apple or deterministic output driver.

**Tech Stack:** C++20, CMake 3.24+, CTest, Python 3.11, nlohmann/json, fixed SPSC queues, Apple AudioUnit/CoreAudio, existing LMDJ Foundation/Domain/Project I/O/Assembly tooling.

## Global Constraints

- Work only on `feat/formal-native-host` in `/Users/endaye/Projects/lmdj/.worktrees/formal-native-host`; never edit protected `main` or another retained worktree.
- The authoritative design is `docs/superpowers/specs/2026-08-02-lmdj-formal-native-realtime-host-design.md`.
- Host Project access is only through Application Facade; Host code and manifest must not depend on `project-io`.
- Realtime format remains exactly 48,000 Hz, mono float32 Sample storage, non-interleaved stereo float32 output, 64 Pad slots, 1,024 Trigger events, and 128 Voices.
- Runtime Bank capacity is four; Capture Ring capacity is 4,096; Capture writer batch size is at most 64.
- Audio Thread performs no allocation, deallocation, lock, filesystem/network/Project/Provider I/O, JSON, logging, locale work, exception propagation, Facade call, Sample conversion, Bank reclamation, or journal append.
- Host main thread is the only Trigger Queue producer; Audio Thread is the only Capture Ring producer; background writer is the only Capture Ring consumer.
- Snapshot and Bank publication are whole-state operations; any failure leaves the previous current Bank usable.
- A Capture Ring overflow, frame-offset overflow, or writer failure makes the Take incomplete, seals it as `capture_incomplete`, and forbids commit.
- Recording continues to use strict whole-revision conflict; selective rebase and product Command classification remain open and are not implemented.
- `record.commit` accepts an explicit existing Pattern shape; 5B does not invent quantization.
- Default real-device output exists only on Apple; all platforms build `lmdj-native-host` and support `--no-device`, while non-Apple device mode fails with `UNSUPPORTED_AUDIO`.
- Existing CLI/MCP/C ABI request/response Contracts and public operation lists do not change.
- Retired `lmdj.patch.v1` and `lmdj.materials.v1` remain forbidden.
- CTest `stress` remains excluded from `scripts/core.sh proof` using `-LE '^stress$'`.
- Product is `1.0.11.0 · canary`; this plan authorizes no push, PR, merge, tag, Release, deployment, publication, or Channel promotion.
- Each implementation Task is one reviewable Conventional Commit with exact-file staging and its own RED/GREEN evidence.

## File Map

- `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`: immutable resolved Pad and Pattern snapshot types.
- `packages/project-cooker/src/project_cooker.cpp`: deduplicated decode of every assigned Pad plus Pattern validation.
- `tests/core/cooker/project_cooker_test.cpp`: Pad coverage, ordering, sharing, and failure component tests.
- `tests/core/cooker/determinism_matrix_test.cpp`: deterministic Snapshot equality including Pad data.
- `packages/project-io/include/lmdj/project_io/take_journal.hpp`: public batch append declaration.
- `packages/project-io/src/take_journal.cpp`: validated one-open/one-fsync JSONL batch append.
- `tests/core/project_io/take_journal_test.cpp`: batch atomic validation and recovery tests.
- `packages/application-facade/include/lmdj/facade/application.hpp`: typed Snapshot and realtime Take Host API.
- `packages/application-facade/src/application.cpp`: typed boundary implementation using existing ProjectStore/Cooker/Journal.
- `tests/core/facade/application_test.cpp`: typed API, no-persistence, batch append, and JSON parity tests.
- `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`: move-only control-thread Bank preparation API.
- `packages/audio-runtime/src/prepared_sample_bank.cpp`: PCM16 mono/stereo conversion and validation.
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`: Bank publication, Capture lifecycle/drain, and telemetry API.
- `packages/audio-runtime/src/realtime_engine.cpp`: fixed Bank Slots, callback swap/retirement, Voice ownership, and Capture Ring.
- `tests/core/audio/prepared_sample_bank_test.cpp`: conversion and validation component tests.
- `tests/core/audio/realtime_engine_test.cpp`: Bank swap, old Voice, reclamation, and Capture behavior.
- `tests/core/audio/realtime_engine_stress_test.cpp`: Trigger, publication, and Capture SPSC stress.
- `tests/core/audio/coreaudio_output_test.cpp`: adapter regression with new Engine preparation.
- `tests/platform/audio/native_audio_probe.cpp`: retained 5A Probe migrated to the new Bank API.
- `apps/native-test-host/module.json`: formal Host identity and direct dependencies.
- `apps/native-test-host/CMakeLists.txt`: portable Host target and black-box CTest registration.
- `apps/native-test-host/src/capture_writer.hpp`: background drain/persist state machine.
- `apps/native-test-host/src/capture_writer.cpp`: event conversion, batch append, failure state, and join.
- `apps/native-test-host/src/main.cpp`: invocation, Assembly/Application setup, JSONL protocol, lifecycle, and drivers.
- `tests/host/native_host_test.py`: portable end-to-end `--no-device` Project/Snapshot/recording test.
- `tests/host/native_host_source_boundary_test.py`: forbidden include/link/I/O source checks.
- `tests/host/native_host_apple_smoke.py`: Apple real-backend startup/lifecycle smoke that does not claim audibility.
- `CMakeLists.txt`, `products/lmdj/CMakeLists.txt`: target registration, Product wiring, and coverage objects.
- Module/Product/Assembly/package/version files in Task 6: exact build identity and distribution update.
- `docs/quality/2026-08-02-formal-native-host-acceptance.md`: automated and physical evidence record.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Domain | Current | Target | API | Reason |
| --- | --- | --- | --- | --- |
| Product Build | `1.0.10.0` | `1.0.11.0` | n/a | Adds a formal Assembly Host and integrated realtime/capture capabilities. |
| `project-cooker` | `0.1.0` | `0.2.0` | stays 1 | Adds resolved Pads to immutable Snapshot without removing existing members. |
| `audio-runtime` | `0.2.0` | `0.3.0` | stays 1 | Adds compatible Bank publication/reclaim and Capture Ring APIs. |
| `project-io` | `0.2.0` | `0.3.0` | stays 1 | Adds compatible Take Journal batch append. |
| `application-facade` | `1.0.1` | `1.1.0` | stays 2 | Adds typed in-process Host methods; JSON and C ABI stay unchanged. |
| `core-cli` | `1.0.1` | `1.0.2` | stays 2 | Updates exact Facade dependency only. |
| `core-mcp` | `1.0.1` | `1.0.2` | stays 2 | Updates exact Facade/Python package identity only. |
| `native-test-host` | none | `1.0.0` | 1 | First formal Headless Native Host. |
| Contracts | unchanged | unchanged | unchanged | No wire, persistence, C ABI, error, or Assembly schema change. |
| Providers / Models | unchanged | unchanged | unchanged | No Capability or implementation change. |

- Update `products/lmdj/version.json`, affected `module.json` files, MCP Python version, `assembly.json`, compiled catalog, generated `assembly.lock.json`, version assertions, Proof output, Product README, package inventory, and acceptance expectations in the same integration Task.
- Product candidate identity is `1.0.11.0 · canary · g<short-sha>`.
- Contract and Project compatibility remain unchanged; no migration or bundle rewrite is allowed.
- Future module and Product tags are exactly those listed in design §14; this implementation does not create them.
- Rollback uses the previous immutable `1.0.10.0` build identity; `1.0.11.0` is never reused for different source.

---

### Task 1: Cook every assigned Pad into the immutable Runtime Snapshot

**Files:**

- Modify: `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`
- Modify: `packages/project-cooker/src/project_cooker.cpp`
- Modify: `tests/core/cooker/project_cooker_test.cpp`
- Modify: `tests/core/cooker/determinism_matrix_test.cpp`
- Modify: `tests/core/audio/offline_renderer_test.cpp`

**Interfaces:**

- Consumes: `domain::ProjectState`, selected `PatternId`, and existing verified `ArtifactResolver`.
- Produces: `RuntimeSnapshot::pads` as a unique global-slot-sorted `std::vector<ResolvedPad>` sharing decoded `PcmSample` instances with `events`.

- [ ] **Step 1: Write failing Snapshot shape and all-Pad tests**

Add the public type and member to the test-side aggregate expectation:

```cpp
struct ResolvedPad {
  domain::PadSlotId slot;
  foundation::ArtifactRef artifact;
  std::shared_ptr<const PcmSample> sample;
};

RuntimeSnapshot expected{
    project.id,
    project.revision,
    project.bpm,
    pattern.bars,
    std::vector<ResolvedPad>{},
    std::vector<ResolvedEvent>{},
};
```

Build a Project where slot `{0,0}` and unused slot `{3,15}` share one Artifact, slot
`{1,2}` uses a stereo Artifact, and only `{0,0}` appears in the Pattern. Assert:

```cpp
LMDJ_CHECK(snapshot->pads.size() == 3);
LMDJ_CHECK(snapshot->pads[0].slot == PadSlotId{0, 0});
LMDJ_CHECK(snapshot->pads[1].slot == PadSlotId{1, 2});
LMDJ_CHECK(snapshot->pads[2].slot == PadSlotId{3, 15});
LMDJ_CHECK(snapshot->pads[0].sample == snapshot->pads[2].sample);
LMDJ_CHECK(snapshot->events[0].sample == snapshot->pads[0].sample);
LMDJ_CHECK(resolver_calls == 2);
```

Add separate tests proving an unused assigned Pad with missing bytes, wrong hash, and unsupported WAV causes `missing_asset`, `cook_failed`, and `unsupported_audio` respectively.

- [ ] **Step 2: Run RED**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target \
  lmdj_project_cooker_tests \
  lmdj_project_cooker_determinism_matrix_tests \
  lmdj_audio_runtime_tests
```

Expected: compilation fails because `ResolvedPad` and `RuntimeSnapshot::pads` do not exist.

- [ ] **Step 3: Implement one deduplicated all-Pad decode pass**

Declare the types exactly as specified and replace event-only decode with a local resolver that caches by SHA-256:

```cpp
auto resolve_sample = [&](const foundation::ArtifactRef& artifact)
    -> foundation::Result<std::shared_ptr<const PcmSample>> {
  const auto found = decoded.find(artifact.sha256);
  if (found != decoded.end()) {
    if (found->second.byte_length != artifact.byte_length) {
      return sample_failure(ErrorCode::cook_failed,
                            "cached artifact metadata is inconsistent");
    }
    return sample_success(found->second.sample);
  }
  const auto bytes = resolve(artifact);
  if (!bytes.has_value()) {
    return sample_failure(bytes.error());
  }
  if (bytes.value().size() != artifact.byte_length ||
      sha256_hex(bytes.value()) != artifact.sha256) {
    return sample_failure(ErrorCode::cook_failed,
                          "artifact bytes do not match declared metadata");
  }
  auto sample = decode_wav(bytes.value());
  if (!sample.has_value()) {
    return sample;
  }
  decoded.emplace(artifact.sha256,
                  DecodedArtifact{artifact.byte_length, sample.value()});
  return sample;
};
```

Iterate banks 0..3 and pads 0..15, resolve only assigned assets, append `ResolvedPad`, then build Pattern events by finding the resolved Pad. Do not call the Artifact resolver again from the event loop.

- [ ] **Step 4: Update aggregate consumers and determinism comparison**

Insert the empty or expected `pads` vector before `events` in every `RuntimeSnapshot{}` construction. Compare Pad slot, Artifact metadata, Sample format, Sample bytes, and shared identity invariants in the determinism matrix.

- [ ] **Step 5: Run GREEN**

```bash
cmake --build build/core/dev --target \
  lmdj_project_cooker_tests \
  lmdj_project_cooker_determinism_matrix_tests \
  lmdj_audio_runtime_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^(cooker\.|audio\.offline_renderer$)'
```

Expected: selected Cooker and renderer tests pass.

- [ ] **Step 6: Commit Task 1**

Stage only the five Task files, run `git diff --cached --check`, and commit. Module versions and all exact downstream dependencies remain unchanged until the single consistent Product integration in Task 6:

```bash
git commit -m "feat(cooker): resolve playable pads in runtime snapshots"
```

### Task 2: Add durable Take batches and typed Facade Host methods

**Files:**

- Modify: `packages/project-io/include/lmdj/project_io/take_journal.hpp`
- Modify: `packages/project-io/src/take_journal.cpp`
- Modify: `tests/core/project_io/take_journal_test.cpp`
- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/core/facade/application_test.cpp`

**Interfaces:**

- Consumes: typed absolute Project path, Pattern ID, Take ID, and background-thread `span<const RawTakeEvent>`.
- Produces: `TakeJournal::append_batch`, `Application::prepare_runtime_snapshot`, `Application::append_realtime_take_events`, and the fixed-reason `Application::seal_realtime_take` without adding JSON/C ABI operations.

- [ ] **Step 1: Write failing Project I/O batch tests**

Declare:

```cpp
foundation::Result<void> TakeJournal::append_batch(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id,
    std::span<const domain::RawTakeEvent> events);
```

Test a three-event batch and assert exact order after `read_active`. Test an empty span and a batch whose second event has velocity 0; both return `INVALID_ARGUMENT` and leave the journal event count unchanged. Inject `active_journal_sync` failure and assert the journal remains recoverable by existing unterminated-tail repair.

- [ ] **Step 2: Run Project I/O RED**

```bash
cmake --build build/core/dev --target lmdj_take_journal_tests
```

Expected: compilation fails because `append_batch` is missing.

- [ ] **Step 3: Implement validate-before-open batch append**

Make `append` delegate to a one-element span. `append_batch` must validate Take ID, non-empty batch, every slot, velocity, and nondecreasing `frame_offset` before opening the file. Encode all lines before the first write:

```cpp
std::string payload;
for (const auto& event : events) {
  payload += foundation::canonical_json(event_json(event));
  payload.push_back('\n');
}
```

Then reuse the existing safe open, `truncate_unterminated_tail`, `write_all`, one fault hook, one `fsync_descriptor`, and close sequence. No event may be written if validation or encoding fails.

- [ ] **Step 4: Write failing typed Facade tests**

Add these public declarations:

```cpp
struct RuntimeSnapshotRequest {
  std::filesystem::path project_path;
  foundation::PatternId pattern_id;
};

foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
prepare_runtime_snapshot(const RuntimeSnapshotRequest& request);

foundation::Result<void> append_realtime_take_events(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::span<const domain::RawTakeEvent> events);

foundation::Result<std::filesystem::path> seal_realtime_take(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::string_view reason);
```

The test must call typed prepare, assert Project revision and all resolved Pads, destroy the returned Snapshot, reload Project through `project.inspect`, and prove revision/state did not change. Begin a Take through existing `command`, append three typed events, and commit through existing `command`. Assert no new name appears in `operation_names()` and the C API/CLI/MCP list remains byte-for-byte unchanged.

Begin a second Take, call `seal_realtime_take` with `capture_incomplete`, and assert existing `take.recoverable.list` returns that reason and all appended events. Reject any other reason before Journal mutation.

- [ ] **Step 5: Run Facade RED**

```bash
cmake --build build/core/dev --target \
  lmdj_application_facade_tests lmdj_application_c_api_tests
```

Expected: compilation fails because the typed methods do not exist.

- [ ] **Step 6: Implement typed methods with boundary exception mapping**

Validate paths with the same absolute/normalized policy as JSON requests and IDs with `domain::is_valid_uuid`. Call the existing `ProjectStore::load`, `cook_project`, new `journals.append_batch`, and `journals.seal`. `seal_realtime_take` accepts only `capture_incomplete`. All public typed methods catch implementation exceptions and return:

```cpp
foundation::Error{
    foundation::ErrorCode::internal_error,
    "unexpected Application Facade Host API failure",
};
```

Do not add an operation name, JSON branch, C symbol, snapshot registry, or mutable Snapshot handle.

- [ ] **Step 7: Run GREEN and ABI checks**

```bash
cmake --build build/core/dev --target \
  lmdj_take_journal_tests \
  lmdj_application_facade_tests \
  lmdj_application_c_api_tests \
  lmdj_application_dynamic_load_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^(project_io\.take_journal|facade\.)'
```

Expected: Project I/O, Facade, C ABI, and dynamic-load checks pass.

- [ ] **Step 8: Commit Task 2**

Stage only Task implementation/test files, inspect staged list/check, and commit. Defer Module manifests and exact dependency identities to Task 6 so no intermediate commit publishes a partially updated version graph:

```bash
git commit -m "feat(facade): add realtime snapshot and take batch APIs"
```

### Task 3: Prepare and publish immutable Sample Banks safely

**Files:**

- Create: `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- Create: `packages/audio-runtime/src/prepared_sample_bank.cpp`
- Create: `tests/core/audio/prepared_sample_bank_test.cpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `tests/core/audio/realtime_engine_test.cpp`
- Modify: `tests/core/audio/coreaudio_output_test.cpp`
- Modify: `tests/platform/audio/native_audio_probe.cpp`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: immutable Cooker Snapshot or validated mono float32 Probe data on one serialized control thread.
- Produces: move-only `PreparedSampleBank`, four fixed Engine Bank Slots, callback-boundary publication, old-Voice pinning, and control-thread reclamation.

- [ ] **Step 1: Write failing Sample Bank conversion tests**

Define the public control-thread API:

```cpp
class PreparedSampleBank final {
 public:
  PreparedSampleBank(PreparedSampleBank&&) noexcept;
  PreparedSampleBank& operator=(PreparedSampleBank&&) noexcept;
  PreparedSampleBank(const PreparedSampleBank&) = delete;
  PreparedSampleBank& operator=(const PreparedSampleBank&) = delete;

  static foundation::Result<PreparedSampleBank> from_snapshot(
      const cooker::RuntimeSnapshot& snapshot);
  static PreparedSampleBank empty(
      foundation::ProjectId project_id,
      std::uint64_t project_revision);
  foundation::Result<void> set_sample(
      std::uint8_t slot,
      std::span<const float> mono_pcm);
  std::uint64_t availability_mask() const noexcept;
  std::size_t sample_count() const noexcept;
};
```

Test mono PCM16 values `{-32768, -16384, 0, 16384, 32767}` and stereo frames `{32767,-32768}`, `{16384,16384}`. Assert finite mono float output through an Engine render, duplicate/out-of-range/empty Samples reject, and all 64 bits can be set.

- [ ] **Step 2: Run Sample Bank RED**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_prepared_sample_bank_tests
```

Expected: target/header/symbols are missing.

- [ ] **Step 3: Implement move-only Bank preparation**

Store Project ID/revision, `std::array<std::vector<float>, 64>`, and `uint64_t availability_mask_` privately. Use:

```cpp
constexpr float pcm16_to_float(std::int16_t value) noexcept {
  return value < 0 ? static_cast<float>(value) / 32768.0F
                   : static_cast<float>(value) / 32767.0F;
}
```

For stereo, convert each channel then average with `0.5F`. Validate all source dimensions before allocating destination vectors; `set_sample` copies only finite non-empty mono spans while Bank is still owned by the control thread.

- [ ] **Step 4: Write failing publication/old-Voice tests**

Add:

```cpp
inline constexpr std::size_t kRealtimeBankCapacity = 4;
inline constexpr std::size_t kRealtimePublishQueueCapacity = 4;

enum class PublishResult : std::uint8_t {
  accepted,
  bank_slots_full,
  publish_queue_full,
};

struct BankTelemetry {
  std::uint64_t current_generation;
  std::uint64_t accepted_publications;
  std::uint64_t applied_publications;
  std::uint64_t reclaimed_banks;
  std::uint64_t bank_slot_rejections;
  std::uint64_t publish_queue_drops;
};

PublishResult publish_sample_bank(PreparedSampleBank bank) noexcept;
std::size_t reclaim_retired_banks() noexcept;
BankTelemetry bank_telemetry() const noexcept;
```

Tests must prove: publish while stopped; new Sample after running publish starts only after next render boundary; a long old Voice finishes from old bytes after swap; new Voice reads new bytes; current Bank is never reclaimed; four Slot backpressure is explicit; callback completion makes retired Slot reclaimable; failed publish leaves old Bank available.

- [ ] **Step 5: Run Engine RED**

```bash
cmake --build build/core/dev --target lmdj_realtime_engine_tests
```

Expected: compilation fails because publication methods and storage do not exist.

- [ ] **Step 6: Refactor Engine into fixed Bank Slots**

Each Slot owns one moved `PreparedSampleBank`, an atomic state, and an audio-thread-only active Voice count. Each Voice gains `std::uint8_t bank_slot`. `render` begins with:

```cpp
std::uint8_t pending = 0;
while (publish_queue_.try_pop(pending)) {
  retire_current_bank_if_needed();
  current_bank_ = pending;
  bank_slots_[pending].state.store(BankState::current,
                                   std::memory_order_release);
  availability_mask_.store(bank_slots_[pending].bank.availability_mask(),
                           std::memory_order_release);
  applied_publications_.fetch_add(1, std::memory_order_relaxed);
}
```

Voice creation reads Sample address/length from the current Slot and increments its audio-thread count. Voice completion decrements the exact Slot count and marks a `retiring` Slot `reclaimable` when zero. `reclaim_retired_banks` is the only function that clears vectors. `enqueue` validates availability through the atomic mask and never reads a vector.

Keep existing `load_sample`/`clear_sample` as stopped-time compatibility wrappers over a private prepared legacy Bank so 5A public behavior and tests remain valid; migrate the Probe to explicit Bank publication to exercise the new path.

- [ ] **Step 7: Prove render allocation/deallocation safety and GREEN**

Extend the existing global allocation counter so the measured region covers Bank apply, old Voice completion, `retiring → reclaimable`, and mixing. Then run:

```bash
cmake --build build/core/dev --target \
  lmdj_prepared_sample_bank_tests \
  lmdj_realtime_engine_tests \
  lmdj_audio_coreaudio_tests \
  lmdj_native_audio_probe
ctest --test-dir build/core/dev --output-on-failure \
  -R '^audio\.(prepared_sample_bank|realtime_engine|coreaudio_output|native_probe_no_device)$'
```

Expected: all selected tests pass and measured render allocations remain zero.

- [ ] **Step 8: Commit Task 3**

Register the new source/test/coverage target. Stage only Task implementation/test/build files, inspect check/list, and commit. Task 6 updates all Module versions and exact dependencies together:

```bash
git commit -m "feat(audio): publish immutable sample banks at render boundaries"
```

### Task 4: Capture actual Voice starts through a lock-free Ring

**Files:**

- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `tests/core/audio/realtime_engine_test.cpp`
- Modify: `tests/core/audio/realtime_engine_stress_test.cpp`

**Interfaces:**

- Consumes: successful Voice starts inside `render` and serialized control arm/disarm requests.
- Produces: fixed 4,096-event audio-to-writer Capture Ring, exact Runtime frame offsets, corruption state, and background-thread drain.

- [ ] **Step 1: Write failing Capture API tests**

Add:

```cpp
inline constexpr std::size_t kRealtimeCaptureCapacity = 4'096;

enum class CaptureState : std::uint8_t {
  idle,
  arm_pending,
  active,
  disarm_pending,
  corrupted,
};

struct CapturedTriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
  std::uint32_t frame_offset;
};

struct CaptureTelemetry {
  CaptureState state;
  std::uint64_t captured_events;
  std::uint64_t drained_events;
  std::uint64_t capture_drops;
  std::uint64_t capture_origin_frame;
};

foundation::Result<void> arm_capture() noexcept;
foundation::Result<void> disarm_capture() noexcept;
std::size_t drain_capture(
    std::span<CapturedTriggerEvent> output) noexcept;
CaptureTelemetry capture_telemetry() const noexcept;
```

Test `arm_pending → active` at next render, two callbacks before first Trigger, exact frame offset, disarm after current callback, only successful Voice starts captured, 4,096 exact capacity, one overflow sets `corrupted`, drain FIFO, and restart clears stale Capture without replay.

- [ ] **Step 2: Run Capture RED**

```bash
cmake --build build/core/dev --target lmdj_realtime_engine_tests
```

Expected: Capture types/methods are missing.

- [ ] **Step 3: Implement callback-owned Capture state**

Use `FixedSpscQueue<CapturedTriggerEvent, 4096>`. Control methods use atomic CAS to publish pending transitions. At render entry, `arm_pending` saves current cumulative rendered frame as origin and becomes active. Immediately after a Voice is successfully allocated, write:

```cpp
const auto offset = absolute_start_frame - capture_origin_frame_;
if (offset > std::numeric_limits<std::uint32_t>::max() ||
    !capture_ring_.try_push(CapturedTriggerEvent{
        event.sequence,
        event.slot,
        event.velocity,
        static_cast<std::uint32_t>(offset),
    })) {
  capture_drops_.fetch_add(1, std::memory_order_relaxed);
  capture_state_.store(CaptureState::corrupted,
                       std::memory_order_release);
} else {
  captured_events_.fetch_add(1, std::memory_order_relaxed);
}
```

Do not capture invalid events or voice drops. Process `disarm_pending` only after voices/events for the current callback are handled. `drain_capture` is a bounded pop loop with no allocation.

- [ ] **Step 4: Extend stress to simultaneous Trigger and Capture transport**

Run one producer thread enqueuing 100,000 monotonically sequenced events, one render consumer, and one Capture drain consumer. The consumer records sequences in a preallocated vector. Assert FIFO, no duplicate/loss while the writer keeps up, all counters reconcile, and the test remains labeled only `stress`.

- [ ] **Step 5: Run GREEN, stress, and TSan**

```bash
cmake --build build/core/dev --target \
  lmdj_realtime_engine_tests lmdj_realtime_engine_stress_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^audio\.realtime_engine$'
scripts/core.sh configure tsan
cmake --build build/core/tsan --target \
  lmdj_realtime_engine_tests lmdj_realtime_engine_stress_tests
ctest --test-dir build/core/tsan --output-on-failure \
  -R '^audio\.realtime_(engine|spsc_stress)$'
```

Expected: component and stress tests pass with no ThreadSanitizer report.

- [ ] **Step 6: Commit Task 4**

Stage only the four Audio Runtime/test files, inspect staged list/check, and commit:

```bash
git commit -m "feat(audio): capture realtime voice starts without locks"
```

### Task 5: Build the Formal Native Host and its portable black-box path

**Files:**

- Create: `apps/native-test-host/module.json`
- Create: `apps/native-test-host/CMakeLists.txt`
- Create: `apps/native-test-host/src/capture_writer.hpp`
- Create: `apps/native-test-host/src/capture_writer.cpp`
- Create: `apps/native-test-host/src/main.cpp`
- Create: `tests/host/native_host_test.py`
- Create: `tests/host/native_host_source_boundary_test.py`
- Create: `tests/host/native_host_apple_smoke.py`
- Modify: `CMakeLists.txt`
- Modify: `products/lmdj/CMakeLists.txt`

**Interfaces:**

- Consumes: typed Facade Snapshot/batch APIs, Audio Runtime Bank/Capture APIs, existing CoreAudio adapter, and installed compiled Assembly.
- Produces: `lmdj-native-host` with strict invocation, JSONL control protocol, serialized Facade gate, sole Trigger producer, background Capture Writer, and deterministic driver.

- [ ] **Step 1: Create failing source-boundary and invocation tests**

The source test recursively reads `apps/native-test-host` and fails on:

```python
forbidden = (
    "lmdj/project_io/",
    "project_store.hpp",
    "take_journal.hpp",
    "std::ifstream",
    "std::ofstream",
    "filesystem::directory_iterator",
)
```

It also reads the generated link-libraries file and requires exactly direct logical dependencies on `lmdj::application` and `lmdj::audio_runtime` plus Apple `lmdj::audio_coreaudio` only under Apple Product wiring.

The black-box test first invokes no args and asserts exit 64 plus the exact usage string from design §10.1.

- [ ] **Step 2: Register a minimal failing Host target**

Add:

```cmake
add_executable(
  lmdj_native_host
  src/main.cpp
  src/capture_writer.cpp
)
set_target_properties(
  lmdj_native_host PROPERTIES OUTPUT_NAME lmdj-native-host
)
target_link_libraries(
  lmdj_native_host PRIVATE lmdj::application lmdj::audio_runtime
)
if(APPLE)
  target_link_libraries(lmdj_native_host PRIVATE lmdj::audio_coreaudio)
endif()
file(GENERATE
  OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/lmdj_native_host.link-libraries.txt"
  CONTENT "$<TARGET_PROPERTY:lmdj_native_host,LINK_LIBRARIES>\n")
```

Register `host.native_source_boundary` on all platforms and `host.native` using the target plus `--no-device` fixture path.

- [ ] **Step 3: Run Host RED**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_native_host
ctest --test-dir build/core/dev --output-on-failure \
  -R '^host\.native'
```

Expected: target source and Host tests fail because the implementation/protocol is absent.

- [ ] **Step 4: Implement strict invocation and installed Assembly setup**

Parse exactly the four required flag/value pairs plus optional `--no-device`; reject duplicates, relative/non-normalized paths, invalid UTF-8, or invalid Pattern UUID before creating Application. Always call `load_installed_assembly`, then construct:

```cpp
lmdj::facade::Application application(
    lmdj::facade::ApplicationConfig{
        invocation.workspace,
        std::move(assembly.providers),
        std::move(assembly.provider_policy),
        {},
    });
```

Prepare Snapshot, prepare/publish Bank, start Engine, then either CoreAudio or the deterministic driver. Output `ready` only after all selected backend steps succeed.

- [ ] **Step 5: Implement bounded JSONL and single Trigger producer**

Read at most 65,537 bytes per line so a 64 KiB command plus newline is accepted and an overlong line is drained/rejected. Parse UTF-8 object depth at most 32. Use exact-key checks per operation. Convert Pad slot using:

```cpp
const auto global_slot = static_cast<std::uint8_t>(bank * 16U + pad);
const auto result = engine.enqueue(
    lmdj::audio::TriggerEvent{next_sequence++, global_slot, velocity});
```

Only this main loop calls `enqueue`. `--no-device` renders 128-frame blocks after accepted Trigger until active voices return to zero. All responses are one-line JSON written/flushed by the main thread.

- [ ] **Step 6: Implement CaptureWriter with serialized Facade access**

The writer owns references to Engine, Application, a Host `std::mutex&`, Project path, Take ID, one `std::jthread`, and atomic stop/failure counters. Its loop is:

```cpp
std::array<CapturedTriggerEvent, 64> captured{};
bool observed_final_empty_drain = false;
while (!observed_final_empty_drain) {
  const auto count = engine.drain_capture(captured);
  if (count == 0) {
    const auto state = engine.capture_telemetry().state;
    if (stop_requested() &&
        (state == CaptureState::idle || state == CaptureState::corrupted)) {
      observed_final_empty_drain = true;
      continue;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
    continue;
  }
  std::vector<domain::RawTakeEvent> events;
  events.reserve(count);
  for (std::size_t index = 0; index < count; ++index) {
    events.push_back(to_raw_take_event(captured[index]));
  }
  std::lock_guard lock(facade_mutex);
  const auto appended = application.append_realtime_take_events(
      project_path, take_id, events);
  if (!appended.has_value()) {
    store_writer_failure(appended.error());
    break;
  }
  persisted_events.fetch_add(count, std::memory_order_relaxed);
}
```

Exit occurs only after stop requested, Capture is idle/corrupted, and one final zero-count drain. The Writer may allocate, sleep, and lock because it is never the Audio Thread.

- [ ] **Step 7: Implement record and reload lifecycle**

`record.begin` calls existing `take.begin` while holding the Facade mutex, starts Writer, calls `arm_capture`, waits for `active` with a two-second monotonic deadline, then accepts triggers. `record.stop` calls `disarm_capture`, waits for `idle` or `corrupted`, requests Writer stop, joins, drains final events, and reports counts. On corruption/failure it calls the typed `Application::seal_realtime_take` from Task 2 with reason `capture_incomplete`; Host never includes or calls `TakeJournal`.

`record.commit` is rejected unless stop was complete and clean, then forwards the exact existing `take.commit` request under the Facade mutex. `snapshot.reload` prepares a full Snapshot/Bank under the same mutex and publishes only after success.

- [ ] **Step 8: Complete black-box behavior tests**

Create a real fixture bundle through `lmdj-core`, import two deterministic WAVs, assign two Pads, and create a Pattern. Start Host with `--no-device`, then assert ready → two triggers → status → record begin → 20+1 triggers → record stop → explicit Pattern commit → Project inspect shows RawTake/Pattern → snapshot reload → stop/rejected trigger/start → quit. Add negative cases for invalid/oversized JSON, failed reload retaining the old Bank, writer failure sealing recovery, and non-Apple real-device mode returning `UNSUPPORTED_AUDIO`.

- [ ] **Step 9: Run Host GREEN and Apple state smoke**

```bash
cmake --build build/core/dev --target lmdj_native_host lmdj_core_cli
ctest --test-dir build/core/dev --output-on-failure \
  -R '^host\.native'
if [[ "$(uname -s)" == "Darwin" ]]; then
  python3 tests/host/native_host_apple_smoke.py \
    build/core/dev/bin/lmdj-native-host
fi
```

Expected: source boundary, portable Host E2E, and platform behavior pass. Apple smoke proves startup/lifecycle only, not audibility. The complete versioned module graph is verified after Task 6 updates every exact identity together.

- [ ] **Step 10: Commit Task 5**

Set Host manifest to:

```json
{
  "contract": "lmdj.module.v1",
  "module": "native-test-host",
  "version": "1.0.0",
  "api_version": 1,
  "dependencies": {
    "application-facade": "1.1.0",
    "audio-runtime": "0.3.0"
  }
}
```

Stage only the Host, Host tests, root CMake, and Product CMake files. Inspect staged list/check and commit:

```bash
git commit -m "feat(host): add formal native realtime project host"
```

### Task 6: Integrate Product version, Assembly, distribution, and Proof identity

**Files:**

- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/assembly.lock.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `products/lmdj/README.md`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `packages/project-cooker/module.json`
- Modify: `packages/audio-runtime/module.json`
- Modify: `packages/project-io/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `tests/distribution/package_acceptance_test.py`
- Modify: `scripts/package-core.py`
- Modify: `scripts/core.sh`

**Interfaces:**

- Consumes: completed Module/Host versions and `lmdj_native_host` target.
- Produces: exact Product Build `1.0.11.0`, matching compiled/locked Assembly, package inventory, and Proof output.

- [ ] **Step 1: Write failing version/lock/package expectations**

Update tests first to require Product `1.0.11.0`, Cooker `0.2.0`, Project I/O `0.3.0`, Audio `0.3.0`, Facade `1.1.0`, CLI/MCP `1.0.2`, and Host `1.0.0`. The package test must require `bin/lmdj-native-host` in addition to `bin/lmdj-core`; the module graph must read the Host manifest and reject `project-io` as a direct dependency.

- [ ] **Step 2: Run identity RED**

```bash
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/module_graph_test.py
```

Expected: assertions fail against the old Product/Assembly/Host inventory.

- [ ] **Step 3: Update all exact identities**

Change Product version to `{milestone:1, minor:0, build:11, patch:0}`. Update Assembly modules/hosts and compiled catalog to the table above. Bump CLI/MCP manifests to `1.0.2`, exact Facade dependency `1.1.0`, and MCP Python package identity `1.0.2`. Link `lmdj_product_lmdj_assembly` into `lmdj_native_host` from `products/lmdj/CMakeLists.txt`.

- [ ] **Step 4: Package the formal Host**

In `scripts/package-core.py`, resolve and require `build_root/bin/lmdj-native-host`, copy it to package `bin/`, preserve executable mode, include its SHA-256 in the package artifact manifest, and make package acceptance invoke `--no-device` usage without opening a real device.

- [ ] **Step 5: Generate and verify the Assembly lock**

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

Expected: `assembly lock generated` then `version verification: PASS (1.0.11.0)`.

- [ ] **Step 6: Update Product status and Proof output**

README status must say 5A Probe and 5B Formal Native Host are implemented, while GUI, physical input adapters/tests, product concurrency, Creator/Web product, Sample intelligence, Sequence editing, production Providers, and deployment remain incomplete. Change only Proof's final Product line to `1.0.11.0`; keep Channel `canary` and stress exclusion unchanged.

- [ ] **Step 7: Run version, assembly, build, package, and Proof GREEN**

```bash
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/module_graph_test.py
scripts/core.sh configure release
scripts/core.sh build release
python3 tests/distribution/package_acceptance_test.py \
  --build-root build/core/release
scripts/core.sh proof
```

Expected: all identity/graph/package tests pass; Proof ends with Product Build `1.0.11.0`, Channel `canary`, Assembly lock `MATCH`.

- [ ] **Step 8: Commit Task 6**

Stage only the listed identity/assembly/package files, inspect list/check, and commit:

```bash
git commit -m "build(lmdj): assemble product build 1.0.11.0"
```

### Task 7: Run complete quality gates and record physical acceptance

**Files:**

- Create: `docs/quality/2026-08-02-formal-native-host-acceptance.md`
- Modify: `docs/superpowers/plans/2026-08-02-lmdj-formal-native-realtime-host.md`

**Interfaces:**

- Consumes: the complete 5B branch and real current Mac default built-in or wired output.
- Produces: reproducible automated logs, requirement-by-requirement review, physical Project playback/live-reload/20+1 Capture evidence, and a final completion audit.

- [ ] **Step 1: Run fresh dev/full and stress gates**

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev full
scripts/core.sh test dev stress
```

Expected: all non-stress and stress CTests pass; no stale build result is accepted.

- [ ] **Step 2: Run ASan full and stress gates**

```bash
scripts/core.sh configure asan
scripts/core.sh build asan
scripts/core.sh test asan full
scripts/core.sh test asan stress
```

Expected: all tests pass with no AddressSanitizer or LeakSanitizer defect.

- [ ] **Step 3: Run TSan full and stress gates**

```bash
scripts/core.sh configure tsan
scripts/core.sh build tsan
scripts/core.sh test tsan full
scripts/core.sh test tsan stress
```

Expected: all tests pass with no ThreadSanitizer report.

- [ ] **Step 4: Run coverage and integrated Proof**

```bash
scripts/core.sh coverage report
scripts/core.sh coverage check
scripts/core.sh proof
```

Expected: coverage policy passes and the fresh integrated Proof passes for `1.0.11.0`.

- [ ] **Step 5: Run direct architecture and repository gates**

```bash
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
git diff --check
```

Expected: dependencies, active tree, version, Assembly lock, and whitespace all pass.

- [ ] **Step 6: Perform the Apple physical Gate**

Use the exact seven-step design §12.4 flow with a real fixture Project and default built-in or wired output. Export the Host JSONL transcript and record: Mac model, macOS version, output route, target SHA, Project revision, Pattern ID, Pad artifacts, 20+1 counts, Take/Pattern IDs, zero-drop telemetry, reload observation, restart observation, and quit exit status. If any audible mapping, reload, Capture, commit, restart, or telemetry requirement fails, 5B is incomplete.

- [ ] **Step 7: Write acceptance evidence and completion matrix**

The acceptance document must separate:

```text
Design requirement | Automated evidence | Physical evidence | Result
```

It must state that stdin/no-device is not Keyboard/MIDI/Pointer latency proof, current Channel remains canary, and no tag/release/deploy occurred.

- [ ] **Step 8: Self-review realtime and failure paths**

Inspect every call reachable from `RealtimeEngine::render`, Bank apply, Voice completion, Capture push/drop, and CoreAudio callback. Record explicit evidence for no allocation/deallocation/lock/I/O/JSON/log/Facade. Inspect overflow, Writer failure, failed reload, revision conflict, stop, restart, and terminal CoreAudio cleanup behavior. A test pass without this source audit is insufficient.

- [ ] **Step 9: Commit Task 7**

Mark only actually completed plan checkboxes, stage the acceptance document and plan, run staged list/check, and commit:

```bash
git commit -m "test(host): record formal native host acceptance"
```

- [ ] **Step 10: Final branch audit without remote mutation**

```bash
git log --oneline --decorate origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: only planned commits/files exist, the worktree is clean, and the branch remains local unless the user separately authorizes push/PR/merge.

## Plan Self-Review

- Spec coverage: Tasks 1–7 cover Snapshot, typed Facade, Sample Bank publication, Capture Ring, Writer/recovery, Formal Host, Assembly/package/version, automation, realtime audit, and physical Gate.
- Open product boundary: no Task implements selective rebase, quantization, UI, MIDI/Keyboard/Pointer, audio input, or release actions.
- Type continuity: `ResolvedPad` feeds `PreparedSampleBank::from_snapshot`; Engine publication feeds Trigger/Voice; successful Voice starts feed `CapturedTriggerEvent`; Writer converts to `RawTakeEvent`; Facade batch appends to the existing Take Journal and `take.commit` path.
- Failure continuity: prepare/publish failure retains old Bank; Capture or Writer failure seals recovery and forbids commit; CoreAudio terminal cleanup remains inherited from 5A.
- Version continuity: every exact dependency and Product identity from design §14 is updated only after the corresponding implementation exists.
