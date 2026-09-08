# Coalesce automatic wakeups without dropping manual requests

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).
No new test, deployment or release trigger is introduced.

## Observed cause and declared boundary

The live GitHub `self-test-report` concurrency group contained 12 controller
jobs: run `34257998450` held the lease and 11 jobs were pending. That run's
control step succeeded on the new provenance-reader implementation; its report
step was still executing. This is not evidence that settlement/reporting is
complete. Historical callback failures at `event-authenticate` remain separate
observations, not proof of a single universal root cause.

The existing `queue: max` is necessary for manual commands but also retains
every redundant push/schedule/completion observation. Add a distinct workflow
admission group: automatic runs share one running plus one replaceable pending
slot; each manual run has a unique admission group. Keep `cancel-in-progress:
false`. Keep the existing job-level `self-test-report` writer lock, `queue: max`,
permissions and all heavy-job/resource/evidence policies unchanged. The outer
group is not the journal lock and cannot exclude manual settlement/reporting
while a product DAG runs. Actual execution remains controlled by durable state.
Automatic reporting/discovery observations wait for the current automatic
workflow (including its product DAG); explicit manual report/settle commands
remain independently admitted. This trades redundant background polling for
bounded queue growth, not a claim of unchanged report latency during a long
batch. Product results still become reportable after their terminal evidence.

Pending automatic events convey no unique command. A retained push/health
observation reconciles durable state and the complete unprocessed main interval;
an authenticated active completion can settle its exact executor. An irrelevant
callback may still be idle: the independent health tick recovers missed work.
Do not reinterpret arbitrary callbacks as execution authority to obtain speed.
No already-running workflow is cancelled, no journal is reset, and no old
queued run is manually cancelled. Previously created workflows retain their
old configuration and must drain; this cutover does not retroactively erase
the historical backlog. Manual retention still has GitHub's existing queue cap.
Replacing a pending workflow is a platform cancellation and can itself emit
completion/relay callbacks. Those automatic callbacks share the same admission
group, but this Task does not claim zero relay jobs or prove their platform
chain-limit behavior. Measure relay fanout as well as writer queue depth during
remote acceptance. A last retained irrelevant callback still relies on the
existing independent health tick; it is never promoted to generic authority.

GitHub's [concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
defines `queue: single` replacement of pending work and non-cancellation of
running work with `cancel-in-progress: false`. The
[concurrency-group API](https://docs.github.com/en/rest/actions/concurrency-groups)
provides authoritative live queue/lease observations; a workflow creation time
is not proof of how long its controller has run.

Declared files:

- `.github/workflows/self-test-report.yml`
- `tests/build/ci_self_test_report_workflow_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `tests/build/ci_o1_cancel_probe_workflow_test.py`
- `tests/build/ci_o1_claim_probe_workflow_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- This plan.

## Verification and far-side acceptance

Before implementation, add failing regressions against the actual workflow
group expression. Check automatic burst replacement, distinct manual groups,
non-cancellation, unchanged shared short writer lock and heavy-job boundaries.
Use a real Git interval to prove skipped intermediate observations do not omit
their commits or paths. Run full CI contract discovery, staged ownership,
Portal check, final range checks and PR declarations.
Three existing rehearsal/probe tests also prohibited every outer concurrency
group. Replace that blanket syntax check with evaluation of the real manual
and automatic group keys, keeping the actual short shared-lock prohibition and
all probe/job/permission assertions. Do not remove their locking invariant.

The local queue model follows documented platform semantics; it does not
execute GitHub scheduling, cancellation-triggered relay side effects or prove
remote manual-request retention. After
merge inspect the new exact-main run and concurrency-group API, distinguish
new groups from draining old jobs, and retain any unobserved burst/manual or
complete test→persist→Issue→next-batch legs as explicit gaps. Never infer
end-to-end latency or successful product testing from a short controller pass.

## Version Management

Version impact: none

Reason: CI wakeup admission only; Product, Host, Module, Provider, Contract,
Assembly and snapshot identities remain unchanged.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: document automatic wakeup coalescing separately from the shared writer
lock and manual controls. No existing Core/Assembly diagram depicts CI
scheduling, so no architecture diagram source is affected.
