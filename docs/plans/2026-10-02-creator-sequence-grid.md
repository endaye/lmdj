# Creator P2.6：Sequence 网格编辑（#1671）

## Outcome and authority

Edit a Pattern on a grid, as in Koala's Sequence Grid:

- add and remove notes;
- drag position and length;
- adjust velocity;
- box-select, then delete or move as a batch.

Every edit changes Project Truth exactly as shown and is undoable.

The product decisions are recorded in [`2026-10-02-sequence-grid-editing.md`](../prd/decisions/2026-10-02-sequence-grid-editing.md): layout, overview display, first-cut scope, and editing while playing. Its other sources are:

- the 2026-09-29 workflow baseline (items 1 and 8) and design §6;
- the 2026-09-30 Undo/Redo semantics (§3, §4);
- the 2026-08-23 Sequence recording semantics.

The work ships as three Tasks. Each Task is one Conventional Commit on its own short-lived branch, with verified commit, push, current-head review and squash merge. No Task releases, allocates a Product Build or cleans worktrees.

## Facts this plan relies on

Checked on `dc0e5c2b`.

- **The Contract needs no change.**
  - `lmdj.project.v5` (`contracts/project/lmdj.project.v5.schema.json`, Contract 5.1.0) gives each `pattern_event` four fields: `slot {bank, pad}`, `onset_tick ≥ 0`, `duration_tick ≥ 1` and `velocity 1..127`.
  - Per-`bars` rules cap `onset_tick ≤ L − 1` and `duration_tick ≤ L`, where `L = bars × 3840`.
- **Domain invariants** (Sequence recording semantics design §10.1, SR-D26):
  - PPQ is 960, so 1/16 is 240 ticks.
  - `duration ≤ L − onset`: no note crosses the loop seam.
  - The event key is `(bank, pad, onset_tick)` and a later write wins; one key never appears twice.
  - Events are sorted canonically.
  - Notes at different onsets may overlap.
  - `merge_pattern_events` and `validate_pattern` in `packages/authoring-domain` enforce these rules.
- **No command removes, moves or resizes individual events.**
  - `MergePatternEvents` inserts or replaces by key. Only the recording flush uses it, and no Facade operation exposes it.
  - `ApplyAuthoringDelta` is Undo/Redo-only.
- **History** is automatic. Every Store commit calls `AuthoringHistory::prepare`, and an empty delta records nothing (`authoring_history.cpp`). A new command needs a label in `project_store.cpp`'s history description.
- **Concurrency.**
  - While the transport journal is open (recording), `admit_non_sequence_authoring` (`application.cpp`) already refuses non-Sequence authoring.
  - Playback alone is admitted, but `prepare_and_publish` does not republish the playing Pattern.
  - `sequence.settings.update` publishes a BPM change during playback through `publish_project_pattern`, which returns the `activation_frame` of the swap (`control_runtime.cpp`). That scheduled swap stops Pattern voices and resets the Pattern origin, so it is not used for grid edits; see the [live-edit erratum](../prd/decisions/2026-10-02-sequence-grid-live-edit.md).
  - Undo and Redo are refused while the transport plays (`pattern_transport_busy`).
- **Creator.**
  - `projectView` (`project_actions.ts`) drops `events`, so `ProjectView.patterns` holds only `{patternId, bars}`.
  - `sequence_overview.tsx` is a read-only facts panel.
  - `sequence_touch_workspace.tsx` holds Pattern, BPM, Swing, Bars, Quantize and recovery.
  - No grid exists.

## T1 — atomic Pattern event edit through Core and the Web Host

**Behaviour.**

- **Domain command** `EditPatternEvents {meta, pattern_id, remove: [EventKey], put: [PatternEvent]}`, applied as one commit:
  - remove every keyed event, then insert or replace every `put` event by key;
  - canonicalise the result.
- **It is refused** when:
  - the Pattern is unknown;
  - a removed key does not exist;
  - a `put` event fails `validate_pattern`;
  - `remove` or `put` repeats a key.

  Refusals use typed reasons, and `expected_revision` / `command_id` follow `apply_checked`: replay returns the receipt, and a stale revision conflicts.
- **Each edit shape is expressed this way:**
  - a move is `remove` plus `put` at the new key;
  - a length or velocity change is a same-key `put`;
  - a batch is one command.
