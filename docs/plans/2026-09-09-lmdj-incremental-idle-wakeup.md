# Recover a missed main wakeup from an idle completion

This bounded repair belongs to the
[result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).

## Declared files

- `scripts/ci/incremental_entry.py`
- `tests/build/ci_incremental_entry_test.py`
- `docs/design/2026-09-08-lmdj-ci-incremental-batches.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `.agents/pitfalls/coalesced-main-wakeup-lost.md`
- This plan.

## Defect and repair

Actual callback `34277723029/1` authenticated relay `34277673180/1` and cancelled
push parent `34277607211/1`, but returned idle with no active batch and processed
still at `2a2da287a3dbc25cd6bedb8850fd90307943ae69` although main was
`2ecd64a04ed4da12b04d9df22b6379ee2e77a1f9`. This proves a lost immediate wakeup,
not who cancelled the push or that independent health recovery cannot work.

Keep exact active-executor settlement. Only when the authenticated journal has
no active batch, independently read main and compare it with durable processed.
If different, invoke the same locked reconciler, which freshly reads main again,
collects the complete first-parent interval and persists a request/claim before
execution. The completed parent's conclusion is not test evidence or admission
authority. No active + unchanged main remains a no-write idle response; another
active owner remains untouched. Main-read failure stops without a journal write.
Reporting callbacks cannot launch tests. No workflow, lock, budget, gate or
daily schedule change.

## Verification and acceptance

First reproduce cancelled push without a claim after old work settled, then
advance main again before the relay: assert the recovered request spans every
intervening commit and its new claim survives independent journal replay.
Repeat the callback while that claim is active: no second executor or writes.
Separately assert unchanged-main idle, other active owner with new main,
unavailable fresh main, invalid source authentication and report-only behavior.
Use real Git/Runtime/Journal with strict HTTP fixtures; relay resolution remains
a seam double with authentication covered by `ci_incremental_completion_test`.
Actual platform coalescing, delivery depth and far-side heavy/result/report
acceptance remain remote obligations, not local-test claims.

Run focused entry/completion tests, full Python CI contract discovery, staged
and committed ownership checks, final range classification, PR body/declaration
validation and `scripts/architecture-portal.sh check`. No new required gate.
After authorized merge inspect the actual new-main wakeup and persisted request,
without cancelling existing work or treating controller success as product green.

## Version Management

Version impact: none
Reason: CI wakeup recovery only; no Product, Host, Module or Contract identity.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: distinguish active settlement from idle new-main recovery. This operation
page has no separate diagram; update the inline flow explanation in the spec.
