# Safari Capture Focus-Loss Recovery Design

**Issue:** [#625](https://github.com/endaye/lmdj/issues/625)

**Outcome:** An ordinary Sample-mode Pad Capture that loses browser focus keeps
its retained take, stop reason, trimming controls, and Commit/Discard actions
visible. Sequence armed-Pad capture continues to use the existing trim overlay
without stopping the active Sequence.

## Context

Product Build `1.0.41.0` failed the macOS Safari M7 focus-loss leg. Capture
correctly stopped and retained non-zero frames, but the app entered Sequence
`trim-overlay` even though no Sequence session existed. The resulting
`sample-overlay-host` class hid the Sample surface and the nested capture modal.

`CapturePanel` already owns the correct interruption behavior: it releases the
capture controller, retains buffered frames, enters `trimming`, and reports
`Recording stopped: the window lost focus.` The defect is the Sequence state
transition above that component, not the capture lifecycle or modal itself.

## Goals

- Keep the ordinary Sample capture modal and retained waveform visible after
  `blur` or `visibilitychange` stops an active recording.
- Keep Commit, Discard, Close, crop, and selection controls operable.
- Keep ordinary Sample capture out of Sequence semantic state when no Sequence
  session owns the capture.
- Preserve the active Sequence session, pending events, boundary switching,
  and return-to-recording behavior beneath an armed-Pad trim overlay.
- Add regression evidence at the state-machine and integrated browser levels.

## Non-goals

- Do not change capture buffering, microphone ownership, audio recovery, trim
  math, modal layout, or CSS stacking.
- Do not change Project Truth, Runtime Snapshot, public Contracts, or Provider
  behavior.
- Do not infer a Safari physical pass from automated browsers. Issue #244 still
  requires a complete rerun on the fixed deployed Product Build.
- Do not allocate a Product Build or immutable Portal snapshot in this
  functional task.

## Design

### Sequence transition invariant

`reduceSequence` will accept `trim-overlay` only while Sequence is already in
`recording` or `switch-pending` and owns a non-null session. A stopped,
recovering, or otherwise sessionless Sequence ignores the action.

The reducer is the authority for this invariant. `CapturePanel` may continue to
publish its generic phase changes, and `Workspace` may continue translating a
trimming/committing phase into a requested overlay. Central rejection prevents
this and any future caller from manufacturing a Sequence overlay without an
active Sequence owner.

No CSS exception is added. Changing the selector to reveal the modal would
mask the immediate symptom while retaining the false `trim-overlay` report and
incorrectly hiding the rest of the ordinary Sample surface.

### Ordinary Sample data flow

1. The operator starts capture from Sample mode.
2. `CapturePanel` receives non-zero frames.
3. Browser focus loss stops and releases capture, retains the buffer, and emits
   phase `trimming` with stop reason `blur` or `hidden`.
4. The requested Sequence `trim-overlay` transition is rejected because
   Sequence has no active session.
5. Sample mode remains mounted without `sample-overlay-host`; the existing
   modal renders the waveform, reason, selection controls, Commit, Discard,
   and Close.
6. Commit and Discard follow their existing paths. Audio lifecycle recovery
   remains separately available and does not destroy the retained take.

### Armed Sequence data flow

1. Capture is armed for a Pad, the operator continues into Sequence, and a
   Sequence session enters `recording` or `switch-pending`.
2. Stopping capture requests `trim-overlay`; the reducer accepts it because an
   active Sequence session owns the journey.
3. Sequence authority and exact Bar-boundary acknowledgements continue to
   update beneath the overlay.
4. Resolving capture disarms the Pad and `trim-closed` restores `recording`,
   `switch-pending`, or `stopped` from the authoritative status exactly as it
   does today.

## Error handling

The change introduces no new error category. Capture permission, device loss,
silence refusal, commit failure, and audio recovery retain their existing
messages and retry paths. The reducer fails closed by returning the unchanged
state for an ownerless overlay request.

## Verification

- Add a reducer regression proving `trim-overlay` is ignored from the initial
  stopped/sessionless state.
- Retain and run the existing reducer coverage proving active and
  switch-pending Sequence sessions survive the overlay and return correctly.
- Add an integrated ordinary Sample browser journey that records non-zero
  frames, dispatches focus loss, and proves the modal, interruption reason,
  waveform, selection controls, Commit, Discard, and Close remain visible. The
  exported report must remain Sequence `stopped` with `session_id: null`.
- Run the deterministic Chromium capture journey.
- Run the equivalent Playwright WebKit journey. Its deterministic input must
  stay at the existing capture-controller/browser boundary; it must not add a
  production-only bypass or weaken the real-microphone contract. If WebKit
  cannot execute the required media path in CI, the task is blocked rather
  than relabelled as cross-browser proof.
- Run Creator unit tests, build, browser proof for the changed surface, and
  `scripts/architecture-portal.sh check` before the implementation commit.

Automated WebKit success proves the rendering and state boundary only. It does
not replace the required real Safari M7 rerun.

## Documentation impact

Documentation impact: required.

When the functional fix lands, update the current Creator Host and testing
Portal routes to distinguish the automated ownerless-overlay regression from
the still-pending physical M7 rerun. Keep the failed `1.0.41.0` evidence
immutable as a failure record. The Stage 8B acceptance row, consolidated manual
TODO, outstanding-work row, and M7 evidence receive the passing deployed Build
only after #244 is rerun from the beginning.

## Version Management

Version impact: required at integration, none in this functional task.

This changes Creator behavior but no public Contract or Provider interface.
Stage 10 Task 10 already reserves Product Build `1.0.42.0` as the next
current-truth integration boundary, so this branch must not race it by editing
active manifests or creating a snapshot. The integration task that ships the
fix must include it in the allocated Build and the separate immutable Portal
snapshot. If `1.0.42.0` is no longer available at integration time, that task
must select the next legal Product Build under the version policy.

## Completion boundary

The functional task is complete when the source fix, tests, and current Portal
truth are committed and verified. It does not by itself close #625 or #244.
Closure requires merge, inclusion in a deployed Product Build, and a fresh
physical M7 pass on the exact deployed revision.
