# LMDJ Serialized Integration Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-owned, label-authorized FIFO Integration Queue that synchronizes one same-repository PR at a time with exact `main`, validates its exact head with full Core CI, and automatically squash-merges only stable protected evidence.

**Architecture:** A hosted `pull_request_target` workflow routes only the exact `merge:queue` label into one job-level `queue: max` concurrency group. A pure Python state machine owns eligibility, synchronization, exact-run validation, drift retry, merge reconciliation, and reporting behind a typed GitHub client; Core CI adds a closed queue-validation mode and machine-readable drift artifact. A separate scheduled watchdog removes stalled authorization when no active queue run can finish the normal fail-closed path.

**Tech Stack:** GitHub Actions YAML, GitHub REST API `2026-03-10`, Python 3.11 standard library, `unittest`, actionlint `1.7.12`, Docusaurus/MDX governance documentation.

## Global Constraints

- Work only on `feat/ci-merge-queue` in the existing isolated worktree; never commit directly on `main`.
- Use `merge:queue` as the sole automatic merge authorization and squash as the sole merge method.
- Use canonical `refs/heads/main`, exact PR head SHA, exact dispatch `workflow_run_id`, and same-run `PR Gate`; never guess a run by name or SHA.
- Keep `main` push concurrency, focused main CI, exact-main release evidence, deployment, publication, and Channel promotion unchanged.
- Use only `GITHUB_TOKEN`; workflow permissions are `actions: write`, `checks: read`, `contents: write`, and `pull-requests: write`.
- Queue worker hard timeout is 360 minutes, internal mutation deadline is 330 minutes, and every validation budget is dynamically derived from remaining time.
- Queue attempts are capped at three; only live-confirmed base/head drift consumes another attempt.
- PRs changing merge authority/control-plane paths are never automatically merged by this queue.
- Version impact: none. The feature changes CI/governance only and allocates no Product Build, Module, Provider, Host, or Contract version.
- Documentation impact: required for `/operations/testing-and-proof/`; update current docs only and create no immutable Portal snapshot.

---

### Task 1: Freeze the reviewed contract and implementation map

**Files:**
- Modify: `docs/superpowers/specs/2026-08-20-lmdj-serialized-integration-queue-design.md`
- Create: `docs/superpowers/plans/2026-08-21-lmdj-serialized-integration-queue.md`

**Interfaces:**
- Consumes: the approved design and review findings dated 2026-08-21.
- Produces: the exact terminal codes, authority boundaries, time budgets, file split, verification commands, and rollout gates used by Tasks 2–7.

- [x] **Step 1: Record the external facts and fail-closed fallbacks**

Add official GitHub/actionlint links, verification date, `queue: max` live probe, numeric dispatch run ID contract, and `validation-dispatch-contract-mismatch` with no run-name polling fallback. Record actionlint issue #657 as a verified schema lag, not as parser support.

- [x] **Step 2: Close the review-discovered state-machine gaps**

Record `already-merged`, `queue-base-drift`, `queue-head-drift`, dynamic attempt budgets, worker finalization, scheduled stall detection, PR-head evidence trust, control-plane self-merge exclusion, explicit squash messages, exact required check names/App ID, canonical main ref, and label revocation window.

- [x] **Step 3: Verify and commit the documentation contract**

Run:

```bash
git diff --check
scripts/architecture-portal.sh check
git diff -- docs/superpowers/specs/2026-08-20-lmdj-serialized-integration-queue-design.md docs/superpowers/plans/2026-08-21-lmdj-serialized-integration-queue.md
```

Expected: no whitespace errors; Portal check exits 0; the diff contains only the reviewed spec and this plan.

Commit:

```bash
git add docs/superpowers/specs/2026-08-20-lmdj-serialized-integration-queue-design.md docs/superpowers/plans/2026-08-21-lmdj-serialized-integration-queue.md
git diff --cached --check
git commit -m "docs(ci): close merge queue review gaps"
```

