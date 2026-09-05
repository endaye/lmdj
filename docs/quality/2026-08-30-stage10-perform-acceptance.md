# Stage 10 Perform Acceptance — 2026-08-30

## Current status

Current source candidate Product Build `1.0.42.0` integrates the complete
Stage 10 Perform capability. It is the first Build in which
`lmdj.project.v4 · 4.0.0` is the only current write truth; `lmdj.project.v3`
joins v1 and v2 as read-only migration input. Authoring Domain is `2.0.0`,
Project I/O is `2.0.0`, Project Cooker is `1.1.0`, Audio Runtime is `3.0.0`,
Application Facade is `3.0.0`, and Web Runtime Platform is `3.0.0`; Core CLI,
Core MCP, Native Host, Formal Web Runtime Host and Creator Web Host are all
`3.0.0`. Foundation stays `0.3.0`, and the Provider, Capability, Assembly,
Bundle, error, module and product-version Contract identities are unchanged.

This ledger records automated source evidence for the integration boundary
only. **Every Stage 10 physical row is `deferred`.** No Perform physical
hearing, MIDI, Touch or device-lifecycle acceptance has been performed, and no
tag, Release, immutable Portal snapshot, deployment, publication or Channel
promotion is claimed here. The immutable `1.0.42.0` snapshot is #438; the
canary Release is #468. Each is a separate authorization boundary.

## Allocation audit

The pre-mutation allocation audit was repeated immediately before any identity
was written, per the plan's Task 10 Step 1. It read protected `origin/main`,
every active module and Host manifest, `products/lmdj/version.json`, the
Assembly and its lock, the immutable snapshot inventory, local and remote tags,
GitHub Releases, open Issues and Pull Requests, and
`docs/release-evidence/release-intents.json`. Product Build `1.0.42.0` and
every module, Host and Contract target in the plan's version table remained
unoccupied on every allocation surface, so the locked table was applied
unchanged.

## Integrated identity

| Component | Baseline `1.0.41.0` | Integrated `1.0.42.0` |
| --- | --- | --- |
| Product Build | `1.0.41.0` | `1.0.42.0` |
| `lmdj.project` Contract | `v3 · 3.0.0` current write truth | `v4 · 4.0.0` current write truth; `v3` demoted to migration input |
| foundation | `0.3.0` | `0.3.0` |
| provider-sdk | `1.1.4` | `1.1.4` |
| authoring-domain | `1.0.0` | `2.0.0` |
| project-io | `1.0.1` | `2.0.0` |
| project-cooker | `1.0.0` | `1.1.0` |
| audio-runtime | `2.0.1` | `3.0.0` |
| application-facade | `2.1.1` | `3.0.0` |
| web-runtime-platform | `2.0.1` | `3.0.0` |
| core-cli | `2.0.0` | `3.0.0` |
| core-mcp | `2.0.0` | `3.0.0` |
| native-host | `2.0.0` | `3.0.0` |
| web-runtime-host | `2.1.1` | `3.0.0` |
| creator-web | `2.1.1` | `3.0.0` |

Unchanged Contracts: `lmdj.project-bundle.v1 · 1.1.0`, `lmdj.capability.v2 ·
2.0.0`, `lmdj.assembly.v2 · 2.0.0`, `lmdj.error.v1 · 1.1.0`, `lmdj.module.v1 ·
1.0.0`, `lmdj.product-version.v1 · 1.0.0`. Both local Proof Providers remain
`1.0.5` with `proof.candidate.v2 · 2.0.0`, and the Provider policy still allows
only `local`, `public` and `proof.execute`.

## Resource and distribution identity

The generated Runtime identity for `1.0.42.0` carries **nine** exact
`resource_limits`, two of which are new in this Build:

| Key | Value |
| --- | --- |
| `decoded_float_pcm_bytes_per_bank` | `67108864` |
| `decoded_float_pcm_bytes_total` | `134217728` |
| `decoded_float_pcm_bytes_resident` | `268435456` |
| `imported_wav_bytes` | `68157440` |
| `ingest_source_bytes` | `104857600` |
| `ingest_decoded_frames` | `43200000` |
| `ingest_channels` | `2` |
| `perform_recording_frames` | **`86400000`** |
| `perform_recording_queue_batches` | **`32`** |

