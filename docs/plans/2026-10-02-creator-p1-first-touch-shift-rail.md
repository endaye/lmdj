# First-touch audio retains the SHIFT history rail

Adopt actual main20d57962f Undo/Redo rail chord after the previous f739 Source
convergence. Retain main SHIFT/direction lamps and history guards. Preserve
native MouseEvent delivery to Record/PlayStop, silently waking audio before
submitting an intent, while consuming SHIFT on each rail action. Tab order
includes the now-enabled SHIFT, Record and Play/Stop before the first Pad.

Synchronize Sample preview next-step copy with the removed activation gate:
play a Pad to start audio, then retry preview. The existing message catalogue
test fixes that concrete rendered guidance. No new product error mapping,
permission policy or gate is introduced.

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
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `docs/plans/2026-10-02-creator-p1-first-touch-shift-rail.md`

## Verification

Run authoring-history, hardware-console, workspace-shell, audio-lifecycle and
error-message component suites, TypeScript, staged scope ownership and full
portal. These cover the rail chord, native activation guard, Project/input
lifecycle and the actual preview guide. Committed Creator/Runtime batch proof
and current-head review remain required. Existing 865 full-unit evidence is
retained on the prior source; no assertion, budget or journey leg is reduced.

## Version Management

Version impact: none. Inherit actual main Product2.0.75.0/Contract5.2.0 without
new allocation; P1 Host identity debt remains T8's coordinated obligation.
No release, tag or Creator deployment.

Documentation impact: required
Affected portal pages: /hosts/creator-web/.
Reason: truthful rail controls and preview guidance without activation gate.
