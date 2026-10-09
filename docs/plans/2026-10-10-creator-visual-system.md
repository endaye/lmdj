# Creator Graphite visual system (#1924)

## Premises

Main/worktree base: `ec15f9adf3ca7c3fd09c06d61b53e0bcdf189fe6`.
Live #1924 remains open. #1917–#1920/#1922/#1923 are delivered; #1921
PR #1946 and local #1925 remain integration prerequisites before final proof.
Do not duplicate their navigation, preview or status changes. Other-owner
#1936 remains open at b07e178dfd1c73c654697317aae71cd0f31ade42; this Task
changes no encoder mapping, controller or DSP operation.

Fresh Figma Desktop Final read: D01 88:1569, D02 88:706, D03 88:1892,
D04 88:2389; high-fidelity D02 touch 88:1512 because whole D02 was sparse.
Rendered D01/D03/D04 and D02 touch confirm compact 36 visible / 44 hit actions,
12px Space Grotesk Medium action text, Mono identity/data, 14px headings,
18px key values, 16px panel padding and 8px groups. Existing 2026-10-04
Sequence decision explicitly retains Mono and 44px/8px controls there;
retain that documented exception. Its EDIT/SETUP layout remains authoritative.

At this base, styles.css still has navy generic controls/card/input rules;
Project actions are 32px/10px and Pad colour restore is 28px/9px, while other
controls are 40/44px. Only IBM Plex Mono is bundled. EncoderIcon has an
absolute radial indicator and outer position ticks; existing relative input
logic needs no change. These are outstanding presentation issues, not missing
runtime capabilities. Reuse the existing token and component system.

## Task and declared files

One Task: shared Graphite controls and font roles, compact visual/hit geometry,
and neutral relative encoder presentation. Content-rich Project cards, Pad
matrix, time/note grids, faders, trim grips and plotting handles retain their
specific geometry. No functionality is removed to fit the fixed panel.

- apps/creator-web/src/styles.css
- apps/creator-web/src/components/hardware_icons.tsx
- apps/creator-web/package.json
- apps/creator-web/package-lock.json
- tests/platform/web/creator/creator_web_hardware_layout.spec.mjs
- tests/platform/web/creator/creator_web_touch_fit.spec.mjs (asynchronous recovery layout measurement)
- apps/docs-site/docs/hosts/creator-web.mdx
- this plan

Refine the declared file list before commit; do not add a new asset/persistence
contract or change Product Assembly for a decorative change.

## Verification

Use actual rendered bounds and native input: compare four pages to D01–D04,
verify loaded font faces, compact visible/hit sizes and nonoverlapping targets
at 1440x900, 1280x600 and 768x600. Cover disabled/focused controls, long labels,
empty/content pages and no horizontal overflow. Preserve full existing
Hardware/Sample/Sequence/Perform journeys and readonly top screen. Real iPad
hit ergonomics and physical audio remain explicitly unverified in #248 and
existing acceptance issues. Run component tests appropriate to modified
controls, TypeScript/Vite, portal, staged ownership and committed-head Creator
batch proof; independent current-head review is required before merge.

## Version Management

Version impact: none — Host presentation and bundled font; no Core/Contract,
Project schema, Product Build or Assembly identity change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Document font roles, compact hit geometry and Sequence exceptions accurately.

## Pitfall Impact

Pitfall impact: none anticipated. Scaled design pixels are not physical/CSS
pixel acceptance, and real geometry/loaded-font evidence must establish fit.

## Initial implementation and verification

Space Grotesk Medium 5.3.0 is bundled through the existing data-font CSS path;
Mono remains on identities/data and all Sequence controls. Compact actions use
transparent 4px block borders with padding-box painting, placing the 36px face
inside their 44px normal-flow hit box. Content-rich controls are explicit
exceptions. Common neutral fills now use Graphite tokens. Existing inline,
CSP-safe EncoderIcon is retained as required by the product asset boundary,
with obsolete absolute pointers/ticks removed as explicitly required by #1924;
no new image role or fourth-encoder Volume claim is introduced.

Initial font/three-viewport geometry native checks passed (2 tests), hardware
components passed 13 tests, and TypeScript/Vite passed. Full source Hardware,
Perform, Sample, Sequence and touch-fit run: 43 passed, one platform skip,
one late-layout measurement failure. This is not a complete pass.

