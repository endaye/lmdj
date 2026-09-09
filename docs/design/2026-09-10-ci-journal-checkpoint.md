# Durable checkpoint and replay-cost reduction protocol

Status: design proposal only. No implementation, migration, configuration
change, journal initialization, or live canary is authorized by this document.
Relates to #1089.

This proposal is the future protocol boundary for T7b in
[`docs/plans/2026-09-10-lmdj-ci-reliability-and-cost.md`](../plans/2026-09-10-lmdj-ci-reliability-and-cost.md).
It is intentionally independent of T7a's accepted transaction-local request-
proof reuse (PR1133, merge `bfe0e755c24dd40bc8faea914a511bc3d5d2b603`). On the
same full-history fixture, T7a reduced HTTP calls from 18 to 15. It reuses only
immutable control source/ancestry proofs against one pinned main SHA across a
comment read transaction; workflow identity is refreshed per page, and each
writer run/jobs inventory is refreshed per page. This proposal addresses the
cost of reconstructing state from a long durable journal. Neither change
permits mutable trust or an incomplete history proof.

## 1. Current boundary and problem

The current journal is an authenticated hash-linked event sequence. The fixed
Issue body contains `{head, pending}` and each comment contains one event
envelope. `Journal.load()` reads every comment page, checks exact pagination,
IDs, edit metadata, writer provenance, previous-link continuity, and the
envelope digest before accepting the body head. A pending append is repaired
only when the exact event is visible; an absent or ambiguous append blocks.
These rules are in [`scripts/ci/incremental_batch_journal.py`](../../scripts/ci/incremental_batch_journal.py).

The GitHub adapter separately verifies the fixed repository/Issue identity,
trusted bot and workflow, run/attempt/control SHA, complete job inventory and
comment metadata. Hashes detect changed bytes but are not signatures; trusted
repository-controlled automation is not resistance to a compromised token or
administrator. These limits are explicit in
[`scripts/ci/batch_github_journal.py`](../../scripts/ci/batch_github_journal.py).

Scheduler and report consumers deliberately replay complete authenticated
history before deriving state. The report outbox also requires a complete
authenticated event list and exact delivery receipts; it must not replay a
business POST after an unknown outcome. See
[`scripts/ci/batch_runtime.py`](../../scripts/ci/batch_runtime.py),
[`scripts/ci/report_runtime.py`](../../scripts/ci/report_runtime.py), and
[`scripts/ci/report_outbox.py`](../../scripts/ci/report_outbox.py).

The problem is bounded replay cost as event count grows, not correctness of a
new state model. A checkpoint is safe only if it proves exactly which
authenticated history prefix produced it and if the omitted prefix remains
available for independent audit. A checkpoint cannot, by itself, make deleted,
edited, reordered, or untrusted history disappear.

## 2. Decision and non-goals

The future implementation shall use **signed, content-addressed checkpoints
over an authenticated immutable segment log**, with full-replay fallback. It
shall not use a plain Issue-body snapshot, a locally cached state, a mutable
label, a comment count, an ETag, or a bot-authored hash as a substitute for
historical integrity.

The checkpoint fast path is admitted only when a concrete authenticated
mechanism supplies all of the following:

1. a signature over the canonical checkpoint and its key identity, with
   authenticated key rotation/revocation metadata;
2. an immutable segment or transparency-log proof covering every event through
   the checkpoint boundary, including event IDs, content digests, order and
   count; and
3. an authenticated current tail proof from that boundary to the durable
   journal head, including a proof that no segment or event was deleted.

If the optional checkpoint capability is absent or unsupported, the reader
uses authenticated complete v1 replay. If the capability is present but any
checkpoint, witness, proof, metadata, or publication is invalid or unknown,
the reader blocks instead. Therefore this design does **not** claim that
checkpointing avoids a historical integrity proof. It reduces state-reduction
work only after the prefix proof has been verified.

Out of scope: changing suite selection, scheduler policy, report semantics,
POST retry behavior, Issue ownership, GitHub permissions, retention policy,
release/deployment/channel behavior, or enabling automatic checkpoint writes.

## 3. Proposed authenticated data model

The protocol keeps the existing v1 journal readable and introduces a future
versioned checkpoint envelope. Canonical JSON uses the repository's existing
strict duplicate-key rejection and deterministic serialization rules.

```json
{
  "schema": "lmdj.ci-journal-checkpoint.v2",
  "epoch": "fixed-storage-epoch",
  "algorithm": "controller-replay-vN",
  "prefix": {
    "first_event_id": "...",
    "last_event_id": "...",
    "event_count": 1234,
    "head_digest": "sha256:...",
    "segment_root": "sha256:..."
  },
  "state_digest": "sha256:...",
  "state": {"...": "..."},
  "key_id": "checkpoint-key-2026-09",
  "signature": "base64..."
}
```

