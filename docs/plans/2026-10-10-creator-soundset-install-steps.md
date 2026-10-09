# Creator Sound Set steps (#1923)

## Premises

Baseline: 23 existing Sound Set component/reducer tests passed.

Initial integration/worktree base:
`08c216647138ef9e1f7824a4a2624f82eef86cce` (2026-10-10).
Read live #1923 and current SoundSetSurface/reducer/component and browser
journeys. #1938 Sequence is in review/committed-head proof; adopt its merged
helper/docs changes before shipping, without touching its working tree.

Refreshed integration/worktree base: `0483967a6b67c7e071dc7f31ec56dc288f92a843`.
PR #1938 is merged; its navigation helper, styles and manuals were adopted by
fast-forward with the owned Sound Set edits safely retained. It delivers no
Sound Set step or target-ownership behavior; the premises below remain open.

- Outstanding: Catalog listing, manifest details, sixteen auditions, target
  selection, mapping, occupied-Pad policy and confirmation all render at once.
  Split presentation into Browse, Details, Target and Review steps, keeping
  all metadata, attribution, cached/refused entries and recovery paths.
- Outstanding: mapping uses the performance `.pad-grid`/`.pad` styling though
  its cells are divs, not sound buttons. Replace it with a compact explicitly
  read-only map with four distinguishable outcomes and a full-text legend.
- Delivered: #1913 applies PAD_MATRIX_ORDER (13–16 at top, 1–4 at bottom).
  Keep that actual mapping; do not redraw a second playable Pad matrix or
  alter the physical Bank. Row address order is an independent absolute oracle.
- Delivered: targetBank is separate from activeBank and initialized on mount;
  `bank-selected` clears preview/policy. Installation uses preview.bankId and
  preview.projectRevision, preserving the confirmed target and stale-revision
  refusal. Do not replace these with the latest live Bank/revision.
- Outstanding: target controls remain actionable during a pending preview,
  allowing a late result to display the old target. Keep navigation and target
  changes disabled during an owned request. Keep the existing stale-revision
  refusal at the Facade boundary and expose explicit mapping refresh/retry;
  do not substitute the current revision or add a gate that bypasses that
  existing failure journey.
- Delivered: actual audition/stop controls call Facade-backed Host methods.
  The old AUDITION ATTACHMENT POINT comment saying no byte path exists is
  contradicted by current code/tests; correct that comment, never remove the
  now-functional auditions because of the stale prose.
- Existing Keep/Replace requires an explicit policy for collisions and empty
  source slots never clear Pads. Those rules, receipt, expected revision,
  failed install retry and onInstalled projection callback remain unchanged.

## Task and declared files

One presentation/navigation Task: browse → details/audition → target → mapping
review/Keep-or-Replace/confirm. Back navigation preserves the selected Set,
restores the originating list control's focus/scroll, and never writes Truth.
Only the outer touch workspace scrolls vertically. Step transitions bring the
new step's controls into view; busy operations keep their owner/context.

The read-only map uses compact flat cells, explicit address/status text and a
legend for Install, Occupied, Empty source — Pad unchanged, and Unmapped.
Keep MPC spatial order; do not project it into the left performance Pad area.
All original manifest/licence/attribution information and sixteen slot
entries remain reachable. Do not invent Catalog search, install-to-active-Bank,
new audition semantics, Core operations or destructive policy defaults.

