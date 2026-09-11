# Durable Pattern recording admission

Date: 2026-09-12. Design for the storage prerequisite of capability
[#1230](https://github.com/endaye/lmdj/issues/1230), supporting Creator migration
U2 and umbrella [#1207](https://github.com/endaye/lmdj/issues/1207).
This document specifies intended behavior, not delivered capability.
Source baseline: `bbdf8d71ecb7641d1f9b6c8915905b4117cad06d`.

## Scope and authority

Implement the durable unresolved-admission dependency in sections 5–6 of the
[global transport design](2026-09-11-global-pattern-transport-design.md).
The user's latest decision supersedes the earlier compatibility proposal: the
product is a pre-release demo, so adopt the new recording format directly without
backward compatibility, legacy readers/writers or automatic migration. Reuse one
journal chain. This is recording recovery metadata, not a new Project Truth schema.
Performance recording is outside this change. This decision does not authorize
deletion of existing user files or unrelated Project bundle changes.

The already merged audio foundation supplies immutable applied boundaries;
it does not make a recording durable. Storage must never infer a missing boundary
from the current Pattern or replay a live input to reconstruct it.

## Ownership and data flow

Project IO owns persistence, identity validation and recovery parsing. The Facade
owns admission selection, musical conversion and existing journal finalization.
The runtime adapter supplies known enqueue outcomes and immutable audio receipts.
Hosts use the Facade, never parse journals. No storage work occurs on the audio
thread. Future asynchronous transport continuations must release the existing
control lane between waits; the synchronous journal API alone does not provide
that capability.

1. Prepare a recording journal and reserve bounded admission storage before
   submitting the audio fence.
2. At the existing post-enqueue/pre-journal point, durably retain each eligible
   candidate with its original input identity and runtime observation.
3. Retain the exact audio fence decision durably before acknowledging its receipt.
4. Select candidates in watermark order. Transfer each classified prefix with an
   atomic journal record containing both its event contribution and receipt.
5. Reconcile normal flush/stop through existing durable command receipts. Retain
   unresolved recovery until its actual obligations are complete.

## Representation and clean-break adoption

Sequence recording sessions use a new explicit format discriminator in both the
active journal header and sealed recovery document. Reuse the existing active
file ownership and recovery discovery paths. Do not place admission data in an
unowned sidecar. Update the active Sequence producers and consumers together;
do not maintain an opt-in legacy-writing path or a dual-format reader. Do not
silently reinterpret an existing old session as a new-format session.

Use the explicit discriminator to prevent accidental interpretation of unsupported
data as a valid new session. Unsupported existing data produces a clear error and
is left untouched. Do not build an old-reader compatibility harness or promise that
old binaries can consume new recordings. Any intentional demo-data reset is a
separate, explicitly scoped operation.

Readers validate the new format's complete record grammar. Old or unknown
formats and unknown record kinds fail closed. Unsupported does not mean empty, complete,
discardable or safe to truncate. Existing torn-tail diagnostics retain the invalid
suffix and identify the verified prefix; no automatic repair is introduced.

Exact format identifiers are to be registered and tested in the implementation
Task against repository contract conventions; this design does not allocate a
cross-language Contract identity or change the Project bundle contract.

## Logical records and identities

All new records use the existing per-record canonical-payload checksum envelope
and writer lease. The existing envelope is not a cryptographic hash chain;
ordering and identity must be validated by the record grammar.
The new grammar contains these logical record types in addition to normal journal
operations; implementation names may differ but semantics may not.

| Record | Required information and validation |
| --- | --- |
| Admission preparation | Session and Project identity, unique operation ID, runtime generation, transport epoch, expected Pattern authority, bounded candidate limit and deadline policy |
| Candidate | Preparation identity, strictly increasing control watermark, runtime frame, Pad Slot, press/release kind, velocity where applicable, original press sequence or existing release correlation |
| Fence outcome | Exact command/epoch/generation, actual effective frame and origin, active Pattern/publication identity, playing state and exact pending-switch applied/canceled decision including actual switch frame |
| Admission closure | Operation identity, last retained watermark B and terminal reason; closure may precede fence resolution |
| Prefix transfer | Stable transfer identity, source watermark interval, complete payload identity, consumed candidates, canonical event contribution and resulting journal sequence/checkpoint needed for retry |

Original live input identity and journal input sequence are distinct. Never
advance journal sequence on timeout, attempted append, or RAM insertion. Exact
duplicate requests reconcile their recorded result; reused identities with
different payloads are errors. Watermarks order equal-frame observations but do
not replace runtime frames with UI timestamps. Validate integer overflow and
cross-session/generation/epoch misuse before any mutation.

A transfer record is the single durable fact for both consumed candidates and
their canonical contribution. It must not require two independent appends to be
atomic. A transfer may consume a prefix with no canonical events, for example
excluded input or a retained held press; replay must reconstruct the bounded
journal-owned press state needed by later releases. Existing event validation and
sixteenth-tick unreleased finalization remain authoritative. Transfer replay is
storage reconstruction, never engine enqueue.

An explicit terminal transfer may have no source candidates: after the prefix has
drained, the user can stop while still holding a Pad. Require durable admission and
cutoff fences, admission closure and an empty outstanding candidate set. Atomically
retain the Facade's existing unreleased-note finalization tail and empty owned-press
checkpoint with the terminal transfer receipt. This operation does not invent an
input sequence or physical release. Exact retry after reopen must recover the same
terminal result, including after the canonical flush has completed.

## Bounds, backpressure and uncertain writes

Each preparation declares finite candidate-count and encoded-byte limits plus a
finite fence-wait deadline supplied by the coordinator. Limits are validated before
preparation; zero, overflow, or values beyond implementation hard caps are rejected.
They are infrastructure parameters, not user-selectable musical behavior. The
implementation plan must set concrete hard caps and test their exact boundaries.

Reserve independent space for one closure record, the outstanding fence decision
and a transfer of the retained prefix. Candidate admission cannot consume those
reservations. Reserving logical space does not guarantee an OS write will succeed;
disk/quota failures retain their ordinary failed/unknown outcomes.

On deadline or the final available candidate slot, close recording admission at B
before processing the next candidate and append the reserved closure reason.
Further live input uses its existing route but is outside this failed recording
attempt. Report recording error/closure pending. Do not evict candidates, grow RAM
indefinitely, or continue reporting successful recording. A later fence may resolve
and drain the eligible retained prefix; loss of the runtime leaves it unresolved.

After an ambiguous write, reread and reconcile the exact record identity under the
writer lease before allowing the ordered drain to advance. A missing response is
not proof of absence. Preserve the verified durable prefix and expose uncertain
suffix identities; do not claim a failed suffix is crash-safe. No live retrigger,
inverse toggle or success synthesis is a recovery action.

## Admission and cutoff rules

Only known accepted presses and the existing successful release-enqueue path
produce candidates. Preserve #725 successful/failed/unknown results even if an
enqueued press never becomes audible. No extra input subscription or gesture model
is introduced. The adapter must demonstrate existing per-slot release correlation;
if that requires redefining #725, stop that adapter Task and report the conflict.

After the admission fence is known, the Facade uses its Pattern origin for tick
zero, not the Record button frame. Select only admitted presses and their owned
releases. A held pre-admission press plus later release is live-only, with no orphan
journal release. Retriggers retain current per-slot behavior.

At terminal cutoff F, candidates stamped at or after F are live-only. An owned
press whose release falls at/after F is finalized by existing unreleased-note
rules, not by a synthetic release at F. The durable control watermark bounds the
retained prefix independently of frame eligibility.

When an exact switch applied at S < F, reconcile its journal boundary at S before
the target segment and terminal F. For S >= F, retain cancellation and create no
segment at S, including the tie. Delayed inspection cannot replace the historical
receipt with later current state. Record-off keeps playback; Play/Stop applies
audio stop before journal flush. IO failure must not undo either known audio fact.

## Recovery and completion

Extend active reread, recovery snapshot, sealing, listing and completion predicates
together. Unresolved candidates, unacknowledged transfers, missing fence authority
or incomplete closure are pending work even when the canonical event list is empty.
The existing `ProjectStore::reconcile_sequence_recovery` must not remove such a
journal via its old event-only completion path.

Sealing retains the complete new recovery state under its new discriminator. A new
runtime starts stopped. If the old fence was never durably retained and cannot be
recovered from its original runtime, present unresolved recovery; never guess the
Pattern, origin, cutoff or switch outcome. Existing original/alternate existing
Pattern recovery routes apply only when the required event authority is known.
Explicit discard remains a separate user operation, not automatic cleanup.

## Acceptance evidence required

Native journal tests and real browser OPFS tests must both cover durable candidate
append, lost response plus reopen, torn suffix, unknown fence, quota/write failure,
terminal reservation, transfer-written-before-response crash, exact deduplication,
and unsupported active/sealed data rejection without mutation. Native filesystem tests cannot
stand in for OPFS flush and reopen behavior.

Facade/runtime tests additionally prove refusal produces no candidate, accepted
enqueue plus failed persistence preserves partial effect, pre-admission held input
creates no orphan, cutoff releases preserve finalization, live routing continues
between transport continuations, and delayed S<F / S=F / S>F decisions produce the
correct journal segments. Each test asserts the far side of its transition, not
only a returned success code. No new test gate without a named defect.

Existing baseline at the source revision: `project_io.sequence_journal` passed
1/1 (test 1.81 s, total 1.95 s). This proves only existing journal behavior; no
new admission or browser acceptance has passed yet.

## Version Management

Version impact: none for this design-only document; no manifests or Product Build
allocation. Implementation requires Project IO API/storage change assessment,
Facade/runtime consumer updates and coherent assembly adoption. Adopt the new
Sequence format directly; no compatibility layer, migration utility or legacy
format support is required during this pre-release demo stage. This does not waive
repository manifest/version policies. New writers, recovery readers and ownership
guards ship together. No release or deployment is authorized by this design.

## Documentation Impact

Documentation impact: none for current portal behavior because this is a proposed
subsystem specification, not an implemented feature or identity change. The source
implementation must update affected Project IO/Facade/runtime ownership and
recovery portal references in its own Task and run applicable portal verification.
The implementation plan must resolve exact routes from portal configuration.
