# LMDJ Stage 10 Perform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a testable Stage 10 candidate in which Creator performs live — playing Pads, launching Patterns at Bar boundaries, switching Banks instantly, applying eight momentary FX as continuous slider gestures with a global HOLD — records that performance as a `lmdj.project.v4` Performance event stream plus a streamed stereo WAV, replays it against the current Project, and resamples a selected range of that recording into a Pad through the existing Bank-quota commit path.

**Authoring gate (refreshed 2026-09-01):** The authority is the approved
[`2026-08-28-lmdj-stage10-perform-design.md`](../specs/2026-08-28-lmdj-stage10-perform-design.md)
(P10-D1–D25), its six decision files, #488, the approved
[`2026-09-01-lmdj-stage10-replay-lineage-contract-design.md`](../specs/2026-09-01-lmdj-stage10-replay-lineage-contract-design.md),
and the approved
[`2026-09-01-lmdj-stage10-host-runtime-session-design.md`](../specs/2026-09-01-lmdj-stage10-host-runtime-session-design.md)
(HRS-D1–D11).
Tasks 1–5 (including Contract prerequisite #516, executed per
[`2026-09-01-lmdj-stage10-replay-lineage-contract-repair.md`](2026-09-01-lmdj-stage10-replay-lineage-contract-repair.md))
and repair Tasks 3A/3B are merged. Task 6 is gated by the host runtime/
session prerequisites #523, #524, #525, #570 and #571, whose exact execution order is in
[`2026-09-01-lmdj-stage10-host-runtime-session-repair.md`](2026-09-01-lmdj-stage10-host-runtime-session-repair.md).
Product Build `1.0.41.0` is now the protected-main baseline and published
canary; the 2026-09-02 refresh audit proved the old Stage 10 target consumed
and locks `1.0.42.0` as the next unoccupied Stage 10 target. Task 10 must still
repeat the required fresh allocation audit immediately before mutation.

**Architecture:** Extend the Stage 9 foundation rather than parallel it.
`lmdj.project.v4` owns both 16 ordered nullable Pattern launch slots and durable
Performance draft objects. Project I/O generalizes the Sequence journal while
adding begin/save/discard/recovery transactions and two-phase Performance
rebase records under the same writer lease. Application Facade owns raw-input
time/order admission, FX quantum coalescing, Pattern boundary acknowledgement,
the exact Performance operation surface, replay resolution against one fixed
current revision, and D1 resample commit. Audio Runtime supplies the delivered
fixed-order, pre-allocated FX chain and authoritative boundary acknowledgements;
the Host-layer WAV tap remains outside the engine. Tasks 1–4 and repair Tasks
3A/3B are delivered; prerequisite #516 and Tasks 5–12 remain separately
reviewable, with one Issue, Conventional Commit and Pull Request per Task.

