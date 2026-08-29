# Formal Web Runtime Host Acceptance — 2026-08-03

## Manual diagnostic candidate — 2026-08-06

The current local candidate advances Product Build `1.0.14.0 -> 1.0.15.0`
and Formal Web Runtime Host `1.0.0 -> 1.1.0`. Private protocol `1`, all Core
Module versions, Contracts, Providers, and Models are unchanged. The generated
Assembly Lock and compiled product identity agree with those two version
changes.

The shipped human sequence is exactly:

`Load diagnostic project -> ready -> Activate audio -> running -> trigger`

The primary packaged Chromium journey starts from a fresh origin and uses only
those visible controls before activation. The first Load performs exactly one
Project create, one bounded WAV import, and 64 Pad assignments, producing
revision `65`. Its browser-local descriptor contains only the diagnostic
contract plus Project, Pattern, and Asset UUIDs; none of those UUIDs appears in
DOM diagnostics. One pointer Pad and one mapped keyboard key produce exactly
two admissions and two `voice_started` outcomes. After reload, Load reuses the
same descriptor, performs no create/import/assignment, reopens revision `65`,
and enables activation to reach `running` again before the existing 500-trigger,
Take, restart, rejection, recovery, and timeout journey continues.

### Current local candidate evidence

| Gate | Observed local result |
| --- | --- |
| Focused visible Chromium journey | PASS; `1 passed` |
| Product version, module graph, Assembly Lock, and lock verification | PASS; Product `1.0.15.0`, Host `1.1.0`, protocol `1` |
| `scripts/web-runtime-host.sh proof` | PASS; AudioWorklet Chromium 17/17, two clean packages byte-identical, Python package 14/14, server 7/7, Node 115/115, native Web CTest 3/3, distribution 6/6, all tracked Formal Host specs selected with packaged Chromium 15 passed/1 designed skip, WebKit 1 limitation-path pass/10 capability skips |
| `scripts/web-runtime-lab.sh test` | PASS; 42/42 Node tests plus server and active-tree checks |
| `scripts/core.sh proof` | PASS; 32/32 selected CTests, CLI 10/10, MCP 10/10, package acceptance, Product `1.0.15.0`, Assembly Lock `MATCH` |
| Dependency, active-tree, and diff checks | PASS |
| Architecture Portal current-source preflight | PASS; 34 pages, 9 diagram sources/18 outputs, Product `1.0.15.0` facts, typecheck, optimized build, and current routes/internal links |
| Immutable snapshot lifecycle | Generated only from a clean committed source boundary; existence and provenance are verified separately by the governed Portal command and are not inferred from this current-source row |

This automated Chromium evidence proves deterministic preparation,
browser-local descriptor persistence, pointer/keyboard routing, and exact audio
outcomes. It does not prove acoustic latency, a physical MIDI device,
Safari/iPad touch behavior, or subjective audio quality. It also does not claim
new Pull Request CI, merge, signed tag, Release, deployment, publication, or
Channel promotion. Immutable snapshot existence and provenance are a separate
governed documentation result and do not upgrade Host or physical evidence.

## Task 12A historical outcome

Task 12A assembles Formal Web Runtime Host `1.0.0` into Product Build
`1.0.14.0 · canary`. The packaged Host identifies itself as Product
`1.0.14.0`, Host `1.0.0`, protocol `1`, and the generated Assembly Lock matches
the declared composition. Clean-distribution Web Proof, Web Runtime Lab, Core
Proof, ASan, TSan, release stress, dependency, active-tree, and exact-identity
gates pass locally.

At the Task 12A evidence point, this section did not claim Pull Request CI,
physical-device acceptance, or an Architecture Portal snapshot outcome.
Current Portal truth and immutable snapshot provenance are verified and
reported by their own documentation gates, rather than inferred from the
historical local Host evidence.

At that point no push, Pull Request, merge, tag, Release, deployment,
publication, or Channel promotion had occurred. `lmdj-v1.0.14.0` remains
future tag text only.

## Task 12A historical identity and environment