`state` is the exact output of the named replay algorithm at
`prefix.last_event_id`; it is not Project Truth, a report receipt, or an
authorization. `head_digest` is the hash-link head at the prefix boundary.
`segment_root` commits to the ordered authenticated segment inventory, not
just the final event. The signature covers every checkpoint field except
`signature` and therefore binds the prefix only; it must not bind a mutable
current tail. A separate authenticated log witness supplies the current root
and tail inventory for each read. The key registry is itself authenticated and
versioned.

The future storage adapter must expose this provider-independent API and proof
contract (the concrete deployment/backend remains an unresolved choice for a
later authority):

- `read_checkpoint_anchor()` returns the exact signed checkpoint, storage epoch,
  key-registry revision and prior-anchor link;
- `read_log_witness()` returns a current append-only root, size, epoch and
  witness ID, plus a proof that the root is a successor of the checkpoint
  prefix root or a precise result that no successor relation is available;
- `read_prefix_proof(checkpoint)` returns inclusion and non-deletion proofs for
  every covered segment; and
- `read_tail(checkpoint, witness)` returns the complete ordered tail events,
  immutable IDs, canonical bytes, metadata and inclusion proofs, or an
  authenticated refusal.

The proof contract requires the adapter to expose, for a requested prefix and
tail:

- exact ordered event IDs, canonical bytes, content digests and segment
  boundaries;
- inclusion proofs for the checkpoint prefix and each tail event;
- an authenticated append-only size/root or equivalent non-deletion proof;
- immutable object identity and metadata sufficient to detect replacement,
  deletion, edit, duplication, reordering and pagination truncation; and
- a stable epoch binding so records from another Issue, repository or storage
  generation cannot be grafted into this one.

The unresolved backend choice must select a concrete system that can satisfy
this API, including authenticated append-only/non-deletion proofs and key
registry lifecycle. A transparency log, a signed append-only object store, or
another provider may be evaluated later, but naming one here without that
authority would not make deployment decision-complete. GitHub Issue body and
comments alone do not satisfy this requirement: their current metadata and
hash chain are valuable detection evidence but do not attest immutability.

## 4. Read and replay protocol

The writer lock protects local anchor/generation transitions, not network
backoff. Capture and proof acquisition happen outside the lock; the candidate
is published only after a short-lock reacquire and exact-boundary
revalidation. The reader performs the following steps in order:

1. Under the short writer lock, capture the local anchor, generation, storage
   epoch and the identity of the optional checkpoint candidate; release the
   lock before any network capture, proof acquisition, retry, or backoff. If
   the optional checkpoint is absent, the provider is not configured, or the
   capability is unsupported, select authenticated v1 full replay. A
   checkpoint is stale only when its epoch/key is invalid or its anchor or
   witness is contradictory; an older prefix with a valid successor witness is
   not stale. Stale, malformed, unsigned, or foreign presented evidence blocks
   (see the decision table below); never invent an empty checkpoint.
2. Verify the checkpoint signature, schema, algorithm support, size limits,
   epoch, prefix ordering, state digest, and key status. Reject unsupported
   algorithms for the fast path rather than interpreting `state` opportunistically;
   if the v1 proof is intact, apply the fallback/block
   precedence in the table below.
3. Outside the lock, verify the immutable inclusion/non-deletion proof for the
   complete prefix, then verify that the separate current-log witness is an
   authenticated successor of that prefix. This is a historical integrity
   proof even when event payload reduction is skipped. Obtain every event after
   the prefix, with the same metadata and provenance checks as v1.
4. Replay only the authenticated tail using the exact named algorithm, starting
   from the checkpoint state. Recompute the event hash chain and compare its
   final event head and inventory to the current witness/root; the event proof
   does not claim to prove derived state. Compare the resulting derived state
   digest and decisions to a complete v1 replay oracle at the same authenticated
   boundary (in shadow mode or required sample), not to the event-tail proof.
5. Reacquire the short writer lock and perform one bounded fresh revalidation
   of the anchor, generation, epoch and current witness. If the exact boundary
   changed, release the lock, discard the candidate and restart capture from
   the newer boundary; do not perform network backoff while holding the lock.
   If the revalidation read or any publication outcome is unknown, block for
   reconciliation. Only after this boundary check may the candidate be
   published. In shadow mode, also run complete v1 replay and compare canonical state,
   event count, final digest and all derived decisions before publishing any
   fast-path result. In enabled mode, retain a sampled or policy-required full
   replay path; mismatch blocks and preserves both diagnostics.

