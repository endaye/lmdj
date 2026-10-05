# P1 capture cancellation ownership

Independent review R7 reproduces a keyboard-owned recording interrupted by a
busy primary mouse press on another empty Pad and its pointer cancellation.
Busy capture input remains consumed so it cannot open a file picker, but its
cancel carries its actual gesture key and cannot seal another owner's take.
Permission preparation uses the same ownership rule. Blur, disposal and other
adverse lifecycle operations retain explicit global cancellation.

## Declared files and verification

- `apps/creator-web/src/capture/pad_capture.ts`
- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/test/pad_capture.test.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `docs/plans/2026-10-02-creator-p1-capture-cancellation-owner.md`

Retain failing ownership assertions before fixing the callbacks. Assert foreign
cancellation cannot abort startup, stop a recording or dismiss another gesture's
permission preparation. Owner release still stops and commits the original
target once. Input cancellation forwards its exact key, consumes busy presses
without a picker or trigger, and lifecycle cancellation stays global. Run the
capture/input suites, complete Creator unit suite, TypeScript and staged scope.
The independent real-module callback harness verifies the App binding; device
microphone and physical input acceptance remain separate.

## Version Management

Version impact: deferred to coordinated P1 candidate settlement.
Reason: fix Creator capture input ownership without changing a public Contract
or allocating a Product Build in this Task.

Documentation impact: none
Reason: restore the existing one-owner recording invariant and documented
cancellation behavior; no new architecture boundary or user flow.
