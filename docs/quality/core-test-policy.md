# Core Test Policy

## Test Layer Model

Every CTest registration has exactly one execution tier and may add risk labels.
The tier determines the maximum timeout and the kind of behavior it proves:

| Tier | Purpose | Maximum timeout |
| --- | --- | --- |
| `unit` | A single Core Module behavior, isolated from I/O and hosts. | 10 seconds |
| `component` | A module boundary or capability collaboration. | 30 seconds |
| `contract` | A versioned contract, conformance rule, or build invariant. | 120 seconds |
| `host` | An Application Facade consumer or host boundary. | 120 seconds |
| `e2e` | The canonical assembled proof path. | 180 seconds |
| `stress` | A bounded reliability or load scenario. | 300 seconds |

`contract` shares `host`'s budget because the release invariants it holds prove
themselves across real Git and build boundaries: each case performs a real
`git init` with several commits, spawns a child interpreter, and regenerates a
Portal snapshot. Measured without a sanitizer on an M1, the slowest is 42.5
seconds and the fastest of that family is 22.1, while a contract test that
crosses none of those boundaries runs in a fraction of a second. The cap is a
guardrail against parking a slow test in a fast tier, not a budget to spend —
the selection rule below still asks for the lowest tier that can prove the
behavior.

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

This rule is the test-layer form of
[`docs/governance/minimization-principle.md`](../governance/minimization-principle.md):
a test has one reason to fail, and that reason names the defect. The lowest
tier keeps the fixture minimal; it never licenses a weaker assertion.

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
measured on both the reference Mac and the then-pinned CI-equivalent Ubuntu
24.04 Clang/LLVM 18 toolchain after the deterministic, persistence-fault, and
C ABI concurrency suites landed. The Linux pin moved to Clang/LLVM 22 on
2026-09-06 (#693); the same tree was re-measured on 22 against 18 before the
pin moved, see
[`2026-09-06-llvm-22-coverage-measurement.md`](2026-09-06-llvm-22-coverage-measurement.md).
Line denominators are identical on both, 22 counts about 40 fewer covered
lines and fewer branch regions, and every floor below still holds with the
Project Cooker line floor the tightest at three lines. No floor changed:

| Scope | Line floor | Branch floor |
| --- | ---: | ---: |
| Overall | 76% | 64% |
| Foundation | 87% | 92% |
| Authoring Domain | 88% | 85% |
| Project I/O | 65% | 61% |
| Project Cooker | 89% | 71% |
| Audio Runtime | 80% | 67% |
| Provider SDK | 77% | 61% |
| Application Facade | 85% | 64% |

These floors may rise after sustained behavioral coverage lands. They must not
be lowered merely to make CI green.

The Application Facade line floor rose from 84% to 85% on 2026-08-19, after
behavioral tests for previously unexercised failure semantics took the package
from 84.04% to 86.15% on the CI-equivalent Ubuntu toolchain. The margin is
deliberate rather than tight: the same tree measured 3526 and 3522 covered
lines on two Ubuntu runs, so this package carries about ±4 lines of
measurement variance, and a floor must sit outside that band to keep a failure
meaningful. 85% leaves roughly 47 lines of headroom; 86% would have left about
6, which is inside the noise. See
[`2026-08-18-facade-coverage-gate-measurement.md`](2026-08-18-facade-coverage-gate-measurement.md). A toolchain or source-topology change that
invalidates a floor requires a reviewed measurement and policy update, not an
ad hoc threshold edit.

## Deterministic Seeds

Tests that use randomness must take an explicit seed and print it on failure.
The default seed is `0`; a different seed must be fixed in the test command or
fixture. Time, network access, and machine-local state are not random-seed
substitutes and must be controlled or injected.

## Optimistic PR Integration and Incremental Main Self-tests

PR integration no longer requires the retired full-CI/strict-update gate.
The T5 automatic trigger switch requires O1 acceptance. The controller uses
main updates, relevant completion callbacks and independent health ticks;
manual exact-target full requests share its durable execution budget.
Task-specific tests still belong to implementation. Current-head AI review or
visible authorized takeover, real conflict handling, required conversations and
explicit merge permission belong to PR shipping. Full Core/Web Proof, sanitizer,
coverage, packaging and portal suites no longer gate PR merge or run on every
main push. A non-conflicting PR need not update only because main advanced.

There is no daily automatic product test. Main
updates and completion wake the lightweight controller; an independent bounded
control-plane health check may recover existing work but must not start product
tests merely because a date changed. No new changes or explicit eligible work
means no heavy run. The old product schedules and daily-missing alert are
retired together; retained historical readers do not restore those triggers.

For each automatic batch, enumerate every commit in the complete main
first-parent interval from processed SHA to the frozen latest target, including
rename/delete/revert and merge results, not only the net endpoint diff. Union
the deterministic old/new policy floors, authenticated PR review requirements
and eligible verification debt, then close over affected consumers. Host scope
includes behavior/dependencies, not merely compilation. AI is consulted during
PR review, not again after merge; labels are display, not trusted scope records.
Unknown mappings, incomplete history or unprovable policy coverage cannot yield
none: retain conservative full scope or block when history cannot be obtained.
Only explicitly safe explanatory documents without consumers may select none;
that does not discard outstanding debt or failures.

The authoritative full inventory remains the sixteen-suite self-test policy,
including TSan and Release stress; do not hand-copy a shorter inventory or lower
coverage, stress budgets or platform coverage to reduce selection. The frozen
batch runs selected suites once; new merges coalesce into the next target, never
cancel the active batch. Independent suites continue collecting results after a
sibling failure, while failed build dependencies become blocked. Resource locks
still protect timing-sensitive native work.

Each batch pins a verified main-history target independently from its trusted
control revision and records exact run/attempt. Required suite failure, missing
result, cancellation, malformed evidence or unavailable infrastructure never
means success. Incremental verdicts distinguish none/focused/full and give
not-selected reasons; not-required and not-selected are not pass. Persist terminal
results before advancing processed progress, preserving failures independently
from missing/blocked/cancelled/infrastructure debt. Bounded debt recovery pauses
known unavailable work without claiming coverage or repeatedly restarting it
on unrelated docs. New obligations remain recorded; explicit resume is distinct
from report retry. Historical explicit candidates cannot move automatic progress
or clear newer failures/debt.

The separate legacy complete verdict retains the complete sixteen-suite result in
`self-test-verdict-<target>-<run>-<attempt>` for thirty days without overwrite.
Only attempt 1 is accepted: repetition uses a new same-target dispatch, never
an Actions partial rerun that can inherit successful jobs from another attempt.
Early request records are unverified requests, not test evidence.

Failures produce triage Issues, not a merge freeze. Recovery may discharge only
a newly created managed bucket whose authenticated causal/policy identity is
preserved, whose later same-policy result covers every required suite job and
dependency, whose selected suite passed without verification debt, and whose
success-comment and close-patch writes each have durable receipts. Historical,
edited, human-investigated, candidate/node, and independent defect Issues stay
under manual disposition; an unrelated green batch does not change them.
Incremental self-testing does not release or allocate a version; manual
candidate selection consumes only evidence accepted by the canonical release
verifier. Local, PR review, self-test, release, deploy, snapshot and physical
acceptance facts stay separate. Manual exact-target full remains available, but
even a new full result requires independent acceptance by the canonical release
verifier. Focused/none or cross-SHA results cannot be promoted to legacy complete
release evidence. Report recovery consumes verified results through a durable
outbox; unknown Issue POST responses require positive receipt reconciliation or
visible manual follow-up, not blind re-creation.

### Advisory path selection and test ownership

The canonical classifier remains available for local test selection and tracked
path ownership. `focused` unions changed paths' consumer lanes; `full` recommends
all local lanes for broad/unknown risk; legacy `draft` semantics remain an
internal compatibility feature, not merge permission. The fourteen classifier
lanes are distinct from the sixteen complete self-test suites. Renames,
deletions, shared fixtures and generated inputs retain consumer coverage.
Classification does not require every recommended lane to execute before push.

`scripts/ci/scope_policy.json` has a classification-preserving exemption from
the local full recommendation, and only against a proof. The upgrade exists because
scoping a policy change by the policy it changes is circular. That circularity
is real when an edit alters how an existing path routes, and absent when it
only adds a rule for a path the same branch introduces — which is the common
case when a new path needs a new ownership rule. Historically, coupling this
classification to required PR CI charged even that shape a full run: one
research spike spent three rounds of about 185 minutes across three days.
The exemption preserves precise local recommendations; O2 removes the broader
mandatory-run coupling rather than depending on exemptions to unblock merges.

`policy_edit_is_classification_preserving` decides it by differential. It
classifies every path tracked at the merge base under both the base policy and
the head policy and requires the results to be identical; paths the branch
introduces are absent from that set by construction, which is precisely the
exemption being claimed. Because the per-path result carries lanes,
`full_rules` matches and `known_top_levels` admission together, the comparison
covers every routing key. `draft_lanes`, `expensive_families`, `lanes`,
`lane_jobs` and `slo_seconds` never surface per path, so they are compared for
equality instead and any change to them keeps the upgrade.

A second exemption sits alongside it and is proved differently. Policy data that
no classification module reads cannot change which lanes run whatever the edit
does, so it needs no differential and applies unconditionally;
`scripts/ci/hosted_runner_policy.json` is the case, read only by the contract
test that enforces it. Recording a hosted job therefore selects `ci_contract`
rather than the full manifest. Because that claim is about the file's role
rather than about any edit, and because prose about a role goes stale silently,
`tests/build/ci_classification_inputs_test.py` holds it: it fails the moment a
classification module references one of these paths. It matches a literal
filename reference, which is how such a dependency would be written; a path
assembled at runtime would evade it, and that gap is accepted rather than
closed by tracing file handles.

`scripts/ci/local_preflight.py` computes the same differential before it
classifies. The pre-flight preserves the canonical classification semantics, and CI derives the exemption in `change_scope.main` rather than
inside `classify`, so a pre-flight that only called `classify` would report
`full` for a change CI classifies `focused` — the one divergence it exists to
prevent. `tests/build/ci_local_preflight_test.py` holds both the wiring and an
end-to-end case built on a throwaway repository, and the end-to-end case drives
`build_plan` itself: a version that computed the exemption in the test and
passed it to `classify` stayed green with the pre-flight's derivation removed,
which is the miss it exists to catch (#609).

The exemption fails closed and stays narrow. An unreadable, unparseable or
absent base policy keeps the upgrade; it suppresses only the policy file's own
contribution, so a classifier change or a `ci.yml` change in the same branch
still selects `full`; and the policy routes itself to `ci_contract`, without
which the exempted path would merely become unclassified, which is itself a
full-upgrade reason. `tests/build/ci_scope_policy_differential_test.py` holds
each of those cases.

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

### Self-hosted control and untrusted code

Trusted control uses the Contabo general pool, separate from the Netcup heavy
executors. It can retain evidence when those heavy executors are down; it does
not promise availability when all self-hosted control capacity is down. In that
case work queues without buying Linux capacity, and existing durable state is
retained until recovery. The control pool shares general jobs, not an exclusive
reserved listener, and a host-wide Contabo outage remains a recovery gap.
A verdict or reviewer publisher must not run PR-authored control code with
write credentials. Fork or PR content is untrusted; title, label or changed
paths do not grant trust. Carrying a reviewed external patch onto an authorized
in-repository branch creates a new head that needs its own review/verification,
not inheritance of fork evidence. Never provision runner/secrets access merely
to make a fork review green.

`scripts/ci/hosted_runner_policy.json` is the authoritative list of hosted-runner
decisions, and `tests/build/ci_hosted_runner_policy_test.py` enforces it. The
test enumerates every job in `.github/workflows` whose `runs-on` can resolve to
a GitHub-hosted label — a `runs-on` built from an expression counts, because it
may resolve to one — and requires each to carry an entry naming a category and a
reason. Routine Linux control, adjudication and product execution must use
literal self-hosted labels, even if someone adds a hosted allowlist entry.
The controller, completion relay, scope, verdicts, Mac selector, read-only audit
and retired queue diagnostics use `ci-general` plus `contabo`; they never run
on the busy `ci-core` / `ci-web-heavy` executors merely to publish a result.
Remaining categories are `deploy-authority` for credentials deliberately denied
to CI users and `platform` for a recorded exception. `temporary` admits a job
that is *not* justified on the merits and must
name the Issue that removes it. The test also rejects entries whose job no longer
exists or no longer runs hosted, so the list cannot outlive what it describes,
and it separately requires every `ci-core` job to stay off hosted runners.

The Owner explicitly retains paid GitHub-hosted macOS availability recovery:
the MacBook being offline or the selected runner failing to publish a terminal
result may use hosted macOS. Busy alone queues; a published product test failure
is final, not grounds for another paid run. Preserve the existing runner-status
unknown/fork safety behavior. Hosted publication/deployment authority and the
disabled, separately budget-approved untrusted Preview pilot are not migrated
to privileged persistent CI users in the name of cost. This is therefore
**zero routine Linux hosted compute**, not a promise of zero account charges:
macOS recovery, explicit privileged operations and storage remain separate.

This exists because prose drifts. Historical watchdog polling spent hosted
minutes without producing evidence; a workload's short runtime alone does not
justify frequent hosted execution. Adding a hosted job is now
a reviewed act with a written reason rather than the path of least resistance.
`tests/build/workflow_inventory.py` holds the shared scan both this test and the
`ci-core` registration gate read, so the two cannot disagree about what a job is.

### Local Pre-Flight

`scripts/local-ci.sh` uses `local_preflight.py`, `local_lanes.json` and the
canonical classifier. It is explicitly invoked advisory verification, not
merge/release evidence and not an automatic all-PR gate. Use `--lanes` for
Task-relevant work; `--list --json` only classifies. Four lane verdicts are
`pass`, `cached-pass`, `fail` and `not-runnable-here`; unavailable platform,
toolchain or clean-tree packaging preconditions cannot become a pass.

The installed pre-push hook is idle unless `LMDJ_PRE_PUSH_FULL=1` explicitly
requests heavy execution. Migration preserves an exact legacy generated hook
in a backup and never overwrites a personal hook, symlink or conflicting backup,
even with `--force`. See the Git workflow for shared-hook and rollback boundaries.

`--declaration-only --pr-body FILE` validates the body without executing any
lane. The body is never cached; a non-portal change can report not-applicable,
which is not a portal pass. Run the complete portal check locally for affected
Tasks only, while retaining it in every complete self-test batch.

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
carrying that role; additional selected jobs queue behind them. Capacity is no
longer a fixed count: each host runs a baseline of always-on services plus
pre-registered elastic services that are stopped by default, and a host-local,
systemd-timer-driven controller (`scripts/ci/elastic_runner.py`, issue #327)
decides expansion. Netcup runs four baseline services with four elastic
services and an operational ceiling of eight; Contabo runs three baseline
services with three elastic services registered and an operational ceiling of
four — runners 05-06 exist as GitHub identities but stay outside controller
consideration until real queueing evidence from operation at four justifies
the approved ceiling of six.

The controller holds no GitHub PAT and observes only host-local state. It
scales out one service at a time, only when every active service has been busy
for consecutive observations, a cooldown has elapsed, and CPU, slice-memory,
system-memory, and I/O guards all admit one more worst-case job; the memory
guards admit the *next* job rather than the current state and never count swap
as relief, because netcup has none and overshoot there is an OOM kill. While a
ci-core service is running a core job (or one the observer cannot classify,
which is treated as core), scale-out is suppressed: admission guards cannot
shed load already admitted, so timing-sensitive Core work wins by not
admitting more, and baseline services additionally carry a higher CPUWeight
than elastic ones. It scales in the highest-numbered idle elastic service
after a sustained idle window, re-checks a grace window against the
job-assignment race before stopping, and never stops a service with a live
Runner.Worker. Invalid observations fail closed and preserve capacity. Stopped
elastic services heartbeat on a schedule well inside GitHub's 14-day offline
auto-removal window; a heartbeat that cannot reach listener-ready is reported
as a registration loss and never silently retried, because re-registration is
an off-host operation under the no-PAT design. A reboot restores baseline
capacity because only baseline services are enabled. Operational rollback is
`systemctl disable --now lmdj-elastic-runner.timer` plus stopping any active
elastic services; it never deregisters healthy runners. The decision core is
pure and covered by `tests/build/ci_elastic_runner_test.py`.

Per-service CMake builds stay capped at three parallel jobs (four on netcup
units), so services multiply into concurrent compile jobs; the elastic guards,
not a fixed service count, now bound that product. `web-runtime-host` is the
lane most exposed to contention, at roughly 40 minutes on the shared pool
against 16-19 GitHub-hosted; its netcup timings are not yet recorded, so its
75-minute limit stays a hang detector with headroom rather than a performance
budget.

Linux product CI routes by role label; short control also pins the `contabo` origin.
Product lanes do not select a host by that origin label. The Contabo Singapore host,
which also runs LMDJ staging, keeps `shared-with-staging` and carries the
`ci-general` role only, under a resource slice that reserves at least about
2 vCPU and 8 GiB for the application and the OS. The CI-only netcup node
carries `ci-only-host` and the `ci-general`, `ci-web-heavy` and `ci-core`
roles — `ci-core` on its four baseline services only; elastic services on
either host carry no `ci-core`, so burst capacity can never broaden that role
or reach deploy, release, production, sudo, or Docker authority — with all
runner services bounded by the `lmdj-ci.slice` at roughly 14 vCore and 48 GB
and the rest left for the OS and cache maintenance. `ci-core` moved from
Contabo to netcup on 2026-09-06 on a same-revision measurement (#676, decision
on #298): every native Core lane ran faster on netcup, cold cache included, and
the host has no staging co-tenant to protect. Both hosts
also serve as Tailscale exit nodes: that is a documented co-tenant workload
covered by the headroom outside the CI slices, capacity math must never assume
the runners own the host, and degraded exit-node latency during full elastic
load is an accepted effect. Because the controller sees no GitHub queue, a
burst ramps one service per cooldown interval rather than jumping to the
ceiling; that ramp latency is the accepted cost of keeping credentials off the
hosts, not a defect. Routing splits two ways:

- **Self-hosted control on Contabo.** Trust, self-test verdict and macOS
  selection use the general pool pinned to Contabo, separate from Netcup heavy
  workloads. There is no Linux hosted fallback if that control pool is offline.
  Retired Pre-heavy/PR Gate jobs are not PR admission or merge authority.
  The hosted policy retains macOS recovery and separately privileged exceptions.
- **Self-hosted workload, addressed by role.** The four Web lanes — Web
  Toolchain, Web Runtime Host, Creator and Web Runtime Lab — name
  `ci-web-heavy` literally. The five general Linux jobs — Docs / static,
  Architecture Portal, CI contract, Deploy contract and Chameleon Lab — name
  `ci-general` literally. The four native Core jobs — Ubuntu Core, Linux ASan,
  Coverage and Core package — name `ci-core` literally. Architecture Portal
  declares its role inside the called `architecture-portal.yml`, because GitHub
  does not allow a `uses:` job to carry `runs-on`. In the complete self-test batch,
  Release stress and, since #693, TSan also name `ci-core`;
  both join the `lmdj-native-heavy` queue so they never run beside each other.

`ci-core` deliberately does not span both hosts: the persistent native `ccache`
and the preinstalled clang-22/llvm-22 coverage toolchain are shared-host state,
not pool state. Both hosts carry the same Clang/LLVM 22 toolchain, so the role
can be placed on either, but it is registered on exactly one at a time — today
netcup. Two pieces of host state travel with the role rather than with the
machine: the Clang/LLVM 22 pin, which both hosts carry, and the mmap ASLR cap
TSan needs, which is applied only where the role lives. Moving `ci-core` means
running `scripts/ci/host/configure-sanitizer-aslr.sh` on the new host first;
the Nightly lane verifies the cap before it builds, so the omission fails
there with the remedy named rather than silently. Ubuntu's own archive stops at LLVM 18.1.3 for noble, so the pinned
major comes from apt.llvm.org's exact-major `llvm-toolchain-noble-22` suite,
installed by `scripts/ci/host/install-llvm-toolchain.sh`: that script verifies
the repository key against a fixed fingerprint, names the suite rather than
the rolling one, and gives the origin apt priority 100 so it can only supply
packages the distribution lacks. No lane installs anything on the role; an
`apt-get` step there would mutate state the runner services share, so every
Core lane only verifies with `command -v` that the pin is present. Every job that can land on a role carries the
closed trust condition itself, because no selector's fork branch is in its path
any more.

Two dispatch-only benchmarks measure the self-hosted roles and never contribute
a formal result: `ci-self-hosted-benchmark.yml` for `ci-web-heavy` and
`ci-self-hosted-core-benchmark.yml` for `ci-core`. Both require `inputs.revision`
to be 40-hex and exactly equal to the dispatch's trusted `github.sha`, keep
`permissions: contents: read`, target one role literally, and report
`runner_name`, elapsed seconds and host capacity separately. Neither is release
evidence and neither creates a required check. The Core benchmark carries two
properties the Web benchmark does not need. It joins the repository-wide
`lmdj-native-heavy` capacity queue, because separate runner services on the
shared host are not independent CPU capacity and an unqueued measurement would
both corrupt itself and consume a concurrent formal lane's test budgets. And its
job name prefix is registered in `core_job_names`.

That registration is an invariant of the role, not of the benchmark. The elastic
controller prefix-matches the running job name against `core_job_names` to
decide whether to suppress scale-out, and the config validator only requires the
list to be non-empty, so an unregistered `ci-core` job classifies as non-core and
the controller keeps admitting load under timing-sensitive Core work.
`tests/build/ci_benchmark_workflow_test.py` therefore enumerates every job in
`.github/workflows` that names the role and requires each to be registered;
adding a `ci-core` job without registering its name now fails the CI contract
lane rather than silently degrading the host. `lane-default` cache mode and
parallelism 3 reproduce the formal lane; `cold` and any other parallelism
measure a different workload and their timings must not be compared with formal
lane runs.

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
asleep would otherwise delay the complete self-test batch. When the self-hosted lane is selected, GitHub-hosted
macOS may run the same gates only if checkout, acceleration/`ccache` setup,
runner communication, or the 30-minute job limit prevents that lane from
publishing a terminal result. A published preparation, Core Proof, or
sanitizer failure is final and must not start the fallback lane.

Local Mac preflight may run additional focused, Proof, or browser checks before
push, but local results do not replace exact-target complete self-test evidence.

Scheduled TSan runs on `ci-core` since 2026-09-06 (#693), and the route was
accepted on same-revision evidence, not on the compiler move. The history that
kept it Hosted is worth keeping because it is what the evidence had to
overturn. Run 33905688022 dispatched the probe from the branch carrying the
capacity queue, so the two native jobs serialised fourteen minutes apart on
one service instead of starting together, and the probe still failed: every
test died in 0.03 to 0.12 seconds with `FATAL: ThreadSanitizer: unexpected
memory mapping`, the runtime refusing to initialise rather than a test
failing. The 2026-09-04 contended run had shown nine stress tests failing with
no TSan diagnostic at all, which was starvation and said nothing about
compatibility. The cause was the host, not the runner or the compiler: the
6.8 kernel's 32-bit `vm.mmap_rnd_bits`, which no TSan runtime can start under
without re-exec'ing with ASLR off, and which `LockPersonality=true` forbids.
With the host capped at 28 bits by `scripts/ci/host/configure-sanitizer-aslr.sh`
the probe passed on `netcup-lmdj-linux-04` at this Task's revision (run
34030066433, 11/11 stress tests in 52 s against the Hosted lane's 157 s), see
[`2026-09-06-llvm-22-coverage-measurement.md`](2026-09-06-llvm-22-coverage-measurement.md).
The lane now verifies that prerequisite before it builds, so a host that loses
the setting fails naming the remedy instead of with a runtime FATAL or, on some
runtimes, an empty log. The probe job and its dispatch input are gone; a second
TSan lane would only measure a different kernel and drift.

The same run also settled a related question in the other direction.
`core-stress` failed uncontended on that run, so the suggestion that recent
nightly stress failures were sibling contention is not supported: the capacity
queue was in force and the suite still failed. #666 traced that failure to its
mechanism: both self-hosted hosts are KVM guests whose kernels lack
`CONFIG_PARAVIRT_TIME_ACCOUNTING` and `CONFIG_IRQ_TIME_ACCOUNTING`, so the
`CLOCK_THREAD_CPUTIME_ID` gate in `master_fx_stress` was billed hypervisor
steal and hardirq time it cannot consume. The gate now samples the host
accounting counters around every render window and attributes such overruns
instead of counting them; the deadline and the zero-unattributed-overruns
bound are unchanged
([decision](../prd/decisions/2026-09-16-master-fx-stress-attribute-guest-stolen-time.md)).

Both native Nightly jobs join the repository-wide `lmdj-native-heavy` queue.
Naming the `ci-core` role is not enough to serialise them: the role spans
several runner services on one physical host, so a TSan job and the release
stress suite would start in the same second and run beside each other. Run
33838737018 did exactly that on 2026-09-04 and both failed, which made the
probe's result unusable -- it measured contention rather than whether the host
can execute the TSan runtime. A TSan result is only evidence when it runs alone.

The nightly Release stress lane is trusted native workload on `ci-core`: it
runs at most 20 consecutive successful repetitions and stops on the first
failure. It does not retry a failed execution.

## Sanitizer Selection

ASan/UBSan `full` runs the complete non-stress suite and `stress` runs the
bounded stress tier. TSan uses the `native` execution label: `full` runs every
direct native non-stress test, while `stress` runs every direct native stress
test. Python and shell orchestration remain covered by Dev, ASan, Release, and
Product Proof, but never host a TSan-instrumented library in their own process.
ASan registrations receive twice the normal tier timeout and TSan
registrations receive four times the normal tier timeout to account for
instrumentation overhead; the underlying tier and workload remain unchanged.

The two sanitizer presets do not choose a compiler; the lane does. `asan`
inherits the platform default — GCC 13's shared `libasan` on Linux, AppleClang
on macOS — because that runtime has not regressed and the MCP Host tests locate
it by its `libasan.so` name. `tsan` is configured with the pinned Clang on
the Linux lane (`CC=clang-22 CXX=clang++-22` on the configure step of
`core-tsan`), because the TSan runtime is the
reason the pin exists: GCC 13.3's `libtsan` refuses to initialise under the
6.8 kernel's 32-bit `vm.mmap_rnd_bits` with `FATAL: ThreadSanitizer:
unexpected memory mapping`, on both self-hosted hosts (#676, #693). Switching
the compiler is not a pure environment change. Clang on Linux links its
sanitizer runtimes static and whole-archive, and the C++ half defines global
`operator new`/`delete`, which collides with the replacements
`tests/core/audio/realtime_engine_test.cpp` installs to count allocations on
the realtime path. `lmdj_target_sanitizers` therefore links the runtime shared
under Clang on Linux (`-shared-libsan` plus an explicit rpath to the
compiler's `-print-runtime-dir`), which resolves the operators by interposition
exactly as GCC's shared runtimes already do and records the runtime's location
so tests run without `LD_LIBRARY_PATH`.

Moving the compiler does not by itself make TSan run on a self-hosted host.
LLVM 22's runtime handles an incompatible layout the same way LLVM 18's does:
it re-execs itself with `ADDR_NO_RANDOMIZE`, and under the runner units'
`LockPersonality=true` that fails closed with `unable to disable ASLR
(perhaps sandboxing is enabled?)`. The fix is therefore the host, not the
compiler: `scripts/ci/host/configure-sanitizer-aslr.sh` caps
`vm.mmap_rnd_bits` at 28 on the `ci-core` host, the value GitHub's hosted
Ubuntu images carry and the pre-6.6 default, so TSan starts without re-exec
and ASLR stays on. The Owner chose that over `LockPersonality=false` on
2026-09-06 (#693), because the latter would disable ASLR for every CI process
and remove a hardening line to solve one runtime's problem.

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
