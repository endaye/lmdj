# Creator Desktop Final T8：Pattern 改长度、DOUBLE UP 与 COPY（#1823）

## Outcome and authority

SETUP's BARS changes the selected Pattern's length, DOUBLE UP doubles it with its notes, and COPY duplicates it. Each is one commit and one Undo entry.

The product decisions are recorded in [`2026-10-08-pattern-length-and-copy.md`](../prd/decisions/2026-10-08-pattern-length-and-copy.md):

- lengths stay 1/2/4/8 bars;
- shortening deletes what lies past the new end and truncates notes that cross it;
- lengthening by choice leaves the added bars empty, and DOUBLE UP repeats the notes, as in Koala;
- COPY selects the copy and places it in the first empty Pattern slot after the source only when the source holds a slot;
- all three are unavailable while playing and refused while recording.

This plan is the "separate plan" that [Desktop Final T8](2026-10-06-creator-desktop-final-ui.md) names. It ships as two Tasks. Each Task is one Conventional Commit on its own short-lived branch, with verified commit, push, current-head review and squash merge. No Task releases, allocates a Product Build or cleans worktrees.

## Facts this plan relies on

Checked on `7350b1a0`.

- **The Contract needs no change.** `lmdj.project.v5` gives each Pattern `bars ∈ {1, 2, 4, 8}` and events capped by `L = bars × 3840` ticks. `pattern_slots` is 16 entries of a Pattern id or null. Nothing new needs to be stored.
- **Domain rules** (`packages/authoring-domain/src/command_handler.cpp`):
  - `validate_pattern` refuses an event with `onset_tick ≥ L` or `duration_tick > L − onset_tick`, so no note crosses the loop seam;
  - `merge_pattern_events` canonicalises by the `(bank, pad, onset_tick)` key;
  - `AssignPatternSlot` refuses an occupied slot and a Pattern that already holds a slot;
  - `CreatePattern` adds a Pattern and assigns no slot.
- **Persistence and history.** New commands live in Project I/O's internal command log, which is not a Contract, as `EditPatternEvents` did (#1766). Every Store commit records one history entry, with its label taken from `project_store.cpp`'s history description; an empty delta records nothing.
- **Facade.** `pattern.create`, `pattern.events.edit` and `pattern.slot.*` are commands. `admit_non_sequence_authoring` refuses authoring while the transport journal is open.
- **Creator.**
  - The Sequence page lists Patterns sorted by Pattern id.
  - Creating a Pattern commits, reloads the Runtime Snapshot when a Pattern transport session exists, then selects the new Pattern.
  - SETUP shows BARS read-only, the 1/2/4/8 segment only inside the "new Pattern" form, and no COPY.

## P1 — resize, double and copy Patterns through Core and the Web Host

**Behaviour.**

- **`ResizePattern {meta, pattern_id, bars}`.**
  - Lengthening keeps every event, so the added bars are empty.
  - Shortening removes events with `onset_tick ≥ L'` and truncates the rest to `duration_tick ≤ L' − onset_tick`.
  - It is refused for an unknown Pattern or invalid `bars`. The same length is a no-op that records nothing.
  - History label: "Change Pattern Length".
- **`DoubleUpPattern {meta, pattern_id}`.**
  - The length goes from `bars` to `2 × bars`, and each event is repeated at `onset_tick + L`.
  - It is refused at 8 bars.
  - History label: "Double Up Pattern".
- **`CopyPattern {meta, source_pattern_id, pattern_id}`.**
  - It creates `pattern_id` with the source's `bars` and events.
  - If the source holds slot `s`, the copy is assigned to the lowest empty slot greater than `s`, in the same commit. Otherwise it is assigned no slot.
  - It is refused for an unknown source, or a `pattern_id` that exists or is not a lowercase UUID.
  - History label: "Copy Pattern".
- **Common to all three.** `expected_revision` and `command_id` follow `apply_checked`: a replay returns the receipt and a stale revision conflicts. Undo restores the exact prior Truth, including the slot.
- **Facade operations.** `pattern.resize`, `pattern.double` and `pattern.copy`, behind the existing non-Sequence authoring admission, so they are refused while recording.
- **Web Host.**
  - **Recording, a transport command in flight, or playing:** refused before commit with `HOST_STATE_INVALID` and reason `sequence_session_active`, `pattern_transport_busy` or the new `pattern_transport_playing`. Truth is unchanged. Unlike `pattern.create`, which only the Creator disables while playing, the Host enforces the decision's playing boundary itself.
  - **Stopped, on the Runtime's current Pattern:** a resize or double-up commits, then republishes the Pattern view immediately, as a stopped `pattern.events.edit` does, so the next Play uses the new length.
  - **Another Pattern:** a copy, or a resize or double-up of a non-current Pattern, commits only.
