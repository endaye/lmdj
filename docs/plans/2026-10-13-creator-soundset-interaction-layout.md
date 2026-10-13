# Creator Sound Sets interaction layout — #2112 U09

## Premise refresh and scope

Task and freshly fetched main base:
`fe6f30bbf3897d3b09e25e4e85f4b1b22df7db23`. Live #2112 and the open PR
inventory were read before editing. #2117 owns physical rail labels/order;
U01 owns shared controls, U03 owns overview panels, and U04 owns Project cards.
None delivers the Sound Sets touch layout. Work is isolated on
`feat/creator-soundset-interaction-layout` with no upstream tracking.

Already delivered: `SoundSetSurface` has Browse/Details/Target/Review,
list/inspect/audition/stop/preview/install handlers, a destination independent
of the playing Bank, global Keep/Replace, revision-bound mapping, request
locks, install receipts, offline/refusal UI, and Browse focus/scroll return.
The reducer and existing three native browser journeys establish their owning
boundaries; do not recreate them or reinterpret this Task as new capability.

Still outstanding: Figma layout hierarchy, compact real catalog cards,
Details demo/Stop row plus two columns of 16 slots, Target card/actions,
Review mapping/policy/confirmation hierarchy, and owning geometry/hit checks.
Figma file `GPFarNiZNsjLQzfG9kR8DO`: `405:1501`, `405:1729`, `405:1980`,
`406:1875`. `figma-design-to-code` was read before all context calls; each
returned high-fidelity context and a screenshot. Touch nodes respectively
`405:1692`, `405:1920`, `405:2171`, `406:2066`. Shared rail/Pad SVGs are outside
this touch-only Task; the owned touch panels have no static image assets.

Approved differences from the mockups:

- Keep/Replace remains one policy for all collisions. The single B03 example
  does not authorize mixed per-slot policy (D0 decision).
- Audition has only its real Host result and failure. No persistent playing
  state is available; Stop remains idempotent and no UI timer invents truth.
- SoundSetSummary has no per-entry cache flag. Keep the real global offline
  cache message; do not mark an online row ON DEVICE from the mockup.
- Show actual names, slot occupancy and licence/attribution. Preserve
  publisher/version/download facts in native expandable details; never copy
  the sample Studio drums, 16 sounds or CC0 text into product state.
- Empty slots remain noninteractive and never imply clearing target Pads.

## Integration and review refresh

Fresh main `50ecc7107a3347878e1d5aa7f72b031d7d58eb98` contains the delivered
U02a rail order (`45c8f479`) and U04 Project list (`50ecc710`). The Sound Sets
layout remains outstanding. Preserve both navigation moves: Project owns its
Sound Sets entry, Browse owns Back to Project, and the shared navigation only
contains Sample/Slice. No controller or Truth operation changes.

Before integration, all nine owned paths were saved as a binary patch, two
untracked-file copies and per-file hashes under ignored
`build/verification/u09/integration-50ecc`; stash
`25cc0e6a9bfe7e4e0d83d733ad618fae9d747e2c` is retained. Only the expected App
navigation-array conflict required resolution; other owned sections merged.

Read-only review found two defects to repair within the nine declared paths:
visible short action/policy labels must occur in their accessible names while
retaining unique Set identity and global policy meaning; the new Back journey
must call the existing real `project.inspect` helper before and after return.
The former cached `window.__lastProjectTruth` comparison can remain equal even
if a mutation occurs without another projection read, so it does not prove
unchanged Truth. Preserve all existing journey legs and operation counters.

## Declared files

1. `apps/creator-web/src/components/soundset_surface.tsx`
2. `apps/creator-web/src/components/soundset_surface.css` (new page CSS)
3. `apps/creator-web/src/app.tsx` (Sound Sets Back entry/callback only)
4. `apps/creator-web/test/soundset_surface.test.tsx`
5. `apps/creator-web/test/workspace_shell.test.tsx` (Sound Sets return only)
6. `tests/platform/web/creator/creator_web_soundset.spec.mjs`
7. `apps/docs-site/docs/hosts/creator-interactions.mdx` (Sound Sets only)
8. `apps/docs-site/docs/hosts/creator-web.mdx` (Sound Sets only)
9. This plan.

