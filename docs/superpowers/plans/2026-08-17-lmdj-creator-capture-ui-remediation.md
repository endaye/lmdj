# LMDJ Creator Capture and Sample UI Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Creator surfaces that the 2026-08-17 physical session
proved unusable by hand, and close the interaction gap that lets every
automated journey pass while a human cannot complete the same journey. Scope is
the Creator front end: the Pad Capture panel, the waveform trim handles, and
the fatal-error presentation.

**Architecture:** Creator-only. No Core Module, Application Facade surface,
transport protocol, Contract, Product Assembly or `resource_limits` change is
in scope. Every fix lives in `apps/creator-web/src/` — component markup,
`styles.css`, and the interaction handlers that own pointer and focus
behaviour. Playback truth stays Pad-Slot-owned and mutation semantics
(`command_id` + `expected_revision`) are untouched.

**Tech Stack:** React `19.2.8`, TypeScript `7.0.2`, Vitest, Playwright
`1.62.1`, Docusaurus Architecture Portal.

## Why this plan exists

Every defect below survived a full green automated matrix — 287 Vitest tests,
the packaged Chromium capture journeys, the WebKit capability boundary, and
`scripts/creator-web.sh proof`. They survived because the browser gate locates
elements by role and accessible name, which requires neither that an element be
on screen nor that a pointer aimed at its visual affordance reaches it. A human
performing row M1 of
[`2026-08-17-manual-verification-todo.md`](../../quality/2026-08-17-manual-verification-todo.md)
hit all of them in one session.

Source evidence:
[`2026-08-17-stage8b-real-microphone-capture-1.0.23.0.md`](../../release-evidence/2026-08-17-stage8b-real-microphone-capture-1.0.23.0.md)
and section F of
[`2026-08-16-outstanding-work-before-stage9.md`](../../quality/2026-08-16-outstanding-work-before-stage9.md).

## Global Constraints

- Execute on a `fix/creator-capture-ui` branch in its own worktree. Never
  implement on `main`.
- Creator front end only. If a fix appears to require a Core, Facade,
  Contract or Assembly change, stop and report instead of widening the diff.
- Do not change `resource_limits`, `COMMIT_MAX_FRAMES`, the capture state
  machine's transition matrix, the single-owner controller lifecycle, or the
  blur/hidden stop semantics. Those are proven and were confirmed by hand.
- Do not introduce a second authority for any limit already pinned to the
  generated manifest.
- **F4 and F6 below are explicitly out of scope.** Both need a product
  decision and neither is a front-end fix. Do not settle them here.
- Every Task is one reviewable Conventional Commit. Before every commit:
  verify the branch is not `main`; run the Task-specific verification and
  `scripts/architecture-portal.sh check`; stage only declared files; inspect
  `git diff --cached --name-status` and `git diff --cached --check`; after
  committing inspect `git show --name-status --oneline HEAD`.
- This plan authorizes local commits only. Push, PR creation, merge, tag,
  Release, publication, deployment and Channel promotion each require separate
  explicit authorization.

---

## Findings in scope

### F1 + F2. The capture panel has no styling and opens below the fold

`.capture-panel` has no rule in `apps/creator-web/src/styles.css`. It renders
as an unstyled flow element at the end of the Sample surface, after the Pad
grid, with no scroll-into-view and no focus move.

Measured at 1440×900: panel box `y ≈ 790`, height `157`, document height `983`.
Entering the `recording` phase adds the level meter and waveform canvas and
grows the panel to `277` px, all downward, and the page does not scroll to
follow.

Human consequence, both observed in one session:

- pressing `Record Sample` looked like nothing happened — the panel and its
  `Record into Pad N` button were off screen, and the button correctly greyed
  out under the `captureSlot !== null` guard (`sample_surface.tsx:633`), which
  read as "the button is broken";
- once recording, `Stop` was off screen and the take could not be stopped from
  the visible surface. It ran to 14.9 s and ended only when the window lost
  focus.

One fix. The panel needs a defined presentation, a position that does not
depend on how tall the Pad grid happens to be, and focus moved into it when it
opens.