Proposed declared files (refine before implementation):
- `apps/creator-web/src/components/soundset_surface.tsx`
- `apps/creator-web/src/state/soundset_state.ts` only if context invalidation needs an action
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/soundset_surface.test.tsx`
- `apps/creator-web/test/soundset_state.test.ts` if reducer changes
- `apps/creator-web/test/workspace_shell.test.tsx` if entry expectations change
- `tests/platform/web/creator/creator_web_soundset.spec.mjs`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- `tests/platform/web/creator/fixtures/creator_navigation.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/design/2026-09-29-creator-user-workflow-guide.md`
- This plan.

## Verification

Preserve every existing Sound Set component/reducer test and browser journey
leg, migrating only the UI entry transitions. Add regressions for back/focus,
selection retention, target changes/pending preview, explicit stale-revision
refresh, Keep/Replace, cancellation and failed retry. Confirm all sixteen map
addresses in independent MPC order and non-interactive read-only presentation.

Native rendered checks cover each step at multiple viewport sizes, no outer
horizontal overflow, a single main vertical scroller, detail auditions and
mapping/policy/confirm reachability. Retain complete install and reopen
assertions, category/override colour behavior, cached/offline listing,
unsupported/refused Sets, exact traffic/identity and no Project change on
failure. A UI screen alone does not prove audible output.

Run build, staged ownership, portal check, committed-head selected Creator
batch, independent current-head review, live protection/conversation checks,
guarded merge and criterion-by-criterion issue audit. Physical iPad/Safari,
hardware touch and listening remain explicitly unverified in existing issues.

## Version Management

Version impact: none — Host presentation over existing Facade operations;
no Project schema, Core/Contract, Product Build or Assembly identity change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Update step locations and target/confirmation behavior with implementation.

## Pitfall Impact

Pitfall impact: none at premise stage. Preserve native input, full journey and
unique proof-output-slot guidance; classify any newly observed process defect
before shipping rather than treating an intermediate failure as a pass.

## Implementation evidence (2026-10-10)

Precommit origin/main remains `0483967a6b67c7e071dc7f31ec56dc288f92a843`.
The Task changes ten declared files; Core, Facade, physical Bank controls and
Project Truth are unchanged. No new qualifying process pitfall was found.

- Four visible steps share one reducer; selection and native list focus/scroll
  survive returning to Browse. Step changes focus the current navigation key.
  Header/card spacing now uses the fixed touch panel's compact tokens instead
  of inherited desktop headings and nested padded cards. Controls remain 44px.
- Target Bank and Keep/Replace are locked while a preview/install owns them.
  A late independent audition failure previously reset the shared busy phase;
  its dedicated error action now preserves the pending request's ownership.
  Expected revision remains the actual preview revision, so a stale Project
  still refuses safely instead of silently installing against newer Truth.
- All four map outcomes have distinct text; read-only flat cells preserve MPC
  spatial order without performance Pad styling or input behavior. Licence and
  attribution remain visible in Details, Target and Review.
- Component/workspace run: 137 passed; the final additional unclassified-map
  regression brings the Sound Set/reducer subset to 29 passed. Existing 109
  workspace tests passed after adopting Sequence. Deferred-response regressions
  cover late audition failure, target/policy ownership, target invalidation and
  failed-install refresh/retry. Final TypeScript/Vite build passed.
- Three original native Sound Set journeys pass (53.6s), preserving Catalog
  traffic/cache/offline refusals, live audition reply and Host liveness, stop,
  explicit Keep/Replace, exact lineage, installation projection, colours and
  persisted reopen. Source UI uses verified PR #1930 Runtime; committed-head
  packaged Creator proof remains required before merge.
- Added rendered bounds for every step at 1440×900, 1280×600 and 768×600:
  no horizontal overflow or clipped descendant, no nested vertical scroller,
  44px navigation, preserved list selection/focus/actual click scroll, attribution
  and read-only map. Confirmation remains reachable by the outer vertical scroll.
- Initial return-scroll assertion sampled before Playwright's native click
  scrolled around sticky navigation (trace: 719 before click, actual 567).
  The oracle now observes the real native click in capture phase, before React;
  it still requires exact restoration. Controls have scroll margin so keyboard
  focus/scroll-into-view clears the sticky navigation. Failed trace retained.
- Visually inspected full-page Target/Review screenshots; removed legacy excess
  heading/paragraph/card whitespace instead of accepting a width-only pass.
- Portal check passed: 50 routes and internal links, after locked dependency
  installation in this isolated worktree. Manuals describe all four steps.

Evidence: `/tmp/lmdj-ui-goal-20261009/1923-*` and browser result slots
`1923-soundset-source-1` through `-5`, including the initial missing-upstream
configuration diagnostic and failed scroll-oracle trace. Physical devices,
Safari support and acoustic listening remain unverified under existing issues.
