# LMDJ Pitfall Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a repository-resident, agent-neutral pitfall ledger, seed it from recurring history, and make the normal shipping and release skills retrieve and update it.

**Architecture:** `.agents/pitfalls/` is a decisions-directory-style store with one Markdown file per pitfall and no shared index file. `docs/governance/pitfall-ledger.md` owns the schema, escalation, gate-admission, and failure-message contracts; `AGENTS.md`, `CLAUDE.md`, and the shipping skills only route agents to that authority at the point of use.

**Tech Stack:** Markdown governance and skill files, Git/GitHub history, existing Architecture Portal checks.

**Spec:** GitHub issues [#300](https://github.com/endaye/lmdj/issues/300), [#301](https://github.com/endaye/lmdj/issues/301), and [#302](https://github.com/endaye/lmdj/issues/302).

## Global Constraints

- Execute Stage 1 and Stage 2 on separate short-lived `docs/*` branches in isolated worktrees.
- Produce one reviewable Conventional Commit per stage; Stage 2 closes #301 and #302 together because both modify the same two skill files.
- Do not implement #303 until either the first real declaration drift is observed or Stage 2 has been merged for two weeks.
- Do not add or modify CI workflow files.
- Before each commit, run Task-specific checks and `scripts/architecture-portal.sh check`, stage only declared files, and inspect the staged and committed file lists.
- Before every GitHub CLI operation, select the `endaye` account.

## Version Management

Version impact: none — both stages change governance documentation, retained process knowledge, and agent instructions only; no Product Build, Core Module, Provider, or Contract identity changes.

## Documentation Impact

Documentation impact: required for Stage 1 — add `docs/governance/pitfall-ledger.md` to the source paths of the current `operations/documentation-governance` portal route because that page enumerates active governance authorities.

Documentation impact: none for Stage 2 — seed entries and `.agents/` skill text are repository-internal retained knowledge, and no portal route derives facts from `.agents/`.

---

### Task 1: Land the Pitfall Ledger Contract (Closes #300)

**Files:**
- Create: `docs/governance/pitfall-ledger.md`
- Create: `.agents/pitfalls/TEMPLATE`
- Create: `docs/superpowers/plans/2026-08-25-lmdj-pitfall-ledger.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `apps/architecture-portal/docs/operations/documentation-governance.mdx`

**Interfaces:**
- Consumes: issue #300's settled ledger schema and governance rules.
- Produces: the canonical entry shape and routing contract consumed by Task 2.

- [ ] **Step 1: Write the contract and copyable entry template**

Define one-file-per-pitfall storage; required `id`, `area`, `status`, `recurrences`, and `exit` frontmatter; occurrence fields; body sections; recurrence-two escalation; the three gate criteria; and the `why` plus `remedy` failure-message rule.

- [ ] **Step 2: Add repository and portal routing**

Add identical short Pitfall Ledger pointer sections to `AGENTS.md` and `CLAUDE.md`, and add the governance contract to the portal page's `source_paths`.

- [ ] **Step 3: Verify Stage 1**

Run:

```bash
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git diff --check
```

Expected: all commands exit 0; `AGENTS.md` and `CLAUDE.md` remain byte-identical; the portal reports all current routes and links valid.

- [ ] **Step 4: Commit and ship Stage 1**

Stage only the six declared paths, inspect `git diff --cached --name-status` and `git diff --cached --check`, then create:

```text
docs(governance): adopt pitfall ledger contract (fixes #300)
```

Push, open a PR containing `Closes #300`, `Documentation impact: required — operations/documentation-governance`, and `Pitfall impact: none — reason: establishes the ledger contract before live entries exist`; enable squash auto-merge, watch required checks, confirm merge, and clean the local worktree and branch.

### Task 2: Seed and Activate the Ledger (Closes #301 and #302)

**Files:**
- Create: `.agents/pitfalls/<pitfall-id>.md` for at least five historically supported recurring pitfalls.
- Modify: `.agents/skills/issue-done/SKILL.md`
- Modify: `.agents/skills/lmdj-release/SKILL.md`

**Interfaces:**
- Consumes: Task 1's entry schema, escalation rule, and gate criteria.
- Produces: initial searchable retained knowledge plus the record-or-bump and retrieval paths used by future Tasks.

- [ ] **Step 1: Mine authoritative history and issue evidence**

For each required cluster in #301, inspect the named PRs, merge commits, enforcing files/tests, and attributable agent/model evidence. Record exact dates and GitHub PR or commit links; use `observed_by: unknown` when history does not authoritatively attribute a model.

- [ ] **Step 2: Write at least five seed entries**

Include squash-witness provenance, release-intent binding, gate-failure readability, coverage-gate tuning temptation, and stress tiers inside the coverage preset. Mark absorbed entries with the exact enforcing `skill:` or `gate:` path and reduce absorbed bodies to concise pointers; leave an entry open only with an explicit explanation for the missing mechanism.

- [ ] **Step 3: Add the dynamic write and retrieval paths**

In `issue-done`, before commit: grep existing IDs and areas, decide out-of-scope/product-test versus new entry versus recurrence, update the entry in the same commit, and at recurrence 2 either land an eligible mechanism or open and link an escalation issue. Add the exact PR declaration alternatives `Pitfall impact: new <id> | recurrence <id> | none — reason:`. In both skills, add a Pitfalls section that retrieves relevant open entries by area at the point the pitfall can occur.

- [ ] **Step 4: Verify Stage 2**

Run schema-shape searches against every seed, targeted skill tests, `bash tests/build/test_active_tree.sh`, `scripts/architecture-portal.sh check`, and `git diff --check`. Confirm no workflow file changed and #303 remains open.

- [ ] **Step 5: Commit and ship Stage 2**

Stage only seed entries and the two skill files, inspect staged and committed file lists, then create:

```text
docs(governance): activate pitfall ledger (fixes #301, fixes #302)
```

Push, open one PR containing both `Closes #301` and `Closes #302`, `Documentation impact: none` with the internal-retained-knowledge reason, and the truthful `Pitfall impact:` state; enable squash auto-merge, watch required checks, confirm merge, and clean the local worktree and branch.

### Task 3: Observe Drift Without Implementing #303

**Files:**
- Modify: none.

**Interfaces:**
- Consumes: the next naturally occurring fix PR after Task 2 merges.
- Produces: either a valid `Pitfall impact:` declaration or the first evidence that permits #303.

- [ ] **Step 1: Record the observation boundary**

After Task 2 merges, inspect the next natural fix PR for a syntactically valid `Pitfall impact:` line. Do not manufacture a PR or edit code for this observation.

- [ ] **Step 2: Preserve the #303 trigger**

Keep #303 open and unimplemented unless the declaration is missing (first real drift) or the Task 2 merge date is at least two weeks old. If neither condition holds, report observation as pending.
