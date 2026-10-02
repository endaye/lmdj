# Creator P4.3：重开询问被打断的录音，错误信息使用用户语言（#1680）

## Outcome and authority

Reopening a Project that holds an interrupted recording asks once whether to
keep it, defaulting to keep; every Creator error surface shows a user-language
message with a next step, and error codes go to Developer diagnostics.
Authority: the 2026-09-29 workflow decision §10 and design §9.1 rows "崩溃 /
关闭时正在录音", "音频引擎出错", "存储空间满" and "错误信息". Automatic error
upload is #1681 and out of scope. Baseline: `dc0e5c2b` on an isolated
`feat/1680-reopen-recovery-prompt` worktree. Each Task includes verified
commit, push, current-head review and squash merge; no release or cleanup.

The inventory found about 30 error surfaces and at least 12 independent
message maps, so the Issue is delivered as three reviewable Tasks. Tasks 1 and
2 relate to #1680; Task 3 closes it.

## Task 1 — Ask once on reopen

- **When.** Each time the pair (Runtime Session, open Project id) changes and
  the Project is ready — boot reopen, library open, take-back, reload or
  Runtime replacement — Creator reads Sequence recovery
  (`listSequenceRecovery`) and Performance recovery
  (`listPerformanceRecovery`) once. If either has candidates it shows a
  non-modal region "Interrupted recording" with **Keep recording** (the
  primary action), **Discard…**, **More options** and **Decide later**. Keep
  is the default in that nothing but an explicit, confirmed Discard removes a
  recording; it does not take focus, because Enter and Space also play Pads. Revision
  changes within the same open never ask again, and a candidate created while
  the Project is open stays in its existing list.
- **Keep** restores every candidate to its original destination: Sequence
  `applySequenceRecovery({destinationPatternId: null})`, Performance through
  the Perform controller's `applyRecovery`. A candidate the Core refuses (for
  example `sequence_admission_unresolved`, whose journal is retained) stays in
  its list; the region then says which could not be kept here and offers
  **Open Sequence** / **Open Perform**.
- **Discard…** asks for confirmation, because a discarded journal cannot be
  undone, then discards every candidate.
- **More options** and **Decide later** change nothing: the candidates remain
  in the Sequence and Perform recovery lists. In the Sequence list, restoring
  to another Pattern moves behind a **More** disclosure; recovering to the
  original Pattern and discarding stay visible.
- The region is not `role="alert"`: an interrupted recording is not an error,
  and existing reopen journeys require no alert after a reopen. Project Truth
  changes only through the existing Facade recovery commands; the prompt keeps
  no recording data of its own.

## Task 2 — Message catalogue and Project-level surfaces

One Creator message catalogue maps each public error code to a user-language
message and a next step, and replaces the ErrorPanel, Project overview and
Duplicate maps. Sequence and transport stop rendering bare codes. Runtime boot
and Host terminal errors also record into Developer diagnostics. Tests that
pinned old copy or codes in user-visible text are updated to the new copy, and
the code assertions move to the diagnostics log.

Task 2 declared files: `apps/creator-web/src/state/error_messages.ts` (new)
with `test/error_messages.test.ts` (new); `src/components/error_panel.tsx`,
`project_surface.tsx`, `project_overview.tsx`, `sequence_overview.tsx`,
`sequence_touch_workspace.tsx`; the Runtime diagnostics effect in
`src/app.tsx`; the tests that pinned the old copy or a code in user-visible
text (`audio_lifecycle`, `project_create`, `workspace_shell`, and the two
WebKit capability-boundary specs, whose code assertion moves to
Developer diagnostics); portal `/hosts/creator-web/`. The Project overview row
shows "Needs attention", so the alert is the single place for the message.

## Task 3 — Remaining surfaces, in two PRs

The inventory's remaining surfaces are split into two reviewable PRs.

- **3a (relates to #1680):** Sample errors, long-source import, Capture and
  Sample diagnostics. One `PUBLIC_ERROR_CODES` set replaces the four
  hand-copied ones in `sample_state.ts`, `sample_actions.ts`,
  `sample_surface.tsx` and `app.tsx`. Sample messages come from
  `sampleMessage`, with a next step rendered under them. Ingest errors become
  two plain sentences; microphone failures name what to do. A
  `DiagnosticsProvider` from the Workspace lets surfaces record failures:
  `src/runtime/diagnostics_context.tsx` (new). Declared files: those modules,
  `long_source_editor.tsx`, `capture_panel.tsx`, `creator_state.ts`
  (projection-refresh copy), `long_source_ingest.ts`, their tests, the two
  browser specs that pinned old Sample copy, and portal `/hosts/creator-web/`.
- **3b (completes #1680):** Candidate, Sound Set, Perform, Authoring History
  and the waveform placeholder. Declared files:
  - the five components and `perform_state.ts`;
  - `performCaptureUnavailableMessage` in `error_messages.ts`;
  - `app.tsx`, which passes `reportFailure` to the Perform controller;
  - their tests;
  - the Perform and Sound Set browser specs. The Sound Set parity check reads
    `data-code`/`data-reason` instead of parsing the visible row;
  - portal `/hosts/creator-web/`.

## Task 3 — Remaining surfaces (original scope)

Sample, long-source ingest, Capture, Candidate, Sound Set, Perform and
Authoring History move to the catalogue. why/remedy text, raw `Error.message`,
DOMException names and resource tokens leave user-visible text and go to
diagnostics. Each surface gains a next step where it lacks one. The three
hand-copied Sample code sets become one, which also fixes the latent
`LOCAL_PROJECT_UNREADABLE` TypeError on Retry Sample preparation.

## Declared files (Task 1)

- `apps/creator-web/src/components/recovery_prompt.tsx` (new),
  `src/app.tsx`, `src/components/sequence_touch_workspace.tsx`,
  `src/styles.css`.
- `apps/creator-web/test/recovery_prompt.test.tsx` (new; the prompt's own
  states); `test/workspace_shell.test.tsx` (open timing and the real
  Keep/Discard calls, beside the existing recovery fixtures);
  `test/sequence_surface.test.tsx` where the destination control moves.
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`: a new
  owner-loss journey that keeps the take through the prompt; the existing
  list-recovery journey stays unchanged.
- Portal page `/hosts/creator-web/`; this plan.

## Verification (Task 1)

Component facts: the prompt appears once per (Session, Project) and not after
a revision change; it does not appear without candidates; Keep applies every
candidate to its original destination and reports a refused one; Discard
requires confirmation; More options and Decide later change nothing; focus
stays where it was. The packaged owner-loss journey keeps the heard take through the
prompt and checks the persisted Pattern events after reopen. Run the Creator
unit suite and TypeScript, the affected browser specs, the `creator` lane,
`scripts/docs-site.sh check`, and new-file ownership.

## Version Management

Version impact: additive Creator Host behaviour; it owes a MINOR change at the
next coordinated Creator parity version settlement. Following the parity
feature/cut split, this work preserves manifests and Assembly identities. No
Core Module, Provider or Contract identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Task 1 documents the reopen prompt, and corrects the stale statement that
owner-lost transport candidates refuse Apply (#1515 replays them). Tasks 2 and
3 document the message catalogue and diagnostics. No diagram changes.
