# Stage 8 Sample Editor Acceptance — 2026-08-09

## Current status

Stage 8 is allocated as Product Build `1.0.22.0 canary` by
`ebaf2fea0e6a2b150fb3fb1229dbf5e30e26a322`. The immutable Architecture
Portal snapshot committed by `9bc9f693470ebe95a20b8849c71e9590d4bedce6`
authenticates that exact allocation revision and Assembly lock
`206cfa444a495595ac180d1467676de834684661abc57981c943fe620f339518`.
Later implementation fixes do not rewrite that immutable candidate projection.

The current reviewed implementation is `9188410` on
`feat/stage8-sample-editor`. It includes the recovery-trigger ownership fix
`4667474023a421b56f569dab5d186dd58d75d5ee` and the two merge-review fixes:
same-token recovery of valid incomplete Sample staging, and preservation of a
successful mutation receipt when preview cleanup or authoritative inspection
fails after commit.

Automated Core, stress, Creator unit/build, Sample Editor Chromium, WebKit
capability, and Portal gates pass at this revision. The complete Creator Proof
is not currently green: its general Chromium lifecycle group reproducibly has
three input-observation timeouts, recorded below. Therefore this record does
not claim final automated acceptance or readiness for merge. Stage 8B remains
unimplemented and unversioned.

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

All commands below ran on 2026-08-14 against implementation revision
`9188410`. Clean-source Proof used Emscripten 6.0.5, Node 22.16.0, and its
bundled Python 3.13.3.

| Gate | Result |
| --- | --- |
| `scripts/core.sh configure dev` | pass |
| `scripts/core.sh build dev` | pass |
| `scripts/core.sh test dev full` | 54/54 pass |
| `scripts/core.sh test dev stress` | 2/2 pass |
| `scripts/core.sh proof` | 38/38 proof tests plus schema, dependency, CLI/MCP parity, Golden audio, package acceptance, and headless proof pass |
| Creator Vitest and production build | 222/222 pass; TypeScript and Vite production build pass |
| `scripts/creator-web.sh proof` | Project/Sample fixtures, byte-identical distributions, Creator 222/222, package 9/9, server 3/3, Runtime Node 127/127, Sample Editor Chromium 1 pass/1 declared skip, and both WebKit capability checks pass; general Chromium is **not green** at 11 pass/3 fail/1 skip |
| `bash scripts/verify-core-dependencies.sh` | pass |
| `bash tests/build/test_active_tree.sh` | pass |
| `python3 tests/build/version_test.py` | pass |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json` | `1.0.22.0` pass |
| `scripts/architecture-portal.sh check` | 47/47 tests, 37 pages, 10 diagram sources/20 outputs, release-doc snapshot, typecheck/build, and 42 routes/internal links pass |

The three reproducible Chromium failures are the lifecycle journeys at
`creator_web_lifecycle.spec.mjs:346`, `:383`, and `:421`: two loop-toggle
journeys remain `data-outcome=idle` after Enter, and the persisted-page journey
does not observe a post-pageshow keyboard outcome. Both full Proof attempts had
the same 11/3/1 result. They are not converted into a pass by the separately
green Sample Editor journey.

## Local artifact evidence

The Core and Creator Proof commands generated local build/package outputs and
proved the Creator distribution byte-identical across two clean builds. They
are not released or published artifacts. Because the overall Creator Proof is
not green, this record deliberately does not promote those transient outputs
to acceptance artifacts or preserve their hashes. No release archive, tag, or
GitHub Release was created by this run.

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
| Push | performed through remote revision `bba79c1b5cd6c08aca1e56f0d02a7f77f113f9a5`; review fix `9188410` remains local |
| Pull Request | Draft PR #137 exists; it remains Draft |
| Merge | not authorized / not performed |
| Product tag or GitHub Release | not authorized / not created |
| Deployment or publication | not authorized / not performed |
| Channel promotion | not authorized / not performed |