| Item | Evidence |
| --- | --- |
| Branch | `feat/formal-web-runtime-host` |
| Proof base revision | `1a33838b3bb35fc69de6574e0e4bd7736ac8cbcf` |
| Product display | `1.0.14.0 · canary · g1a33838b` |
| Web package | Product `1.0.14.0`; Host `1.0.0`; protocol `1` |
| Assembly Lock SHA-256 | `26b34e56596dbb0b8ade7797ec8c1a201cb1e296320308e10e16742005760b1e` |
| Machine | MacBook Pro `Mac16,8`, Apple M4 Pro, 48 GB |
| OS | macOS `26.5.2` (`25F84`), arm64 |
| Native toolchain | Apple Clang `21.0.0`; CMake `4.1.3`; Python `3.14.6` |
| Web Proof toolchain | emsdk revision `dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`; Emscripten `6.0.5`; releases revision `dbd755b5da399329c2576f6e3dfa7f419f5d8409`; emsdk runner Node `22.16.0`; runner npm `10.9.2`; locked Playwright `1.62.1` |

The proof ran against the listed base revision plus the uncommitted Task 12A
diff. The final atomic commit SHA is intentionally not invented inside its own
pre-commit acceptance record.

## Task 12A historical version propagation

| Product, Module, or Host | Previous | Candidate | API |
| --- | --- | --- | --- |
| Product Build | `1.0.13.0` | `1.0.14.0` | — |
| Web Runtime Host | absent | `1.0.0` | `1` |
| Project I/O | `0.3.1` | `0.4.0` | `1` |
| Audio Runtime | `0.3.1` | `0.4.0` | `1` |
| Application Facade | `1.1.2` | `1.2.0` | `2` |
| Core CLI | `1.0.4` | `1.0.5` | `2` |
| Core MCP | `1.1.1` | `1.1.2` | `2` |
| Native Test Host | `1.0.2` | `1.0.3` | `1` |
| Project Cooker | `0.2.1` | `0.2.1` | `1` |

Web Runtime Host declares exactly Application Facade `1.2.0` and Audio Runtime
`0.4.0`; it does not declare Project I/O. Product CMake links the compiled
catalog object to the Web target only when `lmdj_web_runtime_host` exists.
Assembly JSON, generated lock, compiled catalog, manifests, MCP Python package,
CLI/MCP/Native Host assertions, package manifest, and Core Proof agree on the
candidate identities. Contracts, Providers, Capability declarations, and model
identities are unchanged.

## Task 12A historical automated evidence

| Gate | Local result |
| --- | --- |
| `scripts/web-runtime-host.sh proof` | PASS; independent AudioWorklet Chromium 13/13, two clean builds/packages, byte reproducibility, Python package 12/12, server 7/7, Node 82/82, native Web CTest 3/3, distribution 6/6, packaged Chromium 9 passed/1 skipped, WebKit 1 passed/5 capability skips |
| `scripts/web-runtime-lab.sh test` | PASS; 42/42 Node tests plus server and active-tree checks |
| `scripts/core.sh proof` | PASS; 31/31 selected CTests; Product `1.0.14.0`, Channel `canary`, Assembly lock `MATCH` |
| `scripts/core.sh configure asan` / `build asan` / `test asan full` | PASS; 47/47 |
| `scripts/core.sh configure tsan` / `build tsan` / `test tsan full` | PASS; 26/26 native-label tests; no TSan report |
| `scripts/core.sh configure release` / `build release` / `test release stress` | PASS; 2/2 stress tests |
| `scripts/core-coverage.sh check` | PASS; 48/48 tests; 31 module signatures match 31 coverage objects; overall lines `79.78%`, branches `68.40%`; Application Facade lines `84.02%`, branches `68.04%`; every module threshold passes |
| Architecture Portal current gates | PASS at Task 12A acceptance; 34 current pages, 9 diagram sources/18 outputs, Product `1.0.14.0` facts, typecheck, optimized build, and current route/link checks. Immutable snapshot provenance is reported separately. |
| `bash scripts/verify-core-dependencies.sh` | PASS |
| `bash tests/build/test_active_tree.sh` | PASS |
| Product version, module graph, Assembly Lock, and lock verification | PASS; Product `1.0.14.0` |
| `git diff --check` | PASS |

The WebKit result is a structured `UNSUPPORTED_WEB_RUNTIME` limitation for
`opfsSyncAccessHandle` and `opfsWritableReplace`; five skipped tests are not
reported as WebKit product acceptance. The automated browser journey is also
not acoustic, MIDI-device, latency-camera, or iPad evidence.

At this acceptance point, current-page typecheck, optimized build, and the
37-route/internal-link build check passed. This record neither upgrades that
local evidence to remote CI nor weakens the separate release-document gate.

