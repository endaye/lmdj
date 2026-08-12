# Web Runtime Hardening Acceptance — 2026-08-11

## Current status

The completed local branch is an automated `PASS` at clean committed source
revision `56b726092e05821bb76ac1e458c84764b228efcd` and source tree
`96ebbcafc39e3b2d0ca8976996d810057e5ce647`. The immutable Architecture
Portal snapshot records Product Build `1.0.16.8`, Channel `canary`, source
projection SHA-256
`a2faa71493fd1bb287d18c13b469b5e3aa005d9a4093845747bcc531772d4a51`,
and Assembly Lock SHA-256
`397dd99c18e76190c81afbf2ae4e306be814fb339e663f3d251619d9566d7966`.
The generator froze it at `2026-08-11T18:08:12.238Z`.

The snapshot's introducing SHA is the Task 12 Conventional Commit that
contains this acceptance record and the generated boundary. Because a commit
cannot contain its own content-derived SHA, its exact value is recorded in the
Task 12 report immediately after commit; schema-2 provenance binds that
introducing commit to the exact direct-parent source revision above.

The immutable `1.0.16.6 · canary` snapshot at source revision
`fa0e619d3abd99f124e9dcce34e958815c21a23c` is abandoned, unshipped evidence.
Final branch review found that its F4 evidence exercised only a helper rather
than the production Browser Main polling path. Task 7 corrected that
production-path gap, so `1.0.16.6` can never be reused, tagged, released,
deployed, published, or promoted.

The immutable `1.0.16.7 · canary` snapshot at source revision
`8f43f666b3b78bb9571c342c0c64951a7929aed5` is also abandoned and unshipped.
Final review found that its worker-global lease was path-aware but
owner-unaware: a distinct same-page Project I/O platform could fail writer
acquisition and still reuse another platform's covering lease for append,
replace, and immutable create. Review also required correcting the production
pending-rejection evidence: the existing cases reached the real Browser Main
missing-pending branch but did not hold another production request pending.
Tasks 10 and 10A corrected those two boundaries. Neither abandoned snapshot,
metadata file, sidebar, diagram, nor registry identity was rewritten.

This result establishes the reviewed local source, immutable generated
snapshot, and automated evidence boundary only. It does not establish remote
CI, physical-device acceptance, or any release, deployment, publication, or
Channel state.

## Environment and setup classification

All passing gates used the existing command-scoped locked environment. No
toolchain was installed or changed.

| Item | Exact value |
| --- | --- |
| Machine / OS | Apple M1, arm64; macOS `26.5.2` (`25F84`) |
| Native build tools | Apple Clang `21.0.0`; CMake `4.4.2` |
| Python | `3.11.15` from `/opt/homebrew/opt/python@3.11/libexec/bin/python3` |
| Node / npm | Node `v22.16.0`; npm `10.9.2` from the existing Stage 7 emsdk toolchain |
| Emscripten | emsdk revision `dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`; Emscripten `6.0.5` (`1db513782be24469589d7cb8a1f1834e9a33f271`) |
| Browser automation | locked Playwright `1.62.1` |

An initial Task 10 full Chromium invocation used Node `v26.3.0`; it was
classified as setup/operator environment and was not counted. The complete
gate was rerun after emsdk activation with the locked Node executable first in
`PATH`. During Task 12 pre-snapshot evidence capture, the Portal itself reached
the exact expected three absent-artifact errors, but the surrounding zsh
wrapper then attempted to assign the read-only variable `status`. That wrapper
bookkeeping error was also not counted; the unchanged gate was immediately
rerun with `gate_rc` and produced the recorded result. No tracked source or
toolchain changed for either correction.

The ASan profile was configured and built at current HEAD before its gate;
configure passed in less than 1 s and build passed in 15 s. The TSan profile
was configured in 1 s and rebuilt in 13 s before its gate. Neither profile
produced a zero-test invocation, and zero tests would not have been accepted.

## Automated local evidence

