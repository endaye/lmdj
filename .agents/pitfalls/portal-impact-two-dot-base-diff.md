---
id: portal-impact-two-dot-base-diff
area: ci-release
status: open
recurrences:
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/527
    observed_by: claude-fable-5
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/530
    observed_by: claude-opus-5
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
the fix is to bring the branch up to date — not changing the declaration to
`required`.

`gh pr update-branch <n>` is the cheapest remedy: it merges current `main`
into the branch server-side, needs no force push, and emits the `synchronize`
event the gate requires anyway, because the gate reads the PR body from the
frozen event payload and `gh run rerun` reuses the stale one. A local rebase
plus force-with-lease works too. Note the PR object can lag the branch tip by
a minute after `update-branch`; read `.head.sha` back before concluding the
event did not fire.

The durable fix — diffing against `git merge-base` or three-dot `...` in the
portal workflow — is escalated to #531 at recurrence 2. It meets the gate
admission criteria, so the entry stays `open` only until that Task lands.

Recurrence 2 (PR #530) was a single-file `docs/research/**` change blamed for
five portal pages merged by #527 and #529 while the branch sat behind `main`;
the same PR had already passed `scripts/local-ci.sh`, which does not model the
gate's base SHA and so cannot catch this locally.
