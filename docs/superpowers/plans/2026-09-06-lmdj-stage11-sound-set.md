# LMDJ Stage 11 Sound Set Implementation Plan

> **For agentic workers:** Execute each Task on a short-lived `feat/<task>`
> branch in an isolated worktree. One Task = one GitHub Issue = one
> Conventional Commit = one Pull Request. Do not aggregate Tasks.

**Goal:** Deliver Catalog-only Sound Set v1: validate immutable 16-Pad Bank
Packages, cache them in a Workspace Set Store, preview and install occupied
slots into a user-chosen Bank as ordinary Assets, and expose that path through
Facade and Creator — without a second Pad model, without mutating the original
Set, and without time-stretch.

**Authoring gate:** The authority is the approved
[`2026-08-31-lmdj-stage11-sound-set-design.md`](../specs/2026-08-31-lmdj-stage11-sound-set-design.md)
(S11-D1–D12) plus
[`2026-09-06-sound-set-rights-and-mapping.md`](../../prd/decisions/2026-09-06-sound-set-rights-and-mapping.md)
(S11-Q1–Q3). Any conflict returns to design review; an implementation Task must
not silently choose a different semantic.

**Architecture:** Sound Set is a logical package (canonical manifest +
content-addressed WAV blobs), not an archive. Catalog adapters only resolve
`{object_kind, sha256}`. Host settings own Catalog endpoints, cache, and the
read-only Set Store. Install is one atomic Facade command that reuses the
existing import commit path. Pattern events keep Pad Slot references.

**Tech Stack:** C++20, CMake 3.24+, JSON Schema 2020-12, nlohmann/json,
SHA-256 canonical JSON, existing Facade/Host surfaces, React/TypeScript
Creator, Docusaurus Architecture Portal, GitHub Issues.

