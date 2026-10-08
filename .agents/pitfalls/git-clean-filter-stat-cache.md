---
id: git-clean-filter-stat-cache
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-08
    occurrence: https://github.com/endaye/lmdj/issues/1873
    observed_by: Codex GPT-6
exit: gate:tests/build/release_candidate_snapshot_test.py
---

# Disabling Git clean filters does not invalidate stat data cached by an earlier filtered diff.

## Why

A filtered `git diff` can compare replaced bytes through a clean filter that
returns the committed blob, report no change and refresh the index stat cache.
A later invocation with filters disabled can then report no change without
reading the file. Whether the entry is racy changes this observation, so the
snapshot test's requirement that the second diff be non-empty failed under
load. The production raw-byte check correctly refused the replacement.

## How to apply

Keep trusted source verification against raw filesystem bytes and committed
objects; disabling filters alone is not a raw-byte proof. The snapshot safety
regression sets the replacement's mtime well before the index write, primes the
cache through the actual clean filter, and verifies snapshot refusal while
both Git observations appear clean. It also checks that the replacement never
executes and that command history does not advance. Do not fix this fixture
with a sleep or replace the raw-byte refusal with a Git-diff assertion.
