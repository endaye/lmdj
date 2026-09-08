# Authenticate writers independently of waiting product siblings

## Declared files

- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- `.agents/pitfalls/queue-watchdog-ignores-pending-runs.md`
- This plan.

## Actual observation and change

A read-only GET of `/actions/runs/34155431379/attempts/1` returned `pending`,
null conclusion, exact main control `24ee0c4f79e0fe21a89be8813cb0566948583aa4`.
The same attempt's controller job `101846163697` had started at
`2026-09-07T19:24:10Z` and completed successfully at `19:24:48Z`. Unlike the
earlier generic queued observation, this is the exact endpoint the journal
authenticates. It exposes the remaining gap in PR #809's queued-only handling.
It still does not establish the specific historical exception in the first
failed observer run.

Use one closed aggregate status vocabulary consistent with Runtime.run_state:
queued, waiting, requested, pending, in_progress, completed. Every waiting
aggregate retains #809's actual started, non-skipped writer proof, in addition
to exact run/attempt/source/main/Bot checks. No unknown aggregate status is
accepted. Existing in-progress/completed semantics are unchanged. Parent
waiting is not terminal and cannot authorize a second executor or advance.

## Verification

The exact pending shape failed at the original run-status guard before repair.
Tests cover all four waiting states with a started writer, and reject queued,
skipped or missing-start writer jobs across all four. Requested and waiting are
fixture cases, not claimed remote observations. Existing unknown-status and
wrong identity/source tests remain intact. Run transport, runtime, controller,
full CI contracts and staged ownership before the single Task commit.

Local verification passed: 37 transport, 44 runtime, 43 controller, 66 staged
ownership tests; full CI discovery 1351 tests with one existing skip.

Remote acceptance requires a new authorized observer to retain the original
active request while the executor is nonterminal, then later settle its actual
verdict. This Task performs no remote write, dispatch, cancellation or reset;
no failed O1 run is changed into a pass.

Pitfall impact: recurrence queue-watchdog-ignores-pending-runs. This follows
the same observed O1 run, so extend its existing recurrence description rather
than duplicate the same occurrence row. The transport tests are its companion
mechanism; the original watchdog gate remains intact.

## Documentation Impact

Documentation impact: none — internal authentication fix, no Portal or trigger
changes.

## Version Management

Version impact: none — no Product Build, product identities or release action.
