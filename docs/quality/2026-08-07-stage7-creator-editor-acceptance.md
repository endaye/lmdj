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

The first remediation candidate allocated Product Build `1.0.18.0` and Creator
Web `1.1.0`. Its clean automated gate sequence passed at
`c44517bc7bde30cea4a40a7cab495a081028eb7e`, with immutable snapshot source
revision `561fa2d6324d2fe2025eaf692026e5eedcb350bb` and Assembly Lock SHA-256
`3cd490099b7e7f15204d7af719f73bf7983077fe208e7644ce55cdc8c2809407`.
The first human Canary then exposed a release-blocking defect: replacing the
Runtime Session during Import aborted the old operation but could leave the
Creator transfer projection permanently at `importing`, disabling Project and
Audio actions. Operator-reported steps 1–6 are retained only as diagnostic
observations; the incomplete run is withdrawn and `1.0.18.0` is abandoned and
unshipped.

The corrected remediation candidate allocates Product Build `1.0.19.0` and
Creator Web `1.1.1`; Web Runtime Platform remains `0.2.0`, Web Runtime Host
`1.2.7`, Project I/O `0.5.4`, and Application Facade `1.3.5`. A focused rendered
UI regression first failed with `expected ready, received importing`, then
passed after the retiring Session cleanup became responsible for clearing its
transient transfer state. The immutable `1.0.19.0 · canary` snapshot binds
implementation revision `35c09053fd2bc64859b1a01c9cbbc2b5fb3a986d`; the full
candidate sequence passed from clean snapshot revision
`213023d096522de0bbe5e02e6699d775a45e67a6`. Exact results and the fresh blank
ten-step sheet are recorded in
`docs/release-evidence/2026-08-13-stage7-remediation-canary-1.0.19.0.md`.

Before that blank human sheet was executed, review of the physical keyboard
journey found that its lower `A..K` row addressed Pads 1–8 while the upper
`Q..I` row addressed Pads 9–16, opposite the Creator's ascending visual order.
That correction allocated Product Build `1.0.20.0`, Web Runtime Platform
`0.2.1`, Creator Web `1.1.2`, and Formal Web Runtime Host `1.2.8`. The single
shared map now assigns `Q..I -> Pad 1..8` and `A..K -> Pad 9..16`; every Pad
shows an accessible key hint derived from that same map. Pointer, MIDI, stable
Slot, Project, Bundle, Runtime Snapshot, and audio lifecycle semantics remain
unchanged. Product `1.0.20.0` subsequently passed the complete ten-step human
Canary, but its separate physical MIDI row failed: Chrome granted permission,
yet no Trigger reached Creator. macOS CoreMIDI capture showed PAD BANK A PAD1
and PAD16 sending Channel 10 Note 36/51 while Creator was hard-coded to Channel
1. The current correction therefore allocates Product Build `1.0.21.0` and
Creator Web `1.1.3`; Platform `0.2.1` and Formal Host `1.2.8` remain unchanged.
Creator now accepts the bounded Note `36..51` mapping on channels 1–16. Its
immutable `1.0.21.0 · canary` snapshot and complete branch-local automated Proof
passed at clean revision `1a7e84e94fd00030c44b48cd9f597cc42d5ca37a`;
the candidate physical-MIDI UI retest subsequently passed. Exact
revisions, identities, hashes, counts, and the physical checklist are recorded
in
[`2026-08-13-stage7-midi-channel-canary-1.0.21.0.md`](../release-evidence/2026-08-13-stage7-midi-channel-canary-1.0.21.0.md).

That candidate evidence remains branch-local candidate evidence, not merged-main Proof.
The branch was later protected by PR #134 and squash-merged as `5613158`; exact merged-main
full Proof and a fresh local rerun are bound separately in
[`2026-08-13-stage7-remediation-merged-main-1.0.21.0.md`](../release-evidence/2026-08-13-stage7-remediation-merged-main-1.0.21.0.md).
No tag, Release, deployment, publication, or Channel promotion is claimed by
this record.

The `1.0.20.0` ten-step keyboard/hearing canary remains passed historical
evidence. Physical MIDI passed independently on `1.0.21.0`; Safari Pointer and
iPadOS remain separately scoped and unverified. No automated result is promoted
into those claims.

## Abandoned 1.0.18.0 automated candidate evidence

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

