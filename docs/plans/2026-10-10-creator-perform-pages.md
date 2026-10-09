# Creator Perform contextual pages (#1919)

## Premises

Original Task base: `864c0f061033a7f0c3488f1908a8817516cd3b62`.
Refreshed integration and worktree base: `46df56797265942f760afb253c3e4ad2b3a13c80`.
The intervening #1932 records Project DUPLICATE and does not change Perform.
Refreshed live #1919 and successor history on 2026-10-10. Baseline Perform
component suite: 58 passed.

- Outstanding: PatternLaunchStrip renders duplicate Bank controls and the full
  Assign/Clear/Move form before its 16 Pattern slots. PerformSurface stacks
  those, revision, FX/HOLD, every recording action and replay/recovery panels.
  The physical rail already owns Bank selection; the Perform controller's Bank
  projection currently updates only from the duplicate callback. Synchronise it
  from the authoritative Host Bank prop when removing that callback.
- Delivered dependency: #1917/#1928 provides fixed-width, single outer touch
  scrolling. Keep that geometry. #1913 preserves Pad identities while changing
  display order; do not duplicate its matrix or use sound Pads as Pattern slots.
- #1910 provides capture-independent monitor output. The remaining encoder/UI
  projection is separate from this navigation Task. Do not invent the pictured
  LP/HP/BP, Mute/Solo, meters, or a launch capability outside the existing
  Performance recording admission rules.
- Figma Desktop Final D04 `88:2389`, touch `88:2662`, was inspected: Pattern
  launches, Filter/Delay, More FX and HOLD form the live area. Section names and
  MASTER in that picture are not authoritative Runtime capabilities. Preserve
  all 16 real Pattern slots and pending/acknowledged/empty-slot semantics.
- #1918/#1930 merged as `dac4c799`. The isolated Task branch was advanced
  to that main revision with its in-progress edits preserved. Reconciled the
  Sample and Perform navigation imports/helpers, retaining both sets of journey
  assertions. The UI restructuring premises above remain outstanding on this
  main; Sample does not implement Perform pages.

## Task

Use Live, Slots, Takes and Replay pages in one touch scroller. Live opens by
default and retains all Pattern launch slots, Filter/Delay, More FX, HOLD and
phase-appropriate Record/Stop access. Four groups of four retain all 16 launch
slots and show queued/playing indicators even on unselected groups. Group
selection persists across Perform pages and never changes sound Pad identity.
Pattern slots and compact live faders share two columns; HOLD and More FX
remain directly below the faders. Slots owns Assign/Clear/Move and revision.
Takes owns recording flush, naming, Save/Discard, export and retry binding.
Replay owns saved Performances and recovery. Stop Replay remains visible
while playing on every page, so a held live fader never hides the stop action. A stopped recording
and discovered recovery have visible links to their management page.

Keep controller connection, capture ownership, replay polling and visibility/
mode-leave effects on the persistent PerformSurface. Keep local management
selections, recording name and More FX expansion across subpage navigation.
Show only actions applicable to the recording phase, while preserving existing
busy/refusal/retry and artifact-export semantics.

An active FX pointer gesture temporarily disables page navigation until it
releases/cancels; pointer capture keeps release reachable when dragged outside
the slider. Keyboard blur retains its existing release semantics. Switching
pages must not call controller.leave, stop capture/replay, or toggle HOLD. The
normal global mode/visibility leave rule remains unchanged.

Declared files:
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/pattern_launch_strip.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/perform_surface.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_metronome.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- `tests/platform/web/creator/fixtures/creator_navigation.mjs`
- `tests/platform/web/creator/fixtures/perform_helpers.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/design/2026-09-29-creator-user-workflow-guide.md`
- This plan.

## Verification

- Preserve all 58 baseline component tests, adapting only explicit navigation
  and the new phase visibility. Add focused Bank synchronization, page state,
  gesture/navigation, recording and replay continuity regressions.
- Preserve every leg/assertion in packaged Perform, metronome and Sequence
  journeys: launches, FX/HOLD, audio capture, Save/Discard/export, failure,
  owner loss, recover/discard, replay and reopen. Navigate pages explicitly.
- Actual rendered geometry for all pages at desktop, scaled and short-window
  sizes; all 16 launch slots and management actions remain reachable. No
  overflow clipping or reduced journey/timeout assertions.
- TypeScript/build, relevant component suites, ownership, portal check and the
  selected clean committed-head Creator batch, followed by independent review.
- Native pointer-capture behaviour needs browser evidence; a component event
  alone does not prove it. Physical multitouch/iPad/Safari/listening remain the
  existing external acceptance boundaries, not inferred from automation.

## Version Management

Version impact: none — reorganisation of existing Host controls and navigation;
no new public Facade/Contract, persisted truth, Product Build or Assembly identity.

## Documentation Impact

Documentation impact: required — update `/hosts/creator-web/`, `/hosts/creator-interactions/` and the user
workflow guide with Perform page locations and preserved recording semantics.

