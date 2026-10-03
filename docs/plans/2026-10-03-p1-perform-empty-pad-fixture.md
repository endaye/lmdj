# P1 Perform master capture with a real empty target

Complete T6 and T7 Creator proofs reached the final Perform capture leg, then
timed out at empty B1. Their unchanged Native generator explicitly assigns all
64 Pads. The original T7 failure snapshot shows assigned B1 and revision73;
it does not demonstrate an empty-Pad capture failure. Retain both negatives.

## Task scope and verification

- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `docs/plans/2026-10-03-p1-perform-empty-pad-fixture.md`

After the original replay leg, stop replay and assert its stopped far side.
Use the actual Sample/Bank B/Delete B1 controls to create the target. Require an
assigned target beforehand, a new revision, Native null assignment afterward,
unchanged Assets and Patterns, then return to Perform. Retain all original
launch/HOLD/FX/record/WAV/save/replay/reload legs, release-committed master capture
and complete Artifact identity across final reload. Do not modify the shared
fixture generator, any production bytes, or any existing timeout.

The first complete reduction successfully deleted B1, then failed at the final
revision: the retained take contained0.39 seconds of strict digital zero and
the product correctly refused an all-silent save. Preserve that actual1 and
its trace; it does not establish the precise original replay timing mechanism.
Replace the250ms wall-clock guess with a passive observation of delivered
PCM from the real Master AudioWorklet. Require playing and a new non-silent
batch for this active capture before releasing KeyQ, within the existing
30-second launch bound. The observer only reads messages from the unchanged
processor; it never injects audio, replaces a sink or acknowledges a command.
All-silent refusal, all original journey legs and Artifact reload checks stay.

Lowest checks: syntax, staged ownership and whitespace. Run the complete
original named journey on the unchanged authenticated240 Product and unchanged
Native fixture generator; retain every artifact/spec/CLI/fixture/raw/exit
identity. A targeted pass is not a full Creator lane or physical listening.

## Version Management

Version impact: none. Only fixture preparation and its plan change; coordinated
P1 identity settlement remains T8.

Documentation impact: none
Reason: This test uses existing Sample deletion and Perform capture behavior;
no Architecture Portal source fact changes.