**Tech Stack:** C++20, CMake 3.24+, JSON Schema, nlohmann/json, SHA-256 canonical JSON vectors, Emscripten `6.0.5`, WasmFS OPFS, SharedArrayBuffer, Wasm AudioWorklet, JavaScript ES modules, React `19.2.8`, TypeScript `7.0.2`, Vite `8.2.1`, Vitest `4.1.10`, Playwright `1.62.1`, Python 3.11, Docusaurus Architecture Portal, GitHub Issues/Projects.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-08-28-lmdj-stage10-perform-design.md` (P10-D1–D25) plus its six decision files. Any conflict returns to design review; an implementation Task must not silently choose a different semantic.
- Execute each Task on a short-lived `feat/<task>` or `fix/<task>` branch in an isolated worktree. Never implement on `main`.
- Each implementation Task through Task 11 maps one-to-one to one GitHub Issue,
  one reviewable Conventional Commit and one Pull Request. **Do not aggregate
  Tasks into a single squash PR.** Task 12 is a release-operation boundary: its
  release-intent document is one PR, while later audited tag/Draft/publication
  transitions do not create repository commits.
- Functional Tasks keep active manifests and Product Build at their current values until Task 10. Task 10 is the version/current-truth integration boundary; Task 11 is the separate clean-commit immutable Portal snapshot boundary.
- Project Truth is authoritative. Runtime Snapshot, the FX chain state and the WAV tap are derived or transient and are never persisted as Project Truth.
- Hosts use only Application Facade. They must not parse a Project bundle, read a journal directly, or reproduce gesture coalescing, replay resolution, fingerprint or flush rules.
- Exactly one recording session may be active per Project bundle. Perform and Sequence recording are mutually exclusive; the second `begin` is `INVALID_ARGUMENT`. Admission and `expected_revision` validation occur under the same existing Project writer lease.
- Project v4 contains exactly 16 ordered nullable `pattern_slots`; an occupied PatternId must exist and be unique. No Host or Runtime structure may become a second slot truth.
- Every event timestamp and input sequence is allocated by Core at Facade admission. No Host supplies `tick`, `runtime_frame` or `input_sequence`; Host-side semantic FX coalescing is forbidden.
- Only an Audio Runtime boundary acknowledgement may create a canonical `pattern_launch`; a request that fails, is cancelled, is superseded before claim, or loses its owner before the boundary creates no event.
- A visible Project receipt with a missing Performance `rebase_complete` forces `recovery_required` and rejects new event/flush admission until exact-command reconciliation succeeds.
- The render path stays zero-allocation, lock-free and `noexcept`. All FX state and buffers are pre-allocated off the audio thread. No Task may introduce allocation, locking or exceptions into `render`.
- Bank switching is view state: it never enters admission, never occupies a revision, and never emits an event.
- This plan authorizes local commits only. Push, Pull Request creation, squash merge, Product tag, Release publication, deployment and Channel promotion require separate authorization.
- Before every Task commit: run the Task-specific tests and `scripts/architecture-portal.sh check`; stage only declared files; run `git diff --cached --name-status` and `git diff --cached --check`; inspect the staged diff; commit; inspect `git show --name-status --oneline HEAD`; confirm no Task residue remains.

## Locked Constants and Types

All implementations use these values verbatim.

```text
FX_COUNT                = 8
FX_CHAIN_ORDER          = [filter, delay, reverb, stutter, gate, reverse, crush, cutter]
FX_VALUE_MIN            = 0
FX_VALUE_MAX            = 1000
FX_VALUE_CENTER         = 500          // bidirectional effects (filter) only
FX_COALESCE_FRAMES      = 128          // one move event per FX per audio quantum
PERFORMANCE_NAME_MAX    = 64           // UTF-8 code points
PATTERN_SLOT_COUNT      = 16
PATTERN_SLOT_MIN        = 0
PATTERN_SLOT_MAX        = 15
WAV_SAMPLE_RATE         = 48000
WAV_CHANNELS            = 2
WAV_SAMPLE_FORMAT       = pcm_s16le
PERFORM_BATCH_FRAMES    = 4800         // inherited Stage 8B batch contract
PERFORM_MAX_FRAMES      = 86400000     // 30 minutes at 48 kHz
PERFORM_QUEUE_BATCHES   = 32           // 153600 frames / 3.2 seconds
```

The exact Host manifest keys are `resource_limits.perform_recording_frames =
86400000` and `resource_limits.perform_recording_queue_batches = 32`. The queue
therefore bounds Float32 stereo backlog to 1,228,800 bytes. The maximum PCM16
stereo payload is 345,600,000 bytes and the canonical 44-byte RIFF/WAV file is
345,600,044 bytes. These are Host resource parameters, not Project Contract or
Core semantics.

Inherited unchanged from Stage 9 (do not redefine): `PPQ = 960`, `SIXTEENTH_TICKS = 240`, `BAR_TICKS_4_4 = 3840`, `RUNTIME_SAMPLE_RATE = 48000`, and the integer rational BPM anchor rules (SR-D25).

Bidirectional encoding: `filter` uses `value < 500` for low-pass depth and `value > 500` for high-pass depth, with `500` meaning bypass. Tempo-locked effects (`stutter`, `cutter`) map their value range onto their documented division ladder by integer division only; no floating-point interpolation enters the mapping.

## Locked Performance Event Vocabulary

```text
pad_hit        { slot: 0-63, onset_tick: u64, duration_tick: u64, velocity: 1-127 }
pattern_launch { pattern_slot: 0-15, effective_tick: u64 }
fx_engage      { fx: FX_CHAIN_ORDER index, value: 0-1000, tick: u64 }
fx_move        { fx: FX_CHAIN_ORDER index, value: 0-1000, tick: u64 }
fx_release     { fx: FX_CHAIN_ORDER index, tick: u64 }
hold_on        { tick: u64 }
hold_off       { tick: u64 }
```

Invariants, all with cross-language vectors:

- Events are canonically ordered by `(tick, kind_ordinal, fx_or_slot)`; `kind_ordinal` follows the order listed above. Recovery-generated equal-tick releases use FX chain order; Pad owner-loss closure uses `(slot, gesture_id)` before raw IDs are removed.
- Core emits `fx_move` only when the value differs from the effective or pending value for that FX, and at most once per FX per `FX_COALESCE_FRAMES` window. Last admission wins inside a window; release drains that value first.
- `fx_release` without a matching open `fx_engage` is invalid; `fx_engage` for an already-engaged FX is invalid.
- `hold_on` while HOLD is on, and `hold_off` while HOLD is off, are invalid.
- `pattern_launch.effective_tick` is the acknowledged boundary tick, never the input tick.
- Replay end/abort resets every transient FX and HOLD state to neutral even when an imported or recovered stream ends open.
- No event carries an Asset reference, a `pattern_id`, or a Bank identity.

## Locked Project v4 Migration

v3 → v4 is a deterministic total migration:

- `contract` becomes `lmdj.project.v4`.
- A `pattern_slots` array with exactly 16 `null` entries is added.
- A `performances` array is added, empty for every migrated v3 Project.
- Every migrated Asset gains exactly `lineage: null`; `patterns`, `banks`,
  Asset identity/artifact content, `bpm` and `sequence_settings` otherwise
  migrate byte-identically.
- v1 and v2 remain read-only migration inputs through their existing v3 path; the migration chain is v1→v2→v3→v4 with no new direct edges.
- A `performances` or `pattern_slots` key present in a v3-declared document is invalid input, not an implicit upgrade.

## Locked Facade Surface

Every JSON request includes `operation` plus the exact fields below. `uuid`
means a lowercase canonical UUID. Extra fields are invalid.

| Operation | Kind | Exact fields after `operation` |
|---|---|---|
| `pattern.slot.assign` | command | `project_path, command_id, expected_revision, pattern_slot, pattern_id` |
| `pattern.slot.clear` | command | `project_path, command_id, expected_revision, pattern_slot` |
| `pattern.slot.move` | command | `project_path, command_id, expected_revision, from_slot, to_slot` |
| `performance.list` | query | `project_path` |
| `performance.inspect` | query | `project_path, performance_id` |
| `performance.record.begin` | command | `project_path, command_id, expected_revision, session_id, performance_id` |
| `performance.record.event` | command | `project_path, session_id, event_id, event` |
| `performance.record.launch-request` | command | `project_path, session_id, request_id, pattern_slot` |
| `performance.record.flush` | command | `project_path, session_id, command_id` |
| `performance.record.stop` | command | `project_path, session_id, request_id` |
| `performance.record.status` | query | `project_path` |
| `performance.save` | command | `project_path, command_id, expected_revision, performance_id, name, recording_artifact` |
| `performance.discard` | command | `project_path, command_id, expected_revision, performance_id` |
| `performance.recovery.list` | query | `project_path` |
| `performance.recovery.apply` | command | `project_path, command_id, expected_revision, session_id` |
| `performance.recovery.discard` | command | `project_path, session_id, request_id` |
| `performance.rename` | command | `project_path, command_id, expected_revision, performance_id, name` |
| `performance.delete` | command | `project_path, command_id, expected_revision, performance_id` |
| `performance.recording.bind` | command | `project_path, command_id, expected_revision, performance_id, recording_artifact` |
| `performance.replay.begin` | command | `project_path, replay_id, performance_id` |
| `performance.replay.stop` | command | `project_path, replay_id, request_id` |
| `performance.replay.status` | query | `project_path, replay_id` |
| `performance.resample.commit` | command | `project_path, command_id, expected_revision, performance_id, source_start_frame, source_end_frame, target_slot` |

`performance.record.event.event` is one strict tagged union:

```text
{ kind: "pad_press",   gesture_id: uuid, slot: 0-63, velocity: 1-127 }
{ kind: "pad_release", gesture_id: uuid, slot: 0-63 }
{ kind: "fx_engage",   gesture_id: uuid, fx: FX_CHAIN_ORDER value, value: 0-1000 }
{ kind: "fx_move",     gesture_id: uuid, fx: FX_CHAIN_ORDER value, value: 0-1000 }
{ kind: "fx_release",  gesture_id: uuid, fx: FX_CHAIN_ORDER value }
{ kind: "hold_on" }
{ kind: "hold_off" }
```

`recording_artifact` is either `null` on save or exactly
`{sha256, media_type: "audio/wav", byte_length}`. The Facade verifies the
managed immutable bytes before mutation and never accepts a path or byte body.

Success results are exact projections inside the existing success envelope:

```text
Performance management mutation:
                   { performance_id, committed_revision, replayed }
Pattern assign/clear:
                   { pattern_slot, pattern_id|null, committed_revision, replayed }
Pattern move:      { from_slot, to_slot, pattern_id, committed_revision, replayed }
Resample commit:   existing SampleMutationResult + source performance_id
record.event:      { event_id, accepted_tick, input_sequence, coalesced, replayed }
launch-request:    { request_id, state: "pending", target_tick }
record.status:     { state, session_id|null, performance_id|null,
                     journal_revision, next_flush_seq, pending_event_count,
                     open_pad_gestures, open_fx_gestures, hold,
                     pending_launch, last_launch_ack }
recovery.list:     { candidates: [{ session_id, performance_id, reason,
                                    durable_event_count, pending_event_count,
                                    fingerprint }] }
replay status:     { replay_id, state, resolved_revision, event_cursor,
                     event_count }
record.stop:       { request_id, session_id, performance_id, state: "stopped",
                     pending_event_count, replayed }
recovery.discard:  { request_id, session_id, performance_id, state: "stopped",
                     pending_event_count, replayed }
replay.stop:       replay status fields + { request_id, replayed }
performance.list:  { performances: [{ performance_id, name, created_bpm,
                                      recording_artifact, event_count }] }
performance.inspect:
                   { performance: { id, name, created_bpm,
                                    recording_artifact, events } }
```

`record.status.state` is exactly `idle|active|stopped|recovery_required`.
`open_pad_gestures` and `open_fx_gestures` are counts; `pending_launch` is null
or `{request_id, pattern_slot, target_tick, claimed}`; `last_launch_ack` is null
or `{request_id, pattern_slot, effective_tick}`. Replay state is exactly
`playing|stopped|complete`.

`record.begin` is an externally authored Project mutation and uses the Project
receipt. `record.flush` is session-owned: its `expected_revision` is read only
from Journal, never accepted from a Host. `stop`, `recovery.discard` and Replay
actions do not mutate Project Truth. The `event_id`, `request_id`, `gesture_id`
and `replay_id` spaces each reject same-ID/different-payload collisions.

## Dependency Order

```text
Delivered: Task 1 #427 ─┬─ Task 2 #428
                         └─ Task 3 #429
Design repair #488 ─────┬─ Task 3A #498 durable Pattern slots
                         └─ Task 3B #499 draft lifecycle + durable rebase

