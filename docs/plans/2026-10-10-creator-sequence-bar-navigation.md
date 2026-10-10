# Creator Sequence bar navigation (#1922)

## Premises

Initial integration/worktree base:
`46df56797265942f760afb253c3e4ad2b3a13c80` (2026-10-10).
Re-read live #1922, the 2026-10-09 Sequence view/Pad decision, mounted
SequenceGrid/SequenceTouchWorkspace and existing component/browser journeys.
Baseline Sequence component suites: 83 passed across four files.

- Outstanding: the grid's full Pattern-wide editor has only native horizontal
  scrolling and ENC1 navigation. There is no visible bar selector or explicit
  previous/next bar control. The current `onScrollReady` callback already moves
  exactly one lane-derived bar per detent and clamps at both ends; preserve it.
- Outstanding: touch Previous/Next Pattern duplicate the physical direction
  keys. Replace the touch pair with a direct Pattern selector, keeping the
  approved physical mapping and its stopped/busy restrictions.
- Delivered: #1909 implements ENC1 bar scrolling and current-Pad navigation;
  #1917/#1928 fixes outer touch width; #1913 preserves MPC Pad address order.
  Do not reimplement those decisions or treat row labels as sound buttons.
- Figma Desktop Final Sequence D02 `88:706`, touch `88:1512`, was refreshed via
  metadata, high-fidelity context and screenshot. It prescribes the fixed
  368px touch region, 16px inset, 8px gaps, Graphite colours and compact controls
  with 44px touch bounds. The screenshot shows the settings view; the approved
  EDIT grid and this explicitly requested bar navigation take precedence over
  treating the pictured settings as the only Sequence workflow. Existing
  TouchSegment, ModalDialog, tokens and static hardware assets are reused.
  The approved prohibition on native dropdowns/checkboxes remains in force.
- Refreshed integration/worktree base: `08c216647138ef9e1f7824a4a2624f82eef86cce` after #1935 Perform merged
  as `2b495a137cc68c52e30b13929c8093cc92731dc0` and #1931 proof-artifact
  retention merged. Adopted their actual navigation/docs/harness changes; neither
  delivers the outstanding Sequence controls. The existing full-grid editor
  and physical mapping are still present and remain the basis of this Task.
- #1929 is a separate audible tempo-preview plan, not delivery of bar
  navigation. No BPM/audio-preview behavior belongs in this Task.

## Task and invariants

Add explicit previous/next bar and direct bar selection for 1/2/4/8 bars.
Display the actual visible range, preserve native/ENC1 navigation, and make
all bars accessible without dragging a horizontal scrollbar. Keep one bar's
editable scale and the full note geometry, including notes spanning bar edges.
The sticky Pad labels must be excluded from the overview's time viewport so a
whole-bar navigation reports the real unobscured lane range.

View changes never change Project Truth, current Pad, selection or edit mode.
Guard navigation during an active grid gesture so stored pointer geometry
cannot turn into a different edit. Preserve cross-Bank selection rules,
Undo/Redo, recording/projection locks, cancel/failure paths and persisted
reopen. No horizontal overflow is admitted on the outer touch workspace;
verify real note/control bounds, not a CSS class or clipped outer container.

Fit the default EDIT first screen without shrinking its sixteen 13px lanes:
combine the Pattern selector and EDIT/SETUP in one 44px header, then a 44px
row of previous bar / range and direct bar picker / next bar / Grid tools.
Grid tools opens the existing snap and NOTE/VEL controls in an accessible
modal, preserving all choices. Bar and Pattern pickers use touch buttons,
not native selects. Record this explicitly authorized UI-goal refinement of
the old title/toolbar presentation in the existing Sequence decision before
implementation; physical mappings and product semantics do not change.

Replace duplicate touch Pattern stepping with direct selection. Keep current
Pattern identity/count projection and physical left/right stepping, both
locked under their existing transport rules. The navigation helper and tests
must use the real replacement control without dropping any journey legs.

