# PR-Agent retained diagnostic member compatibility

## Defect and scope

PR #1241 run 34630800630 attempt 1 completed engine and publication, but
`review_wait.py` rejected its archive in `review_failure_report.collect`:
`review archive schema is not closed`. The production workflow retains three
T2 diagnostic JSON files absent from the consumer's fixture inventory.

Accept only these explicitly named optional diagnostic members in v2 archives:
`t2-input.json`, `collection-receipt.json`, `t2-result.json`. They are not
admission authority; the canonical collector/config/coverage/history/result
receipts still undergo all existing checks. Keep duplicate-member/key checks,
compressed/expanded size limits, JSON parsing, v1 shape and unknown-member
rejection. Do not reinterpret a diagnostic's claimed success as a review.
No workflow, provider, budget, host, review identity or publication change.

## Declared files

- `scripts/ci/review_failure_report.py`
- `tests/build/ci_review_wait_test.py`
- `.agents/pitfalls/fake-tool-stub-strictness.md`
- `docs/plans/2026-09-12-pr-agent-review-artifacts.md`

## Verification

Run `ci_review_wait_test.py`, `ci_review_failure_report_test.py`,
`ci_review_discovery_test.py`, `ci_review_merge_map_test.py`,
`ci_review_merge_map_reader_test.py`, `ci_review_pipeline_test.py`, and
`ci_change_scope_test.py`. The new wait test constructs its archive inventory
from the actual producer workflow paths, then reaches the real reader. It must
fail on the old consumer and pass after the narrow repair. Negative controls
retain v1/unknown/path/duplicate/missing-canonical/tampered-canonical rejection;
diagnostics alone cannot produce eligible review evidence.

Use an independent exact-head code review before merge. Check the new PR's
actual retained archive with the repaired read-only helper, preserving prior
invalid observations and original failed runs. No extra manual model probe.
Fixture/source verification is not live provider, host, or capacity acceptance.

## Documentation impact

Documentation impact: none — internal compatibility for already-retained
diagnostic members; published review/scope behavior and portal instructions do
not change.

## Version Management

Version impact: none — CI receipt reader compatibility only; no Product Build,
module, provider, host, or Contract manifest allocation.
