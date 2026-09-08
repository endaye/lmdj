# T2e — Assessment persistence and failure outbox handoff

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).

## Declared files

- `tools/canary/assessment_journal.py`
- `tests/build/ci_canary_assessment_journal_test.py`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` (progress only).

Use the existing authenticated `Journal` protocol, not a new database or a
file cache. An independently configured assessment journal stores a complete
input claim and its exact executor identity before model execution. A fresh
observer of a claimed input never launches that input again. Persist terminal
advice only for the original executor after recomputing the protocol result.
Lost write responses reconcile from the journal; terminal replay is idempotent
only for identical complete bytes. Store bounded compressed payloads as complete,
ordered, content-addressed chunks, followed by the claim/terminal reference. This
covers the protocol's full input/output budgets, not only compressible examples.
Resume partial chunk writes without admitting an incomplete reference. Reject missing,
corrupt, truncated, oversized or conflicting records, never silently bootstrap.

Keep claim, model execution and completion as separate phases so model calls
never hold the shared short writer lock. The caller authenticates input and
executor run/control; these records are not bearer capabilities. Missing terminal
producer evidence requires reconciliation, not timed re-execution. No guessed
expiry or automatic lease reset is introduced in this phase.

Project blocked terminal assessments to deterministic report buckets, containing
exact input/result/run identities and finite backend diagnostics, not raw model
prose or credentials. Deliver through the existing independently configured
report outbox under its shared writer lock. A retained terminal assessment can
reconstruct its report after process loss and after temporary artifacts expire.
Claimed or advised assessments produce no failure Issue. Reporting never calls a
model, tests, repair code, PR mutation, allocation or deployment.

The focused Task implements real Journal append/load and Outbox delivery paths,
not remote configuration. The production assessment Issue, source/writer
authentication, phase workflows, retained-result discovery, explicit reconciliation
of a missing executor result and isolated provider acceptance remain required.
No existing scheduler/outbox journal is repurposed or initialized. Live automatic
assessment stays disabled until these integration and acceptance steps land.

## Verification

Begin with missing-module red. Exercise real Git context collection, runtime
process execution, Journal protocol and outbox composition. Use fresh adapter
objects after claim/terminal/Issue write crashes; verify the far-side persisted
result and exact Issue receipt, not just a successful function return. Cover
wrong executor/epoch, changed result, corrupt payload, edited/missing history,
lost append responses, unavailable locks and storage aliases. Transport, GitHub
API identity and distributed lock behavior are fixtures, not production proofs.
Run full canary/CI tests, staged ownership, Portal and final PR declarations.

## Version Management

Version impact: none
Reason: internal assessment persistence/reporting; no active identities, Host
manifests, Product Build, Assembly or snapshots change.

## Documentation Impact

Documentation impact: none
Reason: no active workflow, operator command or Portal behavior changes. The
future live journal configuration/phase entry points must document their recovery
commands and authority boundaries before activation.