## Task 13A reviewed deadline and transport follow-up

The reviewed follow-up defines Project mutation publication claim as the
deadline-cancellation cutoff. Responsive cancellation returns `HOST_TIMEOUT`,
fails and seals the Host, removes staged transaction/checkpoint/artifact files,
consumes the Control owner's native release completion, and reopens the
unchanged Project on the first attempt. The caller cutoff starts before the
synchronous JavaScript-to-Wasm envelope/sidecar copy and remains the native
publication upper bound even while the main-thread timer is blocked. Forged and
replayed BroadcastChannel ACKs plus duplicate release requests cannot
manufacture native completion; the one-shot authorize/complete/consume state
accepts at most one real completion and rejects later consumption. The
separately forced-unresponsive case proves that channel ACKs without native
completion cannot skip the retained 100 ms termination fallback; its non-Truth
staging residue is removed by the first reopen before inspect and explicit
retry.

When publication claims before the caller deadline, the packaged production
transport returns the real committed success or aborted `IO_ERROR` after the
deadline instead of inventing `HOST_TIMEOUT`. A deadline-after-claim cancel call
is observed once as `publish-claimed`. Claimed settlement is bounded by the
exact 1,000 ms production watchdog; proof-only tests may inject 1–1,000 ms. A
permanent claim hang returns typed `HOST_RESTART_REQUIRED` with
`terminal_state: restart-required` and `mutation_outcome: unknown`, seals and
terminates the Host, and permits old-or-new reopen truth plus inspect/retry.

The source-shell controller delegates each operation deadline solely to
`transport.send(request, {deadlineMs})`; it no longer races that authoritative
transport result with a second generic timer. Late authoritative success and
typed error remain observable. The independent 1,000 ms recovery-outcome timer
and default runtime-terminator deadline remain separate and unchanged.

This follow-up has version impact `none`: no public Contract, Product, Module,
Host, Assembly, or Channel identity changes. Documentation impact is limited to
current source/design/acceptance pages; the immutable `1.0.14.0` Portal snapshot
and versioned assets remain unchanged.

### Reviewed verification subject

| Item | Evidence |
| --- | --- |
| Branch | `feat/formal-web-runtime-host` |
| Review base | `8e8d542b4c25c3fee7c328808e3a7b744e51134a` |
| Reviewed unit | The complete Task 13A staged tree prepared as the single direct-child commit of the review base |
| Product / Host / protocol | `1.0.14.0` / `1.0.0` / `1` |
| Assembly Lock SHA-256 | `26b34e56596dbb0b8ade7797ec8c1a201cb1e296320308e10e16742005760b1e` |
| Machine | MacBook Pro `Mac16,8`, Apple M4 Pro, 48 GB |
| OS | macOS `26.5.2` (`25F84`), arm64 |
| Native toolchain | Apple Clang `21.0.0`; CMake `4.1.3`; Python `3.14.6` |
| Web Proof toolchain | emsdk revision `dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`; Emscripten `6.0.5`; releases revision `dbd755b5da399329c2576f6e3dfa7f419f5d8409`; emsdk runner Node `22.16.0`; runner npm `10.9.2`; locked Playwright `1.62.1` |

The final Task 13A commit cannot embed its own SHA. After the local amend, the
ignored Task report and review package bind the resulting SHA to this exact
review base and complete staged tree. This identity does not imply remote CI,
merge, tag, Release, deployment, publication, Channel promotion, or physical
acceptance.

### Task 13A current local evidence

