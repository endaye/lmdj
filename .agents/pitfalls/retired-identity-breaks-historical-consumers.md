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
  - date: 2026-10-26
    occurrence: https://github.com/endaye/lmdj/pull/2510
    observed_by: Claude Opus 5.5
exit: gate:tests/build/ci_test_scope_test.py
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

Regrouping a lane that stays current is the same defect. #2507 made the
`creator` lane two jobs; the policy recorded by the in-flight batch still
named one, historical replay called that drift, and every controller tick
failed for about 19 hours until the revert #2510. A regrouping lands its
former job tuple in `_SUPERSEDED_LANE_JOBS` in `scripts/ci/change_scope.py`
in the same change; historical replay accepts exactly the listed tuples and
the self-hosted jobs only the regrouping introduced, and still rejects any
other grouping. `tests/build/ci_test_scope_test.py` pins both directions.
Before merging a change to `lane_jobs`, also replay the policies recorded
at recent `main` revisions with `test_scope.parse_policy(..., historical=True)`.
