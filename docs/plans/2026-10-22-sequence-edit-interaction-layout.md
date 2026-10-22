# Sequence EDIT layout and transformed pointer coordinates (#1671 / #2112 U06c)

## Authority and current premises

Task branch `feat/sequence-edit-interaction-layout`, isolated worktree; stack base
`a65d57075de343eb0df9258f7d55b97a8468d35e` (Draft2467), above2466 /9b5160fd.
Current integration main84136533c3d1575084b4b4667e905b1a183fa237. Their Creator UI
source is byte-identical to main. Parent independent review is unavailable;
keep this layer on the same stack, never merge an intermediate Draft directly.
Refresh live main/parent/Issue before commit and before eventual integration.
The continuing2112 authorization covers implementation, verification, commit,
push/PR, and guarded ordinary integration. Frozen release/workflow paths stay
excluded. No subagents, release, deployment or Channel action.

Live1671 still owns U06c and manual device acceptance. T1/T2/T3 are delivered by
1766/b76cf207,1769/de09fbd6 and1778/49d4a3c2; do not rebuild Domain/grid authoring.
Current source has16 lanes, actual Grid Tools and Bar navigation, Undo/Redo and
recording refusal. U06a Tools and SETUP already have their own layouts. Retain
current Pattern/queued-target/owner cancellation behavior and current history.

## Design evidence and dispositions

Canonical2112 links Figma GPFarNiZNsjLQzfG9kR8DO,400:67;1671 identifies403:1162.
The whole-frame request was sparse; correlate its actual child IDs, then use
high-fidelity contexts403:1863 (heading),1866 (tabs),1873 (toolbar),1886 (grid)
and1862 (whole touch workspace). The actual368x368 inline workspace screenshot
was inspected. A separate whole-frame URL download returned0 bytes and is not
visual proof. High-fidelity workspace contains no static image/SVG asset: all
notes/cells are data-driven geometry. Reuse existing kit, fonts, colours and
callbacks; screenshots remain reference-only and never implementation assets.

Remaining presentation: heading with read-only BPM, full-width EDIT/SETUP tabs,
44/148/44/76 toolbar grouping, Tools label and dynamic NOTE/VEL+SNAP help footer.
The prototype32-unit faces do not override approved D0's nonoverlapping44 actual
hit areas. Preserve32 faces through the shared kit and normal flow; the named
vertical-scroll workspace may scroll, and all16 lanes remain rendered/reachable.
Do not shrink musical rows into falsely claimed44-unit ordinary controls.

Remaining input: current tick/pad/velocity and selection-preview math directly
uses clientX/clientY axis-aligned DOMRects. Main's sole StageFit writer can
apply rotate(-90deg), so establish a component red against real handler calls
with independently specified transformed geometry before fixing this path.
Map logical axes and local preview coordinates from the actual stage transform,
not viewport shape. Preserve drag threshold, gesture-to-edit mapping and Native
recording locks. A layout change mid-gesture cancels the draft, never commits
coordinates from an old layout. Verify with actual portrait/scale mouse input
and far-side Project Truth, not synthetic viewport or dispatchEvent evidence.

## Exact declared files

1. This plan: docs/plans/2026-10-22-sequence-edit-interaction-layout.md
2. apps/creator-web/src/components/sequence_touch_workspace.tsx
3. apps/creator-web/src/components/sequence_grid.tsx
4. apps/creator-web/src/components/sequence_edit_layout.css
5. apps/creator-web/test/sequence_surface.test.tsx
6. apps/creator-web/test/sequence_grid.test.tsx
7. tests/platform/web/creator/creator_web_sequence_grid.spec.mjs
8. apps/docs-site/docs/hosts/creator-web.mdx
9. apps/docs-site/docs/hosts/creator-interactions.mdx
10. apps/docs-site/docs/platform/input.mdx
11. apps/creator-web/test/workspace_shell.test.tsx — retain all switch/Stop
    assertions; update only the rendered two-digit Bar caption expectations.

Full Creator verification exposed four old unpadded caption assertions in the
existing switch journeys. This file is admitted before editing; no switch,
history, transport or Truth oracle changes.

Amend before any additional edit. No App, shared kit, StageFit, Domain/Facade,
SDK, timing, recorder, generated identity or release files change. Preserve
other worktrees and their unrelated dirty work.

## Verification

