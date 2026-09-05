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
4. **Map acceptance journeys to far-side evidence**: When the Issue, design,
   plan, or acceptance ledger names a multi-step journey, enumerate every leg
   in order before declaring verification complete. For each transition,
   record an observable assertion after the transition, including every named
   crash/retry, failure-to-discard/abort, stop, reload/reopen, and
   persisted-truth leg. Persisted artifacts must be checked by their complete
   required identity (for example digest and byte length, not only media type).
   If a leg was not exercised, keep it as an explicit acceptance gap; a green
   prefix of the journey is not a pass for the full journey.

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

### Writing a contract test that scans source text

When a contract test asserts a string is **absent** from a file, scan the
directives rather than the raw source. Anything worth forbidding is worth
explaining, the explanation lands in a comment in the same file, and the scan
reads both:

```python
directives = "\n".join(
    line for line in source.splitlines()
    if not line.lstrip().startswith("#")
)
```

Presence assertions can keep reading the raw source; only absence has the blind
spot. Where the banned string is a path the file must also declare, constrain
the declaration rather than loosening the gate. See
[`gate-matches-its-own-prose`](../../pitfalls/gate-matches-its-own-prose.md).

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
- [`acceptance-journey-truncation`](../../pitfalls/acceptance-journey-truncation.md)
  — map every specified transition to a far-side observable; do not shorten a
  journey to the last state the current implementation already reaches.

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
3. **Mandatory new-file ownership preflight after staging**:
   ```bash
   git add <file1> <file2> ...
   git diff --cached --diff-filter=A --name-only
   python3 tests/build/ci_change_scope_test.py
   ```
   Whenever `git diff --cached --diff-filter=A --name-only` lists any path, the
   ownership suite (or an equivalent gate that reads the staged index) is
   mandatory before commit.
   Confirm `test_every_tracked_path_has_explicit_ownership_or_full_rule` passes
   with no `unclassified tracked paths`. Task-specific tests do not substitute
   for this ownership check.

   A check that reads `git ls-files`, the index, or the commit graph is blind to
   an unstaged file, so a green run before `git add` proves nothing about a file
   the Task adds. A new tracked file needs a rule in
   `scripts/ci/scope_policy.json`; check whether an existing prefix rule covers
   the exact filename rather than assuming its directory is covered. See
   [`untracked-file-passes-ownership-gate`](../../pitfalls/untracked-file-passes-ownership-gate.md).

4. **Create Conventional Commit**:
   - Format: `<type>(<scope>): <short description> (fixes #<issue_id>)`
   - Example: `fix(core): handle provider timeout on empty buffer (fixes #142)`
   ```bash
   git commit -m "<type>(<scope>): <description>"
   ```

---

## 4. Push & Create Pull Request

Before any push, classify the final committed Task range:

```bash
git status --short
scripts/local-ci.sh --base-ref origin/main --list --json
```

Run this after the Conventional Commit against the clean final `HEAD`. Confirm
the JSON classifies the complete `origin/main...HEAD` range using the canonical
ownership rule in `scripts/ci/scope_policy.json`.

A changed path is safe to push when it matches `rules`, or when it matches
`full_rules` and the JSON selects `full` with every lane. A full-only path
may retain both an `unclassified path` diagnostic and its named `full rule`
reason; that diagnostic alone is not a push blocker. Stop before pushing
only when a path matches neither `rules` nor `full_rules`.

### Split control-plane paths first

Before opening the Pull Request, check whether the branch touches the
control-plane set named in
[`docs/governance/git-workflow.md`](../../../docs/governance/git-workflow.md) §5
— `.github/workflows/merge-queue.yml`, `.github/workflows/ci.yml`,
`.github/actionlint.yaml`, `scripts/ci/merge_queue.py`,
`scripts/ci/github_queue_api.py`, `scripts/ci/merge_queue_watchdog.py`,
`scripts/ci/change_scope.py`, `scripts/ci/pr_gate.py`, or
`scripts/ci/scope_policy.json`:

```bash
git diff --name-only origin/main...HEAD | grep -E '^(\.github/workflows/(ci|merge-queue)\.yml|\.github/actionlint\.yaml|scripts/ci/(merge_queue|github_queue_api|merge_queue_watchdog|change_scope|pr_gate)\.py|scripts/ci/scope_policy\.json)$'
```

A Pull Request touching any of them **cannot use the Integration Queue** and
must take the ordinary protected path, where `strict` branch protection
requires the head to contain current `main`. If it also carries ordinary work,
**split it**: land the control-plane change as its own Pull Request, then open
the remainder, which is queue-eligible and usually selects far fewer lanes.

Bundling loses a race rather than failing loudly. Full CI here runs about 185
minutes, so an active `main` flips the Pull Request to `BEHIND` faster than a
rerun can finish, and each cycle costs another full run. Merging past it needs
a human to bypass `strict`, which discards the guarantee that requirement
exists to provide.

When the control-plane change is a routing rule for paths the same branch
introduces — the common case, since
`tests/build/ci_change_scope_test.py` fails on any tracked path no rule
classifies — land the rule first and the paths second. A rule for a path that
does not exist yet classifies nothing and breaks nothing.

See [`release-cut-bundles-control-plane`](../../pitfalls/release-cut-bundles-control-plane.md).

### Related-Issue vocabulary and the closing-directive check

GitHub reads `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`,
`resolves` and `resolved` immediately before an Issue reference as a closing
directive, and its parser has no notion of the sentence around them. "This
Pull Request does not close #466" closes #466 on merge. Four Issues lost their
open state that way; see
[`github-closing-keyword-negation`](../../pitfalls/github-closing-keyword-negation.md).

Choose exactly one form per Issue the Pull Request references:

- **Final delivery** — this Pull Request completes every acceptance item of the
  Issue: `Closes #<issue_id>`. Keep it; nothing here weakens it.
- **Partial delivery** — this Pull Request intentionally delivers only part of
  the Issue and the Issue must stay open: `Relates to #<number>`, the exact
  positive form. `Part of #<number>` and `Refs #<number>` are accepted
  synonyms for an umbrella reference.

Never write a closing keyword in front of an Issue reference in order to deny
it. Do not write "does not close #<number>", "will not fix #<number>", or any
other negated form: state what is still outstanding instead, in a sentence that
contains no closing keyword before a reference. Never pair `Relates to
#<number>` with `Closes #<number>` for the same Issue in one body — the closing
directive wins on merge and the retained relation is prose.

Write the body to a file and check it before `gh pr create`:

```bash
gh pr view <number> --json body -q .body > /tmp/pr-body.md   # or write the file directly
python3 tests/build/ci_pr_body_lint.py --body-file /tmp/pr-body.md
```

The lint is deterministic and fails closed, naming the violated invariant and
the exact safe replacement. Its regression coverage over the four real
recurrences is `tests/build/ci_pr_body_lint_test.py`. Run it again after any
later edit to the body, including an edit made in the GitHub web editor: the
lint reads the text you give it and cannot see a directive added afterwards.

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

4. **Audit the live state of every Issue the Pull Request meant to keep open**:
   ```bash
   gh issue view <number> --json number,state
   ```
   Run this for each `Relates to #<number>` reference. The closing-directive
   lint reads the body, not GitHub's parser, so a merge that closed a retained
   Issue anyway is still a finding: reopen the Issue, say why in a comment, and
   record the occurrence on
   [`github-closing-keyword-negation`](../../pitfalls/github-closing-keyword-negation.md).

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
