# Creator Interaction UI — U06a Grid Tools

Relates to #2112. Root admitted this Task on 2026-10-13 after the read-only
Sequence audit. Worktree: `/Users/endaye/Projects/lmdj-goal-grid-tools-layout`;
branch: `feat/creator-grid-tools-interaction-layout`, created without an
upstream and with symlinks enabled. Base and refreshed main:
`50ecc7107a3347878e1d5aa7f72b031d7d58eb98`.

## Premises and ownership

The live umbrella Issue and comments were read. Its U06 layout work remains
outstanding at this revision. `sequence_grid.tsx` already implements NOTE/VEL,
all five grid snaps, direct Bar selection and the full gesture model. Its
Tools dialog puts snap before mode in one compressed row with hidden labels.
The high-fidelity Figma context and screenshot for `407:5536` (Tools screen
`407:4836` in `GPFarNiZNsjLQzfG9kR8DO`) instead show a heading, EDIT MODE,
NOTE/VEL, GRID SNAP in three-plus-two columns, explanation, then Done.
The design contains no static image or SVG assets for this surface.

B01 was delivered by #2115, merge `544efcf159d980dd65f4ecca428df43e67541756`:
current Pattern selection asks the owner to cancel a queued switch and waits
for its projection. This Task does not repeat that behavior or change the
Pattern picker. The subsequent U04 merge changes Project navigation, not
Grid Tools; its full browser tests remain the baseline. Existing Source,
Runtime, controller, gesture and state contracts are retained.

Only the Tools modal is in scope. EDIT header/tabs/Bar/footer, SETUP and the
queued Pattern picker remain U06b/U06c. The main editor's sixteen 13 px lanes,
drag threshold, coordinate mapping, selection, keyboard routing and Bar
navigation stay unchanged. Use the existing `ModalDialog` lifecycle, including
inert background, focus trap, Escape, return focus and retained choices.
No App, runtime, SDK, count-in, recording or timing producer changes.

The approved 32 px visible face and at least 44 actual hit area belong to
U01's shared controls and its unresolved small-screen decision. U06a reuses
existing controls and normal layout flow; it does not shrink their current
hit boxes or add overlapping pseudo-element hit targets. The dialog may
scroll when required. This Task cannot claim the final shared-control sizing
or complete Figma/physical-device acceptance.

## Declared files

1. `apps/creator-web/src/components/sequence_grid.tsx` — only Tools modal JSX,
   its dedicated class and stylesheet import. Mode/snap callbacks stay intact.
2. `apps/creator-web/src/components/sequence_grid_tools.css` — new scoped
   Tools-only layout, using existing typography, colours and controls.
3. `apps/creator-web/test/sequence_grid.test.tsx` — visible groups, both mode
   choices and all five snaps, Done/Escape return focus, no authoring edit.
4. `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs` — extend
   the original real NOTE/VEL journey with Tools group/focus assertions and
   add three-viewport modal geometry/keyboard checks. Preserve every original
   journey leg, case, selection and deadline.
5. `apps/docs-site/docs/hosts/creator-web.mdx` — Grid tools bullet only.
6. `apps/docs-site/docs/hosts/creator-interactions.mdx` — Grid tools row only.
7. This plan.

Shared Portal writes are restricted to those Grid tools paragraphs. Root's
System, U09 Sound Sets, U03 upper-screen and other owners' sections are frozen.

## Verification

Before source edits, run the whole owning `sequence_grid.test.tsx` baseline.
The lowest-tier changed assertions cover visible mode-before-snap hierarchy,
all options remaining reachable, and dialog closure returning focus without
editing notes or clearing selection. Component tests do not prove geometry
or native keyboard activation; the packaged browser cases own those facts.

Run the complete five component files, without filtering cases:

```sh
npm --prefix apps/creator-web test -- --run test/sequence_grid.test.tsx test/sequence_grid_model.test.ts test/sequence_grid_edit.test.tsx test/sequence_surface.test.tsx test/sequence_pattern_structure.test.tsx
cd apps/creator-web && npm exec -- tsc --noEmit
node --check tests/platform/web/creator/creator_web_sequence_grid.spec.mjs
python3 tests/build/ci_change_scope_test.py
```

The new CSS and plan must pass both path ownership and top-level admission.
Inspect the exact staged inventory and whitespace before committing. Run the
whole `scripts/docs-site.sh check` because current Portal facts change.
Portal, build and browser runs wait for Root's serialized heavy window.

After those source checks pass, use the established clean local checkpoint
sequence required by the normal packager; it is not a browser-pass claim.
Run fresh normal `scripts/creator-web.sh build` and `package` from this
worktree with pinned Emscripten 6.0.5, Node 26 and locked dependencies.
Use the tracked Creator Project fixture decoded in this worktree; verify its
digest/length with the normal bundle verifier. Do not borrow foreign binaries.

