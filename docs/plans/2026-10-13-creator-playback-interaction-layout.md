# Creator Playback toggle layout — U05a

## Task premises and ownership

Related issue: #2112. Worktree `lmdj-goal-playback-layout`, branch
`feat/creator-playback-interaction-layout`, refreshed main/base
`1b1756b479b12d5929ad8e508cc4b711c8bb2845` (D0 responsive/palette decision merged).
The live issue and current source/tests were read before editing. U04 Project
navigation, B01 current-Pattern cancellation and U06a Grid Tools are already
delivered; this Task does not repeat them.

Before heavy verification, the seven staged files were preserved in an exact
local stash and reapplied after a fast-forward to main
`cf7707d32dd5ad7711db633c452b60ff71d39057`. Intervening #2125 Portal provenance
tooling and #2121 System work do not change Playback premises. The two Portal
paragraphs merged without conflict; all five non-Portal files retained identical
bytes, and the original eleven-case browser prefix still matches main. No
remote Source5 input was accessed. Root admitted the sole heavy window after
reviewing this complete seven-file diff; the retained stash is preservation,
not another implementation candidate.

Precommit main refresh reached `88fd161603ba7d4dec437b8505b5f848a93b9d30`;
#2130 changes only the separate audio lifecycle component test and its plan.
Playback product, consumers and owning acceptance premises are unchanged, so
no further integration is needed for this Task. On the cf7707 integration tree,
all three owning component files passed 93 tests again, TypeScript passed and
the staged ownership suite passed 77 tests, each with actual exit 0
(`/tmp/lmdj-u05a-main-{components,tsc,scope}.log`).

Figma `GPFarNiZNsjLQzfG9kR8DO`, Playback `401:4343`, touch child `401:4670`
was read with high-fidelity design context and screenshot on 2026-10-13. Its
four toggles occupy two equal columns: Loop / One Shot, then Mute / Reverse,
with an 8-unit gap and visible On/Off values. Current `sample_controls.tsx`
already implements all four modes and mutations, but its shared wrapping row
does not preserve that grouping and its text omits the values. Those two
presentation gaps remain outstanding at this base.

Root granted this seven-file source Task after the original ASSIGN coordinator
released a temporary **committed-main-only** Sample browser writer
(`msg_858bb8d276cb`). `sample_controls` and its component tests are not owned by
ASSIGN/C1. The remote Source5 packet is not an implementation input. Do not
touch ASSIGN/R1, source selection, receipts, controllers, App, Runtime/SDK,
`sample_surface`, global styles or the other agents' Portal paragraphs. Root
will return the final merged head and released browser diff to the original
owner. Root admitted heavy verification after U01 released its owned processes.

## Declared files

