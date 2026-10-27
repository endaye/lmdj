---
id: portal-snapshot-retention-unenforced
area: docs-governance
status: absorbed
recurrences:
  - date: 2026-09-14
    occurrence: https://github.com/endaye/lmdj/pull/1310
    observed_by: deepseek-v4-flash
  - date: 2026-10-27
    occurrence: https://github.com/endaye/lmdj/pull/2511
    observed_by: claude-opus-5-5
exit: gate:apps/docs-site/test/version-docs.test.mjs
---

# A Portal snapshot retention rule with no enforcer lets frozen snapshots accumulate silently, because the only writer of snapshots — the candidate cut — may add paths but never delete them.

## Why

#1310 pruned 51 snapshots to five and wrote "keep the latest five" into
`docs/governance/architecture-portal.md`, but added no check. Every later
Product Build was frozen by the one-click candidate cut, whose path guards
(`tools/release/candidate_cut.py`, `candidate_snapshot.py`) admit only the
new Build's own snapshot paths plus `versions.json`. A cut therefore cannot
prune, no other Task owned pruning, and every existing gate validates only
the current Build's snapshot. Six weeks later HEAD carried 37 snapshots
(about 370k lines), with every gate green.

## How to apply

Absorbed by `validateSnapshotRetention` in
`apps/docs-site/scripts/lib/version-docs.mjs`, run by `check:release-docs`
and covered by `apps/docs-site/test/version-docs.test.mjs`. It fails when
more than five snapshots are retained besides the current Product Build,
or when a storage class disagrees with `versions.json`. When it names
excess Builds, prune them in an ordinary Task, not inside a candidate cut.
Remove all five storage classes and the `versions.json` entries together.
