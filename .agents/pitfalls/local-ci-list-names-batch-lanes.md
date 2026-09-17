---
id: local-ci-list-names-batch-lanes
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/pull/1490
    observed_by: Claude Opus 5
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/pull/1492
    observed_by: Claude Opus 5
exit: gate:tests/build/ci_local_preflight_test.py
---

# `scripts/local-ci.sh --list` names lanes a Pull Request never runs, so a change owned by one of them is unverified at merge.

## Why

`--list` reported every lane the change-scope classifier selects, which reads
like "these lanes will verify this Pull Request". Only the lanes
`pr-contract.yml` gates on actually run there; the rest live in the
`workflow_call`-only `ci.yml` and wait for an admitted main batch. #1490 and
#1492 changed `tools/release/`, owned by `deploy_contract`, and broke `main`
with no Pull Request check able to catch it.

## How to apply

The pre-flight now derives the Pull Request lane set from `pr-contract.yml`
itself and splits `selected` into `pull_request_verified` and `batch_only`,
warning on any batch-only lane. Run those lanes locally before pushing:

```bash
scripts/local-ci.sh --lanes deploy_contract
```

`PullRequestLaneVisibilityTest` in
`tests/build/ci_local_preflight_test.py` holds the derivation, the partition and
the fail-closed empty set when the workflow cannot be read.
