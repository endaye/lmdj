# LMDJ Stage 10 Perform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a testable Stage 10 candidate in which Creator performs live — playing Pads, launching Patterns at Bar boundaries, switching Banks instantly, applying eight momentary FX as continuous slider gestures with a global HOLD — records that performance as a `lmdj.project.v4` Performance event stream plus a streamed stereo WAV, replays it against the current Project, and resamples a selected range of that recording into a Pad through the existing Bank-quota commit path.

**Authoring gate (refreshed 2026-08-30):** This plan is written under the approved design [`2026-08-28-lmdj-stage10-perform-design.md`](../specs/2026-08-28-lmdj-stage10-perform-design.md) (P10-D1–D17) and its five decision files. Stage 9 remediation is closed: #371 and #380 are closed, PR #424 records the exact-main evidence, and Core CI run `33259586218` succeeded for the Stage 9 integrated product revision. Protected `main` at `184b808920dcc7a97974c88a814c252ddbfc6f6f` carries Product Build `1.0.40.0`. Issue #426 refreshed the versions, resource limits and Issue map below. **Task 1 may start only after #426 merges; no other authoring prerequisite remains.**

**Architecture:** Extend the Stage 9 foundation rather than parallel it. `lmdj.project.v4` adds a `performances` collection whose events reuse the tick-native clock and canonical ordering already proven in v3. Project I/O generalizes its Sequence journal into a session-kind-parameterized journal so Performance recording inherits writer-lease admission, durable flush intent, idempotent receipts, sealing and fingerprint-gated recovery unchanged. Audio Runtime gains a fixed-order, pre-allocated eight-effect master FX chain driven by integer gesture events; the render path keeps its zero-allocation, lock-free, `noexcept` contract. Application Facade owns Performance session admission, the Perform/Sequence mutual exclusion, replay resolution against the current Project, and the resample selection commit that reuses D1's quota path. The stereo WAV tap lives entirely in the Host layer, mirroring the delivered Stage 8B capture worklet, and never touches the engine. Work is split into eleven independently reviewable Tasks; each Task is one Issue, one Conventional Commit, one Pull Request.

