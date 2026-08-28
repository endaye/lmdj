# Sequence Pending Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to execute this plan in one reviewable Task. Do not split the Issue across commits.

**Goal:** Make accepted, unflushed Sequence events audible from the next Bar through the production Facade → Web control bridge → Audio Runtime path, then replace the overlay with committed Runtime truth without duplicate hits, gaps, or stale overlay state.

**Architecture:** The Application Facade exposes an immutable, session-owned projection of the current in-memory pending events without making them Project Truth. The Web Runtime control thread prepares a `PreparedPatternView` from the committed Runtime Snapshot plus that projection and publishes it for the next Bar. Audio Runtime uses one atomic generation mailbox as the publication linearization point: the control thread may supersede only an unclaimed same-boundary view, while the realtime thread first marks a generation claimed and then owns its boundary application without allocation, locking, destruction, stale rejection, or Project access.

**Tech Stack:** C++20, nlohmann/json, CMake/CTest, atomic generation mailbox plus fixed realtime queues, Docusaurus Architecture Portal.

## Global Constraints

- SR-D13 remains authoritative: a live hit is immediate and the accepted event repeats from the next Bar; Project persistence still occurs only at the approved flush boundaries.
- Overlay merge remains the approved `(slot, onset_tick)` last-write-wins replacement from SR-D12/SR-D26.
- Project Truth remains authoritative; overlay projections and prepared Pattern views are immutable derived Runtime state and never fabricate a Project revision or flush receipt.
- Realtime `render` allocates nothing, frees nothing, locks nothing, blocks on nothing, parses no JSON, and performs no Project I/O.
- Hard-crash tail persistence is excluded and remains #373. Switch-boundary flushing is excluded and remains #376.
- The Task is one local Conventional Commit that closes #375. Push, PR, merge, release, deployment, publication, and Channel promotion are excluded.

---

### Task 1: Publish and retire pending Sequence overlays

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/core/facade/sequence_surface_test.cpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `tests/core/audio/realtime_engine_test.cpp`
- Modify: `tests/core/audio/snapshot_publication_stress_test.cpp`
- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/test/control_runtime_test.cpp`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/audio-runtime.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/diagrams/application-facade.architecture.json`
- Modify: `apps/architecture-portal/diagrams/audio-runtime.architecture.json`
- Modify: `apps/architecture-portal/diagrams/web-runtime-platform.architecture.json`
- Modify: generated current diagram HTML/SVG for the three changed diagram sources
- Modify: `docs/quality/2026-08-27-stage9-sequence-recording-review.md`
- Modify: `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`

**Interfaces:**

- Consumes: the active Facade `SequenceRuntime::pending_events`, `Application::prepare_runtime_snapshot`, `PreparedPatternView::from_snapshot_with_overlay`, and `RealtimeEngine::publish_pattern_view`.
- Produces: `SequenceOverlayProjection { session_id, pattern_id, generation, events }`, `Application::query_sequence_overlay(SequenceOverlayRequest)`, same-boundary immutable Pattern supersession, and Web control publication evidence.

- [x] **Step 1: Write Facade projection tests and observe RED**

  Add a component case that begins a session, records press/release, queries the wished-for typed projection, proves the canonical event is present, replaces the same `(slot, onset_tick)` deterministically, proves a rejected event leaves the projection unchanged, flushes, and proves the active projection is empty. Build the Facade target and expect compilation to fail because `SequenceOverlayRequest` and `query_sequence_overlay` do not exist.

- [x] **Step 2: Implement the minimal Facade projection and observe GREEN**

  Add these exact public value types and method:

  ```cpp
  struct SequenceOverlayRequest {
    std::filesystem::path project_path;
    foundation::SequenceSessionId session_id;
  };

  struct SequenceOverlayProjection {
    foundation::SequenceSessionId session_id;
    foundation::PatternId pattern_id;
    std::uint64_t generation{};
    std::vector<domain::PatternEvent> events;
  };

  foundation::Result<SequenceOverlayProjection> query_sequence_overlay(
      const SequenceOverlayRequest& request) const;
  ```

  Increment a session-local generation only when pending event content changes or clears. Under the existing Sequence mutex, return a copy only to the matching active owner; reject missing/mismatched/invalid sessions. Do not add a JSON operation, persist the projection, or alter status/receipt semantics.

- [x] **Step 3: Write Audio Runtime supersession tests and observe RED**

  Publish two overlay views for the same Pattern and same next-Bar activation before render reaches the boundary, then publish the clean committed view. Expect the newer publications to be accepted, only the newest generation to apply, retired views to be reclaimable, `current_pattern_has_overlay()` to change from true to false, and the guarded render path to allocate/deallocate zero times. Extend the existing pattern stress case so accepted publications are conserved as applied + pending + superseded.

