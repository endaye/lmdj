# Independent report progress during continuous main execution

Relates to #1048 and the result-driven delivery plan. Source Task; real scheduled
delivery and whole-backlog acceptance remain separate far-side observations.

## Declared files

- `.github/workflows/self-test-report.yml`
- `scripts/ci/incremental_entry.py`
- `tests/build/ci_incremental_entry_test.py`
- `tests/build/ci_incremental_cutover_workflow_test.py`
- `tests/build/ci_self_test_report_workflow_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `tests/build/ci_report_progress_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/plans/2026-09-09-lmdj-report-progress.md`
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`
- `.agents/pitfalls/report-progress-requires-independent-admission.md`

## Behavior

Preserve the scheduler health cron `7,22,37,52 * * * *`, main push and exact
completion recovery. Add a closed report-only health cron `9,24,39,54 * * * *`
with its own coalesced admission group. Manual commands remain run-ID isolated;
the same exact controller job retains the existing short writer lock, permissions,
workflow identity and production storage. No new trusted writer or infrastructure.

The report tick skips control, controller outputs and execution artifacts, calls
the existing authenticated reporting adapter and bounded review discovery, and
cannot admit or execute product work. Python also validates the two exact schedule
roles and rejects the report role at the control boundary. Unknown schedule input
cannot collect new reports; existing authenticated frozen-outbox recovery stays
available through the established report error path.

Keep report failures visible on their own run without changing another run's
durable execution claim. Existing non-execute opportunistic reporting remains;
do not silently remove prompt reporting paths. Do not change suite selection,
budgets, active-batch ownership, debt, unknown POST reconciliation or Issue closure.

The existing completion relay still observes the new report runs. Its authenticated
callback may recover genuinely new main work; report-only means no direct admission
by this tick, not no indirect recovery. Measure whole-chain API/job work, including
relay fanout. Four additional report opportunities per hour are not a strict latency
SLA, free API budget or guaranteed delivery with unavailable evidence/credentials.

## Verification and remaining acceptance

First reproduce report-role control admission and missing independent admission
with failing tests. Drive the actual YAML conditions/admission expressions in a
small explicit queue model: a long active batch plus repeated push replacements,
reports pending independently, and a report failure not cancelling the old DAG.
Use real Entry/Runtime/Git/Journal fixtures for report-only collection while active,
exact receipt and restart without repeat POST, forbidden control and unknown role,
and preserved scheduler recovery. Keep wrong main/attempt/event and missing-source
tests. Queue model does not implement GitHub runner scheduling, cron delivery,
queue capacity or relay-depth enforcement; these remain real-platform acceptance.

Run entry/cutover/report/outbox/event-graph suites, all CI contracts, staged path
ownership, pinned actionlint plus ShellCheck, Portal check and version verification.
Ship exact-head review through normal authorized PR/squash merge; preserve Issue
1048 open until its remote scheduling and cost acceptance are complete.

Local verification on September 9: complete `ci_*_test.py` discovery passes
2,110 tests with the pinned actionlint available; staged ownership passes 66.
The entry suite passes 44 tests and the report-progress journey passes eight,
including report failure followed by successful next-interval admission with
the old failure retained. The new YAML admission checks fail against the prior
workflow. Portal build validates 44 routes and internal links; version checks
pass without allocation. Pinned actionlint 1.7.12 plus ShellCheck 0.9.0 passes
with only the existing `concurrency.queue` schema-lag exception. No test scope,
timeout, coverage floor or admission protection was reduced.

Prior live evidence: manual drain 34302160844/1 took 114 s with no new write;
manual batches(limit=1) 34302347438/1 took 314 s and delivered batch139 Creator
comment5594769827 in Issue865, with exact1286-byte body and generations500–503.
Those runs prove neither the new cron nor a full backlog drain. Follow a real new
report tick through queue/claim/actual receipt/ack/delivered and observe independent
main execution. Reconcile existing state; never dispatch duplicate business writes.

## Version Management

Version impact: none
Reason: reporting control plane only; no Product, Host, Module, Contract,
Assembly, tag, allocation or snapshot identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: document independent report opportunities and their recovery/cost limits.