| Gate | Reviewed local result |
| --- | --- |
| `node --test apps/web-runtime-host/test/main_shell.test.mjs` | PASS; 33/33, including delegated late transport success/error, the unchanged 1,000 ms recovery-outcome timer, and default runtime termination |
| `scripts/web-runtime-host.sh proof` | PASS; independent AudioWorklet Chromium 13/13, two clean builds/packages, byte reproducibility, Python package 13/13, server 7/7, Node 84/84, native Web CTest 3/3, distribution 6/6, packaged Chromium 14 passed/1 skipped, WebKit 1 passed/10 capability skips |
| `scripts/web-runtime-lab.sh test` | PASS; 42/42 Node tests plus server and active-tree checks |
| `scripts/core.sh proof` | PASS; 31/31 selected CTests; Product `1.0.14.0`, Channel `canary`, Assembly lock `MATCH` |
| `scripts/core.sh configure asan` / `build asan`; ASAN native and stress | PASS; 26/26 non-stress native tests and 2/2 stress tests |
| `scripts/core.sh configure tsan` / `build tsan` / `test tsan stress` | PASS; 2/2 stress tests; no TSan report |
| `scripts/core.sh test dev stress` | PASS; 2/2 stress tests |
| `scripts/core-coverage.sh check` | PASS; 48/48 tests; 31 module signatures match 31 coverage objects; overall lines `79.44%`, branches `68.20%`; Application Facade lines `84.25%`, branches `68.04%`; every module threshold passes |
| `scripts/architecture-portal.sh check` | PASS on the reviewed Task 13A tree; 40/40 tests, 34 current pages, 9 diagram sources/18 outputs, Product `1.0.14.0` facts, typecheck, optimized build, and 37 routes/internal links. Immutable snapshot provenance remains separate. |
| Dependency, active-tree, Product version, module graph, Assembly Lock, source-boundary, and diff checks | PASS; Product `1.0.14.0` |

The current WebKit result is a structured `UNSUPPORTED_WEB_RUNTIME` limitation
for `opfsSyncAccessHandle` and `opfsWritableReplace`; ten skipped tests are not
WebKit product acceptance. The current automated browser journey is not
acoustic, MIDI-device, latency-camera, or iPad evidence.

## Pull Request CI and merge evidence

The retained CI matrix contains Web Toolchain Conformance, Web Runtime Lab,
macOS Core, Ubuntu Core, Linux ASan, macOS native ASan, and Coverage. A dedicated
Formal Web Host job checks out Git LFS content, uses Python 3.11 and Node 22,
checks out the exact emsdk revision, installs and activates Emscripten `6.0.5`,
runs `npm ci`, explicitly installs Chromium and WebKit, verifies the exact
Emscripten identity, and runs `scripts/web-runtime-host.sh proof`. Nightly keeps
TSan and Stress.

