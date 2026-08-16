# Core Test Policy

## Test Layer Model

Every CTest registration has exactly one execution tier and may add risk labels.
The tier determines the maximum timeout and the kind of behavior it proves:

| Tier | Purpose | Maximum timeout |
| --- | --- | --- |
| `unit` | A single Core Module behavior, isolated from I/O and hosts. | 10 seconds |
| `component` | A module boundary or capability collaboration. | 30 seconds |
| `contract` | A versioned contract, conformance rule, or build invariant. | 30 seconds |
| `host` | An Application Facade consumer or host boundary. | 120 seconds |
| `e2e` | The canonical assembled proof path. | 180 seconds |
| `stress` | A bounded reliability or load scenario. | 300 seconds |

Risk labels describe a cross-cutting concern without creating another tier. The
current labels are `persistence`, `audio`, `provider`, `assembly`, `abi`,
`concurrency`, `domain`, and `generated`.

The `native` execution label is assigned automatically when CTest launches a
configured CMake target directly. It is not a risk label. The TSan preset uses
it to cover native tests without injecting the TSan runtime into Python or
shell Host processes.

## Test Selection Rule

Select the lowest tier that can exercise the changed behavior through its
public boundary. Promote a test only when the behavior depends on a real
cross-module, host, or assembled-product collaboration. Do not use an `e2e`
test to replace missing unit, component, or contract coverage.

The required Test Selection Rules are:

1. valid result;
2. stable public errors;
3. failed mutation leaves state unchanged;
4. replay/idempotency;
5. persisted restart/recovery;
6. audio/frame boundaries including overflow/underflow;
7. C ABI ownership/stale handle/concurrent lifetime;
8. cross-module behavior belongs in host/e2e.

## Coverage Thresholds

Changed Core Module behavior needs at least one automated test at its lowest
applicable tier. Changed contract parsing, serialization, or conformance rules
need a contract test for every supported and rejected case. A host or product
assembly change needs its focused host or end-to-end proof in addition to the
lower-tier coverage that owns its behavior. Coverage percentages are a review
signal, not a substitute for these behavior thresholds.

The long-term first-party C++ coverage targets are:

| Scope | Lines | Branches |
| --- | ---: | ---: |
| Overall | 80% | 70% |
| Authoring Domain and Application Facade/C ABI | 90% | 80% |
| Project I/O | 85% | 75% |
| Project Cooker and Audio Runtime | 90% | 80% |
| Provider SDK | 85% | 75% |

The enforced first ratchet is deliberately separate from those targets. It was
measured on both the reference Mac and the pinned CI-equivalent Ubuntu 24.04,
Clang 18, and LLVM 18 toolchain after the deterministic, persistence-fault, and
C ABI concurrency suites landed:

| Scope | Line floor | Branch floor |
| --- | ---: | ---: |
| Overall | 76% | 64% |
| Foundation | 87% | 92% |
| Authoring Domain | 88% | 85% |
| Project I/O | 65% | 61% |
| Project Cooker | 89% | 71% |
| Audio Runtime | 80% | 67% |
| Provider SDK | 77% | 61% |
| Application Facade | 84% | 64% |

These floors may rise after sustained behavioral coverage lands. They must not
be lowered merely to make CI green. A toolchain or source-topology change that
invalidates a floor requires a reviewed measurement and policy update, not an
ad hoc threshold edit.

## Deterministic Seeds

Tests that use randomness must take an explicit seed and print it on failure.
The default seed is `0`; a different seed must be fixed in the test command or
fixture. Time, network access, and machine-local state are not random-seed
substitutes and must be controlled or injected.

## Risk-Based PR Selection

The main CI workflow triggers for every Pull Request without a workflow-level
path filter. `Change Scope` checks out the complete history, diffs the exact PR
base and head, and reads current Draft and `ci:full` label state. Its retained
`ci-scope-<head-sha>` artifact and job summary record one closed manifest with
14 lane booleans and the formal jobs derived from them. Artifact upload uses
same-run overwrite semantics so rerunning `Change Scope` cannot collide with
the retained manifest from its earlier attempt.

Selection has three modes:

- `draft` runs only `docs_static` and `ci_contract`; a transition to Ready
  starts a new classification for the current head;
- `focused` takes the union of every changed path's owners and inherits every
  consumer test lane for shared code, contracts, fixtures, generated inputs,
  renames, and deletions; and
