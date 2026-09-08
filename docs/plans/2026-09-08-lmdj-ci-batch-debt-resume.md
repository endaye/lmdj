# Explicit paused-debt resume CLI

## Task and declared files

Expose the existing bounded recovery command through the authenticated batch
runtime. This Task changes only `scripts/ci/batch_runtime.py`,
`tests/build/ci_batch_runtime_test.py`, and this plan. It changes no workflow,
permissions, journal schema, retry budget, release gate, or product behavior.

## Interface and safety boundaries

`python3 scripts/ci/batch_runtime.py resume --config CONFIG --request REQUEST --output OUTPUT`
accepts a closed JSON object `{ "id": "repair-host-1", "suites": ["core_macos"],
"reason": "runner repaired" }`. ID and reason must be nonempty strings; suites
must be a nonempty unique list naming actual debt. Null, duplicate JSON keys,
extra keys, execution authorization, and an explicit batch command are rejected.

The existing exact-main, first-attempt controller authentication and short
single-writer lock apply unchanged. Under that same lock, authenticated journal
replay must show no active executor. Even a terminal active executor requires a
separate settle operation first: resume must not incidentally settle results or
clear covered debt. Replay uses the existing Controller historical policy loader;
it does not execute historical control code or invent a checkpoint on failure.

The existing `resume:<id>` event resets only selected debt retry counters and
unpauses them, requesting bounded recovery. It preserves processed progress,
failure history, debt identity, target and evidence. The command returns idle and
never admits heavy execution. Reusing the same ID and payload is a no-op, including
after subsequent attempts; changing its payload is rejected. An identical already
recorded command remains a no-op even if later coverage cleared those debts.
API outages fail closed; a lost append response recovers the one durable event
without granting another retry reset.

## Verification and acceptance

The initial real Runtime/Journal journeys failed because resume was absent. The
actual CLI null regression then failed because null silently became settle; the
entry now requires an explicit object. Tests cover paused debt creation through
two real settlement rounds, mixed failed and missing suites, resume persistence,
later cancellation and replay without renewed budget, conflicting IDs, active
executors, malformed commands, lost append response, unavailable storage, actual
CLI routing, duplicate keys and writer-lock authentication. Every recovery leg
asserts the resulting durable state rather than only a successful return code.

Run `python3 tests/build/ci_batch_runtime_test.py`, the complete
`python3 -m unittest discover -s tests/build -p 'ci_*_test.py'` with pinned
actionlint available, and staged `python3 tests/build/ci_change_scope_test.py`.
Fixtures exercise real local Git and the production Runtime/Controller/Journal
with injectable HTTP. Actual GitHub pause/resume dispatch, visibility delays and
workflow parameter wiring remain separate O1 acceptance; this Task neither
dispatches nor changes remote state. No new required check is introduced.

Local results: 59 runtime tests, 1,363 complete CI tests (no skips, pinned
actionlint available), and 66 staged ownership tests passed. The final additional
journey proves replay after later successful coverage remains a no-op.

## Version Management

Version impact: none — CI recovery command only; no product, module or Contract
identity changes and no version allocation or release operation.

## Documentation impact

Documentation impact: none — no Architecture Portal pages, projected identities,
diagrams or product source facts change. This plan records the operator interface;
workflow wiring remains a separate Task.

## Pitfall disposition

No new ledger entry: the null-command and idempotence invariants are fully
expressed by deterministic regression journeys in this Task. No coverage floor,
timeout, selected suite or acceptance leg was reduced.
