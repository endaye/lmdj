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

### Local pre-flight

`scripts/local-ci.sh` runs the lanes CI would select for the current working
tree, on the current machine. It calls the same `scripts/ci/change_scope.py`
classifier and `scripts/ci/scope_policy.json` policy the workflow uses, so it
cannot select a different lane set than CI, and it caches each lane's passing
verdict against a digest of that lane's inputs — an untouched lane is not
re-run between iterations.

```bash
scripts/local-ci.sh                       # run every selected lane
scripts/local-ci.sh --list                # resolve the plan without running
scripts/local-ci.sh --lanes core_ubuntu   # restrict to named lanes
scripts/local-ci.sh --no-cache            # ignore cached lane verdicts
scripts/local-ci.sh --install-hook        # install the pre-push hook
```

The pre-flight is advisory and produces no evidence. A lane this machine
cannot execute — a Linux lane on macOS, a lane whose toolchain is absent,
`package` against a modified working tree — reports `not-runnable-here`,
never `pass`. `PR Gate` remains the single aggregate decision, and a green
local run authorizes no push, Pull Request, merge, or later state transition
(see §7).

`--install-hook` writes a `pre-push` hook that runs the pre-flight and
refuses the push on a hard failure; it refuses to overwrite an unrelated
existing hook unless `--force` is given. `git push --no-verify` is the
documented bypass.

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

Draft runs publish only Change Scope, Docs/static (`git diff --check` on the
exact range), and CI Contract (pinned actionlint plus `ci_*` contracts). They do
not establish merge evidence. Marking the Pull Request Ready triggers a new
classification and formal result for the current head.

To upgrade the current head to full CI, apply `ci:full`, then wait for the
in-progress run to finish or explicitly cancel it. Because label changes do not
start a separate workflow event, use GitHub's **Re-run all jobs** on the current
head after the label is visible. Confirm the new `Change Scope` summary says
`full`, all 14 lanes are selected, and the same-run `PR Gate` passes. Do not use
an individual job rerun to change scope.

Required-check migration uses a forward dual-gate sequence. Each numbered
boundary needs its own authorization; completion never authorizes the next:

1. finish and locally commit the classifier, conditional lanes, and `PR Gate`;
2. separately authorize branch push and Pull Request creation, apply `ci:full`,
   and declare all 14 lanes selected with none skipped;
3. verify the exact base/head manifest, same-run formal results, both legacy
   Core contexts, and `PR Gate` on that Pull Request;
4. under separate branch-protection authorization, add `PR Gate` as required
   while retaining `core (ubuntu-latest)` and `core (macos-latest)`;
5. separately authorize and perform the merge only after all three required
   contexts and every selected lane succeed;
6. verify the resulting `main` SHA runs `full` in a per-SHA non-cancelling run
   and publishes all formal results;
7. only then, under a new branch-protection authorization, remove the legacy
   Core contexts and confirm strict branch update and conversation resolution
   remain enabled.

The Package lane reuses the existing trusted Ubuntu selector, retains LFS
hydration, and disables ccache. Trusted same-repository work normally avoids
hosted Package execution; an untrusted fork or unavailable token/API/idle pool
still takes the existing hosted fallback. During the observation week compare
routine hosted minutes against the prior unconditional PR/main matrix,
including new control/full-main work and Package fallback. Normalize by PR
updates and merges: routine hosted minutes must not remain above the comparable
baseline. Any sustained regression requires routing correction or job
consolidation without weakening evidence; otherwise roll back the permanent
migration using the sequence below.

Required-check rollback is a fail-closed two-stage operation. Keep `PR Gate`
required and first merge a configuration that forces every Pull Request to
full. Prove that a docs-only Pull Request again publishes the old Core check
contexts, then restore those contexts as required branch-protection checks.
Only after the old protection is active may a separately authorized operation
remove `PR Gate`. No stage authorizes the next one.

## 6. Releases and urgent fixes

Releases are produced from an identified, verified `main` SHA under
[`version-management.md`](version-management.md). A release does not need a
persistent release branch. The normal path uses `scripts/release.sh` and keeps
each transition independently authorized and verified:

1. run a fresh read-only `audit --remote --tag TAG` against canonical state;
2. authorize `prepare` to build, verify, sign, and create only local state;
3. separately authorize `push-tag` to push and reconcile one exact tag;
4. separately authorize `create-draft` to create or reconcile one Draft
   GitHub Release and print its immutable publication inputs;
5. dispatch `publish-release.yml` with the exact tag, numeric Release ID, and
   plan digest; public Release publication occurs only after approval in the
   protected `release` Environment;
6. rerun the exact-tag remote audit and report the observed published state;
7. separately authorize manual Runtime deployment and then any Channel
   promotion, each with its own evidence.

`prepare` does not authorize a tag push. A tag push does not authorize a Draft.
A verified Draft does not authorize publication. A published Release neither
triggers nor authorizes deployment, and deployment does not authorize Channel
promotion. Normal operations do not use handwritten tag/Release commands,
one-step publication, destructive asset replacement, all-tags push, tag
movement, or published-history deletion.

An urgent fix follows the normal `fix/<task>` path from `main` through focused
verification, Pull Request, CI, and squash merge. Urgency can change scheduling
and test focus, but it does not authorize direct commits to `main` or bypassing
required gates. Any emergency release-path exception additionally requires an
incident owner, exact target and asset inventory, rollback and stop conditions,
and after-action evidence. It cannot waive tag immutability, signing, or the
separation between publication and deployment.

## 7. Authority and reported state

These are separate states and permissions:

```text
designed → planned → implemented → committed → pushed → merged
         → release-audited → prepared → exact-tag-pushed
         → Draft-created → Draft-verified → published-Release
         → deployment-authorized → deployed → deployment-verified
         → channel-promoted → release-verified
```

A completed state does not imply permission for the next one. In particular,
a commit does not authorize push, Pull Request creation, merge, tag, release,
deployment, or Channel promotion.
