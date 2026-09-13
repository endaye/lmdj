# Pattern transport: Facade, runtime and Creator integration

## Goal and authority

Complete the remaining integration for [#1230](https://github.com/endaye/lmdj/issues/1230), then return to U1/U2 and the complete [U0–U8 migration](../../plans/2026-09-11-creator-ui-migration.md). This is an execution plan for the approved [transport architecture](../specs/2026-09-11-global-pattern-transport-design.md), not a replacement success criterion. No brainstorming, new transport product decision, release, deployment or user-data deletion is included.

The six approved transitions, restart at Pattern beginning without count-in, and Record-off without playback restart are settled. The demo does not need old Sequence storage compatibility. Preserve existing bytes and report unsupported/unresolved recovery; do not convert or delete user storage. The owner waiver for PR #1265 applied only to its exact head, not to these Tasks.

## Inspected baseline

Source: `e5195d1524b0581c777ecf8ee4bb14773fc3fa07` (PR #1265 merged). These are source observations, not fresh runtime acceptance:

- PR #1247 supplies `RealtimeEngine::enable_pattern_transport`, `submit_pattern_transport`, historical `inspect_pattern_transport_receipt`, acknowledgment and phase-preserving publication. Audio receipts contain generation, epoch, effective/origin frame, Pattern/publication identity and cutoff-relative switch disposition.
- PR #1260 supplies `SequenceJournalStore::prepare_admission`, candidate append, retained admission/cutoff fences, retained switch authority, closure, transfer and completion. `sequence_admission.hpp` defines bounded candidates and canonical-tail transfer/checkpoint receipts.
- PR #1265 supplies the isolated WebKit setup for real OPFS proof. Mac dependencies must be installed locally; Windows/WSL caches are not portable proof inputs.
- `Application::Impl::begin_sequence` creates the journal synchronously under `sequence_mutex`, anchors at the supplied frame and immediately registers a live `SequenceRuntime`. `record_sequence_event` appends a complete recoverable tail before advancing its input sequence. These functions are not prepared admission or an asynchronous transport coordinator.
- `ControlRuntime` still implements `sequence.record.begin` and records immediately after accepted engine enqueue. `runtime_session.mjs` serializes runtime actions. Neither exposes the proposed global request/inspect transport API.
- `ControlBridge::process` serializes dispatch through the complete Asyncify suspension/rewind. `library_opfs_storage.js::suspend` rejects reentry. Merely returning a Promise or moving a synchronous flush into a later dispatch cannot satisfy nonblocking transport continuation.

## Invariants and implementation order

One Facade coordinator owns the transport operation and journal; one audio owner applies clocks; one existing input controller retains live input/result authority. Creator only submits intents and renders projections. No second Runtime, no page-owned recording state, no engine-wide Stop as Pattern Stop, no dummy Pattern or silence publication.

Implement T0 → T1 → T2 → T3 → T4. Each is one isolated, declared Task and Conventional Commit, with current-head review through `issue-done`. Shared files have one writer. Broad CI repair remains with the other agent. A foundational Task is not global transport acceptance and must not enable Creator prematurely.

### T0 — Prove the execution port before transporting IO through it

**Defect caught:** a paused prepare/flush suspends the entire control lane, or a second request reenters a suspended Asyncify stack.

**Files:**

- New `packages/application-facade/include/lmdj/facade/pattern_transport_ports.hpp` and `packages/application-facade/src/pattern_transport_executor.cpp`.
- `packages/application-facade/CMakeLists.txt` and new `tests/core/facade/pattern_transport_executor_test.cpp`.
- `packages/web-runtime-platform/src/bridge.cpp`, `packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`, `packages/web-runtime-platform/src/control_runtime.cpp`, `packages/web-runtime-platform/CMakeLists.txt`.
- `packages/web-runtime-platform/test/control_runtime_test.cpp`, `packages/web-runtime-platform/test/performance_bridge_test.cpp`, `tests/platform/web/audio/realtime_failure.spec.mjs`, `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`, `tests/platform/web/audio/realtime_audio_worklet.html`.
- `apps/docs-site/docs/core/modules/application-facade.mdx`, `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`, corresponding `apps/docs-site/diagrams/application-facade.architecture.json` and `web-runtime-platform.architecture.json`, plus generated outputs from the canonical diagram command.

**Port contract:** submit reserves a bounded ticket and returns without invoking blocking preparation/IO inline. Ticket binds runtime generation, transport epoch, command ID and monotonically identified step. Poll returns pending or one retained completion, with typed success/refusal/unknown outcome. Explicit consume is required before ticket reuse. Duplicate submit with changed payload is refused; timeout neither erases a ticket nor retries an effect. Queue exhaustion is a refusal before effect. No timer qualifies as completion.

Execution ownership must be proven in this Task. A dedicated non-audio execution context may own preparation and its Project writer lease, while the control thread owns engine submissions and consumes immutable completion results. All storage operations on a lease, including destruction, stay on its owning execution context; never carry an OPFS numeric lease token into another worker's JS registry. Do not share a mutable `Application` across workers without an explicit lock/ownership proof. The control path must not wait on an application mutex held across that work.

During pre-admission preparation and after acknowledged cutoff, live input remains live-only and must run while IO is paused. During admission and fence retention, preserve existing post-enqueue append result semantics: a trigger that needs durable candidate retention cannot be reported successful early. This is not permission to move input into a second queue or make journaling fire-and-forget.

- [ ] Register the native component target `lmdj_pattern_transport_executor_tests` / CTest `facade.pattern_transport_executor`; use a deterministic latch to hold work and assert submit returns and the owner can inspect pending state.
- [ ] Add stale completion, duplicate request, queue full, unknown result and disposal/join tests. Dispose must settle or preserve recovery, not detach a worker retaining freed Facade memory.
- [ ] In real browser conformance, hold an actual OPFS operation across dispatch turns; prove a live press/release and its existing receipt complete before unblocking prepare/flush. Then release IO, consume completion once and inspect persisted data.
- [ ] Preserve the existing reentry guard and bridge serialization tests. Extend the declared existing audio browser specs discovered by standard Web toolchain proof; add any additional harness source to this declaration before editing. Do not create an undiscovered spec.
- [ ] Run native component, relevant bridge tests, real Chromium/isolated WebKit proof and ASan/TSan for any new shared-thread state. Do not proceed to global opt-in if only a fake executor passed.

If the current platform cannot implement this port without changing #725 successful/failed/unknown admission outcomes or violating single-owner Asyncify/lease rules, record that exact dependency and stop the adapter implementation. Do not weaken the approved architecture to fit the existing dispatch loop.

### T1 — Prepared journal, acknowledged admission and exactly-once transfer

**Defect caught:** mid-loop Record uses the button frame as tick zero, a pre-admission release fabricates an event, or retry transfers the same retained candidates twice.

**Files:**

- `packages/application-facade/include/lmdj/facade/application.hpp`, `packages/application-facade/src/application.cpp`.
- New internal `packages/application-facade/src/pattern_admission_controller.hpp` and `.cpp`; `packages/application-facade/CMakeLists.txt`.
- `tests/core/facade/sequence_surface_test.cpp`; new `tests/core/facade/pattern_admission_test.cpp` registered as `lmdj_pattern_admission_tests` / `facade.pattern_admission`.
- `tests/platform/web/project_io/project_io_web_test.cpp`, `tests/platform/web/project_io/project_io_web_conformance.spec.mjs` for real Facade/storage recovery; declare any required harness linkage changes before editing.
- `/core/modules/application-facade/` and `/core/modules/project-io/` current pages and corresponding module diagram sources/generated outputs if their boundaries change.

Use the existing journal and `SequenceRuntime` reducer; do not implement a second quantization/overdub algorithm. Add a prepared state with candidate admission closed. Reserve durable admission capacity and its terminal/error record before the fence. Activation takes the retained audio origin/BPM/Pattern identity plus effective frame; origin anchors tick zero, while the effective frame and watermark bound eligibility.

Candidate identity is the original accepted input sequence/correlation, not the journal sequence. Retain candidates only at the existing post-enqueue point; known refusal creates none. A release can close only a matching journal-owned press. Preserve the existing per-slot retrigger behavior and sixteenth-tick finalization. Candidate transfer computes a complete canonical tail and checkpoint, binds exact source digests/receipts, and advances the journal sequence only after durable success. Reconcile an ambiguous append before draining further; never enqueue live input from recovery.

- [ ] First red assertion: an admitted mid-loop press/release produces the correct nonzero Pattern tick without resetting origin.
- [ ] Prove pre-admission press/post-admission release is live-only; owned press/post-cutoff release uses ordinary terminal completion rather than a fabricated cutoff release.
- [ ] Crash/reopen after candidate append, fence retention, transfer append and receipt response loss. Compare complete Pattern/Pad Slot events, revision and transfer identity, not just event count.
- [ ] Reach last reserved capacity and deadline deterministically: close at watermark B, persist reason/prefix, keep subsequent input live-only, and drain that prefix once after delayed receipt. Storage failure reports the uncertain suffix explicitly.
- [ ] Keep unresolved fence state unresolved after owner loss; verify original/alternate existing Pattern recovery and user-requested discard without deleting unrelated data.
- [ ] Native and real OPFS assertions must cover the same far-side state. Reuse storage fault injection and writer leases, not a filesystem-only mock as browser proof.

### T2 — Facade transport coordinator and historical effect reconciliation

**Defect caught:** retry toggles twice, durable Record-off is reported as failure of all effects, or a delayed switch observation selects the wrong Pattern at cutoff.

**Files:**

- `packages/application-facade/include/lmdj/facade/application.hpp`, `packages/application-facade/src/application.cpp`, `packages/application-facade/include/lmdj/facade/pattern_transport_ports.hpp`.
- New `packages/application-facade/src/pattern_transport_controller.hpp` and `.cpp`; `packages/application-facade/CMakeLists.txt`.
- New `tests/core/facade/pattern_transport_test.cpp` registered as `lmdj_pattern_transport_tests` / `facade.pattern_transport`; existing `tests/core/facade/sequence_surface_test.cpp`.
- Application Facade current page and architecture source/generated outputs.

Expose typed request/inspect/continue operations. Bind session/project identity, runtime generation, command ID, expected epoch, intent and relevant expected revision. Resolve the intent once against applied state, retain the operation through terminal outcome, and reject a new mutation while unresolved. Same ID/different payload is invalid; same ID/same payload returns/reconciles its retained operation. Stale generations cannot mutate a restarted session.

The coordinator selects effects, the execution port performs preparation/storage off the control lane, and the audio port submits and inspects the real engine command. Request and continuation never wait for a future receipt. Status separates applied audio state, pending target, operation phase, journal/admission state, exact publication/switch authority, committed revision and structured recovery error. No recording-only successful steady state.

- [ ] Verify all six transitions using the production engine adapter plus journal storage. Playing-only starts no journal. Stopped starts at acknowledged origin; playing Record uses a fence with unchanged origin.
- [ ] End recording by acknowledged cutoff, drain/reconcile switch first, then terminal commit. Record-off leaves scheduling running; Play/Stop stops scheduling before slow/failed flush. Known audio state remains visible on IO failure.
- [ ] For S < F / S = F / S > F, delay inspection past S and assert the historical receipt selects retain/cancel/cancel. Journal segments never extend past F; cancellation failure alone selects nothing.
- [ ] Retain a recording fence durably before acknowledging/releasing the audio receipt. Unknown/lost receipt blocks contradictory closure; it does not authorize guessing from telemetry.
- [ ] After durable commit, phase-preserving replacement may remain pending/refused when slots are full. Keep committed revision separate and retry the same replacement without restarting, reopening the journal or committing twice.
- [ ] Inject each failure before/after effect and completion delivery. Stale/duplicate completion cannot overwrite newer state, consume a receipt twice or synthesize success.

### T3 — Public runtime/bridge integration and lifecycle barrier

**Defect caught:** the JS lane waits for a whole transport operation, direct legacy recording creates a second journal owner, or replacement disposes unresolved recording.

**Files:**

- `packages/web-runtime-platform/src/control_runtime.cpp`, `src/bridge.cpp`, `include/lmdj/web_runtime/control_runtime.hpp` and `CMakeLists.txt`.
- `packages/web-runtime-platform/web/protocol.mjs`, `web/runtime_session.mjs`, `web/runtime_types.d.ts`.
- `packages/web-runtime-platform/test/control_runtime_test.cpp`, `test/performance_bridge_test.cpp`, `test/runtime_session.test.mjs`, `tests/platform/web/audio/realtime_failure.spec.mjs`, `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`, `tests/platform/web/audio/realtime_audio_worklet.html`.
- `/core/modules/web-runtime-platform/`, `/platform/web-runtime/`, `/platform/input/` current pages and affected diagrams.

Add capability-negotiated `pattern.transport.request` and `pattern.transport.inspect`, with internal continuation scheduling. Return the pending ticket through the existing serializer, release its tail, then reenter for short epoch-checked steps. Do not await audio acknowledgment or a long IO job inside that tail. Native/other Host consumers remain explicit legacy users until they opt in; legacy `stopSequence` keeps its journal meaning. Global-enabled sessions reject conflicting direct legacy writes.

- [ ] Wire the actual post-enqueue sequence/release correlation into T1 without altering returned successful/failed/unknown input outcomes. Unknown input is never automatically retriggered.
- [ ] Hold each preparation, audio, storage and publication completion separately; prove applicable live input and releases remain serviceable, and verify journaling responses are not reported before durability.
- [ ] Explicit Suspend, Project replacement and disposal enter a shutdown barrier: acknowledged Pattern Stop, admission closure, journal settlement/recoverable refusal, required input release, then lifecycle effect. Unknown closure prevents a clean replacement claim.
- [ ] Sample capture, performance audio recording/replay and audition keep existing busy/ownership guards. Test live Pad and non-Pattern replay survival across Pattern Stop.
- [ ] Run native control/bridge tests, runtime-session tests and full standard Web proof with fresh Mac toolchain dependencies. Browser tests exercise actual Wasm/OPFS and completion ordering.

### T4 — Creator global owner, six transitions and U2 handoff

**Defect caught:** navigation stops recording, two components own transport, or UI labels advance ahead of acknowledged audio/durable state.

**Files:**

- `apps/creator-web/src/app.tsx`, `src/runtime/sequence_actions.ts`, `src/state/sequence_state.ts`.
- New `src/state/pattern_transport_state.ts` and `src/runtime/pattern_transport_actions.ts` under `apps/creator-web/`.
- Existing `src/components/sequence_surface.tsx` and `src/components/perform_surface.tsx`; hardware control binding paths must be resolved from actual U1 delivery before editing.
- `apps/creator-web/test/sequence_actions.test.ts`, `test/sequence_state.test.ts`, new `test/pattern_transport_actions.test.ts`, new `test/pattern_transport_state.test.ts`, relevant app/workspace tests.
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`; `apps/docs-site/docs/hosts/creator-web.mdx` and affected workflow page/diagram.

Only the app's single session owner opts in. Physical Play/Stop and Record always mean global Pattern transport, never Sample capture or master recording. Every mode consumes the same projection and command identity. Remove ordinary mode-leave journal Stop only after T3 is proven; retain separately owned sample/audition cleanup. Show busy, refused, committed-but-not-published and recoverable states honestly.

- [ ] Reducer/action tests reject stale responses, retain failed operation identity and preserve revision when absent/null. Retry inspects/reconciles, never sends a new inverse toggle.
- [ ] Real packaged journey: opened material → Play → Record → live Pad events → Record-off → page changes → continued playback → Stop → reopen; verify precise events/revision, runtime scheduling and one session/input subscription.
- [ ] Separate journey: stopped Record → overdub → Pattern switch → Play/Stop → reopen; include failed flush retry, failed publication retry, owner loss/recovery and discard.
- [ ] Preserve real acoustic/device acceptance gaps. Synthetic samples and WebKit automation are software evidence, not hearing, touch, MIDI hardware or physical Safari acceptance.
- [ ] Run full Creator proof, new journeys and portal checks. #1230 remains open until every acceptance item has applicable evidence/disposition. U2 still needs the migration layout work; U3–U8 and U7/U8 human acceptance/observation conditions remain intact.

## Verification commands and delivery

Commands below are planned, not passed. New targets must be registered by their owning Task before use; individual tests should isolate one defect.

```bash
bash scripts/core.sh configure dev
cmake --build --preset dev --target lmdj_pattern_transport_executor_tests
ctest --preset dev --output-on-failure -R '^facade\.pattern_transport_executor$'
cmake --build --preset dev --target lmdj_pattern_admission_tests lmdj_facade_sequence_surface_tests
ctest --preset dev --output-on-failure -R '^facade\.(pattern_admission|sequence_surface(\..*)?)$'
cmake --build --preset dev --target lmdj_pattern_transport_tests
ctest --preset dev --output-on-failure -R '^facade\.pattern_transport$'
bash scripts/web-toolchain-conformance.sh proof
bash scripts/creator-web.sh test
bash scripts/creator-web.sh proof
bash scripts/docs-site.sh check
python3 tests/build/ci_change_scope_test.py
git diff --check
```

For concurrency changes use the equivalent registered targets in `asan` and `tsan` and the relevant existing stress suite; `full`/`proof` alone excludes stress. Never lower thresholds, delete journey legs or increase timeouts for green. Record unsupported platform checks as unexecuted. Stage new files before ownership verification; no broad CI scope edits unless an exact newly declared path lacks ownership.

## Version Management

Version impact: none for this planning Task; no active manifests, Product Build or Assembly changed.

T0–T4 are staged source integration until allocation. They add public Facade/runtime APIs and change Host behavior. Assess C++ ABI (including changed layouts), Web protocol capability/version and the complete active manifest consumer closure before distributing a build. Carry forward the staged Audio Runtime ABI and Sequence storage format boundaries from the preceding plans. No old storage reader/writer compatibility is required; unsupported data remains preserved. Do not hand-edit generated Assembly locks or reuse old binaries across the ABI boundary. A team-test/release allocation is a separate version Task requiring current manifest-derived identities and an immutable portal snapshot; no version number is guessed here.

## Documentation Impact

Documentation impact: none — this Task adds future integration instructions and links them from the migration plan, without changing current implemented portal facts.

Implementation Tasks declare Documentation impact: required with their exact affected routes listed above, update current pages/diagram sources and run the portal check in the same Task. Any additional affected route/file must be added to the owning declaration before editing. Do not rewrite prior snapshots or describe the full transport as implemented when only a dependency is present.

## Planning Task boundary

Declared files: this file and `docs/plans/2026-09-11-creator-ui-migration.md`. Verify baseline symbols, linked files, Task ownership, scope classification, documentation declaration and whitespace; no product test pass is claimed by committing this plan. PR uses `Relates to #1230` and `Relates to #1207`. No release, cleanup, protection change or inherited review waiver.

### Initial local preflight (2026-09-13)

At the baseline above, fresh Mac `scripts/core.sh configure dev` fails because `tests/platform/cardputer/CMakeLists.txt` registers `platform.cardputer.input.feedback_interleaving` twice (the dedicated executable and the input-scenario loop). No transport executable was built or tested.

The initial staged `python3 tests/build/ci_change_scope_test.py` run executed 72 tests and failed the two whole-index ownership/top-level assertions: that baseline tracked 2,093 paths under `build/`, which the policy did not admit. This was not caused by the new plan. No broad build-artifact ownership rule, deletion or skipped assertion was added by this Task.

Refreshed base `c1d5e827` includes the separate repairs (#1263/#1266). After a fast-forward retaining only the two declared document edits, Mac Core configuration passes and the full staged ownership suite passes 74/74. The initial configuration/ownership blockers are cleared; this is not evidence that the new transport integration or its browser acceptance is implemented.
