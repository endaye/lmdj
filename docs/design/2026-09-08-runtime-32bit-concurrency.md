# 32-bit runtime synchronization with 64-bit semantics

## Scope and thread authority

This design accompanies the independently authorized Core fix for the ESP32
render-path probe. It retains public signatures and 64-bit frame positions,
counts, epochs and publication identities. It introduces no Host, Contract,
Project Truth change or device deadline claim.

One audio thread calls `render`; one serialized control producer calls the
other mutable operations. Any number of non-realtime observers may call the
seven telemetry APIs. Those readers serialize with one reader-only mutex.
Audio never accesses that mutex. Engine destruction requires all callers to
have left. Stopped state alone is not quiescence: start, stop and stopped
storage mutations require prevention and drainage of callbacks as before.

## Writer ownership and storage

`AudioObservation` and `ControlObservation` in `realtime_engine.hpp` enumerate
the complete value layouts. The scalar members outside the channels are the
authoritative accumulators; recycled output slots are never accumulation bases.

| Domain | Owned values | Lifecycle |
| --- | --- | --- |
| Audio | dequeued events, started/completed/active/canceled voices, audio-invalid and voice-drop counts, callbacks/frames/max block, current Bank generation and applied Bank/Pattern counts, capture count/drop/origin, published outcome/Voice-state counts and drops, dequeued FX, FX processed frames and applied tempo | Control takes over only at callback quiescence; start preserves cumulative Bank/Pattern counts and resets the original per-run fields |
| Control | start epoch, enqueued/canceled events, control-invalid/stopped/drop counts, accepted/reclaimed/rejected Bank/Pattern counts, Pattern superseded/canceled counts, drained capture/outcome/Voice-state counts, enqueued/dropped FX and enqueued tempo | Serialized producer; start preserves original Bank/Pattern cumulative statistics |
| Shared bounded atomic32 | host-input and FX occupancies; pending Bank publications | Original reservation, rollback and release/acquire ordering retained |
| Audio-private transport | rendered-frame frontier and Pattern origin | Separate value channel with control as sole logical reader |
| Pattern ownership | Q and A atomic32 descriptors plus immutable slot payload and audio-local L | Described below; full generation is never a truncated token |

`invalid_events` is the unsigned sum of two independently published 64-bit
counts. Original unsigned count overflow semantics are unchanged. Active voices
are bounded by 128; max block is a uint32 render argument. Queue occupancy is
bounded by Q + P + C: at most 1024 queued entries, one reserved producer entry
and one popped-but-not-yet-subtracted consumer entry. Each producer completes
rollback/publication before reserving another, and each consumer subtracts
before its next pop. Thus the bound is **1026**, not 1024. Every pending Bank
count owns a distinct pending/reserved/in-flight current slot, giving bound 4.

The 64-Pad availability mask remains uint64. A running control read first
acquire-observes pending Bank count zero; all preceding audio mask writes occur
before the final release decrement. Control itself serialized the earlier
increments, so it cannot bypass them by reading an earlier initial zero. The
same control producer cannot publish a new Bank during that read. Its later
queue release orders the read before a future audio mask write. Telemetry never
reads this mask. Stopped mask writes require the existing quiescent handoff.

## Value channel proof

Three preallocated value slots have exclusive W (writer), R (logical reader)
and M (middle) roles, initially 0, 1, 2. Atomic32 M also carries a dirty bit.
All three payloads start with valid zero values.

1. Writer fills all of W, then acq_rel-exchanges W|dirty into M, taking the old
   M index as its new W. No slot access occurs between exchange and index update.
2. Under the reader mutex, a reader acquire-loads M. If dirty, it acq_rel-
   exchanges clean R into M and takes the returned slot as R. It copies R before
   unlocking. Clean reads retain R. The transport reader does the same protocol
   without a mutex because only the serialized control thread calls it.
3. Exchanges permute three exclusive roles. Publication release orders full
   payload writes before the acquiring reader; reader release orders its
   completed old-R copy before the writer may reuse it. Ordinary uint64 accesses
   therefore have happens-before protection, not a seqlock data race.
