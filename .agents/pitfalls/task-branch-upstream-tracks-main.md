---
id: task-branch-upstream-tracks-main
area: docs-governance
status: absorbed
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/commit/eb09b2c25b0ceeed01d6ef788f075e62695e433a
    observed_by: Claude Code (Opus 5)
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A task branch created from `origin/main` inherits `origin/main` as its upstream, so any tool that "syncs to upstream" pushes the Task straight to `main` without a Pull Request.

## Why

`git checkout -b <task> origin/main` (and depending on `branch.autoSetupMerge` or explicit flags, `git worktree add -b <task> origin/main`) sets the new branch's upstream to `origin/main` — git prints
`branch '<task>' set up to track 'origin/main'` and moves on. Nothing in the
Task workflow reads that line again. A bare command-line `git push` is saved
by `push.default=simple`, which refuses when the local and upstream names
differ; IDE and GUI "sync" actions are not, because they push
`<local>:<upstream>` explicitly after pulling.

On 2026-09-07 the `docs/minimization-principle` worktree carried one verified
local commit, `a7c658c6`, reported to the user as "not pushed". At 17:13Z a
`pull --rebase=false origin --prune --tags --progress` — the flag shape of an
IDE sync, not a typed command — merged `main` into the branch as `eb09b2c2`,
and at 17:14Z that merge commit landed on `origin/main` directly. No remote
task branch ever existed, so `gh pr list --head <branch>` was empty; the only
tell was `git status -sb` reading `[behind 5]` with zero commits ahead. The
content was correct, but it bypassed the Pull Request body declaration, the
body lint, current-head review, and squash merge, and left a two-parent merge
commit in an otherwise squash-linear `main`.

The push succeeded because `main` protection had `enforce_admins: false`, so
the owner's push was exempt from the Pull Request requirement. That flag was
enabled on 2026-09-08 as the second layer; this entry is the first, because
protection only refuses the push after the wrong upstream has already been
relied on, and a non-admin collaborator's push would fail with an error rather
than an explanation.

Two further local branches (`feat/673-stage11-assembly`,
`feat/move-chameleon-to-demos`) carried the same upstream and were reset with
`git branch --unset-upstream` on 2026-09-08. The hazard is per branch and
recurs every time a branch is created this way.

## How to apply

Create task branches without inheriting the base as upstream, and verify the
upstream before any push:

```bash
git worktree add --no-track .worktrees/<task> -b <prefix>/<task> origin/main
git rev-parse --abbrev-ref --symbolic-full-name @{upstream}   # must fail, or name origin/<prefix>/<task>
git push -u origin "$(git branch --show-current)"              # first push sets the same-named upstream
```

If `@{upstream}` resolves to `origin/main` on an existing branch, run
`git branch --unset-upstream` before doing anything else in that worktree. The
pre-push step in `.agents/skills/issue-done/SKILL.md` §4 carries this check;
`docs/governance/git-workflow.md` §3 names `--no-track` at task start.
