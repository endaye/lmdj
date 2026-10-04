# P1: one Trigger for a physical touch

## Scope and evidence

The frozen 281ec612 input adapter accepts a trusted Chromium touch twice: pointerdown triggers once, pointerup clears its compatibility marker, and a later touch-generated mousedown triggers again. An independent actual CDP touch reproduced two different gesture keys while the real mouse control triggered once. An independently observed complete first-use journey also sent two positive-velocity trigger requests for one physical touch. Its original response-count poll can momentarily pass while the second request is pending; a targeted pass does not refute the defect.

Reject browser-declared touch-generated mouse events, including React's nativeEvent wrapper. For browsers without that metadata, preserve the existing coordinate/target/slot correlation across a normal touch release and start its bounded compatibility window at release. Preserve cancellation, true mouse input, accessibility, pointer lifecycle, gesture identities, and all existing budgets. Do not prevent default browser focus or change Runtime admission or recording cutoff semantics.

## Declared files

- `packages/web-runtime-platform/web/input_adapters.mjs`
- `packages/web-runtime-platform/test/input_adapters.test.mjs`
- `apps/creator-web/test/input_controller.test.ts`
- `docs/plans/2026-10-02-p1-touch-compatibility.md`

## Task verification

First run the reduced adapter and actual React-wrapper regressions against unchanged Source and retain their actual failing assertion. Then run the complete adapter suite, complete Creator input-controller suite, and TypeScript validation. Run an authenticated independent frozen native Chromium touch/mouse driver against the fixed Source, with fresh processes for the original negative and corrected positive. Inspect staged ownership and whitespace. The regressions catch one physical touch being admitted twice; existing true-mouse and cancellation assertions remain strict. After commit derive the clean current lane plan and complete every changed input-key obligation before shipping. Complete integrated first-use behavior and real Safari/iPad acceptance remain separate evidence.

## Version Management

Version impact: coordinated Module PATCH allocation in P1 T8; no manifest mutation in this Source repair Task.

This is an internal compatibility correction of the existing one-Trigger input behavior; no public API, Project/Contract format or migration changes. Module patch identity is included in the already-declared coordinated P1 T8 version allocation, against its then-live manifest. This Task does not publish a Package, allocate a Product Build/snapshot, or modify an Assembly/manifest/tag. Existing immutable identities are retained until that coordinated allocation; no release or Channel operation is authorized here.

Documentation impact: none
Reason: This repair restores the documented input invariant without changing an Architecture Portal API or product workflow. The current plan and regression assertions record the behavior and evidence.

## Pitfall disposition

The defect is derivable from input Source and browser event order. Its reduced regression is the exit; no new process pitfall is introduced. Original failing packaged evidence is retained.
