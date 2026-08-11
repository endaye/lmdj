# Git Workflow

This document is the canonical Git workflow for LMDJ. It applies equally to
human contributors and coding agents.

## 1. Model

LMDJ uses a lightweight GitHub Flow model built around one protected branch:

```text
main
  └── feat/<task> | fix/<task> | docs/<task>
        └── local verification
        └── Pull Request and CI
        └── squash merge to main
        └── branch and worktree cleanup
```

`main` is the only long-lived branch and must remain deployable. The repository
does not use long-lived `develop`, `release/*`, or `hotfix/*` branches.

## 2. Task branches

Every change starts from the latest `origin/main` in a short-lived branch and
an isolated worktree. Use exactly one of these prefixes:

| Prefix | Use |
| --- | --- |
| `feat/<task>` | New product, Core, Provider, tooling, build, or CI capability |
| `fix/<task>` | Defect, regression, reliability, security, or urgent production repair |
| `docs/<task>` | Documentation, research, governance, or planning with no runtime change |

Use a short lowercase kebab-case task name, such as `feat/runtime-snapshot`,
`fix/provider-timeout`, or `docs/git-workflow`. Coding agents use the same
prefixes; there is no agent-specific branch namespace.

If a task mixes categories, choose the prefix for its primary deliverable. If
the changes cannot form one reviewable unit, split them into separate tasks and
branches.

## 3. Start a task

Before editing:

1. fetch and prune remote refs;
2. confirm the current worktree has no task-related uncommitted changes;
3. create the task branch from the latest `origin/main`;
4. create or enter its isolated worktree;
5. run the smallest relevant baseline verification.

Never implement or commit directly on `main`. Never mix unrelated existing
changes into the task worktree or commit.

## 4. Implement and commit

Each implementation Task is one reviewable Conventional Commit. A later user
turn that requests another modification produces another commit.

Before committing:

1. run the Task-specific tests;
2. stage only the Task's declared files;
3. inspect the staged file list;
4. run `git diff --cached --check`;
5. inspect the complete staged diff;
6. commit with a Conventional Commit message;
7. inspect the committed file list and final worktree status.

Do not create empty commits. If verification fails or the commit boundary
cannot be isolated, stop and report the blocker instead of committing.

Coding agents do not need per-commit confirmation: once a change is complete
and its verification passes, commit autonomously, and commit later
user-requested modifications the same way. This autonomy covers local
commits only; push and every later state transition still require explicit
authorization (see §7).

## 5. Pull Request and merge

Remote operations require separate authorization. When authorized:

1. push the task branch;
2. open a Pull Request targeting `main`;
3. require every manifest-selected formal lane plus `PR Gate` to pass,
   including supported-platform, sanitizer, and coverage gates selected for
   the change;
4. resolve review findings in new task-local commits;
5. update the branch from the latest `main` and rerun required checks when the
   protection rules report it as behind;
6. squash merge the Pull Request;
7. verify the Pull Request is merged and the resulting `main` SHA exists;
8. remove the merged branch and its clean worktree, then prune stale refs.

Prefer rebasing an unshared local branch. For a shared branch, avoid rewriting
published history unless collaborators explicitly agree. Force-push is never
an implicit part of updating a branch.

Squash merging means branch ancestry alone may not prove that cleanup is safe.
Before deleting a branch, verify its Pull Request state and patch equivalence
with `main`, and verify its worktree is clean.

### CI scope operations

Every Pull Request body declares its expected CI mode, selected and skipped
closed lanes, whether `ci:full` is required, and the ownership or upgrade
reason. The checked-in scope policy remains authoritative; the declaration is
review evidence, not an override.

To upgrade the current head to full CI, apply `ci:full`, then wait for the
in-progress run to finish or explicitly cancel it. Because label changes do not
start a separate workflow event, use GitHub's **Re-run all jobs** on the current
head after the label is visible. Confirm the new `Change Scope` summary says
`full`, all 14 lanes are selected, and the same-run `PR Gate` passes. Do not use
an individual job rerun to change scope.

Required-check rollback is a fail-closed two-stage operation. Keep `PR Gate`
required and first merge a configuration that forces every Pull Request to
full. Prove that a docs-only Pull Request again publishes the old Core check
contexts, then restore those contexts as required branch-protection checks.
Only after the old protection is active may a separately authorized operation
remove `PR Gate`. No stage authorizes the next one.

## 6. Releases and urgent fixes

Releases are produced from an identified, verified `main` SHA under
[`version-management.md`](version-management.md). A release does not need a
persistent release branch.

An urgent fix follows the normal `fix/<task>` path from `main` through focused
verification, Pull Request, CI, and squash merge. Urgency can change scheduling
and test focus, but it does not authorize direct commits to `main` or bypassing
required gates.

## 7. Authority and reported state

These are separate states and permissions:

```text
designed → planned → implemented → committed → pushed → merged
         → tagged → built → channel-promoted → released
         → deployed → release-verified
```

A completed state does not imply permission for the next one. In particular,
a commit does not authorize push, Pull Request creation, merge, tag, release,
deployment, or Channel promotion.
