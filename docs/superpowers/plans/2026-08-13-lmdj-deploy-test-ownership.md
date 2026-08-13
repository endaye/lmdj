# LMDJ Deploy Test Ownership and Parallelization Implementation Plan

**Goal:** Close the fail-open gating path where editing
`scripts/web-runtime-deploy.sh` selects a lane that never runs the deploy
command's primary test suite, and remove that suite's 8.5 serial minutes from
the `web-runtime-host` critical path by moving it to the lane that owns its
subject and running it sharded.

**Architecture:** No product source, Module API, Contract, or Proof semantics
change. Test ownership moves in the CI scope policy and the `deploy-contract`
job; the Formal Web Runtime Host proof drops one Python suite from its
non-browser phase; the suite gains a deterministic process-sharding entry
point whose single-shard mode is behaviorally identical to today's serial run.

Evidence (2026-08-13 investigation; run history and local measurements):

- `scripts/ci/change_scope.py::_evaluate_ready_paths` maps
  `scripts/web-runtime-deploy.sh` to `{deploy_contract}`, while
  `apps/web-runtime-host/test/deploy_command_test.py` — the 49-test suite
  that executes that script end to end against a fake Netlify server — maps
  to `{portal, web_runtime_host}`. The `deploy-contract` CI job runs only
  `web_runtime_deploy_workflow_test.py` and
  `web_runtime_public_deployment_docs_test.py` (~6 seconds). Editing the
  deploy command therefore never runs its own suite: a fail-open path inside
  a policy documented as conservative test inheritance.
- The suite copies four sources into each test's fixture repository:
  `scripts/web-runtime-deploy.sh`,
  `apps/web-runtime-host/tools/deploy_orchestrator.py`,
  `apps/web-runtime-host/tools/netlify_api.py`, and
  `apps/web-runtime-host/tools/release_bundle.py`. All four must keep
  selecting the suite after it leaves `web_runtime_host`'s job, or the move
  itself creates the same hole for the three tools.
- On the trusted pool the suite took 512 of the 549 seconds of the proof's
  non-browser Python phase (job 94230153165, 2026-08-12) — 93 percent.
  Local profiling attributes 90 percent of suite time to `run_command`: 75
  deploy-script invocations averaging 3.81 s, each spawning ~23 external
  commands whose test fakes are Python-shebang scripts, i.e. roughly 1,700
  interpreter starts. There are no significant sleeps and no hangs.
- The suite is hermetic per test: each test builds its own temporary
  repository, its own fake-command directory, and its own
  `FakeNetlifyServer` bound to port 0; `tearDown` performs a read-only
  snapshot assertion against the real evidence root. Nothing shares the
  timing-sensitive state that keeps the browser suites at `workers: 1`.

## Global Constraints

- Work on `fix/deploy-test-ownership` in an isolated worktree
  (`.worktrees/deploy-test-ownership`), based on `fix/ci-cost-hardening` at
  `8b31551`: the change depends on Task 6's `scripts/ci/local_lanes.json`
  and edits `ci.yml` regions that branch already touches. Integration
  happens only after the Tasks 1–6 Pull Request merges; rebase onto `main`
  then. Do not modify `fix/ci-cost-hardening` itself.
- This plan does not overturn the recorded owner decision keeping Playwright
  browser suites at `workers: 1`. That decision is about timing-sensitive
  browser fault matrices; this suite is Python `unittest` with no shared
  timing state, which is why sharding it is safe where sharding the browser
  suites is not.
- Union semantics cannot subtract lanes: `deploy_command_test.py` keeps
  matching the `apps/web-runtime-host/` prefix rule and continues to select
  `web_runtime_host` conservatively. Over-selection is the fail-closed
  direction and is accepted.
- Gate semantics unchanged: the PR Gate truth table, the 18-result key set,
  Draft/Ready/push rules, and the no-retry policy are untouched.
  `scripts/ci/` and `ci.yml` edits trigger full-mode CI by policy.
- Sharding must not change test semantics: identical discovered test set,
  deterministic partition, per-test attributable failure output, and the
  single-shard mode behaviorally identical to today's serial run. No test
  may be silently dropped — the runner asserts executed count equals
  discovered count and fails closed on mismatch.
