---
id: macos-fixture-transfer-adds-appledouble
area: ci-release
status: open
recurrences:
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/pull/1716
    observed_by: Codex
exit: none
---

# A macOS tar fixture transfer can add ignored AppleDouble files that break exact corpus verification on Linux.

## Why

The #1716 Linux verification checkout received materialized LFS fixtures through
macOS tar. Extended attributes became 131 `._*` files on extraction. Git status
was clean because those files are ignored, but `provider.slice_evaluation_corpus`
and `fixtures.soundset_corpus` correctly refused undeclared fixture bytes.
The committed fixtures themselves had not changed.

## How to apply

Prefer Git LFS materialization on the verification host. When a fixture transfer
is necessary, disable macOS metadata with `COPYFILE_DISABLE=1 tar --no-xattrs`
and inspect the archive inventory before extraction. Check the actual corpus,
not only Git status. If an owned transfer added metadata, first prove each
`._*` path is untracked and move only those files outside the checkout; preserve
the failed logs and rerun the complete affected lanes. Never weaken the corpus
inventory checks or clean another session's files.

This first occurrence remains open: ad hoc cross-host fixture transport has no
repository-owned entry point in which to enforce metadata exclusion.
