# O1 C1: durable execution claim before output — design only

Status: design-only delivery of the previously reviewed local design commits
`a96abc66fcda0d92d9900b53d10d3cee0474d621` and
`c389501b2fbb5f3ae40d6d482fa1b07943cad298`, now based on main
`dc1e57622136b019aab1a514298ff252a0c32ae6`. The design below records its
original prerequisite boundaries, not the current progress of separately owned
configuration, initialization or implementation Tasks. This delivery still
requires exact-head review. No adapter, workflow wiring,
reservation, initialization, dispatch or cancellation is authorized by this
document. C1 is controlled process exit after a real claim, not GitHub
cancellation, lost HTTP response or cancellation of executing product tests.

## This documentation Task

Declared file: this plan only, on an isolated `docs/` branch. Lowest-tier
verification is docs-static/whitespace and staged new-file ownership. A Portal
check, if run, must retain its actual result; no local check is remote O1 proof.
Preserve this documentation Task separately from any later implementation.

Precommit verification: staged new-file ownership passed 66 tests and staged
whitespace passed. `scripts/architecture-portal.sh check` ran but exited 1:
57 initial Node tests, 54 passed and 3 failed for missing `glob`, `gray-matter`
and `cheerio`; later Portal stages were not reached. No dependency repair or
Portal pass is claimed. The initial docs-static command inspected an empty
committed range while this new file was staged, so it was not proof of the new
document; rerun docs-static against the actual documentation commit range.
The subsequent manifest-prerequisite documentation Task also reran staged
whitespace and all 66 ownership tests successfully, and reran the Portal
command with the same 57/54/3 missing-dependency failure. It does not amend the
original design commit and makes no implementation or remote-acceptance claim.

The isolated documentation delivery reran 66 staged ownership tests and staged
whitespace successfully. Its actual current-policy selection for this sole plan
is `none` with no suites. Portal check again ran 57 tests: 54 passed and three
failed for the same missing dependencies; no later Portal stages ran. This
delivery adds no manifest or code and retains every remote journey as a separate
acceptance boundary; local commit does not authorize shipping or a dispatch.

## Later implementation Task and file ownership

Subject to root review, one adapter Task declares only:

- `scripts/ci/o1_execution_claim_probe.py` — narrowly compose existing Runtime,
  authenticate an isolated initial snapshot, invoke real bootstrap admission,
  verify the committed claim, and exit before any executable output.
- `tests/build/ci_o1_execution_claim_probe_test.py` — real Runtime/journal/Git
  and strict HTTP fixtures with far-side recovery and debt assertions.
- This plan — implementation evidence and explicit remaining gaps.

A prerequisite configuration Task, separate from the three-file adapter Task,
owns `scripts/ci/o1_recovery_storage.json` and its own declared configuration
tests/plan. It cannot populate values until root has actually reserved and
independently verified the new A/B/C storage identities. Missing configuration
must fail closed; no fabricated IDs or placeholders authorize a probe.

A separate root-owned workflow Task may later change
`.github/workflows/self-test-report.yml`, its dedicated workflow contracts and
its own plan. Do not modify Runtime, controller/reducer, reporting, policy or
A/B response-suppression probes to implement C1. If the real interface cannot
support the claimed invariant, report that fact rather than silently expanding
this Task. There is no waiting window, cancellation mode or cancellation client.

## Existing boundary and authority

The inspected source baseline is `c2932ab2fcf43f6643bbd78a160a8ec1b4eb9eaf`.
Recheck these actual functions after implementation dependencies land:

- `batch_controller.Controller.reconcile`: persist admit, persist claim, then
  return the execution action. `_persist` verifies the journal replay equals
  the reducer's expected transition before returning.
- `batch_runtime.Runtime.reconcile`: authenticates current main controller and
  passes `execute=True` to that controller. It does not dispatch another run.
- `batch_runtime.main`: writes `result.json` only after Runtime returns.
- The current workflow calls that CLI with `check=True`, reads the result,
  then writes action/request/executor into `GITHUB_OUTPUT`. Its reusable batch
  job runs only from the controller's `execute` output.

C1 composes the Runtime interface directly. It deliberately stops between its
verified in-memory return and serialization. It must not call the ordinary CLI
and then hope to delete a previously written execute file, or emit an action
and rely only on a later failing step to suppress heavy jobs.

Use one NEW separately reserved/initialized scheduler Issue with fixed numeric
and node identities, new explicit `o1-claim-...` epoch, existing workflow/bot
authority, actual current main, fresh attempt 1 and the same existing
`Incremental batch controller` short writer lock. Storage cannot alias #807,
#817, #819 or the separately reserved A/B storage. Use the reviewed fixed-path
role manifest described below, NOT an operator-supplied arbitrary denylist.
No auto-init or history reset.
Existing contents:read/actions:read/issues:write permissions remain unchanged.

