# Pattern transport: who owns a live overlay publication

## Why this document exists

[#1513](https://github.com/endaye/lmdj/issues/1513) asks for a recorded pass to
be audible on the next one without leaving Record. L0
([#1523](https://github.com/endaye/lmdj/pull/1523)) shared the converter and L1
([#1527](https://github.com/endaye/lmdj/pull/1527)) exposed the projection. L2
was to have the Host publish that projection on the control cadence, and that
is where the plan's declared invariant — "a retired generation keeps its
existing authority" — turned out to be unsettled rather than merely unstated.

The issue said these rules "need a bounded design before implementation. Do not
settle those inside an unrelated Task." This is that design. It settles the
ownership question the owner has decided, and it enumerates what is still open
so that no implementation Task quietly picks one.

## The defect, verified

Source audit at `ccf6d375`, reproduced by an L2 working tree whose Host
publishes the projection each control tick. Record-off then fails:

```
cutoff does not match last applied publication
  packages/project-io/src/sequence_admission_codec.cpp:533
```

For a cutoff with no switch, `switches_valid` requires the cutoff fence to name
the admission's last applied publication authority:

```cpp
require(f.pattern_id == previous.pattern_id &&
        f.publication_generation == previous.generation,
        "cutoff does not match last applied publication");
```

`previous` begins as
`{preparation.pattern_id, preparation.publication_generation, admission_fence->effective_frame}`
— the generation `audio_.pattern_generation()` returned when Record opened —
and only `applied_switches` entries advance it. Every overlay publication
advances the engine's publication generation, so by Record-off the cutoff
receipt names a generation the admission has never heard of.

Two further constraints bound any fix:

- **`applied_switches` cannot express a same-Pattern republication.**
  `switches_valid` requires each entry to change the Pattern:
  ```cpp
  require(a.generation > previous.generation && a.frame >= previous.frame &&
          a.pattern_id != previous.pattern_id, "applied switch history regressed");
  ```
- **Moving `segment_generation` obliges a timing profile.** Once the segment
  leaves `preparation.publication_generation`,
  `build_admission_transfer` needs a profile naming the new generation or
  refuses with `segment_timing_profile_missing`. An overlay republication does
  not change the clock, so any profile it writes must reproduce the current
  anchor exactly rather than resample it.

The engine side is already permissive: `realtime_engine.hpp` states that
"ordinary publications may only supersede the same Pattern at the same
boundary", which is precisely what an overlay republication is. The refusal is
a journal invariant, not an audio one.

## Settled: the coordinator owns the publication

**Decision (issue owner, 2026-09-18):** the publication authority and the cutoff
authority that must match it belong to the same owner. The coordinator decides
when an overlay is published and records what that publication created; the Host
contributes only the capability to perform it.

This is the only one of the three candidates that neither adds a durable write
per loop by construction nor changes audio-runtime receipt semantics:

- *Host publishes, admission records each publication* — the authority is
  created by one owner and retained by another, and every loop pays a durable
  write. Rejected.
- *Overlay publication does not advance the bound generation* — an audio-runtime
  change reaching Pattern slots and receipt identity, for a journal-side
  problem. Rejected.
- *Coordinator publishes* — accepted.

"Owns" means decides and records. The Host still performs the publication,
because building a `PreparedPatternView` needs a Runtime Snapshot from the
Application, which the coordinator does not hold and must not acquire.

## Open decisions this design does not settle

Each of these changes what an implementation Task writes. None may be decided
inside an unrelated Task.

### O1 — The port method and its refusal

The Host-implemented `PatternTransportAudioPort` names only Audio Runtime,
Foundation and `std` types. A publish method fits that rule
(`domain::PatternEvent` is already in the public controller header), roughly:

```cpp
virtual std::optional<audio::PatternPublication> publish_overlay(
    const foundation::PatternId& pattern,
    std::span<const domain::PatternEvent> events) = 0;
```

Open: whether the return is `PatternPublication` (carrying `result`,
`generation`, `activation_frame`) or a narrower authority; how a refused
publication is distinguished from a failed one; and whether the coordinator or
the Host owns the retry. The 4-slot pool makes refusal ordinary, not
exceptional — see O4.

### O2 — How a same-Pattern republication is recorded

Three shapes, all real:

- a new durable authority list for same-Pattern republications, leaving
  `applied_switches` untouched;
- relaxing the `a.pattern_id != previous.pattern_id` invariant and letting
  `applied_switches` carry both kinds, distinguished by a field;
- tracking a current publication generation on the admission separately from
  the segment history, and validating the cutoff against that.

The third is the smallest journal change but the least expressive; the first
costs a storage-shape change. Whichever is chosen must state what the cutoff
validation compares afterwards.

### O3 — Durability, and whether exactly-once survives it

If the record is durable, every loop that changes content pays a journal write,
and L0/L1's exactly-once argument — "the projection is a pure read, so the
transfer a close commits is unchanged by any number of projections" — no longer
covers the publication path. That argument must be rebuilt, not assumed, and
`overlay_projection_does_not_disturb_the_commit` in
`tests/core/facade/pattern_transport_controller_test.cpp` must be extended to
cover publishing, not only projecting.

If the record is not durable, state what happens when the owner is lost between
a publication and its cutoff — the recovery path
([#1515](https://github.com/endaye/lmdj/issues/1515)) reads the same journal.

### O4 — Pool pressure and the publication cadence

`kRealtimePatternCapacity` is 4. The L2 working tree hit exhaustion:
publishing every control tick made the later Stop/commit publication fail with
`runtime Pattern publication is unavailable`. That tree coalesces — when a
publication is already queued for the next Bar, the request stays outstanding
instead of burning another slot — which is also musically correct, since at most
one overlay can land per Bar and the next Bar boundary is the audible deadline.

Open: whether that rule belongs in the coordinator once it owns publication, and
what it does when a publication is refused rather than queued.

### O5 — Interaction with a real switch and with the cutoff

The coordinator already withholds the projection for a candidate prefix awaiting
switch reconciliation, and returns nothing while `close_pending_`. Open: whether
an overlay publication may be in flight when a switch publication is queued, and
what the ordering rule is when both want the next Bar boundary.

## What is already settled and must not be reopened

- The six-transition table, restart at Pattern beginning without count-in, and
  Record-off without playback restart
  ([`2026-09-11-global-pattern-transport-design.md`](2026-09-11-global-pattern-transport-design.md)).
- Koala loop-overdub semantics and immediate durable capture
  ([`2026-09-18-pattern-transport-koala-loop-overdub.md`](../../prd/decisions/2026-09-18-pattern-transport-koala-loop-overdub.md)).
- One converter shared by the commit and the projection (L0), and the projection
  as a pure read with a (Pattern, events) generation identity (L1).
- Ledger leg T-L7 in
  [`2026-09-16-pattern-transport-physical-acceptance.md`](../../quality/2026-09-16-pattern-transport-physical-acceptance.md),
  which no implementation may weaken.

## Retained from the L2 working tree

Two findings, independent of the redesign, that the eventual L2 Task keeps:

1. The per-tick publication coalescing described in O4.
2. `service_pattern_transport()` is driven by `bridge.cpp` on every service tick
   in production, but `control_runtime_test.cpp` drives `ControlRuntime`
   directly, so only a `pattern.transport.inspect` turn steps the continuation.
   A Host test must drive the cadence explicitly. This is a test-harness fact,
   not a product defect.

## Version Management

Version impact: none for this document. An implementation Task settling O1 adds
a public port method to `application-facade`, a backward-incompatible change to
an interface Hosts implement, so it is a SemVer **MAJOR** assessment rather than
the minor the projection seam took. Derive identities from manifests at that
time. `application-facade` already owes `6.1.0 → 6.2.0` for L1's additive seam,
deferred to a version cut because
`products/lmdj/assembly.json` pins the module version; see the #1513 comment of
2026-09-18. Do not fold either bump into a feature Pull Request.

## Documentation impact

Documentation impact: none. This is a design document under `docs/superpowers/`,
not an Architecture Portal page, and it changes no implemented product fact. The
implementation Task that settles O1–O5 declares `required` for
`/core/modules/application-facade/` and `/core/modules/web-runtime-platform/`.