- **Session.** The Runtime Session gains `resizePattern`, `doubleUpPattern` and `copyPattern`. Each mints a `command_id` per call, and a retry reuses it.

**Declared files.**

- Domain: `commands.hpp`, `command_handler.cpp`, `command_handler_test.cpp`.
- Project I/O: `project_store.hpp/.cpp`, `authoring_history_test.cpp`.
- Facade: `application.hpp/.cpp` and a dedicated `pattern_length_copy_test.cpp` with its CMake and coverage registration. Operation-inventory tests are updated where they pin public operations.
- Web Platform: `bridge.cpp`, `control_runtime.cpp`, `protocol.mjs`, `runtime_session.mjs`, `runtime_types.d.ts` and their Host, protocol, Session and source-boundary tests.
- Portal: the Authoring Domain, Project I/O, Facade and Web Runtime Platform module pages, and `/platform/web-runtime/`.

**Lowest-tier tests.**

- **Domain.**
  - Lengthen keeps events.
  - Shorten drops events past the end and truncates a crossing note to the seam.
  - Same length is a no-op.
  - Double-up repeats every event at `+L`, and is refused at 8 bars.
  - Copy: equal content and a new id; the slot after a slotted source; no slot when none is free after it; no slot for an unslotted source; refused for a duplicate id.
  - Replay and a stale revision behave as for every checked command.
- **Store.**
  - One history entry each, with its label.
  - Undo restores events, length and slot exactly; Redo reapplies.
  - Reopen keeps the result.
- **Facade.** Each operation is refused while recording.
- **Host.**
  - Stopped resize of the current Pattern: the next Play loops at the new length.
  - Refusals while playing or recording leave Truth unchanged.
  - A copy publishes nothing.
- **Protocol and Session.** Payload validation.

**Gate defect caught.** A length change or copy that loses, keeps or misplaces notes or slots compared with the decision, or that Undo does not restore exactly.

## P2 — enable BARS, DOUBLE UP and COPY in SETUP (Desktop Final T8)

**Behaviour.**

- SETUP's BARS becomes a 1/2/4/8 segment on the selected Pattern. Choosing a length calls `resizePattern`, and the current length is a no-op.
- A DOUBLE UP button calls `doubleUpPattern`. It is disabled at 8 bars.
- A COPY button calls `copyPattern` with a fresh UUID, then selects the copy, as creation does.
- All three are disabled while playing or recording, matching CREATE.
- The SHIFT + ← Undo lamp and history status show the three labels.

**Declared files.** `sequence_touch_workspace.tsx`, `app.tsx`, `runtime/sequence_actions.ts`, `state/creator_state.ts`, `styles.css`, their unit tests, `creator_web_sequence.spec.mjs`, and the Creator Host portal page.

**Lowest-tier tests.**

- **Component tests:**
  - BARS calls resize with the chosen length;
  - the current length makes no call;
  - DOUBLE UP is disabled at 8 bars;
  - all three are disabled while playing;
  - COPY selects the copy.
- **Journey.** One leg per transition, each with a far-side Truth assertion:
  1. a 1-bar Pattern with notes in bar 1 becomes 2 bars with the second bar empty;
  2. DOUBLE UP to 4 bars repeats the notes at bar 3;
  3. shortening to 1 bar removes the later notes and truncates a crossing note;
  4. Undo restores the 4-bar Pattern exactly;
  5. COPY of a slotted Pattern creates a selected copy in the next empty slot with equal events;
  6. Undo removes the copy and frees the slot;
  7. a reload keeps the final Truth.

**Gate defect caught.** A SETUP control that commits something other than the decision, or that commits while playing.

## Verification

Each Task runs its Task-specific tests and the batch-only lanes it selects (`scripts/local-ci.sh --list`), and records pass keys in its Pull Request. P1 selects the Core lanes; P2 selects creator and portal.

## Version Management

Version impact: none in this plan Pull Request (documentation only). The implementation Tasks owe MINOR bumps at the next coordinated version settlement:

- P1: `authoring-domain`, `project-io`, `application-facade` and `web-runtime-platform`;
- P2: `creator-web`.

No Contract SemVer change: the commands live in Project I/O's internal command log, and the Pattern shape is unchanged. No Product Build or Assembly change in these Tasks.

## Documentation Impact

This plan Pull Request: none. It adds a decision and a plan under `docs/`; no portal page describes them as implemented. P1 updates the Authoring Domain, Project I/O, Facade and Web Runtime Platform module pages and `/platform/web-runtime/`. P2 updates `/hosts/creator-web/`.

## Pitfall Impact

None expected. P1 searches open entries labelled `area:core` and `area:web-runtime` before shipping.
