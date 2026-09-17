# Reuse immutable GitHub GETs inside one review publication

## Task

One `publish` process re-reads the workflow, repository, bot user, and every
same-head prior identity on each authenticate call. Those extra REST GETs share
the repository `GITHUB_TOKEN` 1,000/hour budget with Incremental Completion and
Self-test Report, so a burst of PRs exhausts primary quota.

Declared files:

- `scripts/ci/review_pipeline.py`
- `tests/build/ci_review_pipeline_test.py`
- `docs/plans/2026-09-14-review-get-reuse.md`

Reuse workflow, repository, and bot GETs inside one publication store. Reuse
complete authenticate results only for immutable prior identities. Live
run/pull/jobs reads stay uncached so pre-label head races still execute. No
token, permission, eligibility, or retry-bound changes.

## Verification

Lowest tier: `python3 tests/build/ci_review_pipeline_test.py`.

Unexercised: a live remaining=0 burst; this only reduces GET count.

## Version Management

Version impact: none

Reason: internal publisher GET reuse only.

## Documentation Impact

Documentation impact: none

Reason: no Portal page or product fact changes.
