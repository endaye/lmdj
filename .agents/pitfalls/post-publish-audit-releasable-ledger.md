---
id: post-publish-audit-releasable-ledger
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/actions/runs/34017371873
    observed_by: grok-4.6
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/pull/1095
    observed_by: Codex
exit: gate:tests/build/release_publish_workflow_test.py
---

# A post-publish remote audit read canonical `main`'s still-`releasable` ledger against a GitHub Release that `publish-draft` had already published, so genuine publications exited red.

## Why

The intent ledger remains `releasable` until a later docs Pull Request records
`disposition: published`, while the live Release is already published. The
publish job now ends with `scripts/release.sh verify-published TAG RELEASE_ID
PLAN_SHA256`, which reads the live Release by numeric ID and avoids this
ledger-lag false negative. PR #1095 records the motivating evidence: eight
consecutive red `publish-release.yml` runs after genuine publication.

## How to apply

The enforcing gate is
`tests/build/release_publish_workflow_test.py`, which requires the publish job
to finish with numeric-ID `verify-published` rather than the lagging audit.
Deployment remains a separate authorization and is not inferred from
publication verification.
