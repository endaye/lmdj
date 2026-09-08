# LMDJ Release Intent After Squash Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a current Product Build and its immutable Architecture Portal snapshot to land through the protected-main squash workflow before a separately reviewed release intent binds the resulting exact `main` SHA.

**Architecture:** Keep `_local_repository_issue()` authoritative for active Product manifests, Assembly lock/component digests, the current immutable snapshot and its full provenance, and every non-abandoned ledger target object. Select zero or one current Product intent; reject duplicates, and run only intent binding plus merged-main Proof validation when that intent exists. Remote per-intent protected-main ancestry and explicit-tag authorization remain unchanged.

**Tech Stack:** Python 3 standard library and `unittest`, JSON release authority, Markdown governance and design documents.

## Global Constraints

- Work only on `fix/release-intent-after-squash` in its isolated worktree, created from current `origin/main`.
- Keep the initial implementation and independent-review remediation as separate reviewable Conventional Commits; no push, Pull Request, merge, tag, release, deployment, publication, or Channel mutation.
- Do not edit `docs/release-evidence/release-intents.json`, any Product Build, Assembly, lock, or immutable Portal snapshot.
- Preserve all intent gates: more than one current Product intent fails closed; an existing current intent still requires exact-target and merged-main Proof validation; every non-abandoned ledger target object must exist locally; remote `allocated` and `releasable` targets must be protected-main ancestors; an explicit unregistered tag remains unauthorized.
- Treat the existing `1.0.25.0` non-main target as an inherited independent defect, not part of this Task.

---

### Task 1: Separate Product Build allocation from release intent authorization

**Files:**

- Modify: `tools/release/audit.py`
- Test: `tests/build/release_audit_test.py`
- Modify: `docs/governance/version-management.md`
- Modify: `docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`
- Create: `docs/plans/2026-08-22-lmdj-release-intent-after-squash.md`

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

---

### Task 2: Close independent-review provenance and operations-documentation gaps

**Files:**

- Modify: `tools/release/audit.py`
- Modify: `tools/release/git_repository.py`
- Modify: `tools/release/target_validation.py`
- Test: `tests/build/release_audit_test.py`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `docs/plans/2026-08-22-lmdj-release-intent-after-squash.md`

- [x] **Step 1: Add RED production-path provenance tests**

  Rebuild canonical remote authority with a matching current Product Build and snapshot but zero current Product intent. Verify registered entries still audit normally and the unregistered exact Product tag remains unauthorized. For both local and remote zero-intent audits, corrupt snapshot revision, source tree, and authenticated squash witness evidence and require an `unverifiable` result.

- [x] **Step 2: Extract and enforce intent-independent snapshot provenance validation**

  Add `validate_current_product_snapshot()` in `target_validation.py`, reuse it from Product exact-target validation, expose it through `GitRepository`, and call it unconditionally from the immutable snapshot projection. Keep only intent binding and merged-main Proof conditional on an existing current intent.

- [x] **Step 3: Correct the current operations route**

  Update `/operations/version-and-release/` with the zero-intent allocation window, exact protected-main squash timing, invalid pre-squash targets, and the retained authorization gates. Do not change an immutable snapshot or Product identity.

- [x] **Step 4: Verify and commit the review follow-up**

  Run the focused audit tests, full `tests/build/release_audit_test.py`, all release tests, `scripts/architecture-portal.sh check`, and `scripts/core.sh test dev full`. Stage only the six follow-up files, run `git diff --cached --check`, create a new Conventional Commit without amending the first, then inspect the committed file list and final status.

## Version Management

Version impact: none

Reason: This Task changes only repository release-audit behavior and governance timing. It does not change Product behavior or Assembly, Module/Host API, Contract, Provider, Model identity, or any Product Build.

## Documentation Impact

Documentation impact: required

Affected route: `/operations/version-and-release/`

Reason: This Task changes the release authorization timing and the audit behavior operators rely on. The current operations page must state the zero-intent source-allocation window, the exact protected-main squash boundary, and the gates retained after an intent exists. No immutable snapshot changes.

## Out of Scope

- Repairing or rebinding the inherited `1.0.25.0` non-main release-intent target.
- Changing release intent schema, dispositions, CI evidence, Proof shape, tag policy, or remote state.
- Editing versioned Architecture Portal snapshots.
