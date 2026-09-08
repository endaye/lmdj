# Preserve authenticated writers while their parent run queues product work

## Declared files

- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- `.agents/pitfalls/queue-watchdog-ignores-pending-runs.md`
- This plan.

## Observation and bounded correction

O1 bootstrap run `34155431379` reported aggregate `queued` through the run
endpoint while its exact controller job `101846163697` was completed/success
and product siblings were running or queued. Issue 807's checkpoint named this
writer. A later read of the exact-attempt endpoint reported `in_progress`, and
the unmodified transport authenticated the checkpoint and its three comments.
The generic error in reconcile run `34155641593` does not prove which check
failed earlier. This Task corrects an observed platform-shape assumption; it
does not claim to have recovered the historical exception or turn that failed
O1 run into a pass.

Allow aggregate `queued` only after the existing exact run/attempt, main
control/source, fixed Issue/Bot and unique writer-job authentication. Require
that writer's own start evidence and in-progress or recognized non-skipped
terminal state. Queued/unstarted, skipped, ambiguous and unknown writers remain
rejected. Other unknown parent states still block. No existing journal object,
request, result, active batch or workflow trigger is changed.

## Verification and acceptance

The queued-parent/completed-writer fixture was observed red at the run status
guard before the correction. Companion tests reject queued writers, skipped
writers, missing start evidence and unknown parent states. Existing exact
attempt/source/Bot checks remain exercised by the complete transport suite.
Run transport/runtime/controller tests, complete CI contracts and staged path
ownership before the single local Conventional Commit.

Local results: 34 transport, 44 runtime, 43 controller and 66 staged ownership
tests passed; complete CI discovery passed 1348 tests with one existing skip.

Remote acceptance remains a new authorized reconcile against the untouched
Issue after this fix ships: it must retain the same active request, not emit a
second execution, and later settle only a truly terminal executor. No remote
mutation, cancellation, rerun, reset, protection change or release is performed
by this implementation Task.

Pitfall impact: bump the existing aggregate Actions status pitfall with the
observed bootstrap run and add this exact-writer regression as a companion
mechanism. Historical failure causality remains explicitly unconfirmed.

## Documentation Impact

Documentation impact: none — internal journal authentication correction; no
Portal page, manifest, product identity or scheduling cutover.

## Version Management

Version impact: none — CI transport only, no Product Build or product versions.
