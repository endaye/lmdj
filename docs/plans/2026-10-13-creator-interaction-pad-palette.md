# Creator Interaction UI Pad colours and labels — U02b

## Premises and ownership

Related issue: #2112. Root owns this eight-file Task in
`lmdj-goal-pad-palette`, branch `feat/creator-interaction-pad-palette`, from
main `73fc1c7bf0cd2f0a7f52cef481d0746ff032dd22`, safely integrated from the
initial `cf7707d32dd5ad7711db633c452b60ff71d39057` base. Main already contains
the approved five-colour decision, but its five `data-pad-colour` definitions
still contain the old hex values. The change remains outstanding. Category,
override/default resolution, history and persistence are already implemented;
do not reimplement them or rewrite Project Truth.

The owner explicitly approved DRUMS #F2B584, BASS #DDF478, MELODIC #B6A0EC,
VOCAL #95D4DF and TEXTURE #E5ADC4, keeping indices 0–4 unchanged. Figma
Sample Pad `403:784` was read with full design context and screenshot.
U01's author released the shared palette section after PR #2132. The S6
owner explicitly released display-only PadSurface, its actual component tests
and adjacent Pad styling from frozen candidate 005e339d, confirming these
paths have no S6 delta. Root only changes visible category/identity/dot styling;
all input, capture, capacity and event handlers, accessible names, key mapping,
MPC addresses and MIDI identity stay unchanged. Sample Pad-page grouping is a
separate U05 Task. S6's original full Creator process remains untouched, and all
new heavy verification waits for its owner to release the shared window.

## Declared files

- `apps/creator-web/src/styles.css` (five colours and Pad text/dot styling only)
- `apps/creator-web/src/components/pad_surface.tsx` (visible category readout only)
- `apps/creator-web/test/pad_colour.test.tsx`
- `apps/creator-web/src/state/pad_colour.ts` (palette authority comment only)
- `tests/platform/web/creator/creator_web_soundset.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx` (Pad colour paragraph only)
- `apps/docs-site/docs/hosts/creator-interactions.mdx` (Pad colour note only)
- `docs/plans/2026-10-13-creator-interaction-pad-palette.md`

## Implementation and verification

Retain the Core effective colour index, override/category fallback, neutral
state, white selection outline and lime dot. BASS now equals the global lime,
so selection must continue to use the white outline and explicit dot.
Assigned Pads show their actual category label, even when their display colour
is overridden to another category's palette index. Unknown-category assignments
retain Assigned; Loading/Processing/Failed/Capturing/Empty keep priority. Use
the existing circular selection marker at Figma's 5-unit size, address 11/15
and key/category 9/13 typography, radius 6 and 8-unit text inset. Compact labels
may wrap within the Pad, retaining every status word.

One shared CSS definition continues to feed the Pad, Sequence overview,
Sequence touch grid and colour picker.

Extend the existing colour journey with absolute approved RGB expectations.
Comparing consumers only to one another could let all of them display the old
palette; the independent oracle is the owner's five approved RGB values.
Check actual rendered name/note colours, all five picker text colours and selected
fill, and the Pad's effective colour while retaining its selected treatment.
Exercise all five indices through the existing UI, then restore the current
override before continuing the original journey. Keep every original leg:

1. Old unclassified bundle → neutral, with an actual Sequence note.
2. Install BASS category → default index 1; Undo/Redo restores complete fields.
3. User override → index 2; preserved category, one history operation.
4. Re-install Replace → new Asset, same override; Undo/Redo restores identities.
5. Reload → identical saved Truth, override 2, reset session history.
6. Restore default → index 1; Undo/Redo retains both exact states.

Use the verified pre-fix packaged U01 artifact (normally built at 8f5e4366,
palette source identical to this Task's base, including the current Sound Set
navigation needed by the original journey) to demonstrate the new absolute
colour assertion fails on old displayed colours. This is explicitly pre-fix
evidence, not final-candidate proof. Then normally build/package this Task's
clean checkpoint and run the entire three-case Sound Set spec, preserving its
all other install/keep/replace/licence/failure/preview/reopen journeys and all
deadlines. Record screenshots and raw outcomes separately. Full Portal,
complete `pad_colour.test.tsx` and `pad_surface_keyboard.test.tsx`, TypeScript,
browser syntax, scope ownership,
whitespace and exact declared inventory precede shipping. Browser/Portal heavy
work waits for the original S6 Creator run to release Root's serial window;
no physical acceptance inferred.

