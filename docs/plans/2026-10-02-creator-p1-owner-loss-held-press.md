# P1 Sequence owner-loss held-press proof

The packaged interrupted-recording journey expects the native default
240-tick attack tail, but its fixture completes the press and release before
owner loss. Native recovery preserves a completed pair's recorded duration;
the attack tail belongs to a held press interrupted by owner loss.

## Declared files and verification

- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `docs/plans/2026-10-02-creator-p1-owner-loss-held-press.md`

Hold KeyQ through the durable admission and reload, then release it in the new
document in both the existing recovery-list journey and the current main
reopen-prompt journey. Keep the exact 240-tick assertion, Truth revision, one recovered
event, recovery dismissal and subsequent recording/reopen legs. Run the
two complete affected packaged journeys against the clean parent distribution;
record its source identity and the earlier completed-pair failure. Run syntax
and staged change-scope checks before the Conventional Commit. The committed
candidate's complete Creator lane remains required before merge.

## Version Management

Version impact: none. Only a browser fixture's held-input precondition changes;
product source and recovery semantics remain unchanged.

Documentation impact: none
Reason: the journey verifies existing native recovery semantics without
changing portal facts or product identities.
