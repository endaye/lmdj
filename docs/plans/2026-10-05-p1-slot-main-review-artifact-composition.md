# P1 slot acquisition with current Main review artifacts

## Problem and Task

Compose captured protected Main `cc5a8d6f37539b91ac912da9464a9f0f7089a9af` with the actual current slot-acquisition
head `b5e9fd3d2b8c6cbdac6fecdaa5185b7e6cd74746` using a real two-parent merge. Main separates bulky review diagnostics
from the bounded authentication archive and retains the exact-head reader's
expanded-budget refusal. The merge has no conflicts. Preserve all P1 product
source, original regressions, identities, immutable snapshots and prior evidence.

## Declared files

- `.agents/pitfalls/review-input-generated-bytes-exhaust-limit.md`
- `.github/workflows/pr-review.yml`
- `scripts/ci/review_wait.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_review_wait_test.py`
- `docs/plans/2026-10-05-p1-slot-main-review-artifact-composition.md`

## Verification

Run both original complete `ci_pr_review_workflow_test.py` and
`ci_review_wait_test.py` suites on the composed source: these catch producer/consumer
artifact inventory drift, inappropriate admission and loss of visible archive
budget refusals. After staging, run `ci_change_scope_test.py` to catch ownership
gaps. Inspect the exact staged paths, whitespace, real ordered parents, and clean
postcommit source; authenticate every imported blob against captured Main and
every other preexisting tracked blob against the original P1 head. Classify the
complete committed PR range with the canonical local-ci entry point.

Historical full-lane results stay bound to their own source identities. A failed
Deploy Contract run remains failed while its Git fixture availability is investigated.
This composition does not claim a current full self-test or protected-main merge.

## Version Management

Version impact: none. This is the exact import of an already integrated review
control-plane fix plus this plan; product/module/host/provider/contract identities
and snapshot bytes remain unchanged.

## Documentation impact

Documentation impact: none. No portal route, source diagram, projected identity or
product source fact changes. This plan records the merge and its evidence.