## Verified empty-anchor limitation and manifest prerequisite

The current initialization protocol does NOT bind an epoch into an empty
checkpoint. `batch_runtime.Runtime.initialize` writes a writer identity and
`payload: {head: null, pending: null}`; neither object includes the configured
epoch. Only later events carry it. In a local real-Runtime/Git/HTTP-fixture
reproduction, initialization with `o1-recovery-example` followed by a new Runtime
using the SAME Issue/node and `o1-claim-example` passed `authenticate_current`
and `journal.load() == []`, with identical checkpoint bytes and no second write.
This is a verified existing protocol boundary, not a remote incident.

Consequently, the adapter must never claim that an empty authenticated Issue
proves its supplied epoch or role. An epoch-prefix check alone cannot exclude
reuse of a newly initialized A/B Issue. Do not migrate the journal schema or
change initialization to satisfy that false assumption in this Task.

The selected prerequisite is a closed role map at the trusted fixed path
`scripts/ci/o1_recovery_storage.json`. Its only roles are `scheduler`, `outbox`
and `claim`; each value contains the existing six Runtime configuration fields:
repository, issue_number, issue_node_id, bot_node_id, workflow_id and epoch.
All THREE numeric Issue identities must be pairwise distinct, and independently
all THREE node identities must be pairwise distinct. Repository/bot/workflow
authority must agree; existing protected Issue rejection remains. Roles have
explicit recovery/claim epochs, with no operator-defined role aliases.

Actual values may be committed only by the later configuration Task after root
reserves real storage and independently checks its exact repository/Issue/node/
writer authority. This plan supplies no Issue number or guessed future value.
No arbitrary manifest path, denylist or manifest body is accepted from inputs.
The C1 adapter reads the exact fixed-path blob from its reviewed current-main
control revision as DATA, independently authenticates actual current main and
workflow/run identity, and requires its complete runtime config to equal the
manifest's `claim` role. A dirty local file or an operator-supplied JSON copy
cannot substitute for that immutable Git blob. Missing, malformed, duplicate,
role-aliased or identity-conflicting manifest fails before any remote write.

The Issue is still independently authenticated by the existing transport; the
manifest binds operator intent to an assigned role/config, not a replacement
for Issue/run authentication. For an empty same-Issue config with a changed
epoch, equality to the trusted `claim` entry fails before writes. For A/B Issue
reuse, numeric/node role uniqueness plus equality fails independently of the
fact that its old empty checkpoint has no epoch. Tests must demonstrate both
cases using the real initialization shape, alongside missing-manifest refusal.
Historical nonempty journals retain their existing event-epoch validation.

The three-file adapter remains blocked on this concrete reviewed manifest.
This documentation update authorizes neither adapter implementation nor live
reservation, configuration shipping, initialization or dispatch. C2 cancellation
remains a separate unimplemented authorization boundary.

The operator intent is closed: only C1 operation plus explicit enabled/disabled
selection; disabled is the default and the entire invocation makes zero writes.
No arbitrary event, selection, endpoint, body, executor or fault count is input.
Run ID is not guessed before dispatch: trusted same-controller preparation
derives actual run/attempt/control after independently authenticating API/env,
complete Git/policies, exact storage identity and an empty authenticated anchor
and comment inventory. Preparation cannot repair pending state. Recheck before
the first write; source/main/storage drift stops.

## Preserve the real global old-run audit

An empty state necessarily selects real bootstrap full, including all 16 suites
from the historical canonical inventory. The probe must not replace it with
none, a fabricated baseline or a diagnostic pseudo-suite.

`Runtime.old_runs_terminal` checks all relevant nonterminal states of Core CI
and Self-test report, excluding only its existing authenticated unadmitted
wakeup cases/current lightweight controller. Fresh isolated storage does NOT
exempt this global audit. If the current full run or another possibly admitted
run remains active/unknown, C1 returns an explicit not-armed/blocked diagnostic
and no execute output. Do not override this callback, cancel the current run,
filter away an inconvenient job, force an active bootstrap or call that state
a successful injection. Wait for natural terminal state and separately retry
only where the stored state and declared command permit safe preparation.

The probe must preflight the existing old-run audit before admission. Runtime
may still append an observe if a race makes its later audit block; disclose
that nonempty state and stop instead of repeatedly invoking an injector that
claims an empty starting point. Ordinary authenticated recovery owns it.

## Complete C1 journey

1. Independently snapshot the fresh Issue/epoch, empty checkpoint/comments,
   current main/control and exact run/attempt/job. Confirm old runs terminal.
2. Execute real `Runtime.reconcile(execute=True)` in the non-outputting probe.
   It must persist actual observe/admit/claim through existing APIs. No synthetic
   events or response documents replace that path.
