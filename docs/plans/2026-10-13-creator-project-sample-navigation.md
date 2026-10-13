# K2a: Project and Sample direction navigation

Date: 2026-10-13
Status: Source preparation; verification, commit and shipping are pending a
Root-owned execution window.
Owner: Codex task `/root/n13_current_source14_independent_review`, actual thread
`01a1301f-d080-7b01-a427-39aedff8554c`.
Branch: `feat/creator-project-sample-navigation`.
Main/worktree base: `9f44298c98b190c20443c79cd62d19045ee06e41`, refreshed from
`origin/main` before editing. This is one implementation Task and will retain
one reviewable Conventional Commit. Its local commit provides the clean source
revision required by the supported packager; browser verification and shipping
remain pending until the complete owning journeys pass.

## Premise refresh

Read the live [#1822](https://github.com/endaye/lmdj/issues/1822) body and both
comments, the followup plan's K2 section, decision log and the
[approved navigation decision](../prd/decisions/2026-10-11-creator-navigation-and-live-mute-tails.md).
The open question and its historical SHIFT proposals do not override the
later approved navigation contract.

| Premise at the refreshed base | Disposition and positive source evidence |
| --- | --- |
| Project arrows select adjacent items / three-column rows, with OPEN alone opening | Outstanding. `ProjectSurface` already owns one selection used by cards and ENC1; `App` supplies direction bindings only for Sequence. The actual hardware `.local-projects` grid is still one column. |
| Sample arrows select the shared current Pad and navigate the four existing subpages | Outstanding. `stepSequencePad` already owns silent A01–D16 selection and boundary/bank rules; `SampleSurface` owns its existing page state and page buttons. Neither is bound to Sample's rail directions. |
| Current Pad, Undo/Redo, precise-input cancellation, spatial keyboard and modifier guard | Already delivered; reuse them. #2001 merged as `a5bc444be23edf4d4d14378e3ff60c3c8bf037fc`, #2090 as `5ba70fa2bbe108c9d5fe42da9045a985c4847c2c`, #2058 as `b503688d637789569ea985a4af79cc1454a5facc`, #2082 as `ea15c7b4408de446af9f2cd443bee0a371687349`. Current owning handlers and mounted App tests retain these behaviors. |
| Perform directions / FILTER consumer and the complete K2 / #1822 goal | Outside K2a; still owed to their existing workstream. #2006 (`46045119801d9f03707aaa6f8ed50fbd651e8e95`) approved the mapping; its documentation did not implement the remaining consumers. |

The finite live successor searches for `1822` and `K2` returned complete
results. Their relevant merge scopes and the exact-base owning handlers were
read. Presence would be a Project/Sample `padStep`/`directionStep` binding in
the mounted `App`, connected to their existing state owners; the sole current
binding is Sequence. An empty keyword search was not used as absence proof.

## Task and declared files

Reuse Project's existing selection for left/right ±1 and up/down one row of
three. Render the same hardware list as three columns. At its boundaries
selection stops; a shorter final row uses the existing selection clamp.
Only OPEN opens the selected Project.

Reuse Sequence's current-Pad selection for Sample up/down, including boundary,
bank and visible-row behavior. Reuse Sample's existing page selection for
left/right Trim → Playback → Tone / EQ → Pad, stopping at either end. Both
page buttons and rail directions cancel unsubmitted encoder and precise-input
previews before changing the editing page; an already sent update retains its
existing result owner. Navigation never triggers or writes Project Truth.

SHIFT+left/right retains Undo/Redo. SHIFT+up/down is unassigned for these newly
wired pages. Keep ENC4, existing fine adjustment, Sequence/Perform consumers,
MIDI, Ctrl/Cmd Pad guard, and focused text/encoder keyboard behavior. Do not
introduce a global Arrow key listener.

Declared files:

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/project_surface.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs` (existing history lamps through SHIFT)
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs` (existing reopened-history assertion through SHIFT)
- `apps/docs-site/docs/platform/input.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/plans/2026-10-09-creator-desktop-final-followup.md` (append-only K2a record)
- `docs/plans/2026-10-13-creator-project-sample-navigation.md`

## Verification

The lowest owning checks are the complete `workspace_shell.test.tsx` (real
mounted App with manufactured Session storage), `hardware_console.test.tsx`,
`input_controller.test.ts` and `sample_numeric_editor.test.tsx`, plus complete
Creator TypeScript. New regression assertions cover every Project ±1/row
transition and explicit OPEN, Sample silent selection across Bank and end
boundaries, each existing page and touch/rail agreement, preview cancellation
beyond 400 ms, precise-input retirement including late acknowledgement, and
SHIFT/text keyboard preservation. Existing tests and budgets are retained.

```bash
npm test --prefix apps/creator-web -- --run test/workspace_shell.test.tsx test/hardware_console.test.tsx test/input_controller.test.ts test/sample_numeric_editor.test.tsx
(cd apps/creator-web && npm exec -- tsc --noEmit)
scripts/docs-site.sh check
```

The actual three-column fixed 368 px touch workspace needs a far-side browser
geometry check; jsdom cannot establish painted layout. Extend the existing
hardware-layout journey without dropping its geometry, font, scaling, hit
target or recovery legs. A scheduled packaged run of the complete owning
`creator_web_hardware_layout.spec.mjs` must verify three visible columns,
row movement, explicit OPEN, scaled hit targets and no touch-panel horizontal
overflow at the existing supported viewports. Keep the original budgets and
the stable Creator packaging/test entry point; no blanket full-CI or strict
update gate is added. Before shipping a new plan, run the existing ownership
suite `python3 tests/build/ci_change_scope_test.py` at the declared staged or
committed source boundary.

The two existing Sample-editor and Sequence-grid browser journeys also retain
every original leg; their history lamp/disabled assertions must enter the real
SHIFT layer now that ordinary directions own the unshifted buttons. Run those
complete owning specs in the same scheduled packaged verification, not a
shortened history prefix.

The supported [Creator workflow](../../apps/creator-web/README.md) packages only
clean source. Root approved the following order for this Task; execution still
waits for its assigned host window:

1. Run the complete four owning Vitest files, full Creator TypeScript, whole
   Portal check, ownership suite and whitespace checks on this declared source.
2. After those checks pass, stage only these 13 paths, inspect the staged scope
   and whitespace, and rerun the ownership suite after staging (the current
   suite has 77 tests). Create this Task's single local Conventional Commit on
   its legal branch and inspect its committed paths and final worktree status.
   The Task and browser checks are still pending; do not push or create a PR.
3. From that clean local Task head, use the normal Creator build/package and
   verified distribution server to run all three complete declared browser
   specs with their original workers, budgets and acceptance legs. Bind the
   actual source revision, build inputs, packaged asset bytes and run results.
4. Ship only after every declared check passes. If a browser check exposes a
   source defect, preserve its negative evidence, fix it in this own unpublished
   branch, rerun the affected checks and fresh build, and retain one atomic Task
   commit before current-head review and shipping.

This order allocates no Product Build and requires no S0/S1 Product-allocation
exception. It does not bypass the clean-source packager or turn the three
owning browser specs into a complete Creator proof. No execution, staging or
commit is authorized before Root grants the window.

All product/component/type/Portal/browser commands are UNRUN in this Source
preparation phase. Root owns the shared execution queue. Static diff inspection
does not establish runtime or layout PASS, physical controls, hearing, a
complete candidate, version settlement, release or deployment.

## Version Management

Version impact: compatible Creator Host MINOR debt, to join the existing
followup V1 settlement. The current Host identity is read from its manifest;
this Task adds approved UI navigation and changes no cross-language Contract,
Project storage, Core/Provider identity, Product Assembly or schema. No active
version manifest, Build/Channel or tag is allocated here. V1 must derive its
target identity from the actual integrated baseline; this plan guesses none.
No migration is required. Shipping this implementation does not authorize a
release, publication, deployment, Channel promotion or foreign cleanup.

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/input/ /hosts/creator-interactions/
Reason: the current pages say Project and Sample ordinary directions are
unwired. Update their actual source facts, the three-column list and remaining
Perform debt in this Task; preserve historical evidence and current
Ctrl/Cmd/spatial keyboard/numeric-editing facts. No architecture boundary or
diagram changes are needed.

## Pitfall Impact

Pitfall impact: none. These are product behaviors covered by owning
regressions. Apply the existing stale-premise, synthetic-focus and acceptance
journey procedures; do not add a new generic gate or pitfall entry.
