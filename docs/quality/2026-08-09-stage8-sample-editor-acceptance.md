# Stage 8 Sample Editor Acceptance — 2026-08-09

## Current status

Stage 8 automated local acceptance passed on `feat/stage8-sample-editor` at
verified implementation revision `5f4299d5044ae1181951d004f2e680801ee0602a`
on 2026-08-12. After a conflict-free rebase onto current `main`
`5bf4ace5bf418d6a6d7749586f541fbb7192e9aa`, the patch-equivalent current
implementation revision is `397afae374f1866751642a87a0a9839bf608bc83`;
`git range-diff` marked all 35 Stage 8 commits equivalent and the branch was
0 behind / 35 ahead. The allocated Product identity is `1.0.17.0 canary`. Its
immutable Architecture Portal snapshot records source revision
`195001b494f1c74995dc83fd35b5add00154edfd`; later commits hardened Creator
recovery lifecycle ownership and refreshed acceptance evidence without changing
the governed Product manifests or Assembly projection. The Portal consistency
check accepts that unchanged immutable projection.

This document does not claim a push, Pull Request, merge, tag, Release,
deployment, publication, Channel promotion, physical device result, or human
hearing result. Stage 8B remains unimplemented and unversioned.

## Automated acceptance contract

| Evidence | Required result |
| --- | --- |
| Creator unit/component tests | Sample state, actions, controls, waveform, input, file, lifecycle, recovery, and privacy suites pass |
| Package and server tests | The optimized package contains the Stage 8 surface and same-build Runtime, serves immutable exact bytes, and rejects source maps, debug/private paths, Project parsers, alternate audio engines, and retired Contracts |
| Packaged Chromium | A real Facade journey imports a v1 bundle without migration, imports a WAV into an empty Pad, observes v2 Project Truth and defaults, validates content-derived waveform/viewport behavior, commits trim, exercises all four modes plus Volume/Mute/Reset, cancels and confirms Replace, proves typed negative paths, recovers a saved/runtime split, and reloads without duplicate import |
| Packaged WebKit | The actual structured capability boundary is private and protocol-correct; this is not physical Safari acceptance |
| Creator clean-source Proof | Two clean distributions are byte-identical and every required Creator/browser lane passes |
| Architecture Portal | Current facts, docs, diagrams, release-doc checks, typecheck/build, routes, and links pass |

The Chromium failure injection is accepted only after the real Runtime reports
the bounded live-bank resource failure. The test records the exact saved and
runtime revisions and verifies that Retry Prepare converges without replaying
the Project mutation.

## Automated results

All commands below ran from a clean tracked tree at implementation revision
`5f4299d5044ae1181951d004f2e680801ee0602a`. Browser and Creator gates used the
locked Emscripten 6.0.5 toolchain, Node 22.16.0, and its bundled Python 3.13.3.

| Gate | Result |
| --- | --- |
| `scripts/core.sh configure dev` | pass |
| `scripts/core.sh build dev` | pass |
| `scripts/core.sh test dev full` | 54/54 pass |
| `scripts/core.sh test dev stress` | 2/2 pass |
| `scripts/core.sh coverage check` | 55/55 tests pass; all module thresholds pass |
| `scripts/core.sh proof` | 38/38 proof tests plus schema, dependency, CLI/MCP parity, Golden audio, package acceptance, and headless proof pass |
| `scripts/creator-web.sh test` | Creator 195/195, package 9/9, server 3/3, Runtime Node 117/117 pass |
| `scripts/creator-web.sh proof` | reproducible Project/Sample fixtures and byte-identical Creator distributions pass; Chromium 11 pass/1 capability skip; real Sample Editor 1 pass; declared WebKit capability paths pass |
| `bash scripts/verify-core-dependencies.sh` | pass |
| `bash tests/build/test_active_tree.sh` | pass |
| `python3 tests/build/version_test.py` | pass |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json` | `1.0.17.0` pass |
| `scripts/architecture-portal.sh check` | 42/42 tests, 37 pages, 10 diagram sources/20 outputs, release-doc snapshot, typecheck/build, and 42 routes/internal links pass |

Coverage evidence at this revision records overall line coverage 83.23% and
branch coverage 69.26%. Application Facade line coverage is 84.05%; Audio
Runtime 90.22%; Authoring Domain 89.19%; Foundation 91.16%; Project Cooker
90.00%; Project I/O 70.69%; and Provider API 80.84%. The report and summary
SHA-256 values are respectively
`906374cde56040793f90c0bf546cb1a2001d2999b39f4e534fca5cf3e9ac6c8f`
and
`20186486a0496dea3c1beff1888b35d10ebb9299eb5043fc5e6a9269f32328e5`.

## Local artifact evidence

These are local proof outputs, not released or published artifacts.

| Artifact | SHA-256 |
| --- | --- |
| Core Release build manifest | `13583f1097c47d46c6f634030fc1e412fca0e129c531ea772c9834494e4126b0` |
| Creator Host manifest | `0e56e927e2276436fc39276aa9eef7f1e9ac7e096171c070f5157d0dfd39332c` |
| Creator main JavaScript | `d3a3ee269ea03151157fb02e688c6c5f406351dc7d0bda10eedccf3b9ef0ef14` |
| Creator Runtime Wasm | `060c23a9f470d92c8e059ac4d88c9e769d7619bf1d7fc80baecdccf8e2ec9f0b` |
| Creator Runtime JavaScript | `7c134fd11043ab934fb6eafc4d143687b5364d509316334400b39fc434568ec3` |
| Creator styles | `9ef489e0968b874a12efb69d75847c7c466b99b5fdf292ae6b851c29889de80c` |
| Web toolchain identity | `f9a959a74481c095b07d120f3fd8b39a18e1211ccb69e5fd68d2573176797149` |
| Immutable Portal metadata | `e99229497fda374125e66e39171bb1089ef9307612d6f98470a34d0d01423dce` |

No release archive, detached archive checksum, tag, or GitHub Release was
created by this acceptance run.

## Prohibited-boundary audit

| Boundary | Result |
| --- | --- |
| Retired `lmdj.patch.v1` / `lmdj.materials.v1` in active product source | none; remaining occurrences are governed history, tests/fixtures, versioned snapshots, or package deny-list checks |
| Creator Project or storage parser | none |
| Source maps in the packaged Creator distribution | none |
| Alternate browser audio engine | none; the packaged journey uses the governed Runtime Host and AudioWorklet path |

## Manual and physical acceptance rows

| Platform | Browser / device | Journey | Status |
| --- | --- | --- | --- |
| macOS | Chrome | Human hearing and subjective audio quality | `deferred / unverified` |
| macOS | Chrome | Physical MIDI controller | `deferred / unverified` |
| macOS | Safari | Pointer plus physical hearing | `deferred / unverified` |
| iPadOS | Safari | Physical touch ergonomics | `deferred / unverified` |
| iPadOS | Safari | Background, lock-screen, and recovery lifecycle | `deferred / unverified` |

The five inherited Stage 6 physical rows also remain `deferred / unverified`:
macOS Safari pointer, macOS Chrome pointer, macOS Chrome physical MIDI, iPadOS
Safari touch, and iPadOS Safari lifecycle. Automation does not convert any of
these rows into a pass. They do not block a canary implementation merge, but
they block any physical-pass claim and promotion to Beta or Stable.

## External state

| Transition | Status |
| --- | --- |
| Push | not authorized / not performed |
| Pull Request | not authorized / not created |
| Merge | not authorized / not performed |
| Product tag or GitHub Release | not authorized / not created |
| Deployment or publication | not authorized / not performed |
| Channel promotion | not authorized / not performed |
