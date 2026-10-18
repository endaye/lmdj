# Narrow Creator console hit targets — #2112

## Premises before edits

Integration main refreshed to `f0979f2754faca2a2b26efae8c1a411608b2bbf0`;
Task parent is frozen Draft #2392, `028a8f644b10057ba4216191032013d583a55505`.
Live #2112/#2135 and comments plus all11 open Draft PRs were inspected. No
successor owns this defect. Root main and parent worktrees remain clean; this
isolated `fix/creator-narrow-console-hit-targets` has10 real tracked symlinks.

| Premise | Current evidence / disposition |
| --- | --- |
| Phone Project click is blocked | Reproduced twice on the actual packaged parent with fresh390×844 stores: Project key44×44 is under Touch workspace (x6,width368), Pad region width0. Desktop1440×844 passes the same real pointer/hit oracle. Fresh boot is Sample, so this is a common shell defect, not a Project-specific command failure. |
| Late fit / stale owner causes it | Refuted by fresh contexts, settled boot and actual391→390 resize plus two frames: identical overlap and failed click. |
| Overlay rather than actual geometry | Actual elementFromPoint identifies Touch workspace itself over the key; measured rectangles overlap. No modal or old owner is needed. |
| Common geometry already exists | Perform-only narrow CSS places the matrix above the touch pane to the right of the physical rail. A diagnostic same-origin CSS response applying that existing composition globally restores actual Project click, a258px touch pane and258×250 Pad region. No product source, CSP or command was changed by the probe. |
| Need new responsive product policy | Already approved by2026-10-13 Interaction UI decision: adapt small-screen layout/margins, retain every control and actual44px targets. Reuse that approval and existing Perform geometry; no new command/lifecycle semantics. |
| Generic compact fits before desktop width | Desktop compact matrix width is console width−492; four44px Pads plus three8px gaps need200px, with16px viewport margins. Below708px portrait, use the common stacked composition. Preserve generic compact at708px and all full/rotated layouts. |
| Saved WAV metadata is outstanding | #2135 B remains open and independent. This Task resolves the newly proven input defect before continuing B, without inventing duration or changing its producer. |

The unmodified generic compact CSS is also on refreshed main. The parent adds
Perform-specific avoidance and a mode-dependent refit; neither is evidence that
the common four-region shell was repaired. Historical #2392 restored its
original journey viewport and explicitly retained this phone gap.

## One Task / declared files

