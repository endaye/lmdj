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
[`2026-08-31-lmdj-stage11-sound-set-design.md`](../design/2026-08-31-lmdj-stage11-sound-set-design.md)
(S11-D1–D12) plus
[`2026-09-06-sound-set-rights-and-mapping.md`](../prd/decisions/2026-09-06-sound-set-rights-and-mapping.md)
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
- Stage 10 Task 10 ([#436](https://github.com/endaye/lmdj/issues/436)) is
  merged and Product Build `1.0.42.0` is consumed, so no Task waits on Stage
  10. Task 1 may start after this plan merges. Task 2 starts after Task 1.
  Tasks 3, 4, 5 are serial on each other.
- Hosts use only Application Facade. Catalog endpoints never enter Project
  Truth. Facade requests never carry a Workspace path: the Set Store and the
  Catalog cache live under the configured `ApplicationConfig.workspace_root`,
  exactly like the Provider selection store behind `provider.list` /
  `provider.select`.
- `lmdj.project.v4` stays the writer Contract ID. Install creates ordinary
  Assets and Pad assignments; Lineage uses the existing `Asset.lineage`
  carrier. That carrier is a closed typed variant today (`source.kind` is the
  constant `asset_artifact`, `derivation.kind` is the constant `resample`; the
  Schema and `packages/authoring-domain/src/project.cpp` reject anything
  else), so Task 3 pays one Project Contract MINOR (`4.0.0` → `4.1.0`) that
  adds exactly the S11-D9 `soundset` source variant and the
  `soundset_install` derivation kind. Never add a second Lineage field.
  [#471](https://github.com/endaye/lmdj/issues/471) is a draft Stage 12
  design whose S12L-D6 already lists the same two tokens; if #471 later
  approves different tokens, that is a design conflict that returns to
  review, never a reason for Task 3 to invent a third vocabulary.
- Core gains no network dependency. `scripts/verify-core-dependencies.sh`
  stays unchanged. Task 2 defines an injected `CatalogTransport` interface
  and ships only the local directory adapter plus a test fake; network
  transports are Host-side implementations of that interface (Web Host in
  Task 5). No HTTP client enters `packages/`.
- S8-D6 audio validation (`soundset_audio_unsupported`) is raised by the
  Facade in Task 4 through the existing project-cooker WAV reader, on
  inspect, preview, and install. Task 1 (foundation) and Task 2 (project-io)
  validate manifests, hashes, and byte lengths only; neither module gains a
  project-cooker dependency.
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
| Bank/generation quota | `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED` (existing) | existing quota details; no Sound Set reason token |

Slot **layout** faults (slot count ≠ 16, duplicate or missing slot index,
unknown role) are `soundset_slot_invalid`. Every other manifest shape fault
(License block, artifact ref with malformed `sha256` / `media_type` /
`byte_length`, unknown top-level key) is `soundset_manifest_invalid`.

## Locked Facade Surface

Every JSON request includes `operation` plus the exact fields below. Extra
fields are invalid. `uuid` is a lowercase canonical UUID.

| Operation | Kind | Exact fields after `operation` |
| --- | --- | --- |
| `soundset.catalog.list` | query | (none) |
| `soundset.inspect` | query | `set_id, version, manifest_sha256` |
| `soundset.audition` | query | `set_id, version, manifest_sha256, slot_index?` |
| `soundset.map.preview` | query | `project_path, bank_id, set_id, version, manifest_sha256` |
| `soundset.install` | command | `project_path, command_id, expected_revision, bank_id, set_id, version, manifest_sha256, occupied_pad_policy?` |

Workspace-level operations resolve the Set Store and Catalog cache from
`ApplicationConfig.workspace_root`, following the `provider.list` /
`provider.select` precedent; a request carrying `workspace_path` fails the
`exact_keys` check like any other extra field. `soundset.catalog.list` is a
query with respect to Project Truth: it may refresh the Host-side Catalog
cache, and that side effect never touches a Project, Asset, Pad, or revision.

`soundset.audition` is S11-D5's audition surface, added at
[#773](https://github.com/endaye/lmdj/issues/773) because the four-operation
table above could not carry it: a Set in the Workspace Set Store is not a
Project Pad, so the Pad-addressed `sample.preview.set` cannot reach it, and
moving playback Host-side would make a Host read Set Store bytes instead of
using the Application Facade. It is Set-scoped: omitting `slot_index`
resolves the set-level `demo` of S11-D5, supplying one resolves that slot's
Artifact, through the same project-cooker preparation the ordinary Runtime
preview path uses. Like `soundset.inspect` it is a query with respect to
Project Truth — no Asset, no Pad, no revision — and it resolves the Set Store
from the Workspace. It refuses what the other Set-reading operations refuse,
in the same order: identity, `soundset_license_ineligible`,
`soundset_content_mismatch`, then S11-D3's whole-Set
`soundset_audio_unsupported`. An audition with no source — a `slot_index`
naming an empty slot, keyed off the absence of an `artifact` and never off a
flag, or a `demo` request on a Set that declares none — is the existing
`MISSING_ASSET` carrying no `details.reason`: the Locked Error Reasons table
above does not grow for this operation.

**S11-D5 is not yet closed by this operation.** `soundset.audition` resolves
and gates the audition source and reports the geometry of the exact bytes the
Runtime would play; it does not itself make sound. Nothing carries those
prepared bytes into a Host's audio engine today: the Facade owns no engine and
emits no binary channel, and the engine's preview control is a Pad-slot
override on the bank cooked from a Project, which holds no Set. Delivering the
bytes needs either an audition sink on the Facade or an audition bank in the
Runtime. A Host can browse, inspect, gate and describe an audition but cannot
hear one, and S11-D5 stays open.

**The product question that blocked the second option is now settled.** This
plan previously recorded it as unsettled — whether auditioning a Set displaces
the open Project's bank. Decided by the product owner on 2026-09-08: **a bank
slot is reserved for auditions**, so a Set preview never touches the bank the
open Project plays from. Recorded on #799 and #470 with the two rejected
options: displacing the Project's bank was refused because the restore path
must survive a mid-audition failure, and cooking the Set into the Project's
bank at a scratch pad slot was refused because it mutates a bank derived from
Project Truth for something explicitly outside the Project, contradicting this
Stage's own rule that audition creates no Asset, touches no Pad and leaves the
revision unchanged.

One correction belongs with the decision, because #799 described the engine
inaccurately and the difference changes what the chosen option costs. The
engine has **four** bank slots, not one: `kRealtimeBankCapacity = 4`
(`packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp:31`),
`current_bank_slot_` names the live one, and `publish_sample_bank`
(`packages/audio-runtime/src/realtime_engine.cpp:571-579`) allocates whichever
slot is `BankState::empty`, returning `PublishResult::bank_slots_full` only
when none is. "One current bank and 64 pad slots with no spare" is true of
**pad** slots.

**The reserved slot is a dedicated member, not one of the four.** The decision
was first priced as "hot-swap headroom four down to three", and that number was
wrong: the audition slot lives beside `bank_slots_` as its own
`std::optional<PreparedSampleBank>` plus a sentinel index, so
`kRealtimeBankCapacity` stays 4 and **every existing publication path keeps its
exact arithmetic**. Carving one of the four was rejected for a reason the
original pricing missed — it forces rewriting
`tests/core/audio/realtime_engine_test.cpp:1169-1190`, which publishes four
banks, asserts the fifth is `bank_slots_full`, and asserts
`reclaim_retired_banks() == 3`. Those constants measure real realtime headroom,
so editing them to go green is a threshold edit of the kind the Minimization
Principle forbids. It would also leave
`snapshot_publication_stress_test.cpp:244-262` numerically true at 4 == 4 while
the prose argument behind its `static_assert` quietly stopped holding.

**Holding a slot is not by itself audible, and that cost is real.**
`current_sample` (`packages/audio-runtime/src/realtime_engine.cpp:297`) reads
`bank_slots_[current_bank_slot_]` unconditionally, so every byte a voice plays
comes from the *current* bank. Making the reserved slot current would be the
rejected displacement option under another name, so the engine instead gains a
voice-start path that reads the reserved slot explicitly. `Voice` already
carries `bank_slot` and `release_voice_bank` already refcounts the drain, with
`pattern_slot` as precedent for a voice sourcing off a non-current slot;
`apply_published_bank` must not be reused, because it retires the current bank,
writes `current_bank_slot_` and overwrites `availability_mask_`. The decision
therefore costs an engine change rather than a held slot — which does not
revive either rejected option, since both were rejected on correctness rather
than on cost.

The decision is recorded here; the mechanism is not built. #799 carries the
byte path, and until it lands S11-D5 stays open on delivery alone rather than
on an unanswered product question.

`soundset.map.preview` is the pure function
`map(manifest, bank occupancy) → {proposed, collisions, kept}` and mutates
nothing. `occupied_pad_policy` is required on `soundset.install` when
`collisions` is non-empty; omitted + collisions → `soundset_occupied_conflict`
and zero Project change.

## Dependency Order

```text
This plan #464
  └─ Task 1 Contract/package validation
       └─ Task 2 CatalogTransport interface / local adapter / Set Store
            └─ Task 3 Project adoption (+ lmdj.project.v4 Contract MINOR 4.1.0)
                 └─ Task 4 Facade (+ quota rehearsal, S8-D6 audio, Host op tables)
                      └─ Task 5 Creator (+ Web Host fetch transport)
                           └─ Task 6 Assembly / current Portal
                                └─ Task 7 acceptance
```

[#436](https://github.com/endaye/lmdj/issues/436) is CLOSED and `1.0.42.0` is
the current Product Build; it gates nothing here. #471 is an open Stage 12
design Task and is **not** a hard dependency: Task 3 consumes the `soundset`
source and `soundset_install` derivation tokens from the approved Stage 11
design (S11-D9), and #471's S12L-D6 must stay consistent with them. Task 3
must not invent a second Lineage model.

## Design Traceability

| Decision | Primary Tasks | Acceptance witness |
| --- | --- | --- |
| S11-D1 canonical identity | 1 | canonical-bytes golden vectors; non-canonical JSON rejected |
| S11-D2 schema + license keys | 1 | four keys required; allowlist not a Schema enum |
| S11-D3 S8-D6 audio | 4 | `soundset_audio_unsupported` on inspect/preview/install via project-cooker |
| S11-D4 role enum | 1 | unknown role → `soundset_slot_invalid` |
| S11-D5 audition, no Project change | 4, 5 | inspect/preview leave revision unchanged; `soundset.audition` resolves the set-level `demo` and a slot's Artifact and leaves the revision unchanged. Playback delivery is outstanding — see the Locked Facade Surface note |
| S11-D6 catalog adapters, no archive | 2 | `CatalogTransport` interface; local adapter rejects symlink/`..`/non-regular file |
| S11-D7 download, unique bytes, Host limits | 2 | exact/+1 of four limits; hash mismatch invisible |
| S11-D8 InstallSoundSet, quota, policy | 3, 4 | three write-sets (Task 3); per-Pad decoded-PCM quota zero-change (Task 4) |
| S11-D9 soundset Lineage | 3 | typed source fields all present; Project Contract `4.1.0` fixture + conformance |
| S11-D10 error tokens | 1–4 | no new public error code |
| S11-D11 index-identity map, no DSP | 3, 4 | slot `i` → pad `i`; no stretch |
| S11-D12 empty slot is not wipe | 3, 4 | empty Set slot leaves occupied pad |
| #465 Q1 eligibility | 1, 2, 4 | `soundset_license_ineligible` vs Schema; catalog `license_summary` equality at inspect |
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
      empty `rights_holder`; unknown `role`; 15 and 17 slots; duplicate slot
      index; artifact ref with uppercase `sha256`. Run
      `python3 tests/conformance/schema_contract_test.py`; expect failure
      naming the new contracts.
- [ ] Author both Schemas. `license.spdx_id` is a non-empty string, **not** an
      enum of the allowlist. Role **is** the closed enum. `slots` uses the
      same `allOf` / `contains` / `minContains` / `maxContains` pattern as the
      Project Schema's 16 pads so each index 0–15 appears exactly once (the
      conformance test's `contained_constants` helper already checks that
      shape). Catalog `license_summary` requires `spdx_id` and
      `rights_holder`.
- [ ] RED: `soundset_manifest_test.cpp` — canonical byte equality; BOM/trailing
      newline/key reorder/duplicate key/non-canonical number rejected; slot
      layout faults → `soundset_slot_invalid`; artifact ref / unknown key
      faults → `soundset_manifest_invalid`; allowlisted SPDX with empty BY
      attribution → eligibility `soundset_license_ineligible`; unknown SPDX →
      same; missing license key → `soundset_manifest_invalid`. Expect failure
      before implementation.
- [ ] Implement bounded parse → structural validation → `canonical_json` byte
      equality → eligibility. "Schema" in C++ means hand-written exact-keys
      validation mirroring the JSON Schema, the way
      `packages/authoring-domain/src/project.cpp` does with
      `exact_object_keys`; the repository has no C++ JSON Schema validator and
      this Task must not add one. Eligibility is a pure function over the
      parsed manifest plus an optional catalog `license_summary`; it is not
      Schema. The parser lives in `foundation` because it needs only
      `canonical_json`, `valid_utf8`, `parse_bounded_json`, and the
      foundation-private SHA-256, and must know nothing about Projects,
      Workspaces, or Hosts; it decodes no audio.
- [ ] GREEN: `scripts/core.sh test dev fast` and
      `python3 tests/conformance/schema_contract_test.py`.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(contracts): add Sound Set and Catalog v1 schemas`.

**Version Management:** allocate `lmdj.soundset.v1` / `1.0.0` and
`lmdj.soundset-catalog.v1` / `1.0.0`. (`lmdj.soundset.v1` later moved to
`1.1.0` at #751, which is the version that entered Assembly at Task 6.) `foundation` stays at the protected-main
patch unless the new headers force a MINOR; if so, bump at Task 6 with the
cascade, not in this Task's manifests. This Task does not edit Product
Assembly or Host manifests.

**Documentation impact:** none in this Task. Current Portal truth still has no
Sound Set Contract identity until Task 6.

## Task 2: Catalog transport, cache, and Set Store

**Issue:** [#669](https://github.com/endaye/lmdj/issues/669)

**Serial after:** Task 1.

**Files:**

- Create: `packages/project-io/include/lmdj/project_io/soundset_catalog_transport.hpp`
  (the injected `CatalogTransport` interface: two reads, canonical manifest
  object and content-addressed blob, both addressed by `{object_kind, sha256}`)
- Create: `packages/project-io/include/lmdj/project_io/soundset_store.hpp`
- Create: `packages/project-io/src/soundset_store.cpp` (Set Store, staging,
  limits, and the local directory adapter)
- Modify: `packages/project-io/CMakeLists.txt`
- Test: `tests/core/project_io/soundset_store_test.cpp` (uses an in-memory
  fake `CatalogTransport` defined in the test)
- Test: `tests/core/project_io/soundset_local_adapter_test.cpp` (native label:
  symlink and non-regular-file cases need a POSIX filesystem; the Web OPFS
  platform has neither)

- [ ] RED: local adapter rejects `/`, `..`, non-lowercase sha256 basename,
      symlink, and non-regular file; opened bytes must match the requested
      hash. Expect failure.
- [ ] RED: unique blob hash is fetched once; declared `total_bytes` must
      equal canonical manifest bytes plus unique blob lengths; any mismatch
      leaves staging invisible. Tampered blob → `soundset_content_mismatch`.
      A transport failure maps to `catalog_unavailable` and leaves every
      already-published Set readable.
- [ ] RED: four Host limits, each exact allowed and +1 fail-closed, using
      fixture-sized limits injected like other resource_limits tests.
- [ ] Implement the `CatalogTransport` interface, the local directory adapter
      (root-relative open with no symlink follow, `fstat` regular-file check,
      bounded read, hash check), and atomic publish into a Workspace read-only
      Set Store. Every adapter, local or Host-side network, resolves only
      `{object_kind, sha256}`; there is no archive unpack. This Task ships **no** network code: the network
      adapter is a Host-side `CatalogTransport` (Web Host in Task 5) and Core
      keeps its offline vendored dependency set.
- [ ] Do not validate audio format here. Set Store bytes are content-addressed
      blobs; S8-D6 validation is the Facade's job in Task 4.
- [ ] GREEN: `scripts/core.sh test dev fast` and
      `bash scripts/verify-core-dependencies.sh` (unchanged dependency set).
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(project-io): add Sound Set catalog transport and Set Store`.

**Version Management:** none in this Task's manifests. `project-io` SemVer is
paid at Task 6.

**Documentation impact:** none in this Task.

## Task 3: Project adoption

**Issue:** [#670](https://github.com/endaye/lmdj/issues/670)

**Serial after:** Task 2. (#436 is closed; #471 is not a dependency, see
Dependency Order.)

**Files:**

- Modify: `contracts/project/lmdj.project.v4.schema.json` (Contract MINOR
  `4.0.0` → `4.1.0`: `asset_lineage.source` becomes a `oneOf` of the existing
  `asset_artifact` variant and the new `soundset` variant;
  `asset_lineage.derivation` becomes a `oneOf` of the existing `resample`
  variant and the new `soundset_install` variant; every variant keeps
  `additionalProperties: false` and a constant `kind`)
- Create: `tests/fixtures/contracts/project-v4-soundset-lineage-valid.json`
- Create: `tests/fixtures/contracts/project-v4-soundset-lineage-invalid.json`
  (missing `manifest_sha256`)
- Modify: `tests/conformance/schema_contract_test.py` (`project_v4` version
  `4.1.0`; both lineage variants asserted)
- Modify: `packages/authoring-domain/include/lmdj/domain/project.hpp`
  (`AssetLineage` source/derivation become typed variants)
- Modify: `packages/authoring-domain/src/project.cpp` (parse and emit both
  variants with exact keys; anything else still fails closed)
- Modify: `packages/authoring-domain/include/lmdj/domain/commands.hpp`
  (`MapSoundSet` pure function, `InstallSoundSet` command)
- Modify: `packages/authoring-domain/src/command_handler.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
  and `packages/project-io/src/project_store.cpp` (a multi-Asset,
  multi-Pad commit request beside `ImportAssignSampleBytesRequest`; one
  revision, one receipt)
- Test: `tests/core/domain/soundset_map_test.cpp`
- Test: `tests/core/domain/soundset_install_test.cpp`
- Test: `tests/core/domain/project_test.cpp` (lineage round-trip for both
  variants; existing `asset_artifact` / `resample` fixtures unchanged)
- Test: `tests/core/project_io/soundset_install_commit_test.cpp`

- [ ] RED: Schema fixtures — `soundset` lineage valid; missing typed field
      invalid; existing v4 fixtures still valid. Run
      `python3 tests/conformance/schema_contract_test.py`; expect failure.
- [ ] RED: mapping function is slot-index identity; duplicate roles do not
      permute; empty Set slots are `kept`; same input gives same output.
- [ ] RED: three write-sets on an occupied target Bank — omitted policy →
      `soundset_occupied_conflict` with the full `collisions` list in details
      and unchanged revision; `keep` writes only non-colliding `proposed`
      pads; `replace` writes every `proposed` pad; empty Set slots never
      clear occupied pads. Replaced Assets are not deleted (S8-D5).
- [ ] RED: the store commit is atomic — N Assets plus N Pad assignments land
      as exactly one revision with one receipt; a failure after staging
      leaves Project, Assets, Pads, and revision unchanged; a replayed
      `command_id` returns the stored receipt.
- [ ] Implement `InstallSoundSet` as one revision through the same
      writer-lease and receipt path the sample import commit uses. Each new
      Asset Lineage is
      `source = {kind: soundset, set_id, set_version, manifest_sha256, slot_index, artifact_sha256}`,
      `derivation = {kind: soundset_install}`. Editing a Pad afterwards is
      ordinary §5.2 derivation; Set Store bytes stay unchanged.
- [ ] Quota rehearsal is **not** in this Task: decoded-PCM accounting and
      `assess_runtime_quota` live in the Facade, so Task 4 owns that RED.
      This Task's command takes already-validated Assets and never decodes
      audio.
- [ ] GREEN: `scripts/core.sh test dev fast` and
      `python3 tests/conformance/schema_contract_test.py`.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(domain): install Sound Set slots as ordinary Assets with soundset Lineage`.

**Version Management:** `lmdj.project.v4` Contract version `4.0.0` → `4.1.0`
in the Schema `x-lmdj-contract-version` and the conformance test. The Contract
ID does not change; a `4.0.0` reader rejects a `soundset` lineage by design,
which is the backward-compatible-addition rule of
`docs/governance/version-management.md` §7. **Corrected at execution:** this
Task cannot defer the Assembly lock to Task 6. The lock pins each Contract's
schema sha256, so editing the Schema forces `products/lmdj/assembly.lock.json`
in the same commit, the lock forces a Product Build, and the Build forces
`Documentation impact: required`. Task 3 therefore cut the Contract, the
Assembly, the lock and Product Build `1.0.43.0` together (`ee5a9a18`, #761).
`authoring-domain` and `project-io` SemVer are still paid at Task 6. Never add
a second Lineage field or a Project Contract with a new ID.

**Documentation impact:** **required.** The line above originally read `none`;
execution disproved it. A Contract Schema edit forces the Assembly lock, which
forces a Product Build allocation, and
`docs/governance/architecture-portal.md` forbids a Product Build or Assembly
change from declaring `none`.

## Task 4: Facade

**Issue:** [#671](https://github.com/endaye/lmdj/issues/671)

**Serial after:** Task 3.

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
  (`ApplicationConfig` gains an optional `std::shared_ptr<project_io::CatalogTransport>`
  and the four Sound Set limits beside `runtime_preparation_limits`)
- Modify: `packages/application-facade/src/application.cpp`
- Test: `tests/core/facade/soundset_facade_test.cpp`
- Test: `tests/core/facade/soundset_install_quota_test.cpp`
- Host operation tables, only as required for the locked names to round-trip
  and for the `OperationKind` table to classify them: `apps/core-cli/`,
  `apps/core-mcp/`, `apps/native-host/src/main.cpp`,
  `packages/web-runtime-platform/src/control_runtime.cpp` and
  `packages/web-runtime-platform/src/bridge.cpp` (operation deadline and
  payload validation tables). No Creator UI, and no Web fetch transport yet;
  Task 4 wires the Web Host with the local adapter only.

- [ ] RED: locked operations reject extra fields, including a stray
      `workspace_path`; `map.preview` is zero revision; `install` without
      policy on collisions returns `soundset_occupied_conflict`; catalog list
      of a cached Set succeeds when the injected `CatalogTransport` fails
      with `catalog_unavailable`; a catalog `license_summary` that differs
      from the published manifest → `soundset_license_ineligible` at inspect.
- [ ] RED: S8-D6 — a published Set whose blob is not PCM16 44.1/48 kHz
      mono/stereo WAV → `UNSUPPORTED_AUDIO` + `soundset_audio_unsupported`
      on inspect, slot preview, and install, with zero Project change.
- [ ] RED: Bank and generation quota rehearsals count decoded float PCM per
      Pad (duplicate Artifact on two Pads counts twice) through the existing
      `assess_runtime_quota` binding-constraint rule; either quota fails with
      `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED` and zero change;
      `occupied_pad_policy` never bypasses quota.
- [ ] Implement the four Task 4 operations. Install decodes each occupied slot
      once through the project-cooker WAV reader, rehearses quota, then calls
      Task 3's store commit. Audition of set/slot audio is `soundset.audition`,
      the fifth operation, added at #773 — it creates no Assets. Its Facade,
      MCP and Native Host registrations landed with it; the Web Host's
      `bridge.cpp` / `protocol.mjs` pair and the Creator control follow Task 5,
      so a browser request for it is refused at the bridge until then.
- [ ] GREEN: `scripts/core.sh test dev fast`.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(facade): add Sound Set catalog, preview, and install operations`.

**Version Management:** none in this Task's manifests. `application-facade`
SemVer is paid at Task 6. **Corrected at execution:** this line predicted a
MAJOR, and Task 6 paid a MINOR, `3.0.0` → `3.1.0`. The prediction was written
before this Task existed and guessed at a diff nobody had yet. The diff turned
out to be purely additive — new operations, `SoundSetCatalogSource`,
`make_workspace_soundset_catalog`, and three members **appended** to
`ApplicationConfig` — with no changed signature, no new pure virtual on an
existing class, and `lmdj_engine_create` untouched. Every one of the ~26
positional brace initialisations of `ApplicationConfig` still compiles with the
new members value-initialised, which is what
`docs/governance/version-management.md` §6 calls 向后兼容的新公开能力. A
number that does not mean what the policy says it means mis-describes
compatibility to every consumer, so the policy governs, not the guess.

Contrast `web-runtime-platform`, which Task 6 did pay as a MAJOR for the
opposite reason: its manifest gate now **rejects a distribution manifest it
previously accepted**, which is incompatible in the policy's sense.

**Documentation impact:** none in this Task.

## Task 5: Creator catalog and install surface

**Issue:** [#672](https://github.com/endaye/lmdj/issues/672)

**Serial after:** Task 4.

**Files:**

- Modify: `apps/creator-web/` catalog/install surfaces (exact files chosen at
  execution from the current Creator Mode Rail; do not invent a second Pad
  matrix).
- Modify: `packages/web-runtime-platform/web/` and
  `packages/web-runtime-platform/src/bridge.cpp` as required to supply the Web
  Host's network `CatalogTransport`: browser `fetch` of exactly two object
  kinds addressed by `{object_kind, sha256}` from the Host-configured Catalog
  endpoint, bytes handed to Core through the bridge, Core keeps hash/length
  verification. No archive, no redirect to other object kinds, no endpoint in
  Project Truth.
- Test: Creator unit/component tests for list, inspect, collision confirm
  (`keep`/`replace`), and install receipt; a web-runtime-platform test that
  the fetch transport refuses non-`{object_kind, sha256}` requests.

- [ ] RED: listing a cached Set with Catalog unreachable still offers inspect
      and install; collision UI cannot submit without `keep` or `replace`;
      empty Set slots are not presented as a clear-pad action; the `CC-BY-4.0`
      `attribution` string is shown on listing and inspect.
- [ ] Implement Catalog browse, set/slot preview, target-Bank picker, and
      install confirmation. No Marketplace chrome.
- [ ] GREEN: Creator unit tests; Browser journey if the existing Creator proof
      harness can host a local Catalog fixture server, otherwise record the
      gap for Task 7.

Native Hosts (`core-cli`, `core-mcp`, `native-host`) use the local directory
adapter in v1. A native network `CatalogTransport` is a named follow-up with
its own dependency decision; it is outside Tasks 1–7 and does not block the
Stage 11 acceptance boundary.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(creator): add Sound Set catalog and install surface`.

**Version Management:** none in this Task's manifests. `creator-web` SemVer is
paid at Task 6.

**Documentation impact:** none in this Task.

## Task 6: Versions, Assembly, and current Portal

**Issue:** [#673](https://github.com/endaye/lmdj/issues/673)

**Serial after:** Tasks 1–5. (#436 is closed; `1.0.42.0` is consumed and
current.)

**Files:** active module/Host/Contract/Assembly manifests, `products/lmdj/`,
current Architecture Portal pages and source diagrams named below.

- [ ] Fresh exact-identity audit of protected `origin/main` (version.json,
      Assembly lock, snapshots, tags, Releases, open Issues/PRs,
      `release-intents.json`). Allocate the next unoccupied Product Build.
      If that target has been consumed, stop and refresh this table.
- [ ] Write Contract identities `lmdj.soundset.v1` / **`1.1.0`** (corrected
      at execution: #751 moved it when it added the S11-D5 `demo` carrier) and
      `lmdj.soundset-catalog.v1` / `1.0.0` into Assembly. `lmdj.project.v4` is
      already recorded at `4.1.0` in Assembly and the Assembly lock, cut with
      Product Build `1.0.43.0` at Task 3; do not repeat it. Also move
      `lmdj.project-bundle.v1` `1.1.0` → `1.2.0` so a Bundle can name
      `lmdj.project.v4` (#784). Pay
      SemVer for modules/Hosts whose public surface actually changed in Tasks
      1–5 (`authoring-domain` and `project-io` gained public types,
      `application-facade` gained operations and config, `web-runtime-platform`
      gained the fetch transport). Write the four Sound Set resource_limits
      where each Host's limits actually live today: the Web Host reads them
      from `tools/web-runtime/runtime-identity.json` through the generated
      runtime identity; native Hosts currently pass
      `runtime_preparation_limits` in code, so decide and record their
      injection site in the same commit rather than guessing a manifest.
- [ ] Update current Portal pages listed under Documentation Impact.
- [ ] Automated acceptance: schema conformance, core fast/full, Facade
      install write-sets, local Catalog adapter, Creator unit tests.
- [ ] `scripts/architecture-portal.sh check`.
- [ ] Commit `feat(product): integrate Stage 11 Sound Set versions and current truth`.

**Version Management:** required. Repeat the audit at execution; do not
substitute a guessed Product Build. Baseline at this revision of the plan is
Product `1.0.42.0`, consumed by #436; the next unoccupied Build is decided by
the audit, not by this document.

**Documentation impact:** required at this Task. The eight routes below were
the plan's estimate; execution reached eighteen, because every page that names
a Module, Host or Contract version asserts current truth and this Task moves
ten of them:

- `/contracts/overview/`
- `/contracts/project-bundle/`
- `/contracts/soundset/` (new)
- `/contracts/soundset-catalog/` (new)
- `/core/modules/foundation/`
- `/core/modules/application-facade/`
- `/core/modules/project-io/`
- `/core/modules/authoring-domain/`
- `/core/modules/web-runtime-platform/`
- `/hosts/overview/`
- `/hosts/core-cli/`
- `/hosts/core-mcp/`
- `/hosts/native-host/`
- `/hosts/creator-web/`
- `/hosts/web-runtime/`
- `/platform/web-runtime/`
- `/assembly/lmdj/`
- `/operations/testing-and-proof/`
- `/operations/version-and-release/`
- `/overview/`
- `/product/workflows/`
- `/product/capability-map/`

The Portal generator does require one page per active Contract, so the two
Sound Set Contracts each get one; do not hand-enter identities.

Immutable snapshot is a follow-up of this Task on a clean commit, not Channel
promotion.

## Task 7: Acceptance

**Issue:** [#674](https://github.com/endaye/lmdj/issues/674)

**Serial after:** Task 6.

- [ ] Cross-Host black-box against the local Catalog fixture: list → inspect →
      map.preview → install keep → install replace, each with far-side
      revision/Lineage/Set Store assertions. The Browser journey additionally
      drives the Web fetch transport against a local fixture server.
- [ ] **Acceptance gap recorded by Task 5.** `apps/creator-web/` has no Browser
      proof harness, so Task 5 shipped no Browser journey. Two things are
      therefore unproven end to end in a real browser and belong here: the
      Creator Sound Set surface driven through a live Runtime, and the Web
      Host's fetch `CatalogTransport` against
      `tools/soundset-fixtures/catalog_fixture_server.py`. Task 5 proved each
      half separately — the transport against the real fixture server in
      `packages/web-runtime-platform/test/soundset_catalog.test.mjs`, the
      Core-side acquisition against the real fixture corpus in
      `packages/web-runtime-platform/test/control_runtime_test.cpp`, and the
      surface against a fake session in
      `apps/creator-web/test/soundset_surface.test.tsx` — but never the whole
      chain in one process. A Browser journey sets the Catalog endpoint with
      `window.__LMDJ_SOUNDSET_CATALOG__` or the `lmdj-soundset-catalog` meta
      tag in `apps/creator-web/index.html`. Do not read Task 5's green suites
      as Browser coverage.
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
| `lmdj.soundset.v1` | Task 1 schema, Task 6 Assembly | initial `1.0.0`; **corrected at execution:** it enters Assembly at `1.1.0`, because #751 moved it when it added the S11-D5 `demo` carrier |
| `lmdj.soundset-catalog.v1` | Task 1 schema, Task 6 Assembly | initial `1.0.0` |
| `lmdj.project-bundle.v1` | Task 6 | **added at execution:** Contract MINOR `1.1.0` → `1.2.0` widening `project_contract` to name `lmdj.project.v4`. Since #842 every Project this Build persists is v4, so the narrower enum made every new Project unpackable (#784); a Contract move is what a Build cut carries |
| `lmdj.project.v4` | Task 3 schema, conformance, Assembly **and lock** | Contract MINOR `4.0.0` → `4.1.0` for exactly the S11-D9 `soundset` source and `soundset_install` derivation variants; same Contract ID; never a second Lineage field. **Corrected at execution:** the Assembly and lock could not be deferred to Task 6, because the lock pins each Contract's schema sha256 |
| `foundation` / `project-io` / `authoring-domain` / `application-facade` / `web-runtime-platform` / Hosts | Task 6 | pay SemVer only for surfaces Tasks 1–5 actually changed |
| Product Build | Task 3, then Task 6 | Task 3 consumed `1.0.43.0` with the `lmdj.project.v4` cut; Task 6 allocates the next unoccupied Build. Audit immediately before mutation, never after |

## Documentation Impact

Documentation impact of **this plan document**: none. It edits
`docs/design/` 与 `docs/plans/` only.

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
| 3 Project adoption (+ `lmdj.project.v4` 4.1.0) | #670 | P2 | Core / Contracts | Task 2 |
| 4 Facade (+ quota, S8-D6, Host op tables) | #671 | P2 | Core | Task 3 |
| 5 Creator (+ Web fetch transport) | #672 | P2 | Creator | Task 4 |
| 6 Assembly / Portal | #673 | P2 | Product | Tasks 1–5 |
| 7 Acceptance | #674 | P2 | Product | Task 6 |

## Final Acceptance Boundary

Stage 11 is **implementation-complete** only when Tasks 1–7 are merged, a
local Catalog Set can be inspected and installed into a user-chosen Bank as
ordinary Assets with typed `soundset` Lineage under `lmdj.project.v4` `4.1.0`,
the Web Host can do the same through its fetch transport, collisions require
`keep` or `replace`, empty Set slots do not wipe occupied pads, Catalog
unreachable does not hide cached Sets, Core's vendored dependency set is
unchanged, and the Product Build from Task 6 has current Portal truth plus an
immutable snapshot. A native network transport is not part of this boundary.

Stage 11 is **not** Marketplace-complete. Umbrella #470 stays open until
Tasks 1–7 plus that snapshot exist. This plan does not close #470.
