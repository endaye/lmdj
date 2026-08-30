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
scripts/local-ci.sh --pr-body body.md     # also check the PR body declaration
scripts/local-ci.sh --install-hook        # install the pre-push hook
```

The pre-flight is advisory and produces no evidence. A lane this machine
cannot execute — a Linux lane on macOS, a lane whose toolchain is absent,
`package` against a modified working tree — reports `not-runnable-here`,
never `pass`. `PR Gate` remains the single aggregate decision, and a green
local run authorizes no push, Pull Request, merge, or later state transition
(see §7).

`--pr-body FILE` checks a Pull Request body's documentation-impact
declaration with the same `check-doc-impact.mjs` the `portal` lane runs, so
`Documentation impact:`, `Reason:` and `Affected portal pages:` are validated
in milliseconds instead of after a full portal lane. Write the declaration as
bare lines — the patterns are anchored, so bold or a trailing period does not
match, and CI reads the body from the event payload, which means a body edit
alone does not re-trigger the run. The check is never cached, since a body
file is not repository content, and it reports `not-applicable` rather than
`pass` when the change does not select the `portal` lane, because that is the
only condition under which CI checks the declaration at all. A local `--lanes`
restriction does not change that: it narrows what runs here, not what CI would
select.

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

An ordinary `main` push is classified from the exact `before..after` range with
the same path ownership rules as a Ready Pull Request, so a docs-only merge runs
focused CI while Product Assembly, Contract, central CI-control, unknown-path
and three-expensive-family merges still run full. The push base is an event
field, not a resolved Pull Request base: a zero, absent, non-commit or
non-ancestor `before`, or any incomplete inventory, is reported as an
unverifiable base and runs full with that concrete reason and no path
inventory. Main runs stay grouped per SHA and never cancel an earlier `main`
run.

Focused is a CI cost decision and a merge decision, never a release decision.
A Product Build or release operator who needs full evidence for an exact `main`
SHA dispatches `ci.yml` on that SHA with an empty `lanes` input and records the
resulting run ID in the release intent; `scripts/release.sh audit --remote` and
`prepare` reject focused or `requested` evidence, and a full dispatch by itself
authorizes no release mutation. That operator dispatch is the one
`workflow_dispatch` that stays unconditionally full: a queue dispatch carries a
ticket and classifies, so the two never collapse into each other. See
[`../prd/decisions/2026-08-29-focused-merge-evidence.md`](../prd/decisions/2026-08-29-focused-merge-evidence.md).

To upgrade the current head to full CI, apply `ci:full`, then wait for the
in-progress run to finish or explicitly cancel it. Because label changes do not
start a separate workflow event, use GitHub's **Re-run all jobs** on the current
head after the label is visible. Confirm the new `Change Scope` summary says
`full`, all 14 lanes are selected, and the same-run `PR Gate` passes. Do not use
an individual job rerun to change scope.

### Serialized Integration Queue

The repository-owned Integration Queue is available only after its separate
remote rollout has passed. Workflow code on `main` is not enablement: before the
label exists, run three no-mutation `workflow_dispatch` probes and prove one
running plus two pending runs start in platform FIFO order under the single
`lmdj-merge-main` group. The group must use `queue: max`; the default single
pending behavior is forbidden because a later PR could replace an earlier one.
The dispatch response must also contain a numeric `workflow_run_id`. A failed
probe keeps the exact `merge:queue` label absent.

After enablement, adding `merge:queue` is an explicit, revocable authorization
to update and automatically squash-merge that PR; it is not review approval.
Only an actor whose live repository permission is `write`, `maintain`, or
`admin` may authorize a same-repository, open, non-Draft PR targeting `main`.
The controller re-reads eligibility and the label, then merges exact current
`main` into the PR branch when needed. GitHub creates that `GITHUB_TOKEN`
`synchronize` run in approval-required state; the controller binds the unique
exact PR/head/bot `Core CI` run, approves it with `actions:write`, and uses its
same-run scope as the validation instead of dispatching duplicate CI. If the
PR already contains current `main`, the controller dispatches Core CI bound to
one ticket, PR number, base SHA, head SHA, and numeric `workflow_run_id`. In
either path the exact run must publish `core (ubuntu-latest)`,
`core (macos-latest)`, and same-run `PR Gate` from GitHub Actions App ID
`15368`. Only live-confirmed base/head drift may consume another attempt, with
three attempts total.

Merge evidence is the classification, at `focused` or `full`; a `requested`
lane selection and a `draft` manifest are never merge evidence, and an
untrusted head is never evidence at any breadth. The `merge:queue` label
authorizes a merge and no longer widens one. Because the manifest may be
focused, `core (ubuntu-latest)` and `core (macos-latest)` may be `skipped` when
it did not select their lanes; `PR Gate` may not, because it is what makes the
skip safe. It adjudicates the same run against the manifest and fails both when
a selected job is not success and when an unselected job ran anyway, so its
success already proves each skip was owed.

Queue validation proves the tree that will land, not the history it will land
as. Both paths run CI on a head that already contains exact current `main`, so
the validated tree is the tree GitHub publishes; the commit shape is not the
same, because the squash keeps only that tree with current `main` as its single
parent, and the branch commits never enter `main`'s history. Any invariant that
reads main's history shape can therefore answer differently before and after the
merge. Portal snapshot provenance was such an invariant, and it is settled by
making it decidable from the target tree alone: a Product Build snapshot
introduced by a change must record a source projection equal to the projected
files in that change's own tree. The portal lane decides that before the merge
and the landed provenance gate re-decides it on exactly the tree that landed, so
the two verdicts are identical by construction. A squash witness remains what it
always was, a repair for a divergence that already landed: it names the
introducing commit, so it cannot be written before the squash exists. A change
that freezes a snapshot and then keeps editing projected files must re-freeze at
its own tip rather than rely on a witness it cannot yet produce. This rule is
motivated by the green-then-red failure documented in Issue #296, where PR #282
passed every gate and turned `main` red for 2h50m on the squash it produced.

Once the queue is enabled, it is the default path for every non-control-plane
PR merging into `main`. While an `lmdj-merge-main` queue item is queued or
in-progress, ordinary manual merging of a non-control-plane PR is prohibited:
each such merge creates one confirmed base drift for every PR already in the
queue, consumes one of its three attempts, and invalidates one in-progress full
validation. The ordinary protected path remains for control-plane PRs (which
are already required to use it) and for explicitly recorded exceptions under
the §emergency semantics when the queue is proven unavailable. This rule is
motivated by the mixed-path failure documented in PR #226 and Issue #230.

A PR changing `.github/workflows/merge-queue.yml`, `.github/workflows/ci.yml`,
`.github/actionlint.yaml`, `scripts/ci/merge_queue.py`,
`scripts/ci/github_queue_api.py`, `scripts/ci/merge_queue_watchdog.py`,
`scripts/ci/change_scope.py`, `scripts/ci/pr_gate.py`, or
`scripts/ci/scope_policy.json` is a control-plane change and cannot use the
queue to merge itself. It follows the ordinary protected merge path. The
actionlint `1.7.12` pin has one temporary, exact exception for its upstream
`concurrency.queue` schema lag; repository tests separately require exactly one
`queue: max`, and every other actionlint diagnostic remains fatal.

Removing `merge:queue` cancels authorization while the controller can still
observe it. A final label read and the merge mutation cannot be atomic, so an
operator who revokes during that narrow window must inspect the queue report
and live PR state rather than infer cancellation from label absence. Duplicate
workers that reach an already merged PR exit successfully as `already-merged`.
Every other terminal failure removes the label and leaves one stable-code PR
conversation comment; recovery requires fixing the cause and explicitly adding the
label again.

After GitHub accepts the squash merge, PR merge metadata can briefly lag the
main ref. Within a 30-second scheduling budget, the controller performs up to
seven read-only postcondition observations no more than five seconds apart and
passes the remaining budget to every REST transport timeout. It requires
PR/main/merge SHA/tree equality to converge and never repeats the merge mutation.

An open PR whose latest `merge:queue` event is at least 20 minutes old, with no
associated queued or in-progress queue run since that event, has the
`queue-stalled` signature. Inspect the workflow run, pending capacity, manual
cancellation/platform timeout, and controller report in that order. The
scheduled watchdog re-reads the head, removes the stale label, and emits one
idempotent `queue-stalled` review marker. Reconcile live state before re-adding
the label; the watchdog and controller never restore authorization themselves.

Queue validation proves only the exact synchronized PR head. The resulting
focused `main` run and exact-main release evidence remain separate: release
operations still require a successful full `Core CI` run and retained full
scope manifest for the exact target `main` SHA. Queue success authorizes no tag,
release, deployment, publication, or Channel promotion.

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

0. establish full exact-main CI evidence for the target SHA: a completed,
   successful `Core CI` run on `main` whose retained scope manifest is `full`
   for that exact SHA with a trusted head and whose same-run `Change Scope` and
   `PR Gate` both succeeded. That manifest is retained for 14 days; after it
   expires, rerun every job of the exact recorded run while the run itself is
   retained, or obtain a newly authorized exact-SHA full run and a reviewed
   intent update. Evidence is never inferred or reconstructed;
1. run a fresh read-only `audit --remote --tag TAG` against canonical state;
2. authorize `prepare` to build, verify, sign, and create only local state;
3. separately authorize `push-tag` to push and reconcile one exact tag;
4. separately authorize `create-draft` to create or reconcile one Draft
   GitHub Release and print its immutable publication inputs;
5. explicitly dispatch `publish-release.yml` with the exact tag, numeric
   Release ID, and plan digest; the protected `release` Environment enforces
   the exact-`main` publication policy (the current solo-maintainer mode has no
   required reviewer);
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
