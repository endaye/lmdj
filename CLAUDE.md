# LMDJ New Headless Core

This repository contains the clean-break LMDJ core redesign. New Headless Core
is the only active product source.

## Git workflow

`main` is the protected integration branch; it may temporarily contain defects.
Release readiness belongs to an explicitly selected, fully verified candidate,
not every merge. The optimistic CI rules take effect only at the authorized
O2 cutover; a draft branch does not override live `main` governance or protection.
Work only on a short-lived
branch in an isolated worktree. Branch names must use `feat/<task>`,
`fix/<task>`, or `docs/<task>`; this applies equally to people and coding
agents. Do not create long-lived `develop`, `release/*`, or `hotfix/*` branches.

[`docs/governance/git-workflow.md`](docs/governance/git-workflow.md) is the
canonical workflow, including task start, PR, squash merge, release, and cleanup
rules.

Each implementation Task is one reviewable Conventional Commit. Before every
commit:

- verify the current branch is not `main`;
- run the Task-specific tests;
- stage only the Task's declared files;
- inspect the staged file list and `git diff --cached --check`;
- inspect the committed file list and final worktree status.

Coding agents commit autonomously: once a change is complete and its
Task-specific verification passes, create the Conventional Commit without
asking for confirmation, and commit later user-requested modifications the
same way. This autonomy covers local commits only; push and every later
state transition still require explicit authorization.

A commit does not authorize push, Pull Request creation, merge, tag push,
release, publication, deployment, or Channel promotion.

## Task shipping and issue operations

- For querying/triaging open issues, parallel workstreams, and auditing/cleaning local branches and worktrees, follow `.agents/skills/issue-list/SKILL.md`.
- For shipping a locally completed issue or task, coding agents must follow `.agents/skills/issue-done/SKILL.md` (handles verification, Conventional Commit, push, PR creation, CI auto-merge, and worktree/branch cleanup).

## Pitfall ledger

Process and invariant knowledge that cannot be derived from product code lives
in `.agents/pitfalls/` under the contract in
[`docs/governance/pitfall-ledger.md`](docs/governance/pitfall-ledger.md). At the
relevant skill trigger, search open entries by the Task's `area:*` labels;
before shipping, follow `issue-done` to record or bump any qualifying pitfall.

## Release operations

For any release audit or operation, coding agents must read and follow
`.agents/skills/lmdj-release/SKILL.md`. The normal release path uses only the
stable `scripts/release.sh` interface and begins with a fresh exact-tag remote
audit. `prepare`, `push-tag`, `create-draft`, publication through the protected
`publish-release.yml` workflow, Runtime deployment, and Channel promotion are
separate authorization and verification boundaries. Complete at most one
authorized mutation, rerun the audit, report the verified state and stop before
the next boundary.

Handwritten tag/Release commands, one-step public Release flows,
`gh release upload --clobber`, and `git push --tags` are outside the normal
path. An emergency exception requires an incident owner, exact target and asset
inventory, rollback and stop conditions, and after-action evidence before the
operation begins. Urgency never authorizes moving a tag, skipping signing, or
silently coupling publication to deployment.

## Active source boundaries

- `packages/` contains product-neutral Core Modules.
- `apps/` contains thin Core Hosts that use only the Application Facade.
- `providers/` contains Capability-based Provider implementations.
- `products/` contains Product Assembly and version identity.
- `contracts/` contains versioned cross-language Contracts.
- `workers/` is reserved for future out-of-process Provider Hosts.
- `references/demos/` is frozen reference material, never active product code.

`lmdj.patch.v1` and `lmdj.materials.v1` must not be used by new code. Do not
restore, wrap, translate, or emit the retired contracts.

## Architecture invariants

- Hosts use Application Facade; they must not parse Project bundles.
- Project Truth is authoritative authoring state.
- Runtime Snapshot is immutable derived state and is never persisted as
  Project Truth.
- Pattern events reference Pad Slots, never Assets directly.
- Provider selection belongs to Workspace/Host settings, not Project Truth.
- Provider failure belongs to Attempt state, never Project Truth.
- Provider code receives Artifact inputs and an Artifact output sink; it never
  receives a mutable Project or Project bundle path.
