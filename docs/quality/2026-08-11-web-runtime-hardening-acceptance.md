# Web Runtime Hardening Acceptance — 2026-08-11

## Current status

The completed local branch is an automated `PASS` at committed source revision
`8f43f666b3b78bb9571c342c0c64951a7929aed5`. The immutable Architecture
Portal snapshot records Product Build `1.0.16.7`, Channel `canary`, source tree
`a3a7d45b669f68fc31f44194c778c05d7fc3c5bb`, and Assembly Lock SHA-256
`4e63fd28f8b1b4c98b5154cb3ba4f15b1d88d5d610188465f41199d63ba22ef8`.
The generator froze it at `2026-08-11T16:03:25.671Z`.

The earlier immutable `1.0.16.6 · canary` snapshot at source revision
`fa0e619d3abd99f124e9dcce34e958815c21a23c` remains historical evidence, but
that unshipped candidate is abandoned and can never be reused, tagged,
released, deployed, published, or promoted. Final branch review found that its
unknown-response hardening did not cover the actual production Browser Main
polling path. Task 7 completed that production path and Task 8 allocated the
corrective identities; therefore only the new immutable `1.0.16.7 · canary`
snapshot satisfies this candidate's evidence boundary. No `1.0.16.6`
snapshot, metadata, sidebar, diagram, or registry history was rewritten.

This result establishes the reviewed local source, generated snapshot, and
automated evidence boundary. It does not establish remote CI, physical-device
acceptance, or any release, deployment, publication, or Channel state.

## Environment and setup classification

All passing gates used the existing locked environment. No toolchain was
installed or changed.

| Item | Exact value |
| --- | --- |
| Machine / OS | Apple M1, arm64; macOS `26.5.2` (`25F84`) |
| Native build tools | Apple Clang `21.0.0`; CMake `4.4.2` |
| Python | `3.11.15` from `/opt/homebrew/opt/python@3.11/libexec/bin/python3` |
| Node / npm | Node `v22.16.0`; npm `10.9.2` from the existing Stage 7 emsdk toolchain |
| Emscripten | emsdk revision `dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`; Emscripten `6.0.5` (`1db513782be24469589d7cb8a1f1834e9a33f271`) |
| Browser automation | locked Playwright `1.62.1` |

One initial Core Proof invocation stopped after 1.33 s during Python import and
was not counted as a pass. Under that exact activation and PATH prefix,
`python3` resolved to system `/usr/bin/python3` 3.9.6 rather than the required
Python 3.11. `tests/build/version_test.py:11` imported `scripts.version`, then
`scripts/version.py:68` raised `TypeError: unsupported operand type(s) for |:
'type' and 'type'` while evaluating `def load_version(path: str | Path) ->
ProductVersion`. This was a command-scoped setup/operator-environment error,
not a semantic failure. The PATH was corrected to select Python 3.11.15 and
Node 22.16.0, and the complete exact Core Proof was rerun successfully. No
dependency, toolchain, or tracked source was changed.

The existing ASan profile was configured and built at current HEAD before the
gate: configure passed in 0.96 s and build passed in 16.33 s. The current TSan
profile rebuild passed in 12.53 s before its gate. Neither profile produced a
zero-test invocation; zero tests would not have been accepted as a pass.

## Automated local evidence

