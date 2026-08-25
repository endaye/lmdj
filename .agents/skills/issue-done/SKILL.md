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

## 2. Pitfall Ledger: Record or Bump

Before committing, decide whether this Task taught the repository something it
could not read off the code. `.agents/pitfalls/` is the shared memory every
agent brand and every human reads; the contract is
[`docs/governance/pitfall-ledger.md`](../../../docs/governance/pitfall-ledger.md).

1. **Decide whether it qualifies**:
   - **In scope**: a process or invariant defect whose root cause is not
     derivable from the product code — release/CI ordering, provenance,
     governance timing, tool-boundary behaviour.
   - **Out of scope**: a product-logic defect whose regression test fully
     expresses the invariant. That test is its exit; do not write an entry.
2. **Dedup before creating** — a near match is another recurrence of an
   existing pitfall, not a sibling file:
   ```bash
   ls .agents/pitfalls/
   grep -rn "<keyword>" .agents/pitfalls/
   ```
3. **Bump or create, in the same commit as the fix**:
   - Existing entry: append one occurrence to `recurrences:` with today's date,
     the Pull Request or commit URL, and `observed_by:` naming the agent or
     model that hit it.

     `observed_by` is **self-reported by the agent writing the entry, at the
     moment it writes**. Never infer it from the commit author, the Pull
     Request author, or the Git identity: concurrent sessions share one
     identity, and a branch can also carry commits made through the GitHub web
     interface, so that metadata cannot say which agent did the work. If you
     cannot state it from your own record of what you did, write `unknown`
     rather than a guess. See
     [`cross-agent-commit-attribution`](../../pitfalls/cross-agent-commit-attribution.md).
   - New entry: copy `.agents/pitfalls/TEMPLATE` to
     `.agents/pitfalls/<id>.md`, where `<id>` matches the filename stem.
4. **Escalate at recurrence 2** — when the bump takes the entry's recurrence
   count to 2 or more, this same Task must either:
   - land an eligible mechanism, record it in `exit` as `skill:<path>` or
     `gate:<test path>`, and set `status: absorbed`; or
   - open an escalation Issue, link it from the entry, and leave the entry
     `open`.

   A mechanism becomes a gate only when all three admission criteria hold: the
   invariant is settled, violation is mechanically decidable, and the check is
   deterministic. Otherwise it exits to a skill section. Any gate you add must
   fail with a message naming both the violated invariant and its remedy.

### Pitfalls that bite at this step

Read these before shipping; each is a real recurrence, not a hypothetical:

- [`gate-failure-readability`](../../pitfalls/gate-failure-readability.md) — if
  this Task adds or changes a fail-closed check, its message must carry `why`
  and `remedy`.
- [`coverage-floor-tuning`](../../pitfalls/coverage-floor-tuning.md) — a red
  coverage gate is an instrument reading; raise real coverage, never lower a
  floor to go green.
- [`stress-tier-in-coverage-preset`](../../pitfalls/stress-tier-in-coverage-preset.md)
  — a new busy-spinning `stress` test must be excluded from the `coverage`
  preset in the same commit.

---

## 3. Conventional Commit

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

## 4. Push & Create Pull Request

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

   Pitfall impact: none — reason: no process invariant was learned that the code does not already state.
   <!-- Use exactly one: `new <id>` | `recurrence <id>` | `none — reason: ...` -->
   PR_BODY
   )"
   ```

---

## 5. Enable Auto-Merge & Monitor CI

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

## 6. Local Worktree & Branch Cleanup

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
