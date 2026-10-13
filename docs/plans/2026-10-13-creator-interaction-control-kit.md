# Creator Interaction UI: common control foundation

Relates to #2112 (U01). Owner: `control_kit` agent; the root coordinator owns
integration, resource scheduling and the remaining UI Tasks.

## Premises before implementation

Initial Task base was `9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`.
Resumed on 2026-10-13 against freshly fetched `origin/main`
`613e23c26bb0ae54dccd75003b8858ac484b0faf`. The five owned draft files were
preserved with full contents, SHA-256 and a patch under
`/tmp/lmdj-u01-pre-main-613e23c/`, then reapplied without conflicts after a
fast-forward. Preservation stash: `c07442f3e91f9793515c898ebab099a77924c87c`.
The live umbrella and comments, current source, owning browser assertions and
successor PR list were reread before editing. No successor implements U01;
#2107 owns retained Sample assignment and must not be duplicated.

Before heavy verification, integrated newly merged U06a / #2123 by
fast-forward to `97897f880a218233b7ae58e4d4c3986271d221f8`. All eight drafts
were preserved under `/tmp/lmdj-u01-pre-main-97897f88/` and stash
`e5614d6e2162d0ef93491d9a38266742746a317c`, then reapplied without conflicts.
The shared Portal page retains U06a's modal grouping description. The new
Grid Tools CSS delegates all eight buttons to `touch-control`; its NOTE/VEL,
five Snap options and primary Done now consume U01's face/state rules. Add
actual modal style checks to the existing U01 spec and run the complete
owning sequence-grid spec; its original journeys and bounds remain unchanged.

