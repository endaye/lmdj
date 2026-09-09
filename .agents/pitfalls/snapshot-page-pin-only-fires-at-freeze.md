---
id: snapshot-page-pin-only-fires-at-freeze
area: docs
status: absorbed
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/pull/1024
    observed_by: unknown
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/commit/a9495e2ab618e91c5c9fbdbd1a24ddeb41141a32
    observed_by: Codex
exit: gate:apps/docs-site/test/snapshot-provenance.test.mjs
---

# A completeness pin checked only during rare freezing lets ordinary page additions block the next Build.

## Why

The source comment records the earlier 39-to-41 repair after #1024 added Host
changelogs. K1 #1049 added two Contract pages without moving the same pin;
K2's first freeze then failed with 43 actual pages and a 41-page expectation,
after creating partial snapshot files. Product code cannot reveal this ordering.

## How to apply

Keep the independent completeness pin aligned with the active page inventory
in the page-adding Task. The ordinary Portal test now checks the current tree,
including untracked pages, and names the repair before a rare freeze is tried.
After a failed freeze, preserve or remove only its exact generated partial
outputs, restore its versions-list mutation, and rerun the official generator
from clean committed source. Never hand-author the missing snapshot metadata.
