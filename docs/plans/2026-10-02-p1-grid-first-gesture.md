# P1 Grid journey first-gesture audio

The complete Grid acceptance journey waits for the retired Activate audio
button and reaches its unchanged 360-second budget after P1 removes that gate.
Use the existing trusted Pad gesture helper to prepare the real AudioContext
before driving the original editing journey.

## Task scope and verification

Declared files:
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `docs/plans/2026-10-02-p1-grid-first-gesture.md`

The lowest-tier test is the complete named Chromium Grid journey, including
all gesture edits, exact command accounting, Undo/Redo, recording refusal,
in-place playback swaps and persisted reopen. Keep every assertion and the
original 360-second budget. Test against the unchanged authenticated 8bf835be
Creator distribution, with the Task's exact fixture bytes and the original
Native fixture generator. Product source is unchanged by this Task.

The original complete Creator proof's missing-button failure is retained.
A targeted journey is Task verification and does not replace the complete
committed-head Creator lane before shipping.

## Version Management

Version impact: none. Browser test preparation only; no product source,
operation, component manifest, Product Build or Contract changes.

Documentation impact: none. No portal route, documented source fact or
architecture boundary changes; this plan records the fixture repair.

No required gate, lane, timeout or threshold changes. The regression belongs
in its browser fixture and does not qualify for a process pitfall entry.
