# Main Full-Lane Sweep Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task.

**Issue:** #543
**Authority:** `docs/governance/version-management.md` already sanctions the
empty-lanes `workflow_dispatch` of `Core CI` as the way to produce full
evidence for a `main` SHA whose own push classified focused;
`docs/governance/git-workflow.md` records focused `main` as a cost decision.
This plan adds the compensating control for that decision's known blind spot
(#443: `creator-web` skipped on consecutive `main` pushes while red).

## Outcome

A scheduled workflow dispatches one empty-input `Core CI` run on the current
`main` head every day at an off-peak time, watches it to completion, and goes
red naming the failed lanes when the dispatched run fails. A red sweep is its
own visible signal (a failed scheduled workflow), not a silent skip.
`ci.yml`, `scripts/ci/change_scope.py`, `scripts/ci/scope_policy.json`, PR
Gate, and the Integration Queue are not modified.

## Design decisions

1. **Reuse the sanctioned mechanism, add no classifier surface.** An empty
   `workflow_dispatch` classifies full (`scripts/ci/change_scope.py:539`) and
   a full manifest must select every lane (`change_scope.py:628`), so the
   sweep runs the complete manifest-selected lane set — it cannot drift from
   what `PR Gate` adjudicates, which adjudicates inside the dispatched run
   itself.
2. **A new wrapper workflow, not a `schedule` trigger inside `ci.yml`.**
   Adding a new event to `ci.yml` would push `schedule` through
   `change_scope`'s closed event truth tables and reopen the classifier for
   no gain. `core-nightly.yml` also stays as-is: its contract tests pin it to
   the sanitizer and stress tiers.
3. **The watcher runs Hosted and only Hosted.** The sweep job itself spends
   its time polling; it must never occupy the shared self-hosted capacity
   queue (`.agents/pitfalls/shared-host-runner-capacity.md`). The dispatched
   `Core CI` run inherits every existing capacity-queue and concurrency rule
   unchanged.
4. **Cron `0 21 * * *`** (05:00 runner-local, UTC+8): two hours after
   `core-nightly.yml`'s 19:00, before the working day, clear of the Monday
   03:00 release audit.
5. **Unconditionally daily; no "already swept" guard.** Honest "this SHA
   already holds full evidence" adjudication requires reading the run's
   retained scope manifest (run names are display-only —
   `.agents/pitfalls/actions-run-name-is-display-only.md`), and a daily
   re-proof also detects runner-environment drift, which is exactly the
   failure class #443 exposed. Recorded as a decision; revisit only if the
   one full run per day measurably crowds the capacity queue.
6. **Deterministic run identity, adjudicated by evidence, never by name.**
   The sweep binds to the dispatched run the same way the Integration Queue
   already does: `scripts/ci/github_queue_api.py::dispatch_validation`
   requires the dispatch response to carry a numeric `workflow_run_id` and
   fails closed otherwise. The sweep reuses that client rather than
   reimplementing dispatch, polling, or retry rules. After completion it
   verifies the run it watched was genuinely a full non-queue run on the
   expected SHA via the run's retained `ci-scope-<sha>` manifest artifact
   (`mode == "full"`, no queue binding), the same evidence surface
   `tools/release/ci_evidence.py` trusts — a coinciding queue dispatch
   therefore cannot be mistaken for a sweep.
7. **The sweep is detection, not authority.** Its success mints no release
   evidence and its dispatch authorizes no release mutation
   (`version-management.md` already says a dispatch is not an authorization).
   Release evidence continues to flow only through
   `tools/release/ci_evidence.py` reading the dispatched run itself.

## Tasks

### Task 1: Sweep controller script with hermetic tests

**Files:**
- Create: `scripts/ci/main_sweep.py`
- Create: `tests/build/ci_main_sweep_test.py`

**Interfaces:**
- Consumes `scripts/ci/github_queue_api.py` primitives for dispatch, run
  polling, and artifact reads; adds no new GitHub client.
- `main_sweep.py run` performs: resolve `main` head SHA → dispatch `ci.yml`
  on `refs/heads/main` with empty inputs → hold the returned
  `workflow_run_id` → poll the run to completion within a fixed budget →
  download and validate the `ci-scope-<sha>` artifact (`mode == "full"`,
  no queue fields, exact head SHA) → on any failure, cancellation, timeout,
  wrong-manifest, or missing-evidence condition, print a `why:`/`remedy:`
  diagnostic plus the failed job names to stdout and the step summary, and
  exit non-zero. Success prints the run URL and the swept SHA.

**Steps:**
- [ ] Write `tests/build/ci_main_sweep_test.py` first (auto-discovered by the
  CI contract lane's `unittest discover -p 'ci_*_test.py'`), with a stubbed
  API client in the house style of `ci_merge_queue_test.py`: happy path;
  dispatched-run failure lists failed jobs and exits non-zero; a manifest
  that is not `full`, carries queue fields, or names a different SHA fails
  closed; a dispatch response without `workflow_run_id` fails closed; the
  poll budget expiring fails closed; no code path parses a run name or
  display title.
- [ ] Implement `scripts/ci/main_sweep.py` against those tests.

### Task 2: The scheduled workflow

**Files:**
- Create: `.github/workflows/main-full-sweep.yml`
- Create: `tests/build/ci_main_sweep_workflow_test.py`

**Steps:**
- [ ] Write `tests/build/ci_main_sweep_workflow_test.py` first, pinning: the
  cron is exactly `0 21 * * *` plus a plain `workflow_dispatch` for manual
  sweeps; permissions are exactly `contents: read` and `actions: write`; the
  single job runs on `ubuntu-24.04` (never a self-hosted label);
  `timeout-minutes` is at most 120; the job invokes
  `python3 scripts/ci/main_sweep.py run` with `GITHUB_TOKEN` from
  `secrets.GITHUB_TOKEN` and passes no `lanes` input anywhere; the
  workflow's concurrency group is its own (`main-full-sweep`) with
  `cancel-in-progress: false`.
- [ ] Implement the workflow against the test. Keep it thin: checkout,
  setup-python, one script invocation — every decision lives in
  `main_sweep.py` where it is unit-tested.
- [ ] Confirm classification needs no policy change: the new workflow path is
  not matched by any `full_rules` entry, so its own PR classifies by the
  ordinary rules; the sweep changes runtime behavior of no existing lane.
  If `change_scope` reports the path unclassified, route it deliberately in
  `scripts/ci/scope_policy.json` in this Task rather than accepting an
  accidental classification (`.agents/pitfalls/scope-policy-top-level-admission.md`).
- [ ] Validate with the pinned actionlint contract exactly as `ci-contract`
  runs it (v1.7.12, sha-pinned, with the single approved
  `concurrency.queue` schema exception).

### Task 3: Documentation

**Files:**
- Modify: `docs/governance/git-workflow.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Steps:**
- [ ] In `git-workflow.md`, extend the focused-`main` cost-decision passage:
  the daily full sweep is the compensating control; a red sweep means `main`
  holds a defect or an environment drift that focused classification has not
  yet surfaced, and it is triaged like a red `main` push.
- [ ] In `operations/testing-and-proof.mdx`, describe the sweep beside the
  nightly: what it dispatches, that its evidence is the dispatched run's own
  scope manifest, and that it mints no release evidence.
- [ ] `scripts/architecture-portal.sh check`.

## Version Management

Version impact: none.

Reason: CI detection control only. No Product, Module, Host, Provider,
Contract, Assembly, or Channel identity changes; no version file is touched.

## Documentation Impact

Documentation impact: required. Routes: `docs/governance/git-workflow.md`
(focused-`main` cost decision gains its compensating control) and
`apps/architecture-portal/docs/operations/testing-and-proof.mdx` (scheduled
proof inventory), both updated in Task 3 of this plan. No identity is
hand-entered.

## Verification

```bash
python3 -m unittest tests.build.ci_main_sweep_test -v
python3 -m unittest tests.build.ci_main_sweep_workflow_test -v
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
scripts/architecture-portal.sh check
```

Plus the pinned actionlint run from Task 2. Expected: every command exits 0
and no existing CI-contract test changes. After merge, one manually
dispatched sweep (`workflow_dispatch` on `main-full-sweep.yml`) is the
acceptance evidence: it must dispatch, watch, adjudicate, and summarize one
full `Core CI` run end to end.

## Constraints

- Work only on `fix/main-full-sweep` in an isolated worktree from
  `origin/main`; never modify or commit on `main`.
- One Conventional Commit:
  `fix(ci): sweep the full lane set on main daily (fixes #543)`.
- Declared files: this plan plus the files listed in Tasks 1–3 (and
  `scripts/ci/scope_policy.json` only if Task 2's classification check
  proves routing is required). Stage nothing else; inspect the staged list
  and `git diff --cached --check` before committing.
- Hard boundaries: no change to `ci.yml`, `merge-queue.yml`,
  `core-nightly.yml`, `change_scope.py`, or `pr_gate.py`; the sweep job
  never runs self-hosted; no logic ever branches on a run name or display
  title; the sweep mints no release evidence.
- At implementation start, search open `.agents/pitfalls/` entries by
  `area:ci-release` per `docs/governance/pitfall-ledger.md`; before
  shipping, follow `issue-done` to record or bump any qualifying pitfall.
- A local commit does not authorize push, Pull Request creation, merge,
  remote workflow dispatch, release, publication, deployment, or Channel
  promotion; ship through `.agents/skills/issue-done/SKILL.md`.
