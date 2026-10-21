---
id: cleanup-removes-live-release-state
area: ci-release
status: absorbed
recurrences:
  - date: 2026-10-15
    occurrence: https://github.com/endaye/lmdj/pull/2275
    observed_by: unknown
  - date: 2026-10-16
    occurrence: https://github.com/endaye/lmdj/pull/2310
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-17
    occurrence: https://github.com/endaye/lmdj/pull/2311
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-21
    occurrence: https://github.com/endaye/lmdj/issues/2422
    observed_by: Claude Fable 5.1
exit: skill:.agents/skills/issue-list/SKILL.md
---

# A branch/worktree cleanup treats the release driver's live per-request worktrees as stale and removes them, killing an in-flight release request.

## Why

`scripts/release.sh` keeps each request's live state in
`.local/release-worktrees/<request>/` (candidate-source, candidate-witness-task,
allocate-*, witness-* worktrees), their `.git/worktrees/candidate-*`
registrations, and the journal in `.git/lmdj-release-requests/`. These worktrees
sit on branches whose PRs are already merged, so a generic "clean merged or
expired worktrees" pass classifies them as obsolete.

The 2.0.102.0 candidate was lost when the owner cleaned worktrees on or after
2026-10-15 (recorded under its allocation day; the exact removal time and
agent were not observed first-hand). On 2026-10-16 15:12Z and 2026-10-17
14:04-14:05Z the coordinating Claude Code (Opus 5.5) session's deletion guard
observed an Antigravity session, asked by the owner to "更新 repo，并清理过期分支和
worktree", run `git worktree remove .local/release-worktrees/...` (process chain
`agy --dangerously-skip-permissions` -> python). The first removal killed the
2.0.108.0 request; the second removed everything under
`.local/release-worktrees/`, including the directory.

The same kind of sweep removed `build/toolchains/emsdk` during the 2.0.122.0
release (#2422, phase E): the first `prepare` rounds failed with "EMSDK is not
configured" and the cause was only visible after three resumes. The toolchain
is not request state and no `scripts/release.sh` path regenerates it; it was
simply outside the protected list. `build/release/<tag>/` carries the same
exposure: it is the signed plan and asset set every later step verifies.

## How to apply

Follow issue-list Mode 2 "Protect before classifying": never remove, delete or
prune release-owned paths — `.local/release-worktrees/`,
`.git/worktrees/candidate-*`, `.git/lmdj-release-requests/`,
`build/toolchains/` and `build/release/`; report them as "release-owned,
kept"; do not run `git worktree prune` while
`ls .git/lmdj-release-requests/*.json` shows a non-retired request; let
`scripts/release.sh` settle or `retire` the request. Never sweep `build/`
whole; remove only the specific lane trees you own. `scripts/release.sh
doctor` names a missing or drifted toolchain with its reinstall command. On
the operator host, keep the pinned emsdk outside the repository (any path,
exported as `EMSDK`; every Web entry point and the doctor honour it) so no
repository sweep can reach it. Check for running processes before removing any
other agent's `.worktrees/*` worktree.
