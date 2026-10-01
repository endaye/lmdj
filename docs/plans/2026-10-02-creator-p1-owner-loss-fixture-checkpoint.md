# P1 owner-loss fixture checkpoint

The standalone slot-acquisition Creator proof has two owner-loss failures: after
SIGKILL, Chromium reopens a new blank Project because the fixture's remembered
identity was never confirmed on disk. Reuse the final integration fixture's
clean process checkpoint before the separate active-recording crash.

## Declared files and verification

- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `docs/plans/2026-10-02-creator-p1-owner-loss-fixture-checkpoint.md`

Retain both original failed packaged journeys. Import through the actual UI,
close Chromium cleanly, reopen in a new process and compare complete Project
Truth. Only then begin the recording and SIGKILL its owner. Keep every automatic
reopen, apply/discard, revision, temporary WAV removal and second-owner refusal
assertion. Run both complete affected packaged journeys and staged scope before
commit, then the full Creator lane on the committed head before merge. No
timeout, coverage floor or journey assertion changes.

## Version Management

Version impact: none. Only test fixture lifecycle changes; product and public
Contract bytes are unchanged.

Documentation impact: none
Reason: establish an existing test precondition, with no changed product flow,
portal fact or projected identity.
