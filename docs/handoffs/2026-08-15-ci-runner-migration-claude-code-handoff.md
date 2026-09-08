# CI Runner Migration Handoff for Claude Code

**Prepared:** 2026-08-15 (Asia/Shanghai)
**Repository:** `endaye/lmdj`
**Objective:** Complete the approved dual-node self-hosted CI Runner scheme without silently spending GitHub-hosted Linux minutes or weakening trust, test, or release evidence.
**Current remote main:** `8b636b6a9de1ec841651cfefbae2d3bed966c603`

This document is an operational handoff, not a replacement for the approved design or implementation plan. Read these first:

- `AGENTS.md`
- `docs/design/2026-08-14-lmdj-ci-throughput-dedicated-runner-design.md`
- `docs/plans/2026-08-14-lmdj-ci-throughput-dedicated-runner.md`
- `docs/governance/git-workflow.md`
- `docs/governance/version-management.md`
- `docs/governance/architecture-portal.md`

## 1. Authority and safety boundaries

- Work only on a short-lived `feat/*`, `fix/*`, or `docs/*` branch in an isolated worktree. Never edit or commit on `main`.
- A local commit does **not** authorize push, PR creation, merge, deployment, release, tag, publication, or infrastructure mutation.
- The owner previously authorized and completed PRs #140-#143. That authority does **not** automatically cover the new local Creator fix described below.
- Before any new self-hosted routing push, re-query the private-fork setting. Fork workflows, write tokens, and secrets must remain disabled.
- Never execute fork or otherwise untrusted head code on self-hosted infrastructure.
- Keep Change Scope and PR Gate on GitHub-hosted `ubuntu-24.04` as the small control-plane exception.
- Do not restore automatic GitHub-hosted Linux fallback. A saturated self-hosted pool queues; it must not purchase Hosted capacity automatically.
- Do not modify Tailscale unless the owner explicitly asks. It is outside the current fast-path Runner rollout.
- Never print or copy OAuth values, Runner registration tokens, GitHub tokens, SSH private keys, or `~/.cntb.yaml`. The Contabo config is owner-only and was configured with mode `0600`.
- Netcup `en` currently does not have verified passwordless sudo (`sudo -n true` required a password during the last diagnostic). Do not assume privileged access.
- The user-reported Actions budget snapshot was `$100` budget / about `$80` spent for the month. Treat zero automatic Hosted Linux spend as a hard constraint.

## 2. Merged repository work

