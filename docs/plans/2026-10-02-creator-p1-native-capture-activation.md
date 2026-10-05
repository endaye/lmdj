# P1 native capture activation timing

Independent review confirms that waiting for every Runtime activation before
microphone creation changes the existing legal native mouse/keyboard timing.
Pass the input controller's actual deferred cold touch/pen flag through the
empty-Pad callback and Host source. Only that deferred microphone branch waits
for its owned release. Legal native microphone presses resume synchronously;
their capture remains independent of a pending or refused playback activation.
Master capture continues to require playback activation and its cleanup barrier.

## Declared files and verification

- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/capture/pad_capture_sources.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/pad_capture_sources.test.ts`
- `docs/plans/2026-10-02-creator-p1-native-capture-activation.md`

Retain the prior Source's synchronous-resume failures. Verify actual mouse,
touch and pen flag propagation, same-stack microphone resume with pending and
refused Runtime activation, cold deferred allocation and all prior cleanup
barriers. Run full Creator units, TypeScript and staged scope before commit.
Real Safari/iPad microphone and listening acceptance remain separate.

## Version Management

Version impact: deferred to the coordinated P1 candidate settlement.
Reason: preserve local Creator activation and capture independence without
allocating a Product Build or changing a public Contract in this Task.

Documentation impact: none
Reason: preserve the existing native musical press behavior and the already
documented cold touch release boundary; no new user-facing workflow is added.