## In-progress verification and rendered review

- The 58 baseline Perform component tests remain, plus four regressions for
  page selection, recording/HOLD continuity, FX navigation ownership and replay
  polling. Final integrated Perform/workspace run: 171 passed. Build and portal
  checks passed; the latter validated 50 routes/internal links.
- The first browser attempt still targeted the removed duplicate Bank group;
  it was stopped to repair that leg. On the integrated Sample base the complete
  31-test source run produced 28 passes and three failures: the rail uses
  aria-current rather than the removed group's aria-pressed; a saved Performance
  can remain stopped when its WAV bind needs retry, so its saved-row assertion
  must visit Replay even in that state; stopped recording now removes Stop
  rather than leaving a disabled button. Corrections retain saved-row,
  authoritative stopped/sealed, retry cleanup and Project revision assertions.
- Native drag-off proof passed: gotpointercapture was observed, an FX gesture
  was authoritative, all page buttons stayed disabled until release outside the
  slider, then all pages remained inside the same active recording until Stop.
  This does not substitute for physical multi-touch/iPad/Safari acceptance.
- Source preview `127.0.0.1:62662` uses this UI with the verified #1930 Runtime
  distribution at `127.0.0.1:62590`. It is not a packaged #1919 claim. Inspected
  four screenshots: no horizontal overflow, but Live still needs 921 logical
  vertical pixels and Slots 867. The 16 launch buttons hide FX below the first
  viewport. Before committing, compact the live launch presentation (for
  example four selectable groups with explicit current/queued indicators),
  preserve every slot and validate its real hit targets and full journeys.
  Log/script/screenshot artifacts are retained in `/tmp/lmdj-ui-goal-20261009/`.


## Final layout and precommit evidence

- The four groups keep all 16 Runtime slot addresses. A component regression
  visits and launches all sixteen, checks exact request indices, and preserves
  the selected group across pages. Queued/playing words remain on an offscreen
  slot's group. The original empty-slot/silent-gap acknowledgement remains in
  the browser journey.
- Live uses adjacent Pattern/FX columns. The old vertical range styling used
  block-size as its length, which actually widened a vertical-writing-mode
  input; narrow columns exposed overlapping hit areas. Correct inline/block
  sizing makes the faders 80px tall and 44px wide. A browser geometry regression
  checks both real hit areas, orientation, non-overlap and first-screen bounds
  for both faders, HOLD and More FX at all three viewports.
- Rendered source preview now has 368px scrollWidth for the 368px panel. Live
  content is 575px including the lower recording/status information, versus
  921px previously; the default first screen contains Pattern launch and all
  primary FX controls. Vertical scrolling remains available without clipping.
- The source proof server now matches the packaged general journey's absent
  Catalog upstream. The earlier bind-cleanup failure contained unrelated
  `.lmdj-host/soundset-slots/` WAVs from the live Catalog preview. No file-cleanup
  oracle, timeout or journey leg was relaxed. Live Catalog preview stays on its
  separate origin. Retain both failed and corrected environment evidence.
- Component verification: 172 passed (Perform 63, workspace shell 109).
  TypeScript/Vite build passed. Portal check passed, including 50 routes and
  internal links. React review keeps controller effects/polling persistent,
  calls Hooks before visibility returns, and adds no fetch or global listener.
- The intermediate browser run was intentionally interrupted after geometry
  inspection found the range-axis defect. It is not a pass. The corrected full
  source journey run and subsequent committed-head batch are required below.
- Pitfall impact: none — product layout and navigation defects are captured by
  regressions; the source-server setup mismatch is recorded with its precise
  environment here and does not change the canonical proof harness.

- #1934 added the interaction manual on main during verification. Adopted its
  merged base without modifying another worktree; updated its Perform rows in
  this Task to avoid shipping a stale duplicate-Bank description.
- The corrected 32-journey source run passed 30 and failed two new layout/
  native-input regressions. The no-Catalog failure banner consumes a control
  row; HOLD/More now share one row so both remain first-screen controls. The
  native drag must scroll back from Record before aiming, because the sticky
  navigation occludes a range scrolled to the top. Retained real mouse wheel,
  pointer-capture and authority assertions. Page changes now reset the view to
  the new page's beginning; a real wheel/Slots/Live journey guards that fix.

- Native event probing resolved the remaining capture-test assumption:
  Chromium's vertical range thumb captures inside its UA shadow tree. Window
  capture-phase events are retargeted to the Filter input, but that public
  input's hasPointerCapture is false. The retained event sequence is down →
  gotpointercapture → move (including outside) → up → lostpointercapture;
  authoritative open FX transitions 1 → 0 and the recording survives. The
  final browser test asserts both real capture/release events and that
  lifecycle, rather than assuming the outer DOM input owns native capture.
  The diagnostic probe passed in 8.7s; its full log is retained separately.