- Product-specific wiring belongs only in Product Assembly.

## Minimization principle

[`docs/governance/minimization-principle.md`](docs/governance/minimization-principle.md)
is the canonical statement. It applies at every stage — designing a feature,
writing a plan, implementing, testing, and adding or changing a gate — and it
names three rules, each with something that gets smaller and something that
must never shrink:

- **Gates** minimize the set of required checks, never the invariants they
  cover. A required check must name the defect it catches; otherwise it is
  advisory. Conservative lane selection stays fail-closed.
- **Tests** minimize the reasons a test can fail, never its strictness. One
  test fixes one fact; reduce a defect before fixing it; acceptance journeys
  keep every leg with a far-side assertion per transition.
- **Changes** minimize the distance from a red gate to its cause, never the
  Task's declared scope. One Task is one commit of declared files; a plan
  Task names its files, its lowest-tier tests, and the defect any new gate
  catches.

Thresholds are instruments, not targets: never lower a coverage floor, widen a
timeout, skip a test, de-select an owned lane, or drop a journey leg to make a
run green. Making something smaller is not minimization when what shrinks is
coverage, strictness, or scope.

## Version management

`docs/governance/version-management.md` is the canonical version policy.

- Product Builds use `MILESTONE.MINOR.BUILD.PATCH`; this is not SemVer.
- Core Modules and Provider implementations use independent SemVer.
- Contracts use stable Contract IDs plus Contract SemVer.
- Tags are immutable annotated tags. Product tags are signed.
- Every implementation plan contains a `## Version Management` section.
- A plan with no version impact still records `Version impact: none` and a
  reason.

## Architecture portal and documentation impact

[`docs/governance/architecture-portal.md`](docs/governance/architecture-portal.md)
is the canonical portal and documentation-impact policy. Every implementation
plan and Pull Request declares `Documentation impact: required` with affected
portal routes, or `Documentation impact: none` with a concrete reason. When
required, update the current pages and source diagrams in the same Task.

Do not hand-enter or guess Product, Module, Host, Provider, Contract, Channel,
or revision identities; the portal derives them from active manifests. Run
`scripts/architecture-portal.sh check` before commit when the Task affects portal
pages, diagrams, tooling, projected identities or documented source facts; it is
not a universal pre-push requirement for unrelated Tasks. A local build, CI run, or
Pull Request Preview does not create a permanent snapshot. Any Product Build
allocated for team testing or release must include an immutable snapshot made
with `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`; Product
Build or Assembly changes cannot declare `Documentation impact: none`. Normal
production publication is Git-triggered; manual production uploads are
prohibited.

## Commands

The stable Core entry point is:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev [fast|full|stress]
scripts/core.sh coverage [report|check]
scripts/core.sh proof
scripts/core.sh package
scripts/core.sh clean
```

`test` selects by execution tier and defaults to `full`. `full` runs every tier
except `stress`, `fast` runs only `unit` and `component`, and `stress` runs only
the `stress` tier. Running `scripts/core.sh test dev` therefore does not run the
stress tier; run it explicitly when changing lock-free or concurrent code.
`proof` also excludes the stress tier. The `core-asan` CI job runs `full` then
`stress`, and `core-asan-macos` selects the `native` label. These belong to
complete daily/node self-tests, not a Pull Request merge gate. `core-asan-macos` covers native tests only: the
Python-hosted tests preload the sanitizer runtime into CPython, which does not
work on arm64 macOS, so Linux `core-asan` owns that coverage.
`docs/quality/core-test-policy.md` is the canonical tier definition.

`package` produces a distributable Core archive. It builds Release, runs the
`unit` and `component` tiers, then packages, and it refuses to package a
modified working tree because the recorded Git revision would not describe the
contents. It also writes a detached `<archive>.sha256`.

Direct verification commands:

```bash
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
```

## Design authority

- Core redesign:
  `docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
- Current implementation plan:
  `docs/superpowers/plans/2026-07-30-lmdj-headless-core-proof.md`
- Version policy: `docs/governance/version-management.md`
- Product decisions: `docs/prd/decision-log.md`
- Open product questions: `docs/prd/open-questions.md`

Do not silently settle an open product-level Contract or concurrency question
inside an implementation Task.