- `apps/creator-web/src/components/sample_controls.tsx`
- `apps/creator-web/src/components/sample_controls_layout.css` (new)
- `apps/creator-web/test/sample_controls.test.tsx`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx` (Playback paragraph only)
- `apps/docs-site/docs/hosts/creator-interactions.mdx` (4.3 Playback only)
- `docs/plans/2026-10-13-creator-playback-interaction-layout.md`

Use the existing buttons, state and callbacks. Scoped normal-flow CSS supplies
the two-column grouping; global typography, selected treatment, 32-unit faces
and actual 44 CSS px targets remain U01's shared responsibility. No invisible
overlapping hit extensions are added. Loop still changes One Shot to **Hold**;
the label must describe the real mode, even where the static Figma shows only
One Shot. Visible On/Off follows the same readback as `aria-pressed`, retaining
the existing accessible button names. Loop mode, sliders, precise input,
disabled/suspended states and all saving/preview semantics remain unchanged.
The surrounding Sample shell, Trim, Tone/EQ, Pad and Numeric visual work remain
separate U05 tasks; this does not claim the whole screen is aligned.

## Verification and acceptance

The lowest-tier new assertion catches missing or stale visible state in all
four trigger modes, plus independent Mute/Reverse states. First run that
assertion on the old product source, retain the failure, then apply the JSX/CSS.
Run the complete `sample_controls.test.tsx`, `sample_numeric_editor.test.tsx`
and `value_slider.test.tsx`, followed by TypeScript checking. Baseline complete
Sample controls: 28 PASS, exit 0 (`/tmp/lmdj-u05a-baseline.log`).

The browser addition checks the actual two-row rectangles and reading order at
1440×900, 1024×768 and 768×600, with no horizontal overflow or mutual overlap.
Native focus/Tab and Enter/Space must reach the four controls in that order;
each mutation must settle to the actual saved playback and displayed state.
Persist screenshot and geometry JSON through `testInfo.outputPath`, as well
as attachments. Actual scaled target sizes are recorded, not inferred from
CSS declarations; any U01 size dependency stays explicit.

Before shipping, run the whole Portal check, declared-file/whitespace checks
and the 77-case scope suite for the new CSS/plan. After a clean source
checkpoint, normally build/package this worktree with pinned tools. Run both
complete original browser specs with no filters, changed deadlines or removed
legs: `creator_web_sample_editor.spec.mjs` and
`creator_web_sample_numeric_editor.spec.mjs`. Preserve every original case:

| Existing journey | Required far-side evidence retained |
| --- | --- |
| Facade v1-to-v2 | Import/long trim, defaults, zoom, modes/voices, save, replacement cancel/confirm, bad file, conflict, multi-Pad, publication failure, Resume/Retry Prepare, report, reload and real grips. |
| Source quota | Plus-one-frame clamp and admitted exact selection. |
| WebKit boundary | Existing explicit capability/privacy boundary; its Chromium skip remains platform-scoped. |
| Diverged bundle | Open local recovery without reload, preserved local Truth. |
| Cross-mode history | Sound identity, cancelled edits, Undo/Redo and persisted reopen. |
| Playback parity | Commit, cancel/preview clear, range/revision refusal, failed mutation, reverse/loop/ping-pong and exact saved playback after reopen. |
| Tone parity | Attack/Release/Tone/EQ changes, pointer/keyboard/Escape cancellation, invalid Q/conflict, failure and exact reopened parameters. |
| Pattern history | Changed inventory anchor keeps the Project open. |
| Inactive Delete | Actual deletion after reopen while audio is inactive. |
| Recorded-rhythm Delete | Undo/Redo, reassignment and reopened rhythm/Pad identity. |
| Encoders | One merged save, cancellation on old targets and restored monitor volume. |
| Numeric (separate spec) | Real preview acknowledgment, pause without save, invalid draft clears preview, exact one Apply/history entry, Cancel/Escape, native Undo/Redo, reopened Truth/playback/history and no extra Pad trigger. |

Source verification: the four new readback cases failed against old JSX
(28 PASS / 4 FAIL, exit 1, `/tmp/lmdj-u05a-red.log`), then the complete Sample
controls file passed 32 cases. The three complete component files pass 93
cases. TypeScript initially rejected a Playwright-only `exact` option in the
Testing Library assertion, then exposed a possibly undefined split result;
both failed logs are retained (`/tmp/lmdj-u05a-tsc{,-final}.log`). The assertion
now uses Testing Library's exact string-name semantics and a definite string
slice; `tsc --noEmit` passes (`/tmp/lmdj-u05a-tsc-fixed.log`). Product callbacks
were untouched. Browser syntax, whitespace and tracked symlink checks pass.
After the sole added `writeFile` import, the entire original Sample browser
file is a byte-identical prefix: all 11 cases, legs and budgets remain.
The staged new-file ownership suite also passed all 77 cases, exit 0
(`/tmp/lmdj-u05a-scope.log`).

Whole Portal passed after the main refresh: 179 tests, 50 routes and internal
links, actual exit 0 (`/tmp/lmdj-u05a-portal.log`). At the clean source checkpoint,
normal build/package and browser checks remain UNRUN; the shipping PR records
their final exact-head results and artifact receipts. Source checks do not
establish packaged-browser, device, listening or full-candidate acceptance.
The first admitted heavy window covered the normal package and both complete
browser specs. Its result is retained below, separately from final integration.

### U01 integration and retained first-run evidence

At `3ba7301b6df3d16aad78d731e9ee14b5ae854a97`, normal Creator build and package
passed. The original Sample fixture generator ran unchanged with this
worktree's built native CLI; two packs were byte-identical and bundle
verification passed. The complete Sample 14-case spec plus the original Numeric
spec passed with 14 PASS / 1 existing WebKit-only skip, exit 0, in 6.7 minutes
(`/tmp/lmdj-u05a-browser.log`). Its owned server terminated with -15 and was
confirmed absent. The original packaged distribution remains at
`build/verification/u05a/pre-u01-dist`; fixture/artifact identities, browser
receipt and all three screenshots/geometry JSON files are retained.

Those old-layout buttons measured 55.275, 46.2 and 34.65 CSS px high at
1440×900, 1024×768 and 768×600 respectively, with no mutual overlap or
horizontal overflow. The 768×600 result is explicitly **not** a 44px pass.
Main then delivered U01 as `73fc1c7bf0cd2f0a7f52cef481d0746ff032dd22`, changing
the actual shared button/font/stage inputs that Playback consumes. Root
authorized a source-only merge retaining the 3ba7301b ancestry and all original
receipts. The merge keeps U01's shared rules and Portal text alongside this
Task's independent two-column CSS and Playback paragraphs; no shared source
rule or handler is rewritten.

The existing three new viewport cases now also require each real target to be
at least 44 CSS px in both dimensions and hit its own button at all four edge
midpoints and centre. The old 768×600 measurement would fail that requirement.
All original eleven Sample cases, budgets and the new keyboard/save legs stay
intact. The final integrated candidate still needs a fresh normal build/package
and the same complete 15-case browser invocation. These checks are **UNRUN**
until the original S6 run releases its heavy window and Root admits this run;
the first-run evidence cannot clear the changed shared-input acceptance debt.
The integrated source passes all 93 owning component tests, TypeScript and
77 staged scope tests, each with actual exit 0
(`/tmp/lmdj-u05a-u01-{components,tsc,scope}.log`). JSDOM reports stylesheet
parsing warnings; these component results establish state/interaction
semantics, not rendered CSS acceptance. Browser syntax, full original Sample
prefix and whitespace checks pass. Integrated Portal/build/package/browser
checks remain UNRUN while S6 owns the heavy window.

## Version Management

Version impact: none — presentation only; no manifest, API, Contract, Product
Build or persisted Project representation changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Only describe the Playback grouping and true toggle readbacks; other shared
sections are frozen under their respective owners.

## Pitfall Impact

Pitfall impact: none — reason: This presentation defect is derivable from the
component and covered by its owning assertions. Existing journey, fixed-head,
symlink/upstream and separate browser-output precautions are retained.
