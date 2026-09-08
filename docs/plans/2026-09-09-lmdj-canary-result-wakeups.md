# Result-driven planner entry and durable test-source binding

Part of [result-driven delivery](2026-09-09-lmdj-result-driven-delivery.md).

## Declared files

- `tools/canary/planning.py`
- `tests/build/ci_canary_planning_test.py`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` (progress only).

Remove the retired daily request from the internal planner. Ordinary direct
previews are manual. Result and recovery wakeups use a separate entry that
reads a request and terminal result from caller-authenticated scheduler replay,
decodes its retained verdict and recomputes all suite semantics under the
request's exact historical policy. Missing records, malformed identities,
changed outcomes or corrupt evidence fail closed. Failed/missing/no-test results
do not produce a delivery plan; successful selected evidence is a wakeup only.

Use a stable source-derived request identity. Recovery returns the identical
plan for unchanged progress/control, never creates a date-based request. Pin
the test result's target even when main advances. Keep supplied version/site/
formal progress independent of scheduler processed progress. Retain the entire
planning test floor: the waking focused result is not evidence that all changes
since a site's deployment or version baseline are covered. Do not clear debt,
failures, or Issues and do not allocate versions, invoke models or deploy.

This Task implements the durable-result-to-planner consumer, not GitHub source
authentication or an active workflow. The caller must authenticate complete
scheduler replay and independent progress. Workflow activation, trusted storage
configuration, coalescing, candidate coverage, fencing and external effects
remain required. No source claim in an arbitrary JSON object grants authority.

## Verification

Begin with failing result/recovery/daily-rejection regressions. Use real Git
histories and real verdict building/retained encoding; test changed main,
independent baseline, unrelated focused green, retained failure/debt, corrupt
verdict, identity/outcome mismatch, absent terminal, missing evidence, failed
and not-required outcomes, invalid wakeup and deterministic replay. Assert
unchanged scheduler/progress and Git state. Fixture authority is not live proof.
Run canary and CI discovery, staged ownership and Portal check; ship with the
final committed-range/declaration/current-head review procedure.

## Version Management

Version impact: none
Reason: internal planning inputs only; no active identities or allocations.

## Documentation Impact

Documentation impact: none
Reason: no active workflow or operator entry point changes; the later activation
must update current Portal operations pages and superseded daily deployment text.