4. A paused reader holds at most R, leaving W/M available for unlimited writer
   publications. A dirty check followed by a racing publication takes the
   exchange-time M, not a stale remembered index. Serialized readers cannot
   consume dirty twice without another publication.
5. After the last completed publication and a caller-established happens-before
   edge, the final value is either in M or already held in R. The next read gets
   it without requiring any future callback. Start/stop publish normally and
   never reset slot indices or overwrite an observer-held slot.

There is no finite sequence stamp whose wrap could validate a torn value. On a
target implementing exchange with non-spurious CAS that retries using the last
observed word, at most one reader exchange can interfere with one publisher:
that reader clears dirty, and this publisher has not yet set it again. This is
a conditional contention bound, not a wall-clock or hardware preemption bound.

## Publication and transport timing

Control methods that modify counts have a scope-bound publication on every
return, including failed enqueue, rollback, cancellation and drain. Audio
publishes on every render return, including zero frames, and direct quiescent
apply/clear helpers publish their final changes. Start/stop publish both domains;
failed running clear never takes audio writer ownership.

Capture has two earlier consumer handoffs: publish origin before releasing
active state or the first ring event, and publish final captured counts before
releasing idle state. CaptureWriter may drain an event or finish its final drain
before the callback returns, so callback-tail publication alone is insufficient.
Capture telemetry acquire-loads state before reading the value channel, so an
observed idle handoff orders the subsequent final-count copy, not vice versa.

The Native Host serializes CaptureWriter drain and its other engine control
operations with the existing Facade mutex, releasing it before waits and joins.
The Web AudioWorklet reads current Bank generation and Voice-stream health via
the internal audio-owner accessor after render, not through non-realtime
telemetry. This preserves exact-generation acknowledgement and fatal handling
without taking an observer mutex in the callback. The accessor is valid only
on the audio owner or at callback quiescence; it is not a new public Host API.

Transport has its own channel: moving the frontier to callback end would change
Pattern boundary decisions. It is published at the original callback-start
frame increment. A newly applied Pattern's origin is published **before** the
release clearing A. Control reads Q/A then transport, preserving the acquire
handoff to the new origin. Telemetry does not consume the transport R slot and
cannot block control scheduling by holding its reader mutex.

## Pattern descriptor state machine

Q (queued) and A (audio pending) encode 0 for empty, slot+1 for indices 0..3,
and bit 31 for claimed. External authority is still the exact uint64 generation,
Pattern ID and activation frame. The existing generation exhaustion boundary
2^63 is retained as `kPatternGenerationLimit`; it is no longer a descriptor
marker. Allocation never wraps or recycles an external identity.

| Transition | Linearization and owner after transition |
| --- | --- |
| Control prepares/publishes | Fully initialize empty slot; Q CAS(old unclaimed token -> new token), SC, publishes ownership |
| Control supersedes or cancels queued entry | Q CAS(s -> t or 0) wins before claim; only then may control mark old s reclaimable |
| Audio claims | fetch_or(claimed) returns Q's immediate predecessor; audio copies full immutable metadata into L, release-publishes A=s, then SC-clears Q |
| Audio claims empty | RMW temporarily creates claimed-empty; audio clears it and reopens admission without waiting |
| Cancel audio-owned | A CAS(s -> 0), acq_rel, removes activation authority but does not reclaim L's slot |
| Activate | A CAS(s -> s|claimed), acq_rel, uniquely wins against cancellation; apply current/origin then clear A and L |
| Observe canceled activation | Audio's activation CAS fails; only audio releases L's slot to reclaimable, then clears L |
| Reclaim | Sole control thread destroys only reclaimable slots and later may prepare them again |

Nonzero-token ABA cannot substitute a new generation during a control CAS:
that paused control operation is also the only possible reclaimer/reuser.
Audio activation cannot suffer it either: L protects the slot even after A is
canceled. Claim uses RMW's immediate predecessor, not an earlier saved token.
Control may read immutable payloads because it is the only reclaimer; arbitrary
observers may not. Q=0 is not an identity: every failed publish attempt restores
its prepared value and restarts Q/A/transport and authority/boundary checks.

