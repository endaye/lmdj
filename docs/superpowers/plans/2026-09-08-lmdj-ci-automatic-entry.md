# Automatic incremental entry adapter

Status: local implementation only; workflow activation and exact-head shipping
review remain separate. Base: `319db6f0` (#847). This Task does not dispatch,
initialize, reset, cancel, publish or deploy anything.

## One Task and declared files

One Conventional Commit in `feat/ci-automatic-entry`, isolated worktree:

- `scripts/ci/incremental_entry.py`;
- `scripts/ci/incremental_storage.json`;
- `tests/build/ci_incremental_entry_test.py`;
- this plan.

Reuse the existing Runtime, Controller and ReportRuntime. Do not change their
protocols, `review_discovery.py`, workflows, runner ownership or permissions.
The prospective T5 workflow owner consumes this adapter only after independent
review and the remaining cutover acceptance. No second scheduler or dispatcher.

## Fixed source and interface

`load_storage(root, environment)` reads only the fixed
`scripts/ci/incremental_storage.json` Git blob at exact `GITHUB_SHA`, never a
dirty file or operator-selected path. HEAD must match an exact commit and Git
history must be complete. The closed scheduler/outbox pair retains the existing
six-field Runtime identities, shared bot/workflow authority and distinct Issues.
Runtime still independently authenticates current main ancestry, exact writer
job and remote Issue/node/editor/event history; the local blob alone is not
proof of remote authority.

The existing main scheduler is #807, node `I_kwDOTK_1fs8AAAABQJKJ5w`, epoch
`o1-incremental-20260908-issue807`; outbox is #817, node
`I_kwDOTK_1fs8AAAABQJfE_Q`, epoch `o1-report-outbox-20260908-issue817`.
Both were independently read as OPEN before implementation. They retain bot
`MDM6Qm90NDE4OTgyODI=` and existing Self-test Report workflow `352307416`.
This manifest neither creates nor initializes those objects, and cannot use
isolated recovery storage #824/#825/#840 as main storage.

CLI is closed:

```text
python3 scripts/ci/incremental_entry.py control --root CHECKOUT --output NEW_RESULT
python3 scripts/ci/incremental_entry.py reports --root CHECKOUT --output NEW_REPORT
```

Only `GITHUB_EVENT_NAME=push|schedule|workflow_run` is accepted, using the actual
`GITHUB_EVENT_PATH`. Existing Runtime enforces main ref, first attempt, current
writer authentication and `BATCH_WRITER_LOCK=self-test-report`; the exact API
event must additionally match the workflow environment. There is no config,
init, dispatch, resume or arbitrary request input. Output must not exist.
The control file remains the unmodified `lmdj.ci-batch-runtime.v1` snapshot,
including the full original request/state and current executor; consumers of
original controller attestations remain compatible. Reports have a separate
`lmdj.ci-incremental-entry-report.v1` diagnostic, never an execute action.

## Control routing and completion authentication

1. Main push requires exact nondeleted `refs/heads/main` and `after=control`.
   Push and schedule call only existing `Runtime.reconcile(execute=True)`.
   No calendar-named product batch, implicit debt resume or healthy baseline.
2. `workflow_run` payload is a hint: reread the exact run/attempt, compare its
   source metadata, independently read canonical repository and stable workflow
   ID/path, and require completed status. The owned source set is Core CI,
   PR Review and Self-test Report, not dynamic display names.
3. Self-test Report additionally uses Runtime's main/event/source authentication
   and actual source-control ancestry. Only its exact identity matching the
   authenticated scheduler `active.executor_run` may reconcile/admit next work.
   A none batch still holds active despite an `idle` action; it must receive
   real terminal settlement. Do not filter by a prior execute action or by the
   presence of product jobs.
4. An unrelated Self-test Report completion returns idle without scheduler
   writes. Core CI/PR Review completion is report-only and cannot reconcile.
   Unknown source or API state is an error, never a synthetic terminal result.

## Reporting and execution isolation

Workflow wiring must first persist the control result and publish
action/request/executor outputs. Only then run reports in an independent step
under the same short writer job, with reporting failure tolerated by that step
and explicitly retained in its diagnostic/summary. Control failure must NOT be
swallowed. ReportRuntime authenticates the same running `Incremental batch
controller` job, so simply moving it to another job would violate current
writer identity. The short lock must never span the reusable heavy DAG.

Core CI completion uses existing `ReportRuntime.execute('legacy', run_id,
attempt)`: its exact attempt, producer source and complete sixteen-suite proof
remain owned by `plan_run`. PR Review completion uses existing authenticated
review receipts and outbox; there is no global main-head filter excluding PR
branches. Neither path calls the old direct business writer.

Push/schedule and legitimate batch completion report current frozen scheduler
results. After control settles a batch, it may already have cleared active or
admitted another executor: reporting therefore accepts the exact source in
authenticated `results`, not only current active. Repeated source callbacks
reuse the outbox identity. Definite unrelated idle/report-only callbacks do
not plan reports or drain the outbox.

Current-writer authentication failure stops everything. After that proof,
source authentication, scheduler reading or report planning failure remains a
visible error but does not strand an already frozen outbox payload: independently
try its ordinary `drain`. Never queue a report for an unverified source. Each
operation retains its outcome; uncertain POST claims use existing receipt-only
recovery, not a repeated business write. Reports cannot overwrite an existing
control result and cannot invoke reconciliation or execution.

## Recovery limits and cutover obligations

The adapter prevents scheduler and business-write self-loops. It cannot prevent
GitHub from creating lightweight callback workflows for an ignored workflow's
completion. The platform's maximum three-level workflow_run chain requires an
independent 15-minute health tick for remaining pending/explicit/outbox work.
That tick is a recovery wake, not daily product testing. Actual callback depth,
payload fields, hosted locks, token access and step/needs isolation still need
the real T5 wiring and platform verification; HTTP fixtures are not that proof.

Current direct event reporting plans before it queues an outbox observation.
Thus dropped callbacks or source/plan failures before queue are NOT permanently
captured by this adapter. The separately assigned review-discovery bridge will
retain PR Review source identities and gaps; do not replace that obligation
with a thirty-day rescan claim. Legacy manual-full lost-event/plan-before-queue
recovery also remains a separate obligation before calling the rollout complete.
Existing frozen outbox recovery is proven here, not permanent source discovery.

T5 must separately remove the daily product cron/missing-daily alarm, switch
all automatic report writers atomically to outbox, connect main push and the
independent recovery tick, and preserve manual full/release evidence authority.
This Task changes none of those triggers or old writer entry points. No runtime
bootstrap, Issue reset or permission expansion is authorized by its manifest.

## Verification

Lowest-tier tests drive real temporary Git, actual Runtime/Controller/Journal
and actual ReportRuntime/Outbox through exact-shape HTTP fixtures. They assert
durable claim before execute; full-pass to real docs-only none admission and
terminal settlement; exact completion to advance; idle completion to no writes;
settled source to business Issue/body/receipt; legacy and PR-branch source
authentication to outbox; error to independent frozen-payload drain; and
unchanged control output after reporting failure. Missing initialization,
foreign source/repository, wrong head/attempt/event, unknown config fields and
aliased identities remain rejected.

The current-event regression was first run red (mismatched actual API event
still admitted) and then green after the explicit current-context match.
Do not interpret fixture-only observations as a historical platform incident.
Run dedicated entry/runtime/report tests, full CI contracts, staged ownership
and whitespace checks. Run Portal check because the manifest and documented
source behavior are touched; disclose missing local dependencies rather than
claiming a pass. Do not lower floors, timeouts, suites or journey strictness.

Local final verification: 21 entry, 59 Runtime, 43 ReportRuntime, 1,594 full CI
contracts and 66 staged ownership tests passed without test skips. The first
full-suite run exposed this test's premature reporter import before the existing
fixture loader registered its exception classes. Importing that fixture first
restored the original outbox/probe fault assertions without changing their
tests or production behavior; the complete final rerun passed. Staged
whitespace and the exact four-file declaration were checked. Portal check
reported 54 passing and 3 failing tests because local `glob`, `gray-matter` and
`cheerio` dependencies are absent; it is not a Portal pass. No real automatic
workflow, model call or GitHub mutation was performed by this Task.

Pitfall impact: none — the new event matching invariant and fixture corrections
are fully captured in behavior regressions. Existing fake-tool strictness
escalation #726 and the real callback/locking acceptance gaps remain open.

## Version Management

Version impact: none
Reason: internal CI event routing and existing Issue configuration only; no
Product Build, Assembly, Module, Host, Provider, Contract or product bytes change.

## Documentation Impact

Documentation impact: none
Reason: this inactive adapter does not change current workflow behavior or
portal operations. T5 activation must update current portal/governance pages
with its workflow change; this prerequisite does not claim that rollout.