| Gate | Exact local result |
| --- | --- |
| Complete Project I/O browser conformance | PASS with locked Node worker path; Chromium 3/3 in 96 s; WebKit 2 passed/1 structured capability skip in 3 s, reporting missing `opfsSyncAccessHandle` and `opfsWritableReplace` |
| `scripts/core.sh proof` | PASS, exit 0, 50 s; 37/37 selected CTests; schema 9 positive and 11 negative cases with 17 Product artifacts; CLI 11/11; MCP 10/10; Golden audio, CLI/MCP parity, and Assembly Lock match; distribution package and Headless Proof PASS; Product `1.0.16.8`, Channel `canary` |
| `scripts/core.sh test asan full` | PASS, exit 0, 83 s; 53/53 after current-HEAD configure/build; no ASan report |
| `scripts/core.sh test tsan full` | PASS, exit 0, 89 s; 27/27 supported native tests after current-HEAD configure/build; no TSan report |
| `scripts/core.sh test release stress` | PASS, exit 0, 1 s wall time; 2/2 concurrency stress tests, CTest 0.54 s |
| `scripts/web-runtime-host.sh proof` | PASS, exit 0, 613 s; Chromium AudioWorklet/failure 21/21; Python groups 14/14, 13/13, 18/18, 29/29, 11/11, 47/47, and 9/9; Node 27/27; native Web CTest 3/3; distribution 6/6; packaged Chromium 15 passed/1 designed capability skip; WebKit 1 structured capability-limitation pass/10 inapplicable skips; package, Emscripten identity, both automatic generated production source-boundary checks, and two-clean-build reproducibility PASS |
| `scripts/creator-web.sh proof` | PASS, exit 0, 149 s; Vitest 38/38; Python package 7/7 and server 3/3; shared Platform Node 78/78; packaged Chromium 10 passed/1 designed physical-capability skip; WebKit capability boundary 1/1; Project fixture, package, Emscripten identity, and two-clean-build distribution reproducibility PASS |
| `bash tests/build/test_active_tree.sh` | PASS, exit 0, 2 s |
| Pre-snapshot `scripts/architecture-portal.sh check` | EXPECTED NONZERO, exit 1, 15 s; current-content phases passed: Portal tests 41/41, 37 pages, 10 diagram sources/20 outputs, and Product facts `1.0.16.8` at the exact source revision. The only errors were the permitted absent `1.0.16.8` versions entry, snapshot source, and metadata. |
| `scripts/architecture-portal.sh version 1.0.16.8 canary` | PASS, exit 0, 55 s from the clean committed source boundary; preflight/current and post-generation checks passed; froze `1.0.16.8 · canary` at source revision `56b726092e05821bb76ac1e458c84764b228efcd` |
| Standalone generated-boundary `scripts/architecture-portal.sh check` | PASS, exit 0, 25 s before this acceptance update; Portal tests 41/41, 37 pages, 10 diagram sources/20 outputs, matching schema-2 provenance and release truth, typecheck, optimized build, and 42 routes/internal links |

The owner-aware Project I/O evidence travels through the real
C++/Emscripten/OPFS bridge. While platform A holds the Project writer lease,
distinct same-page platform B receives `PROJECT_BUSY` on acquisition and then
directly attempts append, replace, and immutable create. All three mutations
fail before intent creation or target open with `IO_ERROR` and
`storage_condition=project_busy`; existing bytes and length, absent-target
state, and storage/publication intent inventory remain exact. Platform A can
still mutate and release normally, after which B can acquire. Production and
test imports pass `platform_identity_` to the shared owner-aware lease check.

The strengthened production Browser Main case first submits an untracked
native `host.status` response through the conformance-only native-submit seam,
then starts a different real `transport.send(host.status)` before the scheduled
production poll. The unknown response enters `_lmdj_web_host_poll` through
`pollTransport()` and its missing-pending branch. The real pending promise is
rejected with the same once-only `HOST_PROTOCOL_MISMATCH`, its ID is removed
from production `pendingRequests`, notification delivery remains zero, later
sends remain sealed, and terminal-owner release remains once-only. Both
generated conformance-OFF production builds visibly passed the automatic
source-boundary guard, including rejection of conformance-only seams.

The generated boundary was not hand-edited. It contains the `versions.json`
entry, 37 versioned documents, one schema-2 metadata file, one generated
sidebar, and 20 immutable diagram files: 60 generator-owned files in all. The
37 generated documents and 20 diagram files byte-match their source
projection. The immutable `1.0.16.6` and `1.0.16.7` trees retain their audited
pre-freeze hashes and zero diff.

## Physical acceptance rows

| Platform | Browser | Input / journey | Status |
| --- | --- | --- | --- |
| macOS | Safari | Pointer, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| macOS | Chrome | Pointer, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| macOS | Chrome | Physical MIDI, built-in or wired output, 500 events plus physical timing sample | `deferred / unverified` |
| iPadOS | Safari | Touch, built-in or wired output, 500 triggers plus 10-minute foreground run | `deferred / unverified` |
| iPadOS | Safari | Touch background, foreground, lock, unlock, and route interruption | `deferred / unverified` |

All five rows remain outside automated PASS. Automation does not prove
physical input latency, acoustic output, subjective audio quality, device
permission behavior, touch ergonomics, background or lock-screen recovery, or
long-session stability. These rows continue to block physical-pass, `beta`,
and `stable`.

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

The snapshot's `canary` field records an immutable local documentation
candidate; it does not perform or prove Channel promotion. No push, Pull
Request, CI, merge, tag, Release, deployment, publication, public smoke, or
Channel promotion occurred as part of this local acceptance run.
