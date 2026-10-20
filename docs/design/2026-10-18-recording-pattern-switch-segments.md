# Global Pattern recording switches: retained boundaries and durable segments

Parent: #2112 / #2233 (S3). This addendum prepares implementation; it does not
lift a Host/Creator gate or complete S3. Integration main at inspection:
`4de2e7ddfe7f170aad3771b40d25333392c0a693`. Before shipping, refresh main to
`6be17e78c3be6a9d12a703f65b80ba712ca23c1f`: S7 is now merged; the Native,
Host, Facade, Journal and SDK premise sites remain byte-identical, and the
Creator Applied-recording selection gate remains. Implementation refreshes
these premises again before each Task.

## Authority and current premises

The [approved switch decision](../prd/decisions/2026-10-10-pattern-switch-while-playing.md)
requires uninterrupted recording across Pattern switches, the existing selected
boundary and latest-unclaimed/claimed-successor rules. The
[Sequence decision](../prd/decisions/2026-08-23-sequence-recording-semantics.md)
and [SR-D11/D23/D26](2026-08-22-sequence-recording-semantics-design.md) own events,
held-note fallback, idempotent flush and recovery. S5 OFF, live BPM preview,
Performance Replay semantics and new recording products are outside S3.

At the inspected source:

- The Host's `pattern.transport.switch` explicitly refuses recording with
  `pattern_transport_recording`. Native selected-boundary publication and the
  SDK forwarding method already exist; do not implement them again.
- `PatternTransportIoOwner` retains a switch through `cutoff` and drains /
  reconciles it at `close`. No production continuation settles it while
  recording continues. `PatternAdmissionOwner` already has source-prefix,
  reconciliation and target-drain operations.
- The current admission codec permits one **unreconciled** applied boundary,
  while its history permits further switches after reconciliation. Do not
  mistake that constraint for a one-switch-per-take format or widen it blindly.
- Native already writes actual per-slot applied generation/frame before its
  release publication of `PatternState::current`. Those facts survive a later
  successor while the old slot is retained. Existing control pins and audio
  borrows prevent reclaim independently. Reuse them, rather than add a realtime
  receipt queue, a frame guessed from inspect time or a transport Fence command.
- The S7 consumer reserves its original count-in caller through actual closing
  consumption. Its `countIn.active` authoring lock also covers Applied recording;
  C4 must distinguish that phase without releasing the original caller.

These are bounded negative sites with the existing playing switches, terminal
single-switch reconciliation and retained Native apply facts as positive
controls. The current three-file documentation Task is declared in the
[Pattern plan](../plans/2026-10-10-pattern-switch-and-count-in.md).

## One musical boundary, separate physical work

Let the actual Native apply frames be S1, S2, ... and the real terminal cutoff
be F. Each recorded segment is half-open: `[source_start, S1)`, `[S1, S2)`, ...,
`[last_start, F)`. A request, prepared view, queued frame or current-Pattern
telemetry alone is not an applied boundary. Each S carries its actual Pattern,
publication generation and retained Native evidence. Quantized switches restart
the target at its own zero origin; use actual S with its actual geometry.

This refines the implementation-order wording of SR-D23 §8.3. “Same boundary”
means audio, input partition and durable segment identity all use the same S;
it cannot mean filesystem operations run in the callback or audio waits on a
writer lock. Native applies at S; the existing dedicated I/O owner subsequently
flushes the old prefix and advances the Journal target. Until that ordering is
durable, retain original-frame post-S input and do not report its durable
completion. Never make an optimistic Project mutation or invent an earlier S.
This follows the already-used Native cutoff -> asynchronous durable-close model.

Two retained recording publication leases bound the unsettled pipeline: the
claimed predecessor and its admitted successor. Within it, keep the existing
latest-unclaimed replacement/current-target cancellation rules. After capacity
is occupied, refuse or retain preparation **before admitting a further Native
publication**, with the actual pending identity; do not drop an admitted switch,
expand input limits, stop recording or consume another caller's authority.
Stop/inspect/matching release remain serviceable while I/O is held.

## Retain the actual Native fact

Add a control-side, move-only publication lease/query over the existing slot
pin storage. Acquire the pin as part of successful recording publication
admission, before exposing it to audio; publishing first and pinning later has
a reclaim window. Failed publication rolls back only its own pin. Normal
playing publication keeps its existing path and resource behavior.

