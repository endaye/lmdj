---
id: fresh-shell-cwd-mutates-shared-main
area: docs-governance
status: open
recurrences:
  - date: 2026-10-12
    occurrence: https://github.com/endaye/lmdj/pull/2039
    observed_by: kimi-code-cli
exit: none
---

# An agent shell call starts a fresh shell at the session's default workspace root, so a mutating git command issued without an explicit `cwd` lands on the shared protected-`main` checkout and renames its branch instead of the task worktree's.

## Why

Agent shell tools do not preserve the working directory between calls: every
invocation starts a fresh shell at the session's default root. In this
repository that root is the shared checkout of protected `main`
(`/Users/endaye/Projects/lmdj`), whose branch identity other sessions and
local tooling rely on.

While shipping the #2034 fix from an isolated Orca worktree
(2026-10-12, PR #2039), the agent renamed the task branch with
`git branch -m fix/report-template-replan-compatibility` but omitted `cwd`.
The command therefore ran in the shared checkout and renamed **its** `main`
branch. The call's own output looked like success — `git branch --show-current`
printed the new name — because it was reading the wrong repository, and the
task worktree silently kept its original Orca-assigned branch name. The mistake
surfaced only when a later commit in the task worktree reported the old branch
name. Recovery renamed the shared checkout's branch back to `main` (verified
HEAD and clean status) and renamed the branch inside the task worktree with an
explicit `cwd`; no file content was ever modified.

The same blind spot applies to any state-changing command — test runs, builds,
`git checkout`, `git clean` — issued for one worktree but executed in another:
the command can succeed against the wrong tree and even print confirming output
taken from that wrong tree.

## How to apply

- Pass an explicit `cwd` (tool parameter) or `git -C <path>` on **every**
  command that touches a worktree, including the first one after creating or
  entering it. Never rely on a previous call's directory.
- Before a mutating git command, prove the target in the same invocation
  (`git rev-parse --show-toplevel` / `git branch --show-current`) and read the
  output; a successful exit code alone does not say which repository ran.
- Treat the shared `main` checkout as read-only for task work: no branch
  renames, switches, commits, builds or test runs there. Task branches live in
  isolated worktrees.
- After any recovery, verify both sides: the shared checkout (branch name,
  HEAD, clean status) and the task worktree (intended branch and base).

This entry stays `open` with `exit: none`: the invariant (every worktree
command carries an explicit directory) is settled, but no deterministic gate
can inspect arbitrary agent shell invocations before they run, and the
enforcement point is the checklist above rather than a product-code test.