- [x] **Step 4: Implement bounded realtime-safe supersession and observe GREEN**

  Let a control-thread publication supersede only the currently unclaimed publication for the same Project, Pattern, and activation frame. Publish the immutable prepared slot through one atomic generation mailbox. At callback entry atomically mark the mailbox generation claimed before transferring it to audio-owned pending state; a concurrent publisher that loses the replacement CAS recomputes from the reserved callback end frame, so the claimed view applies at its original boundary and the replacement moves to the following Bar. Mark superseded slots control-thread reclaimable and count them explicitly. Never reject a claimed view because a newer generation exists, and never reset a `PreparedPatternView` on the audio thread.

- [x] **Step 5: Write the production-path Web control test and observe RED**

  Drive a real `ControlRuntime` through Project create, Sample import/assign, snapshot publication, audio activation, Sequence begin, live trigger press/release, Bar rendering, flush/Stop, and another Bar. Assert the release creates a pending Pattern publication, the overlay starts exactly one repeating Pattern voice at the next Bar, the committed replacement produces one hit at the following loop boundary, and the current Pattern reports no stale overlay after the transition.

- [x] **Step 6: Wire Facade projection through Web control and observe GREEN**

  Track the last published overlay generation in the active Web Sequence session. After each accepted Facade event, query the typed projection; if its generation advanced and no different Pattern switch is pending, prepare the committed snapshot with `from_snapshot_with_overlay` and publish it. A BPM update during the session force-rebuilds committed snapshot + current overlay at the existing pending boundary. Reclaim retired Pattern slots on the control thread before publication. On abandon/cancellation/fail-and-seal, schedule the clean committed view before releasing the owner. On successful flush or Stop, preserve the committed Pattern identity in the Facade result and always publish the clean committed Pattern, including an exact idempotent replay after a publication failure. Keep #373 persistence and #376 switch-boundary flushing unchanged.

- [x] **Step 6a: Close review race and lifecycle regressions with RED → GREEN evidence**

  Add a deterministic callback-claim race gate proving a superseding publication cannot cancel a view already claimed for onset zero; extend the production journey through an active-session BPM change; render an overlay before owner loss and prove clean removal at the following Bar; inject one post-commit clean-publication failure and prove exact Stop replay recovers from the durable Pattern identity. These tests must fail against the original queue/generation ordering and Host lifecycle behavior before the production fixes.

- [x] **Step 7: Update current documentation and generated diagrams**

  Mark M1 as source-fixed by #375 while leaving integrated Product identity to #379, immutable snapshot work to #380, and all physical/manual rows unverified. Update `/core/modules/application-facade/`, `/core/modules/audio-runtime/`, `/core/modules/web-runtime-platform/`, `/hosts/web-runtime/`, and `/hosts/creator-web/` to state the projection/publication boundary and tests. Regenerate only the current outputs for the three changed source diagrams; do not modify `versioned_docs`, `versioned_metadata`, version manifests, Assembly identities, or Product Build snapshots.

- [x] **Step 8: Verify, audit pitfalls, and create the atomic commit**

  Run the focused Facade, Audio Runtime, Web control, and pattern-publication stress tests; then `scripts/core.sh test dev full`, `scripts/core.sh test dev stress`, `scripts/architecture-portal.sh check`, `bash tests/build/test_active_tree.sh`, `python3 tests/build/version_test.py`, and `python3 scripts/version.py verify --version-file products/lmdj/version.json`. Search open `area:core`, `area:creator`, and `area:web-host` pitfalls; record no new pitfall when the invariant is fully derivable from product code and regression tests. Exact-stage only declared files, run `git diff --cached --check`, and commit as `feat(sequence): publish pending runtime overlays (fixes #375)`.

## Version Management

Version impact: required, allocation deferred to #379. This Task changes the implementation/API domains of Application Facade, Audio Runtime, Web Runtime Platform, Web Runtime Host, and Creator Web Host, but must not edit their module/Host versions, `products/lmdj/version.json`, Assembly manifests/locks, tags, or Product Build snapshots. Issue #379 performs the fresh identity audit and allocates the integrated Product Build after all six remediation children merge; #380 freezes its immutable Portal snapshot.

## Documentation Impact

Documentation impact: required.

Affected portal pages: `/core/modules/application-facade/`, `/core/modules/audio-runtime/`, `/core/modules/web-runtime-platform/`, `/hosts/web-runtime/`, `/hosts/creator-web/`.

Reason: the current Facade projection boundary, Web control publication lifecycle, Audio Runtime supersession semantics, and automated evidence change. Only current Portal pages/source diagrams and the Stage 9 review/acceptance ledgers move in this Task; immutable Product Build documentation remains deferred to #380.