**Parent:** [#470](https://github.com/endaye/lmdj/issues/470). This plan
satisfies [#464](https://github.com/endaye/lmdj/issues/464).

## Global Constraints

- Execute each Task on `feat/<task>` in an isolated worktree. Never implement
  on `main`.
- Tasks 3–7 are serial after Stage 10 Task 10 ([#436](https://github.com/endaye/lmdj/issues/436))
  and after [#471](https://github.com/endaye/lmdj/issues/471) freezes the
  `Asset.lineage` `soundset` / `soundset_install` vocabulary. Task 1 may start
  after this plan merges. Task 2 starts after Task 1.
- Hosts use only Application Facade. Catalog endpoints never enter Project
  Truth.
- `lmdj.project.v4` stays the writer Contract. Install creates ordinary Assets
  and Pad assignments; Lineage uses the existing `Asset.lineage` carrier.
  Extending that closed union is #471's Contract SemVer, not a second field.
- Do not add public `lmdj.error.v1` codes. Stable `details.reason` tokens are
  locked below.
- v1 install/apply does no time-stretch or pitch DSP.
  [#347](https://github.com/endaye/lmdj/issues/347) stays Later.
- No Marketplace, purchase, upload, account, or production sound acquisition.
- This plan authorizes local commits only. Push, Pull Request, merge, tag,
  Release, deployment, and Channel promotion remain separate boundaries.
- Before every Task commit: Task-specific tests, `scripts/architecture-portal.sh check`,
  stage only declared files, `git diff --cached --check`, inspect the staged
  diff, commit, inspect `git show --name-status`.

## Locked Constants

```text
SLOT_COUNT                 = 16
SLOT_MIN                   = 0
SLOT_MAX                   = 15
ROLES                      = kick, snare, clap, hat_closed, hat_open, perc,
                             cymbal, bass, melody, chord, vocal, fx, other
SPDX_ALLOWLIST             = CC0-1.0, CC-BY-4.0
OCCUPIED_PAD_POLICY        = keep | replace
LICENSE_SCHEMA_KEYS        = spdx_id, rights_holder, copyright, attribution
```

Role is a Schema enum (unknown value is `soundset_slot_invalid`). SPDX
allowlist is **not** a Schema enum.

Host manifest keys (values allocated at Task 6; Task 2 tests use fixture
limits and exact/+1 fail-closed cases):

```text
resource_limits.maximum_soundset_manifest_bytes
resource_limits.maximum_soundset_blob_bytes
resource_limits.maximum_soundset_unique_bytes
resource_limits.maximum_soundset_staging_bytes
```

## Locked Error Reasons

Public codes stay on `lmdj.error.v1`. Reasons:

| Condition | Code | `details.reason` |
| --- | --- | --- |
| License Schema (missing block/key/type, empty `rights_holder`/`copyright`) | `INVALID_ARGUMENT` | `soundset_manifest_invalid` |
| Slot/role/layout illegal | `INVALID_ARGUMENT` | `soundset_slot_invalid` |
| Occupied collision, policy omitted | `INVALID_ARGUMENT` | `soundset_occupied_conflict` |
| SPDX not allowlisted, BY attribution empty, catalog `license_summary` mismatch | `PERMISSION_DENIED` | `soundset_license_ineligible` |
| Artifact hash or length mismatch | `IO_ERROR` | `soundset_content_mismatch` |
| Catalog unreachable | `IO_ERROR` | `catalog_unavailable` |
| Audio not S8-D6 | `UNSUPPORTED_AUDIO` | `soundset_audio_unsupported` |
| Bank/generation quota | existing | `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED` |

## Locked Facade Surface

Every JSON request includes `operation` plus the exact fields below. Extra
fields are invalid. `uuid` is a lowercase canonical UUID.

| Operation | Kind | Exact fields after `operation` |
| --- | --- | --- |
| `soundset.catalog.list` | query | `workspace_path` |
| `soundset.inspect` | query | `workspace_path, set_id, version, manifest_sha256` |
| `soundset.map.preview` | query | `project_path, bank_id, set_id, version, manifest_sha256` |
| `soundset.install` | command | `project_path, command_id, expected_revision, bank_id, set_id, version, manifest_sha256, occupied_pad_policy?` |

`soundset.map.preview` is the pure function
`map(manifest, bank occupancy) → {proposed, collisions, kept}` and mutates
nothing. `occupied_pad_policy` is required on `soundset.install` when
`collisions` is non-empty; omitted + collisions → `soundset_occupied_conflict`
and zero Project change.

## Dependency Order

```text
This plan #464
  └─ Task 1 Contract/package validation
       └─ Task 2 Catalog transport / cache / Set Store
            └─ (#436 merged) + (#471 lineage vocabulary frozen)
                 ├─ Task 3 Project adoption
                 │    └─ Task 4 Facade
                 │         └─ Task 5 Creator
                 └─ Tasks 1–5 ── Task 6 Assembly / current Portal
                                    └─ Task 7 acceptance
```

[#436](https://github.com/endaye/lmdj/issues/436) is still OPEN. Do not start
Tasks 3–7 while it is open. #471 may proceed in parallel as a Stage 12 design
Task; Stage 11 Task 3 consumes its frozen `derivation.kind` / `source.kind`
tokens and must not invent a second Lineage model.

## Design Traceability

| Decision | Primary Tasks | Acceptance witness |
| --- | --- | --- |
| S11-D1 canonical identity | 1 | canonical-bytes golden vectors; non-canonical JSON rejected |
| S11-D2 schema + license keys | 1 | four keys required; allowlist not a Schema enum |
| S11-D3 S8-D6 audio | 1, 2 | `soundset_audio_unsupported` |
| S11-D4 role enum | 1 | unknown role → `soundset_slot_invalid` |
| S11-D5 preview, no Project change | 4, 5 | inspect/preview leave revision unchanged |
| S11-D6 catalog adapters, no archive | 2 | local adapter rejects symlink/`..`/non-regular file |
| S11-D7 download, unique bytes, Host limits | 2 | exact/+1 of four limits; hash mismatch invisible |
| S11-D8 InstallSoundSet, quota, policy | 3, 4 | three write-sets; quota zero-change |
| S11-D9 soundset Lineage | 3 | typed source fields all present |
| S11-D10 error tokens | 1–4 | no new public error code |
| S11-D11 index-identity map, no DSP | 3, 4 | slot `i` → pad `i`; no stretch |
| S11-D12 empty slot is not wipe | 3, 4 | empty Set slot leaves occupied pad |
| #465 Q1 eligibility | 1, 2 | `soundset_license_ineligible` vs Schema |
| #465 Q2 keep/replace | 3, 4 | three write-sets |
| #465 Q3 no stretch | 3–5 | no DSP on install/apply |

## Task 1: Contract and package validation

**Issue:** [#668](https://github.com/endaye/lmdj/issues/668)

**Serial after:** this plan.

**Files:**

- Create: `contracts/soundset/lmdj.soundset.v1.schema.json`
- Create: `contracts/soundset-catalog/lmdj.soundset-catalog.v1.schema.json`
- Create: `tests/fixtures/contracts/soundset-v1-valid.json`
- Create: `tests/fixtures/contracts/soundset-v1-invalid-license-schema.json`
- Create: `tests/fixtures/contracts/soundset-catalog-v1-valid.json`
- Modify: `tests/conformance/schema_contract_test.py`
- Create: `packages/foundation/include/lmdj/foundation/soundset_manifest.hpp`
- Create: `packages/foundation/src/soundset_manifest.cpp`
- Modify: `packages/foundation/CMakeLists.txt`
- Test: `tests/core/foundation/soundset_manifest_test.cpp`

- [ ] RED: Schema fixtures — valid 16-slot manifest; missing `license` key;
      empty `rights_holder`; unknown `role`. Run
      `python3 tests/conformance/schema_contract_test.py`; expect failure
      naming the new contracts.
- [ ] Author both Schemas. `license.spdx_id` is a non-empty string, **not** an
      enum of the allowlist. Role **is** the closed enum. Catalog
      `license_summary` requires `spdx_id` and `rights_holder`.
- [ ] RED: `soundset_manifest_test.cpp` — canonical byte equality; BOM/trailing
      newline/key reorder/duplicate key/non-canonical number rejected;
      allowlisted SPDX with empty BY attribution → eligibility
      `soundset_license_ineligible`; unknown SPDX → same; missing license key
      → `soundset_manifest_invalid`. Expect failure before implementation.
- [ ] Implement bounded parse → Schema → `canonical_json` byte equality →
      eligibility. Eligibility is not Schema.
- [ ] GREEN: `scripts/core.sh test dev fast` and
      `python3 tests/conformance/schema_contract_test.py`.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(contracts): add Sound Set and Catalog v1 schemas`.

**Version Management:** allocate `lmdj.soundset.v1` / `1.0.0` and
`lmdj.soundset-catalog.v1` / `1.0.0`. `foundation` stays at the protected-main
patch unless the new headers force a MINOR; if so, bump at Task 6 with the
cascade, not in this Task's manifests. This Task does not edit Product
Assembly or Host manifests.

**Documentation impact:** none in this Task. Current Portal truth still has no
Sound Set Contract identity until Task 6.

## Task 2: Catalog transport, cache, and Set Store

**Issue:** [#669](https://github.com/endaye/lmdj/issues/669)

**Serial after:** Task 1.

**Files:**

- Create: `packages/project-io/include/lmdj/project_io/soundset_store.hpp`
- Create: `packages/project-io/src/soundset_store.cpp`
- Modify: `packages/project-io/CMakeLists.txt`
- Test: `tests/core/project_io/soundset_store_test.cpp`
- Test: `tests/core/project_io/soundset_local_adapter_test.cpp`

- [ ] RED: local adapter rejects `/`, `..`, non-lowercase sha256 basename,
      symlink, and non-regular file; opened bytes must match the requested
      hash. Expect failure.
- [ ] RED: unique blob hash is downloaded once; declared `total_bytes` must
      equal canonical manifest bytes plus unique blob lengths; any mismatch
      leaves staging invisible. Tampered blob → `soundset_content_mismatch`.
- [ ] RED: four Host limits, each exact allowed and +1 fail-closed, using
      fixture-sized limits injected like other resource_limits tests.
- [ ] Implement root-relative open with no symlink follow, atomic publish into
      a Workspace read-only Set Store, and a network adapter that only fetches
      `{object_kind, sha256}` (no archive unpack). Catalog unreachable is
      `catalog_unavailable` and is non-fatal for already-published Sets.
- [ ] GREEN: `scripts/core.sh test dev fast`.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(project-io): add Sound Set catalog adapters and Set Store`.

**Version Management:** none in this Task's manifests. `project-io` SemVer is
paid at Task 6.

**Documentation impact:** none in this Task.

## Task 3: Project adoption

**Issue:** [#670](https://github.com/endaye/lmdj/issues/670)

**Serial after:** Task 2, #436, #471 lineage vocabulary freeze.

**Files:**

- Modify: `packages/authoring-domain/include/lmdj/domain/commands.hpp`
- Modify: `packages/authoring-domain/src/command_handler.cpp`
- Test: `tests/core/domain/soundset_install_test.cpp`
- Test: `tests/core/domain/soundset_map_test.cpp`

- [ ] RED: mapping function is slot-index identity; duplicate roles do not
      permute; empty Set slots are `kept`.
- [ ] RED: three write-sets on an occupied target Bank — omitted policy →
      `soundset_occupied_conflict` and unchanged revision; `keep` writes only
      non-colliding `proposed` pads; `replace` writes every `proposed` pad;
      empty Set slots never clear occupied pads.
- [ ] RED: Bank and generation quota rehearsals count decoded float PCM per
      Pad (duplicate Artifact on two Pads counts twice); either quota fails
      with zero change.
- [ ] Implement `InstallSoundSet` as one revision through the existing import
      commit path. Each new Asset Lineage is
      `source = {kind: soundset, set_id, set_version, manifest_sha256, slot_index, artifact_sha256}`,
      `derivation.kind = soundset_install`. Editing a Pad afterwards is
      ordinary §5.2 derivation; Set Store bytes stay unchanged.
- [ ] GREEN: `scripts/core.sh test dev fast`.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(domain): install Sound Set slots as ordinary Assets`.

**Version Management:** none in this Task's manifests. `authoring-domain`
SemVer is paid at Task 6. Do not add a Project Contract version unless #471
has already allocated one for the Lineage union; never add a second Lineage
field.

**Documentation impact:** none in this Task.

## Task 4: Facade

**Issue:** [#671](https://github.com/endaye/lmdj/issues/671)

**Serial after:** Task 3.

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Test: `tests/core/facade/soundset_facade_test.cpp`
- Host wiring (CLI/MCP/Native/Web operation tables) only as required for the
  locked operation names to round-trip; no Creator UI.

- [ ] RED: locked operations reject extra fields; `map.preview` is zero
      revision; `install` without policy on collisions returns
      `soundset_occupied_conflict`; catalog list of a cached Set succeeds when
      the network adapter is down.
- [ ] Implement the four operations. Preview of set/slot audio uses the
      ordinary Runtime preview path and does not create Assets.
- [ ] GREEN: `scripts/core.sh test dev fast`.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(facade): add Sound Set catalog, preview, and install operations`.

**Version Management:** none in this Task's manifests. `application-facade`
MAJOR is paid at Task 6.

**Documentation impact:** none in this Task.

## Task 5: Creator catalog and install surface

**Issue:** [#672](https://github.com/endaye/lmdj/issues/672)

**Serial after:** Task 4.

**Files:**

- Modify: `apps/creator-web/` catalog/install surfaces (exact files chosen at
  execution from the current Creator Mode Rail; do not invent a second Pad
  matrix).
- Test: Creator unit/component tests for list, inspect, collision confirm
  (`keep`/`replace`), and install receipt.

- [ ] RED: listing a cached Set with Catalog unreachable still offers inspect
      and install; collision UI cannot submit without `keep` or `replace`;
      empty Set slots are not presented as a clear-pad action.
- [ ] Implement Catalog browse, set/slot preview, target-Bank picker, and
      install confirmation. No Marketplace chrome.
- [ ] GREEN: Creator unit tests; Browser journey if the existing Creator proof
      harness can host a local Catalog fixture, otherwise record the gap for
      Task 7.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(creator): add Sound Set catalog and install surface`.

**Version Management:** none in this Task's manifests. `creator-web` SemVer is
paid at Task 6.

**Documentation impact:** none in this Task.

## Task 6: Versions, Assembly, and current Portal

**Issue:** [#673](https://github.com/endaye/lmdj/issues/673)

**Serial after:** Tasks 1–5 and #436 (so Stage 10's `1.0.42.0` identity is
consumed and current).

**Files:** active module/Host/Contract/Assembly manifests, `products/lmdj/`,
current Architecture Portal pages and source diagrams named below.

- [ ] Fresh exact-identity audit of protected `origin/main` (version.json,
      Assembly lock, snapshots, tags, Releases, open Issues/PRs,
      `release-intents.json`). Allocate the next unoccupied Product Build.
      If that target has been consumed, stop and refresh this table.
- [ ] Write Contract identities `lmdj.soundset.v1` / `1.0.0` and
      `lmdj.soundset-catalog.v1` / `1.0.0` into Assembly. Pay SemVer for
      modules/Hosts whose public surface actually changed in Tasks 1–5.
      Write the four Sound Set resource_limits into Host manifests.
- [ ] Update current Portal pages listed under Documentation Impact.
- [ ] Automated acceptance: schema conformance, core fast/full, Facade
      install write-sets, local Catalog adapter, Creator unit tests.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(product): integrate Stage 11 Sound Set versions and current truth`.

**Version Management:** required. Repeat the audit at execution; do not
substitute a guessed Product Build. Baseline at plan authoring is Product
`1.0.41.0` with Stage 10 Task 10 still targeting `1.0.42.0`.

**Documentation impact:** required at this Task:

- `/contracts/overview/`
- `/core/modules/application-facade/`
- `/core/modules/project-io/`
- `/core/modules/authoring-domain/`
- `/hosts/creator-web/`
- `/assembly/lmdj/`
- `/product/workflows/`
- `/product/capability-map/`

Add Contract pages only if Task 6's Portal generator requires one page per
active Contract; do not hand-enter identities.

Immutable snapshot is a follow-up of this Task on a clean commit, not Channel
promotion.

## Task 7: Acceptance

**Issue:** [#674](https://github.com/endaye/lmdj/issues/674)

**Serial after:** Task 6.

- [ ] Cross-Host black-box: list → inspect → map.preview → install keep →
      install replace, each with far-side revision/Lineage/Set Store
      assertions.
- [ ] Catalog unreachable: cached Set still inspectable and installable.
- [ ] Physical/manual Safari/iPadOS catalog browse is listed as remaining
      human verification if no Browser fixture covers it; do not claim it
      passed.
- [ ] Commit only acceptance evidence documents if they are retained; otherwise
      attach evidence on the Issue and keep this Task's repository delta to
      the automated Host journeys.

**Version Management:** none.

**Documentation impact:** none unless an acceptance page under
`apps/architecture-portal/docs/` is actually edited.

## Version Management

Version impact of **this plan document**: none. It allocates no Product,
Module, Host, Provider, Contract, Assembly, Channel, or snapshot identity.

| Component | When allocated | Rule |
| --- | --- | --- |
| `lmdj.soundset.v1` | Task 1 schema, Task 6 Assembly | initial `1.0.0` |
| `lmdj.soundset-catalog.v1` | Task 1 schema, Task 6 Assembly | initial `1.0.0` |
| `foundation` / `project-io` / `authoring-domain` / `application-facade` / Hosts | Task 6 | pay SemVer only for surfaces Tasks 1–5 actually changed |
| Product Build | Task 6 | next unoccupied after #436; audit immediately before mutation |
| `lmdj.project` | only if #471 allocated a Lineage union revision | never a second Lineage field |

## Documentation Impact

Documentation impact of **this plan document**: none. It edits
`docs/superpowers/` only.

Implementation-backed Portal updates are Task 6's obligation (routes listed
there). Tasks 1–5, 7 declare `none` unless they actually edit
`apps/architecture-portal/docs/`.

## Issue Map

The Stage 11 umbrella is #470. #464 is this plan. #465 is the rights/mapping
decision.

| Plan Task | GitHub Issue | Priority | Primary area | Hard dependencies |
| --- | --- | --- | --- | --- |
| Plan | #464 | P2 | Docs/Governance | #465 |
| 1 Contract/package validation | #668 | P2 | Contracts | #464 |
| 2 Catalog transport/cache | #669 | P2 | Core | Task 1 |
| 3 Project adoption | #670 | P2 | Core | Task 2, #436, #471 vocabulary |
| 4 Facade | #671 | P2 | Core | Task 3 |
| 5 Creator | #672 | P2 | Creator | Task 4 |
| 6 Assembly / Portal | #673 | P2 | Product | Tasks 1–5, #436 |
| 7 Acceptance | #674 | P2 | Product | Task 6 |

## Final Acceptance Boundary

Stage 11 is **implementation-complete** only when Tasks 1–7 are merged, a
local Catalog Set can be inspected and installed into a user-chosen Bank as
ordinary Assets with typed Lineage, collisions require `keep` or `replace`,
empty Set slots do not wipe occupied pads, Catalog unreachable does not hide
cached Sets, and the Product Build from Task 6 has current Portal truth plus
an immutable snapshot.

Stage 11 is **not** Marketplace-complete. Umbrella #470 stays open until
Tasks 1–7 plus that snapshot exist. This plan does not close #470.