State/reducer, public types, Core, `styles.css`, U04's Project entry and other
worktrees are outside scope. Root controls shared Portal section ownership;
Root granted their edit window after U03 froze its sections. Only
`creator-interactions` §7.1 and `creator-web` Sound Set 分步安装 change; overview,
System and historical paragraphs remain outside this Task. No heavy build,
browser or Portal run, checkpoint or shipping in source preparation.

## Design and implementation

Use existing tokens and native semantic buttons. Header shows SOUND SETS /
CATALOG in Browse, real selected name and sound count/target metadata in later
steps. Four tabs keep their current guards and focus behavior.

Browse shows real cards and an Inspect action per Set; Refresh Catalog and
Back to Project form the bottom action row. Details puts demo and Stop first,
then a column-first 1–8 / 9–16 sound list, then Choose install target. Keep
real names and audio details available, long labels wrapping without clipping.
Target uses its existing independent BankSelector, then primary Preview.
Review retains all 16 read-only MPC-ordered statuses, native globally scoped
radio choices with clear all-collisions labels, primary Install before
Refresh mapping, and the actual committed receipt. Error/empty/loading/refusal
states and licence attribution remain reachable on every relevant step.

## Verification and acceptance

- RED then GREEN for hierarchy/semantic differences in the existing component
  suite. Run complete `soundset_surface.test.tsx` and `soundset_state.test.ts`;
  add explicit global-policy, no invented cache/playing facts and reachable
  empty/full 16-slot details assertions where current tests do not cover them.
- Run mounted App's full Sound Sets/Slice entry-and-return case from
  `workspace_shell.test.tsx`, then TypeScript. State tests execute unchanged.
- Preserve all three complete `creator_web_soundset.spec.mjs` journeys:
  real fetch/list/inspect/preview/audition/stop/keep/replace/offline-install;
  same-origin Catalog forwarding; colour default/override/reinstall/reopen/
  restore. Retain every far-side Host receipt, Truth, asset-retention and
  attribution assertion. Extend four-step geometry to inspect actual two
  columns, full slot/button hit reachability, end-of-list CTA, real scaled hit
  rectangles, no horizontal or nested vertical scrolling and focus return.
  Retain the existing navigation `offsetHeight >= 44` design-coordinate gate;
  record actual `getBoundingClientRect` dimensions plus centre/edge hit tests
  at all three viewports. These are U09 layout and no-regression checks. They
  do not establish a 44 CSS px minimum after scaling; that separate compliance
  assertion belongs to U01's final shared-control spec and remains UNRUN here.
  Append the real Browse-footer return to Project with no new open/install
  request and unchanged read-back Truth.
- Full normal build/package and whole Portal check wait for Root's resource
  admission. Complete keyboard/geometry screenshots compare the owned touch
  panels; unrelated rail/overview differences remain separately owned.
- Check whitespace and the ownership scope suite before a local checkpoint.
  Normal packaging requires clean source; use Root's approved clean-source
  checkpoint process, retaining all negatives and one atomic unpublished Task
  commit until owning browser and documentation checks pass. Final package
  must identify the exact source head. Never turn an UNRUN lane into PASS.

## Documentation impact

Documentation impact: required. `/hosts/creator-interactions` and
`/hosts/creator-web` update Sound Sets layout and real data limits. Existing
policy, outcome ownership and recovery descriptions remain authoritative.

## Version Management

Version impact: none. Presentation uses existing Host capabilities without
changing API, protocol, persisted state or allocating a Product Build or
component identity. No release or deployment is initiated.

## Receipts

Source preparation only; receipts are under ignored `build/verification/u09`.

- RED: the three new hierarchy/policy tests failed on the original source
  (`component-red.log`, 3 failed / 21 deselected).
- First GREEN attempt retained two failures: the old exact Empty text acquired
  an index prefix, and the old Target copy assertion needed the approved
  wording. The Empty label remains a separate exact text node; the updated
  copy retains destination independence (`component-green-first.log`).
- Complete SoundSetSurface and unchanged reducer suites: PASS, 32 tests.
- Mounted App Sound Sets entry and Browse-footer return: PASS, 2 selected
  tests; other workspace tests were not selected in this focused run.
- TypeScript, owning browser syntax and whitespace: PASS.
- Scope ownership suite: PASS, 77 tests (8.776 s).
- Initial source component rerun after compact Inspect Set label: PASS, 32
  tests. Those assertions did not yet cover label-in-name; the review below
  found and repaired that separate defect.
