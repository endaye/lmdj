# T2c — Read-only merged PR mapping

## Declared files

- `.github/workflows/pr-review.yml`
- `scripts/ci/review_merge_map.py`
- `tests/build/ci_review_merge_map_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- This plan.

## Boundary and behavior

The private-repository controller must not acquire new PR read permission to
resolve merge mappings. Reuse the existing review publisher's contents read,
actions read and PR write grant, but on closed/merged events run a read-only
mapping branch only. No new permission, model call, label, issue or review write.
Closed-event concurrency is distinct so it does not cancel a finishing review.

Bind live merged PR head to actual main first-parent merge SHA and actual Git
changed paths. Page immutable bot reviews and authenticate historical scope
records against completed producer/publisher jobs, exact workflow source,
trusted main control, historical policy and the actual retained scope artifact.
Historical validation intentionally does not require an open PR. Current-head
publication validation is not weakened or reused with a forged open state.
The publisher's shared bounded compressed metadata codec is reused directly.
A scope-unavailable marker, malformed or unsupported scope-bearing comment
forces full even if another same-head comment contains a valid none record.
No overflow marker is silently interpreted as an absence of AI requirements.

The versioned map includes repository/workflow numeric identities, PR/head,
merge/control/run/attempt, path digest, scope record/artifact/review receipts and
explicit completeness gaps. Missing, expired, unverified or still-in-flight
evidence means `requires_full`; it never grants none. An unrelated active manual
review is conservatively uncertain because Actions does not expose its input PR
number as immutable run identity. No display title is authority.

Controller consumes this artifact with existing actions/contents read and must
independently authenticate map producer source/job/run/attempt and revalidate
record policies. The map digest is consistency, not authentication. Missing map
or API failure is conservative full, not no PR or no changes. The artifact lasts
30 days; expiry uses full fallback rather than requiring a persistent PR token.

## Verification

Lowest tier: `ci_review_merge_map_test.py`, T1/T2a/T2b regressions and full CI
contracts; pinned actionlint 1.7.12; staged ownership and cached diff checks.
Real Git interval mechanics remain covered by T1's temporary repositories;
mocked historical Actions receipts and ZIPs do not prove actual platform event,
token, artifact identity or race behavior. Those remain O1 acceptance obligations.

Pitfall impact: none; no historical incident newly claimed.

## Documentation Impact

Documentation impact: none

Reason: Internal CI evidence producer only. Product self-test trigger and current
Portal governance switch remain T5; no Product Assembly or identity changes.

## Version Management

Version impact: none

Reason: CI-internal mapping schema only; no Product Build/tag/publication,
deployment or Channel promotion.
