# Reuse the authenticated Outbox append result

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md),
specifically reliable bounded failure reporting, not automatic repair or delivery activation.

## Declared files

- `scripts/ci/report_outbox.py`
- `tests/build/ci_report_outbox_test.py`
- This plan.

## Behavior

`Journal.append` already loads/authenticates the complete history before writing,
persists the pending intent, appends once, then loads/authenticates the far-side
history and confirms the checkpoint. It returns that complete committed event
list, including on an exact idempotent append. `Controller._persist` replays this
return value. `Outbox._persist` instead discards it and calls `load` again.

Replay the authenticated append result and compare the entire reduced state with
the expected transition before publishing it locally. Preserve the writer lock
check across this boundary. Reject a missing, malformed or inconsistent returned
history. Do not infer success from the attempted event, a POST response or a
locally reduced expected state. Fresh calls and fresh objects still load and
authenticate history; no metadata, writer proof, failure or mutable response is
cached across reads. No Journal, checkpoint, API, model or report schema change.

## Verification and acceptance

First record a real Journal load count regression for a complete report delivery:
queue → claim → business POST → ack → exact receipt → delivered. Remove only the
four redundant Outbox reads, not the Journal's eight pre/post append reads or
initial/recovery reads. Verify complete persisted state with a fresh Outbox and
the exact Issue receipt; repeated delivery must not repeat the business POST.
Fault returned history and loss of the lock after append: no business POST may
follow unverified queue/claim. Retain queue/claim/ack/delivered write-loss,
process-death, invisible/deleted/edited history, unknown POST and wrong receipt
journeys. Use real Journal with transport/API fixtures; counts are local protocol
accounting, not a measured production latency or rate-limit improvement.

Run Outbox, report runtime, journal and entry suites, complete CI discovery,
staged ownership, final range classification and PR declaration checks. After
authorized merge, inspect actual bounded reporting and exact durable receipts;
the earlier timed-out report run is not proven repaired by local counts alone.
No budget widening, reset, blind POST retry, full product rerun or Issue closure.

## Version Management

Version impact: none
Reason: internal authenticated-result reuse; no Product/Host/Module/Contract identity.

## Documentation Impact

Documentation impact: none
Reason: no Portal page, command, report semantics, workflow or identity changes;
the existing write-before-POST and exact-receipt guarantees are unchanged.
