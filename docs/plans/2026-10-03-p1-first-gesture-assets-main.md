# P1 first gesture with the current asset-service Main

The first-gesture branch now has a real lifecycle-test conflict with Main4afa.
Main requires the stable recovering state after synthetic blur and hidden
edges. Retain that exact invariant through the incoming recovery helper,
without duplicate polling, and preserve every original native idle, first-Pad,
probe, running, focus and visible leg and all original deadlines. Inherit the
entire inspected current Main, including the asset service, source clock,
Sequence editing, metronome, active manifests and immutable snapshots.
This convergence resolves the observed conflict; no strict-update gate is added.

## Task scope and verification

Declared first-parent files:
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/candidate_surface.tsx`
- `apps/creator-web/src/components/capture_panel.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/sample_controls.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/src/state/creator_state.ts`
- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `apps/creator-web/test/candidate_surface.test.tsx`
- `apps/creator-web/test/creator_state.test.ts`
- `apps/creator-web/test/error_messages.test.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/sample_controls.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-01-creator-p1-first-use.md`
- `docs/plans/2026-10-01-creator-p1-fixture-transport-ownership.md`
- `docs/plans/2026-10-01-creator-p1-touch-activation.md`
- `docs/plans/2026-10-02-creator-p1-audio-main-convergence.md`
- `docs/plans/2026-10-02-creator-p1-first-gesture-guidance-layout.md`
- `docs/plans/2026-10-02-creator-p1-first-gesture-main-layout.md`
- `docs/plans/2026-10-02-creator-p1-first-touch-shift-rail.md`
- `docs/plans/2026-10-02-creator-p1-owner-loss-held-press.md`
- `docs/plans/2026-10-02-creator-p1-perform-audio-guidance.md`
- `docs/plans/2026-10-02-creator-p1-primary-pointer-proof.md`
- `docs/plans/2026-10-02-creator-p1-sequence-voice-boundary.md`
- `docs/plans/2026-10-02-creator-p1-t1-current-main.md`
- `docs/plans/2026-10-02-creator-p1-touch-main-error-convergence.md`
- `docs/plans/2026-10-02-p1-first-gesture-metronome-convergence.md`
- `docs/plans/2026-10-02-p1-grid-first-gesture.md`
- `docs/plans/2026-10-02-p1-touch-compatibility.md`
- `docs/plans/2026-10-03-p1-owner-loss-held-note.md`
- `docs/plans/2026-10-03-p1-owner-loss-loop-tail.md`
- `packages/web-runtime-platform/test/input_adapters.test.mjs`
- `packages/web-runtime-platform/web/input_adapters.mjs`
- `tests/platform/web/candidate_journey.mjs`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `tests/platform/web/creator/creator_web_browser.spec.mjs`
- `tests/platform/web/creator/creator_web_candidate.spec.mjs`
- `tests/platform/web/creator/creator_web_candidate_runtime.spec.mjs`
- `tests/platform/web/creator/creator_web_capture.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `tests/platform/web/creator/creator_web_metronome.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `tests/platform/web/creator/creator_web_soundset.spec.mjs`
- `tests/platform/web/creator/creator_web_takeover.spec.mjs`
- `tests/platform/web/creator/fixtures/creator_audio.mjs`
- `docs/plans/2026-10-03-p1-first-gesture-assets-main.md`

Lowest-tier checks: complete Creator units, Creator TypeScript/Vite build,
complete Platform JavaScript units, syntax and staged ownership. Run the
complete current Architecture Portal check. Stage and inspect only the listed
paths and verify every Main blob outside this own scope is retained. After
commit reclassify exact batch inputs, retain every prior negative observation,
and complete each changed selected key. The two original full owner-loss
journeys with the strict loop-tail assertion passed at the parent before
this convergence; they are targeted parent evidence, not a current full proof.

## Version Management

Version impact: none. Active Main identities are inherited through actual
ancestry. No testing Build or snapshot is allocated; P1 T8 retains its
coordinated Module/Host version obligations.

Documentation impact: required. Retain the current facts and first-gesture
behavior on /hosts/creator-web; verify its source and projected identities
through the complete portal check, without editing frozen Main metadata.