The final corrective integration was [PR #91](https://github.com/endaye/lmdj/pull/91).
Its exact reviewed head was
`b8d73e0e9597a7cddbfe3756a70298719ee5b9aa`. The
[Core CI run](https://github.com/endaye/lmdj/actions/runs/31009477920)
completed successfully for Web Toolchain Conformance, Formal Web Runtime Host,
Web Runtime Lab, Ubuntu Core, Linux ASan, Coverage, the primary macOS gate,
macOS Core, and macOS native ASan. The GitHub-hosted macOS fallback was skipped
by design because the primary lane published successful terminal results. The
[Architecture Portal run](https://github.com/endaye/lmdj/actions/runs/31009477985)
also completed successfully. The PR rollup finished with 12 successful checks,
four designed skips/neutral results, zero failures, and zero pending checks.

PR #91 was squash-merged at `2026-08-05T13:31:16Z` as
`d4cf657bdd194e3eeee4e78e119dcb0b97f49cdf`. Its only parent is the verified
pre-merge `main` revision
`7a1b5d3cbc100d5f6b113854592a842af8ab4e84`, and the merged tree exactly equals
the reviewed PR-head tree.

## Merged-main acceptance — 2026-08-05

The required post-merge verification ran from a clean isolated worktree at the
exact merged `main` revision
`d4cf657bdd194e3eeee4e78e119dcb0b97f49cdf`:

| Gate | Merged-main result |
| --- | --- |
| `scripts/web-runtime-host.sh proof` | PASS; AudioWorklet 17/17, two clean builds/packages byte-identical, Python package 13/13, server 7/7, Node 84/84, native Web CTest 3/3, distribution 6/6, packaged Chromium 14 passed/1 designed skip, WebKit 1 capability-path pass/10 skips |
| `scripts/core.sh proof` | PASS; 32/32 selected CTests; Headless Core Proof PASS; Product `1.0.14.0`, Channel `canary`, Assembly lock `MATCH` |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json --assembly products/lmdj/assembly.json --lock products/lmdj/assembly.lock.json` | PASS; Product Build `1.0.14.0` |

This establishes the implemented-and-merged Stage 6 canary boundary. It does
not create a signed Product tag, GitHub Release, deployment, publication,
Channel promotion, or physical-device evidence.

## Required physical rows

| Platform | Browser | Input / journey | Status |
| --- | --- | --- | --- |
| macOS | Safari | Pointer, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| macOS | Chrome | Pointer, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| macOS | Chrome | Physical MIDI, built-in or wired output, 500 events plus physical timing sample | `deferred / unverified` |
| iPadOS | Safari | Touch, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| iPadOS | Safari | Touch background, foreground, lock, unlock, and route interruption | `deferred / unverified` |

All five physical rows remain outside automated PASS. They do not block the
canary implementation boundary, but they block physical-pass, `beta`, and
`stable` claims.

## Remaining boundary

Merged-main Host Proof and successful PR CI do not create a signed tag,
Release, deployment, Channel promotion, or physical-device evidence. The
immutable `1.0.14.0` Portal snapshot remains unchanged and independently
verified by its provenance gate.

## Bank reactivation acknowledgement repair candidate — 2026-08-29

Issue #410 closes an acknowledgement gap found by repeatedly exercising the
packaged Browser lifecycle journey. Before this repair, a live Bank reload
could return while audio still acknowledged the prior generation, and a later
stop/start or suspend/resume could treat that stale nonzero value as activation
success.

The candidate requires exact generation identity at both boundaries. Running
`snapshot.reload`, retry publication, and the automatic running-Bank
publications from `sample.import.commit`, `sample.update_pad`, and
`sample.reset_pad` wait for the newly accepted Bank generation within the
original Host request deadline. When a sample mutation has already committed
Project Truth but the acknowledgement cannot complete, its response retains
the committed revision and reports `runtime_published=false` with a typed
`snapshot_error`; it does not claim that the Project mutation rolled back. The
same Project-committed response and running-Runtime fail-closed outcome applies
when the deadline expires anywhere before Runtime publication completes,
including during immutable Snapshot and Bank preparation.
Initial AudioWorklet bootstrap completes before Browser Main establishes the
one-second activation deadline immediately beside the callback baseline and
`AudioContext.resume()` edge; bootstrap time therefore cannot consume that
budget. Browser Main first observes a lock-free callback heartbeat advance,
including across `uint32` wrap, then gives Control only the remaining activation
budget. Recovery retains one budget from its resume edge. The Bridge computes
the absolute effective cutoff as the earlier of the operation cutoff and caller
cutoff, passes that absolute deadline into Control Runtime, and never rebuilds a
fresh operation window from `submitted_at`. If a Project mutation atomically
wins its publication claim before the cutoff, that claim remains authoritative
until commit or abort settlement; unclaimed work and later Runtime-derived
publication/acknowledgement do not inherit that exemption. AudioWorklet activation validates
current/accepted/pending Bank state before opening the gate, latches that
generation, and makes the first open-gate callback acknowledge it. A stale lower
generation waits; a newer generation or deadline expiry fails closed. No timeout
is increased, and the callback adds only lock-free atomic increment and exchange
operations.

Current automated acceptance includes deterministic Control tests for live
publication, all three running sample-mutation publication paths, committed
Project plus fake-clock post-commit/pre-publication fail-closed Runtime timeout
semantics, stale reactivation acknowledgement, a caller-bounded 100 ms Bridge
activation, pre-deadline Project claim settlement after the deadline, and
terminal timeout.
Runtime Session tests prove that slow initial Worklet bootstrap receives a fresh
activation budget while suspend/resume shares one budget from the resume edge.
A real Chromium production-path journey reloads a live Bank and then
suspends/reactivates while retaining the latest exact acknowledgement. This is
local candidate evidence until independent review, remote CI, and merge are
separately complete; it creates no release, deployment, Channel promotion, or
physical-device evidence.

The final local candidate gates are Core full 79/79, stress 5/5, and proof
63/63; Web Host nonbrowser 160/160; real AudioWorklet 22/22; clean packaged
Chromium 20 passed with one designed skip and WebKit 2 passed with 14 declared
capability skips; Creator Vitest 354/354, Python 13/13, shared platform Node
133/133, and production build; and Portal 59/59 tests, 37 pages, 10 diagram
sources with 20 outputs, and 42 rendered routes. Dependency, active-tree,
version, production source-boundary, Web toolchain symbol-identity, and diff
checks also pass. Creator's clean-tree reproducibility/browser proof is deferred
to the first post-amend gate because its stable entrypoint rejects dirty source.
These remain local candidate facts, not independent review,
remote CI, merge, release, deployment, Channel, or physical acceptance.
