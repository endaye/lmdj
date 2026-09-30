---
id: web-proofs-share-destructive-build-root
area: ci-release
status: open
recurrences:
  - date: 2026-09-30
    occurrence: https://github.com/endaye/lmdj/issues/1659
    observed_by: Codex
exit: none
---

# Run the three Web proof lanes sequentially within one worktree because their build roots overlap.

## Why

`web-toolchain-conformance.sh proof` removes the entire owned `build/web` tree.
Creator and Runtime Host keep their builds and served distributions below that
tree, and Runtime Host also uses the toolchain's formal-audio fixtures. Different
lane names and separate log files do not make their filesystem mutations independent.
During #1659, starting the toolchain proof removed the packaged Creator files
while its test server was still running. The browser then displayed an empty page;
that observation did not describe the committed product.

## How to apply

Within one worktree, finish `web_toolchain`, then run `web_runtime_host` and
`creator` sequentially. Alternatively use distinct isolated worktrees with their
own build trees. Stop only owned overlapping runs; preserve their logs as failed
or interrupted evidence. Restart a static server after replacing its distribution,
and rerun every affected journey from a fresh browser context. Never relax an
assertion or treat an interrupted run as a pass.

A cross-process ownership guard would need to coordinate all three entry points
and their shared fixture consumers. That mechanism belongs in a separate tooling
Task; this first occurrence records the scheduling constraint without adding a
product gate or changing the current proof contract.
