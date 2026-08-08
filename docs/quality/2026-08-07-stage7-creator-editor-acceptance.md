# Stage 7 Creator Editor Acceptance — 2026-08-07

## Current status

Stage 7 automated local product acceptance is `PASS` at repository revision
`ee14a280fec9847c84c5dfd429303b40ef5f0993`. Its immutable Portal snapshot
projects product/current-doc source revision
`8ad5fbf3136074e94492c8408cd1a55befc8322f`. The verified third corrective
candidate is Product Build `1.0.16.3`, Channel `canary`,
Creator Web Host `1.0.2`, shared Web Runtime Platform `0.1.2`, Formal Web
Runtime Host `1.2.2`, and Application Facade `1.3.1`. This evidence-only update
is committed after that revision and does not change Product, Host, Module,
Contract, Provider, snapshot, or test source.

This result establishes the implemented local candidate and its clean-source
Proof boundary. It does not establish remote CI, merge, a signed Product tag,
Release, deployment, publication, Channel promotion, or physical-device
acceptance.

## Automated local evidence

| Gate | Result at the acceptance revision |
| --- | --- |
| `scripts/core.sh proof` | PASS; Product version checks, lock conformance, and version verification passed; 35/35 selected CTests passed; schema checks reported 9 positive cases, 11 negative cases, and 17 Product artifacts; CLI 11/11, MCP 10/10, package acceptance, Product `1.0.16.3`, Channel `canary`, and Assembly Lock `MATCH` |
| `scripts/web-toolchain-conformance.sh proof` | PASS; Chromium toolchain conformance 2/2; WebKit 1 capability pass/1 designed capability skip; Chromium Project I/O 2/2; WebKit Project I/O 2/2 with the declared capability-limited path; Chromium AudioWorklet 17/17 |
| `scripts/web-runtime-host.sh proof` | PASS; AudioWorklet Chromium 17/17; two clean distributions byte-identical; Python package 14/14, server 8/8, Node 25/25, native Web CTest 3/3, and browser fixtures 6/6; packaged Chromium 15 passed/1 designed skip; WebKit 1 limitation-path pass/10 capability skips |
| `scripts/creator-web.sh proof` | PASS; Core-generated Project Bundle pack reproducible; two clean Creator distributions byte-identical; Vitest 38/38, Python package 7/7, server 3/3, shared Platform 76/76; packaged Chromium 10 passed/1 designed skip; WebKit capability boundary 1/1 |
| `scripts/architecture-portal.sh check` | PASS; 41/41 Portal tests, 37 current pages, 10 diagram sources/20 outputs, Product `1.0.16.3` facts, immutable snapshot provenance, typecheck, optimized build, and 42 routes/internal links |
| `bash scripts/verify-core-dependencies.sh` | ENVIRONMENT BLOCKED on two attempts: `curl (28)` could not connect to `github.com:443`. This is not recorded as command PASS. The already populated nlohmann/json archive independently matched the pinned SHA-256 `42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa`, and the PicoSHA2 source independently matched pinned commit `161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29`; those exact sources were supplied to clean CMake Proof runs without modifying tracked source. |
| `bash tests/build/test_active_tree.sh` | PASS |

The Creator Chromium journey imports a real portable Bundle, opens Project
Truth, keeps **Open local** reachable, serializes Project actions, activates the
shared Wasm/AudioWorklet Runtime, admits all 64 stable Pad addresses, verifies a
held-key 16-trigger burst, suspends/reactivates, reloads, preserves a live
Project and input surface across persisted page lifecycle, and proves that
recovery enables only the real Trigger after the Platform's unique probe window
is armed. It also keeps any retiring writer conflict typed as `PROJECT_BUSY`,
reopens without re-listing during that conflict, explicitly reactivates, routes
synthetic MIDI, and preserves exact cleanup and denied-permission semantics. The
WebKit result is the structured `UNSUPPORTED_WEB_RUNTIME`
capability boundary for `opfsSyncAccessHandle` and `opfsWritableReplace`; it is
not Safari product acceptance.

## Physical acceptance rows

| Platform | Browser | Input / journey | Status |
| --- | --- | --- | --- |
| macOS | Safari | Pointer | `deferred / unverified` |
| macOS | Chrome | Pointer | `deferred / unverified` |
| macOS | Chrome | Physical MIDI | `deferred / unverified` |
| iPadOS | Safari | Touch | `deferred / unverified` |
| iPadOS | Safari | Lifecycle | `deferred / unverified` |

Automation does not prove physical input latency, acoustic output, subjective
audio quality, device permission behavior, touch ergonomics, background/lock
screen recovery, or long-session stability on those platforms.

## External state

| State transition | Status |
| --- | --- |
| Push | authorized but not yet performed at the proof evidence point; the remote feature branch still reported `a2c2d02b50c2bd4f556d41177bfe827dbdf45e98` before the authorized push |
| Pull Request | Draft PR #97 is open against `main`, but did not yet contain the `1.0.16.3` corrective candidate at the proof evidence point |
| Pull Request CI | no current result existed for repository revision `ee14a280fec9847c84c5dfd429303b40ef5f0993` at the proof evidence point; results attached to the older remote revision are not evidence for this candidate |
| Merge | not authorized / not performed |
| Product tag or GitHub Release | not authorized / not created |
| Deployment or publication | not authorized / not performed |
| Channel promotion | not authorized / not performed |

This table is a point-in-time evidence record; live remote SHA and CI state must
be checked after the authorized push. Stage 7 remains a locally proven canary
candidate until the current required CI is green, manual canary acceptance is
recorded, the separately authorized merge workflow completes, and merged
`main` passes the required Proof. The five physical rows remain accurately
deferred and continue to block physical-pass, `beta`, and `stable`.