The private Web protocol version stays `1`, the heap stays 512 MiB, and the
Emscripten identity stays `6.0.5`.

Creator Web `3.0.0` declares **six** expected distribution assets under
`lmdj.creator-web.distribution.v1`: `host_main`, `runtime_script`,
`runtime_wasm`, `host_style`, `capture_worklet` and the new
`perform_master_tap_worklet` at `assets/perform-master-tap.<sha256>.js`. The
diagnostic `web-runtime-host 3.0.0` keeps its fifteen expected assets and
declares **no** tap asset. The shared native manifest gate requires exactly one
`perform_master_tap_worklet` entry for the Creator manifest and exactly zero for
the diagnostic Host, and validates both new limits as positive safe integers.
Older immutable packages keep their own exact identity and are not
retroactively required to carry Stage 10 fields.

## Journey coverage against spec §10

The design authority
`docs/superpowers/specs/2026-08-28-lmdj-stage10-perform-design.md` §10
enumerates twenty-one journeys. Each row records the far side actually
asserted by the current source, not the intent.

| # | Journey | Far side asserted | Result |
| --- | --- | --- | --- |
| 1 | v3→v4 migration | 16 empty `pattern_slots` and empty `performances`; wrong length, duplicate PatternId and dangling PatternId rejected by schema and domain gate | PASS · `domain.migration_v4` |
| 2 | Pattern Slot assign/clear/move | success, precondition failure, revision, receipt replay and collision each carry a Project Store witness | PASS · `domain.performance`, `project_io.performance_lifecycle`, `host.performance_cross_host` |
| 3 | Perform mode enabled | Sample and Sequence regressions unchanged | PASS · Creator Vitest 483/483; packaged `creator_web_sample_editor` and `creator_web_sequence` journeys unchanged |
| 4 | `record.begin` crash matrix | every point recovers to "draft and Journal both present" or to nothing at all; no orphan draft; a second Perform or Sequence begin is `INVALID_ARGUMENT` | PASS · `project_io.performance_journal`, `project_io.performance_lifecycle`, `facade.performance_session` |
| 5 | Raw event admission | Host-supplied tick/frame/sequence rejected; event ID idempotent; gesture IDs paired; owner loss closes open Pads with at least 1 tick | PASS · `facade.performance_gesture_admission`, `project_io.performance_journal` |
| 6 | Pattern Launch | defaults to the next Bar; unclaimed is latest-wins; after claim a later request is deferred; only a real acknowledgement writes the effective tick; failure, cancellation and owner loss leave no ghost event | PASS · `facade.performance_engine_adapter`, `host.web_performance_bridge` |
| 7 | Bank switch | instantaneous, no preparation latency, no glitch, no revision, no event | PASS · `audio.master_fx`, packaged `complete Perform journey` |
| 8 | Per-FX behaviour | each of the eight effects including Cutter is audible in automation and restores on release; Core deduplicates equal values and applies per-FX per-quantum last-write-wins; release orders pending moves; the Host performs no semantic merge | PASS · `audio.master_fx`, `audio.master_fx_determinism`, `facade.performance_gesture_admission` |
| 9 | Global HOLD | freezes the final value; owner loss releases in chain order then `hold_off`; replay end and abort reset to neutral; the same Snapshot plus the same canonical stream is sample-identical | PASS · `audio.master_fx_determinism`, packaged `stopping a saved Performance replay restores neutral FX, HOLD and Pattern state` |
| 10 | Eight-FX stress | CPU and underrun stress with zero-allocation, zero-lock and `noexcept` render guards | PASS · `audio.master_fx_stress`, `audio.master_fx_allocation_guard` (stress tier 11/11) |
| 11 | Flush, stop, save, discard | flush is idempotent and a repeated command ID returns the original receipt; stop does not change the Project; save atomically consumes tail, name and optional WAV; discard removes the draft and Journal | PASS · `project_io.performance_lifecycle`, `facade.performance_session`, packaged `discard deletes its temporary WAV ...` |
| 12 | Recovery | apply and discard carry a complete far-side witness; a fingerprint mismatch retains the recovery artifact; rename, delete and bind fail closed while an active or recovery Journal exists | PASS · `project_io.performance_rebase`, `facade.performance_session`, packaged `owner process loss leaves one recoverable recording ...` |
| 13 | Settings fault points | BPM, Quantize and Swing recover at every `prepare → Project receipt → complete` fault point; a visible receipt never duplicates the mutation; recovery-required blocks new input | PASS · `facade.performance_rebase_matrix`, `project_io.performance_rebase` |
| 14 | Concurrent authoring | a failing Sample command does not stop recording; an unknown Authoring Command fails closed | PASS · `facade.performance_session`, `facade.sample_surface.quota_replay` |
| 15 | Operation schema parity | every P10-D20 operation validates kind, exact keys, missing fields, extra fields, ranges and returned fields; CLI, MCP, Native and Web schemas are isomorphic to the Facade | PASS · `facade.performance_operation_contract`, `host.performance_cli`, `host.performance_mcp`, `host.performance_cross_host` |
| 16 | Replay resolution | replay pins the revision current at begin: a replaced Sample produces the new sound, a moved Pattern follows the current slot, an empty slot is a silent gap, and a mid-replay Project change does not alter the resolved revision | PASS · `cooker.performance_replay`, `facade.performance_replay` |
| 17 | WAV Artifact bind | a path, raw bytes, or a missing or wrong digest or length are rejected; an identical ref is idempotent and a conflicting ref fails closed | PASS · `project_io.performance_lifecycle`, packaged `a retryable WAV bind keeps the real Store receipt path ...` |
| 18 | Streaming WAV | long recordings stream to OPFS; 0, the limit, the limit + 1, the 33rd queue batch, and writer or OPFS failure each seal a legal durable prefix without making render wait | PASS · `project_io.performance_writer_lease_stress`, packaged `an active recording receives an empty-slot acknowledgement ...` |
| 19 | Resample commit | a recording selection commits through the D1 path with complete Lineage; cancellation, failure and quota exhaustion change no Project, Asset, Pad or revision | PASS · `facade.resample_performance`, packaged `complete Perform journey ... resample` |
| 20 | CLI/MCP black box | begin → raw events → acknowledged launch → flush → stop → save → replay → resample completes, plus owner-loss → recovery apply/discard and delayed WAV bind | PASS · `host.performance_cli`, `host.performance-cli-session`, `host.performance_mcp`, `host.performance_cross_host` |
| 21 | Creator Browser journey | Pad, Launch, FX, HOLD, Bank, stop, save, replay and resample are covered against the formal package with no candidate identity routing | PASS (automation only) · packaged Chromium 24/24 against the formal package, no candidate identity routing |