- **An edit whose result equals the current Pattern** records no history entry. T1 pins the exact Store outcome (refused or accepted without a revision change) in a test, consistent with the existing no-op behaviour.
- **Persistence and history.** Project I/O persists the command in its internal command log, which is not a Contract, following the `ApplyAuthoringDelta` precedent. History labels it "Edit Pattern".
- **Host operation `pattern.events.edit`** carries `{pattern_id, remove, put, expected_revision, command_id}`.
  - **Recording, a transport command in flight, or a scheduled Pattern publication not yet applied:** refused before commit (`sequence_session_active`, `pattern_transport_busy`, `pattern_publication_pending`); the Facade guard also refuses recording.
  - **Another Pattern than the Runtime's current one:** commit only (`publication: "none"`).
  - **Stopped, current Pattern:** commit, then replace the Pattern view immediately (`"published"`), so the next Play is not refused for a pending publication.
  - **Playing the current Pattern:** commit, then swap the view in place with `publish_pattern_view_preserving_phase` (`"live"`), per the [live-edit erratum](../prd/decisions/2026-10-02-sequence-grid-live-edit.md). The response returns `pattern_publication: {generation, activation_frame}`.
  - **Every engine Pattern slot held by a sounding retiring view:** commit, then defer the swap (`"deferred"`). The transport service cadence swaps the view in place, prepared from Truth, once reclaim frees a slot; a later edit or any other publication supersedes it. The owner chose this over refusing the edit on 2026-10-02 ([erratum](../prd/decisions/2026-10-02-sequence-grid-live-edit.md) item 5).
  - **A failed swap after commit** returns the committed revision with `"failed"` and a typed `snapshot_error`. It never misreports a committed edit.
  - A grid edit changes no Bank, so a Runtime current before it stays current (`runtime_revision`) after a swap, a deferral or an edit of another Pattern.
  - Each edited view is prepared by cooking the Project (`prepare_runtime_snapshot`), which reads every assigned Pad's artifact; only the Bank publication is avoided.
- **Session.** The Runtime Session gains `editPatternEvents`. Its `command_id` is minted per call, and a retry reuses the same identity.

**Declared files.**

- Domain: `commands.hpp`, `command_handler.cpp`, `command_handler_test.cpp`.
- Project I/O: `project_store.hpp/.cpp`, `authoring_history_test.cpp`.
- Facade: `application.hpp/.cpp`, and a dedicated `pattern_events_edit_test.cpp` with its CMake and coverage registration. The operation-inventory tests are updated where they pin public operations.
- Web Platform: `bridge.cpp`, `control_runtime.cpp`, `protocol.mjs`, `runtime_session.mjs`, `runtime_types.d.ts`, plus their Host, protocol, Session and source-boundary tests.
- Portal: Authoring Domain, Project I/O, Facade and Web Runtime Platform module pages, and `/platform/web-runtime/`.

**Lowest-tier tests.**

- Domain: apply, remove-missing, duplicate key, invalid event, seam overflow, replay, stale revision, canonical order, overlap allowed.
- Store: one history entry per edit; Undo restores exactly; Redo; the no-op outcome; reopen.
- Facade: refused while recording; admitted while playing.
- Host:
  - stopped publish applied by the next quantum, so the next Play sounds the edit;
  - a stopped edit after Play and Stop is applied immediately, with nothing left pending;
  - playing publish that keeps the origin and plays a new note ahead of the playhead in the same loop;
  - a deferred swap that lands in place once a sounding view frees its slot, and whose note then sounds;
  - another Pattern publishes nothing;
  - a failed swap reports `"failed"` with the committed revision;
  - a preview is still admitted after an edit;
  - refusals, each with Truth unchanged: recording, a settling transport command, a pending BPM publication (then retried), a legacy Sequence session, and a Facade refusal's code.
- Protocol and Session payload validation.

**Gate defect caught.** Any edit that does not round-trip exactly through Truth, history and publication.

## T2 — grid projection: touch grid read-only and the overview display

**Behaviour.**

- **Creator state.** `ProjectView.patterns` keeps the canonical events. A pure view model (`sequence_grid_model.ts`) maps a Pattern to:
  - rows for the active Bank;
  - tick columns at the chosen snap: 1/4, 1/8, 1/16 (default), 1/32 or off;
  - note rectangles;
  - a horizontal viewport over 1 to 8 bars.
- **Touch workspace.** Sequence gets a grid panel showing 16 rows by the whole Pattern, with horizontal scroll and a snap selector. In T2 it is read-only; it follows Bank switching and the selected Pattern.
- **Overview display** (`sequence_overview.tsx`, read-only) shows:
  - a 64-row thumbnail of the Pattern across all four Banks;
  - the live playhead, from the existing transport projection;
  - a frame marking the touch grid's Bank and time window;
  - the existing facts plus selection facts (count, snap, velocity).

  The placeholder caption goes.
- **Lifecycle.** Refresh after any authoring commit, Undo/Redo or reopen keeps both views in step with Truth.

**Declared files.**