These automated results remain valid historical evidence for the exact
`1.0.18.0` revision only. They do not waive the newly discovered human-path
defect and must not be reused as Proof for `1.0.19.0`.

## Corrected 1.0.19.0 automated candidate evidence

The complete Core, Web Toolchain, Web Runtime Host, Creator Web, Architecture
Portal, dependency, active-tree, and version/Assembly Lock gates passed from
clean revision `213023d096522de0bbe5e02e6699d775a45e67a6`. Creator Proof
included 62/62 Vitest assertions and packaged Chromium 13 passed/1 designed
physical-MIDI skip; the new real rendered-UI generation-replacement regression
is part of that suite. See the corrected evidence record for exact hashes,
commands, and honest automated/manual boundaries.

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
| macOS | Safari | Pointer | **`PASS` 2026-09-04 on deployed `1.0.41.0`** — built-in MacBook trackpad completed ordered Pads/Banks, separated and double clicks, drag/mistake targets, mode navigation, focus and explicit audio recovery, Sample controls, reload/reopen and report export; final clean suffix recorded 2 admitted / 2 outcomes / 0 rejected ([evidence](../release-evidence/2026-09-04-stage8-m8-macos-safari-pointer-hearing-1.0.41.0.md)) |
| macOS | Chrome | Pointer | `PASS — 1.0.40.0 exact packaged Creator at tested revision 3aeba5c5; built-in MacBook trackpad completed A1–A16, all Banks/corners, repeat/double-click, drag/mistake, modes, audio recovery and report export; 115 admitted / 115 outcomes / 0 rejected` — [evidence](../release-evidence/2026-09-01-stage7-m3-macos-chrome-pointer-1.0.40.0.md) |
| macOS | Chrome | Physical keyboard + hearing | `PASS — 1.0.20.0 ten-step Canary confirmed by endaye; report SHA-256 7e2a2b…333a` |
| macOS | Chrome | Physical MIDI | `PASS — 1.0.21.0 accepted MPD218 Channel 10 across all 16 Bank-A Pads, Creator B/C/D samples, reconnect, suspend/re-authorize, and reload/reopen; final report SHA-256 b0491e…603` |
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
| Current remediation push / PR / CI / merge | PR #134 merged as `5613158`; protected PR run `31684663825` and exact `main` push run `31688172806` both completed `success`; the merge and PR head have identical tree `5251522…a9eb` |
| Current Product tag / Release / deployment / publication / Channel promotion | not authorized and not performed |
| Product Build `1.0.18.0` | abandoned and unshipped after the first human Canary exposed permanent `importing` state |
| Product Build `1.0.19.0` | historical branch-local clean full Proof and immutable snapshot passed; superseded by later corrected candidates |
| Product Build `1.0.20.0` | keyboard/hearing Canary passed; direct-main run `31665186166` ended `failure` in `web-runtime-host`, and the Build was superseded after the physical MIDI channel defect was found |
| Product Build `1.0.21.0` | clean candidate Proof and MPD218 physical retest passed; PR #134 merged as `5613158`; full-mode exact-main run `31688172806` and fresh merged-tree local Proof both passed |
| Manual canary | `T1 passed — endaye confirmed all ten 1.0.20.0 steps with no issue; report SHA-256 7e2a2b…333a` |

The historical rows were refreshed from live Git/GitHub on 2026-08-13. The two
historical Proof runs were always present; the review's prior inference from a
missing repository document to a missing execution was incorrect. G1 is now a
recovered documentation binding, not a historical Proof execution failure.

T1 is closed for the `1.0.20.0` branch-local candidate; physical MIDI failed on
that Build, and Safari import was checked separately without reproducing the
importing stall. Product `1.0.21.0` automated Proof, immutable snapshot, Chrome
MPD218 physical retest, protected merge, and exact merged-main Proof are
complete. Creator macOS Chrome Pointer later passed on the exact packaged
`1.0.40.0` surface; macOS Safari Pointer later passed on the deployed
`1.0.41.0` surface ([evidence](../release-evidence/2026-09-04-stage8-m8-macos-safari-pointer-hearing-1.0.41.0.md));
the two iPadOS rows remain unverified. Every physical row stays authoritative
only for its individual platform, so the remaining rows continue to block
broader physical-device, `beta`, and `stable` claims.
No Product tag, Release, deployment, publication, or Channel promotion is
implied.
