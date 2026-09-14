---
name: issue-list
description: Query, classify, and list open GitHub issues and pending project tasks by default, or audit, clean, and prune merged/expired local branches, worktrees, and check PR/issue statuses when invoked with cleanup intent (e.g. 'issue-list 清理', 'issue-list clean').
---

# Issue List (Open Task Triage & Branch/Worktree Lifecycle Management)

This skill enables coding agents (**Antigravity**, **Codex**, **Claude Code**, **Kimi**, **Cursor**, **GitHub Copilot**) and human contributors to:
1. **Default Mode (`issue-list`)**: Query open GitHub issues, cross-reference project task ledgers, classify tasks by readiness, and output actionable parallel workstreams.
2. **Cleanup Mode (`issue-list 清理` / `issue-list clean`)**: Audit all local branches and git worktrees, inspect associated PR and issue states, safely remove merged/obsolete worktrees and branches, and report active/in-flight tasks.

---

## Mode 1: Default Task Triage (`issue-list`)

When invoked without cleanup intent, list and triage open tasks:

### 1. Query GitHub Issues & Project Ledgers
1. **Query GitHub Live Issues**:
   ```bash
   gh issue list --state open --search '-label:"ci:storage"' --limit 1000 \
     --json number,title,labels,assignees
   ```
   `gh issue list` paginates its API requests up to `--limit`, but GitHub
   Search caps results at 1,000. Treat a result count of exactly 1,000 as
   truncated: do not call it complete or claim that no actionable work exists.
   Instead, use the complete REST fallback (which also excludes pull requests)
   and filter labels in the paginated stream:
   ```bash
   gh api --paginate --slurp \
     'repos/endaye/lmdj/issues?state=open&per_page=100' \
     --jq '.[][] | select(has("pull_request") | not) | select(([.labels[].name] | index("ci:storage")) == null) | {number,title,labels,assignees}'
   ```
   The default inventory excludes `ci:storage` journal/state issues. When a
   storage audit is explicitly requested, run a separate positive query with
   `--label "ci:storage" --limit 1000`, apply the same cap check and use the
   paginated REST fallback if capped, changing only the label predicate to
   `select(([.labels[].name] | index("ci:storage")) != null)`:
   ```bash
   gh api --paginate --slurp \
     'repos/endaye/lmdj/issues?state=open&per_page=100' \
     --jq '.[][] | select(has("pull_request") | not) | select(([.labels[].name] | index("ci:storage")) != null) | {number,title,labels,assignees}'
   ```
   Label the output as a storage audit.
   Never mutate journals or bulk-close those Issues. Keep the output concise
   and state whether it is a complete actionable inventory, an incomplete
   capped result, or the explicit storage audit.
2. **Cross-reference Project Task Ledgers**:
   - `docs/quality/2026-08-17-machine-task-todo.md` (Machine-executable tasks & blockers)
   - `docs/quality/2026-08-17-manual-verification-todo.md` (Human verification & decision gates)
   - `docs/prd/questions/` and `docs/prd/decisions/` (Architecture decisions)

### 2. Classification & Independence Rules
Categorize each task into one of four states:
1. **Ready Machine Tasks**: Concrete engineering tasks with no open design blockers. Can be implemented autonomously in isolated worktrees.
2. **Architecture / Question Issues**: Decision or Contract questions requiring a decision record under `docs/prd/decisions/` before implementation.
3. **Physical / Manual Verifications**: Tasks requiring real hardware (macOS Safari, iPadOS touch, physical MIDI, acoustic microphone tests).
4. **Blocked Tasks**: Blocked on a specific upstream decision gate (e.g. P2, F4, F6, D1-D5).

### 3. Identifying Parallel Workstreams
To avoid git merge conflicts and domain coupling, assign parallel tasks to distinct active source boundaries:
- **Stream A (Tooling, Release & Packaging)**: `scripts/`, `tools/release/`, `packaging/`
- **Stream B (Core & Provider SDK)**: `packages/authoring-domain/`, `packages/provider-sdk/`, `providers/`
- **Stream C (Creator Web & UI)**: `apps/creator-web/`, `packages/web-runtime-platform/`
- **Stream D (Architecture Decisions & Docs)**: `docs/prd/decisions/`, `docs/governance/`

Different streams are candidates for parallel work, not proof of independence.
Check declared files, shared routing/portal/generated inputs and producer/consumer
dependencies first; assign one owner per overlapping file and use isolated worktrees.

---

## Mode 2: Branch/worktree audit and authorized cleanup

A status question such as “哪些分支没 push / 没开 PR” is read-only. Audit does
not authorize push, PR creation, merge, closing/reopening Issues, or deletion.
Only an explicit cleanup request enables removal of resources proven safe below;
shipping requires separate applicable authorization and `issue-done`.

### 1. Discover and distinguish states

Read `git branch -vv`, `git worktree list --porcelain`, each exact worktree's
`git status --short`, and live PR metadata. Compare local HEAD with the actual
remote branch, not just the existence of an upstream configuration; say when
remote state could not be verified. A remote refresh updates local refs only;
do not push, change another worktree's branch, reset or pull over local work.

For each branch report separately: uncommitted changes, local commits not pushed,
remote branch existence, open/closed/merged PR, current PR head and review state,
and whether any later local changes remain outside the merged PR. No open PR
does not imply no remote branch or abandoned work.

### 2. Protect before classifying

Never remove dirty (including untracked), locked, active/in-use or ambiguously
owned worktrees. Ancestry and `git cherry origin/main <branch>` are useful
diagnostics but alone do not prove whole-patch retention after squash.
Verify the actual merged PR and compare the complete local change with its
landed patch; protect post-merge local commits not covered by that evidence.

| Observed resource | Response |
| --- | --- |
| Merged PR, complete local patch retained, clean and inactive worktree | Cleanup candidate only within explicit cleanup authorization |
| Closed PR without proven retained patch | Keep; closure is not delivery |
| Open PR | Report current-head review/findings, conflicts and applicable protection; no automatic merge |
| Unpushed commits or no PR | Report exact missing transition; offer shipping, do not execute it from an audit |
| Dirty, divergent, locked, active or uncertain | Keep and name the unresolved safety condition |

Being behind main without conflict, or having red/in-flight incremental or
explicit full self-tests, does not make a PR abandoned or unmergeable under
project policy. Daily product tests and daily-missing alerts are retired;
lightweight health ticks recover pending work, not date-based tests.
AI review failures need visible current-head takeover, not automatic approval.
An unmerged draft does not override live main governance or branch protection.
Report processed progress, selected results, unresolved failures and unexecuted
debt separately; docs-none or a later focused pass is not overall health.
Outbox unknown-write state needs receipt reconciliation, not blind Issue creation.
An audit grants no report retry, dispatch, protection change or Issue mutation.

### 3. Remove only verified, authorized targets

Operate from a different existing worktree without switching another session's
branch. Use a resolved exact path with non-forced `git worktree remove`, then
prefer `git branch -d <exact-branch>`. A squash-only `-D` requires prior proof
that every local change is retained and deletion is authorized. Never force
worktree removal or broaden a target to a workspace root. Remote branch deletion
is not implied by local cleanup. Do not run blind deletion loops.

Report what was removed, what remains and why. Listing/triage returns evidence
and next actions, not claims that a green check granted shipping authority.
