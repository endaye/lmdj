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
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1766
    observed_by: kimi-code
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

The advisory warning is replaced by a merge obligation (#1619, owner's choice
of option 1). The Pull Request body records every `batch_only` lane under
`## Batch-only Lanes` as `- <lane>: pass key=<64 hex>`, pasted from the block a
passing `scripts/local-ci.sh --lanes <lanes>` run prints, or as
`accepted-risk key=<64 hex> — <reason>` the owner explicitly accepted for those
inputs. The `issue-done` merge
procedure runs `scripts/local-ci.sh --batch-evidence-only --pr-body <body>` on a
clean checkout of the exact head. It refuses a missing, extra, stale or
malformed lane, and the key binds the evidence to the lane's inputs, so an
input edit after the run makes it stale. `BatchOnlyEvidenceTest` in
`tests/build/ci_local_preflight_test.py` pins the lane set, staleness,
`accepted-risk`, `none`, the clean-tree requirement, and that `--lanes` cannot
shrink the obligation. It is a procedure check, not a required status: it
catches "never ran", not a fabricated line.

#1766 edited Pattern events through the Facade and Web Host, wrapping an
already-`Result` return in a second `Result::success` and adding
`"pattern.events.edit"` to `bridge.cpp`'s supported-operation list without
growing its `std::array` size. No Pull Request lane compiles
`packages/authoring-domain` or `packages/web-runtime-platform`, so both breaks
reached `main` together and stopped every native and Emscripten build; an
unrelated Creator Task tripped over them while building its own lane. A compile
break is the cheapest case for the batch-evidence obligation: the owning lanes
fail in seconds, so run them locally before merge instead of discovering the
red from someone else's Task.