3. Authenticate complete persisted history and exact final checkpoint. Assert
   the new request is bootstrap, base null, target/control frozen current main,
   canonical full inventory, executor equal this actual run/attempt, one admit
   and one claim, no pending anchor, no result/advance. Compare the returned
   request with the durable request; a digest alone is not writer authority.
4. Only after those assertions, exit nonzero with an honest C1 diagnostic.
   Do not write `result.json`, execute/request/executor outputs or a substitute
   executable artifact. The eventual workflow uses a distinct diagnostic step
   excluded from the ordinary control step and incapable of feeding its outputs.
   Errors before the boundary remain ordinary failures, not completed C1 proof.
5. Read the actual platform run after it is terminal: controller failed,
   reusable/product jobs absent or skipped, no selected verdict producer or
   verdict artifact. Verify all jobs through a complete exact-attempt inventory.
   Save actual storage/run IDs and full bytes, not only a green/failed badge.
6. Dispatch a DIFFERENT fresh first-attempt ordinary settlement-only run with
   no injecting adapter. If source/API/run/job state is unknown, it must wait
   or error without claiming missing evidence. A successful upload whose
   artifact is temporarily invisible must retain the existing pending behavior.
7. For this genuinely terminal no-producer/no-artifact run, existing
   `Runtime.result_for` returns missing. Persist result before advance: all 16
   selected suites are missing with `missing:<request-id>`, never passed,
   never fabricated cancelled verdicts. The bootstrap processed cursor can
   move to its target, but this means processed, NOT tested/covered. Active
   becomes null, each selected suite retains missing debt/attempt 1; failures
   remain unchanged rather than invented from absence.
8. Another fresh ordinary settle must not emit execute, recreate the old
   request/claim/result or increment its debt attempts. Legitimate new main
   observations are allowed; no blanket byte-equality assertion may conceal
   real main drift. Compare the complete original request/result/debt identities.

There is no real heavy run in this journey. Do not call a post-settlement
execution-enabled reconcile merely to demonstrate debt selection: that would
authorize actual product testing and belongs to a separately scoped operation.

## Genuine documentation-after-failed-claim leg

The acceptance goal is that documentation cannot launder unresolved coverage.
After the C1 failure and ordinary settlement, use only a GENUINE later main
revision whose complete first-parent interval from the processed target has
actually been verified as safe explanatory documentation by the existing Git
collector and historical policy. Do not create a fake product modification,
rewrite Git/history, seed a cursor, suppress commits or invent commit counts.

Read that genuine interval and retain exact base/target/commits/paths and the
actual classification. A fresh ordinary settle may observe the new main but
must retain every existing debt and failure, leave processed at the settled
target and emit no execute. Independently project the next required selection
using existing `batch.required_selection`: even if the true interval's floor
is none, all executable debts still require coverage. This is a read-only
selection assertion, not another execution or a fabricated pass.

If intervening main commits are not solely safe documentation, report this leg
unexercised. A mixed interval can still prove debt retention, but cannot be
renamed a documentation-only acceptance case. Do not arrange unrelated merges
or manipulate another active batch to manufacture the required history.

## Tests and unproven boundaries

Lowest tier is the new Python suite with actual Runtime/controller/reducers,
authenticated journal HTTP fixtures and real temporary Git histories. Cover
disabled zero writes, bad source/identity, nonempty/pending state, old active
run blocking, successful durable full claim before output, original HTTP error
not masked, active/unknown executor wait, terminal missing result/debt,
duplicate fresh settle, and full docs-delta debt retention projection.

Every transition needs a far-side assertion: exact full bytes and writer/run
binding, no output files/execute bridge, missing evidence before progress,
unchanged old claim/result/debt on replay. A synthetic docs commit is valid only
inside local fixture tests and is never remote documentation-leg evidence.
Workflow tests must prove the diagnostic command cannot feed ordinary outputs
even on accidental return. Local fixtures cannot prove hosted locking,
concurrency timing, token scope or real process finalization.

C2 actual GitHub cancellation requires a separate design and explicit exact-run
cancellation authorization. C1 does not implement waiting/cancel, prove actual
GitHub cancellation or cancel executing product tests. Claim-before-send,
response-suppression A/B, product failure diagnosis, reporting mutations,
automatic trigger cutover and release operations are not delivered here.

## Version Management

Version impact: none — design of an internal diagnostic adapter, no product,
module, provider or Contract identities change.

## Documentation Impact

Documentation impact: none — plan only, no Architecture Portal pages or
projected source facts change.

Pitfall impact: none — applies existing fixture-strictness, acceptance journey,
unknown-API and no-invented-evidence guidance; no new remote incident occurred.
