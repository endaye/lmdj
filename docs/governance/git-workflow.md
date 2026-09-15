# Git Workflow

This document is the canonical Git workflow for LMDJ. It applies equally to
human contributors and coding agents.

Ordinary PR integration uses current-head review and Task verification without
the retired full-CI/strict-update gate; read live protection before each merge.
The incremental main-only automatic trigger switch is a separate T5 transition,
not an ordinary PR permission. The trigger patch landed in PR #898, but its
controller self-subscription was rejected by GitHub before any job could run.
PR #904 merged the completion-relay repair. Its actual main-push run
`34188723712/1` started the controller, which subsequently succeeded; this is
entry-start evidence, not proof of the complete automatic recovery chain.
Relay callback, chain-limit recovery and O2 acceptance remain separate checks.
Retain persistent state and in-flight inventory; do not restore retired daily
tests or turn controller startup into a full-product or O2 pass.

## 1. Model

LMDJ uses a lightweight GitHub Flow model built around one protected branch:

```text
main
  └── feat/<task> | fix/<task> | docs/<task>
        └── local verification
        └── Pull Request and current-head review
        └── squash merge to main
        └── branch and worktree cleanup
```

`main` is the only long-lived integration branch and may temporarily contain
defects. Releasability belongs to a selected, fully verified exact candidate. The repository
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
3. create the task branch from the latest `origin/main` **without tracking
   it** — `git worktree add --no-track .worktrees/<task> -b <prefix>/<task>
   origin/main`. A branch created with `-b <task> origin/main` alone inherits
   `origin/main` as its upstream, and an IDE "sync" then pushes the Task
   straight to `main`; see
   [`task-branch-upstream-tracks-main`](../../.agents/pitfalls/task-branch-upstream-tracks-main.md);
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

These steps are the change-layer form of
[`minimization-principle.md`](minimization-principle.md): a small, declared
commit is what lets a red gate point at its cause.

### Local pre-flight

`scripts/local-ci.sh` is an explicit advisory local tool. It reuses the canonical
`change_scope.py` / `scope_policy.json` classifier to recommend lanes and
preserve path ownership; classification is not a requirement to run every lane
before pushing. Task-specific verification remains required.

```bash
scripts/local-ci.sh --list --json          # classify without running lanes
scripts/local-ci.sh --lanes core_ubuntu   # explicitly run relevant local lanes
scripts/local-ci.sh                       # explicitly run all selected lanes
scripts/local-ci.sh --declaration-only --pr-body <body-file>
scripts/local-ci.sh --install-hook        # install/migrate this tool's hook
LMDJ_PRE_PUSH_FULL=1 git push             # opt in to heavy pre-push verification
```

A local pass or cached pass is not merge/release evidence and grants no remote
authority. Unavailable platforms, toolchains and packaging preconditions report
`not-runnable-here`, never pass. Input-bound caches remain outside the worktree.
`--declaration-only` requires a body file, executes no lanes and never caches
the body check. A not-applicable declaration check is not portal verification.

The installed hook does no heavy work by default. Only explicit
`LMDJ_PRE_PUSH_FULL=1` runs the selected lane set and propagates its failure.
Installation recognizes only exact generated current/legacy hook content; it
backs up the legacy version before migration and refuses personal hooks,
symlinks or conflicting backups even with `--force`. Hooks may be shared by
worktrees: inspect the reported path rather than mass-updating checkouts.
The backup supports deliberate rollback to the old hook. `--no-verify`
bypasses hooks, not authorization or the Task verification obligation.

Run the portal check locally only when the Task affects pages, diagrams,
tooling, projected identities or documented source facts. Full self-test batches
still include portal verification; unrelated PRs do not acquire a hidden
all-portal pre-push build.

Coding agents complete verified Tasks under the standing authorization in
`AGENTS.md`: commit, push, PR, current-head review and guarded squash merge.
Explicitly restricted draft or local-only work retains its narrower boundary.

## 5. Pull Request and merge

When the user has authorized the relevant transitions:

1. push the declared Task branch and open a reviewable PR to main;
2. retain the Task's actual verification and unexercised acceptance gaps;
3. inspect the live current head, PR state, conflicts and review threads;
4. obtain exact-head AI review or an explicit documented human/agent takeover
   after actual inspection; address findings with a concrete disposition;
5. squash merge only the inspected head, with expected-head protection where
   supported, then verify PR state and the resulting merged SHA;
6. separately perform authorized cleanup only after proving complete patch
   retention and a clean, inactive worktree.

AI review is feedback, not a correctness oracle or machine merge gate. Missing
credentials, backend errors, timeouts, invalid output and old-head evidence
must be visible; none means clean. Takeover records reviewer, head SHA, reason,
scope, findings/disposition and limitations on the PR. A head change requires
new review of the current change. Empty/NEUTRAL check lists and a model's own
completion marker are not review evidence. Resolving threads is not a way to
erase findings without actually evaluating them.

No full test matrix, sanitizer, coverage, or portal build is a PR merge
prerequisite. A non-conflicting branch need
not follow every main advancement. Unknown mergeability is not false or true:
reread within a bounded interval, then report uncertainty. Resolve real conflicts
and rerun affected Task checks; rebasing unshared work is preferred, but published
history must not be rewritten without collaborator agreement and force-push
authority. A self-test failure does not prevent ordinary repair PRs merging.

Read actual protection before merging. If retired required checks or strict
up-to-date rules reappear, stop and report configuration drift. Shipping
authority is not permission to bypass or edit protection.

### Scope diagnostics and batch evidence

Keep canonical path ownership and local classification; match `rules` or
`full_rules` for all tracked paths and validate new files after staging.
An intentional full-only classification is not an unowned-path error. A
classification's breadth recommends verification, not universal full execution.
Split control-plane changes when reviewability or a real dependency warrants
it; do not require every such PR to split or chase main.

