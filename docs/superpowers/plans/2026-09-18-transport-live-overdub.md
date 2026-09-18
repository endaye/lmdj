# Pattern transport: live loop overdub publication

## Goal and authority

Make a pass recorded through the global Pattern transport audible on the next
pass without leaving Record — [#1513](https://github.com/endaye/lmdj/issues/1513),
the Koala loop-overdub behavior confirmed in
[`2026-09-18-pattern-transport-koala-loop-overdub.md`](../../prd/decisions/2026-09-18-pattern-transport-koala-loop-overdub.md).
This is an execution plan for that settled decision, not a new product
question. It closes one acceptance gap of [#1230](https://github.com/endaye/lmdj/issues/1230)
and unblocks ledger leg T-L7.

It is not a release, a deployment, a Contract change, or a user-storage
migration. It does not discharge #1230 acceptance item 7: the physical rows
still need hands and ears on a Build that contains this work.

Boundary with [#1515](https://github.com/endaye/lmdj/issues/1515): both issues
are the two ends of the same missing conversion — this one converts the durable
admission **during** recording so the pass is audible; #1515 converts it
**after** owner loss so an interrupted take is recoverable. L0 below builds the
one converter both consume, as the issue owner directed. #1515's recovery
wiring is not in this plan.

## Inspected baseline

Source observations at `dba40899`. These are reads of the tree, not runtime
acceptance:

- `packages/application-facade/src/pattern_admission_controller.cpp`
  `build_admission_transfer` already performs the complete
  candidate → `domain::PatternEvent` conversion: segment/cutoff authority
  selection, per-candidate timing profile and `audio::raw_tick_at`, the shared
  `PatternEventReducer`, and `recoverable_tail()`, which finalizes still-held
  presses at `domain::kSixteenthTicks`. It is documented as pure — "Does not
  enqueue live input, consult Project settings, or mutate a journal" — and
  `commit_admission_transfer` is what makes its receipt durable.
- The converter already declines exactly the cases a live overlay must decline:
  `switch_prefix_requires_reconciliation` when a candidate sits at or after a
  pending switch frame, and it skips candidates outside
  `[segment.frame, cutoff_fence.effective_frame)`.
- `packages/application-facade/src/pattern_transport_controller.cpp` calls the
  converter only from `finish_close()` — `drain_source_prefix`,
  `drain_target_segment`, `settle_close`. While recording is open, `admit()`
  durably appends candidates (`PatternAdmissionOwner::admit` ~:475) and nothing
  else happens. There is no projection seam on the coordinator and none on the
  public `PatternTransportController`.
- `packages/web-runtime-platform/src/control_runtime.cpp`: the legacy path calls
  `publish_pending_sequence_overlay()` after every recorded Pad event (~:3951,
  ~:4003); the transport path calls only `admit_transport_pad()` (~:3960,
  ~:4011). The transport path's sole publication is
  `transport_continuation_step()` ~:1679, armed when a recording close has
  settled.
- `ControlRuntime::service_pattern_transport()` (~:4792) runs on the serialized
  control cadence from `bridge.cpp` ~:665 every service tick, but returns early
  when `phase == idle && !publish_pending` — which is exactly the state of a
  steadily recording transport. Today only `pattern.transport.inspect` drives a
  step in that state.
- `publish_project_pattern(pattern, /*activation_frame=*/nullopt, overlay)`
  reaches `RealtimeEngine::publish_pattern_view` with no requested activation,
  and `realtime_engine.cpp` ~:1229 lands it at
  `origin + (bars + 1) * bar_frames` — next Bar boundary, origin unchanged.
  That is the intended loop semantics, already implemented.
- `kRealtimePatternCapacity` is 4. `publish_prepared_pattern` calls
  `reclaim_retired_patterns()` before each publication and maps a refused
  publication to `invalid_argument`.

## Invariants and implementation order

One converter, one recording owner, one publication owner. The live overlay is
a **read-only projection of already durable state**: it mutates no journal,
advances no watermark, and retains no receipt. The exactly-once commit at
Record-off is therefore unchanged by construction — the overlay cannot consume
what the close later transfers.

- The overlay never applies across a boundary it does not own: no publication
  while a Pattern switch is pending, while a close is unresolved, or when the
  converter reports an unreconciled switch prefix.
- The overlay never restarts the beat: every publication is submitted with no
  requested activation frame, so it lands at the next Bar boundary against the
  unchanged origin.
- An overlay publication is advisory to durability: the events are already
  durable when it runs. A failed publication is retried on the next control
  tick and must never fail a Pad trigger or seal the runtime. This is a
  deliberate divergence from the legacy path's `fail_and_seal`, stated here so
  it is not read as an oversight.
- Publication is coalesced onto the control cadence, not issued per Pad event.
  The audible deadline is the next Bar boundary, many ticks away; a per-event
  snapshot-prepare on the trigger dispatch path is not needed and is not added.

Implement L0 → L1 → L2 → L3. Each is one isolated Task, one Conventional
Commit of its declared files, shipped through `issue-done` with current-head
review. L0 and L1 change no observable behavior; L2 is the behavior change;
L3 records it. A Task that only lands a seam is not loop-overdub acceptance
and must not be reported as one.

### L0 — One converter serves the commit and the projection

**Defect caught:** a second overdub algorithm that computes a different overlay
than the one the close commits, so what you hear during recording is not what
survives Record-off.

**Files:**

- `packages/application-facade/src/pattern_admission_controller.hpp`
- `packages/application-facade/src/pattern_admission_controller.cpp`
- `tests/core/facade/pattern_admission_test.cpp`

**Shape:** factor the authority-selection and candidate-conversion body of
`build_admission_transfer` into one internal conversion shared by two entry
points. Add:

```
// Projects the events the open admission would contribute if it ended now.
// Pure: reads the durable journal, mutates nothing, advances no watermark and
// mints no receipt identity. Returns an empty projection — never an error —
// for a state that simply has nothing to show yet.
foundation::Result<std::optional<std::vector<domain::PatternEvent>>>
project_admission_overlay(const project_io::ActiveSequenceJournal& journal);
```

`build_admission_transfer` keeps its exact current signature, receipt identity,
collision guard, watermark-prefix selection, checkpoint and durability
contract. A projection must not be expressed by calling the transfer builder
with a synthetic transfer id: a synthetic id that collided with a retained
transfer would return that stale receipt's tail as the live overlay.

An unreconciled switch prefix, an unactivated admission, a completed admission
and an `owner_lost`/`abandoned` journal each project `std::nullopt`. They are
ordinary states of a live recording, not failures, and must not poison the
coordinator.

- [ ] `facade.pattern_admission`: for durable states covering pre-fence,
      mid-admission, held-press, released-press, retrigger, swing/quantize and
      multi-bar candidates, the projection equals the `recoverable_tail` of the
      non-terminal transfer the same journal would build over the same prefix.
      One assertion per state; the equality is the fact under test.
- [ ] `facade.pattern_admission`: a still-held press appears in the projection
      at `kSixteenthTicks`, and the same press appears with its true duration
      once its release candidate is appended.
- [ ] `facade.pattern_admission`: candidates before the admission fence and at
      or after the cutoff fence are absent from the projection, matching the
      transfer's exclusion exactly.
- [ ] `facade.pattern_admission`: a candidate at or after a pending switch
      frame projects `std::nullopt` while the transfer builder still returns
      `switch_prefix_requires_reconciliation`; neither path invents events.
- [ ] `facade.pattern_admission` and the existing Sequence shards: every
      pre-existing transfer receipt — `candidates_sha256`, `first_watermark`,
      `last_watermark`, `checkpoint`, `journal_input_sequence` — is unchanged
      by the extraction. L0 is a refactor; a changed receipt is a defect.

### L1 — Public projection seam on the transport controller

**Defect caught:** the Host has to name a Project I/O type or read the journal
itself to learn what to publish, breaking the Host boundary invariant.

**Files:**

- `packages/application-facade/include/lmdj/facade/pattern_transport_controller.hpp`
- `packages/application-facade/src/pattern_transport_controller.hpp`
- `packages/application-facade/src/pattern_transport_controller.cpp`
- `packages/application-facade/src/pattern_transport_controller_factory.cpp`
- `tests/core/facade/pattern_transport_controller_test.cpp`

**Shape:** mirror `SequenceOverlayProjection` and its `overlay_generation`
de-duplication, which the legacy Host already knows how to consume.

```
struct PatternTransportOverlay {
  foundation::PatternId pattern_id;
  std::uint64_t generation{};
  std::vector<domain::PatternEvent> events;
  bool operator==(const PatternTransportOverlay&) const = default;
};

// What the open recording would contribute if it ended now, for the Host to
// publish as a pending overlay. `generation` advances only when the projected
// content changes, so a Host that publishes on change publishes once per
// change. `std::nullopt` means there is nothing to project right now.
foundation::Result<std::optional<PatternTransportOverlay>> project_overlay();
```

The coordinator owns the generation counter and the last projected content; it
returns `std::nullopt` when not recording, when `close_pending_` has frozen the
candidate set, or when L0 projects nothing. The projection reads the active
journal, so the coordinator recomputes only when something could have changed —
a `retained` admit or an applied receipt since the last projection — rather
than on every call.

`pattern_id` is the coordinator's current binding, which already re-anchors on
an applied switch (#1403); a Host must publish the overlay against that
Pattern, not against its own stale one.

- [ ] `facade.pattern_transport_controller`: before activation and after the
      close is applied, `project_overlay()` returns `std::nullopt`.
- [ ] `facade.pattern_transport_controller`: across a recording with
      candidates admitted, `generation` advances exactly when the projected
      events change and is stable across repeated calls that change nothing.
- [ ] `facade.pattern_transport_controller`: the projected `pattern_id`
      follows an applied switch re-anchor, never the stale vendored binding.
- [ ] `facade.pattern_transport_controller`: a projection call neither
      advances a watermark nor writes the journal — the transfer the
      subsequent close commits is byte-identical to the one it commits with no
      projection call at all. This is the exactly-once guard.

### L2 — Publish the pending overlay on the control cadence

**Defect caught:** the recorded pass stays inaudible until Record is switched
off — the reported defect.

**Files:**

- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`

**Shape:** `TransportEngagement` gains `overlay_pending` and
`published_overlay_generation`.

- `admit_transport_pad` sets `overlay_pending` when `admit()` returns
  `retained`. It publishes nothing inline.
- `service_pattern_transport()`'s early return also continues when
  `overlay_pending` is set, so a steadily recording transport is serviced.
- `transport_continuation_step()` gains an overlay branch **after** the
  existing `publish_pending` commit branch, so a settled close always wins.
  The branch returns without publishing while `pending_pattern_authority()`
  holds a pending switch. Otherwise it calls `project_overlay()`, and on a new
  `generation` calls
  `publish_project_pattern(overlay.pattern_id, std::nullopt, overlay.events)`.
  Success records the generation and clears `overlay_pending`; failure leaves
  `overlay_pending` set and returns the error for the next tick to retry.

- [ ] `host.web_control_runtime`: the transport analogue of
      `test_pending_sequence_overlay_repeats_and_commits_without_duplicate` —
      record several Pad events, service the cadence, and assert the published
      Pattern carries the recorded events **while recording is still open**;
      then Record off and assert the committed Pattern contains each event
      exactly once against the already-published overlay.
- [ ] `host.web_control_runtime`: the transport origin frame is unchanged
      across every overlay publication and across the close — no beat restart.
- [ ] `host.web_control_runtime`: an injected publication failure
      (`fail_next_pattern_publication`) neither fails the Pad trigger nor seals
      the runtime; the next service tick republishes and the events survive.
- [ ] `host.web_control_runtime`: no overlay is published while a Pattern
      switch is pending, and the first publication after the switch applies
      carries the re-anchored Pattern.
- [ ] `host.web_control_runtime`: a burst of Pad events within one control tick
      produces one publication, not one per event.
- [ ] `host.web_control_runtime`: existing transport and legacy Sequence cases
      still pass; the legacy per-event publication path is untouched.

### L3 — Record the shipped behavior

**Files:**

- `docs/quality/2026-09-16-pattern-transport-physical-acceptance.md`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- the corresponding `apps/docs-site/diagrams/*.architecture.json` sources and
  their generated outputs, if the seam changes a documented boundary
- `packages/application-facade/module.json`,
  `packages/web-runtime-platform/module.json`

T-L7 already exists in the ledger (merged in #1518); L3 does not re-add it and
does not flip any row. Rows stay `unverified` until a physical run on an exact
Build produces an evidence file.

- [ ] `scripts/docs-site.sh check` passes.
- [ ] The ledger names the Build that first contains L2 as the earliest Build
      on which T-L7 can pass.

## Version Management

Version impact: required.

- `application-facade` gains a public API surface (`PatternTransportOverlay`,
  `PatternTransportController::project_overlay`). Additive, source- and
  binary-additive to existing callers: SemVer **minor** on
  `packages/application-facade/module.json`, currently `6.1.0`, with
  `api_version` re-derived rather than assumed.
- `web-runtime-platform` changes behavior with no public API change: SemVer
  **patch** on `packages/web-runtime-platform/module.json`, currently `5.3.1`,
  and its `application-facade` dependency pin follows the new Facade minor.
- No Contract identity or Contract SemVer changes: no bundle, journal or wire
  format is altered. The admission journal schema is untouched — L0 only reads
  it.
- No Product Build is allocated by this plan. Read every identity from the
  manifests at implementation time; do not carry the numbers above as
  authority.

## Documentation impact

Documentation impact: required. Affected portal routes:
`/core/modules/application-facade/` (new public transport projection seam) and
`/core/modules/web-runtime-platform/` (the Host publishes a pending transport
overlay on the control cadence). Update the pages and any source diagram in the
same Task that changes the boundary, and run `scripts/docs-site.sh check`
before commit.

## Out of scope

- #1515's owner-loss recovery wiring. L0 builds the converter it will consume;
  consuming it is that issue's Task.
- #1514's diagnostics log surface.
- A Creator event-grid projection. No grid exists today, so #1513's
  "audible and visible never disagree" bullet binds that future work, not this
  plan. Recording that dependency here is not discharging it.
- Any change to the six-transition table, the legacy Sequence path, the
  admission journal format, or the physical ledger's row statuses.
