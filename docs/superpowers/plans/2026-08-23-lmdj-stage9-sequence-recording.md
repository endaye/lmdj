# LMDJ Stage 9 Sequence Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Product Build `1.0.30.0` as a testable Stage 9 candidate in which Creator records, overdubs, switches, trims, reloads, and recovers deterministic Pattern events without a Raw Take or Take product object.

**Architecture:** Replace Project Truth with total `lmdj.project.v3` migration, then build one Project-scoped Sequence session above Project I/O's existing writer lease and manifest publication commit point. Application Facade owns admission, selective rebase, idempotent flush, and recovery orchestration; Cooker and Audio Runtime consume tick-native immutable snapshots; CLI, MCP, Native, Web Runtime, and Creator expose one shared semantic surface. The implementation is split into ten independently reviewable Tasks, with Host work parallel only after its Contract, Project I/O, Runtime, and Facade dependencies merge; the immutable Portal snapshot is a separate clean-commit boundary after version integration.

**Tech Stack:** C++20, CMake 3.24+, JSON Schema, nlohmann/json, SHA-256 canonical JSON vectors, Emscripten `6.0.5`, WasmFS OPFS, SharedArrayBuffer, Wasm AudioWorklet, JavaScript ES modules, React `19.2.8`, TypeScript `7.0.2`, Vite `8.2.1`, Vitest `4.1.10`, Playwright `1.62.1`, Python 3.11, Docusaurus Architecture Portal, GitHub Issues/Projects.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-08-22-sequence-recording-semantics-design.md`. Any conflict returns to design review; an implementation Task must not silently choose a different semantic.
- Stage 9 implementation starts only after the design/plan commit is merged and Issue #238's durable-decision acceptance is satisfied. The question Issue is not evidence that runtime behavior exists.
- Execute each Task on a short-lived `feat/<task>` or `docs/<task>` branch in an isolated worktree. Never implement on `main` or in this retained design worktree.
- Each Task below maps one-to-one to one GitHub Issue, one reviewable Conventional Commit, and one Pull Request. Do not combine Tasks to bypass dependency gates.
- Functional Tasks keep active manifests and Product Build at their current values until Task 9. Task 9 is the version/current-truth integration boundary; Task 10 is the separate clean-commit immutable Portal snapshot boundary.
- Project Truth is authoritative. Runtime Snapshot and the audible journal overlay are derived, immutable publications and are never persisted as Project Truth.
- Hosts use only Application Facade. They must not parse a Project bundle, read the journal directly, mint recovery decisions, or reproduce quantization, fingerprint, selective-rebase, or flush rules.
- Exactly one Sequence session may be active per Project bundle. Admission and `expected_revision` validation occur under the same existing Project writer lease. A second begin is `INVALID_ARGUMENT`; failure to acquire the lease is `PROJECT_BUSY`.
- A successful flush is committed only when the new Project manifest head and its receipt are durably published and visible on reload. Transaction-file or checkpoint durability is not success.
- `session_id`, `flush_seq`, and `command_id` are durably journaled before Project mutation. A visible matching receipt is replayed, never overdubbed again. Journal cleanup happens only after all transactions are durable and reconciled.
- Recovery reconciles visible receipts before sealing `owner_lost`. It can append only when the stored Pattern fingerprint still matches; deletion, bounds changes, or fingerprint mismatch fail closed and retain the recovery file.
- Transport timing is integer-only with PPQ `960` and denominator `48,000 × 60`. BPM changes freeze `(runtime_frame, tick_numerator, bpm)` and preserve the fractional remainder; no floating-point timing enters Project Truth or cross-language vectors.
- Quantization and Swing are recording-time transformations only. Stored events remain `{slot, onset_tick, duration_tick, velocity}`. Quantize-off preserves raw tick positions and ignores Swing.
- Stage 8B capture remains an in-Sequence trimming overlay lasting at most five seconds. It does not navigate to Sample, does not trigger SR-D9, and follows Stage 8B explicit-commit/conflict-buffer behavior.
- This plan authorizes local commits only. Push, Pull Request creation, squash merge, Product tag, Release publication, deployment, and Channel promotion require separate authorization.
- Before every Task commit: run the Task-specific tests and `scripts/architecture-portal.sh check`; stage only declared files; inspect `git diff --cached --name-status`; run `git diff --cached --check`; inspect the staged diff; commit; inspect `git show --name-status --oneline HEAD`; confirm no Task residue remains.

## Locked Cross-Language Constants and Types

All implementations use these values verbatim:

```text
PPQ = 960
SIXTEENTH_TICKS = 240
BAR_TICKS_4_4 = 3840
RUNTIME_SAMPLE_RATE = 48000
TICK_DENOMINATOR = 2880000
SWING_PERCENT_MIN = 50
SWING_PERCENT_MAX = 75
```

The v3 authoring types are:

```cpp
enum class ProjectContract : std::uint8_t { v1, v2, v3 };

struct PatternEvent {
  PadSlotId slot;
  std::uint32_t onset_tick;
  std::uint32_t duration_tick;
  std::uint8_t velocity;
  bool operator==(const PatternEvent&) const = default;
};