- `full` selects all 14 lanes for `ci:full`, central CI control changes,
  unknown or unclassified ownership, broad cross-family risk, every `main`
  push, and every manual dispatch.

The closed lanes are `docs_static`, `portal`, `ci_contract`, `core_ubuntu`,
`core_asan`, `core_coverage`, `core_macos`, `web_toolchain`,
`web_runtime_host`, `creator`, `web_runtime_lab`, `deploy_contract`,
`chameleon_lab`, and `package`. Path ownership is conservative test
inheritance, not component ownership: a shared fixture or tool selects every
consumer whose behavior could change.

Ownership follows the subject under test, not only the directory the test file
sits in. `apps/web-runtime-host/test/deploy_command_test.py` executes
`scripts/web-runtime-deploy.sh` end to end against a fake Netlify server, so
the policy maps that suite and the three tools it drives —
`apps/web-runtime-host/tools/deploy_orchestrator.py`, `netlify_api.py`, and
`release_bundle.py` — to `deploy_contract` on top of their
`apps/web-runtime-host/` prefix owners. Without those rules, editing the deploy
command selected `deploy_contract` alone and never ran the suite that proves
the command: a fail-open gap inside a policy documented as conservative test
inheritance. The `deploy-contract` job now runs that suite, and
`scripts/web-runtime-host.sh run_nonbrowser_tests` no longer does, so the
Formal Web Runtime Host proof's non-browser phase excludes it while the other
six non-browser suites stay — their subjects remain owned by
`web_runtime_host`. Union semantics cannot subtract a lane, so the suite and
the three tools still select `web_runtime_host` through the directory prefix;
that over-selection is the fail-closed direction and is accepted.

`deploy-contract` runs that suite sharded across worker processes rather than
serially. `--shards N` defaults to `min(4, os.cpu_count())`, is overridable
through `LMDJ_DEPLOY_COMMAND_TEST_SHARDS`, and `--shards 1` is the serial run.
Sharding is safe here and deliberately not applied to the Playwright browser
suites, which stay at `workers: 1`: every test in this suite builds its own
temporary repository, its own fake-command directory, and its own fake Netlify
server on port 0, and its `tearDown` only reads the real evidence root, so
there is no shared timing-sensitive state. The runner partitions the discovered
test ids deterministically, prints each failed worker's own output, and fails
closed when the executed set differs from the discovered set — a silently
dropped test is a failure, not a faster pass.

Two tests are the exception and run alone in a serial phase after the parallel
one: the SIGINT/SIGTERM cases drive the deploy command to a blocking point,
signal its process group, and then assert against bounded readiness and
post-signal cleanup windows. They are the only tests in the file with
wall-clock budgets, and competing shard load can exceed those windows and fail
a correct command. The runner names them explicitly and refuses to start if a
named test no longer exists, so a rename cannot silently return them to the
parallel phase. Widening a timing budget to buy parallelism would weaken the
assertion; giving those two tests an idle machine does not.

`select-macos-runner` is the only runner selector left, and it runs only for
`core_macos`. Every Linux lane names its role literally instead, so no Linux
lane has a runner-selector support job. Package retains LFS hydration and
explicitly disables ccache; the three native Core lanes use the role's
persistent `ccache` unconditionally, because they can no longer land anywhere
that lacks it. Bounded build parallelism is unchanged. A selector does not make
a semantic workload conditional on infrastructure success: a selected job must
still publish its formal result.

`PR Gate` is the single aggregate decision. It evaluates same-run static
dependencies and applies this truth table:

| Manifest selection | Job result | Gate result |
| --- | --- | --- |
| selected | `success` | pass |
| selected | `skipped`, `failure`, `cancelled`, or missing | fail |
| unselected | `skipped` | pass |
| unselected | `success`, `failure`, `cancelled`, or missing | fail |

The manifest schema, exact event base/head SHAs, lane-to-job mapping, and
complete 17-result key set must also match. The results are the 15 published
lane jobs plus `select-macos-runner` and `macos-primary`;
`change-scope` is the manifest producer, and conditional `macos-fallback` is
enforced transitively by `core-macos` and `core-asan-macos`. The producer is
not an eighteenth result key, but its own job result must independently be
`success`; a manifest output cannot make a later artifact-upload failure pass.