### F3. `DUPLICATE_ID` presents as fatal with no way out

Re-importing a bundle whose local Project has since diverged renders under the
heading `Creator unavailable` as "The Project conflicts with existing local
data." with no recovery control; `error_panel.tsx` gives one only to
`PROJECT_BUSY` and `HOST_RESTART_REQUIRED`.

Reproduced deterministically: re-importing an unmodified bundle whose local
copy still matches succeeds silently; re-importing after a committed capture
advanced the local Project raises `DUPLICATE_ID`.

No data is lost. `Open local` remains enabled and opens the diverged Project
correctly, and a plain reload clears the error. The defect is the presentation
and the missing affordance, not the refusal.

### F5. The waveform trim handles cannot be aimed

`waveform_editor.tsx:372` and `:393` render both trim handles as native
`input[type="range"]` elements, and `styles.css:127` gives both
`position: absolute; inset-inline: 0; width: 100%; min-height: 44px;
opacity: .01`, stacked over the 12 rem waveform canvas with
`.waveform-start-handle { top: 1rem }` and `.waveform-end-handle
{ bottom: 1rem }`.

Three consequences follow directly from that geometry, and all three were hit
in a single minute of use:

1. **Which handle you grab is decided by vertical band, not by the handle you
   are pointing at.** Both inputs span the full width, so aiming at the green
   `data-handle` line drawn in the SVG is meaningless. A pointer near the left
   line but in the lower band grabs End; near the right line in the upper band
   grabs Start.
2. **The middle band belongs to neither input.** Between roughly `y 60` and
   `y 132` of a 192 px canvas there is no interactive element, so a pointer
   there does nothing at all.
3. **A mis-aimed press is destructive, not inert.** A native range input jumps
   its thumb to the clicked track position, so a click intended for one handle
   immediately moves the other trim point rather than being ignored.

`opacity: .01` means none of this is visible or learnable — nothing on screen
tells the operator where the two bands are.

Operator report: "有的时候我光标明明放在左边 Start 按钮上，但是它改的却是右边的按钮，有时候反过来，有时候是对的，有时候又点不上。" Every clause of that
maps to one of the three consequences above.

The keyboard path (`keyboardEdit`, arrow keys, `Escape` to cancel) is sound and
must be preserved; the accessible names carrying live second values must also
be preserved. The pointer path is what needs replacing.

---

## Findings out of scope — do not settle here

### F4. A silent default input commits silence with no indication

`capture_controller.ts:62` requests audio with no `deviceId`, so capture always
follows the OS default input; the absent device picker is a **declared** scope
boundary for `1.0.23.0` on the `hosts/creator-web` portal page, so the omission
itself is not the finding. The finding is the physical consequence: when the
default input changes silently — macOS Continuity rerouting to a nearby iPhone
is the observed case — `getUserMedia` succeeds, the stream carries digital
silence, and the Creator commits a full 5 s of silence onto a Pad with no
input-level gate, no silence detection and no warning.

Needs a product decision (device picker, visible input identity, an
input-level gate before commit, or some combination). Fixing F1 and F2 makes
the level meter visible, which mitigates but does not close it.

### F6. The render path has no amplitude ramp anywhere

Found by the first check of row M2 on 2026-08-17: trimming a Sample and
triggering it produces audible clicks at the trim boundaries.

This is not a Creator defect. `realtime_engine.cpp:710` renders
`voice.samples[voice.cursor] * voice.gain` and, on reaching `end_frame`, either
assigns `voice.cursor = voice.start_frame` for a loop or hard-stops the voice;
`stop_voice` (`:195`) sets `voice.active = false` immediately. There is no
attack ramp, no release ramp, no fade at the trim boundary and no crossfade at
the loop seam, and no zero-crossing snap anywhere. A trim edge that lands on a
non-zero sample is a step discontinuity, which is exactly what a click is.

The same absence predicts clicks at the loop seam (M2 step 5) and on releasing
a held voice, neither of which has been tested yet.

