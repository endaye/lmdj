# Test, CI and release script hygiene: follow-up plan

Status: in execution. Owner decisions are recorded under each Task.

## Outcome and authority

The 2026-10-14 audit of test, CI and release/deploy scripts shipped eleven
Pull Requests: #2182, #2183, #2184, #2185, #2186, #2187, #2188, #2189, #2200,
#2204 and #2205. This plan carries the findings those Tasks surfaced but did
not settle, so each one is either delivered, explicitly declined, or tracked.

Goal: every remaining finding has an evidence-backed disposition, the coverage
lane's real state is known, and no follow-up is left only in chat history.

Authority: the owner asked on 2026-10-14 to turn the remaining decisions into an
executable plan. Each Task below is one reviewable Conventional Commit shipped
through `issue-done`; the owner's standing Task authorization applies.
Issue closure, workflow disabling and GitHub Environment creation are external
mutations and need the per-item decision recorded below.

## Facts this plan relies on

Recorded at `origin/main` `c73336028fc033b5549c4952aba60a8cb223c0f6`.
Every Task re-runs `issue-done` §0 at its own base before editing.

- #2188's local run on macOS (Apple LLVM 21) measured the Application Facade
  line ratio at 84.76% against the 85% floor on unmodified main. No recent
  Self-test Report run in the last 60 non-cancelled runs contained a coverage
  job, so the authoritative Linux (llvm-22, netcup) result is unknown.
- `incremental-completion.yml` ↔ `self-test-report.yml` relay is bounded:
  2026-10-13/14 showed one relay and one callback per starting run, about
  135 requests per hour after #2205 (#2185 and #2205 analyses).
- `deploy-default-assets.yml` deploys with `environment: creator-canary`, calls
  Wrangler inline instead of `scripts/asset-server.sh deploy`, has no
  `WRANGLER_SEND_METRICS=false`, no workflow test, and no preview or rollback.