Tasks 2, 3, 3A, 3B ── Task 4 #430 authoritative recording/management Facade
                         ├─ prerequisite #516 Lineage + recording revision
                         │    └─ Task 5 #431 replay resolution + resample commit
                         │         └─ prerequisite #523 Core runtime bridge
                         │              ├─ prerequisite #524 CLI session mode
                         │              ├─ prerequisite #525 Native adapter
                         │              └─ prerequisite #570 owner-loss closure
                         │                   (#525 + #570) ── #571 status/service split
                         │
                         ├─ (#524 + #525 + #570 + #571) ── Task 6 #432 CLI/MCP/Native parity
                         └─ (#525 + #571) ── Task 7 #433 Web Runtime raw-input + launch bridge
                              └─ Task 8 #434 Host WAV tap/OPFS writer
Tasks 5, 7, 8 ───────────── Task 9 #435 Creator Perform surface
Tasks 1-9 + 3A/3B ─── Task 10 #436 versions/Assembly/current Portal/automation
                         └─ Task 11 #438 immutable snapshot/final evidence
                                └─ Task 12 #468 release intent + canary Release
```

Tasks 1–5 (with prerequisite #516) and repair Tasks 3A/3B are complete.
Task 6 starts only after host runtime/session prerequisites #523, #524, #525,
#570 and #571 merge: its shared Host journey consumes replay/resample and needs the
Core runtime bridge, the CLI session mode, the Native adapter and crash-durable
owner-loss transient closure plus the read-only status/service split. #524,
#525 and #570 may run in parallel worktrees after #523; #571 follows both.
Task 7 starts after #525/#571 so Web
Runtime reuses the same Core `EnginePerformanceAdapter` instead of owning a
second frame→tick, launch-ack or replay progression implementation. Task 8
starts after Task 7; Task 9 waits for Tasks 5, 7 and 8. Integration,
snapshotting and release stay serial through Tasks 10–12.

## Design Traceability

| Approved decision | Primary implementation Tasks | Acceptance witness |
|---|---|---|
| P10-D1, P10-D17: Perform mode and surface layout | 9 | Mode Rail enablement and Creator component tests |
| P10-D2, P10-D3: Bar-boundary Pattern Launch over the same 16 slots | 3, 4, 7, 9 | boundary integration test; recorded tick equals acknowledged tick |
| P10-D4: Bank switching as view state | 7, 9 | no revision, no event, no preparation latency |
| P10-D5, P10-D15: continuous gesture stream and integer scale | 3, 4, 7 | gesture vectors; dedup and coalescing boundary tests |
| P10-D6: global HOLD | 3, 4, 9 | latch/release state-machine tests |
| P10-D7: fixed chain order, pre-allocation, determinism | 3, 10 | zero-allocation guard; live-vs-replay sample equality |
| P10-D8: v4 Performance object | 1, #516, 10 | Contract fixtures, recording revision and migration vectors |
| P10-D9: generalized session and mutual exclusion | 2, 4, 6 | second-begin `INVALID_ARGUMENT`; fault matrix |
| P10-D10: replay against the current Project | 5, 9 | changed-sample, moved-slot and empty-slot replay tests |
| P10-D11: live-capture resample over the D1 commit path | #516, 5, 8 | durable Lineage assertions; `BANK_QUOTA_EXHAUSTED` non-destructive test |
| P10-D12: Host-layer streamed WAV with sealing | 8 | long-record OPFS test; sealed-prefix validity; render glitch-free stress |
| P10-D13: one Facade surface across Hosts | 4, 6, 7 | CLI/MCP black-box journey parity |
| P10-D14: FX roster with Cutter | 3 | per-effect audible-change and division-ladder tests |
| P10-D16: Perform rebase whitelist | 3B, 4 | durable rebase fault matrix; armed-capture rejection test |
| P10-D18: durable 16 Pattern slots | 3A, 4, 5 | schema/migration/mutation vectors; moved/empty-slot replay |
| P10-D19: durable draft lifecycle | 3B, 4 | begin/stop/save/discard and recovery crash matrix |
| P10-D20, P10-D25: exact Facade surface | 4, 5, 6, 7 | exact-key schemas and cross-Host black-box parity |
| P10-D21: Core raw-input admission | 4, 7 | forbidden Host clock fields; event/gesture idempotency |
| P10-D22: actual launch acknowledgement | 4, 7 | unclaimed replace, claimed defer, ghost-event rejection |
| P10-D23: Core FX/owner-loss rules | 4, 7 | quantum last-write-wins and deterministic closure vectors |
| P10-D24: two-phase durable rebase | 3B, 4 | every prepare/receipt/complete crash point and exact retry |
| HRS-D1–D11: Core runtime authorities, session continuity, hard-owner-loss closure and read-only status (2026-09-01/02 repair) | #523, #524, #525, #570, #571, 6, 7 | bridge/adapter suites; cross-process flush replay; durable transient closure; two-phase launch service; CLI session journey; request-free Web progression |

## Task 1: Add Project v4 and the Performance Authoring Domain — delivered

**Delivered evidence:** Issue #427 closed; PR #445 merged as
`cd1f17954db63091c68ccb41efd69b32243af6e0`. Task 3A is an explicit
pre-release correction, not a claim that this original Task delivered Pattern
slot truth. Prerequisite #516 is the corresponding pre-release correction for
Asset Lineage and Performance recording revision; it supersedes this Task's
historical “all other fields byte-identical” migration detail only as stated in
the current Locked Project v4 Migration section.

**Files:**

- Create: `contracts/project/lmdj.project.v4.schema.json`
- Create: `tests/fixtures/contracts/project-v4-valid.json`
- Create: `tests/fixtures/contracts/project-v4-invalid-event.json`
- Create: `tests/fixtures/contracts/project-v3-to-v4-migration.json`
- Modify: `tests/conformance/schema_contract_test.py`
- Modify: `packages/authoring-domain/include/lmdj/domain/project.hpp`
- Modify: `packages/authoring-domain/src/project.cpp`
- Create: `packages/authoring-domain/src/migration.cpp`
- Modify: `packages/authoring-domain/CMakeLists.txt`
- Test: `tests/core/domain/performance_test.cpp`
- Test: `tests/core/domain/migration_v4_test.cpp`

- [x] RED: add `performance_test.cpp` asserting the locked event vocabulary, canonical ordering by `(tick, kind_ordinal, fx_or_slot)`, and every invalid-event rule (unmatched release, double engage, double hold, Asset/pattern_id/Bank reference); expect failure before implementation.
- [x] RED: add `migration_v4_test.cpp` asserting v3→v4 adds an empty `performances`, migrates all other fields byte-identically, and rejects a v3-declared document that already carries `performances`; expect failure.
- [x] Author `lmdj.project.v4.schema.json` with the `performances` collection, per-event `$defs`, `PERFORMANCE_NAME_MAX`, `PATTERN_SLOT_MIN/MAX` and the `FX_VALUE_MIN/MAX` bounds.
- [x] Implement the domain `Performance` type, canonical ordering, validation, and the v3→v4 migration edge; keep v1→v2→v3 untouched.
- [x] GREEN: run `scripts/core.sh test dev fast`; expect the two new suites to pass with no regression.
- [x] Run `python3 tests/conformance/schema_contract_test.py`; expect PASS including the new fixtures.
- [x] Run `bash tests/build/test_active_tree.sh` and `scripts/architecture-portal.sh check`; expect PASS.
- [x] Commit only the listed files with `feat(contracts): add Project v4 with Performance events`.

## Task 2: Generalize the Session Journal for Performance Recording — delivered

**Delivered evidence:** Issue #428 closed; PR #484 merged as
`a06f8bf3e0e0ff54762bee900d50f715b8973bf8`. Task 3B completes lifecycle and
rebase semantics that this foundation intentionally did not expose.

**Files:**

- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Test: `tests/core/project_io/performance_journal_test.cpp`
- Test: `tests/core/project_io/session_mutual_exclusion_test.cpp`

- [x] RED: add `performance_journal_test.cpp` covering begin/append/complete/seal/recover for a Performance session, durable flush intent before Project mutation, idempotent receipt replay for a repeated `command_id`, and journal cleanup only after all flushes are complete.
- [x] RED: add `session_mutual_exclusion_test.cpp` asserting a Perform begin while a Sequence session is active returns `INVALID_ARGUMENT`, and the reverse, with admission performed inside the writer lease.
- [x] Introduce a `SessionKind` discriminator and parameterize the journal record types over it without changing any existing Sequence-session on-disk semantics; a v3-era Sequence journal must still load and reconcile unchanged.
- [x] Extend fingerprint gating to the Performance recovery path: recovery may append only when the target Performance's canonical fingerprint still matches; deletion or incompatible change fails closed and retains the recovery file.
- [x] GREEN: run `scripts/core.sh test dev fast`; expect PASS.
- [x] Run `scripts/core.sh test dev stress`; expect the existing journal stress tier to pass unchanged.
- [x] Run `scripts/architecture-portal.sh check`; expect PASS.
- [x] Commit only the listed files with `feat(project-io): generalize the recording journal over session kinds`.

## Task 3: Add the Master FX Chain to Audio Runtime — delivered

**Delivered evidence:** Issue #429 closed; PR #485 exact reviewed head
`f2dee54f3d804f9effd4c49c7988bf26bb982aa1` merged as
`8cea870af3bf1ef1cf9b870e0eeb89115e43353e`; exact-head and exact-main Core
CI each completed 19 successful jobs with zero failures.

**Files:**

- Create: `packages/audio-runtime/include/lmdj/audio/master_fx.hpp`
- Create: `packages/audio-runtime/src/master_fx.cpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Test: `tests/core/audio/master_fx_test.cpp`
- Test: `tests/core/audio/master_fx_determinism_test.cpp`
- Test: `tests/core/audio/master_fx_allocation_guard_test.cpp`
- Test: `tests/core/audio/master_fx_stress_test.cpp`

- [x] RED: add `master_fx_test.cpp` asserting each of the eight effects in `FX_CHAIN_ORDER` changes the rendered signal measurably when engaged and restores bit-identical passthrough on release; assert the filter's `500` bypass and the tempo-locked division ladders of `stutter` and `cutter` map by integer division only.
- [x] RED: add `master_fx_determinism_test.cpp` asserting identical Snapshot plus identical gesture event stream yields sample-identical output across two runs and across engage/move/release orderings that coalesce to the same values.
- [x] RED: add `master_fx_allocation_guard_test.cpp` extending the existing render-path guard so a fully engaged eight-effect chain performs no allocation, no lock and no throw inside `render`.
- [x] RED: add `master_fx_stress_test.cpp` (label `stress`, and exclude it from the `coverage` preset in the same commit) driving all eight effects at maximum gesture rate for a sustained run with zero underruns.
- [x] Implement `MasterFxChain` as a POD-state, pre-allocated, fixed-order chain applied after voice mixing; all buffers sized at Snapshot preparation and owned outside the audio thread. Apply gestures through the existing lock-free control-to-render hand-off; add no new locking discipline.
- [x] Implement each effect as the deterministic LMDJ reference DSP defined by its golden parameter mapping and behavioral tests. Koala manual behavior is the product-direction reference; no test, documentation or acceptance claim may assert proprietary Koala coefficient, algorithm or sample identity.
- [x] Wire HOLD as a single chain-level latch: on release with HOLD engaged, freeze that effect's current value; on `hold_off`, release every frozen effect.
- [x] GREEN: run `scripts/core.sh test dev full` then `scripts/core.sh test dev stress`; expect PASS.
- [x] Run `scripts/architecture-portal.sh check`; expect PASS.
- [x] Commit only the listed files with `feat(audio): add the fixed-order master FX chain`.

## Task 3A: Add Durable Pattern Launch Slots to Project v4

**Issue:** #498

**Files:**

- Modify: `contracts/project/lmdj.project.v4.schema.json`
- Modify: `tests/fixtures/contracts/project-v4-valid.json`
- Modify: `tests/fixtures/contracts/project-v3-to-v4-migration.json`
- Create: `tests/fixtures/contracts/project-v4-invalid-pattern-slots.json`
- Modify: `tests/conformance/schema_contract_test.py`
- Modify: `packages/authoring-domain/include/lmdj/domain/project.hpp`
- Modify: `packages/authoring-domain/include/lmdj/domain/commands.hpp`
- Modify: `packages/authoring-domain/src/project.cpp`
- Modify: `packages/authoring-domain/src/migration.cpp`
- Modify: `packages/authoring-domain/src/command_handler.cpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Test: `tests/core/domain/migration_v4_test.cpp`
- Test: `tests/core/domain/command_handler_test.cpp`
- Test: `tests/core/project_io/project_store_test.cpp`

**Interfaces:**

- Produces: `ProjectState::pattern_slots` as
  `std::array<std::optional<foundation::PatternId>, 16>`.
- Produces: domain Commands `AssignPatternSlot {meta, slot, pattern_id}`,
  `ClearPatternSlot {meta, slot}` and
  `MovePatternSlot {meta, from_slot, to_slot}` in `domain::Command`.
- Consumed by: Task 4 JSON operations `pattern.slot.assign|clear|move`, Task 5
  replay resolution and Task 9 Pattern strip.

- [ ] **RED — Contract and migration:** update the valid and migration fixtures,
  add the invalid fixture, and assert that v4 requires exactly 16 nullable UUIDs
  while v3 rejects pre-existing `pattern_slots`. Run
  `python3 tests/conformance/schema_contract_test.py`; expect failure naming the
  missing `pattern_slots` property.
- [ ] **RED — domain integrity:** extend `migration_v4_test.cpp` and
  `command_handler_test.cpp` for all-empty migration, occupied round-trip,
  wrong length, missing Pattern, duplicate Pattern, assign-to-occupied,
  clear-empty, move-from-empty, move-to-occupied, same-slot move, receipt replay
  and same-command-ID/different-payload collision. Run
  `scripts/core.sh test dev fast`; expect the new assertions to fail.
- [ ] Add `pattern_slots` to `ProjectState`, JSON encode/decode and validation.
  Validation must reject every malformed state before returning Project Truth;
  it must not repair, drop or reorder slots.
- [ ] Add the three Commands to the domain variant and Project transaction
  codec. Successful assign/clear/move advances exactly one revision; failed
  preconditions leave state and receipt map unchanged. Exact receipt replay
  returns `replayed: true` and the original committed revision.
- [ ] **GREEN:** run `scripts/core.sh test dev fast`,
  `python3 tests/conformance/schema_contract_test.py` and
  `bash tests/build/test_active_tree.sh`; expect all pass.
- [ ] Run `scripts/core.sh coverage check`; expect the existing floor to pass
  without lowering it. Run `scripts/architecture-portal.sh check`; expect
  59/59 Portal tests and a valid build.
- [ ] Commit only the listed files with
  `feat(contracts): add durable Pattern launch slots (fixes #498)`.

## Task 3B: Complete the Performance Draft Lifecycle and Durable Rebase

**Issue:** #499

**Files:**

- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `packages/project-io/CMakeLists.txt`
- Modify: `CMakeLists.txt`
- Create: `tests/core/project_io/performance_lifecycle_test.cpp`
- Create: `tests/core/project_io/performance_rebase_test.cpp`
- Modify: `tests/core/project_io/performance_journal_test.cpp`
- Modify: `tests/core/project_io/session_mutual_exclusion_test.cpp`

**Interfaces:**

- Produces Project Store entry points:
  `begin_performance_draft(bundle, meta, session_id, performance_id)`,
  `stop_performance_session(bundle, session_id, request_id)`,
  `save_performance_draft(bundle, meta, performance_id, name, artifact)`,
  `discard_performance_draft(bundle, meta, performance_id)`,
  `apply_performance_recovery(bundle, meta, session_id)`,
  `discard_performance_recovery(bundle, session_id, request_id)` and
  `bind_performance_recording(bundle, meta, performance_id, artifact)`.
- Produces Journal records
  `PerformanceRebasePrepare {command_id, command_fingerprint, from_revision,
  to_revision}` and
  `PerformanceRebaseComplete {command_id, committed_revision, bpm_anchor}`;
  Quantize/Swing completion carries no event rewrite.
- Consumed by: Task 4 Facade without direct Journal parsing.

- [ ] **RED — lifecycle:** add tests for atomic begin at revision N→N+1,
  stable begin retry/collision, stopped tail without revision, save consuming
  tail/name/optional ArtifactRef in one revision, discard deleting draft and
  Journal, recovery apply/discard each producing a stopped draft Journal, and
  rename/delete/bind gates.
  Run the two new test executables directly; expect missing API failures.
- [ ] **RED — fault matrix:** inject every durable-write failure before and
  after begin receipt, stop seal, save manifest, recovery receipt and cleanup.
  After a new `ProjectStore` instance opens the bundle, assert either complete
  committed truth or a retained actionable candidate; no orphan draft,
  duplicate events or deleted unbound recovery file is permitted.
- [ ] **RED — two-phase rebase:** cover BPM, Quantize and Swing across
  `prepare → Project receipt → complete`; assert visible receipt plus missing
  completion yields `recovery_required`, blocks event/flush, and exact retry
  appends only completion. Assert no receipt permits the immutable command to
  retry, collision fails, Sample-class rejection keeps active, and unknown
  Authoring Command fails closed.
- [ ] Implement lifecycle transactions under one existing Project writer
  lease. Begin creates exactly `Untitled Performance`, current BPM, null
  artifact and no events. Stop never invokes Project mutation. Save is the
  only normal path that consumes a stopped tail and removes its Journal.
- [ ] Implement verified ArtifactRef binding as a null-only mutation. Resolve
  managed storage bytes through Project I/O, verify sha256 and byte length,
  require `audio/wav`, make the same ref idempotent and reject a conflicting
  ref without state change.
- [ ] Implement the prepare/complete record and reconciliation state machine.
  All `recovery_required` errors must state why admission is blocked and the
  exact retry/reopen remedy.
- [ ] Wire both new tests into `packages/project-io/CMakeLists.txt`, the root
  test inventory and coverage target list. Do not add them to `stress`; extend
  the existing journal stress suite for concurrent writer-lease coverage.
- [ ] **GREEN:** run `scripts/core.sh test dev full`,
  `scripts/core.sh test dev stress`, `scripts/core.sh coverage check` and
  `scripts/architecture-portal.sh check`; expect all pass without lowering a
  coverage floor.
- [ ] Commit only the listed files with
  `feat(project-io): complete Performance lifecycle and rebase (fixes #499)`.

## Task 4: Add the Authoritative Performance Application Facade

**Issue:** #430. Hard dependencies: #428, #429, #498 and #499.

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `CMakeLists.txt`
- Test: `tests/core/facade/performance_session_test.cpp`
- Test: `tests/core/facade/performance_gesture_admission_test.cpp`
- Test: `tests/core/facade/performance_rebase_matrix_test.cpp`
- Create: `tests/core/facade/performance_operation_contract_test.cpp`

**Interfaces:**

- Consumes: Task 3 `MasterFxChain`, Task 3A Pattern-slot Commands and Task 3B
  Project Store lifecycle/rebase entry points.
- Produces: every Locked Facade operation except
  `performance.replay.begin|stop|status` and `performance.resample.commit`,
  which Task 5 adds after replay projection exists.
- Produces injected Core authorities `PerformanceClock::read_tick()`,
  `PerformanceInputSequencer::next()` and
  `PatternLaunchAcknowledger`; no public Host API accepts their values.

- [ ] **RED — operation contract:** register and exact-key test
  `pattern.slot.assign`, `pattern.slot.clear`, `pattern.slot.move`,
  `performance.list`, `performance.inspect`, `performance.record.begin`,
  `performance.record.event`, `performance.record.launch-request`,
  `performance.record.flush`, `performance.record.stop`,
  `performance.record.status`, `performance.save`, `performance.discard`,
  `performance.recovery.list`, `performance.recovery.apply`,
  `performance.recovery.discard`, `performance.rename`, `performance.delete`
  and `performance.recording.bind`. For every operation assert kind, missing
  field, extra field, malformed UUID, range edge and exact success result.
- [ ] **RED — lifecycle journey:** begin→event→flush→stop→save→inspect and the
  parallel discard path. Assert begin revision N→N+1, flush revision from
  Journal only, stop no revision, save tail/name/artifact one revision, receipt
  replay, collision, reopen truth and active/recovery gates for rename/delete/
  bind.
- [ ] **RED — raw admission:** reject any event containing tick,
  `runtime_frame` or `input_sequence`. Cover event ID retry/collision, every
  strict raw union member, gesture mismatch without session seal, Core-assigned
  tick/order, open Pad owner-loss closure and canonical Project output with no
  raw IDs.
- [ ] **RED — FX state machine:** assert per-FX/per-128-frame last-write-wins,
  duplicate-to-effective and duplicate-to-pending removal, independent FX
  windows, release draining pending move, HOLD final value, deterministic
  owner-loss release/hold_off order and replay/reset-neutral hand-off.
- [ ] **RED — launch ack:** assert Host request carries only request ID and slot,
  Core reserves next Bar, unclaimed latest-wins, claimed later request defers,
  empty slot ack records without changing playback, and failure/cancel/
  owner-loss before ack creates no Journal event.
- [ ] **RED — rebase matrix:** cover BPM/Quantize/Swing success and every Task
  3B recovery-required state through public Facade errors/status; Quantize/
  Swing change no Performance timing; Sample-class commands fail while active;
  unknown Authoring Commands fail closed.
- [ ] Implement only by composing Task 3A/3B and the Audio Runtime control/
  acknowledgement boundaries. Facade must not parse Project JSON, synthesize a
  Host time, or write Journal files directly.
- [ ] Wire all four suites into application-facade CMake, the root test
  inventory and coverage target list.
- [ ] GREEN: run `scripts/core.sh test dev full`; expect PASS and no facade coverage-gate regression.
- [ ] Run `scripts/core.sh coverage check`; expect PASS at the current floor (raise real coverage; never lower the floor).
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with
  `feat(facade): add the Performance recording surface (fixes #430)`.

## Contract Prerequisite: Persist Replay/Resample Truth

**Issue:** #516. Hard dependencies: #430, #498 and #499.

This independently reviewable correction adds Project v4 `Asset.lineage`,
`Performance.recording_revision`, and Lineage-aware D1 transaction/recovery
identity. It does not implement replay or the resample operation. Execute Task
1 of
[`2026-09-01-lmdj-stage10-replay-lineage-contract-repair.md`](2026-09-01-lmdj-stage10-replay-lineage-contract-repair.md)
as its complete file list, RED/GREEN sequence, verification and commit
authority.

## Task 5: Add Replay Resolution and the Resample Selection Commit

**Issue:** #431. Hard dependencies: #430, #498 and merged #516.

Execute Task 2 of
[`2026-09-01-lmdj-stage10-replay-lineage-contract-repair.md`](2026-09-01-lmdj-stage10-replay-lineage-contract-repair.md)
as the complete authority for files, interfaces, lifecycle/reset-pending
semantics, tests, verification and commit. It preserves the Locked Facade
Surface while adding immutable Project Cooker projection, required injected
controller, deterministic command-derived Asset identity, and D1-only
resample commit.

## Host Runtime/Session Prerequisite: Make the Performance Surface Drivable

**Issues:** #523, #524, #525, #570, #571. Hard dependencies: #430, #431 and the merged
docs PR carrying the repair design and plan.

The Task 6 start-gate audit found the locked surface undrivable by any
production Host: the three Performance authority ports have no production
implementation (all four Host construction sites inject `nullptr` plus the
unavailable replay controller), the CLI cannot hold a session across
requests, the Facade's in-memory owner guard blocks the fully idempotent
cross-process flush replay, and `performance.recovery.list` seals a live
journal from a query. The independently reviewable corrections are
adjudicated as HRS-D1–D11 in
[`2026-09-01-lmdj-stage10-host-runtime-session-design.md`](../specs/2026-09-01-lmdj-stage10-host-runtime-session-design.md).
Execute Tasks 1–5 of
[`2026-09-01-lmdj-stage10-host-runtime-session-repair.md`](2026-09-01-lmdj-stage10-host-runtime-session-repair.md)
as their complete file lists, RED/GREEN sequences, verification and commit
authority: Task 1 (#523) Core Performance runtime bridge, cross-process
flush identity and read-only recovery queries; Task 2 (#524) CLI persistent
NDJSON session mode and CLI-only cross-process journeys; Task 3 (#525)
Native Host `RealtimeEngine` adapter and construction-order repair; Task 4
(#570) crash-durable transient checkpoints and deterministic hard-owner-loss
closure; Task 5 (#571) read-only status projection plus explicit two-phase
launch-outcome service mutation.

## Task 6: Migrate CLI, MCP and Native Host to Performance Operations

**Issue:** #432. Hard dependencies: #430, #431 and merged #523, #524, #525,
#570, #571.
The CLI journey legs run in the #524 session mode; every Host injects only
the #523 bridge or #525 adapter and adds no runtime semantics of its own.

**Files:**

- Modify: `CMakeLists.txt`
- Modify: `apps/core-cli/src/main.cpp`
- Modify: `apps/core-mcp/lmdj_core_mcp/server.py`
- Modify: `apps/core-mcp/lmdj_core_mcp/c_api.py`
- Modify: `apps/native-host/src/main.cpp`
- Test: `tests/core/facade/c_api_test.cpp`
- Modify: `tests/host/mcp_stdio_test.py`
- Test: `tests/host/performance_cli_test.py`
- Test: `tests/host/performance_mcp_test.py`
- Test: `tests/host/cross_host_performance_idempotency_test.py`

- [ ] RED: add CLI, C API and MCP suites enumerating all 23 operations in the
  Locked Facade Surface (three Pattern-slot plus twenty Performance
  operations), asserting operation kind and strict request/result schema match
  the Facade one-to-one. A set comparison must fail when either side adds,
  removes or wildcard-collapses a name. MCP `outputSchema` success results are
  operation-specific closed schemas; a generic `{type: object}` result is not
  parity and must fail this gate.
- [ ] RED: add `cross_host_performance_idempotency_test.py` asserting an MCP flush replayed by the CLI with the same identity returns `replayed: true`, produces one revision, and leaves `project.inspect` byte-identical.
- [ ] Extend the black-box journey across CLI→MCP→Native for begin, raw event,
  launch request/ack fixture, flush, stop, save, inspect, replay, stop, delayed
  Artifact bind and resample. Separately execute owner-loss→recovery list→apply
  and owner-loss→recovery discard; assert every far-side persisted state.
- [ ] Register the operations in all three Hosts; add no Host-side time/order,
  gesture coalescing, replay resolution, Pattern-slot truth, Artifact digest
  trust or recovery fingerprint logic.
- [ ] Register the three new Host suites with CTest so the full Core gate executes
  them, and update the existing MCP stdio exact tool-schema inventory without
  weakening it to a subset assertion.
- [ ] GREEN: run `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with
  `feat(hosts): expose Performance operations in CLI, MCP and Native (fixes #432)`.

## Task 7: Add the Web Runtime Gesture and Launch Bridge

**Issue:** #433. Hard dependencies: #430 and merged #525/#571; Task 9 also
consumes Task 5 replay.

**Files:**

- Modify: `packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`
- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/src/bridge.cpp`
- Modify: `packages/web-runtime-platform/CMakeLists.txt`
- Modify: `packages/web-runtime-platform/web/protocol.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_types.d.ts`
- Modify: `apps/web-runtime-host/src/main.mjs`
- Modify: `CMakeLists.txt`
- Test: `packages/web-runtime-platform/test/performance_bridge_test.cpp`
- Test: `packages/web-runtime-platform/test/performance_protocol.test.mjs`
- Modify: `packages/web-runtime-platform/test/source_boundary_test.py`

**Interfaces:**

- Consume the #525 public `facade::EnginePerformanceAdapter` and
  `facade::PatternPublicationGateway`; Web Runtime must not implement a second
  Performance clock, input sequencer, launch acknowledger or replay
  controller.
- Change `ControlRuntime::create` so its `RealtimeEngine` exists before the
  `Application` is constructed. Build the engine adapter against that engine,
  inject its four authorities into `ApplicationConfig`, and retain only the
  adapter's `service` callable in the control runtime. The Web entry point in
  `bridge.cpp` no longer constructs an `Application` with null Performance
  authorities.
- The gateway receives only the immutable `RuntimeSnapshot` resolved by the
  Facade. It converts/publishes that material through the existing
  `PreparedPatternView` and replacement-authority path; it never maps a slot,
  loads Project Truth or accepts a Host-supplied tick/frame.
- Call `adapter.service()` before each Performance dispatch and from the
  existing periodic control-thread realtime service under the same control
  serialization. Query methods remain read-only; the render thread gains no
  entry point, callback, allocation or lock.

- [ ] RED: extend the source-boundary suite to forbid, in Host JavaScript, any
  wall-clock/tick/frame/sequence field, semantic gesture coalescing, FX
  chain-order decision, Pattern-slot truth, replay resolution, Artifact digest
  trust or recovery fingerprint computation.
- [ ] RED: add protocol vectors for each strict raw event union, event/request/
  gesture identity collision, every result projection, and all invalid extra
  fields. Assert Bank switching sends no Core message.
- [ ] RED: add boundary bridge tests for pending target tick, unclaimed request
  replacement, claimed request deferral, actual ack, empty-slot no-change ack,
  and failure/cancel/owner-loss with no canonical event. Host messages never
  contain the effective tick before Core emits the acknowledgement.
- [ ] RED: add a construction/service witness proving the Web `Application`
  receives all four #525 adapter authorities and that render-only progression
  plus the existing periodic control service produces launch/replay progress
  with no intervening Host request. A one-shot `status` query must not advance
  either state.
- [ ] Implement thin protocol translation only. Host may batch raw move
  messages for transport efficiency only if it preserves every message and
  order; it may not last-write-win or deduplicate. Reuse the #525 engine
  adapter and the Stage 9 acknowledgement predicate repaired by #376.
- [ ] GREEN: run `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/core.sh test dev stress`; expect the render/concurrency
  guards to pass unchanged.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with
  `feat(web-runtime): bridge Performance gestures and launches (fixes #433)`.

## Task 8: Add the Host-Layer Stereo WAV Tap and OPFS Writer

**Issue:** #434. Hard dependency: #433.

**Files:**

- Create: `apps/creator-web/src/record/master_tap_worklet.js`
- Create: `apps/creator-web/src/record/master_tap_source.ts`
- Create: `apps/creator-web/src/record/wav_stream_writer.ts`
- Create: `apps/creator-web/src/record/performance_recording_store.ts`
- Modify: `apps/creator-web/src/capture/wav_encoder.ts`
- Test: `apps/creator-web/test/wav_stream_writer.test.ts`
- Test: `apps/creator-web/test/master_tap.test.ts`
- Test: `apps/creator-web/test/performance_recording_store.test.ts`

- [ ] RED: add `wav_stream_writer.test.ts` asserting streamed PCM16 48 kHz stereo output is a valid WAV at every flush boundary; cover `0`, `86400000`, and `86400001` attempted frames; assert that the accepted maximum is 345,600,000 PCM bytes plus the canonical 44-byte header; assert that limit, writer error and OPFS failure seal the durable prefix without discarding already-written frames.
- [ ] RED: add `master_tap.test.ts` asserting the tap emits `PERFORM_BATCH_FRAMES = 4800`, accepts at most `PERFORM_QUEUE_BATCHES = 32` pending batches, seals when a 33rd batch arrives, drops only the non-durable recording tail under back-pressure, displays the failure reason, and never waits for, blocks or signals the render path.
- [ ] RED: add `performance_recording_store.test.ts` proving finalization computes
  exact sha256/media type/byte length, installs the immutable WAV in
  Project-managed OPFS before save/bind, passes only ArtifactRef through
  Facade, retains an unbound temp file after retryable bind failure, and deletes
  it only after successful discard or bind acknowledgement.
- [ ] Implement the tap as a same-origin AudioWorklet distribution asset (the hardened CSP rejects blob:/data: module URLs), reusing the delivered capture worklet's batch contract; extend `wav_encoder.ts` for streaming rather than forking it.
- [ ] Make `wav_stream_writer.ts` require the Host parameters named `perform_recording_frames` and `perform_recording_queue_batches`; unit tests inject the locked values `86400000` and `32`. Do not add a default or mutate an active manifest in this Task. Task 10 adds the exact keys to Assembly, generated identity, manifest gates, packaging tests and the distribution manifest together with Product Build `1.0.42.0`.
- [ ] Implement `performance_recording_store.ts` as the Host owner of temp and
  finalized OPFS handles. It may copy/finalize bytes into managed storage but
  never asks Core to open a Host path and never deletes a file before the
  corresponding Facade success result is observed.
- [ ] GREEN: run the Creator unit suite and `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with
  `feat(creator): stream the Perform stereo WAV to OPFS (fixes #434)`.

## Task 9: Build the Creator Perform Surface

**Issue:** #435. Hard dependencies: #431, #433 and #434.

**Files:**

- Create: `apps/creator-web/src/components/perform_surface.tsx`
- Create: `apps/creator-web/src/components/fx_slider_bank.tsx`
- Create: `apps/creator-web/src/components/pattern_launch_strip.tsx`
- Create: `apps/creator-web/src/state/perform_state.ts`
- Modify: `apps/creator-web/src/components/mode_rail.tsx`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/state/creator_state.ts`
- Modify: `apps/creator-web/src/state/view_model.ts`
- Modify: `apps/creator-web/src/styles.css`
- Test: `apps/creator-web/test/perform_surface.test.tsx`
- Test: `tests/platform/web/creator/creator_web_perform.spec.mjs`

- [ ] RED: add `perform_surface.test.tsx` asserting the P10-D17 layout order, that the eight sliders render in `FX_CHAIN_ORDER`, that HOLD is a single global control, that Bank switching is instant with no Core round-trip, and that Sample/Sequence surfaces are unchanged.
- [ ] RED: add `creator_web_perform.spec.mjs` walking the **complete** designed
  journey sentence by sentence — assign/move a Pattern slot, begin a durable
  draft, play Pad, launch and continue beyond actual ack, engage/move/release
  FX, latch/unlatch HOLD, switch Banks, flush, stop, finalize WAV, save/name,
  replace a Pad sample, replay, then resample a selected range. After each
  transition assert visible state and persisted far-side truth.
- [ ] Add separate journeys for discard with temp-WAV cleanup, owner-loss
  recovery apply/discard, writer-backpressure sealed prefix, bind retry, empty
  Pattern slot gap and Replay stop neutral reset. Do not trim journeys to the
  implemented prefix.
- [ ] Implement pointer, touch and MIDI paths through one raw gesture encoder.
  Each input supplies event/gesture identity but never time/order; JavaScript
  sends every raw value and never coalesces. Render pending Pattern state from
  Core target/ack results, not a Host timer.
- [ ] GREEN: run the Creator unit and Playwright suites; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with
  `feat(creator): build the Perform surface (fixes #435)`.

## Task 10: Integrate Versions, Assembly, Current Portal and Automated Acceptance

**Issue:** #436. Hard dependencies: #427, #428, #429, #430, #431, #432,
#433, #434, #435, #498 and #499.

**Files:**

- Modify: `packages/authoring-domain/module.json`
- Modify: `packages/project-io/module.json`
- Modify: `packages/project-cooker/module.json`
- Modify: `packages/audio-runtime/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/native-host/module.json`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/creator-web/module.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/version.json`
- Modify: `packages/web-runtime-platform/src/manifest_gate.cpp`
- Modify: `packages/web-runtime-platform/CMakeLists.txt`
- Modify: `packages/web-runtime-platform/test/manifest_gate_test.cpp`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `apps/web-runtime-host/tools/package.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `apps/web-runtime-host/test/distribution_test.py`
- Modify: `apps/creator-web/tools/package.py`
- Modify: `products/lmdj/generated/web-runtime-identity.json`
- Modify: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`
- Modify: `apps/architecture-portal/docs/contracts/project.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/authoring-domain.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-io.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-cooker.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/audio-runtime.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Modify: `apps/architecture-portal/docs/hosts/core-cli.mdx`
- Modify: `apps/architecture-portal/docs/hosts/core-mcp.mdx`
- Modify: `apps/architecture-portal/docs/hosts/native-host.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/product/workflows.mdx`
- Modify: `apps/architecture-portal/docs/product/capability-map.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/diagrams/lmdj-product.architecture.json`
- Modify: `apps/architecture-portal/diagrams/lmdj-core.architecture.json`
- Modify: `apps/architecture-portal/diagrams/authoring-domain.architecture.json`
- Modify: `apps/architecture-portal/diagrams/project-io.architecture.json`
- Modify: `apps/architecture-portal/diagrams/project-cooker.architecture.json`
- Modify: `apps/architecture-portal/diagrams/audio-runtime.architecture.json`
- Modify: `apps/architecture-portal/diagrams/application-facade.architecture.json`
- Modify: `apps/architecture-portal/diagrams/web-runtime-platform.architecture.json`
- Create: `docs/quality/2026-08-30-stage10-perform-acceptance.md`

- [ ] Re-read every active manifest before applying versions. If another merged Build or module release has consumed an exact target, **stop and amend this plan through design review**; do not silently choose new identities (Stage 9 `1.0.31.0` lesson).
- [ ] Apply the module, Host, Contract and Product Build versions; lock Assembly to v4-only output; add `perform_recording_frames: 86400000` and `perform_recording_queue_batches: 32` to the exact-key `resource_limits`; regenerate and validate every identity/distribution consumer listed above.
- [ ] Update current-truth Portal pages and source diagrams for the listed routes.
- [ ] Record the acceptance ledger with commands, counts, revisions, CI run IDs
  and digests. Enumerate the complete Facade/CLI/MCP/Native/Browser journeys
  from spec §10 and assert the far side of every transition. Record physical
  rows honestly as `deferred` where no device evidence exists.
- [ ] Run `scripts/core.sh test dev full`, `scripts/core.sh test dev stress`, `scripts/core.sh coverage check`, `scripts/core.sh proof`, `python3 scripts/version.py verify --version-file products/lmdj/version.json`, `bash tests/build/test_active_tree.sh` and `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with
  `feat(product): integrate Stage 10 Perform versions and current truth (fixes #436)`.

## Task 11: Freeze the Immutable Portal Snapshot and Final Acceptance Evidence

**Issue:** #438. Hard dependency: merged Task 10 #436.

**Files:**

- Create: the immutable Portal snapshot produced by `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`
- Modify: `docs/quality/2026-08-30-stage10-perform-acceptance.md`

- [ ] Confirm the working tree is clean and the Task 10 commit is merged before snapshotting; the snapshot must bind a committed, non-dangling revision (Stage 9 squash-witness lesson; see `.agents/pitfalls/squash-witness-provenance.md`).
- [ ] Run `scripts/architecture-portal.sh version 1.0.42.0 canary`; expect a new immutable snapshot.
- [ ] Attach the snapshot identity and final evidence to the acceptance ledger.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with
  `docs(portal): snapshot the Stage 10 Perform Product Build (fixes #438)`.

## Task 12: Bind the Release Intent and Publish the Canary Release

**Issue:** #468. Hard dependency: merged Task 11 #438 and its post-squash
snapshot provenance witness. Runtime deployment and beta/stable promotion are
outside this Task.

**Files for the release-intent PR:**

- Modify: `tests/build/release_model_test.py`
- Create: dated `docs/superpowers/plans/YYYY-MM-DD-lmdj-1-0-42-release-intent.md`
- Create: dated `docs/release-evidence/YYYY-MM-DD-lmdj-1.0.42.0-canary-release-intent.md`
- Modify: `docs/release-evidence/release-intents.json`
- Modify only if publication changes current truth:
  `apps/architecture-portal/docs/operations/version-and-release.mdx`

- [ ] Read `.agents/skills/lmdj-release/SKILL.md` and the four release pitfalls
  named by #468. Start with
  `scripts/release.sh audit --remote --tag lmdj-v1.0.42.0`; any state other
  than the exact expected pre-intent state stops the Task.
- [ ] Resolve `TARGET` to the Task 11 squash on protected main. Prove it is a
  main ancestor, Product Build is `1.0.42.0`, Assembly lock digest equals the
  immutable snapshot metadata, and snapshot provenance validates after squash.
- [ ] Establish retained **full** exact-main Core CI for `TARGET`. A focused or
  requested manifest is not evidence. Record the successful run ID, exact head,
  Change Scope, PR Gate and retained `ci-scope-<TARGET>` artifact.
- [ ] **RED:** make `release_model_test.py` require the exact tag, target,
  snapshot, channel `canary`, profile `web-hosts`, disposition
  `releasable`, full-CI run ID and dated evidence path. Run the release model,
  audit and CI evidence tests; expect the missing intent to fail.
- [ ] Create the dated intent plan/evidence and add exactly one immutable row to
  `release-intents.json`. Run the three release test modules, Portal check,
  version verification and `scripts/release.sh audit --local --tag
  lmdj-v1.0.42.0`; expect all pass.
- [ ] Commit the four declared intent files as
  `docs(release): authorize 1.0.42.0 canary intent (fixes #468)`, ship its PR
  through `issue-done`, then rerun the canonical remote audit on merged main.
- [ ] Execute `prepare`, `push-tag`, `create-draft`, `verify-draft` and protected
  `publish-release.yml` only through the stable `scripts/release.sh` mapping.
  Treat each mutation as its own audited transition, recording the exact result
  before the next. Never use handwritten tag/Release commands, `--clobber`,
  `git push --tags` or a movable tag.
- [ ] Final remote audit must report `published` with exact tag, Release ID,
  target and per-asset sha256 inventory. Record explicitly that deployment and
  beta/stable Channel promotion were not performed by this Task.

## Version Management

Allocation was refreshed on 2026-09-02 after `1.0.41.0` became the current
protected-main Product Build, immutable Portal snapshot, signed tag, published
canary Release and release-intent row. The refresh read protected `origin/main`
`9264d8def1d321e284b82eca4f448df256c6ca14`, every active module/Host manifest,
`products/lmdj/version.json`, Assembly lock, snapshot inventory, local/remote
tags, GitHub Releases, open Issues/PRs and
`docs/release-evidence/release-intents.json`; `1.0.42.0` was absent from every
allocation surface. Task 10 must repeat that read-only audit immediately before
mutation; if any exact target has since been consumed, stop and refresh this
table rather than substituting an identity.

| Component | Protected-main baseline | Locked Stage 10 target | Reason |
|---|---|---|---|
| Product Build | `1.0.41.0` | `1.0.42.0` | new integrated Assembly, Contract and Host resource identity |
| `lmdj.project` Contract | `v3` / `3.0.0` | add `v4` / `4.0.0`; v3 becomes read-only migration input | incompatible Project writer Contract |
| foundation | `0.3.0` | unchanged `0.3.0` | Task 1 keeps Performance identity in authoring-domain; no foundation API change |
| authoring-domain | `1.0.0` | `2.0.0` | `pattern_slots`, Performances and event vocabulary change the public domain surface |
| project-io | `1.0.1` | `2.0.0` | session-kind journal, durable draft lifecycle and two-phase rebase change the public I/O surface |
| project-cooker | `1.0.0` | `1.1.0` | additive replay projection inputs |
| audio-runtime | `2.0.1` | `3.0.0` | master FX chain changes the public engine surface |
| application-facade | `2.1.1` | `3.0.0` | Performance operation set changes the public Facade surface |
| web-runtime-platform | `2.0.1` | `3.0.0` | protocol and exact resource-manifest gate change |
| core-cli | `2.0.0` | `3.0.0` | public command surface changes |
| core-mcp | `2.0.0` | `3.0.0` | public tool surface changes |
| native-host | `2.0.0` | `3.0.0` | public operation surface and dependency identity change |
| web-runtime-host | `2.1.1` | `3.0.0` | Platform dependency, protocol and distribution manifest change |
| creator-web | `2.1.1` | `3.0.0` | Perform UI, recording surface and distribution manifest change |

Version impact of **this plan document**: none. It changes no manifest, Contract artifact, module version or Product Build.

## Documentation Impact

Documentation impact: required.

Task 10 updates implementation-backed current truth and source diagrams for these Portal routes:

- `/assembly/lmdj/`
- `/contracts/project/`
- `/core/modules/authoring-domain/`
- `/core/modules/project-io/`
- `/core/modules/project-cooker/`
- `/core/modules/audio-runtime/`
- `/core/modules/application-facade/`
- `/core/modules/web-runtime-platform/`
- `/hosts/core-cli/`
- `/hosts/core-mcp/`
- `/hosts/native-host/`
- `/hosts/web-runtime/`
- `/hosts/creator-web/`
- `/platform/web-runtime/`
- `/product/workflows/`
- `/product/capability-map/`
- `/operations/testing-and-proof/`

The immutable Product Build snapshot is created only after the Task 10 version/current-source commit is clean and merged. Snapshot creation is documentation evidence, not Channel promotion.

## Issue Map

The Stage 10 umbrella is #425. #426 created the original map; #488 repaired its
Contract before Task 4, creating #498/#499 and incorporating the already-open
release boundary #468. The 2026-09-01 Replay/Lineage repair created #516 before
Task 5; the 2026-09-01 host runtime/session repair created #523/#524/#525
before Task 6, and its 2026-09-02 cross-Host RED/review created #570/#571.

| Plan Task | GitHub Issue | Priority | Primary Project area | Hard dependencies |
|---|---|---|---|---|
| Prerequisite | Stage 9 remediation #371–#376, #379/#380 | P1 | Core | — |
| Prerequisite | #426 plan refresh: versions, limits and Issue map | P1 | Docs/Governance | remediation closed |
| Design repair | #488 | P1 | Docs/Governance | Tasks 1–3 start-gate evidence |
| 1 | #427 | P1 | Contracts | #426 |
| 2 | #428 | P1 | Core | #427 |
| 3 | #429 | P1 | Core | #427 |
| 3A | #498 | P1 | Contracts/Core | #427, #488 |
| 3B | #499 | P1 | Core | #428, #488 |
| 4 | #430 | P1 | Core | #428, #429, #498, #499 |
| 5 | #431 | P1 | Core | #430 |
| Prerequisite | #523 | P1 | Core | #431, repair docs PR |
| Prerequisite | #524 | P1 | Core | #523 |
| Prerequisite | #525 | P1 | Core/Native Host | #523 |
| Prerequisite | #570 | P1 | Core | #523, repair docs PR |
| Prerequisite | #571 | P1 | Core/Native Host | #523, #525, #570, repair docs PR |
| 6 | #432 | P2 | Native Host | #430, #431, #523, #524, #525, #570, #571 |
| 7 | #433 | P1 | Web Host | #430, #525, #571 |
| 8 | #434 | P1 | Creator | #433 |
| 9 | #435 | P1 | Creator | #431, #433, #434 |
| 10 | #436 | P1 | Product | #427, #428, #429, #430, #431, #432, #433, #434, #435, #498, #499 |
| 11 | #438 | P2 | Docs/Governance | #436 |
| 12 | #468 | P2 | CI/Release | #438 |

## Final Acceptance Boundary

Stage 10 is **implementation-complete** only when Tasks 1–11 plus repair Tasks
3A/3B are merged and individually accepted, `lmdj.project.v4` is the sole
active writer Contract, full/stress/coverage/proof and complete cross-Host
journeys pass on the integrated head, Browser and Native evidence is attached,
the OPFS physical fixture has real evidence or an honest `deferred`, and Product
Build `1.0.42.0` has an immutable Portal snapshot.

Stage 10 is **canary-release-complete** only after Task 12's final remote audit
reports the immutable signed tag and published Release with exact asset hashes.
Runtime deployment and beta/stable Channel promotion remain separate from both
completion claims.
