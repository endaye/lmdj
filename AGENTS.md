# LMDJ New Headless Core

This repository contains the clean-break LMDJ core redesign. New Headless Core
is the only active product source.

## Git workflow

`main` is protected and must remain deployable. Work only on a short-lived
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

A commit does not authorize push, Pull Request creation, merge, tag push,
release, publication, deployment, or Channel promotion.

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

## Version management

`docs/governance/version-management.md` is the canonical version policy.

- Product Builds use `MILESTONE.MINOR.BUILD.PATCH`; this is not SemVer.
- Core Modules and Provider implementations use independent SemVer.
- Contracts use stable Contract IDs plus Contract SemVer.
- Tags are immutable annotated tags. Product tags are signed.
- Every implementation plan contains a `## Version Management` section.
- A plan with no version impact still records `Version impact: none` and a
  reason.

## Commands

The stable Core entry point is:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev
scripts/core.sh proof
scripts/core.sh clean
```

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