This needs a Core/DSP product decision — ramp length, zero-crossing snap,
crossfade, or a combination — with a realtime-safety review, because the render
path is allocation-free and lock-free and any ramp state must stay inside that
contract. It must not be settled inside a front-end Task.

---

## Tasks

### Task 1 — Design gate: the capture panel's presentation and the trim pointer model

**Done 2026-08-24.** All decisions recorded in
[`docs/prd/decisions/2026-08-24-capture-panel-modal-and-trim-handles.md`](../../prd/decisions/2026-08-24-capture-panel-modal-and-trim-handles.md):
P2-D1 panel presentation (viewport-anchored modal, fixed geometry), P2-D2
focus behaviour, P2-D3 trim pointer model (visible grips, midpoint
partition, inert middle), P2-D4 `DUPLICATE_ID` recovery. The keyboard
editing path, `Escape` cancel and accessible names survive unchanged
(P2-D3). F4 and F6 were not settled here and remain person-level decisions.

- [x] Decide and record the capture panel's presentation: whether it becomes a
      dialog anchored to the viewport, a fixed region of the Sample surface, or
      an in-flow panel with guaranteed scroll-into-view. State how it behaves
      when the panel grows on entering `recording`.
- [x] Decide and record focus behaviour on open, on phase change, and on close,
      preserving the existing `returnFocus` contract.
- [x] Decide and record the replacement pointer model for the trim handles:
      what a press near a handle does, what a press in the middle of the
      waveform does, whether a press on the track is allowed to move a trim
      point at all, and how the two handles stay independently reachable when
      they are close together.
- [x] Confirm the keyboard editing path, the `Escape` cancel, and the
      accessible names survive the replacement unchanged.
- [x] Record the decisions in `docs/prd/decision-log.md`, or as open questions
      if any of them turns out to be a product-level choice rather than an
      implementation one.

**Verification:** the decision record exists and names each behaviour above.
No source change in this Task.

### Task 2 — Capture panel presentation, position and focus (F1 + F2)

**Done 2026-08-24.** Implemented the P2-D1/P2-D2 decisions: the panel is a
viewport-anchored `<dialog>` + `showModal()` modal on a shared `ModalDialog`
primitive extracted from `ConfirmationDialog` (whose behavior and callers are
unchanged), with fixed outer geometry that does not change when entering
`recording`, focus on the phase's primary action on open and after phase
transitions, `Escape` closing in every phase, a non-dismissible backdrop, and
the `returnFocus` restore owned solely by the dialog. Landed with Creator Web
Host `1.5.0` in Product Build `1.0.31.0`.

- [x] Implement the Task 1 presentation decision in `styles.css` and
      `capture_panel.tsx` / `sample_surface.tsx`.
- [x] Guarantee that opening the panel brings it and its primary action into
      view, and that entering `recording` keeps `Stop` reachable without the
      operator knowing to scroll.
- [x] Move focus into the panel on open and restore it on close.

**Verification:** a Playwright assertion that the panel's primary action and
`Stop` are **within the viewport** — `boundingBox` compared against the
viewport, not `isVisible()` — in `idle` and in `recording`, at a viewport short
enough to reproduce the original failure. Component tests for focus movement.
`npm --prefix apps/creator-web test -- run` and `npx tsc --noEmit` pass.

### Task 3 — Trim handle interaction (F5)

**Done 2026-08-24.** Implemented the P2-D3 decisions: each handle line is a
visible grip (14px bar with top/bottom affordances) whose grab zone spans
12 px to each side of the line, partitioned at the midpoint between the two
lines so zones never overlap and adjacent handles each keep half the gap; a
press inside a zone grabs that handle, the drag preserves the grab offset
(handle follows pointer delta, never jumps to the pointer position), a press
on the waveform body outside both zones moves nothing, and
`pointercancel`/`Escape` still cancel and restore through the existing
gesture functions. Both range inputs remain the keyboard/assistive-technology
channel with live-second accessible names, removed from the pointer path
(`pointer-events: none`, visually hidden but focusable). Landed with Creator
Web Host `1.5.1` in Product Build `1.0.32.0`.

