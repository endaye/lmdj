---
id: worktree-checkout-flattens-symlinks
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/commit/cdeb4c3e7f417e1bf17b5266f98f26d86376052a
    observed_by: Codex
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/issues/1037
    observed_by: Codex
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A Linux worktree inheriting `core.symlinks=false` can be Git-clean while tracked directory links are unusable regular files.

## Why

During canary-design verification, a new `/tmp` worktree of the linked baseline
inherited `core.symlinks=false` from the shared repository configuration.
Git's index recorded `apps/docs-site/versioned_docs` and five other docs-site
links as mode `120000`, but checkout wrote their target strings into regular
files. The Portal suite reported 85 passes and one `ENOTDIR` failure when it
opened a historical snapshot below `versioned_docs`. This is a reproduction at
the linked baseline, not a claim that that commit introduced the Git setting.

After restoring only those six pristine links with a command-local
`core.symlinks=true` checkout, the same suite passed all 86 tests without any
tracked source or test changes. A clean status alone had not proven a usable
filesystem layout. Changing shared Git configuration would also affect other
active worktrees and is not an appropriate implicit repair.

## How to apply

- Before interpreting `ENOTDIR` or missing snapshot paths as product drift,
  inspect `git config --get core.symlinks`, index modes from `git ls-files -s`,
  and the actual file types at the named paths.
- On a filesystem supporting links, prefer creating the task worktree with
  command-local `git -c core.symlinks=true worktree add ...` when appropriate.
- For an existing owned worktree, first verify the exact affected paths are
  pristine. Restore only those validated paths with command-local
  `git -c core.symlinks=true checkout-index --force -- <exact paths>`; never
  overwrite user edits, broadly re-checkout the tree, or change shared config.
- Rerun the original failing check and retain its full result. Do not replace
  links with copied snapshot trees or weaken the snapshot assertions.

The shipping skill now requires checking tracked link modes against actual
filesystem types before interpreting these path failures, and prescribes a
pristine, command-local repair. K5 encountered the same ENOTDIR failure in its
isolated Linux worktree; restoring the unchanged tracked links made the
historical snapshot test pass. This skill exit grants no cleanup authority.
