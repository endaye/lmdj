# LMDJ Release Intent After Squash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a current Product Build and its immutable Architecture Portal snapshot to land through the protected-main squash workflow before a separately reviewed release intent binds the resulting exact `main` SHA.

**Architecture:** Keep `_local_repository_issue()` authoritative for active Product manifests, Assembly lock/component digests, the current immutable snapshot, and every non-abandoned ledger target object. Select zero or one current Product intent; reject duplicates, and run exact-target plus merged-main Proof validation only when that intent exists. Remote per-intent protected-main ancestry and explicit-tag authorization remain unchanged.

**Tech Stack:** Python 3 standard library and `unittest`, JSON release authority, Markdown governance and design documents.

## Global Constraints

- Work only on `fix/release-intent-after-squash` in its isolated worktree, created from current `origin/main`.
- One reviewable Conventional Commit; no push, Pull Request, merge, tag, release, deployment, publication, or Channel mutation.
- Do not edit `docs/release-evidence/release-intents.json`, any Product Build, Assembly, lock, current Portal page, or immutable Portal snapshot.
- Preserve all intent gates: more than one current Product intent fails closed; an existing current intent still requires exact-target and merged-main Proof validation; every non-abandoned ledger target object must exist locally; remote `allocated` and `releasable` targets must be protected-main ancestors; an explicit unregistered tag remains unauthorized.
- Treat the existing `1.0.25.0` non-main target as an inherited independent defect, not part of this Task.

---

### Task 1: Separate Product Build allocation from release intent authorization

**Files:**

- Modify: `tools/release/audit.py`
- Test: `tests/build/release_audit_test.py`
- Modify: `docs/governance/version-management.md`
- Modify: `docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md`
- Create: `docs/superpowers/plans/2026-08-22-lmdj-release-intent-after-squash.md`

**Interfaces:**

- Preserve: `_local_repository_issue(context: object, entries: list[ReleaseIntent]) -> AuditFinding | None`.
- Change: the active current Product intent cardinality from exactly one to zero or one.
- Preserve: `_audit_remote_intent()` exact-target, protected-main ancestry, CI, tag, Release, and asset checks.

- [x] **Step 1: Add RED tests for the allocation window and retained fail-closed gates**

  Replace the two repository-current integration assertions with synthetic Product Build fixtures that prove a matching current snapshot plus zero current intent is locally valid and that the snapshot is still mandatory. Add focused assertions for duplicate current intents, current-intent exact-target failure, current-intent Proof mismatch, and missing non-abandoned ledger target objects. Retain the existing remote off-main `allocated`/`releasable` and explicit unregistered-tag tests.

- [x] **Step 2: Run the focused tests and verify RED**

  Run the named new `unittest` methods. The zero-intent fixture must fail because the current implementation requires exactly one active Product intent; the failure must not be a syntax, import, or fixture error.

- [x] **Step 3: Implement the minimal audit change**

  In `_local_repository_issue()`, reject only `len(active) > 1`; bind `active_intent` only for the one-intent case. Always validate manifests, Assembly lock/components, the current immutable Portal snapshot, and every non-abandoned target object. Guard exact-target and merged-main Proof projections behind `active_intent is not None`.

- [x] **Step 4: Verify GREEN and the full audit contract**

  Run the focused tests, then `python3 tests/build/release_audit_test.py`. Confirm zero intent is accepted while duplicate, exact-target, Proof, target-object, remote ancestry, and explicit-tag gates remain fail closed.

- [x] **Step 5: Update the governed timing boundary**

  Update `docs/governance/version-management.md` section 12.1 and the approved release-pipeline design section 6.2: allocating source Product Build plus immutable snapshot requires no release intent; intent is a separate reviewed authorization created only after the exact protected-main squash SHA exists; branch-only/pre-squash SHAs are invalid; zero or one current intent is valid and duplicates are rejected.

- [x] **Step 6: Run repository verification and commit**

  Run `python3 tests/build/version_test.py`, `python3 scripts/version.py verify --version-file products/lmdj/version.json`, `bash tests/build/test_active_tree.sh`, `scripts/architecture-portal.sh check`, and `scripts/core.sh test dev full` when practical. Stage only the five declared files, inspect the staged file list and diff, run `git diff --cached --check`, commit once, then inspect the committed file list and final status.

## Version Management

Version impact: none

Reason: This Task changes only repository release-audit behavior and governance timing. It does not change Product behavior or Assembly, Module/Host API, Contract, Provider, Model identity, or any Product Build.

## Documentation Impact

Documentation impact: none

Reason: The current Architecture Portal `/operations/version-and-release/` page already separates source Product Build allocation, reviewed release intent, and exact protected-main release target. This Task corrects the audit implementation and its canonical governance/specification wording without changing any Portal route or immutable snapshot.

## Out of Scope

- Repairing or rebinding the inherited `1.0.25.0` non-main release-intent target.
- Changing release intent schema, dispositions, CI evidence, Proof shape, tag policy, or remote state.
- Editing current or versioned Architecture Portal content.
