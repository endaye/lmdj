---
id: local-ci-list-names-batch-lanes
area: ci-release
status: open
recurrences:
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/pull/1490
    observed_by: Claude Opus 5
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/pull/1492
    observed_by: Claude Opus 5
  - date: 2026-09-27
    occurrence: https://github.com/endaye/lmdj/pull/1550
    observed_by: claude-code/opus-5.5
  - date: 2026-09-27
    occurrence: https://github.com/endaye/lmdj/pull/1581
    observed_by: claude-code/opus-5.5
  - date: 2026-09-28
    occurrence: https://github.com/endaye/lmdj/pull/1614
    observed_by: claude-code/opus-5.5
  - date: 2026-09-28
    occurrence: https://github.com/endaye/lmdj/pull/1576
    observed_by: claude-code/opus-5.5
  - date: 2026-09-28
    occurrence: https://github.com/endaye/lmdj/pull/1621
    observed_by: claude-code/opus-5.5
exit: gate:tests/build/ci_local_preflight_test.py
escalation: https://github.com/endaye/lmdj/issues/1619
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

The warning is advisory, and it did not stop two later merges. #1550 broke three
Chromium realtime transport journeys (`web_runtime_host`, `web_toolchain`).
#1581 changed owner-lost recovery semantics, and
`packages/web-runtime-platform/test/control_runtime_test.cpp` plus the Creator
owner-loss journey kept asserting the old refusal (`core_asan`,
`core_coverage`, `core_macos`, `creator`). Both stayed red on `main` for a week
and blocked every complete candidate. When a behavior change reaches Core
Module source, search every lane's tests for the old assertion, not only the
module's own tests.

#1614 added a `postinstall` script to `tests/platform/web/package.json`.
`tests/platform/web/toolchain/toolchain_identity_test.py` pins that file
exactly, but it runs only in the batch-only `web_toolchain` lane, so the
first complete candidate after the merge failed at its identity step. The
advisory exit has now failed four times. The entry is reopened, and
[#1619](https://github.com/endaye/lmdj/issues/1619)
owns choosing a replacement mechanism.

#1576 sorted the overdub journey's committed events by Pad, but the stop and
reopen legs of `creator_web_sequence.spec.mjs` kept comparing position-ordered
truth with that sorted copy. They fail whenever the presses straddle the loop
boundary, and only the batch-only `creator` lane runs them.

#1621 raised the `web-runtime-host`, `creator-web` and `web-runtime-platform`
module versions. `tests/conformance/module_graph_test.py` pins all three and
runs only in the batch-only Core lanes, so `core_asan`, `core_coverage`,
`core_macos` and `core_ubuntu` went red on the next complete batch. A version
bump must search every pinned copy of the old version, not only the manifests
it edits.
