# Stage 8 Sample Editor Acceptance — 2026-08-09

## Current status

Stage 8 is allocated as Product Build `1.0.22.0 canary` by
`ebaf2fea0e6a2b150fb3fb1229dbf5e30e26a322`. The immutable Architecture
Portal snapshot committed by `9bc9f693470ebe95a20b8849c71e9590d4bedce6`
authenticates that exact allocation revision and Assembly lock
`206cfa444a495595ac180d1467676de834684661abc57981c943fe620f339518`.
Later implementation fixes do not rewrite that immutable candidate projection.

The accepted implementation is `ca846f96b1a9c73894948bfa32c1aef1968b6e85`, the
exact `feat/stage8-sample-editor` head that Pull Request #137 carried. It was
squash merged into `main` as `51d9e4748cc12a4423954a159949b7b165513789` on
2026-08-16. It includes the recovery-trigger ownership fix
`4667474023a421b56f569dab5d186dd58d75d5ee`, the two merge-review fixes
(same-token recovery of valid incomplete Sample staging, and preservation of a
successful mutation receipt when preview cleanup or authoritative inspection
fails after commit), the later Creator lifecycle, Web Runtime Voice-overflow,
Facade waveform, Cooker GCC and Web Project I/O hardening, and two merged-`main`
drift fixes described under "Pre-merge drift fixes".

The complete exact-head CI matrix is green at `ca846f96`, including the full
Creator Proof. The three reproducible general-Chromium lifecycle timeouts that
an earlier revision of this record reported are no longer present: those
journeys now live at `creator_web_lifecycle.spec.mjs:402`, `:438` and `:476`
and all pass. This record therefore claims automated acceptance at `ca846f96`.

Physical and manual acceptance keeps the exact per-row state below; automation
does not convert those rows. The macOS Chrome hearing row is now a measured
failure rather than a deferred row. Stage 8B remains unimplemented and
unversioned by this Product Build.

