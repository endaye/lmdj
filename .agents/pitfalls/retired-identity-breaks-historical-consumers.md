---
id: retired-identity-breaks-historical-consumers
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-11
    occurrence: https://github.com/endaye/lmdj/issues/2022
    observed_by: Kimi
  - date: 2026-10-11
    occurrence: https://github.com/endaye/lmdj/issues/1048#issuecomment-6109518122
    observed_by: Kimi
exit: gate:tests/build/ci_batch_runtime_test.py
---

# Retiring an identity from a closed canonical registry silently breaks every historical consumer that validates old artifacts against that registry, one layer at a time.

## Why

Closed registries (`_CANONICAL_LANES`, `JOB_NAMES`, policy lane sets) are
written as if they describe the present, but replay, evidence validation and
release tooling read artifacts produced under older registry versions.
Deleting a retired entry makes every historical document naming it invalid,
so the controller fail-closes layer by layer: PR #1997 retired
`chameleon_lab` and first killed scheduler replay (`policy_at` on any
pre-retirement control, #2022), then — one layer deeper, visible only after
that fix — batch evidence validation (`JOB_NAMES` on the pre-retirement
executor run that was active at the outage). The defect is invisible at
retirement time because current artifacts never name the retired identity;
only the next historical read exposes it. Each layer needs its own
era-tolerance: a closed retired-identity registry consulted as a fallback
for historical reads, while current admission keeps the exact closed sets.

## How to apply

Before merging any retirement from a closed canonical registry, enumerate
every consumer that validates historical artifacts against it (journal
replay, evidence validation, release tooling) and give each a closed
retired-identity fallback in the same or a preceding Task; never loosen the
strict current-admission path. The gate pins the evidence-validation layer:
a historical verdict naming the retired `chameleon-lab` job validates
against its recorded API display name, an unknown job is still rejected,
and the retired registry stays disjoint from the current one. The
policy-parse layer is pinned by `tests/build/ci_test_scope_test.py` and
`tests/build/ci_batch_controller_test.py` (#2023).
