# FIX: a11y rail focus-order lock misses the #2108 Next Project stop

## Task

`creator_web_accessibility.spec.mjs` "responsive keyboard surface" fails on
main since #2108 (`95348414`): that Task wired the Project rail directions
into the physical column (`project_surface.tsx` "Previous/Next Project")
without updating the focus-order lock in the a11y spec. On the first Project
"Previous Project — ←" is disabled and skipped; "Next Project — →" is an
enabled tab stop between "Bank D" and SHIFT, which pushes "Pad A13" out of
the asserted window.

Observed on the C1 packaged proof (`/tmp/c1-proof3.log`, exit=1, single
failure at `creator_web_accessibility.spec.mjs:218`); C1's diff has zero
overlap with the asserted elements — the received insertion is literally
#2108's new button label.

## Fix

Insert `"Next Project — →"` after `"Bank D"` in `expectedFocusOrder`. The
walk length follows the lock, so the window extends by one and the first Pad
stays asserted — the lock's stated purpose ("the next inserted or enabled
key changes this list rather than shifting what the loop can see") is
preserved, not weakened. No product code changes.

## Declared files

- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `docs/plans/2026-10-13-creator-a11y-rail-focus-fix.md` (this file)

## Verification

- RED: C1 proof run on a tree containing #2108 without this fix — exit=1 at
  the focus-order assertion (`/tmp/c1-proof3.log`).
- GREEN: `scripts/creator-web.sh proof` on this branch's head
  (`/tmp/fix3-proof.log`).

## Version Management

Version impact: none
Reason: test-expectation sync with an already-merged, reviewed UI change; no
Module, Contract, or Product Build surface changes.

## Documentation Impact

Documentation impact: none
Reason: the rail direction keys are already documented by #2108's own
portal update; this Task changes only a test lock.
