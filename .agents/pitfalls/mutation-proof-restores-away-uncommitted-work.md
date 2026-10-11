---
id: mutation-proof-restores-away-uncommitted-work
area: core
status: open
recurrences:
  - date: 2026-10-11
    occurrence: https://github.com/endaye/lmdj/issues/1822
    observed_by: Kimi Code (k3)
exit: none
---

# Running a mutation/revert proof on uncommitted implementation work lets the restore step delete the work itself

## Why

A mutation proof edits a source file, rebuilds, watches the assertion fail,
then restores. When the implementation under proof is still uncommitted, the
file's committed version does not contain the day's work. Restoring with
`git checkout -- <path>` (or `git stash`/`git restore` against the index)
returns the file to the *base* version — wiping not just the mutation but the
entire uncommitted implementation. The subsequent "fixed tree green" run then
proves nothing, and the work must be reconstructed from scraps. The defect is
a process-ordering invariant: the restore primitive's source of truth (the
index/HEAD) does not match the proof's intent (the pre-mutation working
state), and nothing in the product code reveals the mismatch.

## How to apply

Before any mutation/revert proof on a tree carrying uncommitted work, snapshot
the *working* file (plain `cp` to a side path), apply the mutation on top, and
restore from that snapshot — never from git. Prefer committing the
implementation first so `git checkout --` means what the proof assumes.
Restore single hunks, not whole files, when only one hunk was mutated. After
any restore, re-verify the full owning suites on the rebuilt artifact and diff
the restored file against the pre-mutation snapshot before recording GREEN.
No eligible gate exists yet: whether a tree is "clean enough for a git-based
restore" is session state a deterministic check cannot see, so this remains a
skill-level discipline.