`Change Scope` and every selected lane or support job contribute timing
evidence and a pre-Gate critical-path span to the Gate summary. Queue time is
reported separately; only execution time is compared when the policy defines
an execution SLO, otherwise the summary says `SLO not defined`. The macOS
selector does not inherit a consumer lane SLO; `macos-primary` uses the
defined `core_macos` SLO. Missing timing is non-blocking, and SLO observations
are neither timeouts nor correctness assertions. Independent job safety limits
and test-owned behavior timeouts remain hard failures. A slow successful job
stays successful; a failed compile, Proof, test, sanitizer, or Coverage command
is not retried. `main` and manual dispatch always run the full manifest.

### Hosted Control Plane and Head Trust

`Change Scope`, `PR Gate` and `select-macos-runner` stay on GitHub-hosted
`ubuntu-24.04`. Change Scope must publish the exact diff, scope, trust,
and upgrade reasons even when every self-hosted Linux runner is offline, and
the Gate must adjudicate a workload without depending on that workload's host.
These three are the only declared exception to routing Linux work to the
trusted hosts; their minutes are reported as hosted control plane rather than
as routine self-hosted workload. The two macOS adjudicators also run on
`ubuntu-24.04`, but they republish an already produced result under the
required check name and execute no workload.

The scope manifest is `lmdj.ci-scope.v2`. v2 adds exactly one closed boolean
field, `trusted_head`, and `Change Scope` publishes the matching `trusted-head`
job output. Trust is derived only from the event: a non-`pull_request` event,
or a Pull Request whose head repository equals `github.repository`. It is never
derived from a Pull Request title, a label, the changed paths, or the code
under test, because a fork controls all of those. Producer, Gate, and contract
tests migrate to v2 in one commit; a mixed-version run fails closed.

`scripts/ci/scope_policy.json` declares the closed `self_hosted_jobs` set: the
thirteen formal jobs a self-hosted role may ever execute — Docs/static, Portal,
CI Contract, Ubuntu Core, Linux ASan, Coverage, all four Web lanes, Deploy
Contract, Chameleon Lab, and Package. Every one of them requires
`needs.change-scope.outputs.trusted-head == 'true'` in its `if`, including the
jobs still GitHub-hosted during the rollout, so an accidental repository or
routing change fails closed before the first static self-hosted route exists.
The policy validator rejects a missing, extra, duplicate, or non-formal entry
in that set.

`PR Gate` validates `trusted_head` before any job result. When an untrusted
head selects any job in `self_hosted_jobs`, the Gate fails the run and reports
`untrusted fork blocked from self-hosted CI`; the selected-but-skipped jobs
that condition produces remain ordinary truth-table errors as well. A trusted
head keeps the existing selected-success/unselected-skipped table unchanged.
The repository-level private-fork workflow setting remains the primary
boundary, because a fork can edit its own workflow file, and the manifest field
is defence in depth. An external fork that needs formal merge evidence has its
exact patch carried onto a trusted in-repository branch and CI rebuilt on the
new SHA; a fork run is never inherited.

### Local Pre-Flight

`scripts/local-ci.sh` (implemented by `scripts/ci/local_preflight.py` and the
lane command table `scripts/ci/local_lanes.json`) runs the selected lanes on a
developer machine before a push. It reuses `scripts/ci/change_scope.py` and
`scripts/ci/scope_policy.json` directly, so its lane selection is the workflow's
selection rather than a second opinion, and a contract test asserts the command
table covers exactly the canonical lane list.

The pre-flight is advisory and is never evidence. It publishes no job result,
participates in no `needs` graph, and cannot satisfy a manifest-required job.
`PR Gate` remains the single aggregate decision. Four verdicts are reported:
`pass`, `cached-pass`, `fail`, and `not-runnable-here`. A lane whose platform,
toolchain, or working-tree precondition is unmet reports `not-runnable-here`
and never `pass`; the Linux-only core lanes on macOS and `package` against a
modified working tree are the ordinary cases.

Cached verdicts are keyed by a digest of the lane name, its resolved commands,
and the content identity of every repository path the policy maps to that lane.
Paths that force full mode — shared CMake, Contracts, the CI control plane, and
any path the policy does not classify — are inputs to every lane, so a shared
edit cannot leave a stale cached pass behind. A bounded set of recent passing
states is retained per lane so that reverting an edit returns to a cached pass
instead of re-running. The cache lives outside the worktree under
`~/.cache/lmdj/preflight/` and has no path into a CI result.