Proposed declared files (refine before implementation if inspection requires):
- `apps/creator-web/src/components/sequence_grid.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/touch_kit.tsx`
- `apps/creator-web/src/state/sequence_grid_model.ts` if a pure range helper is needed
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/sequence_grid.test.tsx`
- `apps/creator-web/test/sequence_grid_edit.test.tsx`
- `apps/creator-web/test/sequence_grid_model.test.ts` if the model changes
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- `tests/platform/web/creator/fixtures/creator_navigation.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/design/2026-09-29-creator-user-workflow-guide.md`
- `docs/prd/decisions/2026-10-04-sequence-hardware-ui-revision.md`
- This plan.

## Verification

- Preserve baseline component tests; add focused all-length/all-bar navigation,
  range/edge clamping, no-Truth-change and pointer-lifetime regressions.
- Native browser checks on 1/2/4/8 bars and multiple viewport sizes: buttons and
  selector reach every bar, ENC1 moves one bar and clamps, SETUP accumulates no
  hidden turns, overview follows the unobscured lane, and first/last cells and
  cross-bar note tails remain editable at the existing scale.
- Preserve the complete grid journey: create/move/resize/velocity/batch edit,
  pointercancel, Undo/Redo, authoring refusal while recording, in-place playback
  swaps and reopen with exact persisted events. Preserve current-Pad/Bank
  navigation independence and Pattern selection lock tests.
- TypeScript/build, staged path ownership and required portal check. Run the
  selected Creator batch on the clean committed head, obtain independent
  current-head review, resolve findings and perform the guarded merge.
- Physical iPad/Safari/touch and listening remain explicitly unverified under
  the existing acceptance issues; automation is not a substitute.

## Version Management

Version impact: none — local presentation/navigation over existing Host
operations; no Contract, Core behavior, persisted Project schema, Assembly or
Product Build allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Update the current control locations, bar navigation and viewport semantics,
and the user workflow guide, alongside implementation.

## Pitfall Impact

Pitfall impact: none at premise stage. Review the existing native-event and
complete-journey guidance; retain concrete failure/rebuild evidence if a new
qualifying process defect is found.

## Implementation evidence (2026-10-10)

Final precommit premise refresh: origin/main remains
`08c216647138ef9e1f7824a4a2624f82eef86cce`. #1936 is an open contextual
encoder Task with overlapping consumers, not merged delivery of this scope;
its worktree is untouched. No Core/Contract or physical mapping changes.

- Pattern title is a direct touch picker; selection, cancellation, disabled
  transport and focus return retain their contracts. Keying the grid by
  Pattern identity resets only that Pattern's view. Bank changes remain
  independent of note-selection semantics already owned by the app.
- The compact header and bar/tools row leave sixteen original 13px lanes
  visible. Grid tools retains every original snap and NOTE/VEL choice.
  Bar controls and ENC1 share unscaled layout coordinates and block while
  a note gesture is active. The native editor remains pannable; all bars
  are reachable without its horizontal scrollbar.
- Scaled DOMRect rounding initially made an aligned bar read as BAR 1–2.
  The current layout-coordinate implementation fixes that without relaxing
  the range assertion. A component regression reproduces fractional bounds.
- 200 focused component/workspace tests pass across five files, including
  all-length navigation, partial ranges, active-gesture guards, direct
  selection/cancellation, existing history/recording and current-Pad behavior.
- Source UI with the verified #1930 Runtime: all ten original Sequence
  journeys passed; eight touch-layout journeys passed. The new native bar
  journey passed (21.0s): every bar of all four lengths at 1440×900,
  1280×600 and 768×600; fixed absolute overview tick oracles; unchanged
  Truth across navigation; last-cell and cross-bar resize, Undo/Redo and
  persisted reopen. Its first run caught fractional geometry; its next
  run caught the new test's expected-array ordering (the existing canonical
  oracle sorts Pad before onset), corrected without dropping assertions.
- The independent ENC1/overview assertion was run against the actual base
  SequenceGrid: expected 3840, observed 3480, exit 1 at the intended assertion.
  Restoring the fixed bytes with a fresh mtime and a new Vitest process
  passed (exit 0). Logs: `1922-viewport-before.log` / `1922-viewport-fixed.log`.
- Native rendered preview with Catalog-backed default loading completed:
  touch client/scroll width 368/368 and client/scroll height 368/368;
  all sixteen rows fit. The browser geometry regression also preserves
  13px rows and 44px controls at three sizes. A real global error can add
  vertical content; its recovery action remains available, coordinated with
  #1925 rather than hidden to make this Task fit.
- TypeScript/Vite build passes. Portal check passes (50 routes/internal links)
  after installing this new worktree's locked dependencies; its initial
  missing-glob failure is retained, not misclassified as a document defect.
- React review: hooks are unconditional, observers/callback registration are
  cleaned up, dialog focus/inert behavior reuses ModalDialog, and view state
  never writes Project Truth. No qualifying new process pitfall was found.

Artifacts: `/tmp/lmdj-ui-goal-20261009/1922-*`; browser output slots
`1922-sequence-source-1`, `1922-touch-fit-1`, `1922-bar-navigation-1/2/3`
retain both failing and passing traces. Source checks are not the final
packaged acceptance; the committed-head Creator batch and independent
current-head review remain required before merge/issue closure.