A query verifies the original engine/slot/generation/Pattern authority. It
acquires the slot's published state and checks the matching apply metadata
under the pin. The release publication of current/retired state proves that
actual apply executed at S; a pending view is not Applied. The transport's
announced callback-end frame, and the general audio observation published early
when capture arms, are not completed-render frontiers. Do not infer apply from
those counters or add a new completion channel to prove this already-published
fact. A generation mismatch is not proof of never accepted. Cancellation needs
the existing exact withdrawal/cutoff proof. A later current Pattern cannot erase
an older pinned apply fact.

The slot's apply metadata is written once for that generation. Its acquire
publication and retained pin make a pointer-free copy readable without adding
work to the audio loop. Keep control query/reclaim serialized under the existing
owner contract; I/O receives only copied authority, never Engine or a lease.
Release the control pin after its durable segment disposition/ACK. That is
independent of audio's material/voice last use. Timeout, DTO appearance or SDK
Promise settlement is neither ACK. Runtime replacement waits for actual I/O
owner shutdown/disposition and physical Native quiescence, as it does today.

No extra transport command is used to observe a switch: that would advance or
consume an epoch belonging to Record-off/Stop. Do not change the current public
class layout solely to store another history when the existing storage suffices.

## Durable continuation while recording

For each retained Applied S, in frame/publication order, the same I/O owner:

1. Durably retains its exact existing switch authority before acknowledging
   target-side admission. Candidate frames at or beyond an unretained boundary
   stay pending with their original operation/physical-release identity.
2. Transfers only source candidates before S. Executes each retained source
   flush using its stable command identity and existing manifest/receipt commit
   point. A retry reads the same receipt; it cannot regenerate a flush UUID.
3. Advances the Journal to the target with its actual current bars/fingerprint,
   preserving the original canonical command and recovery residual rules.
   Adds the target's zero-origin timing profile at S through the existing
   profile mechanism, then admits/drains its retained candidates in order.
4. Confirms that reconciliation is durable, then permits the next boundary to
   enter the existing one-unreconciled Journal grammar and retires only this
   publication's control lease. Recording stays active throughout.

Several boundaries may have become Native facts while the worker was held;
process their retained proofs in order, not only the latest current Pattern.
A -> B -> A uses distinct publication/segment identities. Returning to A must
include its already acknowledged notes, whether they are in Truth or retained
admission/overlay state; cooking an old A view and later overwriting its first
flush is forbidden. If the target material cannot yet be prepared correctly,
keep preparation pending/refused before Native admission instead of assigning
it a fictitious apply frame. Snapshot remains immutable derived state.

Keep the current Journal format and one-unreconciled invariant. A proposed
format or timing-semantic change requires an explicit design/version follow-up
before code; do not relax decoder/recovery validation to accept missing history.

## Press/release, cancellation and closure

A press before S belongs to the source; a new press at S belongs to the target.
A source press already flushed while still held keeps SR-D26's existing
240-tick fallback, clamped to that source Pattern. Its later matching release
settles the original physical/input owner and cannot invent a target press or
rewrite an already completed flush. A release at S is outside the old prefix.
A reused Pad Slot does not make an old press_sequence the owner of a newer
press. Preserve original ordering, velocity, integer timing, quantize/swing,
overdub keys and canonical event sorting.

Before-apply cancellation does not advance the Journal. A claimed apply that
wins cancellation remains a real segment. At terminal F, use the existing
strict S < F applied-before-cutoff rule; a boundary cancelled at F does not
create a target segment. Native Record-off/Stop captures F promptly even while
I/O is held, then reconciles every admitted/applied boundary and the last
`[start,F)` prefix before actual completion. Record-off continues playback and
republishes the **actual terminal current Pattern**, not the original config
Pattern or a still-queued target. Stop remains stopped after closure/reopen.

Crash tests cover switch retain, source transfer, pending flush, manifest commit,
target switch/profile, target candidate and terminal close. Acknowledged data
must remain recoverable exactly once in its owning Pattern; unacknowledged
originals remain unknown/retained rather than being reported as discarded or
success. Keep deletion/range/fingerprint recovery precedence and repeat-recovery
idempotency. Do not turn a fresh revision into permission to append to a changed
Pattern.

## COUNT-IN and Performance coexistence

