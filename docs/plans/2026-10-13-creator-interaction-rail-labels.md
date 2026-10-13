# Creator Interaction UI: rail labels and order (U02a)

Relates to #2112. Owner: `control_kit` agent. The root coordinator owns
integration and schedules the shared browser/build resource window.

## Premises before implementation

Task base and refreshed `origin/main`:
`9fb83ce0f70de1bc9114711bf9e854dfa6bb7081` (2026-10-13).
The worktree `lmdj-goal-ui-rail` is clean on
`feat/creator-interaction-rail-labels` with no inherited upstream.

The live umbrella, current physical-control implementation and owning tests
were inspected. #2108 (`95348414`) delivered page navigation on the existing
rail, but retained the former icon faces and SHIFT after the directions.
No current successor covers the following remaining presentation changes.

| Premise | Disposition |
| --- | --- |
| Mode and transport keys still use exported icon faces | Outstanding. `physical_controls.tsx` calls Project/Sample/Sequence/Perform/Record/Play icons. Figma `401:3670` high-fidelity context and screenshot use `PRJ`, `SMP`, `SEQ`, `PRF`, `REC`, `PLAY`. |
| SHIFT is after the direction keys | Outstanding. DOM and existing shell test put SHIFT in row 7. Figma places it in row 5, immediately after the two Bank rows and before both direction rows. Change DOM order so visual and keyboard order agree. |
| Accessible identities and actions | Already delivered. Preserve full existing labels, handlers, current/disabled state, history gating and native button activation. Compact visible text is not a replacement accessible name. |
| Logo and relative encoder assets | Existing inline assets remain unchanged in this Task; no new raw SVG or export removal. Their design comparison and any replacement are separate from text-key delivery. |
| Font/face/hit geometry | U01 owns shared Mono 9/13 and 32-unit faces. Effective 44 CSS-pixel targets under stage scaling remain a separate unresolved layout decision; U02a does not discharge it. |

## Declared implementation

- `apps/creator-web/src/components/physical_controls.tsx`: render the six
  approved text labels; move SHIFT in DOM; keep all functional props.
- `apps/creator-web/src/components/physical_controls.css`: REC rose and PLAY
  lime text on inactive faces, with active ink retained. No geometry rules.
- `apps/creator-web/test/hardware_console.test.tsx`: replace icon-face oracle
  with visible text/full accessible-name oracle, keep local Logo/encoder SVG
  checks and add actual Tab traversal with all direction controls available.
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`: first
  shell test's rail text and SHIFT/arrow row coordinates only.
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`: rail focus
  order only; move SHIFT before the available Project direction.
- `apps/docs-site/docs/hosts/creator-web.mdx`: current text keys and SHIFT
  location, preserving the earlier icon delivery as history.
- `apps/docs-site/docs/hosts/creator-interactions.mdx`: rail diagram and eight
  rows, readable transport label and real keyboard order.
- `docs/plans/2026-10-13-creator-interaction-rail-labels.md`.

No Pad classification/colour change, no new mode, no transport or history
behavior change. U02a is one part of U02, not the complete rail/Pad Task.

## Verification

Lowest-tier checks and defects caught:

- `npm test -- --run test/hardware_console.test.tsx` in `apps/creator-web`:
  text/readable-name mismatch, missing local SVGs, wrong DOM/Tab order,
  changed transport/history/encoder dispatch and disabled gating.
- `npx tsc --noEmit`: unused or incompatible component props/imports.
- Focused existing shell geometry browser test: visible rail faces, full-width
  SHIFT and physical row ordering after stage fit.
- Existing responsive keyboard journey: complete rail traversal through the
  first Pad, with disabled directions skipped and no missing far side.

The coordinator granted the exclusive U02a browser/build/portal window after
B01 completed its proof. Use the normal clean-worktree packager: first run
component/type/portal verification, create the local Conventional Commit as a
clean candidate checkpoint, freshly build/package it, then run both complete
owning browser specs and inspect the rail screenshot. Do not push if a declared
check fails. A product/test correction changes the candidate and requires a
fresh package and the affected complete browser selection again. Final remote
receipts belong in the PR; do not rewrite the verified head just to record it.

U04 changes the Project navigation label in the same accessibility array:
integration must retain `Bank D → SHIFT → Next Project — ↓ → Record →
Play/Stop → first Pad`, then execute the complete responsive journey.

## Version Management

Version impact: none. Presentation-only change; no Product Build, Module,
Host, Provider or Contract identity is allocated or changed.

Documentation impact: required — `/hosts/creator-web` and
`/hosts/creator-interactions`. U01's future common-controls section is disjoint
from these rail facts; it must preserve this Task's current rail presentation.

## Evidence

- Baseline component verification: PASS, 15 tests.
- Source/component verification: PASS, 16 tests including complete native Tab
  order and existing transport/history/encoder behavior. `npx tsc --noEmit`,
  browser-spec JavaScript syntax and `git diff --check`: PASS. An initial
  TypeScript check caught an unsupported Testing Library `exact` option in the
  new test; it was removed, then the complete selection and type check passed.
- Pre-checkpoint Portal verification: PASS, 176 tests, 52 pages, 10 diagram
  sources / 20 outputs, 50 routes and internal links. Receipt:
  `build/verification/u02a/portal.log`.
- Change-scope policy: PASS, 77 tests. Receipt:
  `build/verification/u02a/change-scope.log`.
- First clean candidate `1f85e440` built and packaged successfully. Its complete
  Chromium run retained 14 passing tests, the WebKit-only skip and one failure:
  a second transport oracle still expected the former SVG faces. The actual
  REC/PLAY text, colours and SHIFT row checks passed before that assertion.
  Correct the remaining oracle to require readable text and no transport SVG;
  retain the failed receipt and trace under `build/verification/u02a/` and
  `tests/platform/web/test-results/u02a-rail-1f85e440-chromium/`. The amended
  candidate requires another fresh build/package and both complete specs.
- At checkpoint creation browser/visual verification is still pending. The
  clean checkpoint protocol above governs subsequent build, complete browser
  checks, screenshot inspection and shipping; final receipts are recorded in
  the PR, without rewriting the candidate merely to log its own revision.
- Before checkpoint, refreshed `origin/main` to
  `2a5ec35f6bc1433539fc7064c30be756d779ae29`: D0 planning/governance and input
  documentation only; no product, owned test or rail-premise changes.

Fixture provenance: use the checked-in
`tests/platform/web/deployment/creator_project_fixture.mjs` at the Task base.
Its decoded Project bundle is 767554 bytes, SHA256
`66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`.
Keep the source and decoded hashes in
`build/verification/u02a/fixture-identity.json`; verify the actual bytes with
the normal Project bundle verifier before browser import. No external Runtime
artifact is reused for the fresh candidate build.

Pitfall review: the task follows the existing complete-journey, native-input,
isolated-output and source-receipt guidance. No new qualifying pitfall found.