- `apps/creator-web/src/styles.css`
- `apps/creator-web/src/components/perform_surface.css`
- `apps/creator-web/src/main.tsx`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/plans/2026-10-19-creator-narrow-console-hit-targets.md`

Declare any scope expansion before editing it. No App/SDK/Facade, audio,
persistence, CI, manifest, Contract, release or resource cleanup changes.

## Implementation

Move the existing narrow Perform physical composition into common compact
portrait CSS below708px: separate left rail, full Pad matrix over one touch
scroller, with existing778px console/250px matrix/344px touch geometry. Move
its Pad text sizing with that common matrix; keep FX-specific typography local.
All modes and System use the same dimensions, so remove the now-unnecessary
Perform-presence refit condition. Preserve mount/resize/refit, scale token,
full-layout rotation, nonshrinking margin policy, controls and lifecycle.

## Verification / defect ownership

1. Before the fix, add a real packaged-browser regression to the owning hardware
   file. Fresh phone boot must leave the Project key and all16 Pads reachable;
   actual pointer clicks must navigate every main mode and System/back, then
   reload and click Project again. Assert effective44px input regions, edge
   and centre hits, actual nonoverlapping four regions and no clipped shell.
   Cover390×844,480×844 and the707/708 portrait boundary; wait for real viewport
   resize plus a frame. Preserve all existing hardware assertions/budgets.
2. Record the original RED on the official parent package, then GREEN on the
   fixed official package. The source defect is CSS geometry; jsdom has no
   real layout seam, so do not add a source-string or mirrored unit test.
3. Complete Creator tests and TypeScript; official pinned Node26/Emscripten6.0.5
   configure/build/clean package. An unpublished verified-source checkpoint
   permits packaging; resolve findings and fold them into this same atomic
   Task before publication. No Native API change needs another Core proof.
4. Run complete original hardware/Perform/touch-fit/meter browser files plus
   the new regression, retaining every original recording/PCM/failure/recovery/
   owner-loss/save/reopen/Replay leg and budget. Run canonical WebKit refusal
   boundaries; do not call them product UI/device acceptance. Persist JSON/PNG
   by output path, read back identity/geometry, inspect phone and desktop.
5. Full Portal check, offline dependencies, staged/committed new-file ownership,
   final body lint/declaration and complete main-range ownership. Native/Wasm,
   Portal and browser heavy windows remain serial. Selection is not execution
   of full batch/candidate lanes.

Private diagnosis retains the inline-style CSP refusal as a failed probe; the
successful diagnostic changed only same-origin stylesheet response bytes.
The new reachability journey uses the original CSP and official distribution,
without diagnostic routing patches, force clicks, synthetic input dispatch or
pointer-events hacks. Existing product journeys keep their original seams.
Existing resize/frame and path-backed evidence guidance applies. No new process
pitfall: the product regression owns geometry/hit facts.

Before commit/publication refresh relevant main and successor history; inspect
complete staged diff, exact committed files and final status. One Conventional
Commit and Draft successor of #2392 on the single frozen stack. Independent
current-head review remains PENDING; no merge/auto-merge until explicit unfreeze.

## Version Management

Version impact: compatible Creator Host PATCH bug fix; deduplicate within the
existing Host MINOR rollup debt in #2237. No version allocation, manifests,
Product/Assembly/Build, immutable snapshot or other compatibility domain change.

## Documentation Impact

Documentation impact: required — `/hosts/creator-web/`,
`/hosts/creator-interactions/`, `/platform/input/`. Describe the common narrow
composition and remove obsolete Perform-only refit claims. No Module boundary
or diagram edge changes. Common geometry/input proof is not complete35-screen
styling, saved-WAV metadata or physical mobile acceptance.

## Verification results

- Packaged parent28a8f64: desktop pointer control PASS; two independent fresh
  phone runs RED. Resizing and two frames remain RED. Same-origin diagnostic
  CSS composition restores real Project click; the inline-style CSP refusal
  is retained separately and did not alter product CSP.
- Final owning regression on the unchanged official parent distribution is
  RED at `fresh phone boot: Project centre/edges intercepted`: four of five
  actual hit points are intercepted; the Pad region is0px wide. The runner
  waits for boot and a frame, probes centre plus four inset edge midpoints
  (not rounded-off corners), and writes the failing geometry before asserting.
- Complete Creator82 files /1905 tests PASS (107.59s), TypeScript PASS, offline
  dependencies PASS and pinned Creator configure/build PASS. No test threshold,
  selected lane, original journey leg or existing budget changed.
- Full Portal179 tests /50 routes/internal links PASS; staged new-file
  ownership/admission76 PASS. Corrected packaged browser results follow the
  verified source boundary and are recorded against the final Draft head.
  Source/Task checks do not establish independent review, integration, a full
  candidate, physical mobile input or hearing acceptance.

- First complete browser selection:43 PASS /1 FAIL. The existing Perform
  acceptance case requires Sequence exit to shrink the workspace and Perform
  reentry to grow it. That is the obsolete mode-dependent composition this
  Task explicitly replaces; the observed values786/786 correctly describe
  the new common geometry. Expand declared files to the owning Perform spec
  before changing those two oracles to strict equality and no conflicts.
  Add actual pointer reentry while retaining the original native keyboard
  entry, COUNT-IN, Truth, System/return and every original journey/budget.
  The failed package/result slot remains retained; rerun the corrected full
  selection on the final clean head before publication.

- Corrected targeted browser selection:2 PASS (15.2s), including the entire
  Perform geometry/Filter/mask/System/pointer/native-keyboard/COUNT-IN/Truth
  journey plus the new common-shell regression. The two obsolete height
  comparisons are now exact equality; no original leg or budget was removed.
  Only the owning test and this plan changed after the successful source/
  Creator/TypeScript/Portal checks; product implementation bytes are unchanged.
