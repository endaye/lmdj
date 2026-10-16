# CI per-host native-heavy queues

Status: in execution. Owner approved on 2026-10-15.

## Outcome and authority

Self-test batches serialise every native-heavy job through one
repository-wide concurrency group, `lmdj-native-heavy`, although its members
run on two physical hosts that share no CPU. The owner asked on 2026-10-15 for
a plan and its execution. The capacity work is split into three Issues; this
plan executes only the first:

| Issue | Scope | Depends on |
| --- | --- | --- |
| #2277 | Split the queue per physical host (this plan, Task Q1) | — |
| #2278 | Register the MBP M4 Pro as overflow macOS runner; pin Release stress to M1 | #2277 |
| #2279 | Bring the Win11 WSL runner online as overflow Linux capacity | #2277 |

Adding runners before Q1 adds no heavy parallelism, because the group admits
one running member across the repository.

## Facts this plan relies on

Recorded at `origin/main` `777391e56ce3a39769496ba98fcab65dbeeaed11`.

- Thirteen jobs carry `group: lmdj-native-heavy`, each with `queue: max` and
  `cancel-in-progress: false`: ten in `ci.yml` (`portal`, `package`,
  `web-toolchain-conformance`, `web-runtime-host`, `creator-web`,
  `web-runtime-lab`, `core-ubuntu`, `macos-primary`, `core-asan`,
  `core-coverage`), two in `core-nightly.yml` (`core-tsan`, `core-stress`) and
  one in `ci-self-hosted-core-benchmark.yml` (`benchmark`).
- Routing: `macos-primary` (selected self-hosted Mac or hosted fallback) and
  `core-stress` (`self-hosted, macOS, ARM64, lmdj`) run on the bare-metal M1;
  every other member runs on Linux. `ci-core` and `ci-web-heavy` are
  registered only on the netcup host.
- No script or controller reads the group name; only workflows, four contract
  tests and documentation name it.
- Seven-day sample (352 jobs, to 2026-10-15): ordinary job wait p50≈0,
  p90≈0.1 min; queue members waited 68–199 min; macOS gates started within
  5 s of the previous member finishing in runs 38588990296 and 38619404365.

## Q1 — Split `lmdj-native-heavy` into per-host queues (#2277)

1. Replace the group on every Linux-routed member with
   `lmdj-native-heavy-linux`, and on `macos-primary` and `core-stress` with
   `lmdj-native-heavy-macos`. Keep `queue: max` and
   `cancel-in-progress: false` unchanged on every member.
2. Update the workflow comments that call the queue repository-wide.
3. Update the four tests that pin the group text
   (`ci_build_acceleration_test.py`, `ci_workflow_topology_test.py`,
   `ci_nightly_workflow_test.py`, `ci_benchmark_workflow_test.py`).