---

### Task 2: Implement the pure queue state machine

**Files:**
- Create: `scripts/ci/merge_queue.py`
- Create: `tests/build/ci_merge_queue_test.py`

**Interfaces:**
- Consumes: `QueueClient` methods from Task 3 by structural typing; tests use an in-memory fake with the same methods.
- Produces: `QueueRequest`, `QueueReport`, `QueueAttempt`, `QueueClient` protocol, `run_queue_item(request, client, *, clock, sleeper) -> QueueReport`, `finalize_aborted(request, client) -> QueueReport`, and JSON/Markdown report rendering.

- [x] **Step 1: Write failing model and eligibility tests**

Tests construct `QueueRequest(repository="endaye/lmdj", pr_number=220, actor="endaye", event_head_sha="a" * 40, queue_run_id=123)` and assert:

```python
self.assertEqual(run_queue_item(request, fake).code, "unauthorized-actor")
self.assertEqual(run_queue_item(request, fake_merged).code, "already-merged")
self.assertTrue(run_queue_item(request, fake_merged).ok)
self.assertEqual(run_queue_item(request, fake_control_plane).code, "queue-control-plane-change")
```

Cover open/non-Draft/main/same-repository/label/permission/mergeability invariants and require the exact protected path set from the design.

- [x] **Step 2: Run the new test and observe RED**

Run: `python3 tests/build/ci_merge_queue_test.py`

Expected: FAIL because `scripts/ci/merge_queue.py` or the requested types do not exist.

- [x] **Step 3: Implement closed request/report types and eligibility**

Use frozen dataclasses and stable enums/constants. `QueueReport.ok` is true only for `merged`, `already-merged`, and `queue-label-removed`; failure cleanup is represented in the report rather than inferred from exception text.

- [x] **Step 4: Add failing synchronization and deadline tests**

Cover already-up-to-date, update accepted, expected-head 422 drift, conflict, timeout, uncertain response reconciliation, authoritative refs API use, three-attempt cap, and:

```python
budget = validation_budget_seconds(
    now=clock.now(), mutation_deadline=clock.now() + 9 * 60,
    remaining_attempts=1,
)
self.assertEqual(budget, 0)
self.assertEqual(report.code, "queue-budget-exhausted")
```

- [x] **Step 5: Implement synchronization and dynamic budgets**

Use `min(7200, floor((deadline - now - 600) / remaining_attempts))`; refuse a new attempt below 600 seconds. Read `refs/heads/main` before each attempt, send `expected_head_sha`, and reconcile after every uncertain mutation before another write.

- [x] **Step 6: Add failing exact-validation, drift, merge, and cancellation tests**

Assert numeric run binding, exact run event/path/head, same-run named jobs, GitHub Actions App ID `15368`, full manifest queue metadata, live-confirmed drift retry, ordinary CI failure terminal behavior, label checks during every poll, explicit squash title/message, expected head SHA, post-merge tree equality, merge uncertainty reconciliation, and the final label-removal race statement in reports.

- [x] **Step 7: Implement validation and merge transitions**

Only `queue-base-drift`/`queue-head-drift` artifacts independently confirmed by current ref/PR reads return to synchronization. Dispatch schema mismatch never polls. Merge payload is:

```python
{
    "merge_method": "squash",
    "sha": attempt.head_sha,
    "commit_title": f"{pr.title} (#{request.pr_number})",
    "commit_message": "",
}
```

- [x] **Step 8: Add and implement CLI/report behavior**

Provide `run`, `finalize`, and `render-report` subcommands. `run` always writes an atomic JSON report path before returning; `finalize` treats an existing closed report as idempotent and otherwise reconciles, removes a still-live label, and returns `queue-worker-aborted`.

- [x] **Step 9: Verify and commit the state machine**

Run:

```bash
python3 tests/build/ci_merge_queue_test.py
python3 -m py_compile scripts/ci/merge_queue.py
git diff --check
```

