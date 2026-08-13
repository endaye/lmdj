# Stage 7 Remediation Merged-main Proof — 1.0.21.0

## Evidence boundary

This record closes the exact-merge Proof gate for the Stage 7 review
remediation. It binds Product Build `1.0.21.0` to the protected squash merge,
the full `main` push workflow, and a fresh local Proof rerun from the same merged
revision. The documentation commit that adds this record is later than the
tested revision and does not pretend that its own bytes were part of the
Product Proof.

This record does not create or authorize a Product tag, GitHub Release,
deployment, publication, or Channel promotion. Safari Pointer, Chrome Pointer,
iPadOS Touch, and iPadOS lifecycle remain separate physical rows and are not
upgraded by automated evidence.

## Exact merge binding

| Field | Value |
| --- | --- |
| Product / Platform / Creator / Formal Host | `1.0.21.0` / `0.2.1` / `1.1.3` / `1.2.8` |
| Channel | `canary` |
| Pull Request | [#134](https://github.com/endaye/lmdj/pull/134), `fix(creator): accept physical MIDI on all channels` |
| PR head | `0f403e805694bce957644e004090dda8d60cbaf6` |
| Squash merge revision | `5613158240f7e31385ccb5d175bded3c245ae33b` |
| Merge time | `2026-08-13T09:47:14Z` |
| Base before merge | `f4674ada631d6af7ad8b9dd9f440671c2736d293` |
| PR-head / merge tree | identical: `5251522137323f926a8bfa4c04088f5abd31a9eb` |
| Assembly Lock SHA-256 | `4c76d77560de4c3975fa7114ad3c05736ef2406dab775aff7cce0d62ee50f26b` |
| Snapshot metadata SHA-256 | `c9fa38bf5fb40385683926a8e20a918e78e7d781f73dd1a999b616d7da2d1bb9` |
| Snapshot source / commit | `5939c82d18864bc16c0bcf90b907c61da1357f5b` / `1a7e84e94fd00030c44b48cd9f597cc42d5ca37a` |

`git diff --exit-code 0f403e8 5613158` returned success, and both revisions
resolve to the same tree above. The squash changed commit identity only; the
tested Product tree is byte-identical to the protected PR head.

## Protected PR Proof

PR workflow [31684663825](https://github.com/endaye/lmdj/actions/runs/31684663825)
ran at exact PR head `0f403e8`, completed `success`, and was the gate that
permitted the protected merge. Every selected lane and the single aggregate
`PR Gate` completed successfully. In particular, `web-runtime-host` passed on
the trusted Linux Runner after its writer-handoff test budget was aligned with
the Product's existing 60-second reopen contract.

## Exact merged-main Proof

The merge triggered full `push` workflow
[31688172806](https://github.com/endaye/lmdj/actions/runs/31688172806) at exact
revision `5613158240f7e31385ccb5d175bded3c245ae33b`.

| Field | Value |
| --- | --- |
| Event / mode | `push` / `full` |
| Created / completed | `2026-08-13T09:47:17Z` / `2026-08-13T10:25:48Z` |
| Workflow conclusion | `success` |
| Scope manifest | all 14 closed lanes selected; reason includes `full event: push` |
| Job result | 20 `success`; 1 designed `skipped` fallback; 0 failed |
| Aggregate gate | `PR Gate: success` |

Runner ownership and terminal results were:

| Runner class | Jobs | Result |
| --- | --- | --- |
| GitHub-hosted control/Web | Change Scope, CI contract, Deploy contract, Chameleon Lab, Docs/static, runner selectors, Creator Web, Web Toolchain Conformance, Architecture Portal | all `success` |
| `endaye-mbp-m1` | macOS gates (primary) | `success` |
| `contabo-lmdj-linux` | core coverage, Web Runtime Lab, Core Ubuntu, Core ASan | all `success` |
| `contabo-lmdj-linux-02` | Core package, Formal Web Runtime Host | both `success`; Host ran `09:53:29Z`–`10:25:35Z` |
| GitHub-hosted adjudicators | Core macOS, Core ASan macOS, PR Gate | all `success` |
| GitHub-hosted fallback | macOS gates fallback | `skipped` by design because primary succeeded |

The retained `ci-scope-5613158…` artifact records every one of
`chameleon_lab`, `ci_contract`, `core_asan`, `core_coverage`, `core_macos`,
`core_ubuntu`, `creator`, `deploy_contract`, `docs_static`, `package`, `portal`,
`web_runtime_host`, `web_runtime_lab`, and `web_toolchain` as `true`.

## Fresh local rerun from the merge revision

From a clean isolated worktree at exact `5613158`, the following commands were
rerun on 2026-08-13 in Asia/Shanghai. The Web gates used Node `22.16.0`, npm
`10.9.2`, Emscripten tag `6.0.5`, emsdk revision
`dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`, and Playwright `1.62.1`.

| Command / gate | Fresh result |
| --- | --- |
| `scripts/core.sh configure dev` / `build dev` | PASS; AppleClang `21.0.0.21000101`, Python `3.11.15` |
| `scripts/core.sh test dev full` | PASS; 53/53 |
| `scripts/core.sh test dev stress` | PASS; 2/2 |
| `scripts/core.sh coverage check` | PASS; lines 82.40% (16166/19620), branches 67.89% (4496/6622) |
| `scripts/core.sh proof` | PASS; Release 37/37, Product `1.0.21.0`, Channel `canary`, Assembly Lock `MATCH` |
| `scripts/web-toolchain-conformance.sh proof` | PASS; Chromium toolchain 2/2, Web Project I/O 3/3, AudioWorklet/failure 21/21; WebKit limitation boundaries retained |
| `scripts/web-runtime-host.sh proof` | PASS; Chromium 15 passed/1 designed skip; WebKit 1 passed/10 capability skips; deterministic package and cleanup suites passed |
| `scripts/creator-web.sh proof` | PASS; Vitest 62/62, Python package 7/7, server 3/3, Platform 88/88, Chromium 13 passed/1 designed physical-MIDI skip, WebKit 1/1 |
| `scripts/architecture-portal.sh check` | PASS; 47/47 tests, 37 pages, 10 diagram sources/20 outputs, immutable `1.0.21.0` snapshot, optimized build, 42 routes/internal links |
| dependency / active-tree / version gates | PASS; vendored/offline dependencies, active source tree, Product version, Assembly and lock |

## Manual and physical evidence retained separately

- The complete ten-step keyboard/hearing Canary passed on Product `1.0.20.0`.
- Chrome plus physical AKAI MPD218 passed on corrected Product `1.0.21.0`,
  including Channel-10 Pads, Creator Bank mapping, reconnect, suspend,
  reauthorization, and reload/reopen. The final report was `1/1/0`, with
  SHA-256 `b0491e75b8f275aaef9325ca0b240385cbe7e24fa02243c0e6ac934830f4d603`.
- macOS Safari Bundle import did not reproduce a greater-than-20-second
  `importing` stall.

Those observations do not imply the remaining rows passed:

| Platform | Browser | Input / journey | Status |
| --- | --- | --- | --- |
| macOS | Safari | Pointer | `deferred / unverified` |
| macOS | Chrome | Pointer performance | `deferred / unverified` |
| iPadOS | Safari | Touch | `deferred / unverified` |
| iPadOS | Safari | Lifecycle | `deferred / unverified` |

This satisfies the remediation design's exact merged-main Proof gate while
preserving the explicit physical-evidence boundary. It is not a physical
matrix, `beta`, `stable`, release, or deployment claim.
