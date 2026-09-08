# Durable PR Review discovery protocol

Date: 2026-09-08
Baseline: `c846ed8fd9e7349fdcc6dce15b83a24425d8443f`.
Status: pure local protocol Task; no HTTP adapter, storage reservation or activation.

## Declared files and scope

- `scripts/ci/review_discovery.py`
- `tests/build/ci_review_discovery_test.py`
- `docs/plans/2026-09-08-lmdj-ci-review-discovery.md`

One reviewable Task implements only durable PR Review discovery state. The
existing scheduler Issue 807 and outbox Issue 817 retain their closed protocols.
No reducer, transport, workflow, permission or shared manifest is changed.
Actual separate storage reservation, reviewed fixed configuration and HTTP/runtime
integration require later Tasks; no Issue is created here.

## Why a separate discovery ledger

PR review artifacts are retained for 30 days. Existing outbox entries preserve
complete failed-review report payloads, but successful reviews and closed-map
not-applicable results have no outbox entry. Repeatedly scanning a moving 30-day
window therefore cannot prove whether an observation lost before its first scan
was handled. The legacy Core CI producer scan floor is not review provenance.

This protocol retains complete discovered inventories, each exact attempt's
disposition, and explicit missing-inventory or expired-evidence obligations.
It is not a general event platform or a new product scheduler.

## Closed protocol and API

`new_state`, `reduce`, `replay`, `summary` operate on JSON-compatible data.
Configuration is epoch/repository/workflow_id/source_floor; source_floor binds
an exact trusted control SHA and UTC creation timestamp. State schema is
`lmdj.ci-review-discovery.v1`, with generation, inventory_frontier, windows,
normalized gaps, runs and complete seen_events. Only replay from authenticated
events may restore state; an arbitrary serialized checkpoint is not authority.

Every event has exactly id/epoch/generation/type/data. Reusing an event identity
requires the whole original object to match, even after later progress.

- `inventory`: complete half-open UTC window, original first-attempt run records,
  exact total and digest. Partial/count-mismatched inventories are rejected.
  Windows never overlap. Later windows may be inventoried past an explicitly
  retained gap, but the contiguous frontier never crosses that gap.
- `inventory-gap`: missing interval with why/remedy. Overlapping gaps normalize
  into disjoint segments retaining every original diagnostic range/reason.
  Duplicate delivery is idempotent. A complete later inventory removes only
  its actual overlap, preserving both residual sides and original reasons.
- `attempt`: a later attempt of an already inventoried run, retaining the run's
  original creation time. It does not replace attempt 1 or advance the frontier.
  It begins pending independent source admissibility, never automatically valid.
- `disposition`: pending, unresolved, retention-lost, valid-review, closed-mapping
  or failure-queued. Terminal records bind exact original run/attempt, trusted
  control and receipt digest; failure-queued additionally binds an outbox key.
  Unknown or conflicting fields/identities are rejected with why/remedy.

Old error observations cannot downgrade terminal evidence. Retention-lost cannot
be reset to pending: only an exact positive terminal receipt resolves it. The
outbox's business delivery is independent; failure-queued is not delivered.
Inventory progress is separate from unresolved attempts and inventory gaps.
The summary explicitly covers inventoried attempts only; it never certifies
that undiscovered future reruns or business delivery are complete.

## Authentication and future adapter obligations

Reuse the existing authenticated journal transport and short writer lock for a
separately reserved fixed Issue. `complete: true`, hashes and receipt fields are
commitments, not API/workflow authentication. This reducer cannot detect a
caller that lies consistently about a complete inventory; it must never be used
as the verifier of its own inputs.

The later adapter must independently authenticate source-floor/main provenance,
workflow/run/attempt/source/policy and full pagination before appending. Filtered
API page limits require temporal subdivision and explicit overflow, not a
silently truncated list. Missing artifacts stay unresolved; retention loss stays
debt. A run discovered as latest attempt N must still retain its original
attempt and original creation time; callbacks and revisits of known run IDs must
discover later attempts behind the created-time frontier. If the producer
protocol rejects a later attempt, preserve a source gap rather than widening
trust or replacing its first attempt. The pure identity type does not grant
source admissibility.

Queue a verified failure in the existing durable outbox before recording its
failure-queued disposition. A crash between those operations is recovered by
the stable outbox observation/key, not a second POST. The adapter must verify
that the referenced outbox payload belongs to that exact review receipt. Unknown
business POST results remain the outbox's independent reconciliation obligation.

Discovery/report errors must not hide scheduler errors or invalidate an already
durable execute authorization. Actual workflow steps and HTTP recovery are not
implemented or certified in this Task. No automatic trigger is enabled.

## Verification

Lowest-tier `python3 tests/build/ci_review_discovery_test.py` covers complete
multi-page-shaped inputs (not real HTTP), missing pages/counts/digests, interval
boundaries/holes, pending-to-terminal and old-created later attempts, source
gaps, queued failure versus delivery, retention loss and exact resolution,
original-event redelivery after simulated response loss, full-object conflicts,
partial inventory gap repair, overlapping-gap diagnostic retention, immutability
and strict rejection messages. Every journey asserts its far-side state.

Run full CI discovery with pinned actionlint, stage all three files before
ownership, inspect staged/committed whitespace and run the precommit Portal
check with honest missing-dependency reporting. No thresholds or tests shrink.

## Version Management

Version impact: none — internal CI schema is versioned independently; no
Product/Assembly/Module/Provider/Host/Contract identities are allocated.

## Documentation Impact

Documentation impact: none — pure internal protocol and Task record, no Portal
pages or projected product identities. T5 current Portal obligations remain.

Pitfall impact: none — existing strict-fixture/complete-journey guidance applied;
no new platform incident or HTTP fault is asserted from reducer fixtures.

## Local results

- Pure discovery suite: 44 passed, including all gap/partial repair and later
  attempt legs; complete final CI discovery: 1558 passed, no skips, with pinned
  actionlint configured.
- New files staged before ownership: 66 passed. Staged whitespace and the exact
  three declared paths checked; no shared workflow/runtime or Issue changes.
- Precommit Portal check actually ran: exit 1, 57 initial Node tests / 54 passed /
  3 missing-package failures (`glob`, `gray-matter`, `cheerio`). Downstream stages
  were not reached; no Portal pass or dependency repair is claimed.

Commit is local pending independent review. These fixtures are not authenticated
GitHub inventory, hosted recovery, storage initialization or T5 activation proof.

Independent review found Python equality could treat duplicate-event boolean,
integer and float fields as equal before structural validation. Canonical JSON
byte equality now preserves those types while retaining the complete original
seen event. Three new regressions all failed against the original implementation
and pass with the correction (generation 0/False, total_count 1/1.0, nested
attempt 1/True). The original local unpublished commit is amended only under
the reviewer's explicit authorization; no remote history is rewritten.
