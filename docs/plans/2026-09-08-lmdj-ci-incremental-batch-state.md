# T3 — Recoverable Incremental Batch State

Status: local protocol implementation only; no automatic trigger is enabled.
Depends on T1's `test_scope.ScopePolicy` and canonical selection dictionaries.

## Declared Files

- `scripts/ci/incremental_batch.py`
- `scripts/ci/incremental_batch_journal.py`
- `tests/build/ci_incremental_batch_test.py`
- `tests/build/ci_incremental_batch_journal_test.py`
- This plan.

## API and Trust Boundary

`new_state(epoch)` creates unknown-history state, never a successful baseline.
`make_request(policy, ...)` freezes T1 selection, target/control/policy and the
originating run. Admission separately freezes `executor_run` so a queued
candidate can execute in a later DAG than the run that submitted its request.
`required_selection(state, policy, selection)` adds executable
debt to a new interval. `reduce(state, event, policy)` returns a copied state.
Callers authenticate Git/run observations, persist the transition, then act.
The event envelope is `{id, epoch, generation, type, data}`; exact replay is a
no-op, conflicting reuse and stale writers fail with why/remedy diagnostics.

The DAG candidate is prepare/request, claim bound to the current run, reusable
test workflow, result, then advance. No REST dispatch or Actions write is added.
The short writer lock covers only journal transitions; heavyweight execution
does not hold it. Run identity is not an assertion that jobs executed.
If the admitted executor run terminated before execution, an authenticated controller
can record its missing/cancelled suites and advance with debt; a new request is
needed for another run. If termination preceded claim, the trusted reconciler
first persists a bookkeeping claim bound to that old admitted executor, then
its authenticated terminal missing/cancelled result, then advance. This claim
does not authorize execution in the reconciler's different run; the adapter
must not route recovery bookkeeping into the heavy-job launch path. The local
pre-claim cancellation regression exercises this entire settlement sequence;
the actual terminal-run API check remains a T4/O1 acceptance gap.
Historical node/candidate observations do not update
automatic progress, failure references or debt. FIFO explicit requests get the
next free batch boundary; automatic requests cannot jump that queue.

`Journal` requires a fixed issue ID, transport, checkpoint, authentication and
shared-lock ports. `IssueBodyAnchor` uses that Issue's body as a checkpoint
object separate from comments. The checkpoint hash commits to the full event
identity (epoch, generation, ID); it is not a signature. A pending envelope is
written before a comment POST; only its authenticated exact comment can commit
the new head. POST response loss or visibility delay never causes a blind POST
retry. An absent pending comment stays blocked for deliberate reconciliation.
The protocol minimizes duplicate writes at the expense of stopping on ambiguous
outcomes; it does not promise transparent recovery from every possible outage.

The body is intentionally updated, so authenticate its last editor and trusted
writer workflow/run, not merely the original author. Comments must be unedited.
The concrete HTTP/GraphQL transport and run authenticator are T4 work: this Task
provides ports, not fake network validation. State transport errors block new
admission and cursor advancement. Failure-report business writes are separate;
retrying a report does not rerun tests. Artifacts can buffer pending observations
temporarily but are not permanent state or permission to infer missing results.

## Backend Decision and Limitations

Trust repository-controlled automation, not a compromised write token or a
malicious repository administrator. A human editing the body/comment or deleting
a committed comment tail must cause blocked reconciliation. Body and comments
share one service failure domain. Updates use the single writer lock and checked
reads, **not ETag CAS or platform append-only guarantees**. A missing checkpoint
does not bootstrap itself from comments; bootstrap requires the external old-run
terminal audit, complete Git history and a latest-main full request. Historical
health remains unknown after reconstruction.

Official platform references checked 2026-09-08:

- [Issue comments](https://docs.github.com/en/rest/issues/comments): comments can
  be changed/deleted; complete pagination is mandatory.
- [IssueComment metadata](https://docs.github.com/en/graphql/reference/issues#issuecomment):
  editor and lastEditedAt must be checked by the future transport/authenticator.
- [Conditional requests](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#use-conditional-requests):
  documented ETags concern GET caching, not Issue-body CAS.
- [Concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency):
  short shared lock only; finite pending queue is not durable state.
- [Workflow run events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run):
  at most three chained levels. A lightweight reconcile tick must recover chain
  exhaustion and dropped wakeups; a date change alone selects no product tests.

## Verification and Remaining Acceptance

Run both new Python suites and T1 scope tests, then stage declared files and run
`tests/build/ci_change_scope_test.py` for tracked-file ownership. No required CI
gate is added. Assertions cover one state invariant each with why/remedy.

The reducer journey asserts bootstrap audit, request before cursor advance,
active B while C/E arrive, restart, durable result, advance B, then unique E
interval and terminal E. Other tests cover stale epoch/generation, replay,
duplicate claim, none, no-change ticks, debt pause/resume, and historical
candidate fairness/isolation. Journal tests cover pagination/reopen, manual edits,
tail deletion, state outage, missing checkpoint, append response loss, visibility
delay and checkpoint response loss. These are **in-memory protocol tests**, not
proof of GitHub locks, timestamp/editor fidelity, persistence or event delivery.

T4/O1 must implement and demonstrate actual API identity verification, writer
lock wiring, complete Git/run pagination, durable result consumption, main reread
after completion, chain-depth recovery and no-heavy-run none paths. None of
these remote acceptance gaps may be reported as passed by this local Task.

## Documentation Impact

Documentation impact: none — internal protocol implementation remains unwired;
no current Portal behavior or projected product identities change.

## Version Management

Version impact: none — internal CI schema only, no Product/Module/Host/Provider
or product Contract identity change and no release action.

Pitfall impact: none — reviewed existing ledger guidance; protocol failure
injection is planned test coverage, not an observed new production recurrence.