| PR | Merge SHA | State | Result |
|---|---|---|---|
| [#138](https://github.com/endaye/lmdj/pull/138) | `1563e7b1` | merged | Approved design and implementation plan |
| [#140](https://github.com/endaye/lmdj/pull/140) | `978635d3` | merged | Dispatch-only, non-authoritative self-hosted Web benchmark workflow |
| [#141](https://github.com/endaye/lmdj/pull/141) | `9eb234b1` | merged | Preserved shared cache permissions under Runner hardening |
| [#142](https://github.com/endaye/lmdj/pull/142) | `9544a783` | merged | Trusted the exact shared emsdk checkout per job |
| [#143](https://github.com/endaye/lmdj/pull/143) | `8b636b6a` | merged | Published the Web control bridge before readiness |

PR #143's required CI run was `31868970722`; all formal lanes and PR Gate passed before merge. `web-runtime-host` ran on `contabo-lmdj-linux-02` and passed.

## 3. Live Runner projection

The GitHub Runner API most recently showed all five production runners online and idle:

| Runner | Role labels | Notes |
|---|---|---|
| `contabo-lmdj-linux` | `lmdj-linux-pool`, `shared-with-staging`, `ci-general`, `ci-core` | Contabo host shared with staging |
| `contabo-lmdj-linux-02` | same | Second service on the same Contabo host |
| `netcup-lmdj-linux` | `lmdj-linux-pool`, `netcup`, `ci-only-host`, `ci-general`, `ci-web-heavy` | Netcup CI-only host |
| `netcup-lmdj-linux-02` | same | Second service on the same Netcup host |
| `endaye-mbp-m1` | `macOS`, `ARM64`, `lmdj` | Existing macOS primary |

`win11-wsl-lmdj-linux` is registered but offline. It is accurately labelled `wsl,win11-host`; never add `contabo` merely to make an old selector match.

Read-only service checks most recently returned `active` for both Contabo services and both Netcup services.

Useful SSH aliases:

- `ssh sg` — Contabo/staging host.
- `ssh vienna` — Netcup CI-only host; login user `en`.

Do not confuse `online/idle` with CI integration. Formal evidence requires the Actions job's `runner_name`, conclusion, queue duration, execution duration, and resource output.

## 4. Current GitHub security and branch protection

The private-fork Actions endpoint most recently returned:

```json
{
  "run_workflows_from_fork_pull_requests": false,
  "send_write_tokens_to_workflows": false,
  "send_secrets_and_variables": false,
  "require_approval_for_fork_pr_workflows": false
}
```

The first three `false` values are the binding safety boundary. Recheck with:

```bash
GH_TOKEN="$(gh auth token --user endaye)" gh api \
  repos/endaye/lmdj/actions/permissions/fork-pr-workflows-private-repos \
  | jq -e '
      .run_workflows_from_fork_pull_requests == false and
      .send_write_tokens_to_workflows == false and
      .send_secrets_and_variables == false
    '
```

Current strict branch protection requires:

- `core (ubuntu-latest)`
- `core (macos-latest)`
- `PR Gate`

Do not change branch protection as an incidental part of a routing Task.

## 5. Immediate blocker: local Creator transition fix

### State

- Branch: `fix/creator-open-transition-barrier`
- Worktree: `/Users/endaye/Projects/lmdj/.worktrees/creator-open-transition-barrier`
- Commit: `9f0549f6f3edf1223cf03ad1ac3d9f230f7cab2e`
- Base: exact merged main `8b636b6a9de1ec841651cfefbae2d3bed966c603`
- Worktree: clean
- Remote branch: not pushed
- PR: not created
- Merge: not authorized

### Root cause

Creator benchmark run [31870707291](https://github.com/endaye/lmdj/actions/runs/31870707291) failed on `netcup-lmdj-linux` in:

```text
suspend and reload require explicit reopen and explicit reactivation
```

The test clicked `Open Project 00000000`, immediately saw the still-visible and still-enabled original Open button, classified that unchanged UI as a completed `open` outcome, and exhausted all eight explicit attempts before React/runtime state transitioned. The full failing job took 283 seconds and had ample CPU/memory; this was not load or OOM pressure.

The fix adds an enabled-open exit barrier before classifying ready/busy/replacement outcomes in both:

- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`

It preserves:

- `MAX_OPEN_ATTEMPTS = 8`;
- the existing 500 ms busy retry pacing;
- `OPEN_TRANSITION_TIMEOUT_MS`;
- the final heading and alert assertions;
- all product behavior.

### Verification already completed

- `node --check` for both changed specs: passed.
- `git diff --check`: passed.
- Full `scripts/creator-web.sh proof`: passed.
  - two clean Emscripten builds were byte reproducible;
  - Creator Vitest: 62/62;
  - Python package/server tests: 10/10;
  - runtime/session Node tests: 88/88;
  - Chromium: 13 passed, 1 skipped;
  - WebKit capability gate: 1 passed.
- `scripts/architecture-portal.sh check`: passed, including 42 built routes/internal-link validation.
- Independent review: Spec compliance PASS and Code quality PASS; no Critical, Important, or Minor findings.

### Required next authority

Ask the owner for this exact transition before touching GitHub:

> 授权 push `fix/creator-open-transition-barrier`、创建 PR、CI 通过后合并，并继续 Creator 三次连续 warm 与 dual-load benchmark。

After authorization, verify the branch and push:

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/creator-open-transition-barrier
git status --short
git log -1 --oneline
git diff 8b636b6a9de1ec841651cfefbae2d3bed966c603..HEAD --check
git push -u origin fix/creator-open-transition-barrier
```

Create a PR titled:

```text
fix(creator): await project open transition
```

Expected v1 scope classification is focused with only lane `creator=true` and required job `creator-web`. Suggested declarations:

```text
Expected mode: focused
Expected selected lanes: creator
ci:full required: no
Version impact: none
Documentation impact: none
Release impact: none
```

Reasons: this is test-harness synchronization only; it changes no Product Build, module/provider/contract version, user-visible behavior, portal truth, release state, deployment, or Channel.

Wait for the new run's `creator-web` and `PR Gate`, inspect `runner_name`, and do not merge on the strength of the local proof alone. Merge requires separate explicit owner authorization if it has not been granted in the same message.

## 6. Benchmark evidence so far

These are diagnostic samples, not an accepted Task 4 gate:

| Lane | Run | Exact SHA | Result | Runner / elapsed |
|---|---:|---|---|---|
| Web Toolchain cold | [31856802345](https://github.com/endaye/lmdj/actions/runs/31856802345) | `9544a783` | pass | `netcup-lmdj-linux-02`, 344 s |
| Web Runtime Host cold | [31857107837](https://github.com/endaye/lmdj/actions/runs/31857107837) | `9544a783` | pass | `netcup-lmdj-linux-02`, 417 s |
| Creator cold | [31870253829](https://github.com/endaye/lmdj/actions/runs/31870253829) | `8b636b6a` | pass | `netcup-lmdj-linux-02`, 279 s |
| Creator warm #1 | [31870478567](https://github.com/endaye/lmdj/actions/runs/31870478567) | `8b636b6a` | pass | `netcup-lmdj-linux-02`, 281 s |
| Creator warm #2 | [31870707291](https://github.com/endaye/lmdj/actions/runs/31870707291) | `8b636b6a` | **fail** | `netcup-lmdj-linux`, 283 s |

The failed warm sample resets the consecutive-success streak. Do not rerun it as though it passed, and do not combine the `9544a783` and `8b636b6a` samples into one exact-main acceptance set.

The benchmark workflow currently uses `parallel-level: "4"`. Keep it at 4 unless the accepted **dual-load performance** gate fails. A functional test failure is not authorization to reduce parallelism or relax behavior timeouts.

### Benchmark continuation after the Creator fix merges

Resolve the new exact `origin/main` SHA and use it for every new dispatch:

```bash
git fetch origin main
target_sha="$(git rev-parse origin/main)"
gh workflow run ci-self-hosted-benchmark.yml --repo endaye/lmdj --ref main \
  -f lane=creator -f revision="$target_sha"
```

For the cleanest acceptance record, run on one common exact-main SHA:

1. One Creator cold run after the merge.
2. Three consecutive warm successes for `web_toolchain`.
3. Three consecutive warm successes for `web_runtime_host`.
4. Three consecutive warm successes for `creator`.
5. Dual-load pair: `web_runtime_host` + `creator` dispatched together.
6. Dual-load pair: `web_toolchain` + `web_runtime_host` dispatched together.

Wait for each serial warm run before dispatching the next. For each sample retain:

- run ID and exact SHA;
- job ID and `runner_name`;
- queue seconds and execution seconds;
- semantic conclusion;
- CPU count and load;
- memory/swap and OOM state;
- cache output;
- worker time and wall-clock as separate quantities.

Task 4 passes only when:

- every lane has at least three consecutive warm successes;
- every lane has at least one dual-load success where applicable;
- dual-load execution is no more than 25% slower than that lane's idle median;
- neither service exceeds the 48 GB slice or causes OOM;
- proof assertions and timeouts remain unchanged.

If the performance gate fails, change parallelism from 4 to 3 in a separately reviewed/authorized change and repeat the benchmark. Do not add a third service and do not relax timeouts.

### Known evidence-retention flaw

On a Chromium failure, `scripts/creator-web.sh` continues to the WebKit capability run. Playwright cleans `tests/platform/web/test-results` for the second invocation, so the workflow's later artifact upload can find no trace. Run `31870707291` demonstrated this (`No files were found`). Do not claim trace retention works. If another failure needs trace evidence, fix retention in its own atomic Task or capture the Chromium output before WebKit runs; do not bundle that unrelated change into the open-transition fix.

## 7. Remaining implementation plan

Do not start Task 5 until Task 4 has accepted run IDs. The plan intentionally uses benchmark acceptance as the routing migration gate.

| Task | State | Required outcome |
|---|---|---|
| 1 | operationally complete | Hardened Contabo services with `shared-with-staging`, `ci-general`, `ci-core` |
| 2 | operationally complete | Two Netcup CI-only services with `ci-general`, `ci-web-heavy` |
| 3 | merged | Dispatch-only non-authoritative benchmark workflow |
| 4 | **in progress / blocked on Creator fix integration** | Accepted cold/warm/dual-load run IDs |
| 5 | not started | Atomic `lmdj.ci-scope.v2`, boolean `trusted_head`, Hosted control plane, fail-closed workload conditions |
| 6A | not started | Route Web Toolchain to Netcup `ci-web-heavy` |
| 6B | not started | Route Creator to Netcup `ci-web-heavy` |
| 6C | not started | Route Web Runtime Host to Netcup `ci-web-heavy` |
| 6D | not started | Route Web Runtime Lab to Netcup `ci-web-heavy` |
| 6E | not started | Route general Linux jobs to dual-node `ci-general` |
| 6F | not started | Route native Core to Contabo `ci-core`; remove Linux automatic Hosted fallback |
| 7 | not started | Prove final role routing on PR and full exact-main |
| 8 | not started | Focus ordinary main pushes; bind release authority to full exact-main evidence |
| 9 | not started | Remote proof of focused main and full release evidence |
| 10 | not started | Seven-day observation and final acceptance record |

Task 5 is one atomic commit. Follow its exact file list, TDD sequence, manifest schema, error string, job allowlist, trust condition, documentation route, and verification commands in the plan. It deliberately preserves current `runs-on` values and the Linux selector until Tasks 6A-6F cut over one lane at a time.

Each Task 6 route is a separate commit, push, PR, full merge, and three-run post-merge evidence boundary. Do not combine all routes into one PR; the rollback granularity is part of the design.

Task 8 must preserve this release-evidence rule:

- a focused ordinary main run cannot authorize a release;
- only a retained `full` manifest from the exact current main SHA, plus the same-run successful Gate, can provide release authority.

## 8. Current workflow truth that still needs replacement

At `8b636b6a`:

- scope manifest is still `lmdj.ci-scope.v1`;
- ordinary push and unscoped dispatch still force `full`;
- Linux workload still goes through `select-ubuntu-runner`;
- the selector requires the historical `contabo` label;
- busy capacity already queues instead of selecting Hosted;
- Hosted Linux may still be selected when the token is unavailable, Runner API fails, or no matching runner is online;
- `creator-web` and `web-toolchain-conformance` remain pinned to `ubuntu-24.04` in formal CI;
- static role routing and zero automatic Hosted Linux fallback are therefore **not complete**.

Do not report the Runner migration complete merely because the benchmark workflow can reach Netcup.

## 9. Suggested resumption checklist

```text
[ ] Read AGENTS.md, the design, and the full implementation plan.
[ ] Fetch origin/main; do not trust the local main checkout as current.
[ ] Inspect fix/creator-open-transition-barrier commit 9f0549f6 and clean status.
[ ] Confirm owner authorization before push/PR.
[ ] Re-query private-fork Actions settings immediately before push.
[ ] Push/create PR with focused Creator scope declarations.
[ ] Require creator-web + PR Gate success and real runner_name evidence.
[ ] Obtain explicit merge authorization, merge, and resolve the new exact main SHA.
[ ] Complete the exact-SHA Task 4 benchmark gate.
[ ] Only then implement Task 5 in a fresh isolated worktree using TDD.
[ ] Preserve one-Task/one-commit/one-PR rollout and stop at every authority boundary.
```

## 10. Useful read-only commands

```bash
# Current remote authority
git fetch origin main
git rev-parse origin/main
git log --oneline -10 origin/main

# Live runners and labels
gh api repos/endaye/lmdj/actions/runners --paginate \
  --jq '.runners[] | [.name,.status,.busy,(.labels|map(.name)|join(","))] | @tsv'

# Branch protection
gh api repos/endaye/lmdj/branches/main/protection/required_status_checks

# Benchmark inventory
gh run list --workflow ci-self-hosted-benchmark.yml --event workflow_dispatch \
  --limit 50 --json databaseId,headSha,status,conclusion,createdAt,updatedAt,url

# One run's jobs and actual runner assignment
gh api repos/endaye/lmdj/actions/runs/RUN_ID/jobs?per_page=100 \
  --jq '.jobs[] | [.id,.name,.runner_name,.status,.conclusion,.started_at,.completed_at] | @tsv'

# Existing formal CI truth
rg -n 'manifest_schema|select-ubuntu-runner|runs-on:|trusted-head' \
  scripts/ci/scope_policy.json .github/workflows/ci.yml scripts/ci/change_scope.py
```

## 11. What not to do

- Do not push the handoff branch or Creator fix without owner authorization.
- Do not merge because local proof or an online Runner looks healthy.
- Do not route untrusted fork heads to self-hosted runners.
- Do not move Change Scope or PR Gate onto self-hosted infrastructure.
- Do not treat busy as a Hosted fallback condition; it already queues correctly.
- Do not weaken Playwright assertions or increase behavior timeouts to make the benchmark green.
- Do not label WSL or Netcup as `contabo`.
- Do not use `git reset --hard`, overwrite unrelated worktrees, or clean user-owned branches.
- Do not mix run evidence from different exact-main SHAs into one accepted benchmark set.
- Do not claim `focused main` or release authority work is complete before Tasks 8-9 are remotely proven.