struct ProjectState {
  ProjectContract contract;
  foundation::ProjectId id;
  std::uint64_t revision;
  std::uint16_t bpm;
  bool quantize_enabled;
  std::uint8_t swing_percent;
  std::array<std::array<PadSlot, 16>, 4> banks;
  std::map<foundation::AssetId, Asset> assets;
  std::map<foundation::PatternId, Pattern> patterns;
};

struct MergePatternEvents {
  CommandMeta meta;
  foundation::PatternId pattern_id;
  std::vector<PatternEvent> events;
};

struct UpdateSequenceSettings {
  CommandMeta meta;
  std::optional<std::uint16_t> bpm;
  std::optional<bool> quantize_enabled;
  std::optional<std::uint8_t> swing_percent;
};
```

`RawTakeEvent`, `RawTake`, `RecordTake`, `TakeId`, `takes`, `take.begin`, `take.append`, `take.commit`, and `take.recoverable` are removed from the active product surface. A compatibility reader may recognize v1/v2 input but may not emit either retired shape.

Canonical event order is `(onset_tick, slot.bank, slot.pad)`. Within one flush, the later captured event for the same `(slot, onset_tick)` replaces the earlier event. Across overdubs, incoming events replace stored events at the same key. `duration_tick` is clamped to `1…(bars × 3840 - onset_tick)` and is derived from raw absolute attack/release ticks, not from a quantized onset.

## Locked Project v3 Migration

The writer emits only `lmdj.project.v3`:

```json
{
  "contract": "lmdj.project.v3",
  "project_id": "lowercase UUID",
  "revision": 7,
  "bpm": 120,
  "sequence_settings": {
    "quantize_enabled": true,
    "swing_percent": 50
  },
  "banks": [],
  "assets": [],
  "patterns": [
    {
      "pattern_id": "lowercase UUID",
      "bars": 1,
      "events": [
        {
          "slot": {"bank": 0, "pad": 0},
          "onset_tick": 0,
          "duration_tick": 240,
          "velocity": 100
        }
      ]
    }
  ]
}
```

The v1/v2 total migration sets `quantize_enabled=true` and `swing_percent=50`; converts `step` to `onset_tick=step×240`; uses `duration_tick=240`; discards `takes`; resolves duplicate `(slot, step)` entries by last-write-wins in original array order; sorts canonically; and writes v3 on the next successful mutation. Migration is deterministic and has no user choice.

## Locked Session, Journal, and Facade Surface

`foundation::SequenceSessionId` is a UUID strong type. The journal contains enough identity to replay or recover without a Host inference:

```cpp
enum class SequenceSessionState : std::uint8_t {
  active,
  switching,
  stopped,
  owner_lost,
  abandoned,
};

struct SequenceFlushRecord {
  std::uint64_t flush_seq;
  foundation::CommandId command_id;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision;
  std::vector<domain::PatternEvent> canonical_events;
  bool completed;
};

struct ActiveSequenceJournal {
  foundation::SequenceSessionId session_id;
  foundation::PatternId pattern_id;
  std::uint8_t bars;
  std::string pattern_fingerprint;
  std::uint64_t expected_revision;
  std::uint64_t next_flush_seq;
  SequenceSessionState state;
  std::vector<SequenceFlushRecord> flushes;
};
```

The public typed Facade uses one authority surface; JSON, C ABI, CLI, MCP, Native, and Web bindings are adapters over it:

```cpp
struct SequenceBeginRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision;
  std::uint64_t runtime_frame;
};

struct SequencePadEvent {
  domain::PadSlotId slot;
  std::uint8_t velocity;
  std::uint64_t runtime_frame;
  std::uint64_t input_sequence;
  bool pressed;
};

struct SequenceSwitchRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  foundation::PatternId next_pattern_id;
};

struct SequenceRecoveryRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  std::optional<foundation::PatternId> destination_pattern_id;
};
```

Operation names are `sequence.record.begin`, `sequence.record.event`, `sequence.record.flush`, `sequence.record.stop`, `sequence.record.switch-request`, `sequence.record.status`, `sequence.recovery.list`, `sequence.recovery.apply`, and `sequence.recovery.discard`. `sequence.record.status` is the single Query used by a second Creator window, CLI, and MCP. Query methods do not mutate or acquire ownership.

## Dependency Order

```text
Task 1 durable decision
  └─ Task 2 Project v3 Contract and Domain
       ├─ Task 3 Sequence Journal and Project I/O
       │    └─ Task 5 Application Facade
       └─ Task 4 tick-native Cooker and Audio Runtime
            └─ Task 5 Application Facade
                 ├─ Task 6 CLI, MCP, and Native Host
                 └─ Task 7 Web Runtime Platform and Web Host
                      └─ Task 8 Creator Sequence UX
Tasks 1–8 ────────────────└─ Task 9 version, current Portal, and acceptance integration
                                   └─ Task 10 immutable snapshot and final acceptance
