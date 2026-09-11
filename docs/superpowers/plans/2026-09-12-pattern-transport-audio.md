# Global Pattern transport: audio foundation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement acknowledged Pattern-only playback control and phase-preserving Pattern replacement as the audio foundation of global Play/Stop and Record.

**Architecture:** One serialized control producer submits bounded commands to the existing audio engine. The audio owner applies them before scheduling at a render boundary and retains an immutable receipt until acknowledged; the Facade coordinator, not the engine, will own recording and durability. Existing live Pad and saved replay ownership stays separate.

**Tech Stack:** Existing C++20 Core, fixed SPSC storage, custom C++ test executables, CMake/CTest, ASan and TSan. No new dependency.

**Spec:** [Approved global transport design](../specs/2026-09-11-global-pattern-transport-design.md), especially sections 4 and 6. User approved implementation direction on 2026-09-12 after PR #1235; six transitions and restart/no-count-in are settled.

Source baseline: `f1d10ee8fe4aabf8038e3831ee1d0bf424f87dd2`. The transport source paths are unchanged from the spec's audited baseline. Read the actual task baseline again before coding; a merged plan is not evidence its feature remains absent.

Tracking: [#1230](https://github.com/endaye/lmdj/issues/1230), [U2 #1216](https://github.com/endaye/lmdj/issues/1216), [Umbrella #1207](https://github.com/endaye/lmdj/issues/1207). This is the first independently testable subsystem plan, not a replacement for the full [U0–U8 migration](../../plans/2026-09-11-creator-ui-migration.md). Completing these two tasks does not complete any of those Issues.

## Global Constraints

- Every stopped-to-running start begins the current Pattern at its beginning, without count-in.
- Record on/off while playing never restarts playback.
- Ending recording commits/retains events.
- No recording-only steady state or arm-and-wait mode.
- Normal navigation neither changes key duties nor stops transport.
- Sample capture, performance recording and saved replay remain separately named workflows.
- Never allocate, perform IO, wait on a mutex or spin on the audio thread.
- Keep Project Truth authoritative. Prepared Pattern/Runtime Snapshot and transport state are derived/runtime-only, never persisted as Project Truth.
- Journal events still reference Pad Slots. Hosts do not parse bundles or call Core scheduling directly.
- No #725 successful/failed/unknown input outcome change; no second live input subscription.
- Legacy engine publication/start behavior remains the default until a consumer explicitly opts in.
- Preserve fixed Pattern/voice bounds, exact publication claim/cancel ownership, and all existing release/ramp behavior.
- One Task, one reviewable Conventional Commit in an isolated short-lived branch. Do not amend prior commits, lower test thresholds, or treat a named acceptance gap as passed.

## File ownership and dependency map

| Unit | Exact files | Responsibility |
| --- | --- | --- |
| Engine public boundary | `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp` | Explicit opt-in, commands/receipts, publication API; threading contract |
| Engine implementation | `packages/audio-runtime/src/realtime_engine.cpp` | Audio application ordering, scheduler gate, retained ownership |
| Deterministic race seams | `packages/audio-runtime/src/testing_hooks.hpp` | Extend only if existing claim/apply hooks cannot reach a named race |
| Component proofs | `tests/core/audio/realtime_engine_test.cpp` | Actual rendered samples, state/clock, allocation and deterministic race assertions |
| Production concurrency proofs | `tests/core/audio/realtime_engine_stress_test.cpp` | Race production engine; no reliance on test-only hooks |
| Current manual | `apps/docs-site/docs/core/modules/audio-runtime.mdx` | Actual API, opt-in compatibility and ownership facts |
| Source diagram | `apps/docs-site/diagrams/audio-runtime.architecture.json` | Control-command/audio-receipt and retained Pattern ownership |
| Generated diagram | `apps/docs-site/static/diagrams/audio-runtime.html`, `apps/docs-site/static/diagrams/audio-runtime.svg` | Generator-owned renderings of the source diagram |

Both tasks modify the engine and its existing test executables, sequentially. Register every new test function in its executable's `main()`; these are not automatically discovered test cases. No new executable, coverage target, CI lane or required gate is planned. Generated diagram outputs are produced with the existing generator, never hand-edited.

The remainder of #1230 stays explicit:

| Next subsystem | Depends on | Required deliverable before Creator global opt-in |
| --- | --- | --- |
| Durable unresolved admission | Approved spec; audio receipt identity | Project IO bounded durable candidates, terminal reservation, fence decision and atomic/idempotent transfer receipts; native AND real OPFS recovery |
| Facade coordinator | Audio foundation and durable admission | Six transitions, prepared-journal activation, original Pattern clock, short continuation steps, cutoff-relative switch/flush, exact retry and shutdown barrier |
| Runtime/public bridge | Coordinator | Runtime port, asynchronous prepare/flush completions, `pattern.transport.request/inspect`, JS/types/validation, negotiated legacy exclusion |
| Creator adapter | Runtime/public bridge | One global state/actions owner; ordinary navigation continuity; explicit Sample/Performance actions remain separate |
| Hardware Sequence U2 | Above plus U0-approved slice and U1 | Actual two keys, read-only overview, touch editor, recording/overdub/switch/reopen/recovery journey |

Write the next subsystem's executable plan from these delivered interfaces. In particular, synchronous `append_tail` is not unresolved-input staging and synchronous `dispatch` is not an asynchronous continuation. Do not implement fake UI controls while those dependencies are absent. U3–U8 remain as originally scoped.

## Task A1 — Acknowledged Pattern-only transport and cutoff fence

**Files:** Modify the files in the ownership map, including generated diagram outputs. `testing_hooks.hpp` is conditional on a demonstrated missing interleaving; omit it from the commit if unchanged. Version-related files are governed by Version Management below, not an implicit unrelated edit allowance.

**Interfaces (new, to implement):** Add the following public types in `lmdj::audio` and methods to `RealtimeEngine`. Existing publication authority is reused, not replaced.

```cpp
enum class PatternTransportAction : std::uint8_t { start, stop, fence };
enum class PatternTransportSubmit : std::uint8_t {
  accepted, busy, disabled, not_running, stale_generation,
  stale_epoch, identity_mismatch, invalid_action
};
enum class PatternCutoffDecision : std::uint8_t {
  none, applied_before_cutoff, canceled_at_cutoff
};
struct PatternTransportCommand {
  std::uint64_t runtime_generation{};
  std::uint64_t epoch{};
  std::uint64_t expected_pattern_generation{};
  PatternTransportAction action{};
  std::optional<PatternReplacementAuthority> pending_switch;
};
struct PatternTransportReceipt {
  std::uint64_t runtime_generation{};
  std::uint64_t epoch{};
  std::uint64_t effective_frame{};
  std::uint64_t origin_frame{};
  std::uint64_t pattern_generation{};
  foundation::PatternId pattern_id;
  std::uint16_t bpm{};
  bool playing{};
  PatternCutoffDecision switch_decision{};
  std::optional<PatternReplacementAuthority> switch_authority;
  std::optional<std::uint64_t> switch_applied_frame;
};
// Quiescent, before start(); generation must be nonzero.
foundation::Result<void> enable_pattern_transport(std::uint64_t generation);
// Serialized control thread. No synchronous wait for audio application.
PatternTransportSubmit submit_pattern_transport(const PatternTransportCommand&);
std::optional<PatternTransportReceipt> inspect_pattern_transport_receipt(
    std::uint64_t generation, std::uint64_t epoch) const;
// Only after the caller has retained the full receipt for reconciliation.
bool acknowledge_pattern_transport_receipt(
    std::uint64_t generation, std::uint64_t epoch) noexcept;
```

These are public control-side value types. Never send `PatternId`'s string or an allocating `optional<PatternReplacementAuthority>` copy through the audio path. Resolve authority on control into fixed numeric slot/generation fields, retain its identity on control, and name the internal fixed cells `PatternTransportCommandCell` and `PatternTransportReceiptCell`. The receipt must keep the historical Pattern identity even after slot retirement. Add `static_assert(std::is_trivially_copyable_v<PatternTransportCommandCell>)` and `static_assert(std::is_trivially_copyable_v<PatternTransportReceiptCell>)` beside their definitions.

**Bounded protocol:** One outstanding command and one retained receipt per engine is sufficient for the coordinator's busy rule. Use existing fixed SPSC primitives; producer ownership is held from submit until matching receipt acknowledgment. Subsequent submit returns busy, never overwrites an unacknowledged receipt. Epoch starts at 1 and strictly increases; exhausted epoch refuses. Public command-ID dedup belongs to the later coordinator; the engine never interprets a retry as a new toggle. `fence` is valid only while playing and preserves origin; `start` while playing refuses. A stop while already stopped may acknowledge an unchanged stopped state without resetting origin.

**Step 1 — Add a failing component test and register it.** Use existing `pattern_snapshot`, `render_frames`, `LMDJ_CHECK` and `PreparedPatternView::from_snapshot`. This complete test locks the first start frame, not merely command submission:

```cpp
void explicit_pattern_start_uses_acknowledged_origin() {
  using namespace lmdj::audio;
  RealtimeEngine engine;
  LMDJ_CHECK(engine.enable_pattern_transport(7).has_value());
  LMDJ_CHECK(engine.publish_sample_bank(
      PreparedSampleBank::empty(ProjectId{kProjectId}, 1)) == PublishResult::accepted);
  auto view = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 127, 120, 12'000));
  LMDJ_CHECK(view.has_value());
  const auto publication = engine.publish_pattern_view(std::move(view.value()));
  LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  render_frames(engine, 512);
  const PatternTransportCommand start{
      7, 1, publication.generation, PatternTransportAction::start, std::nullopt};
  LMDJ_CHECK(engine.submit_pattern_transport(start) == PatternTransportSubmit::accepted);
  LMDJ_CHECK(!engine.inspect_pattern_transport_receipt(7, 1).has_value());
  std::array<float, 1> left{}, right{};
  engine.render(left.data(), right.data(), 1);
  const auto receipt = engine.inspect_pattern_transport_receipt(7, 1);
  LMDJ_CHECK(receipt.has_value());
  LMDJ_CHECK(receipt->playing);
  LMDJ_CHECK(receipt->effective_frame == 512);
  LMDJ_CHECK(receipt->origin_frame == 512);
  LMDJ_CHECK(receipt->pattern_id == PatternId{kPatternA});
  LMDJ_CHECK(left[0] == 0.0F);  // First attack sample has zero gain.
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] > 0.0F);   // Existing 96-frame attack continues at F+1.
  LMDJ_CHECK(engine.acknowledge_pattern_transport_receipt(7, 1));
}
```

- [ ] Add the function and its `main()` invocation; run the component command below. Initial failure must be the missing new transport behavior/API, not a missing compiler or fixture.
- [ ] Add a separate pre-start rendered-silence assertion and legacy fixture proving non-opted-in callers still auto-schedule after `start()`.

**Step 2 — Implement the bounded handoff and gate.** In `render`, consume at the first effective block boundary before any Pattern scheduling/publication claim for that frame. `start` sets playing, origin=F and cursor=0. `stop` clears playing before scheduling F and releases only validated `pattern_voice` owners, including retired generations, through the existing 96-frame ramp. `fence` records the clock without changing it. Engine running, held live Pads and replay-origin non-Pattern voices remain independent.

```text
control submit: validate mode/generation/epoch/authority -> reserve -> publish POD cell
audio boundary F: resolve exact switch -> apply action -> publish immutable POD receipt
control inspect: acquire receipt -> attach retained identity -> return historical value
control acknowledge: validate exact generation/epoch -> release reservation
```

- [ ] Store explicit Pattern-playing state independently from `RealtimeState`. Quiescent engine restart clears old command channels and starts an opted-in engine Pattern-stopped; it does not auto-replay a prior command. After a quiescent engine stop, require a new nonzero runtime generation through `enable_pattern_transport` before accepting transport again; reject reuse of the prior generation. Do not create a second queue consumer while rendering.
- [ ] Reject mismatched expected identity unless the command's exact named pending switch is the acknowledged successor. Freeze conflicting publication submission while the fence is reserved. Audio-local pending and already-claimed switches still need audio-owner reconciliation.

**Step 3 — Implement cutoff-relative switch authority.** For both stop and fence, a switch applied at S<F is retained; S>=F is canceled/suppressed, including ties. A command arriving after an application takes its actual F, never the earlier requested frame. Receipt includes the exact winning/canceled authority and S when applied. New current-status observations may not overwrite it. Extend existing apply/claim hooks only as needed to deterministically hold the named interleaving; do not use a control cancellation's false result as a decision.

- [ ] Add individual cases for S<F, S=F, S>F, delayed inspection beyond S, stale runtime generation, stale epoch, wrong authority and occupied receipt. Assert applied Pattern, playing, origin and receipt history after each transition.
- [ ] Start -> Stop -> wait -> Start: assert second origin equals second receipt F and the tick-zero event sounds again with no count-in. During playing, fence -> inspect -> acknowledge must retain the first origin.
- [ ] Hold a live loop-gate Pad across Stop, assert it still renders, send its original release and assert bounded completion. Repeat with a replay-origin non-Pattern voice. Separately assert Pattern voices stop after the ramp and no later Pattern events schedule.
- [ ] Extend the existing render allocation test through submit/apply/stop receipt production. Control-side value construction may allocate; the measured render interval may not allocate or deallocate.

**Step 4 — Prove production concurrency.** Extend the existing production-linked stress executable with one control producer and one rendering thread. Race publication, start/fence/stop and reclaim; assert accepted and refused submissions both occur, every accepted epoch yields exactly its receipt, no stale restart, and voices/resources remain valid. Do not add test-only hook dependencies to this executable.

- [ ] Run component, production stress and sanitizer commands below. A TSan startup/platform failure is an unexecuted UB check, not a pass; retain it and use a supported runner before accepting this task.
- [ ] Update current module page/diagram with the opt-in state and acknowledgment ownership; run the documentation check.
- [ ] Inspect declared/staged paths and whitespace, complete version assessment, then commit `feat(audio): add acknowledged Pattern transport fences` and ship through `issue-done` with current-head independent review. Retain #1230 and #1207 as partial relations.

## Task A2 — Phase-preserving overlays and sustained-voice retention

**Dependency:** A1 delivered and verified. **Files:** Same ownership map, sequentially; no unrelated runtime/Creator changes.

**Interfaces:** Keep existing publication methods/signatures/default semantics. Add this method and a named rejection enum value `PatternPublishResult::phase_mismatch`:

```cpp
PatternPublication publish_pattern_view_preserving_phase(
    PreparedPatternView&& pattern,
    std::uint64_t expected_generation) noexcept;
```

Control validates same Project/Pattern identity, BPM, PPQ and loop length against the retained expected publication. While explicitly Pattern-stopped, replacement updates the current view but leaves scheduling disabled. While playing, publish at the first effective render frame, preserve origin, and set the new event cursor to the first not-yet-scheduled event at that frame. Already-past events wait until the next loop; events exactly at the not-yet-scheduled frame run once. Pending switch or reserved transport fence refuses/defer explicitly, not a silent restart.

**Step 1 — Add/register a failing sustained-note test.** Prepare two independent engines from the same `pattern_snapshot`, explicitly start both as in A1, advance both 512 frames, and replace only the test engine with a same-Pattern empty overlay at its current generation. The following comparison is the core assertion; `expected` and `actual` are those two running engines, and `replacement` is the independently prepared same-Pattern view:

```cpp
const auto origin = actual.current_pattern_origin_frame();
const auto generation = actual.pattern_telemetry().current_generation;
const auto publication = actual.publish_pattern_view_preserving_phase(
    std::move(replacement), generation);
LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
std::array<float, 256> expected_left{}, expected_right{}, actual_left{}, actual_right{};
expected.render(expected_left.data(), expected_right.data(), 256);
actual.render(actual_left.data(), actual_right.data(), 256);
LMDJ_CHECK(actual.current_pattern_origin_frame() == origin);
LMDJ_CHECK(actual_left == expected_left);
LMDJ_CHECK(actual_right == expected_right);
LMDJ_CHECK(actual.reclaim_retired_patterns() == 0);
```

- [ ] Run the same component command; confirm failure is the missing phase/voice behavior.
- [ ] Extend the fixture to a nonconstant/ramped sample and compare until its scheduled release. This catches restarted cursors/envelopes that a constant sample could hide. No snapshot material is shared mutably between engines.

**Step 2 — Retain the old voice owner, replace only future scheduling.** Do not execute the old unconditional origin reset or outgoing-voice-stop loop for preserve-phase publication. Keep each sounding voice's slot, generation, sample reference, cursor, envelope and absolute scheduled release. Retire the old Pattern slot but reclaim only after voice AND publication/audio references are gone.

```text
preserve_phase apply:
  validate expected owner and musical identity
  retain origin and all active old-generation voices
  select replacement for future events; position cursor at F
  retire outgoing publication owner without freeing its voices' material
normal completion:
  release voice reference; reclaim only after every owner released
```

- [ ] Add distinct tests for overlay, committed replacement, changed BPM/length/identity rejection, exact-frame event once, past event next loop only, and stopped replacement not enabling playback.
- [ ] Fill the fixed Pattern pool with sustained retired generations; assert `pattern_slots_full`, unchanged samples and scheduler, then allow a note to finish and verify a retry succeeds. No forced voice stealing, forced reclaim or storage growth.
- [ ] Stop after several overlays and verify all retired-generation Pattern voices terminate within the ramp; live Pad/replay voices still survive. True Pattern switch retains existing restart semantics and releases the proper Pattern voices.

**Step 3 — Race replacement against rendering/reclaim and Stop.** Extend production stress with accepted/rejected preserve-phase publications and eventual reclaim. Assert both contention outcomes occur. Keep the existing sample Bank/audition/publication concurrency tests intact. Render allocation proof must also cover phase-preserving application and retired-note completion.

- [ ] Run component, stress, ASan and TSan verification; update the current module page and source diagram, generate outputs and check docs.
- [ ] Inspect the exact staged paths, version assessment and whitespace; commit `feat(audio): preserve Pattern phase and sustained voices on replacement`, then ship via `issue-done`. No Creator global opt-in until the later coordinator/recording dependencies are delivered.

## Commands and evidence

Run from this task's isolated worktree using the supported Unix Core environment (WSL on this Windows machine). Configure once; after each red/green edit rebuild the named targets. These are planned commands, not results:

```bash
bash scripts/core.sh configure dev
cmake --build --preset dev --target lmdj_realtime_engine_tests lmdj_realtime_engine_stress_tests
ctest --preset dev --output-on-failure -R '^audio\.realtime_engine$'
ctest --preset dev --output-on-failure -R '^audio\.realtime_spsc_stress$'

bash scripts/core.sh configure asan
cmake --build --preset asan --target lmdj_realtime_engine_tests lmdj_realtime_engine_stress_tests
ctest --preset asan --output-on-failure -R '^audio\.(realtime_engine|realtime_spsc_stress)$'

bash scripts/core.sh configure tsan
cmake --build --preset tsan --target lmdj_realtime_engine_tests lmdj_realtime_engine_stress_tests
ctest --preset tsan --output-on-failure -R '^audio\.(realtime_engine|realtime_spsc_stress)$'

npm --prefix apps/docs-site run diagrams
bash scripts/docs-site.sh check
git diff --check
```

Core `full` excludes stress. Existing stress tests are already registered/excluded from coverage as appropriate; if a new executable becomes necessary, declare CMake/coverage registration before adding it. No threshold, timeout or selection reduction to obtain green. A plain stress pass cannot substitute for TSan's race detection. These tests prove software samples/ownership, not physical device hearing or touch usability.

## Acceptance coverage and downstream boundary

| Approved spec requirement | Evidence owner |
| --- | --- |
| Start at acknowledged origin / no count-in | A1 component start/restart sample assertions |
| Pattern-only Stop, live Pad and replay retained | A1 separate ownership tests and production stress |
| Fence without restart; cutoff switch before/at/after | A1 historical receipt tests and claim/apply races |
| No audio allocation, blocking or unsafe reclaim | A1/A2 allocation assertions, source review, stress plus sanitizers |
| Preserve origin, event cursor and sustained-note lifetime | A2 reference sample comparison and release/reclaim assertions |
| Fixed-slot exhaustion and stopped replacement | A2 rejection/retry and stopped-scheduler tests |
| Six global key transitions and no duplicate commands | Later Facade/bridge plan; not proven by this engine API |
| Durable bounded candidates, transfer/recovery, Record closure | Later Project IO/Facade plan, including actual OPFS; not fulfilled by audio receipts |
| Global navigation, single input owner, shutdown barrier | Later runtime/Creator plan and browser journeys |
| Four-zone UI, all workspaces, default switch, retirement | Original U0–U8; unchanged and incomplete |

The receipt acknowledgment API transfers retention responsibility; it does not make RAM crash-durable. The coordinator must durably retain an unresolved fence decision before acknowledgment. Runtime loss before that is unresolved recovery, never a guessed successful journal closure. Playback-only operations may acknowledge after consuming the receipt because there is no journal durability claim.

## Version Management

Version impact: none for this planning commit; no manifest, Contract, Product Build or release change.

Implementation affects `audio-runtime`, observed `5.0.0` / API `2` at the baseline. Target identity must be allocated from the then-current active manifests before shipping each Task, not copied from this date or guessed here. Explicitly assess `sizeof(RealtimeEngine)`/public enum/API compatibility: adding private storage may change a public C++ object's ABI, so do not automatically call the change Minor. A source-compatible opt-in addition with no supported ABI break is Minor; a supported ABI/API break requires Major and corresponding API/dependent compatibility updates under the version policy. Record that decision with concrete consumers before commit.

If identities change, declare `packages/audio-runtime/module.json`, exact affected dependent `module.json` files discovered from their current pins and generated Assembly inputs before editing; handle Product Assembly/build allocation through its separate approved version workflow. No hand-edit of `assembly.lock.json`, no guessed Product Build/Channel, no tag, release, deployment or immutable snapshot rewrite. Team-test/release allocation requires the canonical exact-main candidate and matching immutable portal snapshot. Rollback preserves existing immutable identities; ordinary code rollback is a new commit, not history rewriting.

The later Project IO slice must assess its observed `4.1.0` / API `1` storage format separately. Current `lmdj.sequence.journal.v1` checked records and `append_tail` do not provide raw candidates or atomic transfer. Decide a versioned reader/writer compatibility strategy with native and OPFS recovery tests before global opt-in; unknown/new records must not permit an older writer to silently discard unresolved data. This plan neither chooses a new cross-language Contract nor changes #725.

## Documentation Impact

Documentation impact: none for this planning commit; it adds execution instructions and aligns the existing migration dependency, not current implemented portal behavior.

For A1 and A2 implementation: Documentation impact: required.
Affected portal pages: /core/modules/audio-runtime/.
Update `apps/docs-site/docs/core/modules/audio-runtime.mdx` and `apps/docs-site/diagrams/audio-runtime.architecture.json` in each owning Task; generate diagram outputs and run `scripts/docs-site.sh check`.

Downstream plans must declare the actual changed routes: `/core/modules/project-io/`, `/platform/storage/`, `/core/modules/application-facade/`, `/core/modules/web-runtime-platform/`, `/platform/web-runtime/`, `/platform/input/`, `/hosts/creator-web/`, `/product/workflows/`. Existing module diagram sources use the corresponding module name with `.architecture.json`. Do not pre-update them to claim transport implemented.

## Planning-task verification and execution handoff

Declared planning files: this document and `docs/plans/2026-09-11-creator-ui-migration.md` only. Validate source/test registration, spec coverage, proposed type consistency, local links, staged ownership and `docs_static`; no audio/Creator runtime tests are claimed for writing this plan. PR uses partial Issue relations. No new process pitfall was discovered; known concurrency/storage pitfalls shape the listed tests.

Preferred execution: subagent-driven, one task at a time with independent current-diff review. Inline execution remains available. User's approval to continue covers implementation of the approved design; it does not require re-asking the six transport behaviors or convert incomplete U0 device/focus evidence into acceptance.