The command table records, per lane, the CI steps the pre-flight deliberately
does not reproduce — toolchain provisioning, `actionlint`, LFS fixture
rehydration, and the Pull Request body the Portal impact check reads. Those
notes are the declared divergence; anything else diverging is a defect.

## No-Retry Policy

An automated test runs once per requested command. A failure is evidence to
diagnose, not a reason to retry until it passes. A deliberate rerun after a
code or environment correction must be recorded as a new result.

No routine Linux workload can reach GitHub-hosted capacity automatically any
more. Every Linux job names a trusted role literally, and a literal label set
has no fallback branch: a saturated or absent role queues the job instead of
buying paid capacity. `select-ubuntu-runner`, which resolved `runs-on` from a
single Runner API snapshot taken before the workload started, no longer exists.
While it did, one snapshot could divert an entire manifest to paid
infrastructure whenever concurrent runs saturated the pool for an instant — the
dominant cost driver in the 2026-08-12 run history — and its hosted branch
could have been reconnected by a single `needs`. Removing the job removes the
route, along with its result key, its Runner API probe and its use of
`SELF_HOSTED_RUNNER_READ_TOKEN` for Linux.

Busy-versus-absent is now platform behavior rather than workflow logic. GitHub
queues a label-matched job against a loaded role, so a busy role is a latency
condition; an offline or missing role is an availability condition that stays
queued until GitHub cancels the job at its 24-hour queue limit. The terminal
state of a dead role is therefore a cancelled run plus a runner-availability
alert — not an unbounded wait, and not a silent bill.

Concurrency is per role and equals the number of online runner services
carrying that role; additional selected jobs queue behind them. Both hosts run
the approved two services each, so `ci-general` offers four concurrent slots
across the two hosts, `ci-web-heavy` two on netcup, and `ci-core` two on the
Contabo host it shares with LMDJ staging. Raising the count is an operational
change on the existing hosts, not a workflow change. Two per host is bounded
rather than maximal because each CI CMake build is already capped at three
parallel jobs, so services per host multiply into concurrent compile jobs per
host: two services means at most six, which the hosts absorb, while three would
mean nine and would slow every job on the machine. `web-runtime-host` is the
lane most exposed to that contention, at roughly 40 minutes on the shared pool
against 16-19 GitHub-hosted; its netcup timings are not yet recorded, so its
75-minute limit stays a hang detector with headroom rather than a performance
budget.

Linux CI routes by role label rather than by the shared `contabo` origin label,
which is no longer a selection condition anywhere. The Contabo Singapore host,
which also runs LMDJ staging, keeps `shared-with-staging` and carries the
`ci-general` and `ci-core` roles under a resource slice that reserves at least
about 2 vCPU and 8 GiB for the application and the OS. The CI-only netcup node
carries `ci-only-host` and the `ci-general` and `ci-web-heavy` roles, with two
runner services bounded to roughly 14 vCore and 48 GB and the rest left for the
OS and cache maintenance. Routing splits two ways:

- **Hosted control plane, the declared exception.** Change Scope, PR Gate and
  `select-macos-runner` stay on `ubuntu-24.04`. Change Scope decides what runs
  and whether the head is trusted, and PR Gate decides whether the run passed,
  so a self-hosted outage must not be able to take the scope and trust
  evidence down with the jobs it governs. The macOS selector is Hosted for the
  same reason and is deliberately unchanged by this migration.
- **Self-hosted workload, addressed by role.** The four Web lanes — Web
  Toolchain, Web Runtime Host, Creator and Web Runtime Lab — name
  `ci-web-heavy` literally. The five general Linux jobs — Docs / static,
  Architecture Portal, CI contract, Deploy contract and Chameleon Lab — name
  `ci-general` literally. The four native Core jobs — Ubuntu Core, Linux ASan,
  Coverage and Core package — name `ci-core` literally. Architecture Portal
  declares its role inside the called `architecture-portal.yml`, because GitHub
  does not allow a `uses:` job to carry `runs-on`.

`ci-core` deliberately does not span both hosts: the persistent native `ccache`
and the preinstalled clang-18/llvm-18 coverage toolchain are shared-host state,
not pool state. Coverage accordingly no longer installs that toolchain; the
`apt-get` step existed only for the hosted fallback and would otherwise mutate
state both runner services share. Every job that can land on a role carries the
closed trust condition itself, because no selector's fork branch is in its path
any more.

