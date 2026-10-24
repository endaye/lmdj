# Validate COUNT-IN consumption before sealing its caller

Relates to #2112 and #2233. Task3 follows Task1/Task2 on
`fix/count-in-recording-selection`, parent
`73ad0f3f1cb7fd2d040dcb4c07b779d8e5f883e3`; refreshed integration main is
`fa6998234de0560b09ba4720f6f49f8e8af8ba4e`.

## Premise and declared scope

Independent current-head GLM review40058497711/1 on PR2483 reports
discussion_r4365849714: `candidate.consumed` is set before `accept` validates
the consumed reply's original ticket. A mismatched reply throws, leaving the
old caller active but its cancellation/observation permanently sealed.
Current source confirms that order. The SDK normally validates responses, but
this Host controller must retain its own documented wrong-ticket behavior.

Move sealing after successful `accept`, keeping `candidate.consuming` as the
in-flight fence. A mismatch reports the protocol error, retains the exact
original caller and allows genuine reconciliation/cancellation. A validated
positive ACK still seals the old lane before awaiting the ordinary projection.
Preserve all valid-reply handoff behavior and authoring locks.

Declared files:

1. This plan.
2. `apps/creator-web/src/runtime/count_in_controller.ts`.
3. `apps/creator-web/test/count_in_controller.test.ts`.

No public protocol/SDK/Core/Facade, portal fact, manifest or frozen release
path changes. This is an atomic review correction on the existing PR stack.

## Verification

Add a controller regression first: a foreign positive consume reply reports
HOST_PROTOCOL_MISMATCH, preserves the original ticket, and a later genuine
cancel/consume still retires that original caller. The new test must actually
fail against the old ordering. Then run the complete Creator unit suite/types.
Freeze a clean local source checkpoint for official ordinary build/package;
push only after all four complete recording-switch and20 existing COUNT-IN/
metronome journeys pass on that artifact with the official PCM observer.
Keep original deadlines, truth/asset/release/capture/Stop/reopen assertions.
Retain previous successful and failed receipts as their actual source heads.
Run staged/committed ownership, final body checks, current-head independent
review and actual conversation disposition before guarded merge.

## Version Management

Version impact: Creator Host PATCH debt
Reason: internal fault-path ordering correction, absorbed by Task1's existing
same-domain MINOR debt in #2237. No allocation or identity changes.

## Documentation Impact

Documentation impact: none
Reason: this correction enforces the already documented original-ticket
validation and retention rule; Task1 owns the three Portal updates.