### Admission and bounded claim contention

Before claim, audio SC-stores closed to `pattern_claim_closed_`. Every control
Q modification requires a fresh SC open check; on closed, only control retries.
Audio never waits for control acknowledgement. It performs claim/handoff/clear
and SC-reopens admission on both empty and nonempty paths. All control Q CASes
are SC. A cancellation remains a separate, exact-authority acq_rel CAS.

In the SC order between closing and reopening, a new control check cannot read
open. At most one check predating closure can still lead to a Q modification,
because that serialized producer must finish its one CAS before another check.
An operation delayed across multiple callback rounds still occupies this same
single producer position. Consequently claim sees at most one successful
control interference, including queued cancellation. With the non-spurious
compare-and-retry target implementation, that permits at most one conflict
retry. There is no retry-budget branch dropping an already accepted publication
or delaying its application. Control recomputes timing after retrying admission.
Quiescent stop/start can restore open because no claim is in flight.

This is protocol-level progress. It does not bound interrupt latency, scheduling,
cache stalls or the rest of the preexisting render algorithm. No constant-time
or deadline claim follows from `is_always_lock_free` alone.

## Pattern observations without slot reads

Control publishes epoch, last successfully queued generation/frame, and the
exact last successfully canceled audio generation. Queued cancellation clears
the queued copy but **does not overwrite the audio-cancellation identity**.
Audio publishes epoch, claimed-through generation, current generation and its
pending generation/frame. Claim frontiers are monotone because external
generation never repeats.

For equal epochs, keep the queued copy only when its generation exceeds the
audio claimed-through frontier. Keep the audio pending copy unless its identity
equals the successful audio cancellation. Prefer queued for the reported tuple
and count distinct remaining identities (0..2). With different epochs, do not
associate pending tuples. These are value copies only, never slot references.

This filters stale queued copies after the final callback claims/applies them,
and filters canceled audio copies even if there is no next callback. A later
audio cancellation necessarily required audio to leave the previous L and claim
a newer entry; therefore the last exact cancellation suffices. Start resets both
epoch histories without resetting the generation allocator; stop clears both
pending copies and accounts each still-live descriptor once. Counters are exact
after all relevant writers finish and synchronize with readers; cross-domain
running observations remain best effort, not transactional conservation proofs.

## Verification and limitations

- `audio.value_channel`: low-half carry, final publication, repeated slot reuse,
  a reader paused halfway through copying while 65,537 publications and reset
  complete, and four serialized observers.
- `audio.realtime_engine`: Q/P/C=1026 plus rollback/drain for both queues;
  high/low Pad mask handoff; full 64-bit generation through repeated same-slot
  cancellation/reclamation; audio then queued cancellation with no next callback;
  64-bit transport carry; closed admission with a paused control producer and
  both empty/nonempty audio claims. Original claim/apply Bar-boundary journeys,
  start epoch exhaustion, allocation guards and exact cancellation remain.
  Paused capture handoffs verify origin and final counts before callback return;
  an observer holding the reader mutex cannot block render or its internal
  audio-owner status read.
- `audio.snapshot_publication_stress`: four concurrent observers during Bank and
  Pattern publication/reclamation, plus callback-drained start/stop writer handoff.
  The other three existing audio stress tests remain enabled.
- Host TSan executes these tests; successful compilation alone is not TSan proof.
- Fixed GCC 15.2.0 Xtensa object compilation and disassembly are Core portability
  checks. The later independent Step A must still retain the complete unchanged
  closure in an IDF link, audit all archives and positive-control atomic64 symbols,
  and report map/size and filesystem dependencies. No target execution, I2S,
  callback deadline, jitter, underrun or voice-capacity measurement is claimed.

## Version and documentation

Version impact: none for this source implementation; no independently distributed
Package, Product Build, Assembly identity or persistent Contract changes. Consumers
rebuild from source; no binary ABI compatibility claim is made. Documentation
impact: required at `/core/modules/audio-runtime/`, including its source diagram,
`/platform/native-audio/` and `/platform/web-runtime/`.