- Each Task is one reviewable Conventional Commit with its declared files
  only; before every commit run the Task-specific tests, inspect the staged
  list, and run `git diff --cached --check`.

## Tasks

### Task 1: Give the deploy suite to the lane that owns its subject — IMPLEMENTED (`6bfe06b`)

Implementation note: `deploy_command_test.py` itself was edited in this Task,
beyond the declared file list. The suite carried
`test_host_nonbrowser_gate_registers_isolated_command_test`, which asserted
the Host script runs it exactly once — true before the move, red after it.
The test was retargeted to assert the `deploy-contract` job runs the suite
exactly once **and** the Host script no longer does, so the guard that keeps
this move from silently reverting survives instead of being deleted.

- `scripts/ci/scope_policy.json`: add exact rules mapping
  `apps/web-runtime-host/test/deploy_command_test.py`,
  `apps/web-runtime-host/tools/deploy_orchestrator.py`,
  `apps/web-runtime-host/tools/netlify_api.py`, and
  `apps/web-runtime-host/tools/release_bundle.py` to `deploy_contract`.
  Union adds; the existing prefix ownership (`portal`, `web_runtime_host`)
  remains on all four.
- `.github/workflows/ci.yml` `deploy-contract` job: run
  `apps/web-runtime-host/test/deploy_command_test.py` alongside the two
  existing tests (Task 2 switches this to the sharded invocation).
- `scripts/web-runtime-host.sh` `run_nonbrowser_tests`: drop
  `deploy_command_test.py`. The other six suites stay — their subjects
  remain owned by `web_runtime_host` and they cost ~37 seconds combined.
- `tests/build/ci_change_scope_test.py` CASES: add the four paths above with
  their new lane sets.
