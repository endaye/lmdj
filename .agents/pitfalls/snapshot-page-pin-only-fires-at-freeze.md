---
id: snapshot-page-pin-only-fires-at-freeze
area: docs-governance
status: absorbed
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/pull/1024
    observed_by: unknown
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/commit/a9495e2ab618e91c5c9fbdbd1a24ddeb41141a32
    observed_by: Codex
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/commit/692ac4837ce79c9681fed81d06eedfac9ee84f5c
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

K3 added a 44th current page after K2 froze 43. During review, the verifier
was found to reuse the current freeze pin for historical archives. Bind old
archives to the complete inventory at their recorded source revision instead;
retain the independent current-tree pin for new freezes. The same test suite
now verifies historical acceptance and rejection of a removed inventory entry.