Expected: all queue state tests pass and compile/check exit 0.

Commit only the two declared files with `feat(ci): add merge queue state machine`.

---

### Task 3: Implement the GitHub REST boundary and watchdog

**Files:**
- Create: `scripts/ci/github_queue_api.py`
- Create: `scripts/ci/merge_queue_watchdog.py`
- Create: `tests/build/ci_merge_queue_api_test.py`
- Create: `tests/build/ci_merge_queue_watchdog_test.py`

**Interfaces:**
- Consumes: `QueueClient`, `QueueRequest`, `QueueReport`, and report JSON from Task 2.
- Produces: `GitHubQueueClient(repository, token, *, api_version="2026-03-10", opener=urlopen)`, `find_stalled_items(client, *, now, minimum_age_seconds=1200)`, and `reconcile_stalled_item(client, item)`.

- [x] **Step 1: Write failing HTTP contract tests**

Use a recording opener and deterministic response fixtures. Assert structured JSON, auth redaction, bounded pagination/retry, canonical ref reads, PR/files/permission/update/compare/dispatch/run/jobs/check-runs/artifact/commit/merge/label/review endpoints, API version header, and response-schema rejection.

- [x] **Step 2: Run API tests and observe RED**

Run: `python3 tests/build/ci_merge_queue_api_test.py`

Expected: FAIL because the client does not exist.

- [x] **Step 3: Implement the standard-library GitHub client**

Centralize `_request(method, path, payload=None, expected_statuses=...)`; retry reads only for transport/5xx/secondary-rate-limit responses. Mutation callers receive a typed uncertain result on transport ambiguity and must reconcile through Task 2. Parse downloaded `queue-validation` zip in memory and reject duplicate/missing/non-closed JSON entries.

- [x] **Step 4: Write failing watchdog tests**

Cover: younger-than-20-minute labels, active queued/in-progress run, label-event timestamp after an old run, manual cancel, platform timeout, pending eviction, already-removed label, already-merged PR, and idempotent review markers.

- [x] **Step 5: Implement watchdog reconciliation**

The stall signature is an open labeled PR whose latest label event is at least 1200 seconds old and has no associated queued/in-progress `Merge Queue` run created after that event. Re-read PR/label before mutation; remove the label and leave one review containing `<!-- lmdj-merge-queue:queue-stalled:<label-event-id> -->`.

- [x] **Step 6: Verify and commit the API boundary**

Run:

```bash
python3 tests/build/ci_merge_queue_api_test.py
python3 tests/build/ci_merge_queue_watchdog_test.py
python3 -m py_compile scripts/ci/github_queue_api.py scripts/ci/merge_queue_watchdog.py
git diff --check
```

Expected: all API/watchdog tests pass and no syntax/whitespace errors.

Commit the four declared files with `feat(ci): add merge queue GitHub boundary`.

---

### Task 4: Add the hosted queue workflow and actionlint contract

**Files:**
- Create: `.github/workflows/merge-queue.yml`
- Create: `tests/build/ci_merge_queue_workflow_test.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/build/ci_runner_fallback_test.py`

**Interfaces:**
- Consumes: Task 2 CLI commands and Task 3 watchdog CLI.
- Produces: `route`, `queue-item`, `finalize`, `watchdog`, and no-mutation `workflow_dispatch` preflight jobs; fixed job-level `lmdj-merge-main` concurrency with `queue: max`.

- [x] **Step 1: Write failing workflow topology tests**

Assert `pull_request_target.types == [labeled]`, no workflow-level concurrency, `route` has no concurrency, exact label comparison precedes `queue-item`, `queue-item` owns `queue: max`, nonmatching labels skip it, schedule is `*/15 * * * *`, watchdog/finalize do not share queue concurrency, checkout pins canonical default branch and disables persisted credentials, and permissions are exactly actions/checks/contents/pull-requests.

- [x] **Step 2: Observe RED, then add the minimal workflow**

