# Bounded primary rate-limit wait for PR review publication

## Task

PR Review `Publish review and scope` fails closed on GitHub REST
`X-RateLimit-Remaining: 0` (example: run `34834291036/1` on PR #1318,
`reason=primary-rate-limit remaining=0 reset=1789383416`). That required check
then stays red until a human reruns after reset. `GITHUB_TOKEN` is 1,000 REST
requests per hour per repository; concurrent review, incremental, and report
jobs share it.

This is the PR-blocking sibling of #979 (controller/relay). Do not close #979.

Declared files:

- `.github/scripts/pr_review_target.py`
- `.github/workflows/pr-review.yml`
- `tests/build/ci_pr_review_workflow_test.py`
- `docs/plans/2026-09-14-review-primary-rate-limit.md`

Wait until `X-RateLimit-Reset` for 403/429 with remaining 0, once, inside a
20-minute cap. Permission 403 (remaining > 0) and a reset beyond the cap stay
fail-closed with the existing HTTP diagnostic. Target and publish job timeouts
become 25 minutes so the wait plus the original short work still fit. No token,
permission, eligibility, or extra GitHub request changes. Writes retry only
because remaining 0 means the POST was refused.

## Verification

Lowest tier: `python3 tests/build/ci_pr_review_workflow_test.py`. Add focused
retries through the real `urlopen` wrapper: wait-then-GET, wait-then-POST,
permission 403 not retried, reset beyond the cap not slept. Pin job timeout to
the wait cap. Re-run the publisher diagnostic suite
`python3 tests/build/ci_review_pipeline_test.py` so remaining-0 still projects
`reason=primary-rate-limit` after retries are exhausted.

## Version Management

Version impact: none

Reason: CI review client retry only; no Product Assembly, public API, Contract,
Provider or model identity changes. No release is initiated.

## Documentation Impact

Documentation impact: none

Reason: no Portal-documented command, workflow identity, release state or
product fact changes; job timeout and retry stay internal to PR Review.

Pitfall disposition: the wait/no-wait distinction is fully expressed by the
focused regressions; no new process-ledger entry.
