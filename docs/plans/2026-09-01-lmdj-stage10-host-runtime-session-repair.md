# LMDJ Stage 10 Host Runtime and Session Repair Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the locked 23-operation Performance surface actually drivable
end-to-end by production Hosts, so Stage 10 Task 6 (#432) can migrate CLI, MCP
and Native Host honestly: deliver Core-owned runtime authorities (clock, input
sequencer, headless launch transport, replay progression), cross-process flush
identity from Project Truth, read-only recovery queries, a persistent CLI
session mode, the Native `RealtimeEngine` adapter, and crash-durable transient
closure before recovery or re-attach, plus an explicit launch-outcome service
mutation that keeps status read-only.

**Design authority:**
[`2026-09-01-lmdj-stage10-host-runtime-session-design.md`](../design/2026-09-01-lmdj-stage10-host-runtime-session-design.md)
(HRS-D1–D11). Any conflict returns to design review; a Task must not silently
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
(P10-D21/P10-D22 unchanged). Task 4 (#570) repairs the Task 6 RED exposed by
hard owner loss: raw admission durably checkpoints non-Project-Truth transient
state before acknowledgement, and Core closes that checkpoint exactly once
after owner-death proof.
Task 5 (#571) removes launch-outcome draining from status and introduces a
two-phase Core service mutation used at command/control-loop boundaries.

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
- Every accepted raw Performance event, including a Pad press that produces no
  canonical event yet, durably appends its post-admission transient checkpoint
  before acknowledgement. The checkpoint is Runtime metadata only; no raw
  event or gesture identity enters Project Truth (HRS-D10).
- Acknowledger outcomes are exactly-once under the HRS-D11 two-phase protocol:
  `peek` retains each outcome until Application has established its durable
  consequence and `commit` removes that exact request identity. A definitive
  append failure leaves it retryable; an ambiguous tail result freezes the
  session under HRS-D10.
- The `RealtimeEngine` two-thread contract is inviolable: adapters poll from
  the control thread; the render thread gains no new entry point, allocation,
  lock or callback.
- Replay progression is a function of elapsed transport time, never of call
  count; `status` never advances state (HRS-D7, RLC-D8).
- Version impact: no new allocation. Everything is paid by the locked Stage 10
  targets: application-facade `3.0.0`, project-io `2.0.0`, core-cli `3.0.0`,
  native-host `3.0.0`, Product Build `1.0.42.0`. The C ABI stays
  `lmdj_core_c@1` with exactly five exported symbols.
- Documentation impact: none for all five Tasks (no active manifest, Product
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
- Modify: `packages/project-io/src/sequence_journal.cpp`
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
  (HRS-D3). The Facade calls it exactly once per **in-process session
  attach**: a fresh `performance.record.begin` anchors at (draft BPM,
  current tick); a journal re-attach anchors at (journal `created_bpm`,
  maximum durable event tick in the journal, 0 when none) and additionally
  seeds the input sequencer from the journal's `last_input_sequence`. A
  replayed begin against an already-attached in-memory runtime neither
  re-anchors nor consumes authority reads. A whitelist BPM
  `rebase_complete` re-anchors at (new BPM, current tick). Both test fakes
  implement it. All three port classes gain the locked contract comments
  from HRS-D1.
- `PatternLaunchAcknowledger::reserve` gains a trailing
  `std::shared_ptr<const cooker::RuntimeSnapshot> resolved_pattern`
  parameter (HRS-D9): the Facade resolves `pattern_slot` → occupying
  PatternId → immutable cooked material at the session's current revision
  during launch admission and passes it (null for an empty slot). The
  headless transport ignores the material; both test fakes record it. No
  Host code resolves slots or parses Project Truth.
- Sealing an active Performance journal as `owner_lost` at a command
  boundary (`performance.record.begin` / `performance.recovery.apply` /
  `performance.recovery.discard`) first takes a **non-blocking exclusive
  advisory flock** on the session's lock file under `recovery/active/`
  (HRS-D5). The owning process holds that lock from attach until seal; a
  held lock returns the existing `recording_session_active` typed refusal
  with zero disk change; a crash releases it automatically. The lock file
  is runtime metadata, never Project Truth, and is removed with the active
  journal at seal.
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

- [ ] **Step 3: Anchor and seed per in-process attach (RED then GREEN)**

In `performance_session_test.cpp`, assert per HRS-D3:

- a fresh successful `record.begin` records exactly one
  `anchor(draft_bpm, current_tick)`;
- a replayed begin against the already-attached in-memory runtime records
  no further anchor and consumes no `read_tick()`/`next()`;
- a journal re-attach (destroy the first Application with the journal kept
  alive at the store layer, then replay the exact original begin in a
  second Application) records exactly one
  `anchor(created_bpm, max_durable_event_tick)`, seeds the sequencer so its
  next value is `last_input_sequence + 1`, and subsequently admitted events
  never receive a tick below the journal's maximum durable tick or a
  repeated input sequence;
- a BPM `rebase_complete` records one `anchor(new_bpm, current_tick)`.

Implement the call sites in `application.cpp`. Expect PASS.

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

- [ ] **Step 6: Make recovery queries read-only and gate orphan sealing on the owner lock (RED then GREEN)**

RED in `performance_lifecycle_test.cpp`: while one store/Facade holds a live
active Performance journal, `performance.recovery.list` and
`performance.record.status` from a second instance report the truthful state
and leave `recovery/active/performance.jsonl` byte-identical. Orphan sealing
is command-boundary-only and lock-gated (HRS-D5):

- while the owner lock is held (hold it from a helper process so the lock is
  a genuine cross-process witness), a second instance's
  `performance.record.begin` (different session) /
  `performance.recovery.apply` / `performance.recovery.discard` returns the
  existing `recording_session_active` refusal with zero disk change;
- after the lock holder is killed (SIGKILL — the kernel releases the lock),
  the same command seals the journal `owner_lost` and proceeds;
- the owning instance acquires the lock at attach (fresh begin and
  re-attach), and seal removes the lock file with the active journal.

Implement by moving the `reconcile_performance_recovery` sealing off the
query path into those command boundaries in `project_store.cpp` /
`sequence_journal.cpp`, adding the advisory-flock owner lock, and keeping
the sealed-candidate listing pure. Expect PASS, including every existing
recovery fault-matrix case.

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
  (SIGKILL) before stop — the kernel releases A's owner lock, which is what
  lets B treat the journal as orphaned (HRS-D5); one-shot process B observes
  `performance.record.status`, seals via the Step 6 command-boundary
  reconciliation on `performance.recovery.apply`, applies, and asserts the
  complete far side (revision, Performance events, receipts); a second run
  discards instead and asserts zero Project change. Additionally, while A is
  still alive, B's `performance.recovery.apply` returns
  `recording_session_active` with zero disk change.

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
- Modify: `packages/application-facade/include/lmdj/facade/performance_replay.hpp`
- Modify: `packages/application-facade/src/performance_replay.cpp`
- Modify: `packages/application-facade/src/performance_runtime.cpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/src/prepared_sample_bank.cpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `apps/native-host/src/main.cpp`
- Create: `tests/core/facade/performance_engine_adapter_test.cpp`
- Modify: `tests/core/facade/performance_replay_test.cpp`
- Modify: `tests/core/facade/performance_runtime_bridge_test.cpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/audio/realtime_engine_test.cpp`
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

enum class NeutralResetProgress : std::uint8_t {
  pending,
  complete,
};

// PerformanceReplayRuntimeSink contract:
virtual foundation::Result<NeutralResetProgress> reset_neutral() = 0;

enum class PadControlOrigin : std::uint8_t {
  host_input,
  performance_replay,
};

// prepared_sample_bank.hpp — one trivially-copyable material view used by
// direct replay Pad events and prepared Pattern events.
struct PreparedSampleMaterialView {
  const std::int16_t* interleaved{};
  std::uint32_t frame_count{};
  std::uint16_t channels{};
};

// Trailing PadControlEvent fields; existing aggregate callers retain the
// host_input / zero-duration / empty-material defaults.
PadControlOrigin origin{PadControlOrigin::host_input};
std::uint64_t duration_frames{};
PreparedSampleMaterialView material{};
```

- The clock converts `engine.telemetry().rendered_frames` to ticks with
  SR-D25 integer-rational anchoring at 48 kHz, re-anchored through the same
  `anchor(bpm, at_tick)` notification as Task 1.
- `PatternPublicationGateway` is the adapter's only way to publish. It
  receives the immutable `cooker::RuntimeSnapshot` that the Facade resolved
  and passed through `reserve` (HRS-D9), converts it to a
  `PreparedPatternView`, and wraps `engine.publish_pattern_view(view,
  activation_frame, replacement_authority)` and
  `cancel_pattern_publication`. It never resolves a slot, never touches
  Project Truth, and the acknowledger controls latest-wins replacement and
  claimed-defer without the Host choosing anything.
- `reserve` publishes the Core-resolved material at the frame of the
  requested bar tick and returns `{target_tick, claimed}` from the
  publication result; a later request before the render thread claims the
  boundary replaces it (latest-wins); a claimed boundary defers the new
  request to the following bar. An empty-slot reserve (null material)
  publishes nothing: `service` acknowledges it at the boundary as `applied`
  without changing what is playing (#488 §5).
- A failed cancellation means the prior reservation was claimed, not
  cancelled. Keep that reservation until its original #376 predicate emits
  exactly one `applied`; retain the new reservation separately at the
  following Bar. Per-session storage is ordered and may therefore contain a
  claimed predecessor plus one replaceable, not-yet-claimed successor.
- `service` ports the #376 predicate:
  `pattern_telemetry().current_generation == reserved generation` **and**
  `telemetry().rendered_frames >= activation_frame`, with an exactly-once
  notified latch per reservation; only that produces an `applied` outcome at
  the reserved tick. Failed, superseded and cancelled publications produce
  `cancelled`/`failed` outcomes and never an `applied` one (no ghost event).
- The replay controller composes `ReferencePerformanceReplayController` over
  an engine-backed `PerformanceReplayRuntimeSink`. Pad hits use the existing
  `enqueue_control` / Voice render path with `performance_replay` origin and
  an SR-D25 integer `duration_frames` plus the projection's immutable
  `PreparedSampleMaterialView`; render derives the release from the actual
  Voice start frame and the existing scheduled-release latch. Render consumes
  that PCM16 view with the same conversion/stereo averaging as
  `PreparedSampleBank`, never late-resolves through the current live bank.
  Replay origin never enters live trigger outcomes, voice-state outcomes or
  Capture. An empty material on a live `host_input` event keeps the existing
  float-bank path byte-compatible. Pattern launches use the same publication
  gateway, and every `PreparedPatternEvent` carries the same material view;
  FX gestures use the Stage 10 FX chain entry points.
- `PreparedPatternView::prepare` owns deduplicated
  `shared_ptr<const PcmSample>` values from the immutable Runtime Snapshot.
  Pattern slots track `active_voices` and a `retiring` state so replacement or
  reclaim cannot invalidate old material until natural completion, scheduled
  release tails and hard kills have all decremented the count. The adapter
  retains deduplicated direct-replay material owners until engine
  stop/quiescence and adapter destruction; a later replay or live bank reload
  cannot clear or replace owners that queued/active Voices may still read. No
  shared ownership, allocation, lock or callback crosses the render queue.
- `reset_neutral` returns `pending` until render has dequeued the one logical
  `hold_off + 8 release` reset, using `MasterFxTelemetry` as the completion
  witness; queue-pressure continuation must not duplicate gestures. Reference
  controller state retains identity/ownership while pending. Natural-end
  progression polls an accepted pending reset, `status` remains read-only,
  and true reset failures are retried only by `stop` as locked by RLC-D9. An
  empty replay begin creates the identity and returns `playing` while its
  reset is pending instead of erasing the replay.
- The existing headless `SilentPerformanceReplayRuntimeSink` adopts the same
  tri-state interface and returns `complete` immediately because it owns no
  audible Runtime state or render queue. Keep a focused
  `performance_runtime_bridge_test` witness so this product implementation is
  not covered only by compilation while the engine-backed sink exercises
  `pending`.
- Facade stop writes `replay_stop_receipts` only for `complete`/`stopped`.
  A `pending` poll returns the current `playing` response with
  `replayed:false` but does not consume `request_id`, so the same request ID
  reaches the controller again; a true reset failure likewise writes no
  receipt. For an empty replay whose begin-time reset truly fails, Facade
  retains the controller-created identity/active exclusion before returning
  the stable error, so an exact begin retry can observe `playing` and `stop`
  can perform the locked retry.
- `EnginePerformanceAdapter::service` remains the locked `void` composition
  surface. An `advance_to` failure must leave the controller-owned reset
  target, frozen cursor and active latch intact; periodic service does not
  retry a true failure or clear the replay. The externally visible recovery
  surface remains read-only `status` plus `stop`, with no Host-specific error
  field or process-fatal side channel.
- Native Host wiring: construct the `RealtimeEngine` before the
  `Application` (hoist), build the adapter, inject its members into
  `ApplicationConfig`, and call `adapter.service()` both inside the existing
  per-request `drain_trigger_outcomes_once` wrapper **and on the Host's
  existing periodic control-loop tick** (HRS-D7): a host with a live audio
  runtime must keep replay sink application and launch outcomes tracking the
  actual boundaries even when no request arrives. The periodic call runs on
  the control thread under `facade_mutex_`; the render thread gains nothing.
  The Host's own protocol surface does not change in this Task; registering
  the 23 operations stays in Task 6 (#432).

- [ ] **Step 1: Write the adapter RED suite**

In `performance_engine_adapter_test.cpp`, drive a real `RealtimeEngine`
deterministically from the test thread (`render` in 128-frame blocks, the
`--no-device` pattern): reserve at the next bar and assert the returned
`target_tick`/`claimed`; render across the boundary and assert `service`
emits exactly one `applied` outcome whose `effective_tick` equals the
reserved bar tick under the frame→tick anchor; latest-wins before claim;
claimed-defer to the following bar while the claimed predecessor still emits
one `applied` at its original target; a third request replaces only the
unclaimed deferred successor; an empty-slot reserve (null material)
publishes nothing yet is acknowledged `applied` at the boundary with the
playing content unchanged; cancel and publication failure produce
no `applied` outcome; clock monotonicity across BPM re-anchor; replay
begin→progression→natural end with neutral reset against the engine-backed
sink, where progression is driven purely by rendering plus periodic
`service` calls with no interleaved Facade requests. The replay witness must
use a non-one-shot Pad and prove `duration_tick` becomes an exact relative
render-frame release, produces no live outcome/capture event, remains
`playing` after reset enqueue, and becomes terminal only after render dequeues
the final reset gesture. After enqueueing that direct replay Pad, publish a
different live sample bank before render and prove the Voice still renders the
projection's old PCM. For Pattern replay, publish material from projection R,
replace/reload the live bank and Pattern slot, then prove the replay uses R's
PCM and that an old Pattern Voice release tail survives replacement/reclaim
attempts until its final frame. Also cover partial reset enqueue continuation
without duplicates; pending stop calls must not create a receipt, and the same
request ID must poll again until terminal before later replaying the receipt.
Cover an empty replay retaining its identity while reset is pending and after
a true begin-time reset error. In `performance_runtime_bridge_test.cpp`,
update the headless replay witness to prove the silent sink still
completes/reset-closes without an artificial pending cycle under the tri-state
contract. Expect FAIL (RED).

- [ ] **Step 2: Implement the adapter**

Implement `performance_engine_adapter.hpp/.cpp` per **Interfaces**, reusing
the web runtime's ack predicate shape (`drain_sequence_bar_boundary`) and
respecting the engine's two-thread contract (control-thread polling only,
no callback, no allocation on the render path). Extend the existing
`PadControlEvent` queue entry only with the locked trailing
origin/duration/material fields, and reuse the current Voice
`scheduled_release_frame`; do not add a second render queue or a Host timer.
Teach `PreparedPatternView` to retain deduplicated PCM owners and the engine to
retire Pattern material only after its active Voice count reaches zero. Reuse
the existing PCM16 conversion exactly, including stereo averaging. Ensure
natural completion, scheduled release and hard kill all release the Pattern
Voice reference, while engine stop/quiescence precedes adapter owner
destruction. Repair the reference controller's tri-state reset handling and
zero-event identity retention. Wire CMake and the root coverage list. Run Step
1's suite; expect PASS.

- [ ] **Step 3: Repair the Native Host construction order and inject (RED then GREEN)**

RED in `native_host_test.py`: startup with the adapter injected must keep
every existing host protocol behavior (sample.quota, trigger, record.begin/
stop, status, start/stop, quit) byte-compatible, and a
`performance.record.status` issued through a one-shot CLI observer against
the same workspace must show the host process's Performance surface healthy
(no `performance_*_unavailable`). Implement: hoist the engine ahead of the
`Application`, build the adapter, inject, and service it in the existing
request wrapper plus the periodic control-loop tick (HRS-D7). Expect PASS.

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

### Task 4: Make Hard Owner-Loss Transient Closure Durable

**Issue:** #570. Hard dependencies: merged #523; execute after the docs PR
carrying HRS-D10 and this Task. It blocks #432 independently of #524/#525.

**Files:**

- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/core/project_io/performance_journal_test.cpp`
- Modify: `tests/core/project_io/performance_lifecycle_test.cpp`
- Modify: `tests/core/facade/performance_session_test.cpp`
- Modify: `tests/core/facade/performance_gesture_admission_test.cpp`

**Interfaces and durability model:**

- Add a typed Performance transient checkpoint to the active journal. It holds
  sorted open Pad records `(gesture_id, slot, onset_tick, velocity)`, per-FX
  open state, HOLD, and `last_accepted_tick`. It is Runtime metadata and must
  never appear in Project Truth, Performance JSON, a flush identity, or a
  Runtime Snapshot.
- Expose one pure closure preview used by the journal mutation and read-only
  Facade projections. Cross-process `record.status` reports checkpoint-backed
  open Pad/FX/HOLD state, while `recovery.list.pending_event_count` includes
  the canonical closure that apply would commit; neither query acquires the
  owner lock or changes disk.
- Extend the existing checksummed Performance tail record so one append stores
  the complete canonical pending-event snapshot, complete post-event transient
  checkpoint, and `input_sequence`. An empty event snapshot is valid only when
  it accompanies a valid checkpoint transition, so `pad_press` is durable
  before its acknowledgement.
- A tail append error is potentially post-write. Resolve exact read-back plus
  one bounded exact retry inside the journal operation; if durable success is
  still unknowable, return `performance_tail_outcome_unknown`, freeze the
  in-process session as `recovery_required`, and reject later event/flush/stop
  so stale memory cannot overwrite the durable prefix. Owner teardown then
  leaves explicit recovery to apply/discard instead of appending from memory.
- Add one Project I/O owner-loss closure operation used only after the caller
  holds the HRS-D5 owner-death lock. It computes
  `closure_tick = max(last_accepted_tick, max_durable_event_tick) + 1`, refuses
  tick or input-sequence overflow, appends Pad closures ordered by
  `(slot, gesture_id)`, FX releases
  in chain order after pending moves, then `hold_off`, and atomically records a
  neutral checkpoint with the next input sequence. A neutral checkpoint is an
  idempotent no-op, so crash-after-close/before-seal retry cannot duplicate an
  event.
- Publish a Performance sealed candidate under stable session identity. An
  exact existing candidate makes seal replay finish only active-file removal;
  a same-session/different-digest candidate fails closed and retains both
  witnesses. Never create a suffixed second candidate after a
  candidate-publication/active-remove crash gap.
- `reconcile_performance_recovery()` closes before `owner_lost` seal. Exact
  begin replay in a fresh process also proves the previous owner dead, closes
  the checkpoint in place, then attaches a neutral runtime to the preserved
  canonical tail. An already-attached in-process begin replay remains a pure
  short circuit; a live foreign flock remains `recording_session_active` with
  byte-identical disk state.
- Fresh-process exact re-attach retains the same acquired flock continuously
  through closure and insertion into the ProjectStore retained-owner map. A
  two-process race has one winner; the loser is `recording_session_active`.
- Missing-checkpoint legacy migration is allowed only for a validated stopped
  journal. Active, recovery-required, or owner-lost legacy state is retained
  fail-closed even when its canonical pending list is empty.
- The Facade persists the post-admission checkpoint before returning every raw
  event acknowledgement. A definitive pre-write failure may roll back; an
  ambiguous failure freezes the session and never permits a later stale
  snapshot. Event receipts and unacknowledged launch reservations remain
  process-local; owner loss cancels the latter with no ghost event.

- [ ] **Step 1: Write Project I/O journal REDs.** Cover round-trip/checksum and
  strict shape validation for neutral/open Pad/open FX/HOLD checkpoints; an
  empty canonical event snapshot with a checkpoint transition; malformed,
  torn, non-monotone sequence, tick/input-sequence overflow, and active legacy
  missing-checkpoint retention. Expect FAIL.
- [ ] **Step 2: Implement typed checkpoint persistence.** Update the active
  journal reader/writer and append validation. Keep legacy active journals
  readable only when they are validated and stopped; otherwise fail closed
  rather than guessing an open Pad. Run Step 1; expect PASS.
- [ ] **Step 3: Write closure and command-boundary REDs.** In Project I/O,
  leave Pad/FX/HOLD open, release the helper process by SIGKILL, and assert
  status/list truthfully preview open state and closure count while remaining
  byte-identical; apply closes and commits exactly one revision;
  discard removes the candidate with zero Project mutation; retry after a
  simulated close-append/seal gap adds no duplicate. Inject the post-write
  `active_journal_sync` failure and prove the session freezes instead of
  allowing a stale next snapshot. Cover live-lock refusal, stable candidate
  replay after publication/remove failure, and two re-attach contenders.
  Expect FAIL.
- [ ] **Step 4: Implement Core closure.** Close only after owner-death proof,
  before seal or fresh-process exact re-attach. Reuse canonical event ordering
  and the active journal append protocol; do not synthesize Host time, expose
  checkpoint fields through Facade schemas, or alter the 23-operation surface.
- [ ] **Step 5: Write Facade admission/re-attach REDs, then GREEN.** Prove each
  accepted raw union member durably advances the checkpoint before response;
  a pre-write rejection is not accepted, while ambiguous post-write failure
  returns the stable recovery-required error and cannot be overwritten; exact
  begin after SIGKILL closes the old checkpoint once, anchors at the neutral
  checkpoint's `last_accepted_tick`/durable temporal high-water mark after that
  closure (including Pad `onset_tick + duration_tick`), seeds the next input
  sequence,
  and starts neutral without rehydrating gesture ownership or
  releasing/reacquiring the flock. Prove no raw IDs occur in inspect/save/
  replay output.
- [ ] **Step 6: Run complete verification.** Run
  `scripts/core.sh test dev full`, `scripts/core.sh coverage check`,
  `scripts/core.sh test dev stress`, and
  `scripts/architecture-portal.sh check`. Never lower a floor.
- [ ] **Step 7: Ship one review unit.** Follow `issue-done`, stage only the
  files above, and commit
  `fix(facade): preserve Performance transients across owner loss (fixes #570)`.
  Push, queue, squash-merge, verify exact merged-main CI, and clean only this
  worktree/branch. Then resume #432 from its retained RED.

### Task 5: Separate Read-Only Status From Launch-Outcome Service Mutation

**Issue:** #571. Hard dependencies: merged #523, #525 and #570 plus the docs PR
carrying HRS-D11. It blocks both #432 and #433.

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/include/lmdj/facade/performance_engine_adapter.hpp`
- Modify: `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- Modify: `packages/project-io/src/sequence_journal.cpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/src/c_api.cpp`
- Modify: `packages/application-facade/src/performance_runtime.cpp`
- Modify: `packages/application-facade/src/performance_engine_adapter.cpp`
- Modify: `apps/core-cli/src/main.cpp`
- Modify: `apps/native-host/src/main.cpp`
- Modify: `tests/core/facade/performance_runtime_bridge_test.cpp`
- Modify: `tests/core/facade/performance_engine_adapter_test.cpp`
- Modify: `tests/core/facade/performance_gesture_admission_test.cpp`
- Modify: `tests/core/facade/c_api_test.cpp`
- Modify: `tests/core/project_io/performance_journal_test.cpp`
- Modify: `tests/host/performance_cli_session_test.py`
- Modify: `tests/host/native_host_test.py`

**Interfaces:**

- Replace destructive `PatternLaunchAcknowledger::drain(session)` with a
  two-phase Core protocol: `peek(session)` returns ordered uncommitted outcomes
  without removal; `commit(session, request_id)` removes exactly that outcome
  after its durable consequence is established. Headless and engine adapters
  retain outcomes until commit and never redeliver afterward.
- Application processes only the ordered front outcome for a session: one
  applied outcome gets one append followed by one commit, and no later outcome
  is examined until that commit succeeds. Never batch multiple outcomes behind
  a single durable `last_launch_ack` marker.
- Extend the Performance tail/runtime metadata with an optional durable
  `last_launch_ack` carrying the exact request identity, slot and effective
  tick. It is never a Project Truth event field, flush identity input or
  Runtime Snapshot field. Cross-process status may project it; applied-outcome
  retry compares it with the front peeked outcome before deciding append versus
  commit-only.
- Add `Application::service_performance()` as an explicit mutating control
  operation outside the 23-operation request surface. Under the existing
  serialization it peeks each active session, appends an applied launch event
  once, then commits the outcome; failed/cancelled outcomes are committed only
  after confirming they produce no event. Exact request identity plus the
  durable pending snapshot resolves append-success/commit-gap retry without a
  duplicate event.
- `performance.record.status` removes all drain/service calls. It reports only
  already-durable runtime/journal projection and is byte-identical even when an
  outcome is waiting in the acknowledger.
- The C API/CLI Host composition calls Runtime bridge service before every
  request, while Application's serialized dispatch calls
  `service_performance()` only before command execution. Native
  calls adapter service then Application service on its existing periodic
  serialized control tick and before commands. Queries never invoke the
  mutating service; the render thread gains no entry point.
- A definitive pre-write Application append failure leaves the outcome
  peekable, rolls runtime projection back, and retries the same front identity.
  If exact read-back cannot resolve a possible post-write result, HRS-D10
  freezes the session as recovery-required; service must not append again or
  allow a later command to overwrite the unknown tail. If read-back proves the
  applied ack durable, retry is commit-only. Hosts do not drop the outcome,
  fabricate an ack, or terminate the render callback.
- Native stores the first Application service typed failure in a non-terminal
  control-thread latch under `facade_mutex_`. Each later control tick retries
  the same front; a command also services first and returns the latched/current
  typed error without dispatch when retry fails, clearing the latch only after
  success. Queries never run the mutating service and may still project
  already-durable state. Headless command dispatch follows the same refusal
  rule without inventing a Host-specific error.

- [ ] **Step 1: Write two-phase acknowledger REDs.** In headless and engine
  adapter suites, prove repeated peek is identical, wrong/out-of-order commit
  fails closed, exact commit removes once, and cancelled/failed/applied
  outcomes cannot cross sessions. Expect FAIL.
- [ ] **Step 2: Implement `peek`/`commit`.** Update all production adapters and
  test fakes; preserve claimed-defer/latest-wins and engine boundary predicates.
  Run Step 1; expect PASS.
- [ ] **Step 3: Write journal/Application service/status REDs.** Round-trip and
  strictly validate the Runtime-only durable launch-ack identity. Make an applied
  outcome ready, hash active/sealed/Project bytes, call status repeatedly, and
  require byte identity plus still-pending outcome. Call explicit service and
  require one durable `pattern_launch`; repeat service/status and require no
  change. Inject journal append failure and append-success/commit-gap failure;
  distinguish definitive pre-write retry from ambiguous post-write freeze,
  and require commit-only retry from a proven durable identity with no lost or
  duplicate event. Queue at least two outcomes and crash between each
  append/commit boundary to prove strict front-only progress. Expect FAIL.
- [ ] **Step 4: Implement Application service and remove query mutation.** Keep
  all Project/fingerprint/time/order logic in Core. Do not add an operation,
  schema field, Host clock, or query-side writer lease.
- [ ] **Step 5: Prove Host cadence.** C API/CLI tests prove query-only requests
  are disk-read-only and the next command services the outcome. Native test
  crosses a launch boundary with no request, waits for the periodic control
  tick, then observes the already-durable ack through status without status
  changing disk. Inject a service failure: render/audio remains non-terminal,
  the next control tick retries the same front, query remains read-only, and a
  command returns the typed error without dispatch until service succeeds.
  Existing request and protocol bytes remain compatible.
- [ ] **Step 6: Run complete verification.** Run
  `scripts/core.sh test dev full`, `scripts/core.sh coverage check`,
  `scripts/core.sh test dev stress`, and
  `scripts/architecture-portal.sh check`.
- [ ] **Step 7: Ship one review unit.** Follow `issue-done`, stage only the
  files above, and commit
  `fix(facade): keep Performance status read-only (fixes #571)`. Push, queue,
  squash-merge, verify exact merged-main CI, and clean only this worktree/
  branch. Then #432/#433 may consume the explicit service boundary.

## Version Management

Version impact: no new allocation.

All five Tasks land before Stage 10 Task 10 enables the v4 writer and
publishes module versions. They consume the already locked targets:

- application-facade `3.0.0` (bridge/adapter headers, port contract
  comments, `anchor` method);
- project-io `2.0.0` (recovery reconciliation boundary move, flush identity
  lookup);
- core-cli `3.0.0` (session mode);
- native-host `3.0.0` (construction order and adapter wiring);
- C ABI unchanged at `lmdj_core_c@1` with exactly five symbols;
- Product Build `1.0.42.0`.

Before #436 allocates or publishes identities, rerun its fresh allocation
audit. If any identity has become occupied, stop and refresh the Stage 10
allocation rather than changing it inside #523, #524, #525, #570 or #571.

## Documentation Impact

Documentation impact: none for #523, #524, #525, #570 and #571.

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
  -> Issue #570 one commit / PR / merge / cleanup   (needs #523)
  -> Issue #571 one commit / PR / merge / cleanup   (needs #523, #525, #570)
  -> Stage 10 Task 6 (#432) — CLI/MCP/Native migration and cross-Host journeys
```

#524 and #525 touch disjoint primary files and may run in parallel worktrees
after #523 merges. #570 may also run after #523; #571 needs #523, #525 and #570.
Task 6 (#432) requires all five merged, and Task 7 (#433) requires #525/#571.
