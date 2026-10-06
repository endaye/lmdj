# P1 T8 prerequisite: restore Portal snapshot retention

The approved Architecture Portal policy retains the latest five Product Build
snapshots in HEAD. The T8 source baseline currently carries 23; reconcile this
existing inventory before freezing the next candidate. This documentation Task
changes no product code, identities, or immutable bytes of retained snapshots.

## Declared files

- `apps/architecture-portal/versions.json`: retain the existing newest five.
- Remove only the tracked files belonging to the aged-out versions below from
  `versioned_docs/version-BUILD/`, `versioned_sidebars/version-BUILD-sidebars.json`,
  `versioned_metadata/version-BUILD.json`,
  `versioned_provenance/version-BUILD-squash-witness.json`, and
  `static/versions/BUILD/`. The exact deletion list is derived from the source
  index; all five archive families and the index change together.
- This plan, `docs/plans/2026-10-06-p1-snapshot-retention.md`.

Retained: `2.0.82.0`, `2.0.81.0`, `2.0.80.0`, `2.0.78.0`, `2.0.76.0`.

Aged out: `2.0.75.0`, `2.0.71.0`, `2.0.70.0`, `2.0.69.0`, `1.0.66.0`, `1.0.65.0`, `1.0.64.0`, `1.0.62.0`, `1.0.61.0`, `1.0.60.0`, `1.0.59.0`, `1.0.58.0`, `1.0.57.0`, `1.0.56.0`, `1.0.55.0`, `1.0.54.0`, `1.0.53.0`, `1.0.52.0`.

The unchanged snapshots and their provenance remain byte-identical. All removed
blobs remain auditable at protected Main revision `0bf98229374d355313502b2f9fb593e74e2297cf`. Failed Build 83/84
reservations, candidate worktrees, frozen outputs, and raw evidence are outside
this Task. No branches or worktrees are removed.

## Verification

Before editing, authenticate each retained and aged-out file against its source
Git blob, archive the original bytes, run the content-inventory tests, and verify
the current Product Build snapshot. Check current page links before removal.
After editing, verify the exact declared diff, all retained byte hashes, the
latest-five index and complete five-family inventories, and run the full
`scripts/docs-site.sh check` (unit tests, content/diagram validation, facts,
release provenance, TypeScript, production build, and far-side rendered-link
checks). These existing checks catch loss of the current snapshot, invalid
provenance, stranded test samples, stale diagrams, and broken navigation.
Run selected committed-head batch-only lanes if the canonical classifier names
any; do not introduce a new gate or lower an existing threshold.

## Version Management

Version impact: none — this Task removes historical documentation copies from
HEAD under the existing retention policy; it allocates no identity and changes
no active manifest, Assembly, Contract, Host or Provider version.

## Documentation impact

Documentation impact: none — current Portal pages, source diagrams and projected
identities are unchanged. Only the historical version index and aged-out copies
change. Their historical Git revision remains available for audit.

## Remaining P1 scope

T8 still needs a newly allocated testing Build, its official immutable canary
snapshot, and complete selected integration proofs. A later retention-only Task
may remove the oldest prior snapshot after that new cut lands so HEAD again
contains the latest five; never widen or rewrite the candidate's closed snapshot
scope. Real-device, audible and lifecycle acceptance remains separately
unverified. This Task initiates no release, publication, deployment or Channel
promotion and does not complete the P1 issues.
