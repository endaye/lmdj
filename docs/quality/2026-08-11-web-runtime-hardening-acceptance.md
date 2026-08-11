# Web Runtime Hardening Acceptance — 2026-08-11

## Current status

The completed local branch is an automated `PASS` at source revision
`fa0e619d3abd99f124e9dcce34e958815c21a23c`. The immutable Architecture
Portal snapshot records Product Build `1.0.16.6`, Channel `canary`, source tree
`d9cfd4dfe7775a3ef777a8fec7a9ff46a7379b9c`, and Assembly Lock SHA-256
`86a3c89221f7b5167c0b1575fccd60373902411e42b7964c9198ea0de0f6f9c7`.
The generator froze it at `2026-08-11T13:29:38.736Z`.

This result establishes the reviewed local source, generated snapshot, and
automated evidence boundary. It does not establish remote CI, physical-device
acceptance, or any release or deployment state.

## Environment

All required gates used the existing locked environment. No toolchain was
installed or changed.

| Item | Exact value |
| --- | --- |
| Machine / OS | Apple M1, arm64; macOS `26.5.2` (`25F84`) |
| Native build tools | Apple Clang `21.0.0`; CMake `4.4.2` |
| Python | `3.11.15` from the existing Homebrew Python 3.11 Framework |
| Node / npm | Node `v22.16.0`; npm `10.9.2` from the existing Stage 7 emsdk toolchain |
| Emscripten | emsdk revision `dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`; Emscripten `6.0.5` (`1db513782be24469589d7cb8a1f1834e9a33f271`) |
| Browser automation | locked Playwright `1.62.1` |

The ignored Creator dependency directory was initially absent. The first
Creator Proof stopped before tests with an explicit setup error. Lockfile-only
`npm ci` under Node `v22.16.0` restored 109 packages; it changed neither the
toolchain nor tracked source. The complete Creator Proof was then rerun.

## Automated local evidence

| Gate | Exact local result |
| --- | --- |
| `scripts/core.sh proof` | PASS, exit 0, 105.58 s; 37/37 selected CTests; schema 9 positive and 11 negative cases with 17 Product artifacts; CLI 11/11; MCP 10/10; Golden audio and CLI/MCP parity match; package acceptance PASS; Product `1.0.16.6`, Channel `canary`, Assembly Lock `MATCH` |
| `scripts/core.sh test asan full` | PASS, exit 0, 110.03 s; 53/53. The first invocation found no configured ASan tests and was not counted as PASS; after locked-environment configure/build, the exact command was rerun successfully. |
| `scripts/core.sh test tsan full` | PASS, exit 0, 111.95 s; 27/27 supported native tests after rebuilding the TSan profile at current HEAD; no TSan report |
| `scripts/core.sh test release stress` | PASS, exit 0, 1.06 s; 2/2 concurrency stress tests |
| `scripts/web-runtime-host.sh proof` | PASS, exit 0, 706.32 s; Chromium AudioWorklet 18/18; two clean Host distributions byte-identical; Python groups 14/14, 13/13, 18/18, 29/29, 11/11, 47/47, and 9/9; Node 27/27; native Web CTest 3/3; distribution 6/6; packaged Chromium 15 passed/1 designed WebKit-row skip; WebKit 1 structured capability-limitation pass/10 inapplicable skips |
| `scripts/creator-web.sh proof` | PASS, exit 0, 183.25 s; Project fixture and two clean Creator distributions byte reproducible; Vitest 38/38; Python package 7/7 and server 3/3; shared Platform Node 78/78; packaged Chromium 10 passed/1 designed WebKit-row skip; WebKit capability boundary 1/1 |
| `bash tests/build/test_active_tree.sh` | PASS, exit 0, 1.74 s |
| Initial `scripts/architecture-portal.sh check` | EXPECTED NONZERO, exit 1, 14.90 s; current-content phases passed: Portal tests 41/41, 37 pages, 10 diagram sources/20 outputs, and Product facts. The only errors were the not-yet-generated `1.0.16.6` versions entry, snapshot source, and metadata. |
| `scripts/architecture-portal.sh version 1.0.16.6 canary` | PASS, exit 0, 51.61 s from the clean committed source boundary; preflight/current and post-generation checks passed; froze `1.0.16.6 · canary` at source revision `fa0e619d3abd99f124e9dcce34e958815c21a23c` |
| Standalone generated-boundary `scripts/architecture-portal.sh check` | PASS, exit 0, 25.04 s before this acceptance document existed; 41/41 Portal tests, 37 pages, 10 diagram sources/20 outputs, matching schema-2 provenance, typecheck, optimized build, and 42 routes/internal links |

The hardening-specific retained automation includes the real Chromium stalled
AudioWorklet bounded-quiescence case, production-bridge quota and invalid-state
storage-condition cases, an unleased append that preserves file content, and
unknown/duplicate protocol responses that terminate fail closed. The complete
Host and Creator Proofs rebuilt and exercised the current production bridge and
packaged browser journeys at the source revision above.

The generated boundary was not hand-edited. It contains the `versions.json`
entry, 37 versioned documents, one schema-2 metadata file, one generated
sidebar, and 20 immutable versioned diagram files: 60 generated files in all.
No generated path is a symbolic link.

## Physical acceptance rows

| Platform | Browser | Input / journey | Status |
| --- | --- | --- | --- |
| macOS | Safari | Pointer, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| macOS | Chrome | Pointer, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| macOS | Chrome | Physical MIDI, built-in or wired output, 500 events plus physical timing sample | `deferred / unverified` |
| iPadOS | Safari | Touch, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| iPadOS | Safari | Touch background, foreground, lock, unlock, and route interruption | `deferred / unverified` |

All five rows remain outside automated PASS. Automation does not prove physical
input latency, acoustic output, subjective audio quality, device permission
behavior, touch ergonomics, background or lock-screen recovery, or long-session
stability. These rows continue to block physical-pass, `beta`, and `stable`.

## External state

| State transition or evidence | Status at this evidence point |
| --- | --- |
| Push | not performed / not proved |
| Pull Request | not opened / not proved |
| Pull Request CI | not run / not proved |
| Merge | not performed / not proved |
| Product tag | not created or pushed / not proved |
| GitHub Release | not created / not proved |
| Deployment or publication | not performed / not proved |
| Public smoke | not performed / not proved |
| Channel promotion | not performed / not proved |

The snapshot's `canary` field records the immutable documentation candidate; it
does not itself perform or prove a Channel promotion. No push, Pull Request,
merge, CI-on-PR, tag, Release, deployment, public smoke, publication, or Channel
promotion occurred as part of this acceptance run.