COUNT-IN's scheduled receipts identify its original schedule material and S0.
The existing Native status deliberately keeps that original identity even when
its genuine later cutoff supplies F. The ordinary cutoff receipt separately
carries the actual current Pattern/origin. Preserve that distinction: do not
rewrite the original schedule ticket to B, pass the ordinary current identity
through the strict scheduled decoder, or add a second companion merely because
those identities differ. The existing same-schedule SDK checks remain valid.

S3 publication does not consume a transport epoch. S7 keeps its original caller
through Record-off/Stop and positive terminal consumption; the final I/O owner
closes the actual last segment from the real cutoff. Native's original S0
metronome exclusion stays original; a later ordinary switch's downbeat is not
that scheduled S0. Before Applied/opening completion and during cancellation /
settlement, Pattern controls remain locked. BPM/structure editing retain their
current recording restrictions.

Every applicable global-recording publication source goes through this retained
boundary path: Sequence arrows/picker and ordinary Perform Launch. The current
single-Project recording rule admits one active Journal kind: Sequence begin
and Performance draft begin both reject an already active recording kind.
The approved switch decision keeps Performance-record Launch as its existing
recorded event; it does not introduce simultaneous Sequence/Performance takes.
That path therefore keeps its own Native publication, clock and event/replay
shape, without acquiring a second global recorder. C3 proves both mutual-
exclusion directions before effect, plus the positive existing Performance
Launch path. This corrects the initial implementation premise that a live
Performance-record publication could also feed an admitted global take; it
preserves the settled one-Journal rule rather than widening concurrency.
Keep the existing shared physical-gesture quota and publish each request once.

## Bounded implementation Tasks and acceptance

The following are candidate owners, not permission to edit a wildcard. Freeze
each Task's exact files, source premises, lowest tests and version/doc impact
before implementing it; one Task is one commit.

- **C1: retained Native publication lease/query.** Existing realtime-engine
  header/source and owning audio unit/stress tests. Prove independent absolute
  S, delayed observation after a successor, slot pressure/reclaim/reuse,
  cancellation/claim races, generation mismatch, move/release once, scheduled
  material coexistence and unchanged ordinary publication. A test must fail
  against the rebuilt old producer; no new callback queue or blanket CI gate.
- **C2: durable segment continuation.** Pattern transport coordinator and I/O
  owner, admission owner/current Journal codec and their owning Facade/Project
  I/O integration/restart/stress tests. Prove A -> B -> A at actual frames,
  held I/O and reserved release/Stop, each crash/commit boundary, repeated
  operation/recovery and actual last-Pattern closure. Keep each admission and
  closure far side; do not replace the journey with a final events assertion.
- **C3: production Host/SDK wiring.** Current control-runtime production port,
  existing protocol/session/types/tests and the applicable Performance producer.
  Remove the recording refusal only after the real coordinator path is ready.
  Reuse existing request/inspect shapes and SDK forwarding; prove legacy
  decoders, original count-in identities, actual current binding, refusal /
  unknown results and original budgets. Do not invent an absent API premise.
- **C4: Creator consumer.** App transport/Sequence/Perform gates and owning
  component/packaged journeys. Enable only the applicable recording phase;
  show requested/queued/actual truthfully. Prove repeated mixed-source switches,
  S-1/S/S+1 input and crossing holds, Record-off/Stop, complete per-Pattern Truth
  and reopen for both immediate and COUNT-IN recording. Retain original S7,
  ordinary recording, Performance and snapshot-failure/recovery journeys.

Each Native/Facade persistence/concurrency Task owns its integration/restart/
stress checks. Use existing deterministic barriers and named scenario tables;
new deadline cases retain their own shard and original operation bounds.
Complete candidate/full lanes and physical listening remain separate A01 facts.
Current Portal pages/diagrams are updated by the implementation Task that changes
their source facts, not by claiming this preparation delivered the feature.

## Version Management

Version impact: none for this three-document preparation. No Product, Module,
Host, Provider, Contract or Channel identity is allocated. Implementation records
actual API/ABI/format debt in #2237: additive methods/types with preserved old
layouts differ from a changed public layout or wire/Journal contract. Check the
real delta under the canonical policy; do not guess a version or repeat the
historical settlement. Product/candidate snapshot allocation remains V01.

## Documentation Impact

Documentation impact: none — this Task changes design/plan authority only, not
current Portal behavior, diagrams or product source. Subsequent implementation
updates its affected module/platform/Creator routes and owning diagrams with
its actual delivery, then runs the applicable Portal check.
