---
id: portal-impact-two-dot-base-diff
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/527
    observed_by: claude-fable-5
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/530
    observed_by: claude-opus-5
exit: gate:apps/architecture-portal/test/changed-files.test.mjs
---

# The portal impact gate diffed `PORTAL_BASE_SHA..PORTAL_HEAD_SHA` two-dot, so a branch behind `main` inherited every portal page merged after its base as "changed by this PR" and a truthful `Documentation impact: none` failed.

## Why

`PORTAL_BASE_SHA` comes from the `pull_request` event's `base.sha`, which is
the tip of `main` at event time, not the merge base. `git diff A B` (two-dot)
compares the trees, so commits that landed on `main` after the branch was cut
appeared in the diff in reverse. PR #527 was a four-file `docs/superpowers/**`
branch blamed for the pages #521 had merged; PR #530 was a single-file
`docs/research/**` branch blamed for five pages merged by #527 and #529.
Neither touched a portal page.

## How to apply

Absorbed by #531. `apps/architecture-portal/scripts/lib/changed-files.mjs`
resolves both the documentation-impact and snapshot-projection ranges from the
merge base, which is the range `scripts/ci/local_preflight.py` already measured
locally, and `.github/workflows/architecture-portal.yml` computes no range of
its own. `apps/architecture-portal/test/changed-files.test.mjs` pins the
behind-base branch, and
`tests/build/ci_workflow_topology_test.py::test_portal_never_measures_a_two_dot_range_between_the_inputs`
keeps the range out of the workflow.

A gate failure naming portal pages is therefore the branch's own edit. #539
converged the two sibling ranges on the same rule: `ci.yml`'s docs-static
`git diff --check` and `read_git_inventory` in `scripts/ci/change_scope.py`
both measure from the merge base, pinned by
`tests/build/ci_change_scope_test.py` and
`tests/build/ci_workflow_topology_test.py`. No CI range now reads a Pull
Request's base branch tip as its range endpoint.