Pre-checkpoint refresh: `origin/main` is
`1b1756b479b12d5929ad8e508cc4b711c8bb2845` (#2127). Its three documentation
paths record the approved adaptive geometry and separate palette decision;
there is no product-input change from this worktree's `97897f88` base. The
live #2112 remains open with no comments. The U01 premises still hold.

| Premise | Disposition and evidence at this base |
| --- | --- |
| Ordinary controls use the previous visual system | Outstanding: `styles.css` uses Space Grotesk 12/16, 36-unit visible faces and 44-unit layout boxes. Sequence is explicitly exempted. The owning `compact actions` browser test asserts those previous facts. |
| New control typography and states | Outstanding: Figma `400:85` and `400:132` high-fidelity context and screenshots specify IBM Plex Mono Regular 9/13, 32-unit faces and 6-unit radii. Touch variants are Primary, Secondary, Selected, Danger and Disabled. |
| Design dimension conflict | Resolved by the user's 2026-10-13 choice: 32 visible face and at least 44 hit area; verify effective scaled targets. |
| Physical CSS-pixel minimum under stage fit | Still outstanding in current source, product choice now resolved: the user explicitly allows adaptive small-screen layout and margins while retaining the wide-screen Figma layout, actual nonoverlapping targets at least 44 CSS px, and no horizontal scrolling. The fixed 880×640 workspace still yields scale 0.7875 at 1280×600 / 768×600, so source layout must change before U01 can pass. |
| Offline assets and semantics | Already present: local IBM Plex Mono and Space Grotesk font packages, native buttons, disabled/pressed/current attributes and focus-visible styling. Reuse them. No new exported image is needed for the two control component nodes. |
| Rail text and physical order | Delivered by U02a / #2117 / `45c8f479aa350cd490a100044a4723428976e2be`. Preserve PRJ/SMP/SEQ/PRF, REC/PLAY, SHIFT after Banks, callbacks and accessibility order; do not redo its markup. |
| Project and Sound Sets layout | Delivered by U04 / #2120 / `50ecc7107a3347878e1d5aa7f72b031d7d58eb98` and U09 / #2122 / `613e23c26bb0ae54dccd75003b8858ac484b0faf`. Preserve their scoped CSS, single-column selection and four-step actions. New consumers still use `--creator-font-action`; retain that token while ordinary buttons adopt Mono explicitly. |
| Queued Pattern cancellation | Delivered by B01 / #2115 / `544efcf159d980dd65f4ecca428df43e67541756`; keep current `touch_kit.tsx` behavior. |
| Five-colour Pad palette | The user approved synchronizing all five new colours without changing stable indexes. Root assigns that separately to U02b; no palette-index or Pad state changes belong to U01. |

## Task and declared files

1. Use existing buttons and `touch-control`; provide the five Figma variants
   through CSS, a separately painted face, reserved normal-flow target space,
   and unchanged native focus/disabled behavior. Rich Project cards, launch
   tiles, Pad colour swatches, musical Pads and waveform/grid edit geometry
   remain under their owning page Tasks.
2. Apply shared typography and radius to existing rail faces, without silently
   enlarging overlapping rail targets or changing their actions/assets.
3. Update the existing geometry oracle and add focused state/hit testing.
   Report real CSS-pixel measurements separately from design-unit dimensions.

Declared files:

- `apps/creator-web/src/styles.css`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
  (shell/rail geometry and the existing compact-actions block; retain all journeys)
- `tests/platform/web/creator/creator_web_control_kit.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-13-creator-interaction-control-kit.md`
- `apps/creator-web/src/main.tsx` (stage-fit selection only)
- `apps/creator-web/src/components/hardware_console.tsx` (pure layout policy only)
- `apps/creator-web/test/hardware_console.test.tsx` (layout/portrait boundaries)

No new shared React abstraction or behavior change. `touch_kit.tsx` requires
no markup change for the current proposal. App, Project and physical-control
markup stay with their owners. Danger styling
is an explicit class hook, not a selector inferred from accessible text.

## Approved adaptive layout

Use the original fit when the wide/rotated Figma console fits at scale at
least 1. When it would shrink below 1, choose one compact layout before
measuring and fitting its natural size; do not clamp an oversized console
and clip its controls. Keep the existing four regions and their DOM order.

- Compact header and footer: 24 px each; console outer block margins: 4 px.
  Console width `min(880px, viewport width - 16px)`, height 544 px. At the
  required 600 px viewport height, the stage and natural workspace are both
  552 px, so no downward scaling is needed. Compact fitting caps its scale
  at 1 and centres the shell, retaining those actual outer margins at taller
  viewports instead of enlarging the shell to consume them. The existing full
  layout still enlarges; the existing portrait layout still caps at 1.
- Compact rail: 92 × 528 px, comprising a 48 px logo, a 92 px encoder area
  and a 380 px key area, with 4 px gaps. Encoder and key tracks reserve 44 px
  targets with 4 px gaps; visible key faces stay 32 px. Keep the logo asset.
- Preserve a 368 × 368 touch workspace. An overview 152 px high and a Pad
  matrix in the remaining left-hand width fit the compact shell. At
  768 × 600 the Pad matrix is 260 px wide: four 59 px Pads plus three 8 px
  gaps. Pads stay square and exceed the actual target minimum.
  The compact overview uses 8 px padding / 4 px gaps and aligned 8 px
  status insets; Sequence uses 2 px outer row gaps so its header, encoder
  readbacks and all eight unchanged track rows fit the 136 px content height.
- Wide rail targets can reserve 44 px tracks around the original 32 px face
  centres. Their original 48 px pitch leaves a real 4 px target gap; the
  expanded grid is 92 px wide, with no overlapping pseudo-element targets.
  SHIFT retains an 80 px face within its 92 px target.

Root admitted all eight exact paths above on 2026-10-13. Select the layout
from viewport dimensions and the original full-layout chrome dimensions,
never from a stage already changed by compact mode. That avoids a feedback
loop on resize or Runtime remount. The existing hardware-layout spec needs
its shell/rail geometry
assertions updated to distinguish faces from targets, retaining every
journey and the wide-screen frame positions.

Geometric acceptance viewports: 1440×900, 1024×768, 1280×600, 768×600,
768×900 and 768×1024. Check the actual button/encoder/Pad targets, inset
pointer activation, sibling nonoverlap, keyboard focus, outer horizontal
fit and contained scrolling, including forward/backward resize and Runtime
remount. Preserve the fitting wide-screen layout and
the fitting 768×1024 portrait rotation. Source calculations are a proposal,
not rendered acceptance. The supported geometric acceptance range remains
at least 768 px wide and 600 px high; smaller viewports are not silently
counted as accepted. No control is conditionally removed for space.

## Verification

Lowest-tier checks and the defect they catch:

- `npm test -- --run test/hardware_console.test.tsx test/shell_polish.test.tsx test/sequence_grid.test.tsx`
  in `apps/creator-web`: preserve shell stage-fit and existing action semantics.
- `npx tsc --noEmit` in `apps/creator-web`: preserve the consumer build contract.
- Complete owning hardware-layout, accessibility and sequence-grid specs, plus the
  new control-kit spec on Chromium/WebKit as configured:
  catch wrong font/state/face, invisible focus, target overlap, ineffective
  reserved hit insets and outer horizontal overflow on actual rendered pages.
- Six-viewport receipts assert all 20 rail controls, 16 Pads and four Sample
  navigation actions. Forward/backward resize and a real reload / remembered
  Project reopen verify asynchronous Runtime boot mounting. This is not a
  claim about replacement-generation recovery; existing lifecycle journeys
  remain untouched.
- The existing font-loading browser test: verify both bundled fonts remain
  usable under distribution CSP, with no external font dependency.
- `scripts/docs-site.sh check`: current portal facts and links.

The coordinator granted U01 the exclusive heavy window after U10 completed.
Run current source/component checks, the whole Portal check and staged new-file
scope check before the authorized clean local checkpoint. Then run a fresh
normal build/package and the four complete owning browser specs. The local
checkpoint permits packaging an exact clean tree; it is not completion or
permission to push before the remaining checks pass. Root owns final review
and merge.
The scaled target policy must pass before commit; a partial CSS result is not
a completed U01. This Task does not claim all 35 screen layouts, real devices,
audio acceptance, release or deployment.

## Version Management

Version impact: none. This Task changes presentation and tests only; it does
not allocate a Product Build or change Module, Host, Provider or Contract
identity. No immutable snapshot is allocated.

Documentation impact: required — `/hosts/creator-web`, common controls and
their verified geometry boundary.

## Evidence

- Initial worktree clean on `feat/creator-interaction-control-kit`.
- Historical initial-base targeted component verification: PASS, 2 files / 29 tests.
- Historical initial-base post-change component verification: PASS, 2 files / 29 tests;
  `npx tsc --noEmit`, browser-spec JavaScript syntax and `git diff --check`: PASS.
- Resumed-main baseline: complete hardware-console and shell-polish component
  files PASS, 32 tests; raw `/tmp/lmdj-u01-resumed-components-baseline.log`.
- Resumed source: the same complete component files PASS, 39 tests (including
  seven layout/threshold/round-trip cases); raw
  `/tmp/lmdj-u01-resumed-components.log`. `npx tsc --noEmit`: PASS, raw
  `/tmp/lmdj-u01-resumed-tsc.log`.
- Current-main Portal/browser checks and effective 44 CSS-pixel geometry:
  UNRUN. Source calculations and component tests do not verify rendered fit.
- After U06a integration, three complete component files PASS, 65 tests.
  The new compact-margin regression then failed against the uncapped fit at
  its exact assertion (`scale=1.021276…`, `dx≈0` instead of `1` / `8`), raw
  `/tmp/lmdj-u01-compact-margin-red.log`. After the approved max-scale fix,
  all three files PASS, 66 tests, raw
  `/tmp/lmdj-u01-integrated-final-components.log`; integrated `tsc`: PASS,
  raw `/tmp/lmdj-u01-integrated-final-tsc.log`.
- Exclusive-window pre-checkpoint rerun: all 66 component cases and `tsc`
  PASS (`/tmp/lmdj-u01-final-components.log`, `/tmp/lmdj-u01-final-tsc.log`).
  Whole Portal PASS: 177 tests, 50 routes and internal links, terminal exit 0
  (`/tmp/lmdj-u01-portal.log`). All ten tracked symlinks are actual links.
  Browser/build/package remain UNRUN at this local checkpoint. No new
  process pitfall was observed; compact-margin behavior is captured by the
  regression test rather than a ledger entry.
- Exact eight-file staged inventory and whitespace PASS; the new-file scope
  suite PASS, 77 cases (`/tmp/lmdj-u01-scope.log`). The official tracked Project
  fixture was independently decoded in this worktree and accepted by
  `tools/project-bundle/project_bundle.py verify`: 767,554 bytes, bundle SHA-256
  `66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`.
  Hardware overview uses its declared all-Pad fallback fixture; no foreign
  native binary or rewritten bundle is used. Final build/package/browser
  receipts belong under ignored `build/verification/u01/` and the PR's
  Verification section, so recording their exact commit identity does not
  recursively change that identity.
- First clean checkpoint `6e99d036ddca921a89e4dd0882d89dbf117ad8e9` normal
  build/package PASS. Its complete four-spec Chromium run exited 1:
  31 PASS / 1 FAIL / 1 existing WebKit-only skip (3.1 minutes), raw
  `/tmp/lmdj-u01-first-browser.log`, trace retained in
  `tests/platform/web/test-results/u01-first-chromium/`. The new ordinary
  inset test incorrectly expected Sample sliders after a no-Catalog boot,
  whose unassigned Pads correctly have no playback controls. Fix only its
  prerequisite by importing the verified bundle through the real Project UI;
  retain Volume/Tone far-side assertions, keyboard focus and all deadlines.
  The six geometry cases, round trip/remount, Grid Tools state and all original
  hardware/accessibility/grid journeys passed. Product and Portal bytes are
  unchanged by this test/plan amendment. Rebuild/package and rerun the complete
  original selection against the amended clean checkpoint before shipping.
- Removed the inherited `origin/main` upstream before any push; integration
  remains under the root coordinator.
