# LMDJ Release Workflow Identity Repair Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make release CI evidence resolve GitHub Actions' stable workflow identity instead of treating a dynamic `run-name` as the policy workflow name, so the already successful exact-main full run can be audited without weakening any release gate.

**Architecture:** The GitHub REST adapter will bind each run to its `workflow_id` and workflow path, resolve the canonical workflow metadata through the Actions workflow endpoint, and project that stable name to the existing closed release policy. Same-run job identity remains bound by exact run ID and head SHA; its `workflow_name` is retained only as GitHub's dynamic run display name and is not reused as workflow authority.

**Tech Stack:** Python 3.11 `unittest`, GitHub Actions REST projections, existing `scripts/release.sh` audit, release governance and Architecture Portal operations pages.

**Spec:** `docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`

## Global Constraints

- Work only on `fix/release-workflow-identity` in the isolated `.worktrees/release-workflow-identity` worktree.
- Preserve the closed `Core CI` policy and every exact SHA, branch, event, conclusion, Gate, and retained full-scope check.
- Use only read-only GitHub endpoints in the verifier; this Task performs no tag, Release, deployment, or Channel mutation.
- Before commit, run the declared tests, stage only the declared files, inspect the staged file list and diff, run `git diff --cached --check`, and inspect the committed file list and final status.

## Version Management

Version impact: none

Reason: This repairs the release control-plane interpretation of GitHub metadata. It does not change any Product Build, Assembly Lock, Module, Host, Provider, or Contract identity.

## Documentation Impact

Documentation impact: required

Affected portal routes: `/operations/testing-and-proof/` and `/operations/version-and-release/`.

Reason: Operators need the stable-workflow-versus-dynamic-run-name boundary stated where exact-main CI release evidence is defined. The canonical version policy receives the same clarification.

---

### Task 1: Bind release evidence to stable Actions workflow metadata

**Files:**

- Create: `docs/plans/2026-08-25-lmdj-release-workflow-identity.md`
- Create: `.agents/pitfalls/actions-run-name-is-display-only.md`
- Modify: `tools/release/github_api.py`
- Modify: `tools/release/ci_evidence.py`
- Modify: `tests/build/release_github_api_test.py`
- Modify: `tests/build/release_ci_evidence_test.py`
- Modify: `tests/build/release_transitions_test.py`
- Modify: `docs/governance/version-management.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`

- [ ] **Step 1: Add live-shaped failing tests**

Add a REST projection test whose run and jobs expose `Core CI / main` while the workflow metadata endpoint exposes stable name `Core CI`. Add a verifier test proving that same-run jobs remain valid with that dynamic display name while a run resolved to a different stable workflow remains a conflict.

- [ ] **Step 2: Run RED**

Run:

```bash
python3 -m unittest tests.build.release_github_api_test tests.build.release_ci_evidence_test
```

Expected: the run projection test fails because the adapter currently reads `workflow_runs[].name`, and the same-run job test fails because the verifier compares the job display name to the stable policy name.

- [ ] **Step 3: Resolve and bind stable workflow identity**

Require `workflow_id` and `path` on each run, resolve `/actions/workflows/{workflow_id}`, verify the response ID and path match the run, cache repeated workflow metadata within one listing, and project its stable `name`. Remove the redundant job display-name comparison while retaining exact run ID and head SHA binding.

- [ ] **Step 4: Document the operational invariant**

Clarify in release governance and both affected Portal routes that `name:` is the policy identity while `run-name:` is display-only. Record the failure mode in the `ci-release` pitfall ledger with its regression-test exit.

- [ ] **Step 5: Verify locally**

Run:

```bash
python3 -m unittest tests.build.release_github_api_test tests.build.release_ci_evidence_test tests.build.release_audit_test tests.build.release_prepare_test tests.build.release_transitions_test
scripts/local-ci.sh --list
scripts/local-ci.sh --lanes deploy_contract,ci_contract,docs_static,portal
scripts/architecture-portal.sh check
GITHUB_TOKEN="$(gh auth token -h github.com)" scripts/release.sh audit --remote --tag lmdj-v1.0.36.0
```

The final command is read-only and must accept run `32857088479` for target `4a145f4aeba8594cf4b9c53cddfe8a67fabb5bf2` without mutating tag or Release state.

- [ ] **Step 6: Commit and open the review boundary**

Stage only the ten declared files, inspect the staged and committed paths, commit once as `fix(release): resolve stable Actions workflow identity`, then follow `issue-done` to push the branch and create a non-draft PR. Stop before merge unless merge authority is separately explicit.