Run the unchanged complete Creator tests and TypeScript first; establish the
transformed-coordinate red on the actual component seam. Verify layout and
all retained grid edits at component level. Complete final Creator tests/types,
full Portal, staged new-path ownership and committed-range classification.
Official clean ordinary Creator build/package uses pinned Emscripten6.0.5,
Node26 and locked browsers with conformance OFF. Decode/verify this worktree's
tracked Project fixture through the normal verifier; no foreign binary proof.

Run every case in creator_web_sequence_grid.spec.mjs (original add/move/resize,
velocity/default velocity, batch selection/delete/move, each Undo/Redo, recording
refusal with no sent mutation, live in-place edit/unchanged origin, Bar viewport,
last-cell/cross-Bar persistence, Stop and exact reopen), plus complete hardware
layout and accessibility specs. Add portrait/scale pointer cases with absolute
expected tick/Pad/end/velocity and whole Truth/reopen. Keep all old legs and
budgets. Verify normal actions' nonoverlapping44 actual hits, all16 lanes and
local Figma correspondence; preserve passing/failing screenshots, JSON and logs
in separate owned run slots and read back every needed attachment.

The official packager requires clean source. After tests/types/Portal/ownership
and source inspection pass, make a local clean-source checkpoint; its committed
identity is the input to the official build/package and all browser journeys.
It is not shipping or Task completion. Any browser defect requires correction,
affected verification and a new clean checkpoint before the complete selection
is rerun. Keep one final unpublished Task commit before pushing this Draft
layer. Final package/browser receipts live in its PR body and retained external
evidence, avoiding a source-identity cycle caused by editing this plan afterward.

### Pre-checkpoint evidence

- Unchanged baseline:85 Creator files/1963 tests PASS94.994s; TypeScript PASS.
- Actual component red: unchanged source passes scaled upright control and
  fails rotated input at the exact onset oracle (0.717s). No deadline or
  edit-semantic change. Final component selection:77/77 PASS1.710s, including
  rotation/scale for move, end, velocity, box coordinates and cancellation.
- First full verification:84 files passed/one failed, four old unpadded Bar
  caption assertions. Preserve switch/Stop/Truth legs and update only captions
  in the newly admitted test file. A prematurely launched partial-correction
  run was explicitly stopped (exit143); it is not a pass. Corrected complete
  run:85 files/1976 tests PASS93.611s. TypeScript PASS0.766s.
- Full Portal check PASS73.000s, including51 routes and internal links. All
  tracked symlinks are actual symlinks. The tracked frozen Project fixture is
  decoded and accepted by the normal bundle verifier. Main refreshed before
  this checkpoint remains84136533; no premise or source conflict changed.
- Staged ownership, clean package, actual browser pointers, screenshots and
  acceptance attachment readback must be inspected before shipping. No manual/
  device or complete candidate result is inferred.

### First clean browser checkpoint and correction

At local5ef6a778, official build/package PASS with conformance OFF. Complete
three-spec Chromium selection:27 PASS/one expected browser-boundary skip/one
FAIL260.099s. Both new portrait and enlarged-desktop journeys passed all14
edit/history/first-last-track legs and whole Truth reopen with no page error.
The retained original journey's VEL stroke was3.5 screen pixels after the row
geometry changed, below the unchanged4-pixel threshold, so no edit was sent.
Move its starting point inside the note's foot to cross4 pixels while retaining
the exact midpoint velocity64 and every later journey leg. Retain the failure.
Visual inspection also found the shared button selector winning over the
heading's font/fill. Strengthen only the local heading selector and add actual
rendered design assertions. Verify footer reachability explicitly. Refresh the
nearby old documentation sentence to the already-delivered B01 recording-time
selection rule; change no selection or transport implementation.

Physical touch/real Safari/listening remain manual1671/1221 acceptance. This
Task cannot close2112 or infer complete candidate/release/device acceptance.

## Version Management

Version impact: Creator Host MINOR for compatible EDIT presentation, absorbing
its coordinate PATCH into existing same-domain2237 debt without lowering any
higher debt. No API/ABI, Contract, Project Truth shape or manifest/Product/
Assembly/Build/snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/ /platform/input/
Reason: EDIT grouping/help and transformed musical-editor coordinate ownership.
No architecture topology changes; the same existing Host/Facade paths remain.

After this correction, the complete85-file/1976-test Creator suite PASS93.299s
and full Portal PASS57.629s. Main refresh remains84136533. Rebuild/package the
new clean checkpoint and rerun all29 browser cases; earlier failures and initial
visual screenshots stay retained. Final receipts belong in the PR/evidence.
