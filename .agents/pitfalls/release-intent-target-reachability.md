---
id: release-intent-target-reachability
area: ci-release
status: open
recurrences:
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/pull/328
    observed_by: claude-code/fable-5
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/issues/331
    observed_by: claude-code/fable-5
exit: none
---

# Allocated release intents can target commits no branch or tag reaches, and long-lived runner workspaces mask it

## Why

An allocated intent in `docs/release-evidence/release-intents.json` may record
a pre-squash `target_revision` whose branch was deleted after merge, so no
advertised ref reaches it. A fresh full clone (`fetch-depth: 0`) therefore
lacks the object, and the repository-local release audit correctly reports the
intent unverifiable — but only on machines without workspace residue.
Long-lived runner `_work` checkouts accumulate objects across runs, so the
Deploy contract lane passed for weeks on established runners and failed the
first time an elastic runner with a fresh workspace picked it up (PR #328,
`lmdj-v1.0.25.0`, target `349a834f`). The failure signature depends on which
machine takes the job, not on the change under test, and the same trap awaits
any operator running `scripts/release.sh audit --local` from a fresh clone.

## How to apply

- GitHub serves these objects when fetched by SHA; hydrate explicitly instead
  of relying on workspace history. The Deploy contract lane now does this in a
  dedicated step before the release test suite (`.github/workflows/ci.yml`).
- When a release audit reports an intent target absent from the local object
  store, first `git fetch --no-tags origin <sha>` before treating the intent
  as inconsistent.
- `release-audit.yml` and both `publish-release.yml` jobs now hydrate the same
  way before invoking `scripts/release.sh`, and their workflow contract tests
  assert the hydration step runs first
  (`tests/build/release_audit_workflow_test.py`,
  `tests/build/release_publish_workflow_test.py`).
- No gate exit yet: reachability cannot be asserted repo-statically (it is a
  property of the remote), and the audit tool's own fetch-on-miss behavior is
  a release-tooling decision that should not be settled inside an unrelated
  Task. The recurrence-2 escalation is
  [#332](https://github.com/endaye/lmdj/issues/332): decide fetch-on-miss
  hydration inside the release tooling instead of per-workflow copies.
