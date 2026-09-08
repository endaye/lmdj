# Main PR-only Rule Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PR-only integration into `main` an explicit repository rule for Codex and Claude collaborators.

**Architecture:** Add one identical workflow section near the top of both repository guidance files. Keep GitHub branch protection as the enforcement layer and document a narrowly scoped administrator emergency exception.

**Tech Stack:** Markdown, Git, GitHub Pull Requests

## Global Constraints

- Never modify or commit project files directly on local `main` during normal development.
- All normal changes reach `main` through a short-lived branch, required validation, and a Pull Request.
- Codex-created branches use the `codex/` prefix.
- Administrator bypass is limited to incident recovery or repair of broken branch protection and requires an after-the-fact record.
- `AGENTS.md` and `CLAUDE.md` must carry semantically identical shared guidance.

---

### Task 1: Add the repository workflow rule

**Files:**
- Modify: `AGENTS.md:5`
- Modify: `CLAUDE.md:5`

**Interfaces:**
- Consumes: The approved policy in `docs/design/2026-07-16-main-pr-only-rule-design.md`.
- Produces: A `## Git workflow` section used by repository collaborators before they edit files.

- [ ] **Step 1: Insert the workflow section in `AGENTS.md`**

Insert after the introductory paragraph and before `## Repository layout`:

```markdown
## Git workflow

`main` is protected and must remain deployable. During normal development, do not create, modify, or commit project files directly on local `main`.

- Before changing files, update `main`, then create a short-lived branch. Codex-created branches use the `codex/` prefix; use an isolated worktree when the work should not disturb the main checkout.
- Complete and verify all changes on the short-lived branch, push it, and merge it into `main` only through a Pull Request after required CI and review gates pass. Use squash merge unless the repository policy explicitly changes.
- After merge, delete the short-lived branch. Use `main` only for synchronization, read-only inspection, creating branches, and deploying already-merged commits.
- If an intended edit starts while the current branch is `main`, stop and create or switch to a short-lived branch before modifying files. Do not make the edits first and move them later.
- An administrator may bypass the PR path only for incident recovery or to repair branch protection that blocks its own fix. Keep the bypass minimal and follow it with a PR, issue, or incident record describing the reason, changes, and verification. Urgency alone is not an exception.
```

- [ ] **Step 2: Insert the identical workflow section in `CLAUDE.md`**

Insert the exact `## Git workflow` block from Step 1 after the introductory paragraph and before `## Repository layout`.

- [ ] **Step 3: Verify both rule blocks are identical and complete**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

def section(path: str) -> str:
    text = Path(path).read_text()
    return text.split("## Git workflow\n", 1)[1].split("\n## Repository layout", 1)[0]

agents = section("AGENTS.md")
claude = section("CLAUDE.md")
assert agents == claude
for phrase in ("do not create, modify, or commit", "Pull Request", "codex/", "administrator may bypass"):
    assert phrase in agents
print("Git workflow rules match")
PY
git diff --check
```

Expected: `Git workflow rules match`, followed by a zero exit status from `git diff --check`.

- [ ] **Step 4: Commit the rule change**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs(workflow): require PRs for main changes"
```

- [ ] **Step 5: Publish through the rule being introduced**

```bash
git push -u origin codex/chore-main-pr-rule
gh pr create \
  --base main \
  --head codex/chore-main-pr-rule \
  --title "docs(workflow): require PRs for main changes" \
  --body $'## Summary\n\n- document the PR-only workflow for main\n- keep AGENTS.md and CLAUDE.md guidance aligned\n- define the administrator emergency bypass and follow-up record\n\n## Validation\n\n- workflow rule blocks match exactly\n- git diff --check'
```

Expected: GitHub returns a Pull Request URL. Merge only after all required checks pass, using squash merge.
