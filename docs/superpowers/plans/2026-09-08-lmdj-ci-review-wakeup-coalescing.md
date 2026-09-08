# Coalesce PR Review wakeups

## Scope

The Owner authorized commit, push, PR and merge for CI cost remediation while
retaining paid macOS availability recovery. This independent Task removes the
PR Review completion subscription from Self-test Report. Main pushes continue
to coalesce new targets in the durable scheduler. Actual batch completion relay
and legacy Core CI completion remain subscribed, without changing authentication,
scope union, event receipts or writer cancellation behavior.

Declared files:

- `.github/workflows/self-test-report.yml`
- `tests/build/ci_incremental_cutover_workflow_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `tests/build/ci_o1_claim_probe_workflow_test.py`
- `tests/build/ci_o1_probe_workflow_test.py`
- this plan

The parallel routing Task moves routine control to Contabo; this Task does not
alter runner labels and can merge in either order without granting hosted
exceptions. Do not infer a complete cost migration from this trigger-only diff.

## Behavior and tradeoff

PR-only opened/synchronize/review activity no longer creates a scheduler/relay
chain. Reviews still publish authenticated scope and findings. Existing bounded
discovery on idle main/15-minute health observations recovers retained valid
reviews, closed mappings and failure reports. This can delay review-infrastructure
Issue creation: the health interval is not a delivery SLA when the control pool
is down, busy executing a batch, or processing backlog. Unknown scope still
selects the deterministic safe fallback; labels never reduce required coverage.

Keep the old authenticated review callback handler and exact manual
report-review/report-discovery recovery for old queued runs and retained data.
Keep immediate completion relay: the GitHub event does not expose whether its
parent actually ran product jobs before allocating a runner. Removing that
relay without another verified completion signal could strand or delay the
next batch. Eliminating all idle completion relays remains a separate design
item, not a claimed result of this Task. Do not cancel a writer or erase debt
to reduce event counts. The existing health tick is recovery, not daily testing.

## Verification

Run `ci_incremental_cutover_workflow_test.py`, full `ci_*_test.py` discovery,
`ci_review_discovery_runtime_test.py` (covered by discovery), actionlint and
staged ownership validation. Existing behavioral tests execute the actual
discovery condition for main, schedule, executing, failed and callback states;
new assertions retain bounded discovery and exact manual recovery. Exercise
post-merge PR Review completion without a new main push and observe no directly
subscribed scheduler run; do not confuse contemporaneous main/schedule or old
workflow callbacks with this event. Successful main-trigger execution and
subsequent discovery are separate far-side acceptance legs.

## Version Management

Version impact: none
Reason: workflow subscription only, no product or Contract identity changes.

## Documentation Impact

Documentation impact: none
Reason: implementation plan only, no Architecture Portal pages or identities.

## Pitfall Impact

Pitfall impact: none — this callback inventory regression directly states the
behavior, while the routing Task owns the billed-control allowlist pitfall.

## Release Impact

Release impact: none
Reason: no budget change, product test request, tag, release or deployment.
