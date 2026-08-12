# Stage 7 Creator Editor Acceptance — 2026-08-07

## Historical acceptance

The original Stage 7 branch-local product acceptance was `PASS` at repository
revision `ee14a280fec9847c84c5dfd429303b40ef5f0993`. Its immutable Portal snapshot
projects product/current-doc source revision
`8ad5fbf3136074e94492c8408cd1a55befc8322f`. That point-in-time evidence covered
Product Build `1.0.16.3`, Creator Web Host `1.0.2`, shared Web Runtime Platform
`0.1.2`, Formal Web Runtime Host `1.2.2`, and Application Facade `1.3.1`.

This historical branch-local Proof never established merged-main Proof,
physical acceptance, or later Release/deployment state. Subsequent merge and tag
facts are recorded separately below; they do not retroactively change what this
local evidence proved.

## Current remediation candidate

As of the live Git check on 2026-08-13, `origin/main` is
`d1d8bb6a629b6e05b86b3c8843870ef27edcfe5c`. The remediation branch
`fix/stage7-review-remediation` is unpublished and allocates Product Build
`1.0.18.0`, Creator Web `1.1.0`, Web Runtime Platform `0.2.0`, Web Runtime Host
`1.2.7`, Project I/O `0.5.4`, and Application Facade `1.3.5`. Creator Web
and the complete multi-product candidate gate sequence passed from clean revision
`c44517bc7bde30cea4a40a7cab495a081028eb7e`. The immutable `1.0.18.0`
snapshot records its pre-snapshot source revision `561fa2d6324d2fe2025eaf692026e5eedcb350bb`
and Assembly Lock SHA-256
`3cd490099b7e7f15204d7af719f73bf7983077fe208e7644ce55cdc8c2809407`;
the Portal provenance gate accepts that unchanged snapshot at the tested
descendant. Exact commands, toolchain identity, results, and the unexecuted
human sheet are recorded in
`docs/release-evidence/2026-08-13-stage7-remediation-canary.md`.

This remains branch-local candidate evidence, not merged-main Proof. No push,
PR, merge, tag, Release, deployment, publication, or Channel promotion is
claimed by this record.

Manual canary is `open — awaiting human execution`. Physical Keyboard/MIDI,
hearing, Safari, and iPadOS observations remain `deferred / unverified`; no
automated result is promoted into those claims.

## Remediation candidate automated evidence

All rows below ran successfully from clean revision
`c44517bc7bde30cea4a40a7cab495a081028eb7e`.

| Gate | Candidate result |
| --- | --- |
| `scripts/core.sh configure dev` / `build dev` | PASS |
| `scripts/core.sh test dev full` | PASS; 53/53 CTests |
| `scripts/core.sh test dev stress` | PASS; 2/2 CTests |
| `scripts/core.sh coverage check` | PASS; lines 82.40% (16166/19620), branches 67.93% (4498/6622) |
| `scripts/core.sh proof` | PASS; Product Build `1.0.18.0`, Channel `canary`, Assembly Lock `MATCH` |
| `scripts/web-toolchain-conformance.sh proof` | PASS; Chromium toolchain 2/2, Chromium Project I/O 3/3, Chromium AudioWorklet 21/21; WebKit capability boundary 1/1 with one designed capability skip and Project I/O 2/2 with one designed capability skip |
| `scripts/web-runtime-host.sh proof` | PASS; packaged/source/native, reproducibility, deployment-orchestrator, and browser suites passed; Chromium full Host 15 passed/1 designed skip; WebKit boundary 1 passed/10 designed skips |
| `scripts/creator-web.sh proof` | PASS; Vitest 61/61, package 7/7, server 3/3, Platform 88/88; packaged Chromium 13 passed/1 designed physical-MIDI skip; WebKit capability boundary 1/1 |
| `scripts/architecture-portal.sh check` | PASS; 46/46 Portal tests, 37 pages, 10 diagram sources/20 outputs, Product `1.0.18.0` facts, immutable snapshot provenance, optimized build, and 42 routes/internal links |
| dependency, active-tree, and version gates | PASS; vendored/offline dependencies, active source boundary, Product version tests, version/Assembly Lock verification |

The automated Chromium binary was Google Chrome for Testing
`151.0.7922.34`; it is not the human canary browser and does not establish
Safari, iPadOS, physical input, or hearing acceptance.

## Historical automated local evidence (1.0.16.3)

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
| Historical Stage 7 PR | PR #97 is `MERGED` as `c39d8b6`; follow-up PR #101 is `MERGED` as `488ffa7`, and #102 is `MERGED` as `38a8c13` |
| Historical hardening PR | PR #117 is `MERGED` as `7555cfd`; squash-witness PR #118 is `MERGED` as `336a27c` |
| Historical Product tags | signed annotated `lmdj-v1.0.16.5` targets `38a8c13`; signed annotated `lmdj-v1.0.16.8` targets `336a27c` |
| Historical merged-main Proof | recovered and bound: `main` push run `31327104838` succeeded at `38a8c130e5f1ced6f27d8fd7d2cba2fd1d70f97f` (`1.0.16.5`, 12 success/1 designed skip); run `31529410253` succeeded at `336a27c0799035b2f8d6455b32259ee227df20f6` (`1.0.16.8`, 20 success/1 designed skip) |
| Current remediation push / PR / CI / merge | not performed; current branch-local Proof is not merged-main Proof |
| Current Product tag / Release / deployment / publication / Channel promotion | not authorized and not performed |
| Manual canary | `open — awaiting human execution` |

The historical rows were refreshed from live Git/GitHub on 2026-08-13. The two
historical Proof runs were always present; the review's prior inference from a
missing repository document to a missing execution was incorrect. G1 is now a
recovered documentation binding, not a historical Proof execution failure.

The current remediation rows must be refreshed again after any separately
authorized push or external transition. T1 remains `open — awaiting human
execution`, and Product Build `1.0.18.0` still requires a future Proof at its
exact merged `main` revision before any new Product tag. The five physical rows
continue to block physical-pass, `beta`, and `stable`.
