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

The Ubuntu selector runs only when a selected lane needs the trusted Linux
pool; the macOS selector runs only for `core_macos`. Fork trust routing,
GitHub-hosted preflight fallback, labels, LFS hydration, bounded build
parallelism, and persistent self-hosted `ccache` behavior remain unchanged.
Selectors do not make a semantic workload conditional on infrastructure
success: a selected job must still publish its formal result.

`PR Gate` is the single aggregate decision. It evaluates same-run static
dependencies and applies this truth table:

| Manifest selection | Job result | Gate result |
| --- | --- | --- |
| selected | `success` | pass |
| selected | `skipped`, `failure`, `cancelled`, or missing | fail |
| unselected | `skipped` | pass |
| unselected | `success`, `failure`, `cancelled`, or missing | fail |

The manifest schema, head SHA, lane-to-job mapping, and complete 18-result key
set must also match. The results are the 15 published lane jobs plus
`select-ubuntu-runner`, `select-macos-runner`, and `macos-primary`;
`change-scope` is the manifest producer, and conditional `macos-fallback` is
enforced transitively by `core-macos` and `core-asan-macos`. The producer is
not a nineteenth result key, but its own job result must independently be
`success`; a manifest output cannot make a later artifact-upload failure pass.

`Change Scope` and every selected lane or support job contribute timing
evidence and a pre-Gate critical-path span to the Gate summary. Queue time is
reported separately; only execution time is compared when the policy defines
an execution SLO, otherwise the summary says `SLO not defined`. The Ubuntu and
macOS selectors do not inherit a consumer lane SLO; `macos-primary` uses the
defined `core_macos` SLO. Missing timing is non-blocking, and SLO observations
are neither timeouts nor correctness assertions. Independent job safety limits
and test-owned behavior timeouts remain hard failures. A slow successful job
stays successful; a failed compile, Proof, test, sanitizer, or Coverage command
is not retried. `main` and manual dispatch always run the full manifest.

## No-Retry Policy

An automated test runs once per requested command. A failure is evidence to
diagnose, not a reason to retry until it passes. A deliberate rerun after a
code or environment correction must be recorded as a new result.

The PR and `main` Core CI Linux workloads prefer the repository's trusted
runner pool whenever at least one online, idle runner carries the
`self-hosted`, `Linux`, `X64`, `lmdj-linux`, and `contabo` labels. Selection is
label-based rather than bound to a runner name, so GitHub assigns each selected
job to any matching free runner. The selector uses GitHub-hosted Ubuntu for an
untrusted fork, a missing status token, a Runner API failure, or a pool with no
online idle matching runner. Selection happens before the workload jobs start;
a semantic failure on the selected lane is final and is not retried on a
GitHub-hosted runner.

The trusted Linux pool currently contains two independent runner services and
therefore executes at most two selected jobs concurrently; additional jobs
queue. Each CI CMake build is capped at three parallel jobs. Native Linux jobs
use the pool's shared checkout-external persistent `ccache`, while Emscripten
jobs deliberately bypass it. The trusted M1 runner uses its own persistent
`ccache` with the same three-job build cap. GitHub-hosted Linux and macOS lanes
keep the cap but do not depend on runner-local persistent caches. Per-job cache
statistics are diagnostic evidence only and never replace semantic gate
results.

The macOS CI fallback is infrastructure recovery, not a test retry. Runner
selection uses GitHub-hosted macOS immediately when the trusted self-hosted
runner is unavailable. When the self-hosted lane is selected, GitHub-hosted
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
