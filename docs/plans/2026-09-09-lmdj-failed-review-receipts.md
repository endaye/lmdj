# Admit authenticated all-backend failure receipts from a failed producer

Status: implemented and locally verified; remote delivery acceptance pending.
Relates to #939 and #1048.

## Defect and scope

The review finalizer now saves a complete `not-reviewed` receipt and exits 1
when all backends fail. The collector still requires both the producer job and
`Save honest final result` step to succeed. It therefore rejects actual failure
receipts before reading artifacts; discovery retains `unresolved` instead of
queueing the failure Issue. PR #1061 run `34307707493/1` is a real example:
producer `102327798885` and finalizer failed, input collection and upload passed,
and artifact `10087423949` retains three `runtime_failure` attempts.

Fix only this producer/consumer mismatch. Do not turn failed model review into
green review, change review scope, skip authentication, repair product code,
rerun models/tests, close Issues or alter any journal/history. A successful
review whose later PR publication fails is already independently classified by
its authenticated result; no merged-PR special case is required.

## Implementation Task

Declared files:

- `scripts/ci/review_failure_report.py`
- `tests/build/ci_review_failure_report_test.py`
- `tests/build/ci_review_discovery_runtime_test.py`
- `tests/build/ci_report_runtime_test.py`
- this plan
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`

Accept two producer shapes: the historical successful job/finalizer, and a
failed job with an explicitly failed finalizer. Both require successful complete
input collection and artifact upload. After full source/run/attempt/artifact
validation and independent policy/history/result recomputation, the failed
shape must prove `not-reviewed` and the exact all-backend failure document.
Reject cancelled/skipped/incomplete producers, unexpected finalizer states,
missing/foreign/expired artifacts and contradictory or forged results.
Preserve the historical successful-producer failure receipts and valid-review
path. Existing review-history validation owns backend order and completeness.

## Verification and complete journey

Use the actual `review_pipeline.py finalize` CLI with complete fixture input to
produce its exit status and retained JSON files; do not invent a successful
producer fixture for its current failed status. First reproduce rejection in
the unmodified collector and unresolved discovery with no queued report.

Walk actual finalizer failure → authenticated collector → discovery's durable
`failure-queued` → fresh report runtime drain → exact Issue/body/receipt → fresh
adapter replay without another POST. Retain queued recovery after source expiry
and uncertain-POST recovery. Include negative integrity cases with the failed
producer shape, plus historical compatibility and successful review despite
failed publication. These local API fixtures do not prove platform locks,
production delivery, backend repair, or an empty global backlog.

Run focused producer/collector/discovery/outbox/runtime tests, complete CI
contract discovery, staged ownership and Architecture Portal check before
commit. After merge, use existing bounded discovery/report recovery to verify
one real retained failure reaches the durable outbox and exact Issue receipt;
do not issue another model or product test request as a reporting retry.

### Retained pre-merge evidence

- Collector, discovery and report-runtime focused suites: 46 + 39 + 44 tests
  passed. The unmodified collector and discovery first reproduced rejection
  and the stranded `unresolved` state using the actual finalizer CLI output.
- Complete `ci_*_test.py` discovery with actionlint available: 2,178 tests
  passed, no skips. No test budget, selection or coverage floor changed.
- `scripts/architecture-portal.sh check`: 112 tests passed and all 44 generated
  routes/internal links validated. Product version verification passed unchanged.
- Independent GET-only collection of real run `34307707493/1` returns the
  exact original request/head-bound failure report. Run `34309218113/1` (PR
  #1066) returns no backend-failure report: Kimi reviewed successfully even
  though its later publisher rejected the already-merged PR.
- These real reads perform no outbox or Issue mutation. Production queueing,
  exact delivery receipt and recovery remain the post-merge acceptance gap;
  this Task does not establish an empty global backlog or repaired backends.

## Version Management

Version impact: none

Reason: internal CI receipt admission only; no Product, Host, Module, Provider,
Contract, Assembly or snapshot identity changes.

## Documentation Impact

Documentation impact: none

Reason: restores the existing documented all-backend-failure reporting behavior;
no Portal command, route, identity or selection policy changes.