Run: `python3 tests/build/ci_merge_queue_workflow_test.py`

Expected RED: workflow is missing. Add the workflow so label events run the controller, `workflow_dispatch` accepts bounded `hold_seconds` for the three-run preflight, `finalize` runs with `if: always()`, and schedule invokes the watchdog.

- [x] **Step 3: Pin actionlint 1.7.12, its official Linux amd64 digest, and one exact schema-lag exception**

Update the existing actionlint version/digest in `ci.yml`; update the runner contract expected version/archive. Because upstream issue #657 remains open, ignore only `unexpected key "queue" for "concurrency" section` and make the repository contract prove that exactly one `queue: max` exists. Do not change runner routing or formal lanes.

- [x] **Step 4: Verify and commit the workflow**

Run:

```bash
python3 tests/build/ci_merge_queue_workflow_test.py
python3 tests/build/ci_runner_fallback_test.py
python3 tests/build/ci_workflow_topology_test.py
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
```

Then run the verified actionlint `1.7.12` binary over `.github/workflows/*.yml` with that one exact ignore and require exit 0; every other diagnostic remains fatal.

Commit the declared files with `feat(ci): add serialized merge queue workflow`.

---

### Task 5: Add closed Core CI queue-validation mode

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/change_scope.py`
- Modify: `scripts/ci/pr_gate.py`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `tests/build/ci_change_scope_test.py`
- Modify: `tests/build/ci_pr_gate_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_local_preflight_test.py`

**Interfaces:**
- Consumes: queue inputs `queue_ticket`, `queue_pr_number`, `queue_base_sha`, and `queue_head_sha` from Task 2 dispatch.
- Produces: manifest field `queue` (`null` or a closed metadata object), output `pull-request-body`, and `queue-validation.json` classification `valid|queue-base-drift|queue-head-drift|invalid` uploaded even when Change Scope fails.

- [x] **Step 1: Write failing all-or-none and drift-classification tests**

Add unit cases for no queue inputs preserving current semantics, any partial set failing closed, SHA/ticket/PR validation, exact full-only selection, live PR/ref mismatch classifications, same-repository trust, label presence, ancestor proof, and closed validation JSON schema.

- [x] **Step 2: Observe RED and implement queue metadata validation**

Run: `python3 tests/build/ci_change_scope_test.py`

Expected RED on the new cases. Add `QueueValidation` helpers and ensure `main()` writes `queue-validation.json` in every queue-mode path before exit.

- [x] **Step 3: Write failing PR Gate queue binding tests**

Assert queue mode requires full, trusted head, exact ticket/base/head/PR, successful Change Scope, and all same-run formal results. Assert non-queue manifests retain the existing decision table.

- [x] **Step 4: Implement PR Gate binding and workflow threading**

Declare all four dispatch inputs. In queue mode, set base/head from queue inputs, fetch PR body through Change Scope, pass exact range/body to docs/Portal, upload the queue validation artifact with `if: always()`, and keep regular pull_request/push/manual dispatch behavior byte-for-byte equivalent at the interface level.

- [x] **Step 5: Verify and commit Core CI mode**

Run:

```bash
python3 tests/build/ci_change_scope_test.py
python3 tests/build/ci_pr_gate_test.py
python3 tests/build/ci_workflow_topology_test.py
python3 tests/build/ci_local_preflight_test.py
python3 tests/build/ci_runner_fallback_test.py
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
```

Expected: all current and queue-mode contracts pass.

Commit the declared files with `feat(ci): bind queued full validation evidence`.

---

### Task 6: Publish governance, runbook, and Portal truth

**Files:**
- Modify: `docs/governance/git-workflow.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/test/content-inventory.test.mjs`
- Modify: `docs/superpowers/plans/2026-08-21-lmdj-serialized-integration-queue.md`

**Interfaces:**
- Consumes: implemented workflow/state codes from Tasks 2–5.
- Produces: operator procedure for approval-before-label, FIFO limits, exact evidence, cancellation window, stall diagnosis/recovery, control-plane exclusion, main/release separation, and remote preflight/enablement.

- [x] **Step 1: Write the failing Portal content assertion**

Require current `/operations/testing-and-proof/` content to name `merge:queue`, `queue: max`, `queue-stalled`, exact dispatch run ID, control-plane self-merge exclusion, and the fact that exact-main release evidence remains separate.

- [x] **Step 2: Observe RED and update current governance pages**

Run: `node --test apps/architecture-portal/test/content-inventory.test.mjs`

Expected RED on missing queue text. Add concise operator-facing prose and the rollout checklist; do not edit versioned snapshots.

- [x] **Step 3: Mark plan checkboxes with actual evidence**

Check only steps actually completed and add an `## Execution Evidence` table mapping each Task to commit SHA and verification command output summary.

