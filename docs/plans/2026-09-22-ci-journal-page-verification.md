# Journal page verification — #1486 follow-up

Base: `117db40e5b2bd33f102dd7a5c62bff74b62bcab5`.

## Problem and scope

PR #1488 already delivered reuse between appends. A complete multi-page read
still authenticates earlier writers twice: `page()` authenticates each page,
then `Journal._read_complete()` authenticates the accumulated rows after the
transport has reset its mutable writer observations for the last page.
Six distinct writers across three pages produce eleven attempt GETs including
the anchor, where seven suffice. This is an HTTP-fixture measurement.

One Task consumes each page through the existing envelope verifier before
reading the next page. Keep writer observations page-local, check every link,
digest and ID, and publish the verified prefix only after the entire read
passes. No transport cache lifetime or trust rule changes.

Declared files:

- `scripts/ci/incremental_batch_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `.agents/pitfalls/journal-append-replays-full-history.md`
- this plan

## Verification

The lowest-tier regression uses the real Journal/transport composition with
the existing HTTP fixture and counts writer attempt GETs across three pages.
It must fail before the fix (11 versus 7). A later-page rejection must leave
the verified-prefix cache unpublished. Run the complete journal protocol,
GitHub transport, runtime, controller and report-outbox suites; then Portal,
staged ownership, diff and PR-body checks. No new required check is introduced.

Local results on 2026-09-22:

- Before the implementation change, the two new tests ran with exit 1:
  the request-count assertion failed at 11 versus 7; the rejection test passed.
- After the change, `python3 tests/build/ci_incremental_batch_journal_test.py`
  passed 29 tests; `ci_batch_github_journal_test.py` passed 79;
  `ci_batch_runtime_test.py` passed 81; `ci_batch_controller_test.py` passed 48;
  and `ci_report_outbox_test.py` passed 28 (all via `python3 tests/build/`).
- `python3 tests/build/ci_pitfall_ledger_test.py` passed 15 tests.
- `scripts/docs-site.sh check` exited 0: 170 tests passed, zero skipped;
  metadata, diagrams, facts, release-document consistency, typecheck, build,
  and the 48-route/internal-link check passed.

Remote acceptance remains separate: the post-merge scheduler must reach
admission/execution, followed by durable outbox delivery, with actual request
counters. Historical run 35303063784 started product jobs but its controller
used 1,871 HTTP attempts; this does not prove the Issue's 500–700 estimate.
Outbox generations 668–671 in run 35380045953 delivered Issue #1533, as read
back on 2026-09-22. Current run 35692698542 fails at `scheduler-read` after
28 HTTP attempts with 4,926 REST requests remaining; its red status does not
establish that repeated history verification caused it. Keep #1486 open until
its remaining operational evidence is verified.

## Version Management

Version impact: none
Reason: internal CI verification cost; no product or contract identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: explain the page boundary and correct an unverified request-cost claim.