Run all cases in the packaged Chromium `creator_web_sequence_grid.spec.mjs`,
`creator_web_hardware_layout.spec.mjs` and `creator_web_accessibility.spec.mjs`.
The grid journey keeps add, move, resize, VEL, default velocity, box selection,
batch delete/move, each Undo/Redo, refusal while recording with unchanged
Truth, live snapshot swap without restarting, Stop and exact reopen. The
other grid journeys retain independent view navigation, all Bars and persisted
last-cell/cross-Bar edits. New Tools checks cover visible group order, 3+2 snap
rows, nonoverlapping existing hit boxes, viewport containment/scrolling and
native keyboard activation with actual focused controls. Capture and inspect
the modal's real screenshot against the Figma target; no screenshot-only pass.

Do not push until all declared Task checks pass and Root accepts the receipts.
Full Creator proof, listening, physical devices and the complete 35-screen
acceptance ledger remain separate and unverified by this Task.

## Version Management

Version impact: none — a layout change over existing controls and contracts;
no manifest, API or Product Build allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/, /hosts/creator-interactions/

Update only the Tools layout descriptions. No source diagram changes: the
same existing modal, callbacks and authoring path remain authoritative.

## Evidence

At declaration, all verification is UNRUN. Historical U03a/U04 receipts do
not verify this Task. Pitfall review found no new process invariant to record;
the owning source and tests express this layout and lifecycle behavior.

Initial whole grid component baseline passed 22 tests, exit 0
(`/tmp/lmdj-u06a-baseline.log`). Before changing product source, the added
visible-group assertion failed at the absent EDIT MODE heading: 25 passed,
one failed, exit 1 (`/tmp/lmdj-u06a-red.log`). This is the actual layout gap,
not a callback or runtime failure. Root briefly paused U06a for U03's real
main-merge repair; the U06a draft and baseline were preserved unchanged.

After the admitted Tools JSX/CSS change, the whole grid component file passed
26 tests (`/tmp/lmdj-u06a-green.log`), then the five complete owning files
passed 116/116, exit 0, 7.39 seconds (`/tmp/lmdj-u06a-components.log`). Whole
Creator typecheck exited 0 (`/tmp/lmdj-u06a-tsc.log`); browser-file syntax and
diff whitespace checks passed. A final CSS specificity adjustment ensures
the scoped gap wins over the shared dialog rule regardless of import order;
the Tools-only width follows Figma's 368 px panel while retaining the existing
viewport margin and scrolling. Layout remains subject to the actual browser
checks, not jsdom evidence.

The browser extension retains all four original grid cases and every original
gesture/Truth leg. Three added viewport cases measure the normal-flow hit
boxes and grouping, capture the real modal, and use native Tab/Space/Enter/
Escape to verify retained mode/snap choices and return focus. Actual hit
dimensions are recorded; final shared 32-face/44-actual sizing remains U01's
separate obligation, with no reduced sizing threshold added here. Portal,
build/package and all browser checks remain UNRUN pending Root's window.

Root subsequently admitted the heavy window. Both the pre-Portal and
pre-commit main refreshes still resolve to
`50ecc7107a3347878e1d5aa7f72b031d7d58eb98`; no newer Task premise changed.
The complete Portal check exited 0 (`/tmp/lmdj-u06a-portal.log`): 177 tests,
52 pages, 10 diagram sources/20 outputs and 50 routes/internal links. Scope
ownership passed 77 tests, exit 0, 9.076 seconds
(`/tmp/lmdj-u06a-scope.log`); the staged seven-file inventory and whitespace
check passed. Locked docs/web dependencies are installed without lock changes.

The local clean-source commit is an input checkpoint for the normal product
packager, not a browser-pass claim. The independently decoded tracked fixture
has source SHA-256 `df718fc7b0dc08b6f806767a31ee55e0628b0e03c571ad79483310276f5facd1`,
bundle SHA-256 `66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`
and 767554 bytes. The normal bundle verifier exited 0
(`/tmp/lmdj-u06a-fixture-verify.log`). Build/package and browser evidence will
be bound to that clean checkpoint and recorded in PR Verification, avoiding
a plan-only amend that changes the artifact identity after verification.

The initial checkpoint `66bd9dc5630f3accdc367de46fc2c1ad403fb89e` passed
normal build and package (both exit 0; `/tmp/lmdj-u06a-build.log` and
`/tmp/lmdj-u06a-package.log`). Its first complete three-spec browser run
exited 1: 21 passed, one failed and the existing WebKit-only case was skipped
(`/tmp/lmdj-u06a-browser.log`). The failure is the original Sequence
view-navigation journey's final Project assertion: it still sought
`Previous Project row — ↑`, while U04's current source and the actual
accessibility tree expose `Previous Project — ↑`, disabled. The correction
changes that exact name only; the disabled assertion and every journey leg
remain. All three new viewport cases and the other original grid cases
passed in that run, which does not make the complete run a pass.

The new geometry JSON and modal screenshot are now written to each test's
output path before attachment, so a line-only reporter retains the evidence
for passed cases too. This is test evidence persistence, with no product
change. The original failure trace remains in the `u06a-chromium` results
slot. The unpublished Task checkpoint is amended with this narrow test and
plan repair; final normal build/package and the same complete three browser
specs must run against the resulting revision. Their terminal results and
artifact identity belong in PR Verification, not an unverified completion
claim in this checkpoint.
