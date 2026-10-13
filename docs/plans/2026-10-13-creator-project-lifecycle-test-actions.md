# Creator Project lifecycle test actions

Issue: #2129. Integration base: `de1baf121949557e53a38820372721c852214e47`.

## Premise and outcome

The Project browser introduced by #2120 always displays its local list and
replaces the old Open-local navigation with the selected Open Project action.
Four audio lifecycle tests still query the removed button. Their owning suite
fails 4/22 on the earlier clean main source `613e23c2` as well as during C1.

Assert the existing Open Project action's disabled/enabled state during audio
suspension, automatic reopen and aborted-import recovery. The loop lifecycle
journey directly opens the already-listed Project and retains every fresh
trigger, voice, subscription, shutdown and recovery assertion after reopening.

## Declared files

- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `docs/plans/2026-10-13-creator-project-lifecycle-test-actions.md`

## Verification

- `npx --no-install vitest run test/audio_lifecycle.test.tsx` in Creator: all
  22 lifecycle cases, unchanged deadlines and runtime ownership assertions.
- `npx --no-install tsc --noEmit` in Creator.
- PR body lint, documentation declaration and final ownership classification.
- C1 full packaged proof remains a separate Task; this check is not that proof.

## Version Management

Version impact: none — test locators follow existing UI; no product behaviour,
public API, assembly or build identity changes.

## Documentation impact

Documentation impact: none
Reason: test-only alignment with the already-documented Project browser; no
Portal fact or route changes.

## Pitfall impact

The selector mismatch is directly explained by the component source. Keep its
existing lifecycle regressions; no new process-ledger entry is warranted.
