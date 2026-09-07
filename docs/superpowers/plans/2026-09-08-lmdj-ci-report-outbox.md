# Durable report outbox

## Declared files

- `scripts/ci/report_outbox.py`
- `tests/build/ci_report_outbox_test.py`
- This plan.

## Storage and authority

Use a separate fixed, explicitly initialized outbox Issue with the existing
GitHubJournalTransport, IssueBodyAnchor and Journal. The caller supplies that
authenticated Journal and its epoch; no new backend, permission, initialization,
Issue creation for storage or workflow edit is performed by this module.
Never mix these events into the scheduler reducer, which has a different closed
schema. A reporting business write failure must not corrupt scheduler progress.
GitHub service failures still share the same storage failure domain.

All reporting entrypoints must use the same short writer job lock and this
outbox before claiming cross-process duplicate protection. A legacy writer
bypassing it voids that claim. No parent workflow or product DAG holds the lock.

## Durable transitions

Outbox.deliver freezes the actual Report issue/comment bodies, label/assignee
and key/observation into a bounded queue event. Rendering changes under the same
identity fail, not silently replace a pending body. The existing apply_report
still performs issue lookup and ordinary report behavior. Its API proxy persists
an exact POST claim before the single business POST, then records acknowledged
IDs and confirms the unique visible exact body before delivered. Known durable
bucket IDs seed the existing adapter so a stale list cannot create a replacement.
`drain_once` first reconciles claimed work, then may deliver one frozen queued
but never-claimed report without rereading expiring source artifacts. An
unresolved claim pauses this reporting outbox (new reports may still queue),
not the independent product scheduler journal.

Fresh code may execute only a newly confirmed claim's local continuation.
Replayed claims authorize reads only. Death after claim but before POST is
indistinguishable from a lost POST response; an absent/404 receipt therefore
remains `needs-reconciliation` with why/remedy, never automatic retransmission.
This deliberately sacrifices liveness at the ambiguous boundary. Explicit HTTP
refusal is retained and also requires operator disposition, not automatic reset.
There is no claim-expiry timer, reset API or assertion of exactly-once delivery.

Recovery reads a bounded pass, validates unique bot receipt identity and full
body against the frozen payload, then durably records delivery. A delivery is
not successful merely because a loop kept waiting. An acknowledged response
with invisible reads is still pending. Uncertain Journal intent/append/anchor
blocks business writes until the existing storage protocol reconciles.

Issue reopen PATCH remains the existing idempotent exact-issue operation; it
is not a report observation receipt. The module neither closes failures nor
reruns product tests. Delivered records survive ordinary duplicate requests;
known lost/deleted buckets cannot be recreated by a stale-list inference.

## Verification

Lowest tier: cross-process driver fixtures using the real Journal and real
apply_report, new reducer tests, then all CI contracts and staged ownership.
Journeys include lost queue/claim/ack/delivered responses, before-send death,
POST-after-store death/response loss, temporary empty reads/404, exact receipt
reappearance, duplicate delivery, a new observation on an existing bucket,
body/receipt/digest conflict, deleted tail and missing lock.

The in-memory transport reproduces storage faults but not GitHub permission,
last-editor provenance, visibility ordering or lock enforcement. O1 must use
the existing authenticated live transport and a separately authorized fixed
outbox Issue. This task does not wire producers/reporters or initialize it, and
does not claim a remotely operating recovery service.

Pitfall impact: existing storage uncertainty and fixture-shape guidance applied;
no additional production incident is claimed.

## Documentation Impact

Documentation impact: none

Reason: Internal reporting adapter only; no Portal routes or product facts change.

## Version Management

Version impact: none

Reason: No Product, Module, Provider or Contract identity changes.
