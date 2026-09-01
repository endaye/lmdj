# LMDJ Stage 10 Host Runtime and Session Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the locked 23-operation Performance surface actually drivable
end-to-end by production Hosts, so Stage 10 Task 6 (#432) can migrate CLI, MCP
and Native Host honestly: deliver Core-owned runtime authorities (clock, input
sequencer, headless launch transport, replay progression), cross-process flush
identity from Project Truth, read-only recovery queries, a persistent CLI
session mode, and the Native `RealtimeEngine` adapter.

**Design authority:**
[`2026-09-01-lmdj-stage10-host-runtime-session-design.md`](../specs/2026-09-01-lmdj-stage10-host-runtime-session-design.md)
(HRS-D1–D9). Any conflict returns to design review; a Task must not silently
choose a different semantic.

**Architecture:** Task 1 (#523) adds the production authority implementations
and the headless deterministic transport to application-facade, composes them
inside the C API (zero new C symbols), makes completed-flush identity
answerable from Project Truth, and moves Performance recovery reconciliation
off the query path. Task 2 (#524) gives `lmdj-core` a persistent NDJSON
`session` mode and proves the full headless journey plus the cross-process
flush-replay and owner-loss recovery journeys with CLI processes alone. Task 3
(#525) ports the Stage 9 #376 acknowledgement predicate onto
`RealtimeEngine` pattern publication as a Core adapter, owns the frame→tick
conversion, and repairs the Native Host construction order. Hosts never gain
time, order, coalescing, slot-truth or replay semantics of their own
(P10-D21/P10-D22 unchanged).

**Tech Stack:** C++20, nlohmann/json, CMake/CTest, Python 3.11 host tests,
existing integer tick/frame transports, `lmdj_core_c@1` five-symbol C ABI.

## Global Constraints

- New code must not read, write, translate, or emit retired `lmdj.patch.v1`
  or `lmdj.materials.v1` contracts.
- The Locked Facade Surface (23 operation names, kinds, exact request/result
  shapes) does not change. This repair adds no operation and no field.
- Host code (CLI `main.cpp`, MCP Python, Native Host `main.cpp`) may only
  compose and inject Core-provided authorities; it must not compute a tick,
  frame, input sequence, coalescing decision, replay progression step, slot
  truth, Artifact digest trust or recovery fingerprint.
- The three authority ports gain locked contract comments (HRS-D1): musical
  ticks at 3840/bar in 4/4; `read_tick()` monotone non-decreasing; exactly one
  `read_tick()` and one `next()` per successful admission; replayed receipts
  short-circuit before any authority read.
- Every query (`performance.record.status`, `performance.recovery.list`,
  `performance.replay.status`, `performance.list`, `performance.inspect`)
  performs zero disk mutation (HRS-D5).
- Acknowledger outcomes are exactly-once: `drain` must never redeliver an
  outcome, because `Application::drain_performance_launches` durably journals
  each `applied` outcome once and rolls back the whole runtime on append
  failure.
- The `RealtimeEngine` two-thread contract is inviolable: adapters poll from
  the control thread; the render thread gains no new entry point, allocation,
  lock or callback.
- Replay progression is a function of elapsed transport time, never of call
  count; `status` never advances state (HRS-D7, RLC-D8).
- Version impact: no new allocation. Everything is paid by the locked Stage 10
  targets: application-facade `3.0.0`, project-io `2.0.0`, core-cli `3.0.0`,
  native-host `3.0.0`, Product Build `1.0.41.0`. The C ABI stays
  `lmdj_core_c@1` with exactly five exported symbols.
- Documentation impact: none for all three Tasks (no active manifest, Product
  Build or Portal current truth change). Stage 10 Task 10 (#436) owns Portal
  integration; Task 11 (#438) owns the immutable snapshot.
- Never lower a coverage floor. New test executables must be added to the root
  coverage target list.
- Execute each Task on a short-lived `feat/<task>` or `fix/<task>` branch in
  an isolated worktree; one Issue, one Conventional Commit, one PR per Task.

---

### Task 1: Deliver the Core Performance Runtime Bridge and Cross-Process Flush Identity

**Issue:** #523. Hard dependencies: #430, #431 (both merged), and the merged
docs PR carrying this plan.

**Files:**

- Create: `packages/application-facade/include/lmdj/facade/performance_runtime.hpp`
- Create: `packages/application-facade/src/performance_runtime.cpp`
- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/src/c_api.cpp`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Create: `tests/core/facade/performance_runtime_bridge_test.cpp`
- Modify: `tests/core/facade/performance_session_test.cpp`
- Modify: `tests/core/facade/performance_gesture_admission_test.cpp`
- Modify: `tests/core/facade/c_api_test.cpp`
- Modify: `tests/core/project_io/performance_lifecycle_test.cpp`
- Modify: `CMakeLists.txt`

**Interfaces (application-facade public surface, paid by 3.0.0):**

```cpp
// performance_runtime.hpp — Core-owned production authorities (HRS-D1/D2/D7).
class PerformanceTimeSource {
 public:
  virtual ~PerformanceTimeSource() = default;
  // Monotone non-decreasing nanoseconds since an arbitrary epoch.
  virtual std::uint64_t now_ns() = 0;
};

std::shared_ptr<PerformanceTimeSource> make_steady_performance_time_source();

struct PerformanceRuntimeBridge {
  std::shared_ptr<PerformanceClock> clock;
  std::shared_ptr<PerformanceInputSequencer> input_sequencer;
  std::shared_ptr<PatternLaunchAcknowledger> launch_acknowledger;
  std::shared_ptr<PerformanceReplayController> replay_controller;
  // Advances the deterministic transport: acknowledges launch reservations
  // whose target_tick the clock has crossed and drives replay progression by
  // elapsed transport time. Hosts call it before dispatching each request.
  std::function<void()> service;
};

PerformanceRuntimeBridge make_headless_performance_runtime_bridge(
    std::shared_ptr<PerformanceTimeSource> time_source);
```

- `PerformanceClock` (in `application.hpp`) gains
  `virtual void anchor(std::uint16_t bpm, std::uint64_t at_tick) = 0;`
  (HRS-D3). The Facade calls it after a successful
  `performance.record.begin` (draft BPM, current tick) and after a whitelist
  BPM `rebase_complete` becomes visible (new BPM, current tick). Both test
  fakes implement it. All three port classes gain the locked contract
  comments from HRS-D1.
- The headless transport implements `PatternLaunchAcknowledger` exactly as
  HRS-D2: `reserve` returns the requested `earliest_target_tick` with
  `claimed = false`; a later `reserve` before the boundary replaces the
  unclaimed reservation (latest-wins); `service` emits exactly one `applied`
  outcome with `effective_tick == target_tick` when the clock crosses it;
  `cancel` drops the pending reservation; no ghost outcome for a dropped or
  replaced reservation.
- The headless replay path composes `ReferencePerformanceReplayController`
  over a Core-owned silent `PerformanceReplayRuntimeSink`; `service` calls
  the controller's deterministic `advance_to(elapsed_tick)`. Tick mapping
  uses SR-D25 integer-rational anchoring at the projection BPM.

- [ ] **Step 1: Write the bridge RED suite**

In `performance_runtime_bridge_test.cpp`, with a scripted
`PerformanceTimeSource`:

- clock anchoring: `anchor(bpm, at_tick)` then `read_tick()` follows the
  integer-rational SR-D25 mapping; re-anchor at a mid-session BPM change
  leaves already-produced ticks untouched and continues from `at_tick`;
  `read_tick()` is monotone across re-anchors;
- sequencer: strictly increasing from 1, no gaps, no reuse;
- transport: reserve→`{earliest, claimed:false}`; latest-wins replacement
  before crossing; `service` before the boundary emits nothing; `service`
  after crossing emits exactly one `applied` outcome at exactly
  `target_tick`; a second `service` emits nothing (exactly-once); `cancel`
  before crossing yields no outcome ever;
- replay progression: cursor is a function of elapsed time, repeated
  `service` at the same time point does not advance, and `status` never
  advances.

Run the new target; expect FAIL (RED) before implementation.

- [ ] **Step 2: Implement `performance_runtime.hpp/.cpp` and the port comments**

Implement the bridge per **Interfaces**. Add the HRS-D1 contract comments to
`PerformanceClock`, `PerformanceInputSequencer`, `PatternLaunchAcknowledger`
in `application.hpp` and add the `anchor` method. Update both facade test
fakes. Wire the new test executable into facade CMake and the root coverage
list. Run Step 1's suite; expect PASS.

- [ ] **Step 3: Anchor the clock from the Facade (RED then GREEN)**

In `performance_session_test.cpp`, assert the fake clock records exactly one
`anchor(draft_bpm, current_tick)` on successful `record.begin` (none on
replayed begin), and one `anchor(new_bpm, current_tick)` after a BPM
rebase completes. Implement the two call sites in `application.cpp`. Expect
PASS.

- [ ] **Step 4: Write the cross-process flush identity RED suite**

In `performance_lifecycle_test.cpp` (store level) and
`performance_session_test.cpp` (facade level): first Application begins,
admits events, flushes with `command_id` C, saves, and is destroyed (journal
sealed); a second Application on the same workspace issues
`performance.record.flush` with the same `{session_id, command_id C}` and
must receive the original receipt with `replayed: true` and byte-identical
`project.inspect`; same `command_id`/different payload must return the
existing collision error; an unknown identity must return the existing owner
mismatch error. All three leave the Project bytes unchanged.

- [ ] **Step 5: Implement HRS-D4 flush resolution**

In `application.cpp` `performance_flush`, when no in-memory session matches,
resolve the identity before refusing: first against the active journal's
flush records, then against `LoadedProject::performance_flush_identities`
via a new read-only `ProjectStore` lookup that returns the completed flush
receipt for `(session_id, command_id)`. Only an unresolved identity returns
"Performance flush owner does not match". Raw `record.event` and
`launch-request` keep their in-memory-only receipts (HRS-D4): add explicit
witnesses that a second process replaying an `event_id` gets the owner
mismatch refusal, fail closed with zero disk change. Run Step 4's suites;
expect PASS.

- [ ] **Step 6: Make Performance recovery queries read-only (RED then GREEN)**

RED in `performance_lifecycle_test.cpp`: while one store/Facade holds a live
active Performance journal, `performance.recovery.list` and
`performance.record.status` from a second instance report the truthful state
and leave `recovery/active/performance.jsonl` byte-identical; an orphaned
active journal (owner destroyed without sealing, simulated at the store
layer) is sealed `owner_lost` only by the next
`performance.record.begin` / `performance.recovery.apply` /
`performance.recovery.discard` command. Implement by moving the
`reconcile_performance_recovery` sealing off the query path into those
command boundaries in `project_store.cpp`, keeping the sealed-candidate
listing pure. Expect PASS, including every existing recovery fault-matrix
case.

- [ ] **Step 7: Compose the bridge in the C API (RED then GREEN)**

RED in `c_api_test.cpp`: through the five existing symbols only, one engine
completes begin → pad/FX/HOLD events → launch-request → (service via the
next request) → status shows `last_launch_ack` at the reserved bar tick →
flush → stop → save → `performance.replay.begin/status/stop` →
`performance.resample.commit`. Assert no `performance_*_unavailable` reason
appears anywhere. Implement: `lmdj_engine_create` builds
`make_headless_performance_runtime_bridge(make_steady_performance_time_source())`
and passes its members into `ApplicationConfig`; `lmdj_engine_command/query`
invoke `bridge.service()` before dispatch. The config JSON keys, the export
maps and the ABI version stay unchanged. Expect PASS.

- [ ] **Step 8: Run Task 1 full verification**

```bash
scripts/core.sh test dev full
scripts/core.sh coverage check
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
```

Expected: every command PASS; no coverage floor reduction; ABI check
(`mcp_stdio_test.py` `lmdj_core_c@1`) unchanged.

- [ ] **Step 9: Ship Task 1 as one review unit**

Follow `.agents/skills/issue-done/SKILL.md`. Stage only the Task 1 files,
inspect `git diff --cached --check`, then commit:

```bash
git commit -m \
  "feat(facade): deliver the Core Performance runtime bridge (fixes #523)"
```

Push, open the PR with the exact Version/Documentation impact declarations,
wait for required CI, squash-merge, and clean the worktree before Task 2.

---

### Task 2: Add the CLI Persistent Session Mode and Cross-Process Journeys

**Issue:** #524. Hard dependency: merged #523.

**Files:**

- Modify: `apps/core-cli/src/main.cpp`
- Modify: `apps/core-cli/CMakeLists.txt`
- Create: `tests/host/performance_cli_session_test.py`
- Modify: `tests/host/cli_test.py`

**Interfaces:**

- New invocation form (HRS-D8):
  `lmdj-core --workspace W [--assembly A] session` — argc exactly 4 or 6.
  The existing `command`/`query` forms (argc 6 or 8) keep their exact
  behavior and exit codes; the usage line becomes
  `(command|query|session)`.
- Session mode holds one `Application` composed with the Task 1 headless
  bridge, calls `bridge.service()` before each dispatch, reads one strict
  NDJSON request per line from stdin —
  `{"surface": "command"|"query", "request": {…}}`, exact two keys — and
  writes exactly one existing response envelope line to stdout per request.
- A malformed line (over-long, invalid UTF-8, not an object, wrong keys,
  wrong `surface` value) writes one `INVALID_ARGUMENT` envelope and the
  session continues; stdin EOF performs the normal destructor teardown
  (open sessions seal `owner_lost`) and exits 0; an unrecoverable stdout
  write failure exits 2.

- [ ] **Step 1: Write the session-mode RED suite**

In `performance_cli_session_test.py` (registered in core-cli CMake at tier
`host`, following `cli_test.py` conventions and sanitizer timeout scaling):

- framing: each malformed-line case returns one `INVALID_ARGUMENT` envelope
  and the session survives; ordering of responses matches requests;
- full headless journey inside one session process: begin → pad/FX/HOLD
  events → launch-request → status shows the pending reservation and then
  `last_launch_ack` at the reserved bar boundary → flush → stop → save →
  replay begin/status/stop → resample commit; assert no
  `performance_*_unavailable` reason and a real committed revision chain;
- clean EOF: after closing stdin the process exits 0 and a still-open
  recording session is sealed exactly like today's destructor path
  (`recovery/sealed/*-performance-owner_lost.json` exists, no
  `recovery/active/performance.jsonl` remains).

In `cli_test.py`, extend the usage assertions to the new mode string and
add regression witnesses that every existing one-shot invocation (valid,
invalid argc, invalid flag order, exit codes 0/2/64) behaves exactly as
before.

- [ ] **Step 2: Implement session mode**

Extend `Mode` with `session`, `parse_invocation` with the argc-4/6 form, and
add the line loop: bounded line length (16 MiB request bound reused), strict
UTF-8 and two-key object validation, `bridge.service()` before dispatch,
one flushed response line per request, `SIGPIPE` ignored as today. One-shot
paths share the same `Application` construction (now injecting the Task 1
bridge instead of nullptr authorities) so a single-request
`performance.record.status`/`performance.recovery.*`/flush-replay behaves
identically in both modes. Run Step 1's suite; expect PASS.

- [ ] **Step 3: Write and pass the cross-process journeys (RED then GREEN)**

Extend `performance_cli_session_test.py` with two CLI-only journeys:

- **flush replay:** session process A begins/events/flushes (`command_id` C)
  and saves, then exits cleanly; one-shot process B replays flush C and
  asserts `replayed: true`, one revision, and byte-identical
  `project.inspect` before/after;
- **owner loss:** session process A begins and admits events, is killed
  (SIGKILL) before stop; one-shot process B observes
  `performance.record.status`, seals via the Step 6 command-boundary
  reconciliation on `performance.recovery.apply`, applies, and asserts the
  complete far side (revision, Performance events, receipts); a second run
  discards instead and asserts zero Project change.

Expect PASS.

- [ ] **Step 4: Run Task 2 full verification**

```bash
scripts/core.sh test dev full
scripts/core.sh coverage check
scripts/architecture-portal.sh check
```

Expected: PASS, including the unchanged one-shot `host.cli` suite.

- [ ] **Step 5: Ship Task 2 as one review unit**

Follow `.agents/skills/issue-done/SKILL.md`. Stage only the Task 2 files,
then commit:

```bash
git commit -m \
  "feat(core-cli): add the persistent NDJSON session mode (fixes #524)"
```

Push, open the PR, wait for CI, squash-merge, clean the worktree.

---

### Task 3: Add the Native Host Performance Runtime Adapter

**Issue:** #525. Hard dependency: merged #523.

**Files:**

- Create: `packages/application-facade/include/lmdj/facade/performance_engine_adapter.hpp`
- Create: `packages/application-facade/src/performance_engine_adapter.cpp`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `apps/native-host/src/main.cpp`
- Create: `tests/core/facade/performance_engine_adapter_test.cpp`
- Modify: `tests/host/native_host_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

```cpp
// performance_engine_adapter.hpp — Core adapter over a RealtimeEngine
// (HRS-D9). Control-thread only; render gains no new entry point.
struct EnginePerformanceAdapter {
  std::shared_ptr<PerformanceClock> clock;            // rendered_frames → tick
  std::shared_ptr<PerformanceInputSequencer> input_sequencer;
  std::shared_ptr<PatternLaunchAcknowledger> launch_acknowledger;
  std::shared_ptr<PerformanceReplayController> replay_controller;
  std::function<void()> service;                      // control-thread poll
};

EnginePerformanceAdapter make_engine_performance_adapter(
    audio::RealtimeEngine& engine,
    PatternPublicationGateway gateway);
```

- The clock converts `engine.telemetry().rendered_frames` to ticks with
  SR-D25 integer-rational anchoring at 48 kHz, re-anchored through the same
  `anchor(bpm, at_tick)` notification as Task 1.
- `PatternPublicationGateway` is the adapter's only way to publish: it wraps
  `PreparedPatternView` preparation, `engine.publish_pattern_view(view,
  activation_frame, replacement_authority)` and
  `cancel_pattern_publication`, so the acknowledger controls latest-wins
  replacement and claimed-defer without the Host choosing anything.
- `reserve` publishes at the frame of the requested bar tick and returns
  `{target_tick, claimed}` from the publication result; a later request
  before the render thread claims the boundary replaces it (latest-wins); a
  claimed boundary defers the new request to the following bar.
- `service` ports the #376 predicate:
  `pattern_telemetry().current_generation == reserved generation` **and**
  `telemetry().rendered_frames >= activation_frame`, with an exactly-once
  notified latch per reservation; only that produces an `applied` outcome at
  the reserved tick. Failed, superseded and cancelled publications produce
  `cancelled`/`failed` outcomes and never an `applied` one (no ghost event).
- The replay controller composes `ReferencePerformanceReplayController` over
  an engine-backed `PerformanceReplayRuntimeSink` (pad hits →
  existing trigger path, pattern launches → the same publication gateway,
  FX gestures → the Stage 10 FX chain entry points, `reset_neutral` →
  neutral FX/HOLD state); progression is driven by `service` from
  rendered-frame time.
- Native Host wiring: construct the `RealtimeEngine` before the
  `Application` (hoist), build the adapter, inject its members into
  `ApplicationConfig`, and call `adapter.service()` inside the existing
  per-request `drain_trigger_outcomes_once` wrapper. The Host's own protocol
  surface does not change in this Task; registering the 23 operations stays
  in Task 6 (#432).

- [ ] **Step 1: Write the adapter RED suite**

In `performance_engine_adapter_test.cpp`, drive a real `RealtimeEngine`
deterministically from the test thread (`render` in 128-frame blocks, the
`--no-device` pattern): reserve at the next bar and assert the returned
`target_tick`/`claimed`; render across the boundary and assert `service`
emits exactly one `applied` outcome whose `effective_tick` equals the
reserved bar tick under the frame→tick anchor; latest-wins before claim;
claimed-defer to the following bar; cancel and publication failure produce
no `applied` outcome; clock monotonicity across BPM re-anchor; replay
begin→progression→natural end with neutral reset against the engine-backed
sink. Expect FAIL (RED).

- [ ] **Step 2: Implement the adapter**

Implement `performance_engine_adapter.hpp/.cpp` per **Interfaces**, reusing
the web runtime's ack predicate shape (`drain_sequence_bar_boundary`) and
respecting the engine's two-thread contract (control-thread polling only,
no callback, no allocation on the render path). Wire CMake and the root
coverage list. Run Step 1's suite; expect PASS.

- [ ] **Step 3: Repair the Native Host construction order and inject (RED then GREEN)**

RED in `native_host_test.py`: startup with the adapter injected must keep
every existing host protocol behavior (sample.quota, trigger, record.begin/
stop, status, start/stop, quit) byte-compatible, and a
`performance.record.status` issued through a one-shot CLI observer against
the same workspace must show the host process's Performance surface healthy
(no `performance_*_unavailable`). Implement: hoist the engine ahead of the
`Application`, build the adapter, inject, and service it in the existing
request wrapper. Expect PASS.

- [ ] **Step 4: Run Task 3 full verification**

```bash
scripts/core.sh test dev full
scripts/core.sh coverage check
scripts/architecture-portal.sh check
```

Expected: PASS, including `host.native` and the facade/audio stress guards
unchanged. Changing lock-free or concurrent engine interaction requires an
explicit `scripts/core.sh test dev stress` run before shipping.

- [ ] **Step 5: Ship Task 3 as one review unit**

Follow `.agents/skills/issue-done/SKILL.md`. Stage only the Task 3 files,
then commit:

```bash
git commit -m \
  "feat(native-host): connect the Performance runtime adapter (fixes #525)"
```

Push, open the PR, wait for CI (including both ASAN/stress lanes),
squash-merge, clean the worktree. Only then may Stage 10 Task 6 (#432)
begin.

## Version Management

Version impact: no new allocation.

All three Tasks land before Stage 10 Task 10 enables the v4 writer and
publishes module versions. They consume the already locked targets:

- application-facade `3.0.0` (bridge/adapter headers, port contract
  comments, `anchor` method);
- project-io `2.0.0` (recovery reconciliation boundary move, flush identity
  lookup);
- core-cli `3.0.0` (session mode);
- native-host `3.0.0` (construction order and adapter wiring);
- C ABI unchanged at `lmdj_core_c@1` with exactly five symbols;
- Product Build `1.0.41.0`.

Before #436 allocates or publishes identities, rerun its fresh allocation
audit. If any identity has become occupied, stop and refresh the Stage 10
allocation rather than changing it inside #523, #524 or #525.

## Documentation Impact

Documentation impact: none for #523, #524 and #525.

None of the Tasks changes active manifests, Assembly, Product Build, or
Portal current pages. Stage 10 Task 10 (#436) must declare the required
Portal routes and source diagrams in its own PR, and Task 11 (#438) freezes
the immutable snapshot.

## Execution Order

```text
docs PR (this design + plan + Stage 10 plan/spec revision)
  -> Issue #523 isolated worktree / one commit / PR / merge / cleanup
  -> Issue #524 one commit / PR / merge / cleanup   (needs #523)
  -> Issue #525 one commit / PR / merge / cleanup   (needs #523)
  -> Stage 10 Task 6 (#432) — CLI/MCP/Native migration and cross-Host journeys
```

#524 and #525 touch disjoint primary files and may run in parallel worktrees
after #523 merges. Task 6 (#432) requires all three merged.
