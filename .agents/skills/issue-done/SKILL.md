---
name: issue-done
description: Universal skill for shipping a completed local task/issue to main - handles verification, Conventional Commit, push, PR creation with governance declarations, CI tracking, auto-merging, and local worktree/branch cleanup.
---

# Issue Done (Local Issue/Task → Main & Cleanup)

This skill defines the canonical, universal workflow for taking a locally completed GitHub issue/task in an isolated worktree branch, verifying it, creating a Conventional Commit, pushing, opening a Pull Request, waiting for CI / auto-merging into `main`, and cleaning up the branch and worktree.

Compatible with: **Antigravity (AGY)**, **Codex / OpenAI**, **Claude Code**, **Kimi**, **Cursor**, **GitHub Copilot**, and human contributors.

---

## 1. Prerequisites & Verification Check

Before starting the shipping pipeline:

1. **Verify Task Branch**: Confirm you are on a short-lived task branch (`feat/<task>`, `fix/<task>`, or `docs/<task>`), **NEVER** on `main`.
   ```bash
   git branch --show-current
   ```
2. **Local Pre-flight & Tests**:
   Run the task-specific verification or local CI pre-flight:
   ```bash
   scripts/local-ci.sh
   # or fast core tests:
   scripts/core.sh test dev fast
   ```
3. **Inspect Working Tree**: Ensure there are no uncommitted or untracked changes left behind unintentionally.
   ```bash
   git status --short
   ```

---

## 2. Conventional Commit

Commit the changes following repository governance rules:

1. **Stage only declared task files**:
   ```bash
   git add <file1> <file2> ...
   ```
2. **Inspect whitespace & diff**:
   ```bash
   git diff --cached --check
   git diff --cached --stat
   ```
3. **Create Conventional Commit**:
   - Format: `<type>(<scope>): <short description> (fixes #<issue_id>)`
   - Example: `fix(core): handle provider timeout on empty buffer (fixes #142)`
   ```bash
   git commit -m "<type>(<scope>): <description>"
   ```

---

## 3. Push & Create Pull Request

1. **Push branch to origin**:
   ```bash
   BRANCH=$(git branch --show-current)
   git push -u origin "$BRANCH"
   ```

2. **Open Pull Request via `gh` CLI**:
   Ensure PR body contains issue reference (`Closes #<id>`) and documentation impact declaration:
   ```bash
   gh pr create \
     --base main \
     --head "$BRANCH" \
     --title "<Conventional Commit Title>" \
     --body "$(cat <<'PR_BODY'
   ## Summary
   Closes #<ISSUE_ID>

   ## Verification
   - Task tests and local verification passed cleanly.

   ## Impact Declaration
   Documentation impact: none
   Reason: Task-specific implementation with no public API/documentation impact.
   PR_BODY
   )"
   ```

---

## 4. Enable Auto-Merge & Monitor CI

1. **Enable GitHub Auto-Merge (Squash Merge & Delete Branch)**:
   ```bash
   gh pr merge --auto --squash --delete-branch
   ```
   *(Optional: If the repository uses `merge:queue`, apply label: `gh pr edit --add-label "merge:queue"`)*

2. **Watch CI Checks**:
   ```bash
   gh pr checks --watch
   ```
   Wait until all checks pass and GitHub automatically squash-merges the PR into `main`.

3. **Confirm Merged State**:
   ```bash
   gh pr view --json state,mergedAt,mergeCommit
   ```

---

## 5. Local Worktree & Branch Cleanup

After the PR is confirmed `MERGED`:

1. **Switch to main workspace / root repo**:
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Remove the temporary worktree**:
   ```bash
   git worktree list
   git worktree remove <worktree-path>
   ```

3. **Delete local branch and prune remote references**:
   ```bash
   git branch -d "$BRANCH"
   git fetch --prune
   ```

4. **Confirm Clean State**:
   ```bash
   git status
   ```
