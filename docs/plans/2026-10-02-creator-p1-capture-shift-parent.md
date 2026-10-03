# Pad recording retains the reviewed SHIFT rail

Adopt streaminga855c7be7bdafa7d58eeb8417937b9c9df2aa74a. Automatic merging
needed no conflict resolution. Preserve microphone/master startup and abort,
exact gesture ownership, recording exclusions, default-seed mutation guard
and capture retained-take behavior. Adopt actual main20d history hook/layer,
native transport event delivery, SHIFT consumption and the concrete preview
guide independently verified on0ecd. No capture Source or adapter is replaced.

## Declared files

- `.agents/pitfalls/review-invalid-output-is-model-flake.md`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/authoring_history.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/authoring_history.test.tsx`
- `apps/creator-web/test/error_messages.test.ts`
- `apps/creator-web/test/hardware_console.test.tsx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-02-creator-p1-audio-main-convergence.md`
- `docs/plans/2026-10-02-creator-p1-first-touch-shift-rail.md`
- `docs/plans/2026-10-02-creator-p1-streaming-shift-parent.md`
- `docs/plans/2026-10-02-creator-p1-t1-current-main.md`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `docs/plans/2026-10-02-creator-p1-capture-shift-parent.md`

## Verification

Run authoring-history, hardware-console, workspace-shell, audio-lifecycle,
error-message, PadCapture, source-adapter and InputController component suites;
TypeScript, staged scope and full portal. The prior full904-unit run remains
bound to378b0edb. Before shipping run current committed-head selected lanes
and review, retaining full native microphone/cancel/reload and internal replay
journeys. No assertion, budget or owned lane is reduced.

## Version Management

Version impact: none. Retain actual main Product2.0.75.0/Contract5.2.0 and its
immutable snapshot/witness. T8 settles P1 identities from live reservations.
No allocation, release, tag or Creator deployment.

Documentation impact: required
Affected portal pages: /hosts/creator-web/.
Reason: retain capture source facts beside truthful rail and preview behavior.
