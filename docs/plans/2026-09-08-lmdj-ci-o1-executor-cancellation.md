# O1 C2: cancel the isolated claimed executor workflow

## Task and authority

This local adapter Task declares only `scripts/ci/o1_execution_cancel_probe.py`,
`tests/build/ci_o1_execution_cancel_probe_test.py`, and this plan. Base is
`2b8a44e275942e8e37be0d70e0c101cfd9b335b5`. No workflow, manifest, C1 module,
reducer or permission changes belong here. Local commit remains HOLD until
independent review and explicit shipping authority. No remote cancellation,
initialization, dispatch, storage migration or release is performed.

C2 means the exact workflow run bound to a real claim reaches GitHub's
`cancelled` conclusion. The short controller job may already have succeeded;
only its separate diagnostic waiter needs to be interrupted. This does NOT
claim cancellation of the controller process or a running product test. The
C1 plan requires separate design and exact-run cancellation authority; this
plan satisfies the design boundary, not the later authority or live evidence.

## Adapter and diagnostic record

Reuse real `ClaimProbe.prepare/execute`: current-main API authentication,
first attempt, committed fixed-role manifest, empty authenticated anchor,
complete old-run audit, full bootstrap selection and durable observe/admit/claim
verification remain unchanged. No synthetic selection, history or result is
inserted. Ordinary preparation/API failure is not a ready boundary.

Closed intent: `{operation: executor-cancellation, enabled?: boolean}`.
Absent enabled is false, and false performs no API calls. No waiting duration,
arbitrary event, cancellation target or fault count is accepted as input.
Enabled mode requires an independently assigned `o1-claim-cancel-...` namespace
and exact equality to the trusted fixed manifest's claim role. Old C1/A/B
configurations cannot be silently reused to arm this probe.

Only the actual C1 `ControlledExit(87)` boundary can return readiness. Its closed
identity must match current run, attempt 1, control, Issue and epoch, and contain
the verified request ID and journal head. The adapter catches no other exit as
success and rejects a normal return from the claim path.

CLI: `--config PATH --request PATH --root PATH --diagnostic PATH --summary PATH`.
The fresh exclusively created diagnostic path is reserved before admission and
initially contains a false error record. It is never a `result.json` scheduler
action and is never written to `GITHUB_OUTPUT`. Its closed JSON contains only
`schema: lmdj.o1-cancel-diagnostic.v1`, `status: ready|disabled|error`, the strict
boolean `diagnostic_ready`, and `identity` (the closed claim identity for ready,
otherwise null). Failure does not erase or recover journal writes. A stale
diagnostic file rejects before API admission instead of being overwritten.
The diagnostic schema is local handoff data, not a journal protocol, signed
attestation, execution request or test verdict.

## Separately reviewed storage migration

After C1 acceptance, the operator must reserve and independently verify a NEW
Issue/node/epoch for C2, then separately review a fixed-manifest claim-role
migration. Do not guess an Issue here. Keep old C1 storage intact; do not reset
its baseline, debts, comments or checkpoint. Scheduler/outbox roles stay fixed
and all role numbers/nodes remain independently distinct. Initialize only by
an explicitly authorized existing entry after live identity/empty-marker checks.
An empty checkpoint does not prove epoch: the reviewed fixed manifest binds it.

## Later independent workflow Task

Only after the adapter and C1 wiring are integrated may a separate Task alter
`self-test-report.yml`, its contracts and hosted inventory. The short controller
retains its shared writer lock and existing permissions, calls this CLI in its
own exclusive operation and validates the closed diagnostic shape, exact true
boolean and actual run/attempt/control identity. It independently authenticates
the source/context; caller-supplied JSON is not authority. Only that validated
ready record may set a dedicated `c2_diagnostic_ready` boolean. Disabled/error
must not start the waiter even if the controller reports success.

That boolean is NOT action/request/executor and is never read by a product DAG.
The controller emits no executable artifact. A separate hosted diagnostic
waiter runs only for enabled C2, successful controller and the validated true
flag. It has no checkout, token, write permissions or shared writer lock; no
`always()` or cancellation-signal suppression. Give it a fixed five-minute
window, not operator-controlled waiting or automatic retries. Expiry exits
failure and is reported as C2 unexercised, not successful cancellation.

## Actual cancellation and complete acceptance journey

