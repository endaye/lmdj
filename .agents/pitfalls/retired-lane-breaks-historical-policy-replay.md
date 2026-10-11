---
id: retired-lane-breaks-historical-policy-replay
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-11
    occurrence: https://github.com/endaye/lmdj/issues/1048#issuecomment-6104406514
    observed_by: Kimi
exit: gate:tests/build/ci_batch_controller_test.py
---

# Retiring an identity from a closed canonical registry breaks every historical-replay consumer of artifacts validated against that registry.

## Why

The CI scope policy is validated against a closed, code-resident canonical
lane registry (`change_scope._validate_policy`), and the same strict validator
serves two different duties: current admission, and read-only reconstruction
of historical state (scheduler journal replay, report planning, historical
scope-record authentication). PR #1997 retired the `chameleon_lab` demo lane
from the registry — a correct, reviewed change to the current contract — but
every policy document frozen into Git before that merge still named the
retired lane, so the next scheduler tick's journal replay raised "lanes do
not match the closed v1 allowlist" on the first historical request and the
whole batch controller (control and reports) fail-closed. The strictness was
doing its job for admission; the defect was that replay had no era-aware
mode, and nothing in the lane-removal Task audited the historical consumers.

## How to apply

Before retiring an identity from any closed canonical registry (lanes, jobs,
suites, workflows), grep for every consumer that parses artifacts frozen
under the old registry — journal replay, digest comparisons, historical
record authentication, report projections — and classify each as current
admission (stays strict) or historical reconstruction (gets an opt-in
tolerant mode backed by a closed, code-recorded registry of the retired
facts: exact position, jobs and self-hosted membership, recovered from the
removal commit's parent). Tolerance must be opt-in per callsite with the
default strict, and any policy cache must be keyed by mode so a tolerant
parse can never satisfy a later strict read. The gate
`tests/build/ci_batch_controller_test.py` (`RetiredEraReplayTests`) replays a
journal over a pre-#1997 control from a real two-era Git fixture and proves
the strict admission read of the same control still fails closed;
`tests/build/ci_change_scope_test.py` pins the registry to the recorded
historical facts and proves tolerant mode accepts exactly the era document
and rejects every non-registry variation.