4. Add `test_every_heavy_queue_member_queues_on_the_host_it_runs_on` to
   `tests/build/ci_build_acceleration_test.py`. It reads every workflow and
   catches two defects: a member whose group names a different host than its
   routing (it would run beside that host's timing-sensitive work), and a
   revived host-agnostic group (it would re-serialise both hosts). It also
   pins the member count at 13.
5. Record the amended decision in
   `docs/prd/decisions/2026-10-15-per-host-native-heavy-queues.md`, and update
   `docs/quality/core-test-policy.md`, the portal page
   `apps/docs-site/docs/operations/testing-and-proof.mdx` and
   `.agents/pitfalls/shared-host-runner-capacity.md`.

Declared files: the three workflows above, the four tests, the decision,
this plan, the policy, the portal page and the pitfall.

Lowest-tier tests: the six `tests/build/ci_*` contract suites that read these
workflows (`ci_build_acceleration_test`, `ci_workflow_topology_test`,
`ci_nightly_workflow_test`, `ci_benchmark_workflow_test`,
`ci_pr_review_workflow_test`, `ci_self_test_workflow_test`), plus the
ownership suite `ci_change_scope_test` for the new files. Mutation proof: each
of the three defects (Mac member on the Linux group, Linux member on a
host-agnostic group, `macos-primary` on the Linux group) must fail the new
test, and the restored tree must pass it.

Acceptance after merge: in the next complete self-test batch, macOS gates or
Release stress start while a Linux member is still running, and no two Linux
members overlap. Report the run ID; this is observation, not a merge gate.

## Q2 — Pin Release stress to the M1 and route gates per Mac (#2278)

Status: in execution; owner approved on 2026-10-15 ("同意，先做第 1 步").
Recorded at `origin/main` `0cce10576a774b988f162d7bf15e674e3b9cd5af`.

Premise: `select-macos-runner` checked the M1 by name but emitted the generic
labels `self-hosted, macOS, ARM64, lmdj`, and `core-stress` named the same
set. A second Mac registered with `lmdj` would therefore take Release stress
and the gates without a benchmark and outside its own queue.

1. Runner labels (Runner API, done before the PR): the M1 gains
   `lmdj-mac-m1` and `ci-macos-gates`. The M4 Pro registers later as
   `endaye-mbp-m4-pro` with `self-hosted, macOS, ARM64, lmdj-mac-m4` only.
2. `core-stress` routes to `lmdj-mac-m1` and queues on
   `lmdj-native-heavy-macos-m1`.
3. `select-macos-runner` admits a Mac only while online with its host label
   and `ci-macos-gates`, compared exactly. Order: idle M4 → online M1 → busy
   M4 → hosted. It outputs the runner labels and the queue
   (`lmdj-native-heavy-macos-m1`/`-m4`; hosted keeps the M1 slot), and
   `macos-primary` uses that queue.
4. Register the three labels with actionlint; update the tests that pin the
   old labels and group; replace the selector's text-shape test with tests
   that execute the selector against stubbed Runner API replies.
5. Record the decision and update policy, portal page and pitfall.

Declared files: `.github/workflows/ci.yml`, `.github/workflows/core-nightly.yml`,
`.github/actionlint.yaml`, `tests/build/ci_runner_fallback_test.py`,
`tests/build/ci_build_acceleration_test.py`,
`tests/build/ci_workflow_topology_test.py`,
`tests/build/ci_nightly_workflow_test.py`,
`docs/prd/decisions/2026-10-15-two-mac-runner-routing.md`, this plan,
`docs/quality/core-test-policy.md`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`,
`.agents/pitfalls/shared-host-runner-capacity.md`.

Defects the new selector tests catch: a substring label match admitting the
wrong Mac or an unaccepted one; a busy overflow Mac preferred over the M1;
a hosted selection without a queue. Each was mutation-proven.

Out of this Task: installing the M4 Pro runner (done on that machine), its
benchmark acceptance, and adding `ci-macos-gates` to it afterwards.

## Q3 — Pin the Portal to the Linux heavy host (#2277 follow-up)

Found on 2026-10-15 by the M1 session reviewing the post-#2280 batches and
confirmed here: the `portal` caller in `ci.yml` queues on
`lmdj-native-heavy-linux`, but `architecture-portal.yml` routed by the
dual-node `ci-general` role, so the Portal could run on Contabo (run
38662185311 ran it on `contabo-lmdj-linux-02`) while holding netcup's queue
slot. Q1's cross-workflow test treated every `uses:` member as Linux without
reading the called workflow, so it could not see this.

1. Add `ci-only-host` (registered only on netcup) to the Portal's `runs-on`.
2. Extend `test_every_heavy_queue_member_queues_on_the_host_it_runs_on` to
   resolve a member's called workflow and require every Linux member to route
   by a role only that host carries: `ci-core`, `ci-web-heavy` or
   `ci-only-host`.
3. Update the Portal routing test, the test policy and the portal page.

Declared files: `.github/workflows/architecture-portal.yml`,
`tests/build/ci_build_acceleration_test.py`,
`tests/build/ci_runner_fallback_test.py`, `docs/quality/core-test-policy.md`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`, this plan.

Defect the extended test catches: a Linux heavy-queue member, direct or via a
called workflow, routed by a role another host also carries. Mutation-proven by
reverting the Portal's `runs-on`.

## Q4 — Web lanes overflow to the en-home WSL runner (#2279)

Owner decision 2026-10-16: the en-home workstation takes the four Web lanes,
selected while idle and otherwise falling back to netcup ("4 条 Web lane").
Recorded at `origin/main` `f608cd14`.

Premises: `win11-wsl-lmdj-linux` was registered but offline, with no role
label, so no job could reach it. The Web lanes named the netcup
`ci-web-heavy` role literally. A second host cannot share that role, because
GitHub chooses the runner after the queue group is fixed: it would either
re-serialise two hosts or let a lane hold the wrong host's slot (Q1, Q3).

Host side, done before the PR. The `LMDJ-Runner-Ubuntu` WSL2 distribution
(Ubuntu 24.04, systemd, runner service as `lmdj-runner`) gained git-lfs, the
Playwright 1.62.1 Chromium/WebKit system libraries, and persistent
`/var/cache/lmdj-emsdk`, `/var/cache/lmdj-playwright` and `/var/cache/lmdj-npm`
named in the runner `.env`. `vm.mmap_rnd_bits` is already 28.

1. Add `select-web-runner`. It admits `win11-wsl-lmdj-linux` only while
   online, idle and carrying exactly `lmdj-wsl-enhome` and `ci-web-overflow`,
   and emits the en-home label set with `lmdj-native-heavy-enhome`. Every
   other case emits the netcup `ci-web-heavy` set with
   `lmdj-native-heavy-linux`; there is no hosted branch.
2. The four Web lanes need the selector and use its runner and queue. The
   netcup set and queue are the literal defaults.
3. Register `lmdj-wsl-enhome` and `ci-web-overflow` with actionlint, and
   update the tests that pinned the static route. Add tests that execute the
   selector against stubbed Runner API replies. Allow the Web lanes' dynamic
   `runs-on` in the hosted-spend policy only because the selector emits no
   hosted label set.
4. After merge, add `lmdj-wsl-enhome` and then `ci-web-overflow` through the
   Runner API, and verify with one explicit node batch whose Web lanes run on
   en-home.

Declared files: `.github/workflows/ci.yml`, `.github/actionlint.yaml`,
`tests/build/ci_runner_fallback_test.py`,
`tests/build/ci_build_acceleration_test.py`,
`tests/build/ci_workflow_topology_test.py`,
`tests/build/ci_hosted_runner_policy_test.py`,
`docs/prd/decisions/2026-10-16-web-lanes-enhome-overflow.md`, this plan,
`docs/quality/core-test-policy.md`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`,
`.agents/pitfalls/shared-host-runner-capacity.md`.

Defects the new tests catch: a busy workstation chosen; en-home chosen
without its own queue; a hosted label set emitted by the Web selector.
Each was mutation-proven.

## Completion criteria

- No workflow carries the host-agnostic `lmdj-native-heavy` group.
- Every member's group matches its routed host, pinned across all workflows.
- One post-merge batch shows cross-host overlap without same-host overlap.

## Version Management

Version impact: none. The change touches CI workflows, contract tests and
documentation; no Product Build, Core Module, Provider or Contract identity
changes.

## Documentation impact

Documentation impact: required. Affected portal pages:
`/operations/testing-and-proof`, whose text named the repository-wide queue.