1. Freeze exact reviewed main/control and the new storage identity. Independently
   read complete empty state and authenticate all old relevant runs terminal;
   isolated storage does not waive that global audit. Do not cancel another run
   to make the audit pass. Unknown state stops before admission.
2. Dispatch enabled C2 once. Verify exact repository, workflow ID/path, event,
   branch, head, run and attempt 1 through API. Read complete journal/body:
   observe/admit/claim only, bootstrap/base null, full canonical 16 suites,
   executor equals this run, no pending anchor, result, advance or tested base.
3. Confirm controller complete and writer lock released, waiter actually in
   progress, and no product job/verdict producer/artifact through complete
   exact-attempt inventories. Read the diagnostic identity against the durable
   claim; a hash or boolean alone is not provenance. Expired, queued, failed,
   wrong-head or ambiguous windows do not authorize a cancellation guess.
4. Obtain explicit authorization for this exact run, then issue ONE ordinary
   GitHub cancel request using the authorized operator identity. Do not grant
   workflow `actions:write`, cancel latest/all runs, use force-cancel, or change
   runner permissions/services. An ambiguous POST response permits read-only
   inspection, not a second cancel request.
5. A cancel API 202 is not a terminal conclusion. Independently observe the
   actual workflow `completed/cancelled` and all jobs terminal, waiter cancelled,
   no product execution/producer/artifact, and unchanged complete claim. An
   earlier failure, natural timeout, C1 exit 87 or synthetic fixture is not C2.
6. Run a DIFFERENT fresh ordinary settlement-only attempt after real terminal
   proof. Unknown run/source/API/evidence remains waiting or blocked; it cannot
   be replaced with fabricated cancelled evidence. With terminal no-producer,
   the current Runtime produces missing, persists result BEFORE advance, retains
   all 16 missing debts at attempt 1 and does not invent failures. Active clears;
   processed may reach the target but means processed, not tested or covered.
7. A further fresh ordinary settle must retain every full request/claim/result/
   debt identity and attempt count, make no execute output or duplicate event,
   and preserve unrelated storage. Legitimate new-main observations are allowed
   but cannot clear debts. No execution-enabled reconcile belongs to this test.

GitHub re-evaluates job conditions on cancellation, sends termination signals
and may take time to finish. Do not bypass a lingering cancellation with a
force endpoint: retain the unresolved boundary and stop. Official references:
[cancellation behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation)
and [ordinary cancel API](https://docs.github.com/en/rest/actions/workflow-runs#cancel-a-workflow-run).

## Verification

Lowest-tier tests compose the real C1/Runtime/journal with strict HTTP fixtures
and real temporary Git manifests. Cover default disabled/invalid intent,
wrong role/epoch, old live execution, normal return not ready, malformed
completion identity, real claim-to-ready, claim response loss without repair,
terminal cancelled metadata to all-16 missing result/debt, unknown executor
waiting, and fresh settlement replay with complete record equality. CLI tests
assert strict ready/false records, no scheduler outputs and stale-file refusal.

The local cancelled metadata fixture exercises the consumer, not GitHub signals,
waiter startup, hosted lock release, real token permissions or actual run
finalization. Every remote leg above remains unexercised by this Task.
Run targeted tests, all CI contracts with pinned actionlint, staged ownership,
cached whitespace, final committed-range docs-static and an honest Portal check.
No gate threshold or product coverage is reduced.

Local results: 15 targeted tests and 1,520 complete CI tests with pinned
actionlint passed, with no skips. Staged ownership passed 66 tests and cached
whitespace passed. The first fixture revision honestly failed because it
mutated the source identity of a run that had already initialized the anchor;
the fixture now commits its assigned manifest before actual initialization,
preserving historical writer authentication instead of weakening it. Portal
check ran 57 tests: 54 passed and three failed for missing `glob`, `gray-matter`
and `cheerio`; subsequent validation/build stages did not run. Final committed
range docs-static is checked after the local commit. These are local checks,
not proof of a real cancelled executor or permission to cancel one.

## Version Management

Version impact: none — internal diagnostic adapter, no product/module/provider/
Contract version allocation or release operation.

## Documentation Impact

Documentation impact: none — internal adapter and plan only; no Portal page,
diagram, projected identity or product behavior changes.

Pitfall impact: none — explicit real-cancellation versus fixture and exact-run
authorization boundaries apply existing complete-journey guidance.