The failure was reduced: a default-sounds failure inserted Retry after scrolling
but before reading the last-row bounds. Diagnostic recorded touch scrollHeight
368 -> 407, scrollTop 0 and unchanged 13-unit grid rows. Isolated source case
failed 1/3 runs; the old-style control passed 3/3, a timing observation rather
than proof of absence. Re-scroll and read both rectangles in one browser task
under the existing expect timeout; retain all four bounds and the 1px tolerance.
Three corrected repetitions passed. A rebuilt mutation placing the last row
fixed at top -1000 failed specifically the same helper's top-bound assertion
(default 5000ms); restored source is rebuilt with a fresh mtime. This verifies
that genuinely unreachable controls remain failures. Keep all logs/traces under
`/tmp/lmdj-ui-goal-20261009/1924-fit-*`.

Manual Project/Sample/Sequence/Perform screenshots use source UI plus the
separately verified Runtime, not final packaged or physical device evidence.
Final integration with #1921/#1925 and complete proof remain outstanding.

## Integration and stage correction

The actual stage defect was reproduced at 1280x600: Perform's existing
scrollIntoView moved `#root.scrollTop` to 136, putting the console at y=-61.1
instead of 74.9 and clipping its top screen. `overflow: clip` replaces hidden
only on the fixed outer stage; touch scrolling remains auto. No content is
newly clipped: the complete transformed console already fits that stage.
The new mode-by-mode stage assertion failed on the old CSS at the original
boundary; corrected hardware/touch-fit complete files passed 14 tests.
Manual trial confirmed root.scrollTop 136 -> 0 and console y -61.1 -> 74.9.

The second 45-case source run was stopped with exit 143 after a Sample native
trim leg detached; its snapshot showed unexpected System navigation. It is
retained as failed/incomplete, not a pass. Recheck the complete journey after
stage correction and live-preview integration; do not shorten the leg.
Portal initially failed because this new worktree lacked docs dependencies;
after locked npm ci, all 50 routes/internal links passed.

Current unpublished parent is #1947 head
`f2362b57697c85de33c49fddc9144deecbe65116`, which includes actual #1946 merge
4281d5f5. Stashed only the eight declared Task files and applied them onto that
parent; retained recovery stash `0531107fd24087aac4a19d485c79589ecb5019b6`.
CSS conflicts preserve #1925's removed Stage note and compact status layout,
plus #1924's Graphite tokens and action geometry. No preview/status journey was
removed. Integrate the actual #1947 merge before publishing the final Task.


## Integrated source verification on f2362b5

After the stage correction and integration of live preview/status, complete
Hardware/Perform/Sample/Sequence/Default/System/touch-fit files passed:
46 passed, one WebKit capability skip, exit 0 (7.0 minutes). This includes the
previously detached Sample trim, persistence/reopen, Undo/Redo, recording
failure/retry/discard/owner-loss and native pointer journeys without deleting
any leg. `1924-integrated-ui.log` retains the complete run. Hardware component
suite passed 13, TypeScript/Vite passed, and portal passed 50 routes/links.

Reloaded the manual browser to remove the earlier inline trial: root inline
overflow is empty, computed overflow is clip, root scrollTop is 0 and console
y is 74.9 at 1280x600. All four actual-source screenshots were inspected under
`1924-manual-artifacts/output/playwright/*-integrated.png`; complete top screen
and one outer touch scroller remain. These are source UI/verified Runtime
checks, not final packaged or physical iPad acceptance.

#1947 is receiving a follow-up: its full old-head batch exposed a late default
failure banner displacing Perform first-screen controls. Integrate its fixed
head, which moves download recovery below the workspace, before final proof.


## Review-fix parent integration

Integrated #1947 follow-up head 96d2d7b46920c3e0dc14e9dca0940916ec530bc6
without conflicts, preserving exactly the eight declared files. Recovery stash
8fbd41506e81a3c4e1ec46236f18c1868386a28e is retained. The new parent moves
download status below the workspace and prevents obsolete preparation results
from reappearing. TypeScript/Vite passed; affected Hardware/touch-fit/Default/
System native files passed all 16 cases (1.1 minutes), including the explicit
Catalog-503 first-screen regression and actual font/control/stage geometry.
The prior 46-pass complete source journey evidence remains recorded above;
committed-input full Creator proof and independent review are still required.

The review-fix parent portal check passed all 50 routes/internal links, and
staged new-file ownership passed all 77 checks before commit.