- `deploy-web-runtime-host.yml` and `deploy-creator-web.yml` differ only in
  Host names, paths, Environment and contract identifiers (#2187 analysis).
- `apps/web-runtime-host/tools/cloudflare_host.py` `stage()` runs its
  subprocess without a timeout; only the workflow `timeout 1080s` bounds it.
- `scripts/core-coverage.sh` exports each object twice with identical
  `llvm-cov export` inputs (fragment loop and topology loop at ~366-377), so
  the "fragments missing topology regions" check in `coverage_union.py` cannot
  fail. LLVM 22 supports `--empty-profile`.
- `scripts/ci/report_runtime.py` `drain` computes
  `planned = plan_batch_reports(...)` (~462) and does not use the result; the
  call validates evidence and can raise.
- `ci.yml:46` hard-codes `queue-mode: 'false'`, consumed at `ci.yml:255` for
  `check_documentation_impact`; the merge queue is retired (#2200).
- Workflow "Runner Network Diagnostic" (id 332958195) is registered `active`
  with no file on main; it last ran on 2026-08-12.
- O1 storage Issues #824, #825, #826, #840 and #857 have no writer since #2204.
- Review discovery reports `status: blocked` with about 2,615 pending and 167
  unresolved attempts; no open Issue tracks that backlog. #1048 is closed.
- Pitfall `netlify-new-site-null-disabled` was deleted by #2186; a pitfall for
  "one expensive scan attached to every tick role" was not written (#2205).

## F1 — Establish and repair the coverage lane state

Decision: approved (never lower a floor).

1. Obtain the authoritative Linux result: run the `core_coverage` lane on
   netcup (`scripts/local-ci.sh --lanes core_coverage`, llvm-22) at current main.
2. If every floor passes, record the result here and close F1.
3. If the Application Facade (or any) floor fails, identify the uncovered
   lines from the lcov union and add focused component tests that exercise
   real behavior. Do not lower a floor, widen a filter or exclude sources.

Declared files: tests under `tests/core/` owning the uncovered facade paths
(named after step 1). Tests: `scripts/core.sh coverage check` on Linux.

Result (2026-10-14): every floor passes on Linux, so step 3 is not needed and
F1 is closed. Measured at `origin/main`
`10f30c0d95b4d395446de317bb191a35860d722f` on netcup (Ubuntu 24.04.5,
x86_64, 16 vCPU) with clang and llvm-cov 22.1.8, running the `core_coverage`
lane's four commands from `scripts/ci/local_lanes.json` in a fresh clone with
every LFS object present. The clean run passed 257 of 257 tests and the gate:

| Path | Lines | Floor | Branches | Floor |
| --- | --- | --- | --- | --- |
| overall | 86.83% (64447/74225) | 76 | 72.28% (22485/31108) | 64 |
| `packages/application-facade/` | 85.77% (15505/18077) | 85 | 71.02% (6214/8750) | 64 |
| `packages/audio-runtime/` | 92.74% (5750/6200) | 80 | 82.05% (2757/3360) | 67 |
| `packages/authoring-domain/` | 93.55% (2523/2697) | 88 | 88.26% (1361/1542) | 85 |
| `packages/foundation/` | 95.07% (578/608) | 87 | 95.49% (254/266) | 92 |
| `packages/project-cooker/` | 93.32% (1412/1513) | 89 | 88.27% (542/614) | 71 |
| `packages/project-io/` | 75.95% (13976/18402) | 65 | 66.95% (5685/8492) | 61 |
| `packages/provider-sdk/` | 85.44% (2160/2528) | 77 | 70.78% (821/1160) | 61 |

The Application Facade line ratio is 139 lines above its floor on Linux; the
84.76% macOS reading in #2188 came from Apple LLVM 21 and is not the lane's
instrument. Of three runs, the second was invalidated by a stray profile this
investigation left in the tree, and the first was red before the gate:
`facade.pattern_transport_controller` timed out at its 30 s component budget
while it normally takes 14-15 s, and `facade.pattern_count_in` used 89-91% of
the same budget on every run. `tests/quality/test_budget_report.py` lists
neither, because its registration pattern misses 45 single-line
`lmdj_add_test` calls. #2238 tracks both; no floor, filter, budget or test
changed here.

## F2 — Relay ping-pong disposition

Decision: keep as is (owner, 2026-10-14). Both filters cost more than the
~135 requests/hour they save: a run-name marker is display-only and untrusted
(pitfall `actions-run-name-is-display-only`), and success-only relaying moves
the visible red to Incremental Completion and drops the deliberate recovery
wakeup (pitfall `coalesced-main-wakeup-lost`).
If kept: record the bounded-chain evidence in the existing
`coalesced-main-wakeup-lost` entry. No workflow change.

## F3 — Bring `deploy-default-assets.yml` to the deploy-workflow standard

Decision: dedicated `default-assets` Environment with the same protection as
`creator-canary` (owner, 2026-10-14), so approvals for asset publication are not
shared with the Creator canary. The Environment is created in repository
settings before step 4.

1. Deploy through `scripts/asset-server.sh deploy` instead of inline Wrangler.
2. Set `WRANGLER_SEND_METRICS=false` and per-step `timeout-minutes`.
3. Add `tests/build/default_assets_deploy_workflow_test.py` pinning the
   locked Wrangler install, SHA pins, `persist-credentials: false`, the
   Environment and the script entry point.
4. Switch the Environment only after the owner has created it.

## F4 — One reusable Web Host deploy workflow

Decision: keep two files with a parity test (owner, 2026-10-14). Release
tooling binds each Host to its own caller file: `deployment_effect.py` (jobs
`preflight`/`deploy` and the evidence upload step), `dispatch_evidence.py`
(`preflight` correlation steps), `entry_composition.py` (producer revision is
the last commit touching the caller file) and `hosted_runner_policy.json` (jobs
listed per workflow file).

`tests/build/web_host_deploy_workflow_parity_test.py` replaces each file's
Host-specific values with placeholders and requires identical normalized text.

## F5 — Bound `cloudflare_host.stage()`

Decision: approved. Give `stage()` its own timeout below the workflow's
`1080s`, killing the process group as `run_upload_process` does, and print
captured output on timeout. Test: `cloudflare_host_test.py`.

## F6 — Remove the duplicate coverage export

Decision: approved for reuse; `--empty-profile` is out of scope because it
changes what coverage measures.

Reuse each fragment export as its topology input instead of exporting twice,
and make the topology check meaningful or remove it with its claim. Update
`tests/quality/core_coverage_runner_test.py`. Verify that the lcov union is
byte-identical before and after on the same build.

Delivered: F6 by #2219 (`f96ef1e08`).

## F7 — Small dead-code residues

Decision: approved.

- `ci.yml` `queue-mode: 'false'`: remove the output and make
  `check_documentation_impact` follow the post-#2200 rule; update
  `ci_workflow_topology_test.py`.
- `report_runtime.py` `drain` `planned`: establish from history whether the
  call is an intended evidence validation. If so, name it explicitly; if not,
  remove it. Test: `ci_report_runtime_test.py`.

## F8 — External housekeeping

Decision: approved (owner, 2026-10-14). Done 2026-10-14: "Runner Network
Diagnostic" (id 332958195) is `disabled_manually`; #824, #825, #826, #840 and
#857 are closed as not planned with a comment pointing to #2204.

## F9 — Pitfall ledger

Decision: approved.

- Do not restore `netlify-new-site-null-disabled`; Netlify cannot recur.
- Add `report-scan-repeated-per-tick-role` with gate
  `tests/build/ci_report_progress_test.py` (UTC dates; run
  `ci_pitfall_ledger_test`).
- The F2 relay decision is recorded in `report-scan-repeated-per-tick-role`,
  because the ledger contract has no place to annotate
  `coalesced-main-wakeup-lost` (#2215).

Delivered: F5 by #2211, F7 by #2213, F9 by #2215. F3: PR1 #2212 merged; PR2
#2214 waits on the `default-assets` Environment secret.

## F10 — Track the review-discovery backlog

Decision: approved. Open one Issue recording the blocked review-discovery
backlog (pending/unresolved counts, per-tick progress, owner of recovery), so
the red report run has a tracked cause.

## F11 — Run tests/quality in CI

Decision: approved (owner, 2026-10-14).

Premise: #2219 found `tests/quality/core_coverage_runner_test.py` broken on
`main`. No lane ran it: `tests/quality/` was routed only to `core_coverage`,
whose runner invokes the coverage tools but none of their four suites
(`core_coverage_runner_test.py`, `coverage_gate_test.py`,
`coverage_union_test.py`, `test_budget_report_test.py`). They are pure Python
and take about three seconds, so the `ci-contract` job runs
`python3 -m unittest discover -s tests/quality -p '*_test.py'` in both
`pr-contract.yml` (Pull Request time) and `ci.yml` (main batches);
`scripts/ci/local_lanes.json` lists the same command and
`scripts/ci/scope_policy.json` routes `tests/quality/` and
`scripts/core-coverage.sh` to `ci_contract` as well.
`test_every_quality_test_is_run_by_a_lane_that_owns_it` in
`tests/build/ci_change_scope_test.py` requires every `tests/quality` suite to
be run by a lane command, in that lane's job in each workflow defining it, on
a lane its route selects.

Delivered: F11 by the Pull Request on `fix/quality-tests-ownership`.

## Order

F1 first (it may show a red lane). F5, F6, F7, F9 and F10 are independent and
can run in parallel. F4 after F5 (both touch the Host deploy path). F3 switches
its Environment only after the Environment exists. F2 and F8 are settled.

## Version Management

Version impact: none. These Tasks change CI, deploy and test tooling, tests and
process documents only; no Module, Host, Provider, Contract or Product Build
identity changes. A Task that discovers a version effect records it in its own
Pull Request.

## Documentation Impact

This plan document has no portal consumer. Documentation impact: none.
Reason: `docs/plans` is not projected by the portal. Tasks F3, F4 and F6 check
`/operations/testing-and-proof` and `/operations/version-and-release` and
declare their own impact.

## Pitfall Impact

F9 adds one entry. Each Task searches the ledger by its area labels at start.
