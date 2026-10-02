---
id: batch-key-omits-executed-host-test
area: ci-release
status: open
recurrences:
  - date: 2026-10-03
    occurrence: https://github.com/endaye/lmdj/pull/1808
    observed_by: Codex
exit: none
escalation: none
---

# A batch-only lane key can omit a test that the lane actually executes.

## Why

In #1808, `core_coverage` executed `host.native_source_boundary` and failed
because `tests/host/native_host_source_boundary_test.py` still pinned Facade
6.5.0 after the manifest advanced to 6.5.1. The precise assertion was corrected;
neither the assertion nor the test was removed.

`local_preflight.lane_input_paths` nevertheless excludes that Python file from
both `core_coverage` and `core_asan`. Their content keys stayed unchanged across
`efa63cd8` → `8d67bbda`; `core_macos` and `core_ubuntu` keys changed. Both Linux
lanes execute this Host test through their full CTest selection. Input grouping
by path ownership is therefore narrower than those commands' actual reads.
A matching key alone cannot prove that a changed test was rerun. This occurrence
found a failed run, not an observed false pass.

## How to apply

When a failing lane names a file, verify that file belongs to the lane's key
inputs before accepting a cached pass after a correction. For an omitted input,
run the entire affected lane with `--no-cache` on the corrected committed tree
and retain the head and complete result in the PR, in addition to its key.
Do not skip the test or widen timeouts. Fixing the CI input closure belongs in a
separate control-plane Task; this record does not authorize changing it while
shipping a product Task.
