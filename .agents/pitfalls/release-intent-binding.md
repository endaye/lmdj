---
id: release-intent-binding
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-16
    occurrence: https://github.com/endaye/lmdj/pull/180
    observed_by: unknown
  - date: 2026-08-20
    occurrence: https://github.com/endaye/lmdj/pull/201
    observed_by: unknown
  - date: 2026-08-22
    occurrence: https://github.com/endaye/lmdj/pull/260
    observed_by: unknown
exit: gate:tests/build/release_audit_test.py
---

# A release intent bound before the squash names a SHA that never reaches `main`, so the target is invalid the moment the Pull Request merges.

## Why

Squash merging rewrites the branch head into a new commit. An intent authored
against the branch SHA, or against a pre-squash merge preview, points at an
object that is not a protected-main ancestor. Four intents were bound this way
across three Pull Requests before the mechanism changed: the Stage 8 and
Stage 8b intents were rebound together in #180, Product Build 1.0.24.0 in #201,
and only then did #260 separate Product Build allocation from intent
authorization so that zero current intents is a valid state during the
allocation window.

## How to apply

Allocate the Product Build and its immutable snapshot first; they require no
intent. Create the release intent only after the exact protected-main squash
SHA exists, and bind it to that SHA. Zero or one current Product intent is
valid; duplicates fail closed. `tools/release/target_validation.py` and the
assertions in `tests/build/release_audit_test.py` now enforce this, so a
pre-squash target is rejected rather than discovered later.