The observable result must be byte-equivalent to complete v1 replay for the
same authenticated history. Equivalence includes scheduler state, active
request identity, debt and outcome maps, report/outbox state, event IDs and
generation; it is not merely equal final status or equal counts. No provider
may execute historical control code to produce a checkpoint. Checkpoint state
is produced by the current reviewed reducer and records its algorithm identity.

The precedence rule is strict: an absent or explicitly unsupported optional
fast-path capability (including an unknown optional checkpoint schema or
algorithm when the v1 proof is intact) may fall back to authenticated v1
replay. Once a checkpoint or provider witness is presented, malformed,
contradictory, or untrusted evidence blocks; an unknown durable publication or
write outcome also blocks. V1 fallback must not conceal those conditions.

### Fast-path decision table

| Observation | Result | Reason |
| --- | --- | --- |
| No v2 checkpoint exists, provider is not configured, or the optional fast-path capability is unsupported | Authenticate and run complete v1 replay | Compatibility fallback; no evidence has been declared corrupt |
| v2 schema/algorithm is unknown but the v1 journal and its complete proof are intact | Authenticate and run complete v1 replay; retain the unknown v2 object for diagnosis | Forward compatibility is a fallback, not permission to interpret unknown state |
| Checkpoint signature/key/epoch is invalid, prefix proof is missing, an event is edited/deleted/reordered, metadata/provenance is untrusted, or the witness contradicts the prefix | Block admission with the exact failing identity; do not hide it with v1 fallback | Detected integrity or trust failure must remain visible |
| Tail retrieval, pagination, root advancement, checkpoint publication, or write receipt is ambiguous | Block or return `needs-reconciliation`; never advance, skip, or retry blindly | Unknown durable outcomes are not absence |
| Fast-path replay completes but state/oracle equivalence fails | Block admission and preserve both states/evidence; do not conceal the mismatch with v1 fallback | A reducer mismatch is a protocol defect, not a green result |

## 5. History edits, deletions and metadata trust

The fast path fails closed on any of these findings:

- an event body or checkpoint payload differs from its committed digest;
- an event is edited, duplicated, reordered, missing, or outside the exact
  authenticated prefix/tail inventory;
- pagination totals, cursors, immutable object IDs, segment roots or append-only
  size proofs disagree;
- author/editor, repository, Issue, workflow, run/attempt, control SHA or key
  provenance is absent, changed, foreign, or not independently authenticated;
- a key is unknown, expired, revoked, or used outside its authenticated epoch;
- an anchor is replaced without the expected previous root, or the current head
  is not the signed checkpoint prefix plus the verified tail; or
- API response loss leaves any write, checkpoint publication, or root update
  unknown.

These are not repaired by recomputing a digest, accepting a newer page, or
trusting a current bot editor. The system records the exact failing identity,
retains the raw authenticated evidence where policy permits, and blocks or
returns `needs-reconciliation`. Authenticated full-replay fallback applies
only to an absent or unsupported optional fast path, not to any finding in
this list. A missing historical record is never treated as “not selected,”
successful, or equivalent to an empty prefix.

## 6. Pending and unknown writes

The existing intent-before-write ordering remains mandatory. A future
checkpoint writer may publish a checkpoint only after:

1. the append intent is durably recorded;
2. the event is visible in the immutable log with exact receipt and proofs;
3. the authenticated tail/head is re-read and the reducer result is verified;
4. the checkpoint signature and anchor publication are visible and verified;
5. the pending marker is cleared only after all of the above.

An unresolved pending append, checkpoint publication, root update, or response
loss blocks checkpoint advancement. Recovery may reconcile an exact visible
write; it may not issue a second POST, skip the event, reset pending to null,
or build a checkpoint from the attempted payload. `report_outbox.py` retains
its current rule that a claimed business POST without an exact receipt is
needs-reconciliation and never an automatic retry.

If a checkpoint is newer than the last independently proven log root, the
checkpoint and root disagree: block and retain both exact identities for
reconciliation. If the current root or checkpoint publication is unknown, also
block; do not discard evidence and silently fall back. A normal append after a
checkpoint is not this condition: it is accepted only when the separate
authenticated witness proves the current root is a successor of that prefix.
An older prefix with that valid successor proof is not a stale checkpoint.
Do not roll the journal head backward or delete the suspect checkpoint.

### Checkpoint generation concurrency boundary

Checkpoint generation binds a candidate to an exact observed prefix root,
generation and storage epoch. Before publishing, it must reacquire the short
writer lock and re-read the anchor and current witness; publication is allowed
only if that exact boundary is unchanged and the candidate's prefix proof
still verifies. If an append advanced the root, discard the candidate as
stale and generate a new candidate from the newer boundary. If a read, write,
or publication outcome is unknown, block for reconciliation rather than
guessing whether the boundary moved. Network backoff and proof acquisition
must not extend the writer lock: retrying later requires a fresh exact-boundary
check under the lock before any publication.

