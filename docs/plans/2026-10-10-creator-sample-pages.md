# Creator Sample contextual pages (#1918)

## Premises and integration

- Original Task base: `50d79fa894f3483d6593d50fafcfd3e1bff28ce0`.
  Refreshed integration base: `864c0f061033a7f0c3488f1908a8817516cd3b62` (2026-10-10). #1928 merged as
  `74708e6e`; its fit changes are now a delivered dependency, not part of this
  Task diff. Transplanted only the Sample Task commit onto current main.
  #1913's bottom-left Pad traversal, #1910's capture-independent monitor,
  #1915's portable loop fixture and #1914's portal corrections are retained.
  The Sample page and management placement premises below remain outstanding
  on this main revision; none of those successors implements them. Recheck
  combined rendered journeys and the exact committed-head Creator lane.
- Outstanding: SampleSurface renders its waveform, all playback/Tone/EQ
  controls and management actions consecutively. SampleControls has no page
  selection. App mounts colour controls after SampleSurface. These render
  sites are the positive controls for locating each capability and its owner.
- Outstanding: Edit only focuses `.sample-value-input`; remove this redundant
  action and keep direct waveform editing on the first page.
- Already delivered: one playable PadSurface and one physical Bank selector;
  do not introduce another Pad/Bank matrix. Keep the global top waveform and
  local waveform editor; long read-only metadata reorganisation belongs to #1920.
- Existing confirmations, preview ownership, import/capture overlays and
  history remain authoritative. Page navigation must not move them into a
  transient child or change their operation target.
- Figma Desktop Final D03 `88:1892`, touch `88:2332`, was inspected: current
  object, waveform and trim are primary. The user's contextual-page direction
  governs overflow. D4 Assign/fine-step semantics remain undecided in #1214;
  preserve existing import/replace controls without inventing Assign.
- #1913 Pad ordering and #1910 monitor output are merged dependencies;
  this Task preserves both and does not implement the remaining encoder UI.

## Task

Provide Trim, Playback, Tone / EQ and Pad pages under one persistent current-Pad
heading. Only the active controls render. Pad selection changes their target;
the selected page stays stable while switching Pads/Banks. A fresh Sample mode
entry returns to Trim. Page switches cancel previews still active at unmount
through the existing
cancellation path; completed edits keep their existing history. Existing
keyboard gestures still finish on blur before a later navigation click.

Pad management owns Add/Replace, Record Sample, Delete, Reset and colour.
The empty Trim page retains a direct Add Sample action. Capture, file
replacement, long-source trim and error/recovery UI remain owned by the
persistent SampleSurface, outside the switched page. Navigation uses visible,
keyboard-reachable buttons and one outer touch scroller, without horizontal
scrolling or clipping as a workaround.

Declared files:
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/components/sample_controls.tsx`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/sample_controls.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_capture.spec.mjs`
- `tests/platform/web/creator/creator_web_soundset.spec.mjs`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- `tests/platform/web/creator/fixtures/creator_navigation.mjs`
- `tests/platform/web/creator/fixtures/perform_helpers.mjs`
- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_takeover.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/design/2026-09-29-creator-user-workflow-guide.md`
- This plan.

## Verification

- Baseline and changed SampleControls/workspace component suites. Regressions
  cover reachable active pages, current Pad/Bank target, preview cancellation,
  reset confirmation/focus, colour placement and System/mode return.
- Real rendered packaged Sample Editor, capture and colour/history journeys:
  retain import/replace/trim/commit, refusal/cancel/recovery, Undo/Redo and
  save/reopen assertions; navigate the new pages explicitly.
- Read touch geometry at the supported desktop/narrow viewports for each page;
  the active controls must be reachable without horizontal scrolling.
- TypeScript/build, affected full Creator component suite, portal check, and
  committed-head selected batch-only evidence before merge. No new CI gate.
- Physical iPad/Safari/audio listening remain their existing manual acceptance
  obligations; automated capability boundaries do not satisfy them.

## Version Management

Version impact: none — reorganises existing Host controls without adding or
changing its public Facade/Contract capability, persisted truth or producer
identity. No Product Build, Assembly identity or release is allocated here.

## Documentation Impact

Documentation impact: required — update `/hosts/creator-web/` and the user
workflow guide to describe the four Sample pages and management locations.


## Implementation evidence

- Baseline SampleControls/workspace: 133 passed. Final targeted SampleControls,
  workspace and audio lifecycle: 159 passed. Complete Creator component suite:
  67 files / 1,143 passed before the final Reset placement/ref cleanup; targeted
  suites reran after that refinement. Reset is inside the named Pad management
  region and the original confirmation, inert background and focus assertions
  remain.
- Owned source UI at `127.0.0.1:58170` uses the verified baseline Runtime and
  manifest; it is not a packaged-head claim. Five geometry journeys passed at
  1440x900, 1280x600 and 768x600. The Sample journey visits every new page,
  checks error-to-success import and verifies reachable controls. Viewed Trim
  and Pad screenshots prompted a real correction to the wrapping navigation
  labels and selected-state contrast; final geometry rerun passed.
- Source-UI Sample browser group: nine passed / one capability-project skip.
  Its retained assertions include replace cancellation, imported-artifact
  identity, preview/cancel/commit, refusal and injected failure, reprepare,
  persisted reopen, mode changes and Undo/Redo preserving recorded rhythm.
- The first source capture run preserved seven passes / one skip / one failure:
  after closing capture, the test still looked for the Trim waveform while on
  Pad. Add the explicit Trim navigation without dropping audio, quota, PCM
  length or saved-revision assertions. The full capture group then passed
  eight tests / one permission-project skip; the failed trace is retained.
- Component-only pointer cancellation uses a second input before the first
  pointer releases; it does not claim physical multi-touch/Safari acceptance.
- React review: persistent overlay/operation owners stay in SampleSurface;
  only the active parameter group mounts; controls are keyed to the selected
  slot so an old gesture cannot leak into another Pad. Colour mutation and
  error ownership remain in App. No new data-fetching or provider path.
- Full packaged committed-head Creator lane and independent current-head
  review remain required before merge. Physical acceptance stays pending in
  its existing issues. No qualifying new process pitfall: regressions express
  the product invariants, and existing acceptance-journey guidance applies.

## Integrated-base verification follow-up

The first packaged batch on `90653d60` exposed missing page navigation in
cross-mode lifecycle and metronome/Perform witness setup. Chromium recorded
53 passes, three failures, one skip and two interrupted journeys before the
remaining run was deliberately stopped for repair; this is failed evidence,
not a passing batch. Its log and traces are retained under
`/tmp/lmdj-ui-goal-20261009/1918-first-batch-evidence/` and `1918-batch.log`.

The follow-up adds explicit Playback, Pad and Tone / EQ navigation in those
journeys and the two-tab takeover write, preserving their original audio,
Project revision, saved artifact, replay and recovery assertions. No timeout,
assertion or journey leg is weakened. Fresh full-lane evidence is required
on the corrected, integrated-base commit before merge.

Integrated-base preflight after that correction: 159 targeted component tests,
TypeScript/Vite build, 77 path-ownership tests and the complete portal check
(50 routes/internal links) pass. All 24 cross-page lifecycle, metronome,
Perform and two-tab takeover browser journeys pass (3.7 minutes). This browser
preflight uses the current source UI with the earlier verified Runtime; it
repairs the observed navigation regressions but does not claim to validate the
newly merged monitor Runtime. The fresh packaged batch covers that integration.