Squash merging collapsed the allocation revision, so the `1.0.22.0` snapshot
provenance was re-authenticated on `main` by
`01e3ae24bfa2512a010e06eca0ef954ff3022397` (Pull Request #169), which adds only
`apps/architecture-portal/versioned_provenance/version-1.0.22.0-squash-witness.json`
and rewrites no immutable snapshot content.

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

Acceptance evidence is the exact-head `Core CI` run
[31927768644](https://github.com/endaye/lmdj/actions/runs/31927768644) on
`ca846f96`, completed successfully on 2026-08-16. Every lane below is a job of
that one run; no result is carried over from another revision.

| Gate (job) | Result |
| --- | --- |
| `Change Scope` | success |
| `Docs / static` | success |
| `CI contract` | success |
| `Architecture Portal / portal` | success |
| `core (ubuntu-latest)` | success; `Headless Core Proof: PASS`, including proof path safety, CLI/MCP Facade parity and Core distribution package acceptance |
| `core-asan` | success; 61/61 full-tier tests and 2/2 stress-tier tests pass under ASan |
| `core-coverage` | success; `Core coverage gate: PASS` |
| `macOS gates (primary)` / `core (macos-latest)` | success; `Headless Core Proof: PASS` and 30/30 native tests |
| `core-asan-macos` | success |
| `Core package` | success; 24/24 tests |
| `web-toolchain-conformance` | success; `Web Toolchain Conformance Proof: PASS` |
| `web-runtime-host` | success; `Web Runtime Host Proof: PASS` |
| `creator-web` | success; `Creator Web Proof: PASS` (detailed below) |
| `web-runtime-lab` | success |
| `Deploy contract` | success |
| `Chameleon Lab` | success |
| `PR Gate` | success |

`Creator Web Proof: PASS` decomposes into: `Creator Web distribution
reproducibility: PASS` (two clean builds byte-identical), Creator Vitest
222/222 across 11 files, package 9/9, server 3/3, Runtime Node 127/127,
general Chromium 14 pass with 1 declared skip out of 15, Sample Editor
`creator-sample-chromium` 1 pass with 1 declared skip, and both WebKit
capability checks pass.

The general-Chromium lifecycle group is green. The three journeys an earlier
revision of this record reported as reproducible timeouts now run at
`creator_web_lifecycle.spec.mjs:402`, `:438` and `:476` and all pass in this
run. The earlier 11 pass/3 fail/1 skip result stood at implementation revision
`9188410` and is superseded historical context, not current evidence.

### Pre-merge drift fixes

Two defects were surfaced only when the Pull Request left Draft and the full
matrix first executed, in run
[31927144643](https://github.com/endaye/lmdj/actions/runs/31927144643) on
`fe55a9e9`. Both were drift between the branch and merged `main`, not product
defects, and both are fixed in the accepted head:

1. `2ca0d17f fix(release): bind sanitized-target test to the stage 8 build` —
   `release_prepare_test.test_failed_target_command_reports_a_sanitized_reason`
   still pinned identity `1.0.21.0`, so the exact-target validator rejected it
   on the manifest comparison before reaching the Portal snapshot command whose
   sanitized diagnostic the test asserts. This failed `core (ubuntu-latest)`,
   `core (macos-latest)`, `core-asan`, `core-coverage` and `Deploy contract`.
2. `ca846f96 fix(creator): assert the packaged sample editor lane by its
   binding` — `apps/creator-web/test/package_test.py` asserted a literal
   `ci.yml` step name that the merged runner-topology refactor replaced with the
   shared `.github/actions/web-ci-proof` composite action. The lane still runs
   `scripts/creator-web.sh proof`; only the assertion was stale. This failed
   `creator-web`.

### Local artifact evidence

The CI Core and Creator Proof lanes generated build and package outputs and
proved the Creator distribution byte-identical across two clean builds. They
are not released or published artifacts, and this record does not promote them
to acceptance artifacts or preserve their hashes. No release archive, tag, or
GitHub Release was created by this run.

## Prohibited-boundary audit

| Boundary | Result |
| --- | --- |
| Retired `lmdj.patch.v1` / `lmdj.materials.v1` in active product source | none; remaining occurrences are governed history, tests/fixtures, versioned snapshots, or package deny-list checks |
| Creator Project or storage parser | none |
| Source maps in the packaged Creator distribution | none |
| Alternate browser audio engine | none; the packaged journey uses the governed Runtime Host and AudioWorklet path |

These boundaries are enforced automatically by the `creator-web` and
`Core package` gates, both `success` in run `31927768644` at `ca846f96`, and the
source inventory was re-inspected on merged `main` at
`01e3ae24bfa2512a010e06eca0ef954ff3022397`.

## Manual and physical acceptance rows

| Platform | Browser / device | Journey | Status |
| --- | --- | --- | --- |
| macOS | Chrome | Human hearing and subjective audio quality | **`PASS` 2026-09-01 on `1.0.40.0`** — all eight checklist groups passed; the operator corrected the initial interpretation of the 40 ms loop's rapid texture after exact replay ([evidence](../release-evidence/2026-09-01-stage8-m2-macos-chrome-hearing-1.0.40.0.md)) |
| macOS | Chrome | Physical MIDI controller | `deferred / unverified` |
| macOS | Safari | Pointer plus physical hearing | **`PASS` 2026-09-04 on deployed `1.0.41.0`** — built-in trackpad covered all Pads/Banks and mistake targets, focus plus explicit audio recovery, strict `0.505–0.545 s` trim, four playback modes, Volume/Mute and reload persistence; the clean report recorded revision 83 and 2 admitted / 2 outcomes / 0 rejected ([evidence](../release-evidence/2026-09-04-stage8-m8-macos-safari-pointer-hearing-1.0.41.0.md)) |
| iPadOS | Safari | Physical touch ergonomics | `deferred / unverified` |
| iPadOS | Safari | Background, lock-screen, and recovery lifecycle | `deferred / unverified` |

The macOS Safari Creator Pointer/hearing row now has its own exact-Build human
evidence. Remaining rows in this matrix stay `deferred / unverified` until
their named operators and devices produce equivalent evidence. Separate Web
Runtime Lab, Chrome, MIDI and iPadOS records are not inferred from this pass;
automation also cannot convert another physical row into a pass.

The 2026-09-01 M2 run preserves rather than overwrites the 2026-08-17 stopped
run. On the exact `1.0.40.0` package, a strict non-zero trim boundary, One
Shot, Gate release, Loop Gate, Loop Toggle, Volume/Mute, all 16 Pads, Replace
and reload passed by ear. The approximately 40 ms loop's rapid repeated
texture was initially described as a click; exact replay produced no obvious
independent seam transient, and the operator explicitly corrected the sound
to normal short-loop playback. The evidence retains both the superseded
description and the final authoritative classification.

The 2026-09-04 M8 run exercised the deployed `1.0.41.0` Creator on macOS
Safari with a built-in trackpad and physical hearing. It covered all Pads and
Banks, repeated/double/drag/mistake targeting, mode navigation, focus and
explicit lifecycle recovery, strict non-zero trim, all four trigger modes,
Volume/Mute, reload/reopen persistence and a clean final report. The retained
report binds Project/Runtime revision 83, state `running`, 2 admissions / 2
outcomes / 0 rejections and no error. This upgrades only M8; macOS Safari
capture M7 and Stage 9 Safari Sequence acceptance remain separate.

## External state

| Transition | Status |
| --- | --- |
| Push | performed; the accepted head `ca846f96b1a9c73894948bfa32c1aef1968b6e85` was the exact remote branch tip |
| Pull Request | #137 was marked ready for review and is `MERGED` |
| Merge | authorized and performed on 2026-08-16; squash merged as `51d9e4748cc12a4423954a159949b7b165513789` |
| Snapshot provenance follow-up | performed; #169 merged as `01e3ae24bfa2512a010e06eca0ef954ff3022397` and the `Release identity audit` on `main` returned to `success` |
| Product tag or GitHub Release | not authorized / not created; `lmdj-v1.0.22.0` remains `allocated` |
| Deployment or publication | not authorized / not performed |
| Channel promotion | not authorized / not performed |

Merging authorized none of the remaining transitions. A tag, Draft Release,
publication, Runtime deployment, and Channel promotion each remain separate
authorization boundaries.