| Gate | Exact local result |
| --- | --- |
| `scripts/core.sh proof` | PASS, exit 0, 47.28 s; 37/37 selected CTests; schema 9 positive and 11 negative cases with 17 Product artifacts; CLI 11/11; MCP 10/10; Golden audio and CLI/MCP parity match; distribution package and Headless Proof PASS; Product `1.0.16.7`, Channel `canary`, Assembly Lock `MATCH` |
| `scripts/core.sh test asan full` | PASS, exit 0, 82.37 s; 53/53 after the current-HEAD configure/build precondition; no ASan report |
| `scripts/core.sh test tsan full` | PASS, exit 0, 89.69 s; 27/27 supported native tests after the 12.53 s current-HEAD rebuild; no TSan report |
| `scripts/core.sh test release stress` | PASS, exit 0, 0.52 s; 2/2 concurrency stress tests |
| `scripts/web-runtime-host.sh proof` | PASS, exit 0, 644.92 s; Chromium AudioWorklet/failure 20/20; Python groups 14/14, 13/13, 18/18, 29/29, 11/11, 47/47, and 9/9; Node 27/27; native Web CTest 3/3; distribution 6/6; packaged Chromium 15 passed/1 designed skip; WebKit 1 structured capability-limitation pass/10 inapplicable skips; package, Emscripten identity, and two-clean-build reproducibility PASS |
| `scripts/creator-web.sh proof` | PASS, exit 0, 161.27 s; Vitest 38/38; Python package 7/7 and server 3/3; shared Platform Node 78/78; packaged Chromium 10 passed/1 designed skip; WebKit capability boundary 1/1; Project fixture, package, Emscripten identity, and two-clean-build distribution reproducibility PASS |
| `bash tests/build/test_active_tree.sh` | PASS, exit 0, 2.04 s |
| Pre-snapshot `scripts/architecture-portal.sh check` | EXPECTED NONZERO, exit 1, 15.49 s; current-content phases passed: Portal tests 41/41, 37 pages, 10 diagram sources/20 outputs, and Product facts `1.0.16.7` at the exact source revision. The only errors were the permitted not-yet-generated `1.0.16.7` versions entry, snapshot source, and metadata. |
| `scripts/architecture-portal.sh version 1.0.16.7 canary` | PASS, exit 0, 54.34 s from the clean committed source boundary; preflight/current and post-generation checks passed; froze `1.0.16.7 · canary` at source revision `8f43f666b3b78bb9571c342c0c64951a7929aed5` |
| Standalone generated-boundary `scripts/architecture-portal.sh check` | PASS, exit 0, 26.30 s before this acceptance update; Portal tests 41/41, 37 pages, 10 diagram sources/20 outputs, matching schema-2 provenance and release truth, typecheck, optimized build, and 42 routes/internal links |

The retained hardening automation covers the real Chromium stalled
AudioWorklet bounded-quiescence case, production-bridge quota and invalid-state
storage conditions, an unleased append that preserves file content, and
unknown or already-settled protocol responses that terminate fail closed.

Task 7's production call chain is Browser Main `pollTransport()` to the direct
`_lmdj_web_host_poll` C export, `ControlBridge::poll`, production JSON decode,
and `pendingRequests` correlation. The corrective branch in
`packages/web-runtime-platform/src/web-runtime-pre.js` calls the existing
`HOST_PROTOCOL_MISMATCH` fail-closed path and returns when a response ID is not
pending. The stable Web Host build wrapper automatically runs
`apps/web-runtime-host/test/web_host_source_boundary_test.py` against the
generated production pre-JS after linking and before packaging. Both clean
production builds in this Proof visibly printed `web Host source boundary:
PASS`; the guard also proved that conformance-only seams were absent from the
generated production source.

The generated boundary was not hand-edited. It contains the `versions.json`
entry, 37 versioned documents, one schema-2 metadata file, one generated
sidebar, and 20 immutable versioned diagram files: 60 generated files in all.
No generated path is a symbolic link. The 37 generated documents and 20
generated diagram files byte-match their current sources, and all 59 files in
the abandoned `1.0.16.6` immutable boundary retain their pre-freeze hashes.

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
| Deployment | not performed / not proved |
| Publication | not performed / not proved |
| Public smoke | not performed / not proved |
| Channel promotion | not performed / not proved |

The snapshot's `canary` field records the immutable documentation candidate; it
does not itself perform or prove a Channel promotion. No push, Pull Request,
CI, merge, tag, Release, deployment, publication, public smoke, or Channel
promotion occurred as part of this acceptance run.
