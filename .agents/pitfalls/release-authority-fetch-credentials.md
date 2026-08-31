---
id: release-authority-fetch-credentials
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/issues/331
    observed_by: claude-code/fable-5
  - date: 2026-08-31
    occurrence: https://github.com/endaye/lmdj/issues/491
    observed_by: Codex
exit: gate:tests/build/release_prepare_test.py
---

# Canonical release fetches need an explicit credential everywhere the operator's keychain is absent

## Why

The repository is private, and the release tooling's `fetch_authority`
(`tools/release/git_repository.py`) fetches `https://github.com/endaye/lmdj.git`
with whatever credential git resolves. On an operator machine the OS keychain
answers silently, so `scripts/release.sh` appears to need nothing — but the
GitHub API client only reads `GITHUB_TOKEN`, so a local remote audit without
`GITHUB_TOKEN` exported fails with a misleading `external-error` (the audit's
broad exception handler hides the real `GitHubApiError`). On a hosted runner
there is no keychain at all: the pipeline design (spec §10.3) mandates
`persist-credentials: false`, so every `publish-release.yml` run failed at
preflight with `Git release authority command failed` before any verification
ran, and nothing distinguished this from a real authority conflict. The
pipeline had never been exercised end-to-end against a private repository, so
its first real publication (lmdj-v1.0.36.0) was the discovery.

## How to apply

- Operator machines: authenticate `gh` once. Release commands use a non-empty
  `GITHUB_TOKEN` when explicitly provided and otherwise read the current
  `gh auth token`; they fail closed when neither source provides a credential.
- Workflows: keep `persist-credentials: false` and scope the job's own
  `github.token` to the steps that fetch, via environment-only git config
  (`GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0=url.….insteadOf`), never by
  persisting a credential to disk. `publish-release.yml` and
  `release-audit.yml` carry the pattern and their contract tests assert it.
- When an audit reports `external-error` with `incomplete sources: git-remote,
  github-api`, check for a missing or unauthorized token before suspecting the
  remote projection itself.
- `tests/build/release_prepare_test.py` exercises the real Authorization header
  boundary with an empty environment token and a logged-in `gh` credential.