The approved incremental strategy has no daily automatic product tests. A main
wakeup selects one pinned target from the complete first-parent interval since
durable processed progress, including each commit's rename/delete/revert paths,
not only the endpoint net diff. Scope is the conservative deterministic floor
under applicable old/new policies, union authenticated review requirements and
eligible verification debt, closed over all affected consumers. AI and mutable
labels cannot reduce that floor. Unknown scope evidence selects full; unreadable
history blocks admission rather than inventing a complete interval.
None requires explicitly safe explanatory documents with no automated consumer
and no selected debt. Local classification is not the authoritative review record.

One active automatic batch runs at a time. New merges coalesce into the next
target without cancelling the current batch. Persist the immutable request and
execution claim before heavy work, then the terminal result before progress;
the short writer lock must not span heavy execution. Preserve resource locks,
exact target/control/policy/run/attempt and each selected or not-selected verdict.
Processed progress is not health: test failures remain separate from unexecuted,
blocked, cancelled or infrastructure verification debt. Bounded recovery may
pause debt, never erase it or retry indefinitely for green. Missing evidence is
not success; storage failure blocks progress rather than inventing a result.

Authenticated failures enter durable report outboxes without freezing PR merges;
report recovery does not rerun product tests. Explicit exact-target full requests
remain available and cannot be displaced by automatic pending work. Historical
candidate results do not move automatic progress or clear newer debt.
Testing does not allocate a version or select/release a candidate. See
[the incremental spec](../design/2026-09-08-lmdj-ci-incremental-batches.md)
for the activation and recovery requirements. Daily product triggers and their
daily-missing alert are retired together; the independent lightweight health
tick recovers existing pending work and never creates a date-based test request.

The managed-report exception is deliberately narrower than the historical
failure rule: only a newly created managed bucket with authenticated causal and
policy identity, complete required suite/dependency coverage, a later selected
PASS with no verification debt, and durable success-comment plus close-patch
receipts may be discharged by recovery. Historical, edited, human-investigated,
candidate/node, and independent defect Issues remain under manual disposition;
an unrelated green batch never changes them. Unknown write outcomes remain
unresolved until positively reconciled.

### Post-merge provenance and cleanup

A merged PR is not evidence that uncommitted or later local work is retained.
Squash ancestry alone is insufficient: verify the complete local patch and
worktree cleanliness, locks and active sessions before any authorized removal.
Never switch/reset another session's checkout to make cleanup convenient.

Prevent the witness rather than repairing it. Provenance resolves with no
witness when the commit introducing a snapshot's metadata has the recorded
source revision as its parent. A squash merge makes that parent whichever
commit was `main`'s tip at merge time, and the freeze records the HEAD it ran
against, so the two agree only when the freeze is the first and only commit on
a branch cut from the current `main` and the merge happens before `main` moves.
Do not bundle a snapshot freeze into a branch that already carries commits: the
freeze then records a branch commit the squash discards, and direct-parent
provenance can never resolve. Every snapshot frozen so far recorded such a
branch commit, and five of the six then needed a witness.

For a Task allocating a Product Build or introducing a snapshot, verify
provenance against the actual merged introducing SHA. If a squash witness is
missing, use the official `architecture-portal.sh witness` generator and ship
its output in a separate authorized commit/PR; do not hand-edit frozen data.
This conditional follow-up is neither an all-PR portal build nor release
authorization.

## 6. Releases and urgent fixes

Releases begin with a user request for an explicitly chosen, verified exact main-history
candidate under [version-management.md](version-management.md) and the
`lmdj-release` skill. A green complete self-test is reusable only if the canonical
release verifier accepts its complete, current, exact-candidate evidence; it
does not authorize prepare, tag, Draft, publication, deploy or promotion.
Expired or missing evidence must be reacquired as a new authorized test request,
never inferred or reconstructed from a focused/local pass.

Use only `scripts/release.sh`, beginning with a fresh exact-tag remote audit.
Publication uses the separately dispatched `publish-release.yml` workflow and
its protected `release` Environment; a self-test does not invoke it.
Prepare, one exact tag push, Draft creation, protected publication, each Host
deployment and Channel promotion are separate verification boundaries covered
by one overall release authorization. Continue covered transitions after each
successful verification without asking again; stop for a failed gate, required
external approval or missing scope. Follow the canonical policy's current asset inventory, signatures,
profile and historical exceptions rather than duplicating them here.
The [Web Host release and deployment policy](version-management.md) is
authoritative for the release profile, signed asset inventory, independent Host
deployments, and immutable historical exceptions.
Publication never implicitly fans out to deployments.

Keep Product Build allocation reviewable and separate from unrelated feature /
infrastructure changes; freeze its immutable snapshot and verify post-merge
provenance. A cut does not freeze all ordinary PR merges or require queue labels.
Selected candidate/tag identities do not move just because main advances.
Urgent fixes use short-lived `fix/<task>` branches and ordinary PR review;
urgency does not grant direct-main writes, release authority or protection bypass.
An emergency exception requires an incident owner, exact targets/assets,
rollback and stop conditions and after-action evidence; tag immutability,
signing and publication/deployment separation still hold.

## 7. Authority and reported state

These are separate states and permissions:

```text
designed → planned → implemented → committed → pushed → merged
         → release-audited → prepared → exact-tag-pushed
         → Draft-created → Draft-verified → published-Release
         → deployment-authorized → deployed → deployment-verified
         → channel-promoted → release-verified
```

A completed state does not itself imply permission for the next one. Permission
comes from the user's Task or release request and the standing rules in
`AGENTS.md`, not from a green check or prior transition. Task authorization does
not initiate a release, and a release request does not authorize protection bypass.