```

Tasks 3 and 4 may run in parallel after Task 2. Tasks 6 and 7 may run in parallel after Tasks 4 and 5. Task 8 starts only after Task 7's runtime contract is stable. Integration and snapshotting remain serial through Tasks 9 and 10.

## Design Traceability

| Approved decision | Primary implementation Tasks | Acceptance witness |
|---|---|---|
| SR-D1–D4: Pattern-only, Sequence naming, event-only capture, Slot references | 1, 2, 5, 6, 7, 8 | no active Take symbols; v3 Contract/Facade/Host parity |
| SR-D5–D7: destructive Quantize, defaults, PPQ 960 | 2, 4, 5 | Contract/Domain and cross-language timing vectors |
| SR-D8–D10: Play/Record/Sample transitions and flush | 5, 7, 8 | Facade state-machine and Creator browser journey |
| SR-D11–D13: next-Bar switch, overdub, audible overlay | 3, 4, 5, 7, 8 | boundary, replacement, and next-loop tests |
| SR-D14, SR-D16, SR-D18: settings rebase and rejected Command classes | 3, 5, 6, 7 | revision/lease/selective-rebase matrix |
| SR-D15, SR-D24: Stage 8B trimming overlay | 5, 8 | capture/trim/conflict-buffer component and browser tests |
| SR-D17, SR-D20–D22: ownership, flush idempotency, owner-loss recovery | 3, 5, 6, 7 | fault matrix, stress tests, restart and cross-Host tests |
| SR-D19, SR-D28: Project v3 and total migration | 2, 9 | Contract fixtures, migration vectors, Assembly v3 lock |
| SR-D23: one effective switch boundary | 3, 4, 5, 7, 8 | old-slot/new-slot boundary integration test |
| SR-D25: integer transport clock and BPM anchors | 4, 5, 7 | C++/Python/JavaScript timing vectors |
| SR-D26: canonical event/overdub invariants | 2, 3, 5 | shared canonicalization and merge vectors |
| SR-D27: recording-time Swing bake | 2, 5, 8 | straight/odd-sixteenth/Quantize-off vectors |

Task 9 reruns the integrated automated witnesses; Task 10 binds their committed source identity to the immutable Portal snapshot and acceptance ledger.

## Task 1: Record the Durable Stage 9 Product Decision

**Files:**

- Modify: `docs/prd/decision-log.md`
- Create: `docs/prd/decisions/2026-08-23-sequence-recording-semantics.md`
- Delete: `docs/prd/questions/take-event-vs-audio-bounce.md`
- Delete: `docs/prd/questions/recording-concurrency-semantics.md`
- Modify: `docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
- Modify: `products/lmdj/README.md`
- Modify: `apps/architecture-portal/docs/contracts/project.md`
- Modify: `apps/architecture-portal/docs/product/workflows.md`
- Test: `tests/build/test_active_tree.sh`

- [ ] Add `docs/prd/decisions/2026-08-23-sequence-recording-semantics.md` and a dated decision-log entry that name `lmdj.project.v3`, no Raw Take, one Project-scoped session, idempotent flush, selective rebase, and fingerprint-gated recovery; link the approved design, plan, and implementation Issues.
- [ ] Delete the two resolved Stage 9 question files; `docs/prd/open-questions.md` remains unchanged because the directory itself is the canonical index.
- [ ] Correct redesign spec §6.2 and §6.5 so they describe tick-native Pattern recording and stop treating Take as active product truth.
- [ ] Update Product and Portal designed-state prose without claiming the implementation is current.
- [ ] Run `rg -n "RawTake|Raw Take|RecordTake|take\\.(begin|append|commit|recoverable)" docs/prd products/lmdj apps/architecture-portal/docs docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`; expect no active-authority claim that Take remains Stage 9 Project Truth.
- [ ] Run `bash tests/build/test_active_tree.sh`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect all checks PASS.
- [ ] Commit only the listed files with `docs(prd): record Stage 9 sequence decision`.

## Task 2: Add Project v3 and Tick-Native Authoring Domain

**Files:**

