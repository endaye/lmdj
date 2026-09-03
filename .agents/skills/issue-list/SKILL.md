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
   gh issue list --state open --limit 50 --json number,title,labels,assignees
   ```
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

Two tasks in different streams can always be worked on simultaneously in separate git worktrees.

---

## Mode 2: Branch & Worktree Cleanup (`issue-list 清理` / `issue-list clean`)

When invoked with `清理` / `clean` / `prune` intent, perform a full workspace hygiene audit and clean up expired resources:

### Step 1: Discover Local Branches and Worktrees
Fetch remote updates and list all local resources:
```bash
git fetch origin --prune
git branch --list
git worktree list
```

### Step 2: Inspect State & Safety Matrix
For every local task branch and its corresponding worktree:
1. **Check Working Tree Cleanliness**:
   ```bash
   git -C <worktree-path> status --short
   ```
   > [!CAUTION]
   > **Never** delete a worktree or branch that contains uncommitted changes (`M`, `A`, `??`) without explicit confirmation.

2. **Inspect Remote Pull Request Status**:
   ```bash
   gh pr list --head "<branch-name>" --state all --json number,title,state,url,mergedAt
   ```

3. **Check Commit Equality with Main**:
   Check if the branch's commits are already squashed or integrated into `origin/main`:
   ```bash
   git cherry origin/main <branch-name>
   ```

### Step 3: Action Routing Matrix

| Resource State | PR State | Action |
| :--- | :--- | :--- |
| **Merged to main** | `MERGED` | **Safe to Clean**: Remove worktree (`git worktree remove <path>`) and delete local branch (`git branch -D <branch>`). |
| **Squashed in main** | Closed / Merged | **Safe to Clean**: If commit diff shows changes already landed in main, remove worktree and delete branch. |
| **Open PR (In-Flight)** | `OPEN` | **Keep & Report**: Check CI checks (`gh pr checks <pr-number>`). If green, inform user or proceed with auto-merge via `issue-done`. |
| **Unpushed / No PR** | None | **Evaluate**: If work is done and verified, offer shipping via `issue-done`. If abandoned / empty, delete upon confirmation. |
| **Dirty Working Tree** | Any | **Stop & Protect**: Do not delete; report uncommitted files to user. |

### Step 4: Execute Cleanup Operations
For all identified merged/obsolete resources:
```bash
# 1. Switch main repo to clean main branch
git checkout main
git pull origin main

# 2. Remove obsolete worktree(s)
git worktree remove <worktree-path>

# 3. Delete merged local branch(es)
git branch -d <branch-name>  # or git branch -D if squashed

# 4. Prune remote references
git fetch origin --prune
```

### Step 5: Summary Report
Print a clear markdown table showing:
- **Cleaned Resources**: Deleted worktrees and branches.
- **Active In-Flight Worktrees**: Worktrees with open PRs and their CI status.
- **Pending/Local Branches**: Branches requiring attention or `issue-done`.
