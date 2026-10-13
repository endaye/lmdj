# Creator Project single list — #2112 U04

## Premises and authority

- Initial implementation base: `9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`.
  `ProjectSurface` supplied horizontal ±1 and vertical ±3 navigation;
  `.hardware-workspace .local-projects` rendered three columns. This is the
  delivered K2a behavior, not an unimplemented claim.
- Refreshed integration base: `2a5ec35f6bc1433539fc7064c30be756d779ae29`
  (D0 #2114). Its approved [Interaction UI decision](../prd/decisions/2026-10-13-creator-interaction-ui-baseline.md)
  supersedes the old Project three-column rule. Still outstanding: single
  cards, adjacent ↑/↓ navigation, no ordinary ←/→ assignment, selected-card
  Open and the Figma action hierarchy. Existing controller ownership, import,
  create, duplicate and recovery are already implemented and stay intact.
- Live umbrella #2112 and the original
  [K2a plan](2026-10-13-creator-project-sample-navigation.md) were read before
  implementation. The user explicitly approved single-column selection,
  endpoint stopping and explicit Open, including unchanged SHIFT history.
- Read `figma-design-to-code` before `get_design_context` for file
  `GPFarNiZNsjLQzfG9kR8DO`, node `401:3669`; read its screenshot and generated
  design context. Owned touch child is `401:3860`: PROJECT/LOCAL, top New and
  Import, selected-card Open, lower Duplicate/Sound Sets and browse hint.
- LocalProjectSummary has no display name or Pattern count. The mockup's
  sample titles and counts cannot be copied into product state. The view uses
  short real Project IDs and actual Pads, Assets, BPM and revision; the full
  ID remains in the card title. A long user-name test is not applicable until
  a real name field exists; actual UUID metadata overflow is browser-owned.

The D0 rebase used an owned autostash. Tracked before/after diffs were byte
identical, and the untracked CSS hash was unchanged. Other worktrees were not
modified. B01 #2115 subsequently merged at
`544efcf159d980dd65f4ecca428df43e67541756`. A second owned autostash rebase
absorbed current main `ecc2c9ece903bcbd8205e6dde655c28ec07ebf2a` (also #2107).
Every U04 added/deleted line was preserved; only diff base hashes/coordinates
changed, and both untracked-file hashes matched. B01 touches GROOVE and #2107
adds retained Pad assignments; neither delivers or changes U04 Project
navigation/list premises. No new Facade capability is used here.
U02a #2117 is now merged at refreshed main
`45c8f479aa350cd490a100044a4723428976e2be`. The owned dirty patch and untracked
file hashes were saved under `build/verification/u04/pre-45c8f479/` before an
owned stash/rebase/apply. Only the expected focus-array hunk conflicted: both
approved intents are retained as Banks, SHIFT, Next Project ↓, Record,
Play/Stop, Pad A13. U02a owns physical order and labels; Project single-column
navigation still requires this Task. The new main commits do not deliver it.

## Declared files

1. `apps/creator-web/src/components/project_surface.tsx`
2. `apps/creator-web/src/components/project_surface.css` (new, page-owned)
3. `apps/creator-web/src/app.tsx` (Sound Sets entry wiring only)
4. `apps/creator-web/test/shell_polish.test.tsx`
5. `apps/creator-web/test/workspace_shell.test.tsx` (Project navigation and old
   chooser-entry seams only; retain import/history/recovery far-side checks)
6. `apps/creator-web/test/project_create.test.tsx` (obsolete browse entry only)
7. `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs` (Project
   journey only; shared control and physical-rail blocks belong to U01/U02a)
8. `tests/platform/web/creator/creator_web_accessibility.spec.mjs` (Project
   browse entry and arrow accessible names; coordinate SHIFT order with U02a)
9. `tests/platform/web/creator/creator_web_browser.spec.mjs` (obsolete browse
   entry only; keep create/remember/reload assertions)
10. `apps/docs-site/docs/platform/input.mdx` (Project rules)
11. `apps/docs-site/docs/hosts/creator-interactions.mdx` (Project facts; retain
    historical K2a record with an explicit supersession note)
12. `apps/docs-site/docs/hosts/creator-web.mdx` (Project browse/current facts)
13. This plan.

`styles.css`, Core, Facade, Host protocol, Project model and other agents'
worktrees are outside this Task. `.project-card` remains on rich card buttons
so U01's ordinary-control selector does not restyle them. U01 owns common
32-unit faces and the approved hit-size requirement. U01 separately owns
actual >=44 CSS px compliance after scaling; this Task does not establish
that pending result from a 44-unit CSS declaration.

## Implementation and acceptance

One local selection is shared by card, ENC1 and ↑/↓. Boundary keys stop;
ordinary ←/→ remain unassigned and SHIFT + ←/→ still routes history. Changing
selection keeps the open Project, Truth, audio and trigger traffic unchanged.
The touch panel scrolls the selected card and its Open into view using layout
coordinates that survive console scaling/rotation. ENC2 continues to scroll
without selecting or opening.

Only the selected card carries a native Open button. Opening still uses the
existing serialized App journey and only changes the current Project after
its authoritative result. Duplicate still copies the open Project even when
a different card is selected. New/Import, Duplicate/Sound Sets are reordered
without moving their action ownership. Empty/importing/refusal/retry states
and the `Open local Project` duplicate-import recovery action remain.

The single-column CSS owns only the Project touch page; the legacy isolated
summary component's tests remain. No product schema or fake persisted names,
counts or timestamps are introduced.

## Verification

Required lowest-tier checks and defects caught:

- Full `shell_polish.test.tsx` and `project_create.test.tsx`: 0/1/multiple card
  states, selected Open, action hierarchy and unchanged create/duplicate
  refusal/storage/remembered-open journeys.
- Full `workspace_shell.test.tsx`: mounted real App selection routing and no
  unintended Facade calls, serialized opens, blocked actions during import,
  current Project and Sample-owner/recovery/history boundaries. Its manual
  stylesheet injection includes the new owning CSS for the layout seam.
- `npx tsc --noEmit`; `node --check` on the three changed browser suites;
  `git diff --check`; applicable change-scope tests.
- Fresh official build/package and owning browser selections after Root's
  resource window: rewritten Project hardware journey, keyboard-only Project
  and focus-order accessibility cases, and browser New/duplicate/reload cases.
  The Project geometry journey uses four real created Projects at 1440×900,
  1280×600 and 768×600, validates one column and metadata overflow, card hit
  testing, every adjacent navigation leg, endpoints, card/encoder selection,
  selected-card visibility, independent ENC2 scrolling, no native project.open/trigger traffic and full
  Truth equality before explicit Open. Explicit Open must issue project.open
  for the selected identity, update native Truth, and survive reload.
  Execute the complete named cases: hardware `Project arrows follow the
  single list and only Open changes Project`; accessibility `keyboard-only
  Project and Bank journey preserves native activation`, `packaged Creator
  owns an exact local-only asset inventory`, and all three `responsive keyboard
  surface` cases (the actual owners of keyboard focus order);
  browser `boot creates a stored Project, New Project adds one, and a reload
  reopens the last` and `Duplicate copies the open Project under a new
  identity, keeps edits apart, and a reload reopens the copy`. Keep their full
  original journeys, timeouts and far-side assertions. The owning Project
  case captures first-card and scrolled-selection screenshots at each viewport
  for comparison with the approved touch layout.
- Whole `scripts/docs-site.sh check`: the three current Portal routes and
  internal links must render and pass without rewriting historical evidence.

Execution receipts so far (source preparation, not completion):

- RED: the new mounted Project navigation test failed on old source because
  `Next Project — ↓` did not exist. The previous ±3/three-column behavior was
  read in source and the owning CSS seam before the fix.
- First post-change selection: 4 component failures exposed the obsolete
  Open local test steps and an overly strict no-argument synthetic-click
  expectation. Those tests were migrated without dropping their far-side
  outcomes. The first focused workspace check also exposed missing new CSS
  from its manual JSDOM style injection; it now loads both owning stylesheets.
- Current `shell_polish` + `project_create`: PASS, 37 tests (3.80 s).
- Full `workspace_shell`: PASS, 188 tests (70.52 s); subsequent added 0/1-item
  endpoint cases PASS, 2 tests. TypeScript and all three browser syntax checks
  PASS. Whitespace PASS. Ownership scope suite PASS, 77 tests (9.052 s).
  After the B01/#2107 rebase and ENC2 full-card scroll-stride correction,
  TypeScript and the final three-file component selection PASS: 227 tests in
  72.09 s. Receipts are in ignored `build/verification/u04/`; browser remains
  UNRUN.
- Initial whole Portal attempt failed before execution because a fresh
  worktree lacked its local MDX/glob/cheerio dependencies; retain
  `portal-precheckpoint.log`. After its locked dependency install, the entire
  Portal check PASS: 177 tests, 50 routes and internal links
  (`portal-installed.log`).
- After the U02a merge, refreshed TypeScript and all three component files
  PASS: 227 tests in 68.56 s (`component-45c8f479.log`). Browser syntax and
  whitespace PASS; scope suite PASS, 77 tests in 8.608 s.
- Fresh complete Portal on base `45c8f479`: PASS, 177 tests, 50 routes and
  internal links (`portal-45c8f479.log`).
- Root admitted U04's heavy window after U02a merge. These dirty-source
  checks qualify an unpublished local source checkpoint for the normal clean
  packager. Build/package and eight owning Chromium cases remain UNRUN at
  checkpoint creation; this is not Task completion or shipping. Browser
  receipts and final exact-source packaging will be retained separately.
- Initial checkpoint `f910d374` fresh normal build/package and all eight
  Chromium cases PASS in 40.5 s. Screenshot review then found the title/New/
  Import row shrinking to content width through inherited grid alignment.
  A real geometry regression against that freshly built checkpoint FAILS at
  the owning assertion: heading 250.11 CSS px versus list 422.10 CSS px
  (`heading-red-f910d374.log`). The page-owned header now declares one
  stretching column; title and action rows must match the card-list width.
  Preserve the initial eight-case PASS and this additional negative, then
  rebuild and rerun the full eight-case selection before shipping.

Follow the documented clean-source packaging sequence if needed: all checks
available on dirty source must pass first; only then an unpublished local
source checkpoint can satisfy the official packager. Browser UNRUN/FAIL is
not completion or authorization to ship. Retain original negative receipts,
repair and rerun affected checks against a fresh bundle, and finish with one
atomic unpublished Task commit before the authorized PR handoff. Final bundle
revision must match final source commit; final receipts can remain ignored
and in the PR body to avoid an evidence-only amendment cycle.

## Documentation impact

Documentation impact: required. Routes `/platform/input`,
`/hosts/creator-interactions`, `/hosts/creator-web` describe current Project
navigation and actions. Historical three-column K2a evidence is marked as
superseded, not erased or relabeled as current passing verification.

## Version Management

Version impact: none. This implements an approved Creator presentation and
navigation change using existing capabilities. It does not allocate a Product
Build, change a public Contract or publish an immutable release snapshot.

Pitfall disposition: existing tests express the product/navigation boundary.
The stash conflict was the expected overlap of two independently approved
focus-order changes; no new process or invariant pitfall is introduced.