- [x] **Step 4: Verify and commit documentation**

Run:

```bash
node --test apps/architecture-portal/test/content-inventory.test.mjs
scripts/architecture-portal.sh check
git diff --check
```

Expected: Portal content test and full Portal check pass; no immutable snapshot changed.

Commit the declared files with `docs(ci): publish merge queue operations`.

## Execution Evidence

| Task | Commit | Verified evidence |
| --- | --- | --- |
| 1. Reviewed contract | `af11d6ff` | Architecture Portal check: 50 tests, 37 pages, 10 diagrams, 42 routes |
| 2. Pure state machine | `c90b94f4` | `ci_merge_queue_test.py`: 24 tests passed |
| 3. GitHub boundary/watchdog | `fa81865b` | API: 10 tests passed; watchdog: 6 tests passed |
| 4. Queue workflow | `d230e8ac` | Workflow contract and runner contract passed; verified actionlint 1.7.12 binary exited 0 with one exact schema-lag ignore |
| 5. Core CI binding | `af8261ae` | All `ci_*` tests: 286 passed; verified actionlint 1.7.12 binary exited 0 |
| 6. Governance and Portal | `593acc47` | Portal: 50 tests, 37 pages, 10 diagrams, 42 routes; production build passed |

---

### Task 7: Full local acceptance, push, PR, and all-green merge

**Files:**
- No planned source edits; failures return to the owning Task and create a new focused commit.

**Interfaces:**
- Consumes: all prior commits.
- Produces: clean branch, pushed remote branch, one PR declaring full CI and documentation impact, all required checks green, squash merge on `main`, and verified remote post-state.

- [ ] **Step 1: Run the complete local acceptance gate**

Run:

```bash
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
bash tests/build/test_active_tree.sh
bash scripts/verify-core-dependencies.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
git diff --check
```

Run actionlint `1.7.12` with the verified official digest. Expected: every command exits 0.

- [ ] **Step 2: Inspect atomic commit and worktree boundaries**

Run:

```bash
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git status --short --branch
```

Expected: only reviewed queue/spec/plan/governance files and task commits; no staged or unrelated files.

- [ ] **Step 3: Push and create the PR**

Push `feat/ci-merge-queue` to `origin`. Create a PR targeting `main` with:

```text
CI mode: full
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Version impact: none
```

Include the exact local verification evidence and state that this PR changes the queue control plane, so it must be merged through existing branch protection rather than self-labeling.

- [ ] **Step 4: Monitor and remediate until required checks are green**

Watch the exact PR head. For any failure, inspect the failed job/log, reproduce locally where possible, implement the smallest tested fix in a new Conventional Commit, push, and restart monitoring. Never merge a stale SHA or infer green from a different run.

- [ ] **Step 5: Squash merge and verify remote postconditions**

Only after `core (ubuntu-latest)`, `core (macos-latest)`, and `PR Gate` are successful for the current head, request squash merge. Verify PR `merged=true`, `origin/main` points to the merge SHA after fetch, and the resulting `main` workflow run exists; do not create the remote `merge:queue` label or run the first automated queue merge without a later explicit authorization.
