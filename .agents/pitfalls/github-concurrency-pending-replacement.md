---
id: github-concurrency-pending-replacement
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/453
    observed_by: codex-gpt-5
exit: gate:tests/build/ci_build_acceleration_test.py
---

# GitHub's default concurrency group retains only one pending member, so a later workflow can cancel an older required check even when `cancel-in-progress` is false.

## Why

PR #453 put Linux `core-asan` and `core-coverage` in one repository-wide
concurrency group with `cancel-in-progress: false`. That protected the running
job, but each workflow still contributed two pending siblings. When post-merge
main CI and PR #444 CI overlapped, later arrivals replaced the older pending
member; both required `core-asan` checks were cancelled at the same instant.
This pending-replacement behavior is a GitHub platform rule, not something
derivable from the workflow's `cancel-in-progress` spelling.

## How to apply

Any required jobs sharing a concurrency group across workflow runs must set
`queue: max` as well as `cancel-in-progress: false`. The former retains every
pending member; the latter prevents a new member from cancelling the running
one. Keep the exact approved sites covered by deterministic workflow contract
tests, and retain the pinned actionlint exception until its schema understands
GitHub's `concurrency.queue` key.
