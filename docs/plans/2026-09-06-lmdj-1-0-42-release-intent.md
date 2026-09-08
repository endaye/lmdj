# LMDJ 1.0.42.0 Release Intent Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reviewable, fail-closed release intent for the Stage 10 Perform Product Build `1.0.42.0` at an exact protected-`main` revision with retained full-CI evidence, while stopping before tag creation, GitHub Release creation, publication, deployment, or Channel promotion.

**Architecture:** The tracked intent ledger remains the reviewed authorization source. A dated evidence record binds the candidate to one immutable Product snapshot, one exact protected-`main` revision, and one successful full `Core CI` run. The existing release control plane revalidates all remote state after merge; this PR performs no release transition.

**Tech Stack:** JSON release intent ledger, Markdown retained evidence, Python 3.11 `unittest`, existing `scripts/release.sh` audit and repository CI scope classifier.

**Spec:** `docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`

## Global Constraints

- Work only on `docs/468-stage10-release-intent` in the isolated `.worktrees/issue-438-snapshot-witness` worktree already checked out for the Stage 10 close-out.
- Bind `lmdj-v1.0.42.0` to exact protected-`main` revision `59cc202b3f4d772814c8de8c1d0c0e6203485a11` (Task 11 squash / PR #682, the first main commit that contains the `1.0.42.0` squash witness) and to successful full run `33996811880`, whose retained scope manifest and aggregate gate match that exact revision.
- The Integration Queue merges with `GITHUB_TOKEN`, so the squash produced no `push` event `Core CI` run. The full run was dispatched with an empty `lanes` input while `main` HEAD was still exactly the target SHA; a lane selection would produce a rejected `requested` manifest.
- Keep the intent at Product Channel `canary`. Every Stage 10 Perform physical row remains `deferred` and does not become automated Proof.
- This Task may push its branch and create a reviewable PR. It must not merge, create or push a tag, create or publish a GitHub Release, deploy Runtime assets, or promote a Channel.
- Before commit, run the declared tests, stage only the declared files, inspect the staged file list and diff, run `git diff --cached --check`, and inspect the committed file list and final status.

## Version Management

Version impact: none

Reason: Product Build `1.0.42.0`, its Assembly Lock, Module, Host, Provider, and Contract identities are already immutable on protected `main` through PR #664; this Task adds release authorization and evidence only.

## Documentation Impact

Documentation impact: none

Reason: No Product, Assembly, portal route, manual behavior, or architecture content changes. The dated evidence and intent ledger are release control-plane records, and the existing immutable `1.0.42.0` snapshot remains unchanged.

---

### Task 1: Bind and verify the Product release intent

**Issue:** #468.

**Files:**

- Create: `docs/plans/2026-09-06-lmdj-1-0-42-release-intent.md`
- Create: `docs/release-evidence/2026-09-06-lmdj-1.0.42.0-canary-release-intent.md`
- Modify: `docs/release-evidence/release-intents.json`
- Modify: `tests/build/release_model_test.py`

- [x] **Step 1: Add a failing tracked-ledger assertion**

Require the exact tag, target revision, snapshot, channel `canary`, profile `web-hosts`, disposition `releasable`, full-CI run ID and dated evidence path in `tests/build/release_model_test.py`. Expected: FAIL with `stage10 unexpectedly None` because no intent row exists.

- [x] **Step 2: Run the canonical pre-intent remote audit**

Run `scripts/release.sh audit --remote --tag lmdj-v1.0.42.0`. Expected: `unauthorized`, because the ledger holds no entry and no historical exception for the tag. Confirm no remote tag and no GitHub Release exist.

- [x] **Step 3: Establish full exact-main CI evidence**

Confirm no `push` event `Core CI` run exists for the target SHA, then dispatch `ci.yml` with an empty `lanes` input while `main` HEAD is exactly the target. Record the run ID.

- [ ] **Step 4: Create the intent records**

Write the dated plan and evidence documents and append exactly one immutable `releasable` row to `docs/release-evidence/release-intents.json`.

- [ ] **Step 5: Verify GREEN**

Run `python3 tests/build/release_model_test.py`, `python3 tests/build/release_audit_test.py`, `python3 tests/build/release_ci_evidence_test.py`, `scripts/architecture-portal.sh check`, `python3 scripts/version.py verify --version-file products/lmdj/version.json` and `scripts/release.sh audit --local --tag lmdj-v1.0.42.0`. Expected: all pass.

- [ ] **Step 6: Commit and ship**

Commit the four declared files as `docs(release): authorize 1.0.42.0 canary intent (fixes #468)` and ship through `issue-done`. Rerun the canonical remote audit on merged `main` before any mutation.

## Execution Order

```text
merged #664 (Product Build 1.0.42.0 + immutable snapshot)
  → merged #681 (Stage 10 acceptance evidence)
      → this intent PR
          → prepare → push-tag → create-draft → verify-draft → publication
```

Runtime deployment and `beta`/`stable` Channel promotion are outside this plan.