- `runtime_types.ts`, `project_actions.ts`.
- New `state/sequence_grid_model.ts`, `components/sequence_grid.tsx` and `components/sequence_pattern_overview.tsx` (or the existing `sequence_overview.tsx`).
- `sequence_touch_workspace.tsx`, `styles.css`, and their tests.
- Portal `/hosts/creator-web/`.

**Lowest-tier tests.**

- View model: snap columns, the 1/2/4/8-bar extents, the seam, overlap rendering, Bank filtering, and thumbnail mapping of all 64 rows.
- Component: grid rows and notes for a fixture Pattern; Bank switch; viewport frame; playhead.
- A packaged journey that records notes, then sees them on both grids after reopen.

## T3 — grid editing with Undo/Redo

**Behaviour.**

- **Gestures:**
  - a pen tap on an empty cell adds a note;
  - a tap on a note removes it;
  - dragging a note's body moves it, and dragging its end changes its length;
  - velocity is set by dragging vertically in VEL mode;
  - a box-select chooses notes, which can then be deleted or moved as a batch.
- **One gesture is one `pattern.events.edit`, sent at gesture end.** A gesture that ends where it started sends nothing.
- **Rules applied by the grid:**
  - moves and lengths snap to the selected grid;
  - the grid clamps length to the seam (`duration ≤ L − onset`);
  - a move onto an occupied key replaces that note, by the key rule.
- **Defaults** (proposed; adjustable in review):
  - a new note's length is one snap step, or 1/16 with snap off;
  - its velocity is the last velocity set in the grid, starting at 100.
- **Disabled and refused states:**
  - while recording, editing is disabled, with the reason given;
  - while playing, edits commit and are heard in place from the next not-yet-played note; a `"deferred"` edit is heard once its swap lands;
  - a `pattern_transport_busy` or `pattern_publication_pending` refusal is retried, not shown as a conflict;
  - a conflict or refusal restores the projection from Truth and shows the reason.
- **Undo and Redo.** The existing controls apply. They stay stop-only, per the 2026-09-30 decision.

**Declared files.**

- `sequence_grid.tsx`, `sequence_grid_model.ts`, `sequence_actions.ts` (`editPatternEventsJourney`), `sequence_state.ts`, the app wiring, `styles.css`, and their tests.
- `tests/platform/web/creator/creator_web_sequence.spec.mjs` (or a new `creator_web_sequence_grid.spec.mjs`).
- Portal `/hosts/creator-web/` and `/product/workflows/`.

**Lowest-tier tests.**

- Model: each gesture to its exact `remove`/`put`; no-op suppression; snap; clamp; collision.
- Component:
  - one command per gesture;
  - disabled while recording;
  - the deferred state while playing;
  - conflict recovery;
  - Undo/Redo refresh.
- The packaged journey covers, with a far-side assertion per leg:
  1. add, move, resize, velocity, batch delete and batch move, each checked against `project.inspect` Truth;
  2. Undo and Redo of each;
  3. refused while recording;
  4. an edit during playback that swaps in place without restarting playback, recording the per-edit Host round-trip;
  5. reopen with the same Truth and an empty history.

## Verification

- Each Task runs its lowest-tier tests, then the relevant native and JS suites.
- `scripts/docs-site.sh check`.
- Each batch-only lane the change selects runs on the committed head. Its `pass key=` goes into the Pull Request.
- Revert proofs run against rebuilt artefacts.
- No timeout, coverage floor, owned lane or journey leg is relaxed.

Not inferred from automation: physical touch and drag ergonomics on iPad or touch screens, real Safari, and audible in-place swaps while playing. Those remain separate acceptance rows.

## Version Management

Version impact: none in this plan Pull Request (documentation only). The implementation Tasks owe MINOR bumps at the next coordinated version settlement, after #1741's Product Build 2.0.71.0:

- T1: `authoring-domain`, `project-io`, `application-facade` and `web-runtime-platform`;
- T2 and T3: `creator-web`.

No Contract SemVer change: `lmdj.project.v5` already carries `duration_tick`, and the new command lives in Project I/O's internal command log. No Product Build or Assembly change in these Tasks.

## Documentation Impact

Documentation impact: required for this plan Pull Request, `/product/workflows/`. Following the #1695 precedent, it records the approved grid behaviour there, kept separate from the current unimplemented status. Each implementation Task declares its own impact:

- T1 is required for `/core/modules/authoring-domain/`, `/core/modules/project-io/`, `/core/modules/application-facade/`, `/core/modules/web-runtime-platform/` and `/platform/web-runtime/`.
- T2 is required for `/hosts/creator-web/`.
- T3 is required for `/hosts/creator-web/` and `/product/workflows/`.

The Host → Facade → Store/Cooker dependency topology is unchanged.

## Pitfall Impact

Pitfall impact: none expected. Each Task re-checks open entries for `area:core`, `area:creator` and `area:web-host` before shipping.
