# LMDJ 1.0.40.0 Release Intent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reviewable, fail-closed release intent for the Stage 9 Sequence Recording Product Build `1.0.40.0` at an exact protected-`main` revision with retained full-CI evidence, while stopping before tag creation, GitHub Release creation, publication, deployment, or Channel promotion.

**Architecture:** The tracked intent ledger remains the reviewed authorization source. A dated evidence record binds the candidate to one immutable Product snapshot, one exact protected-`main` revision, and one successful full `Core CI` run. The existing release control plane revalidates all remote state after merge; this PR performs no release transition.

**Tech Stack:** JSON release intent ledger, Markdown retained evidence, Python 3.11 `unittest`, existing `scripts/release.sh` audit and repository CI scope classifier.

**Spec:** `docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md`

## Global Constraints

- Work only on `docs/release-intent-1-0-40` in the isolated `.worktrees/release-intent-1-0-40` worktree.
- Bind `lmdj-v1.0.40.0` to exact protected-`main` revision `bb0544c46d4b3fc3a7c96cb848e10cdecb4be040` and to successful full run `33259586218`, whose retained scope manifest and aggregate gate match that exact revision.
- Keep the intent at Product Channel `canary`. The open #360 manual/physical rows and the open `p1` defects #442 and #443 are preserved as explicit boundaries and do not become automated Proof.
- This Task may push its branch and create a reviewable PR. It must not merge, create or push a tag, create or publish a GitHub Release, deploy Runtime assets, or promote a Channel.
- Before commit, run the declared tests, stage only the declared files, inspect the staged file list and diff, run `git diff --cached --check`, and inspect the committed file list and final status.

## Version Management

Version impact: none

Reason: Product Build `1.0.40.0`, its Assembly Lock, Module, Host, Provider, and Contract identities are already immutable on protected `main` through PR #420; this Task adds release authorization and evidence only.

## Documentation Impact

Documentation impact: none

Reason: No Product, Assembly, portal route, manual behavior, or architecture content changes. The dated evidence and intent ledger are release control-plane records, and the existing immutable `1.0.40.0` snapshot remains unchanged.

---

### Task 1: Bind and verify the Product release intent

**Files:**

- Create: `docs/superpowers/plans/2026-08-31-lmdj-1-0-40-release-intent.md`
- Create: `docs/release-evidence/2026-08-31-lmdj-1.0.40.0-canary-release-intent.md`
- Modify: `docs/release-evidence/release-intents.json`
- Modify: `tests/build/release_model_test.py`

- [x] **Step 1: Add a failing tracked-ledger assertion**

Require `lmdj-v1.0.40.0` to be `releasable`, `canary`, `web-runtime-host`, bound to the exact target revision, snapshot, retained full-CI run, and dated evidence path.

- [x] **Step 2: Run RED**

Run `python3 -m unittest tests.build.release_model_test`.

Observed: `AssertionError: unexpectedly None` — the reviewed ledger did not yet authorize `lmdj-v1.0.40.0`.

- [x] **Step 3: Add the evidence record and intent**

Record the exact Product/snapshot/Assembly identities, the introducing commit, the current protected-`main` target, the retained full-CI run and scope manifest, the unchanged Product tree between allocation and target, and the remaining manual/physical boundaries. Add one `releasable` ledger row with the same exact values.

- [ ] **Step 4: Verify locally**

Run:

```bash
python3 -m unittest tests.build.release_model_test tests.build.release_audit_test tests.build.release_ci_evidence_test
scripts/architecture-portal.sh check
python3 scripts/version.py verify --version-file products/lmdj/version.json --assembly products/lmdj/assembly.json --lock products/lmdj/assembly.lock.json
GITHUB_TOKEN="$(gh auth token -h github.com)" scripts/release.sh audit --local --tag lmdj-v1.0.40.0
```

The local audit must validate the candidate without mutating release state. The canonical remote audit remains unauthorized until this PR is merged and must be rerun after merge before any separate release transition.

- [ ] **Step 5: Commit and open the review boundary**

Stage only the four declared files, inspect the staged and committed paths, commit once as `docs(release): authorize 1.0.40.0 canary intent`, push this branch, create a non-draft PR with exact CI, version, documentation, pitfall, release-impact, and transition-authority declarations, then stop before merge.
