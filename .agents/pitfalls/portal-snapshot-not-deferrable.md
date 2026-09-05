---
id: portal-snapshot-not-deferrable
area: docs-governance
status: open
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/issues/436
    observed_by: claude-opus-5
exit: none
---

# An immutable Portal snapshot cannot be scheduled after the Product Build integration merges, because the Core `full` tier and the Portal check both read the snapshot for whatever Product Build the manifests already name.

## Why

The obligation is triggered by the allocation, not by the merge. The moment
`products/lmdj/version.json` names a new Product Build,
`apps/architecture-portal/scripts/check-release-docs.mjs` requires a matching
snapshot unconditionally, `.github/workflows/ci.yml` runs the full
`scripts/architecture-portal.sh check`, and six `build.release_*` tests in the
Core `full` tier read
`apps/architecture-portal/versioned_metadata/version-<build>.json` directly.

So an implementation plan that allocates the Build in one Task and defers the
snapshot to a later post-merge Task describes an unshippable sequence: the
first Task cannot go green on its own, locally or in CI. The Stage 10 plan
split #436 (integration) from #438 (snapshot) exactly that way, and the gap was
only visible after the version bump was already written.

This is not the same failure as
[`squash-witness-provenance`](squash-witness-provenance.md). That entry covers
provenance *after* the two land in one squash; this one is about a plan that
never lets them land together in the first place.

## How to apply

Write the plan so the immutable snapshot lands in the **same Pull Request** as
the Product Build allocation. Keep them as two commits if the plan wants
separate reviewable units — Product Build `1.0.41.0` (#520) and `1.0.40.0`
(#420) both did this — but never as two Pull Requests.

The snapshot freeze requires a clean worktree and binds the current `HEAD`, so
the order inside the branch is fixed: commit the integration, then run
`scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`, then commit the
snapshot. Any later amendment of the integration commit changes its SHA and
invalidates the frozen revision, so delete the snapshot artifacts and refreeze
rather than editing them.

A follow-up Task then retains only what genuinely cannot exist before the
merge: the post-squash source-tree witness, the merged revision, and the remote
CI run IDs.