## 7. Schema compatibility and migration

- v1 readers remain the compatibility and recovery floor. They continue to
  authenticate and replay the complete existing Issue journal.
- v2 readers accept only the exact checkpoint schema, supported algorithm,
  authenticated key, and compatible state schema. Unknown fields, algorithms,
  key IDs, epochs or state versions are rejected; they are not ignored.
- A v2 writer must dual-publish v1-compatible journal events and v2 proof
  material until the migration exit below is met. The v1 event chain remains
  the audit source and rollback path.
- Migration is an explicit, separately authorized operation. It first builds a
  checkpoint from a complete v1 replay, verifies it against a second complete
  replay, signs it, and publishes it without changing v1 records. No bulk
  deletion, compaction, Issue rewrite, or automatic initialization is allowed.
- A storage epoch or key rotation creates a new authenticated boundary. Old
  checkpoints remain readable with their historical key metadata; no key is
  silently substituted. A new algorithm requires a new schema/algorithm ID
  and a fresh full-replay equivalence proof.

## 8. Rollout, rollback and stop conditions

Rollout is staged and off by default:

1. **Offline fixture phase:** verify proof validation and equivalence over
   immutable captured histories, including edits, deletion, pagination change,
   metadata substitution, key rotation, unknown writes and corrupted state.
2. **Shadow phase:** production reads still use complete replay; the proposed
   path runs read-only and publishes counters/diagnostics only. Any mismatch
   blocks promotion.
3. **Canary phase:** enable the fast path for an explicitly bounded writer or
   report-only cohort, with mandatory full-replay sampling and an immediate
   full-replay fallback. No scheduler or report write is coupled to an
   unverified fast-path result.
4. **Bounded enablement:** expand only after the measured exit criteria pass
   for the same fixed history and consecutive real report-only observations.

Rollback is a code/config transition that disables checkpoint reads and writes,
leaves all v1 events, v2 proofs, anchors and diagnostics intact, and returns
to complete authenticated replay. It does not reset the head, delete
checkpoints, rewrite comments, rotate keys implicitly, replay business POSTs,
or declare unresolved writes failed. If proof verification, equivalence,
metadata trust, pending recovery or write outcome is unknown, stop admission
and use the reconciliation path.

## 9. Verification and measurable exit

Future implementation authority must name the lowest-tier tests for each
contract. At minimum, tests must prove:

- exact replay equivalence across empty, one-event, long-tail, duplicate-event
  and repeated-command histories;
- rejection of every edit, delete, reorder, truncation, pagination, metadata,
  provenance, signature, key, epoch and root mismatch listed above;
- pending-before/after-write and response-loss recovery with no duplicate
  POST, no skipped event and no unsafe checkpoint advancement;
- v1 fallback, v2 unknown-schema rejection, dual-read compatibility, key
  rotation, migration interruption, and rollback to untouched v1 replay; and
- scheduler and outbox state equivalence, exact receipt retention and no
  business write after an unknown claim.

Exit is evidence-based, not a target request-count reduction. For a frozen
history, record before/after HTTP request counts by operation, bytes/pages
read, events reduced, checkpoint verification time, tail replay time, total
elapsed time, and peak memory. Separately record at least three consecutive
real report-only observations: selected suites, backlog size/oldest age,
blocked/unknown outcomes, full-replay fallback rate, equivalence mismatches,
and authenticated write/receipt outcomes. A burst sample is not a baseline.

Promotion requires zero unexplained equivalence mismatches, zero accepted
history-integrity violations, zero lost/duplicated events, zero unsafe retries,
and zero unresolved checkpoint writes silently advanced, with all negative
fixtures failing closed. It also requires a documented, authenticated
immutable-log provider and key lifecycle. If any metric is unavailable or an
observation is skipped, the result is incomplete—not a pass—and the current
full replay remains authoritative.

## Version Management

Version impact: none.

Reason: this is a design-only proposal for internal CI journal durability. It
allocates no Product Build, Module, Provider, Contract, Assembly, snapshot or
release identity.

## Documentation Impact

Documentation impact: none.

Reason: this round changes no current Portal page, operator command, workflow,
selection policy, runtime behavior or documented source fact. A future
implementation that changes those surfaces must declare the affected Portal
routes and update them in the same Task.

## Authority and deferred work

This document is not implementation or migration approval. No source,
configuration, Issue body, key, journal, checkpoint, deployment, release or
channel state may be changed under this proposal. Future implementation must
be a separately authorized Task with declared files, lowest-tier tests,
staged-ownership checks, current-head review, and an explicit immutable proof
mechanism; until then, complete authenticated v1 replay is the authority.