Journey 21's physical half — continuous OPFS write coverage on macOS Safari and
on a physical iPadOS device — is **`deferred`**. Playwright results are state
and boundary evidence, never physical acceptance.

## Physical rows

| Physical row | Status |
| --- | --- |
| Perform macOS Chrome hearing (eight FX, HOLD, Launch) | `deferred` |
| Perform macOS Safari continuous OPFS recording | `deferred` |
| Perform physical iPadOS Safari continuous OPFS recording | `deferred` |
| Perform physical MIDI Pad and FX control | `deferred` |
| Perform long-recording device lifecycle and interruption | `deferred` |

No Perform physical evidence exists. These rows cannot be upgraded by
automation, by a Product Build allocation, by an immutable snapshot, or by a
Release.

## Plan deviations

The Task 10 file inventory in
`docs/superpowers/plans/2026-09-04-lmdj-stage10-creator-master-tap-projection-repair.md`
is incomplete. The following files were required to reach a consistent
`1.0.42.0` identity but were not declared, and are recorded here rather than
silently absorbed.

Identity consumers the plan omitted:

- `tools/web-runtime/runtime-identity.json`
- `tools/web-runtime/generate_runtime_identity.py`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/src/compiled_assembly.cpp`
- `tests/build/version_test.py`
- `apps/creator-web/package.json`
- `apps/web-runtime-host/tools/deployment_smoke.py`

Two of these were genuine source defects rather than stale fixtures: the Host
SemVer had been written to `apps/core-mcp/module.json` and
`apps/creator-web/package.json` without being propagated to
`apps/core-mcp/pyproject.toml`, `apps/core-mcp/lmdj_core_mcp/__init__.py` and
`apps/creator-web/package-lock.json`. Left uncorrected, the Build would have
shipped an internally inconsistent Host identity, and the Creator package
conformance gate would have failed on the lockfile.

Version fixtures the plan omitted:

- `tests/conformance/module_graph_test.py`
- `tests/host/mcp_stdio_test.py`
- `tests/core/facade/application_test.cpp`
- `tests/host/native_host_source_boundary_test.py`
- `apps/architecture-portal/test/repo-facts.test.mjs`

Portal routes the plan omitted:

- `apps/architecture-portal/docs/operations/version-and-release.mdx`, which
  `tests/build/web_runtime_public_deployment_docs_test.py` requires to name the
  current Product Build.
- `apps/architecture-portal/static/diagrams/*.svg` and `*.html`, the committed
  deterministic outputs regenerated from the eight edited source diagrams.

## Snapshot boundary deviation

The plan schedules the immutable Portal snapshot as Task 11 (#438), after
Task 10 merges. That ordering is not reachable: `check-release-docs.mjs`
unconditionally requires a snapshot for the allocated Product Build, `ci.yml`
runs the full `scripts/architecture-portal.sh check`, and six `build.release_*`
tests in the Core `full` tier read
`apps/architecture-portal/versioned_metadata/version-1.0.42.0.json` directly.
Task 10 therefore cannot be green on its own.

The repository's own precedent resolves it: Product Build `1.0.41.0` (#520) and
`1.0.40.0` (#420) both carried the version integration and the immutable
snapshot in the same squash. This Task follows that precedent — the integration
commit and the snapshot commit stay separate, as the plan requires, but ship in
one Pull Request. Per `.agents/pitfalls/squash-witness-provenance.md`, the
snapshot then names a pre-squash revision, so #438 retains the post-squash
source-tree witness and the final evidence.

## Verification commands and results

Every command below was run on a clean worktree at the Task 10 integration
commit. This ledger lives inside that commit, so it does not restate the
commit's own SHA: a squash merge rewrites it in any case. #438 records the
exact merged revision, the post-squash source-tree witness and the remote CI
run IDs once they exist.

| Boundary | Command | Result |
| --- | --- | --- |
| Core full tiers | `scripts/core.sh test dev full` | PASS: 111/111 |
| Stress tier | `scripts/core.sh test dev stress` | PASS: 11/11 |
| Coverage gate | `scripts/core.sh coverage check` | PASS: every scoped threshold met; application-facade lines 85.85% / branches 71.19%, audio-runtime 89.95% / 81.31%, authoring-domain 93.38% / 89.34%, project-cooker 89.46% / 79.89%, project-io 71.06% / 62.87% |
| Core proof | `scripts/core.sh proof` | PASS: 89/89 Release CTest plus module-graph conformance, proof path safety and Core distribution package acceptance |
| Version identity | `python3 scripts/version.py verify --version-file products/lmdj/version.json` | PASS (1.0.42.0) |
| Active tree | `bash tests/build/test_active_tree.sh` | PASS |
| Creator package gate | `python3 apps/creator-web/test/package_test.py` | PASS |
| Creator deployment smoke | `python3 apps/creator-web/test/deployment_smoke_test.py` | PASS |
| Creator secure server | `python3 apps/creator-web/test/server_test.py` | PASS |
| Manifest gate | `ctest --test-dir build/core/dev -R 'host.web_manifest_gate' --output-on-failure` | PASS: 1/1 |
| Portal | `scripts/architecture-portal.sh check` | PASS: 65 tests, 37 current pages, 10 diagram sources / 20 outputs, 42 routes and internal links, and `Product Build 1.0.42.0 snapshot matches repository truth` |
| Clean-tree formal package and Browser proof | `scripts/creator-web.sh proof` | PASS: fixture and distribution reproducibility, Vitest 483/483 across 27 files, packaged Chromium 24 passed / 1 designed skip, Sample Editor 3, Capture 7 passed / 1 skip, denied-capture 1 passed / 7 skips, WebKit capability boundary 1 |

## Formal package digests

The formal `1.0.42.0` Creator package produced the following exact digests.
They bind this ledger to one reproducible package, not to any deployment.

| Artifact | SHA-256 |
| --- | --- |
| Creator distribution manifest (`host-manifest.json`) | `5052dd2dff57d77c27117ca15ffe33d952af3f3db82b67594037f439cf3ce25e` |
| Master-tap processor asset (`assets/perform-master-tap.<sha>.js`, 3,048 bytes) | `93193d732e882bcaa19b7c6ed143e6d747e0e610439bab92f988a600b4a6d3da` |
| Creator main bundle (`assets/main.<sha>.js`) | `01d2bbe46999fe46e16f8cc72c2e6be6ed4f77dc364f6769c3dbf57079ed7434` |
| Assembly lock | `f1bd8d218fba029d1141f6fcc18ff7390d649857c657266dc5027687abd868c6` |
| Portal snapshot source projection | `3d64d3df48753f3c2d1afcc31ca17cdea667d1243e135b0c841f39a89efce96c` |

The hashed master-tap asset name embeds its own SHA-256, and the Creator
manifest carries exactly six assets. The immutable `1.0.42.0 · canary` Portal
snapshot is frozen from that same integration commit.

## Merged evidence

Pull Request [#664](https://github.com/endaye/lmdj/pull/664) squash-merged into
protected `main` on 2026-09-05 as
`0ffa77c0c4f786dc5d9b285f272abe1725250b8d`, which is a verified `main`
ancestor. It carried the Task 10 integration commit and the immutable
`1.0.42.0 · canary` Portal snapshot as two separate commits.

| Boundary | Evidence |
| --- | --- |
| Gating Core CI run | [`33991083518`](https://github.com/endaye/lmdj/actions/runs/33991083518) — success on Integration Queue head `d16e687e` |
| Prior queue Core CI run | [`33987221291`](https://github.com/endaye/lmdj/actions/runs/33987221291) — success on head `904c377c` |
| Squash revision | `0ffa77c0c4f786dc5d9b285f272abe1725250b8d` |
| Post-merge Portal gate | `scripts/architecture-portal.sh check` on merged `main` — PASS, 65 tests, 37 pages, 42 routes, `Product Build 1.0.42.0 snapshot matches repository truth` |

### Snapshot provenance after the squash

`.agents/pitfalls/squash-witness-provenance.md` requires a source-tree witness
when the introducing squash tree cannot equal the frozen source projection —
specifically when the squash additionally carries mutable current-page updates
made *after* the freeze. That condition did not occur here.

Every current Portal page edit landed in the integration commit, and the
snapshot was frozen from that commit afterwards, so the squash tree matches the
recorded source projection exactly. `check-release-docs.mjs` re-ran
`verifySnapshotProvenance` against merged `main` and reported
`Product Build 1.0.42.0 snapshot matches repository truth`, so the schema-2
provenance validates on `main` with no witness. A witness is a conditional
remedy, not an unconditional artifact, so none was written: fabricating one
where provenance already validates would add an immutable provenance record
that documents nothing.

## Evidence separation

This ledger records local automated evidence, the merged Pull Request and its
gating remote CI run. It does not claim a tag, a Release, a deployment, a
publication, a Channel promotion, or any physical device acceptance. Those
remain separate boundaries with their own evidence; the release boundary is
tracked by #468.
