---
id: shared-host-tmp-staging-permissions
area: ci-release
status: open
recurrences:
  - date: 2026-10-11
    occurrence: https://github.com/endaye/lmdj/issues/1996
    observed_by: Codex
exit: none
---

# An isolated worktree does not isolate host staging under the system temporary directory.

## Why

The first native quick run for #1996 passed 204 of 205 tests but failed
`project_io.authoring_history` at its sample import assertion. Product sources
and that test were unchanged. A separately compiled diagnostic retaining the
assertion exposed `Permission denied` while creating
`/tmp/.lmdj-host/sample-staging/20000000-0000-4000-8000-000000000100`.
Both parent directories were owned by root with mode 0755. Repository isolation
could not make that shared host directory writable by the invoking user.

## How to apply

Inspect the actual error and ownership before calling an import assertion a
product regression. On this Linux permission failure, use an owned temporary
directory via `TMPDIR` and rerun the original complete selected tier. Retain the
failed result and the rerun's status. Do not remove, chown or chmod another
session's staging data, and do not skip the failing test.

This is not a remedy for macOS ASan fork failures: changing the temporary path
can change their allocation layout; follow `asan-macos-fork-child-stack-depot-boundary`
for that distinct failure. A universal temporary-root wrapper is not introduced
here because entry points and tests have different artifact-retention needs.