## Version Management

Version impact: none — only presentation values and documentation; no stored
index, schema, API, Contract, Product Build or manifest changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Update the displayed palette while preserving the documented effective-index,
history and retention semantics.

## Pitfall Impact

Pitfall impact: none — the colour change follows an explicit product decision.
Existing parity-oracle and complete-journey guidance applies; no new process
invariant or new required gate is introduced.

## Evidence status

The eight-file palette/category presentation source is prepared. Initial complete `pad_colour.test.tsx`: 4 PASS,
exit 0 (`/tmp/lmdj-u02b1-components.log`); `tsc --noEmit`: exit 0
(`/tmp/lmdj-u02b1-tsc.log`). Browser syntax and whitespace checks pass, and
all tracked symlinks are actual links. Independent review corrected the
neutral-state documentation to exclude unknown-category Pads with a custom
override. The new rendered proof explicitly asserts selected A04 white outline
and lime dot on Sample before navigating to Sequence; it does not rely solely
on a conditional selected branch on Sequence. Independent eight-file source
review found no actionable defect, but noted that the BASS screenshot cannot
establish long-caption geometry. The existing full install journey now also
selects the real installed Foundry MELODIC Pad B09 at 768×600 and checks each
rendered text line against the Pad, address and selected dot, saves geometry
and a screenshot, and verifies the entire Truth is unchanged. Transient long
statuses still need actual visual readback in the final integrated journeys;
no synthetic runtime status is asserted. This browser extension remains UNRUN.
The category assertion failed
against the old Assigned caption (12 PASS / 1 FAIL); after the display-only
change, both complete `pad_colour.test.tsx` and `pad_surface_keyboard.test.tsx`
pass, 13/13, and full TypeScript exits 0. Raw receipts:
`/tmp/lmdj-u02b-category-red.log`, `/tmp/lmdj-u02b-category-green.log`, and
`/tmp/lmdj-u02b-category-tsc.log`. These do not establish rendered geometry.
The final eight-file staged inventory passes all 77 change-scope checks
(`/tmp/lmdj-u02b-final-scope.log`, exit 0) and staged whitespace validation.
Fresh remote main `692d2ac18397190f71a54ce0297e5e0a54cee5ab` adds only the
independent Facade headered gesture fix, its owning test, plan and Facade Portal
page (#2126); no palette, Pad or owning browser input changed. No unrelated
rebase is required. Whole Portal, actual
pre-fix colour proof, final normal build/package and full Sound Set browser
remain UNRUN. No release, deployment or worktree cleanup is included.

The Task safely absorbed U01 main `73fc1c7bf0cd2f0a7f52cef481d0746ff032dd22`
with its shared sizing/fit changes before final verification. Original six-file
bytes/patch remain in `/tmp/lmdj-u02b-pre-main-73fc1c7/` and retained stash
`7e5fa4042229b0254fb0796ed10801241048806b`; the overlapping palette and Portal
Task hunks were preserved. Final source and browser evidence must describe
this integrated candidate. Complete hardware/control-kit journeys accompany
the Sound Set journeys because Pad text/dot geometry changed.

## First integrated browser result and bounded correction

The clean checkpoint `0de1831e674dd833dc658a833c4673dc6c31d0bf` passed
the full Portal check (179 tests / 50 routes), normal build and package. Its
complete original four-spec Chromium selection naturally finished on
2026-10-13 at 07:35:13 UTC: **27 PASS / 1 FAIL / 1 existing platform skip**.
All declared source, browser inputs and packaged assets remained unchanged;
the owned server and every recorded child exited. Original trace, error
snapshot, screenshots, logs and hashes remain under the ignored
`build/verification/u02b/final-original/` receipt and its retained result paths.

The failed absolute-colour assertion correctly exposed a cascade defect:
`.hardware-workspace .sample-surface button` (specificity 0,2,1) overrode
the unselected swatch's `.hardware-workspace .pad-colour-swatch` (0,2,0),
painting its text white. The two swatch rules now include their existing
`.sample-surface` ancestor, giving their palette declarations priority while
leaving all other buttons and every handler unchanged. No oracle, timeout,
worker count or journey leg changes. The new candidate must be normally
rebuilt/packaged and repeat the complete original four-spec selection; that
corrected browser proof is UNRUN at this source checkpoint. The earlier
old-artifact RED remains independent: it failed on the obsolete Sequence
colour before reaching this picker assertion.