No CI job requires Docker. The CI-only host runs no daemon and the shared
host's runner users are outside the `docker` group, so CI can never reach the
socket that runs production. The CI contract lane accordingly validates
workflows with a checksum-pinned actionlint release archive instead of a
container action, at the same pinned version; a digest names the exact bytes,
where the Docker tag it replaced named only a version.

Runner evidence stays separated. Registration and online status are not
selection, and selection is not success. The real `runner_name`, queue seconds,
execution seconds, billable worker time, and run wall-clock are each reported
on their own, and none of them substitutes for another.

Each CI CMake build is capped at three parallel jobs. Native Linux jobs use the
`ci-core` host's shared checkout-external persistent `ccache` unconditionally,
because they can no longer land on a machine without it, while Emscripten and
Package deliberately bypass it. The trusted M1 runner uses its own persistent
`ccache` with the same three-job build cap. The GitHub-hosted macOS fallback
lane keeps the cap but does not depend on a runner-local persistent cache.
Per-job cache statistics are diagnostic evidence only and never replace
semantic gate results.

The macOS CI fallback is infrastructure recovery, not a test retry. Runner
selection uses GitHub-hosted macOS immediately when the trusted self-hosted
runner is offline, missing, or mislabeled. A busy trusted Mac queues instead,
on the same reasoning as the Linux pool and with more weight behind it:
GitHub-hosted macOS bills at 10.3 times the Linux rate and was 57 percent of
the 2026-08-01..13 Actions spend on 11 percent of the minutes. Offline is
still an availability condition, because a single laptop runner that is
asleep would otherwise hold a Pull Request in the queue rather than merely
delay it. When the self-hosted lane is selected, GitHub-hosted
macOS may run the same gates only if checkout, acceleration/`ccache` setup,
runner communication, or the 30-minute job limit prevents that lane from
publishing a terminal result. A published preparation, Core Proof, or
sanitizer failure is final and must not start the fallback lane.

Local Mac preflight may run additional focused, Proof, or browser checks before
push, but local results do not replace the commit-bound GitHub required checks.

The nightly Release stress lane is bounded stability sampling: it runs at most
20 consecutive successful repetitions and stops on the first failure. It does
not retry a failed execution.

## Sanitizer Selection

ASan/UBSan `full` runs the complete non-stress suite and `stress` runs the
bounded stress tier. TSan uses the `native` execution label: `full` runs every
direct native non-stress test, while `stress` runs every direct native stress
test. Python and shell orchestration remain covered by Dev, ASan, Release, and
Product Proof, but never host a TSan-instrumented library in their own process.
ASan registrations receive twice the normal tier timeout and TSan
registrations receive four times the normal tier timeout to account for
instrumentation overhead; the underlying tier and workload remain unchanged.

## Proof-Scoped C ABI Concurrency Baseline

The C ABI stress suite verifies the behavior already approved and implemented
by Headless Core Proof Task 8:

- the live-engine registry is synchronized;
- operations on one live engine are serialized;
- different live engines may make progress independently;
- `free` racing with an in-flight call is safe because the call retains shared
  state;
- null, unknown, freed, double-freed, and ABA handles remain invalid and safe;
- opaque handle shells are retained for process lifetime to prevent address
  reuse; and
- one shell per successful create is an intentional Proof-stage memory
  tradeoff.

This is verification of the existing Proof implementation, not a new
cross-language product Contract. It does not promise ordering between
concurrent calls on one engine, and it does not promise that caller-owned
response strings may be transferred across threads. A future change to
tombstone lifetime or stable external threading semantics requires its own
approved design and C ABI version review.

## Product Proof and Evidence Boundaries

Coverage and sanitizer gates supplement but do not replace
`scripts/core.sh proof`. Product Proof remains the acceptance evidence for the
Product Assembly, CLI/MCP Product-provider wiring, Golden WAV, Provider
isolation, and Take recovery.

Automated Core gates do not establish browser realtime-audio behavior,
physical MIDI or controller behavior, store sandbox acceptance, release
signing, deployment promotion, or production-service acceptance. Those gates
require their own browser, device, release, deployment, and production
evidence.