- Whole Portal, normal build/package, three complete owning browser journeys,
  actual scaled-hit compliance (U01), checkpoint and shipping: UNRUN.

Integration/review repair at base `50ecc710`:

- Three new label-in-name assertions failed on the original short-label source
  for Inspect Set, Audition demo and the policy controls (`label-in-name-red.log`).
- Accessible names now start with the exact visible short phrase and preserve
  Set identity or the full policy meaning. Component and owning browser
  locators, and the Portal demo action label, were updated together.
- Browse-footer Back now independently calls `inspectTruth(page)` before and
  after returning; open/install counters and every original journey leg remain.
  Browser execution of this strengthened assertion is still UNRUN.
- Complete component/state rerun: PASS, 32 tests (1.83 s). Mounted App entry
  and return: PASS, 2 selected tests (1.75 s); TypeScript PASS.
- Retained intermediate negatives: TypeScript caught an unchecked test array
  access; the assertion now finds the visible demo button directly. The first
  mounted invocation used repository root and could not load relative CSS;
  the final run used `apps/creator-web` as required. Neither is counted as PASS.
- Scope ownership suite: PASS, 77 tests (9.311 s); owning browser syntax and
  whitespace PASS. No heavy checks or commit were performed in this phase.

## Admitted verification sequence

Root admitted U09's exclusive heavy window after the U03 and U11 runners
terminated. Process inventory showed no other local Creator/Portal/browser
heavy runner. Run whole Portal first, then retain the already-passed dirty
source component/type/scope checks and inspect the nine-path diff/whitespace.
Create one unpublished local checkpoint solely to satisfy the normal clean
packager; it is not completion. Fresh normal build/package must record that
head, followed by all three unchanged owning browser journeys and the added
layout/Back assertions. Any failure remains in the evidence directory and is
fixed/rebuilt/reverified before the single atomic unpublished commit is final.
Push/PR only after every Task check passes; Root owns current-head review and
merge. Device acceptance, U01 actual 44 CSS px compliance and release remain
outside this Task's proof.

Pre-checkpoint receipts:

- Whole `scripts/docs-site.sh check`: PASS, 177 tests, 50 built routes and
  internal links (`portal-check.log`). Locked dependencies installed first.
- Fresh main before the checkpoint remains
  `50ecc7107a3347878e1d5aa7f72b031d7d58eb98`; U09 premises remain outstanding.
- Browser Project fixture is decoded anew from the tracked
  `tests/platform/web/deployment/creator_project_fixture.mjs` (source SHA256
  `df718fc7b0dc08b6f806767a31ee55e0628b0e03c571ad79483310276f5facd1`).
  Official bundle verification passes; decoded bytes are 767554, SHA256
  `66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`.
  Its real v5 Project `00000000-0000-4000-8000-000000000001` has revision 66,
  BPM 120, one Pattern, one Asset and 64 assigned Pads across four Banks.
  This covers the existing all-occupied Keep/Replace/offline journey; it is
  not invented evidence for partially occupied Keep behavior.
- No new process pitfall arose: the two review defects are product/test logic
  expressed directly by the owning assertions, so no ledger path is added.
- Browser/build/package are still UNRUN at this local source checkpoint.

First complete packaged verification:

- Local source checkpoint `3f71ad6c8ceff8e0982ca07738f8f6c7472a206b` was clean.
  Normal build and package PASS; manifest SHA256
  `a7fcc848cf096f55590767d51800ba9a2a40adde61569dccf145ad6311a6bad1`.
- All three complete Chromium journeys PASS (56.9 s), including real Back
  Truth readback, original fetch/receipt/offline/reopen/colour assertions and
  all new four-step geometry. Logs and original screenshots remain retained.
- Screenshot review showed Browse geometry could run while Catalog refresh
  was still busy: disabled Inspect buttons were excluded from enabled-target
  hit checks. Move the existing Inspect-enabled wait before geometry, so all
  Browse actions are measured in their ready state. No journey leg is removed.
- Save actual rendered-hit JSON to the owning output path as well as attaching
  it, and retain a screenshot at each of the three measured viewports. Inline
  text attachments alone were not retained by the line reporter's filesystem
  output. These changes strengthen the receipt, not the success threshold.
- Final amended source requires fresh normal build/package and all three
  complete browser journeys again. Final head/manifest/results are recorded
  in ignored receipts and the PR body to avoid an endless revision-only amend.
