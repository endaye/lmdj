# T2g — Authenticate assessment completion before metadata handoff

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).

## Declared files

- `tools/canary/assessment_handoff.py`
- `tests/build/ci_canary_assessment_handoff_test.py`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` (progress only).

Connect the existing real Actions Runtime, assessment Journal and canonical
metadata proposal. A fresh observer authenticates its main controller identity,
using a separate `canary-assessment-*` epoch and never scheduler/outbox storage.
An explicitly selected first-parent interval can be durably claimed only after
main/policy/Git input verification; selection of version-accounted progress is
still the coordinator's responsibility. The completion observer
replays the independent assessment journal and resolves only the persisted
claim's exact producer run/attempt/control. It never accepts a caller-supplied
terminal assessment as completion authority. Verify the complete terminal job
inventory, exact producer and successful execution/upload steps, exact named
artifact, closed envelope, claimed input identity and recomputed protocol result
before durably completing the existing claim.

An active producer or temporarily invisible successful upload remains pending.
A terminal producer without successful output, an expired artifact or invalid
retained output requires explicit reconciliation. Keep the claim, never reset
it or rerun a model. An API/provenance error is not missing evidence. Already
persisted terminal bytes are reused without depending on artifact retention.
Compatible metadata preparation consumes only an authenticated terminal row;
blocked advice and pending/missing results cannot prepare versions.

This is the production API/storage consumer, not its activation: the independent
assessment Issue, reviewed executor workflow/binary configuration, successful
real provider run and recovery trigger wiring still need implementation and
remote acceptance. This Task neither invokes a model nor initializes storage,
allocates a Product Build, publishes, deploys, promotes or repairs an Issue.
Failure reporting for blocked assessment advice reuses the existing durable
outbox path. Terminal producer/output failures use a separate stable execution
report through that same outbox, while preserving the uncompleted claim; they
never fabricate a backend result. Pending upload visibility does not file a
failure. No Issue is repaired or automatically closed. Automatic delivery stays disabled.

## Verification

Start with the missing consumer regression. Use actual temporary Git histories,
the production Runtime/GitHub Journal/assessment reducer and strict HTTP/ZIP
fixtures. Observe claim → completed exact producer → persisted terminal → fresh
consumer after artifact expiry; compare complete result bytes. Cover active,
cancelled, missing, expired, ambiguous, wrong-run/control/input, malformed ZIP,
failed upload, lost completion acknowledgement and forged result cases. Verify
terminal-execution failure → durable Issue → fresh-process exact receipt recovery
after a lost business POST, without a second POST or resetting the claim. No
artifact/API fixture proves platform provenance or OS isolation; retain those
as live acceptance gaps. Run focused and complete CI-contract tests, staged and
committed ownership, Portal verification, final scope and issue-done review.

## Version Management

Version impact: none
Reason: internal evidence handoff and fixture proposals only; active identities,
Assembly, snapshots and channels remain unchanged.

## Documentation Impact

Documentation impact: none
Reason: no active workflow or operator command is added; this consumer's future
workflow wiring must document producer, storage and recovery before activation.
