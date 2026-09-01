---
id: portal-impact-two-dot-base-diff
area: ci-release
status: open
recurrences:
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/527
    observed_by: claude-fable-5
exit: none
---

# The portal impact gate diffs `PORTAL_BASE_SHA..PORTAL_HEAD_SHA` two-dot, so a branch behind `main` inherits every portal page merged after its base as "changed by this PR" and a truthful `Documentation impact: none` fails.

## Why

`PORTAL_BASE_SHA` comes from the `pull_request` event's `base.sha`, which is
the tip of `main` at event time, not the merge base. `git diff A B` (two-dot)
compares the trees, so commits that landed on `main` after the branch was cut
appear in the diff in reverse. On PR #527 a four-file `docs/superpowers/**`
branch based two commits behind `main` was blamed for the
`apps/architecture-portal/docs/**.mdx` pages that #521 had merged in the
meantime, and `check:impact` failed with "documentation impact is none but
current portal pages changed" — a message that points at the PR's own edits
and never mentions base drift.

## How to avoid

Before pushing a PR that declares `Documentation impact: none`, rebase the
branch onto current `origin/main` (or verify
`git diff --name-only origin/main HEAD` contains only the Task's files). If
the gate fails with "portal pages changed" that the branch never touched,
the fix is a rebase and force-with-lease push — not changing the declaration
to `required`. A durable fix would be diffing against `git merge-base` (or
three-dot `...`) in the portal workflow; that change needs its own Task.
