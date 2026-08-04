# Formal Web Runtime Host Local Acceptance — 2026-08-03

## Outcome

Task 12A assembles Formal Web Runtime Host `1.0.0` into Product Build
`1.0.14.0 · canary`. The packaged Host identifies itself as Product
`1.0.14.0`, Host `1.0.0`, protocol `1`, and the generated Assembly Lock matches
the declared composition. Clean-distribution Web Proof, Web Runtime Lab, Core
Proof, ASan, TSan, release stress, dependency, active-tree, and exact-identity
gates pass locally.

This record does not claim Pull Request CI or physical-device acceptance. The
Architecture Portal check exits nonzero only for the three planned missing
`1.0.14.0` snapshot artifacts; the immutable canary snapshot remains
exclusively owned by Task 12B.

No push, Pull Request, merge, tag, Release, deployment, publication, or Channel
promotion occurred. `lmdj-v1.0.14.0` is future tag text only.

## Tested identity and environment

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

## Exact version propagation

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

## Automated evidence

| Gate | Local result |
| --- | --- |
| `scripts/web-runtime-host.sh proof` | PASS; independent AudioWorklet Chromium 13/13, two clean builds/packages, byte reproducibility, Python package 12/12, server 7/7, Node 82/82, native Web CTest 3/3, distribution 6/6, packaged Chromium 9 passed/1 skipped, WebKit 1 passed/5 capability skips |
| `scripts/web-runtime-lab.sh test` | PASS; 42/42 Node tests plus server and active-tree checks |
| `scripts/core.sh proof` | PASS; 31/31 selected CTests; Product `1.0.14.0`, Channel `canary`, Assembly lock `MATCH` |
| `scripts/core.sh configure asan` / `build asan` / `test asan full` | PASS; 47/47 |
| `scripts/core.sh configure tsan` / `build tsan` / `test tsan full` | PASS; 26/26 native-label tests; no TSan report |
| `scripts/core.sh configure release` / `build release` / `test release stress` | PASS; 2/2 stress tests |
| `scripts/core-coverage.sh check` | PASS; 48/48 tests; 31 module signatures match 31 coverage objects; overall lines `79.78%`, branches `68.40%`; Application Facade lines `84.02%`, branches `68.04%`; every module threshold passes |
| `scripts/architecture-portal.sh check` | EXPECTED TASK 12B EXCEPTION; 26/26 unit tests, 34 current pages, 9 diagram sources/18 outputs, and `1.0.14.0` facts pass before the check reports only missing `versions.json`, snapshot source, and metadata entries |
| `bash scripts/verify-core-dependencies.sh` | PASS |
| `bash tests/build/test_active_tree.sh` | PASS |
| Product version, module graph, Assembly Lock, and lock verification | PASS; Product `1.0.14.0` |
| `git diff --check` | PASS |

The WebKit result is a structured `UNSUPPORTED_WEB_RUNTIME` limitation for
`opfsSyncAccessHandle` and `opfsWritableReplace`; five skipped tests are not
reported as WebKit product acceptance. The automated browser journey is also
not acoustic, MIDI-device, latency-camera, or iPad evidence.

Because the full Portal check intentionally stops at `check:release-docs`, its
remaining current-page subcommands were run separately: typecheck, optimized
build, and the 37-route/internal-link build check all pass. No snapshot command
was run and no release-doc assertion was weakened.

## CI configuration boundary

The retained CI matrix contains Web Toolchain Conformance, Web Runtime Lab,
macOS Core, Ubuntu Core, Linux ASan, macOS native ASan, and Coverage. A dedicated
Formal Web Host job checks out Git LFS content, uses Python 3.11 and Node 22,
checks out the exact emsdk revision, installs and activates Emscripten `6.0.5`,
runs `npm ci`, explicitly installs Chromium and WebKit, verifies the exact
Emscripten identity, and runs `scripts/web-runtime-host.sh proof`. Nightly keeps
TSan and Stress.

This is workflow configuration evidence only. Pull Request CI is `not run /
pending`; there is no CI URL or remote job result because no push or Pull
Request was authorized.

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

Task 12B alone may create
`apps/architecture-portal/versioned_docs/version-1.0.14.0/`, the matching
versioned sidebar and metadata, and the `versions.json` entry. Local Task 12A
proof does not create that immutable snapshot, a signed tag, a Release, or any
deployment artifact.