- [x] Replace the two stacked full-width invisible range inputs with the
      Task 1 pointer model.
- [x] Make the interactive regions visible, so which handle a pointer will grab
      is predictable before pressing.
- [x] Keep both handles independently reachable when their values are adjacent.
- [x] Preserve the keyboard path, `Escape` cancel, gesture begin/preview/commit
      semantics, and the accessible names with live second values.

**Verification:** component tests for grabbing each handle from a pointer
position that previously hit the wrong one, for a press in the previously dead
middle band, and for two adjacent handle values. A Playwright assertion that a
pointer press aimed at the Start handle changes Start and leaves End unchanged,
and the mirror case. Existing waveform tests continue to pass unchanged.

### Task 4 — Recoverable presentation for `DUPLICATE_ID` (F3)

**Done 2026-08-24.** Implemented the P2-D4 decisions: `DUPLICATE_ID` no
longer renders under the fatal `Creator unavailable` heading — the panel
names the actual situation ("Project already on this device") and explains
that the import was refused because the local copy of the Project has newer
changes and that nothing was lost. A new `Open local Project` recovery
control leads to the local Projects list — the same destination as the
existing `Open local` affordance — and dismisses the panel through the
existing listing path, without a reload; the diverged local Project's
identity is not available to the Host (the Runtime's `DUPLICATE_ID` error
carries no details and the Host must not parse the bundle), so the control
targets the list rather than a direct open. Every other error code's
heading, message and retry wiring is byte-identical. Landed with Creator
Web Host `1.5.2` in Product Build `1.0.33.0`.

- [x] Give `DUPLICATE_ID` a message that names the actual situation and a
      recovery control that leads to the existing local Project, rather than
      the bare `Creator unavailable` heading.
- [x] Confirm no other error code's presentation changes.

**Verification:** component tests for the message and the control; a Playwright
journey that imports, diverges the local Project, re-imports, and recovers
without a reload. The `error_panel` mapping table test still covers every code.

### Task 5 — Re-run the physical checks the fixes claim to repair

- [ ] Re-run row M1's capture journey by hand far enough to confirm the panel,
      `Stop`, and the recovery path are usable without prior knowledge. This
      does not re-open M1's hearing result, which stands.
- [ ] Run rows M2 and M3 from
      `2026-08-17-manual-verification-todo.md`, recording M2 step 1's outcome
      against F6 rather than against this plan.
- [ ] Record the outcome in `docs/release-evidence/`.

**Verification:** a physical record exists and names the exact Product Build,
revisions, OS and browser versions.

---

## Version Management

**Version impact: required.**

- `creator-web` takes a SemVer **minor** bump from `1.3.0`: the capture panel
  presentation and the trim interaction are observable behaviour changes to a
  Host surface, not internal refactors, and no Contract or protocol changes.
- No Core Module, Provider, Contract or Application Facade version changes;
  the diff does not reach them.
- A new Product Build must be allocated before any team-testing or release
  distribution of these fixes, per `docs/governance/version-management.md`, and
  that allocation carries its own immutable Architecture Portal snapshot made
  with `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`.
- `assembly.lock.json` must be regenerated after the compiled assembly is
  final, not before — see B4 in the pre-Stage-9 triage.

## Documentation impact

**Documentation impact: required.**

- `hosts/creator-web` describes the Creator's Sample and Pad Capture surfaces
  and its physical-evidence boundary; both change when these Tasks land.
- The affected physical rows in
  `docs/quality/2026-08-17-manual-verification-todo.md` and section F of
  `docs/quality/2026-08-16-outstanding-work-before-stage9.md` must be updated
  in the same Task that closes each finding.
- Run `scripts/architecture-portal.sh check` before every commit.

## Out of scope

Device picker, input-level gate and silence detection (F4); any amplitude ramp,
zero-crossing snap or crossfade in the render path (F6); Sequence and Perform
surfaces; long-material resource model; offline install / PWA; anything behind
a Stage 9 or later boundary.