- Create: `contracts/project/lmdj.project.v3.schema.json`
- Create: `tests/fixtures/contracts/project-v3-valid.json`
- Create: `tests/fixtures/contracts/project-v3-invalid-event.json`
- Modify: `tests/conformance/schema_contract_test.py`
- Modify: `tests/conformance/project_bundle_contract_test.py`
- Modify: `packages/foundation/include/lmdj/foundation/ids.hpp`
- Modify: `packages/authoring-domain/include/lmdj/domain/project.hpp`
- Modify: `packages/authoring-domain/include/lmdj/domain/commands.hpp`
- Modify: `packages/authoring-domain/include/lmdj/domain/command_handler.hpp`
- Modify: `packages/authoring-domain/src/project.cpp`
- Modify: `packages/authoring-domain/src/command_handler.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `tests/core/domain/project_test.cpp`
- Modify: `tests/core/domain/command_handler_test.cpp`
- Modify: `tests/core/domain/model_sequence_test.cpp`
- Modify: `tests/core/project_io/project_store_test.cpp`

- [ ] Add failing schema/Domain boundary tests that preserve BPM `40…240` and bars `{1,2,4,8}`, and enforce velocity `1…127`, Swing `50…75`, onset `< bars×3840`, and duration `1…loop remainder`.
- [ ] Add failing Domain tests for duplicate replacement, earlier-half quantization, last-grid wrap to tick `0`, Swing on odd sixteenths, duration from raw release, and canonical ordering.
- [ ] Add failing v1/v2 migration vectors proving defaults, `step×240`, 240-tick duration, Take removal, original-array last-write-wins, and byte-stable v3 output.
- [ ] Add `SequenceSessionId`, v3 Project/Pattern types, `MergePatternEvents`, and `UpdateSequenceSettings`; remove Take types and `RecordTake` from active headers.
- [ ] Implement shared integer helpers `quantize_onset_tick`, `normalize_duration_tick`, and `merge_pattern_events`; neither Schema adapters nor Hosts may duplicate them.
- [ ] Make the v3 schema the only writer target while retaining bounded v1/v2 read migration.
- [ ] Run `scripts/core.sh configure dev && scripts/core.sh build dev`; expect success.
- [ ] Run `scripts/core.sh test dev fast`; expect all unit/component tests PASS.
- [ ] Run `python3 tests/conformance/schema_contract_test.py && python3 tests/conformance/project_bundle_contract_test.py`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed Contract, fixture, Foundation, Domain, and test files with `feat(domain): add tick-native Project v3`.

## Task 3: Replace Take Journal with Idempotent Sequence Project I/O

**Files:**

- Create: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Create: `packages/project-io/src/sequence_journal.cpp`
- Delete: `packages/project-io/include/lmdj/project_io/take_journal.hpp`
- Delete: `packages/project-io/src/take_journal.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `packages/project-io/src/testing_hooks.hpp`
- Modify: `packages/project-io/CMakeLists.txt`
- Delete: `tests/core/project_io/take_journal_test.cpp`
- Create: `tests/core/project_io/sequence_journal_test.cpp`
- Modify: `tests/core/project_io/project_store_test.cpp`
- Modify: `tests/core/project_io/fault_matrix_test.cpp`
- Modify: `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- Modify: `tests/platform/web/project_io/project_io_web_faults.mjs`

- [ ] Add failing tests for a second begin, lease contention, monotonically increasing `flush_seq`, and durable `{session_id, flush_seq, command_id}` before Project mutation.
- [ ] Add a fault-injection matrix at journal write, transaction write, checkpoint write, manifest publish, reload receipt visibility, journal completion, and journal deletion.
- [ ] Prove every restart outcome is exactly one of: no visible mutation with recoverable journal, one visible mutation with replayable receipt, or reconciled completed flush; never duplicate overdub.
- [ ] Implement bundle-local `SequenceJournal` with active/sealed records, checksummed canonical JSON, append-only flush records, explicit completion, and retained failure artifacts.
- [ ] Replace `RecordTakeReplayIdentity` with `SequenceFlushIdentity {session_id, flush_seq, command_id, pattern_id}` and make `ProjectStore::execute_sequence_flush` return an existing matching receipt without reapplying events.
- [ ] Define flush commit as manifest-head publication plus reload-visible receipt; transaction/checkpoint writes remain preparation only.
- [ ] Reconcile matching receipts before `owner_lost` sealing and before any recovery list is returned.
- [ ] Compute the recovery fingerprint as lowercase SHA-256 of the exact canonical JSON preimage specified by SR-D22; add C++/Python/JavaScript shared vectors for UTF-8, key order, no BOM, and no trailing newline.
- [ ] Run `scripts/core.sh test dev fast`; expect PASS.
- [ ] Run `scripts/core.sh test dev stress`; expect the writer/flush/recovery stress tests PASS.
- [ ] Run `python3 tests/build/project_io_test_hook_symbols_test.py`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only Project I/O, build registration, vectors, and tests with `feat(project-io): add idempotent sequence journal`.

## Task 4: Make Cooker and Audio Runtime Tick-Native

**Files:**

- Modify: `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`
- Modify: `packages/project-cooker/include/lmdj/cooker/project_cooker.hpp`
- Modify: `packages/project-cooker/src/project_cooker.cpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/offline_renderer.hpp`
- Modify: `packages/audio-runtime/src/prepared_sample_bank.cpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `packages/audio-runtime/src/offline_renderer.cpp`
- Modify: `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- Modify: `tests/core/cooker/project_cooker_test.cpp`
- Modify: `tests/core/cooker/determinism_matrix_test.cpp`
- Modify: `tests/core/audio/prepared_sample_bank_test.cpp`
- Modify: `tests/core/audio/realtime_engine_test.cpp`
- Modify: `tests/core/audio/realtime_engine_stress_test.cpp`
- Modify: `tests/core/audio/offline_renderer_test.cpp`
- Modify: `tests/core/audio/snapshot_publication_invariant_test.cpp`
- Modify: `tests/core/audio/snapshot_publication_stress_test.cpp`
- Modify: `tests/fixtures/golden/reference_render.py`
- Modify: `tests/fixtures/golden/one_bar_120bpm.wav`
- Modify: `tests/fixtures/golden/one_bar_120bpm.sha256`

- [ ] Add failing Cooker tests that reject invalid tick/duration bounds and preserve canonical events in immutable Runtime Snapshot.
- [ ] Replace `ResolvedEvent::step` with `onset_tick` and `duration_tick`; include loop length and PPQ explicitly in the prepared immutable pattern.
- [ ] Add failing integer timing vectors around half-frame boundaries and BPM-anchor changes; assert identical results in C++, Python, and the Web worklet.
- [ ] Implement `tick_numerator += frames × bpm × PPQ`; derive whole ticks using denominator `2,880,000`; preserve remainder when freezing a new BPM anchor.
- [ ] Prepare event start/release boundaries on the control thread; the render thread must allocate nothing, lock nothing, parse no JSON, and perform no Project I/O.
- [ ] Schedule the audible journal overlay as a separately published immutable Pattern view. Publishing it must not mutate Project Truth or fabricate a receipt.
- [ ] Add next-Bar activation of a prepared Pattern publication; before the boundary the old Pattern remains both audible and record-active.
- [ ] Update offline rendering and the golden fixture to use v3 ticks and deterministic duration semantics.
- [ ] Run `scripts/core.sh test dev fast`; expect PASS.
- [ ] Run `scripts/core.sh test dev stress`; expect realtime publication and scheduler stress tests PASS.
- [ ] Run `scripts/core.sh proof`; expect the updated golden-render and realtime Proof PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only Cooker, Audio Runtime, fixtures, and tests with `feat(audio): schedule tick-native patterns`.

## Task 5: Add the Authoritative Sequence Application Facade

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/include/lmdj/facade/c_api.h`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/src/c_api.cpp`
- Modify: `packages/application-facade/exports_elf.map`
- Modify: `packages/application-facade/exports_macos.txt`
- Create: `tests/core/facade/sequence_surface_test.cpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/c_api_test.cpp`
- Modify: `tests/core/facade/c_api_stress_test.cpp`
- Modify: `tests/core/facade/failure_contract_test.cpp`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `tests/host/mcp_facade_parity_test.py`

- [ ] Add failing typed/JSON/C ABI parity tests for all nine locked Sequence operations and for identical error codes across adapters.
- [ ] Add failing admission tests proving the writer lease encloses owner check and `expected_revision` validation, and that Query observes but never acquires a session.
- [ ] Implement a Project-keyed session registry owned by `Application::Impl`; never key ownership by window, Host, process command, or Pattern.
- [ ] Implement integer frame-to-tick capture, paired press/release duration, quantize/Swing bake, same-key replacement, periodic/stop/switch flush, and monotonic stable flush identities.
- [ ] Classify commands as settings-only, armed-capture, or other. Settings-only changes rebase with the current revision; other external commits are queued; a competing armed capture is rejected.
- [ ] On switch request, calculate the next Bar boundary, keep the old Pattern active until it, flush the old Pattern at it, update journal identity, then publish the new runtime Pattern.
- [ ] On owner destruction or restart, reconcile receipts first, then seal `owner_lost`; never resume the old live session.
- [ ] Implement recovery apply to the original Pattern only on fingerprint match, or to a valid user-selected new Pattern; mismatch/deletion/out-of-bounds retains the sealed file and returns a typed failure.
- [ ] Remove `append_realtime_take_events` and `seal_realtime_take`; update symbol-export allowlists so no Take API remains public.
- [ ] Run `scripts/core.sh test dev fast`; expect PASS.
- [ ] Run `scripts/core.sh test dev stress`; expect session ownership/selective-rebase/flush stress tests PASS.
- [ ] Run `python3 tests/host/mcp_facade_parity_test.py`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only Facade, exports, and tests with `feat(facade): expose Sequence recording sessions`.

## Task 6: Migrate CLI, MCP, and Native Host to Sequence Operations

**Files:**

- Modify: `apps/core-cli/src/main.cpp`
- Modify: `tests/host/cli_test.py`
- Modify: `apps/core-mcp/lmdj_core_mcp/c_api.py`
- Modify: `apps/core-mcp/lmdj_core_mcp/server.py`
- Modify: `tests/host/mcp_stdio_test.py`
- Modify: `tests/host/mcp_facade_parity_test.py`
- Modify: `apps/native-test-host/src/main.cpp`
- Modify: `apps/native-test-host/src/capture_writer.hpp`
- Modify: `apps/native-test-host/src/capture_writer.cpp`
- Modify: `tests/host/native_host_test.py`
- Modify: `tests/host/native_host_apple_smoke.py`

- [ ] Replace Take commands/tools with the nine Sequence operations, preserving one-to-one field and error-code parity with Facade.
- [ ] Add CLI and MCP black-box tests that begin in one adapter and observe `sequence.record.status` from the other without gaining ownership.
- [ ] Add restart tests that leave an interrupted journal, launch a fresh Host, expose one recovery candidate, and prove no live session resumes.
- [ ] Make Native test capture emit timestamped press/release Sequence events instead of `RawTakeEvent` frame offsets.
- [ ] Add a cross-Host idempotency test that replays the same flush identity and observes one Project revision and one event set.
- [ ] Run `scripts/core.sh test dev fast`; expect PASS.
- [ ] Run `python3 tests/host/cli_test.py tests/host/mcp_stdio_test.py tests/host/mcp_facade_parity_test.py tests/host/native_host_test.py`; expect PASS.
- [ ] On macOS, run `python3 tests/host/native_host_apple_smoke.py`; expect PASS or a separately reported capability skip, never a fabricated pass.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only CLI, MCP, Native Host, and host tests with `feat(hosts): expose Sequence recording parity`.

## Task 7: Add Sequence Timing to Web Runtime Platform and Web Host

**Files:**

- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Create: `packages/web-runtime-platform/web/runtime_types.d.ts`
- Modify: Web Runtime Platform tests under `packages/web-runtime-platform/test/`
- Modify: `apps/web-runtime-host/src/main.mjs`
- Modify: `apps/web-runtime-host/src/diagnostic_project.mjs`
- Modify: `apps/web-runtime-host/test/main_shell.test.mjs`
- Modify: `apps/web-runtime-host/test/diagnostic_project.test.mjs`
- Modify: `apps/web-runtime-host/test/web_host_source_boundary_test.py`
- Modify: `tests/platform/web/` Sequence protocol and Playwright tests

- [ ] Add a failing Web source-boundary test that rejects Project parsing, journal access, quantization math, fingerprint code, or a JavaScript-side fallback sequencer in either Host.
- [ ] Extend Runtime Session with Host-neutral `beginSequence`, `recordSequenceEvent`, `requestPatternSwitch`, `stopSequence`, `querySequenceStatus`, and recovery adapters over Facade.
- [ ] Timestamp pointer/keyboard/MIDI admission at the shared Audio Runtime frame clock and serialize press/release events by `input_sequence`.
- [ ] Forward the Audio Runtime's integer BPM anchors and Bar-boundary notifications; JavaScript must not derive musical time from `performance.now()` or wall clock.
- [ ] Add diagnostic flows for quantize off, Swing, overdub replacement, next-Bar switch, settings-only selective rebase, reload-visible receipt, and owner-loss recovery.
- [ ] Prove two browser windows share one Project status and that the second window receives busy/observer behavior without a second recorder.
- [ ] Run `node --test packages/web-runtime-platform/test/*.test.mjs`; expect PASS.
- [ ] Run `node --test apps/web-runtime-host/test/*.test.mjs` and the Host Python tests selected by `python3 -m unittest discover -s apps/web-runtime-host/test -p '*test.py'`; expect PASS.
- [ ] Run `npm --prefix tests/platform/web test -- --project=chromium`; expect the Stage 9 Chromium rows PASS; run the corresponding WebKit subset and record capability-specific results without translating a skip into physical evidence.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only Web Runtime Platform, diagnostic Host, and tests with `feat(web-runtime): bridge Sequence recording timing`.

## Task 8: Build Creator Sequence Recording UX

**Files:**

- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/components/mode_rail.tsx`
- Modify: `apps/creator-web/src/components/pad_surface.tsx`
- Modify: `apps/creator-web/src/components/capture_panel.tsx`
- Create: `apps/creator-web/src/components/sequence_surface.tsx`
- Create: `apps/creator-web/src/components/sequence_transport.tsx`
- Create: `apps/creator-web/src/state/sequence_state.ts`
- Modify: `apps/creator-web/src/state/capture_state.ts`
- Create: `apps/creator-web/src/runtime/sequence_actions.ts`
- Modify: `apps/creator-web/src/runtime/input_controller.ts`
- Modify: `apps/creator-web/src/runtime/runtime_types.ts`
- Modify: `apps/creator-web/src/capture/capture_controller.ts`
- Modify: `apps/creator-web/src/styles.css`
- Create: `apps/creator-web/test/sequence_state.test.ts`
- Create: `apps/creator-web/test/sequence_actions.test.ts`
- Create: `apps/creator-web/test/sequence_surface.test.tsx`
- Modify: `apps/creator-web/test/capture_controller.test.ts`
- Modify: `apps/creator-web/test/capture_panel.test.tsx`
- Modify: `apps/creator-web/test/capture_state.test.ts`
- Modify: `apps/creator-web/test/input_controller.test.ts`
- Modify: `apps/creator-web/test/workspace_shell.test.tsx`
- Modify: `apps/creator-web/src/report/acceptance_report.ts`
- Modify: `apps/creator-web/test/acceptance_report.test.ts`

- [ ] Add state tests for stopped/recording/switch-pending/flushing/recovery/trim-overlay states and reject impossible ownership transitions.
- [ ] Enable Sequence mode only after Runtime Session reports Project/Pattern readiness; Sample and Perform behavior remain unchanged.
- [ ] Add Pattern selection, Record/Stop, Quantize, Swing, BPM, bars, and recovery controls. Controls issue Facade operations and display returned authority state; they do not predict success.
- [ ] Keep playing/recording the old Pattern while a switch is pending, show the next-Bar target, and change selection only after the boundary acknowledgement.
- [ ] Route pad press/release through the existing unified Input Controller so pointer, keyboard, and MIDI produce the same Sequence event and live trigger admission.
- [ ] Add the at-most-five-second Stage 8B trimming overlay after capture stops. Explicit commit updates Sample; conflict retains the buffer; opening it does not navigate to Sample or trigger SR-D9.
- [ ] Add recovery UI with exactly original Pattern when fingerprint matches, user-selected valid new Pattern, and discard; failed recovery retains the artifact and explains why.
- [ ] Add a privacy-safe acceptance report containing semantic state, receipt/session identities, revisions, and timing counters but no audio samples or local filesystem paths.
- [ ] Run `npm --prefix apps/creator-web test`; expect PASS.
- [ ] Run `npm --prefix apps/creator-web run build`; expect PASS.
- [ ] Run the Creator Stage 9 Playwright journey; expect record → overdub → switch → trim → reload → recover evidence.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only Creator source/tests with `feat(creator): add Sequence recording workflow`.

## Task 9: Integrate Versions, Assembly, Current Portal, and Automated Acceptance

**Files:**

- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `packages/foundation/module.json`
- Modify: `packages/authoring-domain/module.json`
- Modify: `packages/project-io/module.json`
- Modify: `packages/project-cooker/module.json`
- Modify: `packages/audio-runtime/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/native-test-host/module.json`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/creator-web/module.json`
- Modify: current Portal pages for Assembly, modules, Hosts, Project Contract, storage, web runtime, native audio, workflows, capability map, and testing/proof
- Modify: `tests/e2e/headless_core_proof.py`
- Modify: `tests/e2e/requests/record-pattern.json`
- Create: `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`

- [ ] Rebase onto the merged Tasks 1–8 and audit for unresolved Take symbols, v1/v2 writers, `step` event fields, duplicate quantizers, floating musical clocks, or Host-side bundle parsing.
- [ ] Set Product Build to `1.0.30.0` and update Assembly to Project Contract v3 only.
- [ ] Apply these module versions exactly: Foundation `0.3.0`; Authoring Domain `1.0.0`; Project I/O `1.0.0`; Project Cooker `1.0.0`; Audio Runtime `1.0.0`; Application Facade `2.0.0`; Web Runtime Platform `1.0.0`; Core CLI `2.0.0`; Core MCP `2.0.0`; Native Test Host `2.0.0`; Web Runtime Host `2.0.0`; Creator Web `2.0.0`.
- [ ] Update Assembly dependency requirements and `api_version` values coherently; run `python3 scripts/version.py verify --version-file products/lmdj/version.json` and `python3 tests/build/version_test.py`; expect PASS.
- [ ] Update Portal current-state pages and source diagrams so they distinguish Project Truth, journal overlay, immutable Runtime Snapshot, commit receipt, and recovery artifact.
- [ ] Update headless and browser E2E Proof for deterministic v3 Pattern recording, idempotent replay, owner-loss recovery, next-Bar switching, and cross-Host status.
- [ ] Run `bash scripts/verify-core-dependencies.sh`; expect PASS.
- [ ] Run `bash tests/build/test_active_tree.sh`; expect PASS.
- [ ] Run `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/core.sh test dev stress`; expect PASS.
- [ ] Run `scripts/core.sh coverage check`; expect PASS.
- [ ] Run `scripts/core.sh proof`; expect PASS.
- [ ] Run all Web Runtime Host and Creator test/build/Playwright suites; expect automated rows PASS and physical-device rows truthfully recorded.
- [ ] Run `npm --prefix apps/architecture-portal run check:current`; expect PASS before snapshot generation.
- [ ] In `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`, record exact automated commands, results, revisions, artifact digests, and truthful physical-device rows; leave immutable snapshot, merged-main, publication, and promotion evidence pending.
- [ ] Commit the version, Assembly, current Portal, Proof, and acceptance changes with `feat(product): integrate Stage 9 Sequence recording`.

## Task 10: Freeze the Immutable Portal Snapshot and Final Acceptance Evidence

**Files:**

- Create: generated immutable Architecture Portal snapshot and provenance files for Product Build `1.0.30.0`
- Modify: `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`

- [ ] Start from Task 9's committed, clean head. Run `git status --short`; expect no output. Run `python3 scripts/version.py verify --version-file products/lmdj/version.json`; expect `1.0.30.0` verification PASS.
- [ ] Run `scripts/architecture-portal.sh version 1.0.30.0 canary`; inspect the generated identity, provenance, route inventory, and Assembly lock digest.
- [ ] Run `scripts/architecture-portal.sh check`; expect the immutable snapshot and all checks PASS.
- [ ] Run `scripts/core.sh proof`; expect PASS against the exact Task 9 source identity.
- [ ] Update the acceptance ledger with the exact Task 9 revision, snapshot paths/digests, and command results. Do not claim merged-main, Release, deployment, Channel promotion, or unperformed physical evidence.
- [ ] Stage only the generated snapshot/provenance files and the acceptance ledger; inspect `git diff --cached --name-status` and `git diff --cached --check`.
- [ ] Commit with `docs(portal): snapshot Product Build 1.0.30.0`.
- [ ] Inspect `git show --name-status --oneline HEAD` and `git status --short`; expect only the declared snapshot/ledger files in the commit and a clean worktree.

## Version Management

- Product Build: `1.0.27.0 → 1.0.30.0`. Builds `1.0.28.0` and `1.0.29.0` were subsequently allocated, with explicit user approval, to the prerequisite Creator capture Tasks #212 and #213. Those identities are not reused; `1.0.30.0` is reserved for the integrated Stage 9 candidate. This allocation does not publish, deploy, or promote a Channel.
- Contract: add `lmdj.project.v3` Contract SemVer `3.0.0`; v1/v2 remain read-only migration inputs and are removed from active Assembly output.
- Foundation: `0.2.0 → 0.3.0` for `SequenceSessionId`.
- Authoring Domain, Project I/O, Project Cooker, Audio Runtime, and Web Runtime Platform: move to `1.0.0` because their pre-1.0 Take/step or timing surfaces are replaced.
- Application Facade: `1.4.4 → 2.0.0` because Take operations are removed and Sequence operations replace them.
- Core CLI `1.0.16 → 2.0.0`, Core MCP `1.1.13 → 2.0.0`, Native Test Host `1.0.14 → 2.0.0`, Web Runtime Host `1.2.13 → 2.0.0`, and Creator Web `1.3.4 → 2.0.0` because their active recording/protocol surface changes incompatibly.
- Task 9 must re-read current manifests before applying versions. If another merged Build or module release has consumed an exact target, stop and amend this plan through design review; do not silently choose new identities.

## Documentation Impact

Documentation impact: required.

Task 1 updates durable product authority and designed state. Task 9 updates implementation-backed current truth and source diagrams for these Portal routes:

- `/assembly/lmdj/`
- `/contracts/project/`
- `/core/modules/foundation/`
- `/core/modules/authoring-domain/`
- `/core/modules/project-io/`
- `/core/modules/project-cooker/`
- `/core/modules/audio-runtime/`
- `/core/modules/application-facade/`
- `/core/modules/web-runtime-platform/`
- `/hosts/core-cli/`
- `/hosts/core-mcp/`
- `/hosts/native-test-host/`
- `/hosts/web-runtime/`
- `/hosts/creator-web/`
- `/platform/storage/`
- `/platform/web-runtime/`
- `/platform/native-audio/`
- `/product/workflows/`
- `/product/capability-map/`
- `/operations/testing-and-proof/`

The immutable Product Build `1.0.30.0 · canary` snapshot is created only after the version/current-source commit is clean. Snapshot creation is documentation evidence, not Channel promotion.

## Issue Map

Umbrella: [#265 — feature: deliver Stage 9 Sequence recording semantics](https://github.com/endaye/lmdj/issues/265)

| Plan Task | GitHub Issue | Priority | Primary Project area | Hard dependencies |
|---|---|---|---|---|
| 1 | [#266 — durable Stage 9 decision](https://github.com/endaye/lmdj/issues/266) | P1 | Product | #238 |
| 2 | [#267 — Project v3 and tick-native Domain](https://github.com/endaye/lmdj/issues/267) | P1 | Contracts | #266 |
| 3 | [#268 — Sequence journal and flush recovery](https://github.com/endaye/lmdj/issues/268) | P1 | Core | #267 |
| 4 | [#269 — tick-native Audio Runtime](https://github.com/endaye/lmdj/issues/269) | P1 | Core | #267 |
| 5 | [#270 — authoritative Sequence Facade](https://github.com/endaye/lmdj/issues/270) | P1 | Core | #268, #269 |
| 6 | [#271 — CLI/MCP/Native parity](https://github.com/endaye/lmdj/issues/271) | P2 | Native Host | #269, #270 |
| 7 | [#272 — Web Runtime timing bridge](https://github.com/endaye/lmdj/issues/272) | P1 | Web Host | #269, #270 |
| 8 | [#273 — Creator Sequence workflow](https://github.com/endaye/lmdj/issues/273) | P1 | Creator | #270, #272 |
| 9 | [#274 — versions, current Portal, automated acceptance](https://github.com/endaye/lmdj/issues/274) | P1 | Product | #266–#273 |
| 10 | [#275 — immutable Portal snapshot](https://github.com/endaye/lmdj/issues/275) | P2 | Docs/Governance | #274 |

All eleven Issues are in the `LMDJ Work` Project with Status `Todo`, Stage `Stage 9`, the listed Project Priority/Area, and an explicit Target. Labels may carry secondary areas that the single-select Project field cannot represent.

## Final Acceptance Boundary

Stage 9 is implementation-complete only when all ten Task Issues are merged and individually accepted, Project v3 is the sole active writer Contract, the full and stress suites pass on the integrated head, Browser and Native evidence is attached, and Product Build `1.0.30.0` has an immutable Portal snapshot. This does not by itself authorize a tag, GitHub Release, deployment, or `canary`/`beta`/`stable` Channel promotion.
