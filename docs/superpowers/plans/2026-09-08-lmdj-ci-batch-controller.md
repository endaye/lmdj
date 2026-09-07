# T4e — Callable incremental batch controller

## Declared files

- `scripts/ci/batch_controller.py`
- `tests/build/ci_batch_controller_test.py`
- This plan.

No workflow, existing protocol, main history, Issue initialization, permission,
secret, release or remote protection changes. This is callable composition, not
an enabled automatic test service. Parent integrates and ships separately.

## Implementation and public boundary

`Controller(journal, inputs, current_run, run_state=..., result_for=...,
old_runs_terminal=..., lock_held=..., epoch=None).reconcile(explicit=None,
resume=None)` returns `{action, reason, request, state}`. Actions are `execute`,
`idle`, or `waiting`; neither idle nor progress means globally healthy.

The caller holds one shared short writer lock over the entire invocation. T3's
actual `Journal.load/append` and reducer own the durable schema and transition
rules. No additional scheduler database or dispatch service is introduced.
Every returned state transition is loaded from a confirmed journal append.
An uncertain write raises; it never authorizes execution or cursor movement.

An `execute` return is one-use and only follows a newly persisted claim for the
current admitted executor run, attempt 1. Replaying an existing claim never
returns execute again. A lost return can sacrifice coverage: after the old
executor is terminal, verified missing evidence becomes debt. Safety wins over
blind duplicate launches. A same-run persisted admit without claim may still
claim; a different live/unknown executor retains exclusive ownership.

`run_state(executor)` independently authenticates the exact recorded attempt,
returning `running`, `terminal`, or `unknown`. The port must not use the mutable
latest-run endpoint or a suite completion as proof the whole executor ended.
Current-run attempt 2 is rejected. The initial old-run inventory excludes the
currently invoking lightweight controller, which has not admitted heavy work.

`result_for(request, executor)` is invoked only after actual terminal proof:

- `{status: "pending"}`: unavailable API, incomplete visibility, or evidence
  still under reconciliation; keep active, do not fabricate missing.
- `{status: "missing"}`: independently confirmed lost/expired evidence; retain
  missing coverage for every selected suite.
- `{status: "ready", outcomes: {...}, reference: "..."}`: trusted consumer has
  authenticated exact request/target/control/policy/run/attempt and recomputed
  `batch_verdict.scheduler_outcomes`; never copy artifact-owned outcomes.

The result port preserves the complete scoped report at its durable reference,
including mixed real failures and uncovered work. Scheduler outcomes prioritize
debt; that does not erase real failures from the full report. Report API retries
read existing `state.results` and never request new product execution. Scheduler
storage failure still blocks admission/progress even if report business failure
would otherwise be independent.

Results append before advance. None batches return idle with a claimed request,
start no heavy suites, and wait for a later invocation to authenticate whole-run
termination before appending empty/not-required result and advancing. The active
lightweight run is never falsely recorded as terminal.

Explicit node/candidate requests use the existing stable-ID fair queue and full
selection. They preserve their exact target and never change automatic cursor
or debts. Explicit resume commands have stable journal IDs so redelivery cannot
reset retry budgets. No-change automatic calls do not retry debt without resume.
No-change ticks append no observations. After completion the controller rereads
actual main once before admission, coalescing all intervening changes.

## Git and historical policies

`GitInputs(repository, control_sha, read_main, advice=None)` uses read-only Git
with replacement objects disabled. `read_main` must authenticate/fetch the actual
repository main and full history before returning a full SHA. Both main and
selected targets must be commit objects, not tag objects accepted through peel.
Targets/control belong to verified main history. Shallow/missing Git blocks.

T1 `collect_interval` supplies all first-parent per-commit path deltas, retaining
reverted/renamed/deleted paths. Current and each interval revision's JSON policy
snapshots are unioned through T1's cross-policy dependency closure. Historical
Python/workflow code is never executed. Missing interval policy selects full;
missing historical journal request policy blocks replay instead of interpreting
old request digests under today's rules. Every replayed enqueue/admit loads its
request.control policy through the current safe parser.

The optional trusted advice mapper receives the complete Git interval and must
authenticate all PR mappings/records before returning `{complete, labels}`.
It cannot replace the actual Git path floor. This Task supplies no remote PR
mapper; absent/incomplete advice selects full conservatively. Consequently
production docs-none optimization is not claimed until the mapper is integrated.
Tests explicitly inject complete advice for the real Git docs-none case.

An existing first journal event supplies epoch; otherwise explicitly configured
epoch is required. Empty journal never implies a tested baseline or health.
First admission requires an independent exhaustive old-run terminal audit and
full bootstrap. Missing/unreadable checkpoint or deleted tail blocks at Journal;
the controller does not recreate an Issue or silently choose a new epoch.
Non-first-parent/non-ancestor baselines block and require separately authorized
reconstruction/bootstrap, not automatic cursor rewriting.

## Verification and acceptance gaps

Lowest tier: `python3 tests/build/ci_batch_controller_test.py`, plus existing
T3 reducer/journal and T1 tests. After staging all three files, run
`python3 tests/build/ci_change_scope_test.py` and cached diff checks.
No new required gate, timeout widening, coverage reduction or suite de-selection.

Fault journeys exercise the real Journal intent/append/anchor protocol through
a strict in-memory transport: bootstrap → claim → terminal → durable result →
advance → idle; coalesced next tip and completion-boundary change; lost admit,
claim, result and advance response → restart → no duplicate execution/POST;
absent uncertain append → blocked; deleted tail → blocked. Other cases cover
unknown executor, pending versus missing evidence, old unclaimed terminal run,
historical policy migration, explicit fairness/cursor isolation, bounded debt
pause/resume redelivery, none progress retaining product failures, and durable
result reuse after reporter failure. Real Git fixtures cover reverted contract,
docs-none, missing mapper full, absent policy and unpeeled tag rejection.

These tests do not prove GitHub lock ownership, API consistency, artifact
visibility, terminal-job authentication, accepted permissions, Issue persistence,
or actual provider/reporter behavior. Those belong to T4 wiring/O1. The future
workflow DAG must pass execute once to its reusable suite jobs after releasing
the short lock, then reconcile through a separate completion run. `workflow_run`
chain limits require a lightweight recovery tick; no claim of infinite immediate
chains or automatic liveness is made. Health ticks never create tests merely
because the date changes. O1 must prove the tail wakeup, and storage/API outages
must remain visibly blocked. No production fault injection occurs in this Task.

Pitfall impact: none. Existing fail-closed diagnostics, journey completeness and
synthetic-platform boundaries applied; deterministic local regressions are not
invented production incident recurrences.

## Documentation Impact

Documentation impact: none

Reason: Internal callable composition only; no current Portal behavior, Product
Assembly, identity or enabled trigger changes. T5 owns the eventual portal cutover.

## Version Management

Version impact: none

Reason: No product/module/contract version changes, Build allocation, tag,
publication, deployment or Channel promotion.
