# P1 primary pointer proof model

Use a primary touch and a primary pen for concurrently admitted pointer
gestures. Two simultaneous touches cannot both be the primary pointer of their
type; the adapter intentionally refuses non-primary input. Retain reverse
release ordering, same-Pad gate suppression and cancellation isolation using
different pointer types the actual adapter can admit concurrently.

## Declared files and verification

- `apps/creator-web/test/input_controller.test.ts`
- `docs/plans/2026-10-02-creator-p1-primary-pointer-proof.md`

Run the complete Creator unit suite, TypeScript and staged scope. The cases
establish admitted input ordering and ownership; they do not establish physical
multi-finger support or touch-device acceptance. No existing assertion is removed.

## Version Management

Version impact: none. Only test input models change; product bytes and public
Contracts are unchanged.

Documentation impact: none
Reason: correct test realism for the existing input contract without changing
portal facts, user behavior or projected identities.
