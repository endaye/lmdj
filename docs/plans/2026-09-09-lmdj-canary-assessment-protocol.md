# T2a — Read-only canary assessment protocol

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).
No activation, version allocation, Issue POST, signing or deployment.

## Declared files

- `tools/canary/assessment.py`
- `tests/build/ci_canary_assessment_test.py`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` (progress link only).

Implement the deterministic input/output boundary of T2a. Read exact Git
first-parent deltas (including reverts), endpoint Host manifests and Assembly
inputs; reject bootstrap, incomplete or oversized inputs rather than truncate.
Reuse the CI review adapter's ordered backends, finite errors and time budgets.
Adapter results are data supplied by a trusted caller, never model-provided
execution receipts. Validate full input coverage, exact component/commit
references, bounded prose and closed fields. Stop on the first valid assessment;
major, migration or unknown compatibility pauses preparation rather than trying
another model for a more convenient answer. All failed backends yield a stable
report intent, not a blind Issue write or a successful empty assessment.

This library does not prove GitHub receipt authenticity, semantic truth of AI
prose, process isolation, timeout enforcement or durable Issue delivery. Those
remain obligations of the future adapter/coordinator integration. No CLI or
workflow is introduced. Input content is untrusted data; downstream changelog
rendering must escape it. No output carries command or mutation authority.

This first protocol covers the two Web Host version domains only. It does not
allocate or adjudicate Module, Provider or Contract versions. Authenticated PR
review collection and bounded chunking remain adapter integration work; the
Git-only input contract accepts no PR-number or external-URL citations.

## Verification and acceptance

Start with missing-module regressions. Use real temporary Git repositories for
complete/reverted/renamed histories, pinned endpoint manifests and dirty-tree
immunity. Exercise invalid JSON, stale digests, omitted inputs/components,
invented references, injected fields, size limits, ordered fallback, stop after
valid uncertainty, stable all-failure intents and replay. Execute existing
canary suites and complete CI contract discovery, staged ownership, Portal
check, final committed-range classification and PR declaration checks.

Local tests establish only the deterministic protocol. Live provider execution,
durable report enqueue/delivery, local version/changelog preparation, version
PR reconciliation and final merged candidate verification remain unexercised.
The main test/report acceptance ledger remains open independently of this Task.

Local verification: 34 new protocol tests pass. Full CI contract discovery and
Portal results are recorded with the exact shipped head in the PR. Real AI,
outbox delivery, candidate preparation and deployment are not claimed by these
fixture-based process-receipt tests.

## Version Management

Version impact: none

Reason: read-only internal assessment tooling; no manifests, Product Build,
Host versions, Assembly inputs or snapshots are modified.

## Documentation Impact

Documentation impact: none

Reason: internal library with no operator entry point or active delivery change;
no current Portal fact or route changes.