**Tech Stack:** C++20, CMake 3.24+, JSON Schema, nlohmann/json, SHA-256 canonical JSON vectors, Emscripten `6.0.5`, WasmFS OPFS, SharedArrayBuffer, Wasm AudioWorklet, JavaScript ES modules, React `19.2.8`, TypeScript `7.0.2`, Vite `8.2.1`, Vitest `4.1.10`, Playwright `1.62.1`, Python 3.11, Docusaurus Architecture Portal, GitHub Issues/Projects.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-08-28-lmdj-stage10-perform-design.md` (P10-D1–D17) plus the five 2026-08-28 decision files. Any conflict returns to design review; an implementation Task must not silently choose a different semantic.
- Execute each Task on a short-lived `feat/<task>` or `fix/<task>` branch in an isolated worktree. Never implement on `main`.
- Each Task maps one-to-one to one GitHub Issue, one reviewable Conventional Commit, and one Pull Request. **Do not aggregate Tasks into a single squash PR** — this is the explicit process correction from the Stage 9 review.
- Functional Tasks keep active manifests and Product Build at their current values until Task 10. Task 10 is the version/current-truth integration boundary; Task 11 is the separate clean-commit immutable Portal snapshot boundary.
- Project Truth is authoritative. Runtime Snapshot, the FX chain state and the WAV tap are derived or transient and are never persisted as Project Truth.
- Hosts use only Application Facade. They must not parse a Project bundle, read a journal directly, or reproduce gesture coalescing, replay resolution, fingerprint or flush rules.
- Exactly one recording session may be active per Project bundle. Perform and Sequence recording are mutually exclusive; the second `begin` is `INVALID_ARGUMENT`. Admission and `expected_revision` validation occur under the same existing Project writer lease.
- Every event timestamp is read from the integer tick clock at Facade admission. Host JavaScript never supplies `runtime_frame` or `input_sequence`.
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

- Events are canonically ordered by `(tick, kind_ordinal, fx_or_slot)`; `kind_ordinal` follows the order listed above.
- `fx_move` is emitted only when the value differs from the previous value for that FX, and at most once per FX per `FX_COALESCE_FRAMES` window.
- `fx_release` without a matching open `fx_engage` is invalid; `fx_engage` for an already-engaged FX is invalid.
- `hold_on` while HOLD is on, and `hold_off` while HOLD is off, are invalid.
- `pattern_launch.effective_tick` is the acknowledged boundary tick, never the input tick.
- No event carries an Asset reference, a `pattern_id`, or a Bank identity.

## Locked Project v4 Migration

v3 → v4 is a deterministic total migration:

- `contract` becomes `lmdj.project.v4`.
- A `performances` array is added, empty for every migrated v3 Project.
- No other field changes; `patterns`, `banks`, `assets`, `bpm` and `sequence_settings` migrate byte-identically.
- v1 and v2 remain read-only migration inputs through their existing v3 path; the migration chain is v1→v2→v3→v4 with no new direct edges.
- A `performances` key present in a v3-declared document is invalid input, not an implicit upgrade.

## Dependency Order

```text
Prerequisite: Stage 9 remediation (#371-#376, #379/#380) closed and this plan's versions refreshed
  └─ Task 1 Project v4 Contract and Performance domain
       ├─ Task 2 session-kind journal and Performance Project I/O
       │    └─ Task 4 Application Facade Performance surface
       ├─ Task 3 master FX chain in Audio Runtime
       │    └─ Task 4 Application Facade Performance surface
       └─ Task 5 replay resolution and resample selection commit
            └─ (needs Task 4)
Task 4 ──┬─ Task 6 CLI, MCP and Native Host parity
         └─ Task 7 Web Runtime Platform gesture and launch bridge
              ├─ Task 8 Host-layer stereo WAV tap and OPFS writer
              └─ Task 9 Creator Perform surface
Tasks 1-9 ─── Task 10 versions, Assembly, current Portal, automated acceptance
                   └─ Task 11 immutable Portal snapshot and final acceptance evidence
```

Tasks 2 and 3 may run in parallel after Task 1. Tasks 6 and 7 may run in parallel after Task 4. Tasks 8 and 9 may run in parallel after Task 7, but Task 9's recording controls need Task 8's Host contract to be stable. Integration and snapshotting stay serial through Tasks 10 and 11.

## Design Traceability

| Approved decision | Primary implementation Tasks | Acceptance witness |
|---|---|---|
| P10-D1, P10-D17: Perform mode and surface layout | 9 | Mode Rail enablement and Creator component tests |
| P10-D2, P10-D3: Bar-boundary Pattern Launch over the same 16 slots | 3, 4, 7, 9 | boundary integration test; recorded tick equals acknowledged tick |
| P10-D4: Bank switching as view state | 7, 9 | no revision, no event, no preparation latency |
| P10-D5, P10-D15: continuous gesture stream and integer scale | 3, 4, 7 | gesture vectors; dedup and coalescing boundary tests |
| P10-D6: global HOLD | 3, 4, 9 | latch/release state-machine tests |
| P10-D7: fixed chain order, pre-allocation, determinism | 3, 10 | zero-allocation guard; live-vs-replay sample equality |
| P10-D8: v4 Performance object | 1, 10 | Contract fixtures and migration vectors |
| P10-D9: generalized session and mutual exclusion | 2, 4, 6 | second-begin `INVALID_ARGUMENT`; fault matrix |
| P10-D10: replay against the current Project | 5, 9 | changed-sample, moved-slot and empty-slot replay tests |
| P10-D11: live-capture resample over the D1 commit path | 5, 8 | Lineage assertions; `BANK_QUOTA_EXHAUSTED` non-destructive test |
| P10-D12: Host-layer streamed WAV with sealing | 8 | long-record OPFS test; sealed-prefix validity; render glitch-free stress |
| P10-D13: one Facade surface across Hosts | 4, 6, 7 | CLI/MCP black-box journey parity |
| P10-D14: FX roster with Cutter | 3 | per-effect audible-change and division-ladder tests |
| P10-D16: Perform rebase whitelist | 4 | settings-rebase matrix; armed-capture rejection test |

## Task 1: Add Project v4 and the Performance Authoring Domain

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

- [ ] RED: add `performance_test.cpp` asserting the locked event vocabulary, canonical ordering by `(tick, kind_ordinal, fx_or_slot)`, and every invalid-event rule (unmatched release, double engage, double hold, Asset/pattern_id/Bank reference); expect failure before implementation.
- [ ] RED: add `migration_v4_test.cpp` asserting v3→v4 adds an empty `performances`, migrates all other fields byte-identically, and rejects a v3-declared document that already carries `performances`; expect failure.
- [ ] Author `lmdj.project.v4.schema.json` with the `performances` collection, per-event `$defs`, `PERFORMANCE_NAME_MAX`, `PATTERN_SLOT_MIN/MAX` and the `FX_VALUE_MIN/MAX` bounds.
- [ ] Implement the domain `Performance` type, canonical ordering, validation, and the v3→v4 migration edge; keep v1→v2→v3 untouched.
- [ ] GREEN: run `scripts/core.sh test dev fast`; expect the two new suites to pass with no regression.
- [ ] Run `python3 tests/conformance/schema_contract_test.py`; expect PASS including the new fixtures.
- [ ] Run `bash tests/build/test_active_tree.sh` and `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(contracts): add Project v4 with Performance events`.

## Task 2: Generalize the Session Journal for Performance Recording

**Files:**

- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Test: `tests/core/project_io/performance_journal_test.cpp`
- Test: `tests/core/project_io/session_mutual_exclusion_test.cpp`

- [ ] RED: add `performance_journal_test.cpp` covering begin/append/complete/seal/recover for a Performance session, durable flush intent before Project mutation, idempotent receipt replay for a repeated `command_id`, and journal cleanup only after all flushes are complete.
- [ ] RED: add `session_mutual_exclusion_test.cpp` asserting a Perform begin while a Sequence session is active returns `INVALID_ARGUMENT`, and the reverse, with admission performed inside the writer lease.
- [ ] Introduce a `SessionKind` discriminator and parameterize the journal record types over it without changing any existing Sequence-session on-disk semantics; a v3-era Sequence journal must still load and reconcile unchanged.
- [ ] Extend fingerprint gating to the Performance recovery path: recovery may append only when the target Performance's canonical fingerprint still matches; deletion or incompatible change fails closed and retains the recovery file.
- [ ] GREEN: run `scripts/core.sh test dev fast`; expect PASS.
- [ ] Run `scripts/core.sh test dev stress`; expect the existing journal stress tier to pass unchanged.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(project-io): generalize the recording journal over session kinds`.

## Task 3: Add the Master FX Chain to Audio Runtime

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

- [ ] RED: add `master_fx_test.cpp` asserting each of the eight effects in `FX_CHAIN_ORDER` changes the rendered signal measurably when engaged and restores bit-identical passthrough on release; assert the filter's `500` bypass and the tempo-locked division ladders of `stutter` and `cutter` map by integer division only.
- [ ] RED: add `master_fx_determinism_test.cpp` asserting identical Snapshot plus identical gesture event stream yields sample-identical output across two runs and across engage/move/release orderings that coalesce to the same values.
- [ ] RED: add `master_fx_allocation_guard_test.cpp` extending the existing render-path guard so a fully engaged eight-effect chain performs no allocation, no lock and no throw inside `render`.
- [ ] RED: add `master_fx_stress_test.cpp` (label `stress`, and exclude it from the `coverage` preset in the same commit) driving all eight effects at maximum gesture rate for a sustained run with zero underruns.
- [ ] Implement `MasterFxChain` as a POD-state, pre-allocated, fixed-order chain applied after voice mixing; all buffers sized at Snapshot preparation and owned outside the audio thread. Apply gestures through the existing lock-free control-to-render hand-off; add no new locking discipline.
- [ ] Implement each effect as the deterministic LMDJ reference DSP defined by its golden parameter mapping and behavioral tests. Koala manual behavior is the product-direction reference; no test, documentation or acceptance claim may assert proprietary Koala coefficient, algorithm or sample identity.
- [ ] Wire HOLD as a single chain-level latch: on release with HOLD engaged, freeze that effect's current value; on `hold_off`, release every frozen effect.
- [ ] GREEN: run `scripts/core.sh test dev full` then `scripts/core.sh test dev stress`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(audio): add the fixed-order master FX chain`.

## Task 4: Add the Authoritative Performance Application Facade

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Test: `tests/core/facade/performance_session_test.cpp`
- Test: `tests/core/facade/performance_gesture_admission_test.cpp`
- Test: `tests/core/facade/performance_rebase_matrix_test.cpp`

- [ ] RED: add `performance_session_test.cpp` for the operation set `performance.record.begin|event|flush|stop|status`, `performance.replay.*`, `performance.rename`, `performance.delete`, asserting registration kind, request-shape validation, `expected_revision` binding and idempotent flush receipts.
- [ ] RED: add `performance_gesture_admission_test.cpp` asserting every timestamp comes from the integer tick clock at admission, that `fx_move` dedup and `FX_COALESCE_FRAMES` coalescing happen in Core, and that `pattern_launch` records the acknowledged boundary tick rather than the input tick.
- [ ] RED: add `performance_rebase_matrix_test.cpp` covering P10-D16: BPM and Quantize/Swing rebase and recording continues; Quantize/Swing produce no timing change in recorded events; Sample-class Commands including armed-Pad capture commit fail while recording continues and the session is not sealed; unknown Commands fail closed.
- [ ] Implement session admission under the writer lease with Perform/Sequence mutual exclusion, gesture normalization, boundary-bound launch recording, flush orchestration and recovery orchestration; reuse the Stage 9 primitives rather than reimplementing them.
- [ ] GREEN: run `scripts/core.sh test dev full`; expect PASS and no facade coverage-gate regression.
- [ ] Run `scripts/core.sh coverage check`; expect PASS at the current floor (raise real coverage; never lower the floor).
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(facade): add the Performance recording surface`.

## Task 5: Add Replay Resolution and the Resample Selection Commit

**Files:**

- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/project-cooker/src/project_cooker.cpp`
- Test: `tests/core/facade/performance_replay_test.cpp`
- Test: `tests/core/facade/resample_performance_test.cpp`

- [ ] RED: add `performance_replay_test.cpp` asserting replay resolves against the **current** Project: a replaced Pad sample plays the new sound; a Pattern moved to another slot follows the slot index; an emptied slot's launch is a non-fatal silent gap; replay performs no fingerprint gating and mutates nothing.
- [ ] RED: add `resample_performance_test.cpp` asserting a selected range of a recording Artifact commits through the D1 path with identical quota validation, that Lineage records source hash, range, Performance identity and recording revision, that the user-chosen target Pad is never auto-selected, and that `BANK_QUOTA_EXHAUSTED` leaves Project, Asset, Pad and revision unchanged.
- [ ] Implement replay resolution as a read-only derived projection; implement `ResamplePerformance` as an atomic Command over the existing selection-commit path with no new Job category.
- [ ] GREEN: run `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(facade): add Performance replay and resample commit`.

## Task 6: Migrate CLI, MCP and Native Host to Performance Operations

**Files:**

- Modify: `apps/core-cli/src/main.cpp`
- Modify: `apps/core-mcp/lmdj_core_mcp/server.py`
- Modify: `apps/core-mcp/lmdj_core_mcp/c_api.py`
- Modify: `apps/native-host/src/main.cpp`
- Test: `tests/host/performance_cli_test.py`
- Test: `tests/host/performance_mcp_test.py`
- Test: `tests/host/cross_host_performance_idempotency_test.py`

- [ ] RED: add CLI and MCP suites asserting every Performance operation is registered and passes through as pure JSON with no Host-side semantics, and that the MCP schema matches the locked request/response shapes one-to-one.
- [ ] RED: add `cross_host_performance_idempotency_test.py` asserting an MCP flush replayed by the CLI with the same identity returns `replayed: true`, produces one revision, and leaves `project.inspect` byte-identical.
- [ ] Register the operations in all three Hosts; add no Host-side gesture coalescing, replay logic or fingerprint handling.
- [ ] GREEN: run `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(hosts): expose Performance operations in CLI, MCP and Native`.

## Task 7: Add the Web Runtime Gesture and Launch Bridge

**Files:**

- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/web/protocol.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_types.d.ts`
- Modify: `apps/web-runtime-host/src/main.mjs`
- Test: `packages/web-runtime-platform/test/performance_bridge_test.cpp`
- Test: `packages/web-runtime-platform/test/performance_protocol.test.mjs`
- Modify: `packages/web-runtime-platform/test/source_boundary_test.py`

- [ ] RED: extend the source-boundary suite to forbid, in Host JavaScript, any wall-clock timestamp, gesture coalescing, chain-order knowledge, replay resolution or fingerprint computation for Performance.
- [ ] RED: add bridge tests asserting gesture and launch messages carry no `runtime_frame`/`input_sequence`, that Core stamps every tick at admission, and that Bank switching sends no Core message at all.
- [ ] Implement the protocol additions and the acknowledged-boundary launch notification that Creator needs; reuse the Stage 9 acknowledgement mechanism repaired by #376 rather than adding a second one.
- [ ] GREEN: run `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(web-runtime): bridge Performance gestures and launches`.

## Task 8: Add the Host-Layer Stereo WAV Tap and OPFS Writer

**Files:**

- Create: `apps/creator-web/src/record/master_tap_worklet.js`
- Create: `apps/creator-web/src/record/master_tap_source.ts`
- Create: `apps/creator-web/src/record/wav_stream_writer.ts`
- Modify: `apps/creator-web/src/capture/wav_encoder.ts`
- Test: `apps/creator-web/test/wav_stream_writer.test.ts`
- Test: `apps/creator-web/test/master_tap.test.ts`

- [ ] RED: add `wav_stream_writer.test.ts` asserting streamed PCM16 48 kHz stereo output is a valid WAV at every flush boundary; cover `0`, `86400000`, and `86400001` attempted frames; assert that the accepted maximum is 345,600,000 PCM bytes plus the canonical 44-byte header; assert that limit, writer error and OPFS failure seal the durable prefix without discarding already-written frames.
- [ ] RED: add `master_tap.test.ts` asserting the tap emits `PERFORM_BATCH_FRAMES = 4800`, accepts at most `PERFORM_QUEUE_BATCHES = 32` pending batches, seals when a 33rd batch arrives, drops only the non-durable recording tail under back-pressure, displays the failure reason, and never waits for, blocks or signals the render path.
- [ ] Implement the tap as a same-origin AudioWorklet distribution asset (the hardened CSP rejects blob:/data: module URLs), reusing the delivered capture worklet's batch contract; extend `wav_encoder.ts` for streaming rather than forking it.
- [ ] Make `wav_stream_writer.ts` require the Host parameters named `perform_recording_frames` and `perform_recording_queue_batches`; unit tests inject the locked values `86400000` and `32`. Do not add a default or mutate an active manifest in this Task. Task 10 adds the exact keys to Assembly, generated identity, manifest gates, packaging tests and the distribution manifest together with Product Build `1.0.41.0`.
- [ ] GREEN: run the Creator unit suite and `scripts/core.sh test dev full`; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(creator): stream the Perform stereo WAV to OPFS`.

## Task 9: Build the Creator Perform Surface

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
- [ ] RED: add `perform_journey.spec.ts` walking the **complete** designed journey sentence by sentence — record, launch a Pattern and keep recording past the boundary, engage and release FX, latch and unlatch HOLD, switch Banks mid-performance, stop and name, replay after replacing a Pad sample, then resample a selected range into a Pad. Do not trim the journey to what is already implemented (Stage 9 review lesson; see `.agents/pitfalls/acceptance-journey-truncation.md`).
- [ ] Implement the surface with pointer, touch and MIDI input paths sharing one gesture normalizer, sending raw values to Core and never coalescing client-side.
- [ ] GREEN: run the Creator unit and Playwright suites; expect PASS.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(creator): build the Perform surface`.

## Task 10: Integrate Versions, Assembly, Current Portal and Automated Acceptance

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
- Modify: `apps/architecture-portal/docs/**` (routes listed in `## Documentation Impact`)
- Create: `docs/quality/2026-08-30-stage10-perform-acceptance.md`

- [ ] Re-read every active manifest before applying versions. If another merged Build or module release has consumed an exact target, **stop and amend this plan through design review**; do not silently choose new identities (Stage 9 `1.0.31.0` lesson).
- [ ] Apply the module, Host, Contract and Product Build versions; lock Assembly to v4-only output; add `perform_recording_frames: 86400000` and `perform_recording_queue_batches: 32` to the exact-key `resource_limits`; regenerate and validate every identity/distribution consumer listed above.
- [ ] Update current-truth Portal pages and source diagrams for the listed routes.
- [ ] Record the acceptance ledger with commands, counts, revisions, CI run ids and digests; record physical rows honestly as `deferred` where no device evidence exists — never fold them into automated evidence.
- [ ] Run `scripts/core.sh test dev full`, `scripts/core.sh test dev stress`, `scripts/core.sh coverage check`, `scripts/core.sh proof`, `python3 scripts/version.py verify --version-file products/lmdj/version.json`, `bash tests/build/test_active_tree.sh` and `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `feat(product): integrate Stage 10 Perform versions and current truth`.

## Task 11: Freeze the Immutable Portal Snapshot and Final Acceptance Evidence

**Files:**

- Create: the immutable Portal snapshot produced by `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`
- Modify: `docs/quality/2026-08-30-stage10-perform-acceptance.md`

- [ ] Confirm the working tree is clean and the Task 10 commit is merged before snapshotting; the snapshot must bind a committed, non-dangling revision (Stage 9 squash-witness lesson; see `.agents/pitfalls/squash-witness-provenance.md`).
- [ ] Run `scripts/architecture-portal.sh version 1.0.41.0 canary`; expect a new immutable snapshot.
- [ ] Attach the snapshot identity and final evidence to the acceptance ledger.
- [ ] Run `scripts/architecture-portal.sh check`; expect PASS.
- [ ] Commit only the listed files with `docs(portal): snapshot the Stage 10 Perform Product Build`.

## Version Management

Allocation was locked by #426 after Stage 9 remediation closed. The audit read
protected `main` `184b808920dcc7a97974c88a814c252ddbfc6f6f`, every active
module/Host manifest, `products/lmdj/version.json`, Assembly lock, immutable
snapshot inventory, local and remote tags, GitHub Releases, open PRs and
`docs/release-evidence/release-intents.json`. `1.0.41.0` was absent from every
allocation surface on 2026-08-30. Task 10 must repeat that read-only audit
immediately before mutation; if any exact target has since been consumed, stop
and refresh this table rather than substituting an identity.

| Component | Protected-main baseline | Locked Stage 10 target | Reason |
|---|---|---|---|
| Product Build | `1.0.40.0` | `1.0.41.0` | new integrated Assembly, Contract and Host resource identity |
| `lmdj.project` Contract | `v3` / `3.0.0` | add `v4` / `4.0.0`; v3 becomes read-only migration input | incompatible Project writer Contract |
| foundation | `0.3.0` | unchanged `0.3.0` | Task 1 keeps Performance identity in authoring-domain; no foundation API change |
| authoring-domain | `1.0.0` | `2.0.0` | `performances` and event vocabulary change the public domain surface |
| project-io | `1.0.1` | `2.0.0` | journal records gain a session-kind discriminator |
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

The Stage 10 umbrella is #425. Issue #426 created the Task Issues after the
Stage 9 remediation prerequisite closed and locked this exact map.

| Plan Task | GitHub Issue | Priority | Primary Project area | Hard dependencies |
|---|---|---|---|---|
| Prerequisite | Stage 9 remediation #371–#376, #379/#380 | P1 | Core | — |
| Prerequisite | #426 plan refresh: versions, limits and Issue map | P1 | Docs/Governance | remediation closed |
| 1 | #427 | P1 | Contracts | #426 |
| 2 | #428 | P1 | Core | #427 |
| 3 | #429 | P1 | Core | #427 |
| 4 | #430 | P1 | Core | #428, #429 |
| 5 | #431 | P1 | Core | #430 |
| 6 | #432 | P2 | Native Host | #430 |
| 7 | #433 | P1 | Web Host | #430 |
| 8 | #434 | P1 | Creator | #433 |
| 9 | #435 | P1 | Creator | #433, #434 |
| 10 | #436 | P1 | Product | #427–#435 |
| 11 | #438 | P2 | Docs/Governance | #436 |

## Final Acceptance Boundary

Stage 10 is implementation-complete only when all eleven Task Issues are merged and individually accepted, `lmdj.project.v4` is the sole active writer Contract, the full and stress suites pass on the integrated head, Browser and Native evidence is attached, the OPFS write-bandwidth physical fixture has real device evidence or is honestly recorded as `deferred`, and the Product Build has an immutable Portal snapshot. This does not by itself authorize a tag, GitHub Release, deployment, or `canary`/`beta`/`stable` Channel promotion.
