# Primary REST quota exhaustion is unknown, not dead

## Task

When GitHub REST `X-RateLimit-Remaining` hits 0, Incremental Completion and
the self-test controller fail closed immediately. The relay log used only the
generic authenticate `why`, and the 25-second secondary retry budget cannot
cover a real `X-RateLimit-Reset` window. Observed 2026-09-08 14:11–14:17 UTC
(`reset` 14:22:05). This is #979 / P5.1.

Declared files:

- `scripts/ci/self_test_report.py`
- `scripts/ci/batch_runtime.py`
- `scripts/ci/batch_github_journal.py`
- `scripts/ci/incremental_completion.py`
- `scripts/ci/incremental_entry.py`
- `.github/workflows/incremental-completion.yml`
- `.github/workflows/self-test-report.yml`
- `tests/build/ci_self_test_report_test.py`
- `tests/build/ci_batch_runtime_test.py`
- `tests/build/ci_incremental_completion_test.py`
- `tests/build/ci_incremental_entry_test.py`
- `tests/build/ci_self_test_report_workflow_test.py`
- `docs/plans/2026-09-14-primary-quota-unknown.md`

Wait once until `X-RateLimit-Reset` inside a 20-minute cap. That wait does not
consume the short 429/5xx budget. Writer-lock GETs wait for this known primary
reset and still refuse secondary/transport sleeps. A later reset stays
fail-closed with the existing closed diagnostic, including `http.remaining` /
`http.reset` / `http.status`, never `not live`. Incremental Completion prints
that diagnostic. Controller and relay job timeouts become 25 minutes so the
wait plus the original short work still fit. No token, permission, or execute
authority changes.

## Verification

- `python3 tests/build/ci_self_test_report_test.py`
- `python3 tests/build/ci_batch_runtime_test.py`
- `python3 tests/build/ci_incremental_completion_test.py`
- `python3 tests/build/ci_incremental_entry_test.py`
- `python3 tests/build/ci_self_test_report_workflow_test.py`

Red-first: remaining=0 waits until reset; a reset beyond the cap is not slept;
permission 403 and lock-held 429 are not retried; relay CLI projects the closed
HTTP diagnostic.

Unexercised: a live Actions burst with remaining=0.

## Version Management

Version impact: none

Reason: CI controller/relay retry only; no Product Assembly, public API,
Contract, Provider or model identity changes.

## Documentation Impact

Documentation impact: none

Reason: no Portal page, source diagram, or projected identity changes; job
timeout and retry stay internal to CI control jobs.