- Documentation in the same Task: `docs/quality/core-test-policy.md` (deploy
  suite ownership, proof composition change, and the gating-hole rationale)
  and `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
  (CI 责任 section: `deploy_contract` now owns the deploy command suite; the
  Host proof's non-browser phase no longer includes it).
- Verify: `python3.11 -m unittest discover -s tests/build -p 'ci_*_test.py'`;
  `python3.11 apps/web-runtime-host/test/deploy_command_test.py` standalone;
  `bash -n scripts/web-runtime-host.sh`;
  `scripts/architecture-portal.sh check`.

Files: `scripts/ci/scope_policy.json`, `.github/workflows/ci.yml`,
`scripts/web-runtime-host.sh`, `tests/build/ci_change_scope_test.py`,
`docs/quality/core-test-policy.md`,
`apps/architecture-portal/docs/operations/testing-and-proof.mdx`.

### Task 2: Shard the suite — IMPLEMENTED with one premise corrected (`a71f9dc`)

Premise correction: this plan claimed the suite shares no timing-sensitive
state. That is true of *state* but was wrong about *wall clock*: two tests
(`test_int_and_term_cleanup_owned_state_without_restore_or_evidence`,
`test_post_publish_int_and_term_reconcile_and_restore_prior_good`) carry
real readiness and post-signal budgets (10 s / 15 s) and both failed an
honest first 4-shard run under competing load. Widening their budgets would
have weakened real assertions, so the runner executes them in a serial phase
after the shards (~18 s) and refuses to start if either named test
disappears, so a rename cannot silently return them to the parallel phase.
Measured: `--shards 1` 383 s, `--shards 4` 196 s (~2x, not the hoped 3x —
the serial phase and spawn-bound load are the difference). Task 2 also
touched the two documentation files beyond its declared list: the sharding
contract sits directly against the recorded `workers: 1` browser decision,
which makes documenting the distinction `required`, not optional.

- Extend the suite's `__main__` (single file preferred; a sibling runner is
  acceptable if the file stays importable unchanged) with a
  `--shards N` mode that partitions discovered test ids deterministically
  across N worker processes, streams each failed worker's output, and exits
  non-zero if any worker fails or the union of executed tests differs from
  discovery.
- Default N: `min(4, os.cpu_count())`, overridable by environment variable;
  `--shards 1` preserves today's behavior exactly.
- `.github/workflows/ci.yml` `deploy-contract` uses the sharded invocation.
  `deploy-contract`'s `timeout-minutes: 15` is expected to hold (the sharded
  suite should run in roughly 2–3 minutes on hosted runners); if measurement
  says otherwise, update the limit and
  `tests/build/ci_workflow_topology_test.py`'s timeout map together.
- Verify: sequential and sharded runs pass with identical test counts;
  record wall-clock for both (expect roughly 3x on 4 cores); a deliberately
  injected failing test surfaces attributably in the sharded output, then is
  removed.

Files: `apps/web-runtime-host/test/deploy_command_test.py`,
`.github/workflows/ci.yml`
(plus `tests/build/ci_workflow_topology_test.py` only if the timeout
changes).

### Task 3: Close the pre-flight drift gap this move exposed — IMPLEMENTED (`599bc77`)

Implementation note: CI pins `--shards 4` (the hosted runner's four vCPUs)
while `local_lanes.json` uses the adaptive default; the divergence is
recorded in the lane's `ci_only` notes, which is the declared-divergence
mechanism for exactly this.

Task 6's contract test asserts only lane-key equality between
`scripts/ci/local_lanes.json` and the scope policy, so a lane's commands can
drift from the workflow silently — exactly what a test moving between lanes
would trigger.

- `scripts/ci/local_lanes.json`: `deploy_contract` gains the sharded suite
  invocation. `web_runtime_host` needs no command change — its commands call
  `scripts/web-runtime-host.sh`, whose composition Task 1 already changed.
- Strengthen `tests/build/ci_local_preflight_test.py`: assert that
  `deploy_contract`'s local commands cover the same Python test files the
  `deploy-contract` workflow job invokes (parse the job body from
  `ci.yml`), so the next ownership move fails a contract test instead of
  drifting silently.
- Verify: `python3.11 -m unittest tests.build.ci_local_preflight_test`;
  `scripts/local-ci.sh --lanes deploy_contract --no-cache` passes locally.

Files: `scripts/ci/local_lanes.json`,
`tests/build/ci_local_preflight_test.py`.

## Follow-up measurement (not a Task)

After merge, re-evaluate `web-runtime-host`'s `timeout-minutes: 75` against
post-move pool durations (expected 25–31 minutes on the trusted pool). 75 was
calibrated to a 40-minute observation plus contention headroom; revisit it
with two to three cache-warm samples from `main`, not preemptively.

## Owner decisions deliberately not taken here

- Overturning `workers: 1` for the Playwright browser suites (recorded owner
  decision; the browser fault matrices are timing-sensitive).
- Converting the remaining Python-shebang command fakes to `/bin/sh`
  (~70 ms per spawn across ~1,700 spawns; medium yield, wide diff — worth a
  separate look only if the sharded suite is still the deploy-contract
  critical path afterward).
- Moving the other six non-browser suites out of the Host proof (their
  subjects stay owned by `web_runtime_host`; no gating hole exists for them,
  and they cost ~37 seconds combined).

## Version Management

Canonical policy: `docs/governance/version-management.md`.

Version impact: none.
Reason: No Module, Host, Provider, Contract, or Assembly identity changes.
The Tasks move test ownership inside the CI control plane, recompose one
proof phase, and add a test-harness sharding entry point; built Product
artifacts remain byte-identical, which the unchanged double-clean-build gates
continue to prove. Precedent: Tasks 1–6 of
`2026-08-13-lmdj-ci-cost-and-reliability-hardening.md` and #115/#116.

## Documentation Impact

Documentation impact: required.

- Affected portal route: `/operations/testing-and-proof/` (the
  `deploy_contract` lane's composition, the Host proof's non-browser phase,
  and the ownership rationale).
- `docs/quality/core-test-policy.md`: deploy suite ownership and the proof
  composition change.
- No Product Build or Assembly change is planned, so no immutable snapshot
  is required.

## Pull Request and Completion Boundary

This branch bases on `fix/ci-cost-hardening` and must not open a Pull
Request before that branch's Tasks 1–6 Pull Request is squash-merged; rebase
onto `main` afterward. Every Task here touches the central CI control plane,
so the integration candidate runs full-mode CI by policy. A green local run
does not authorize push; a green pushed PR does not authorize merge. The
plan is complete when the approved PR is squash-merged and the merged `main`
run shows `deploy-contract` running the sharded suite green and
`web-runtime-host`'s non-browser phase without it, with the wall-clock
reduction visible in the Actions jobs API.
