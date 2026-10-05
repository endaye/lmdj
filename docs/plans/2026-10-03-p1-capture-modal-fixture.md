# P1 capture ownership behind the retained trim modal

The complete T7 capture proof reached retained trimming, then failed finding
Record through the public accessibility tree. CapturePanel intentionally
remounts a native modal at trimming; its background leaves that tree. Preserve
the original raw failure and trace; this is not proof the button was removed.

## Task scope and verification

- `tests/platform/web/creator/creator_web_capture.spec.mjs`
- `docs/plans/2026-10-03-p1-capture-modal-fixture.md`

At that one existing assertion, locate the real background Record element with
includeHidden and still require disabled. Modal inertness alone must not count
as disabled. Keep the visible armed-capture assertion, discard/re-enabled
Record, new Pattern recording, replacement capture/commit, uninterrupted
playback, later recording, complete Artifact persistence and final stop/reload.
No Production bytes, action, count or timeout changes.

Lowest checks: syntax, staged ownership and whitespace. Run the complete
original named granted-microphone journey on the unchanged authenticated240
distribution with its unchanged Native sample fixture and pinned Chromium fake
capture input. Retain full artifact/spec/CLI/fixture/raw/exit identity. This
targeted fake-device result is neither a complete Creator lane nor physical
microphone acceptance.

## Version Management

Version impact: none. Only the test locator and its plan change; T8 is separate.

Documentation impact: none
Reason: Existing modal and capture-owner behavior remains unchanged; no
Architecture Portal source fact changes.
