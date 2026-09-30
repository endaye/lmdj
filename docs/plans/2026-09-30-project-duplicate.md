# Duplicate a Project (#1684)

Decision item 4 of
`docs/prd/decisions/2026-09-29-creator-user-workflow-baseline.md` makes every
Project autosave and turns Save As into Duplicate. No layer has a copy operation
today. #1684 needs one that publishes an independent Project under a new
identity with identical Pads, Patterns and settings. It must refuse a source
that is open in another tab or recording, and must never publish a partial copy.

## Design

- **A byte copy is not enough.** `project_id` is stored in every checkpoint and
  in `AdoptCandidates` transactions, and replay refuses a mismatch. The copy
  therefore starts a **fresh history**: the source's committed head state, with
  the new `id` and `revision = 0`, written by `ProjectStore::create` as
  checkpoint 0. History is not user-visible (there is no undo), so nothing a
  user can observe is lost.
- **What is copied.** Committed Project Truth plus every blob it references:
  `state.assets[*].artifact` and `performances[*].recording_artifact`. Each blob
  is verified by length and SHA-256 before it is staged. Sealed recoveries and
  unreferenced blobs stay with the source. Lineage `project_revision` and
  Performance `recording_revision` are kept verbatim as provenance.
- **Concurrency.**
  - The source writer lease is held for the whole call. Another process or tab
    that holds it is refused with `storage_condition=project_busy`.
  - An active Sequence or Performance Journal is refused with
    `sequence_session_active` or `performance_session_active`. The copy refuses
    rather than quiescing, because a live take is not yet Project Truth.
  - In-process sessions are gated by the Facade (Task 2), because the lease is
    re-entrant within one platform.
- **Publication.**
  - Staging lives under `.lmdj-host/import-staging/duplicate-<id>/`, so the
    existing `cleanup_incomplete` also removes a crashed attempt.
  - The staged copy is fully reloaded, then published with
    `publish_directory_if_absent` under the destination lease.
  - An existing destination returns `DUPLICATE_ID`.
  - The caller's publish token sees exactly one claim/commit (or abort). This is
    what gives the operation cancelled and failed paths.
- **Identity.** The caller supplies the new Project ID, as `project.create`
  does. Naming and display of the copy are left to the Creator Task; the
  `lmdj.project.v5` Project format has no name field.

## Tasks

1. **project-io** (`feat/1684-project-duplicate-core`):
   `ProjectBundleTransfer::duplicate(workspace_root, source_project_id, project_id)`.
   - Declared files:
     - `packages/project-io/include/lmdj/project_io/project_bundle_transfer.hpp`
     - `packages/project-io/src/project_bundle_transfer.cpp`
     - `tests/core/project_io/project_bundle_transfer_test.cpp`
     - `apps/docs-site/docs/core/modules/project-io.mdx`
     - `apps/docs-site/diagrams/project-io.architecture.json`
     - generated `apps/docs-site/static/diagrams/project-io.{svg,html}`
     - `apps/docs-site/docs/platform/storage.mdx`
     - `.agents/pitfalls/revert-proof-rebuild-skipped.md`
     - this plan
   - Lowest-tier test: `project_io.project_bundle_transfer` (component;
     persistence, concurrency). `duplicate` is a `ProjectBundleTransfer`
     method, so its cases join that binary and reuse its `TempDirectory` and
     `FaultPlatform` instead of adding a new target. One fact per test:
     - identity and state;
     - Artifact bytes;
     - fresh history;
     - library listing;
     - independence in both directions;
     - reopen and further commands;
     - refusals: busy source, lease held while Artifacts are read, active
       Sequence journal, active Performance journal, existing destination,
       invalid identities, missing source;
     - failures: corrupt Artifact, publication failure, quota;
     - publish token: exactly one claim and commit, cancellation, forced
       failure;
     - interrupted staging recovery.
2. **application-facade** (`feat/1684-facade-duplicate`): typed
   `duplicate_project(ProjectDuplicateRequest{source_project_id, project_id})`
   returning `LocalProjectSummary`, for the Workspace the Application owns.
   There is no JSON, C API, MCP or CLI operation: the Web Host calls the typed
   project API.
   - It validates both identities, then holds the Project-scoped admission
     lock (`admit_non_sequence_authoring`) through the copy. A live in-process
     Sequence, Pattern transport or Performance session is refused, and no
     in-process authoring commits to the source mid-copy.
   - **It does not reconcile an orphaned Journal.** Normal authoring seals a
     crashed owner's active Journal as `owner_lost` before admission.
     Duplicate passes `reconcile_owner_loss = false`, so Project I/O refuses
     the active Journal and it stays active. The take is recovered by reopening
     the source, never silently left out of a copy.
   - **Sample imports on the source are not refused.** An import's commit takes
     the same admission lock, so the copy is always a consistent committed
     snapshot and the import lands only on the source.
   - Declared files:
     - `packages/application-facade/include/lmdj/facade/application.hpp`
     - `packages/application-facade/src/application.cpp`
     - `tests/core/facade/application_test.cpp`
     - `tests/core/facade/failure_contract_test.cpp`
     - `apps/docs-site/docs/core/modules/application-facade.mdx`
     - this plan
   - Lowest-tier tests: `facade.application` (listed copy with the same Truth;
     live Sequence refusal; crashed owner's active Journal refused and not
     sealed; invalid identities) and `facade.failure_contracts` (an unexpected
     throw becomes the public envelope).
3. **web-runtime-platform** (`feat/1684-web-duplicate`). It does not depend
   on #1660 Task 2: it touches no Creator boot logic or browser spec.
   - Host operation `project.duplicate {source_project_id, project_id}` returns
     the copy's Local Project summary. It only copies: the open Project, its
     writer lease and the Runtime are untouched, and the caller opens the copy.
   - Like `project.create`, it refuses with `HOST_STATE_INVALID` while running,
     with an active Sequence, or with a pending Sample import.
   - Facade refusals map as follows:
     - `project_busy` → `PROJECT_BUSY`;
     - `duplicate_id` → `DUPLICATE_ID`;
     - an unfinished recording (`sequence_session_active` /
       `performance_session_active`) → `HOST_STATE_INVALID` with "source
       Project has an unfinished recording". The generic sanitizer would
       otherwise reduce it to a malformed request.
   - A deadline that passes before publication refuses the claim, so nothing is
     published and the bridge reports `HOST_TIMEOUT`.
   - Runtime Session `duplicateProject({sourceProjectId, projectId})` runs on
     the serial Project action lane, refuses an invalid or identical identity
     before any Host request, and accepts only the new identity at revision 0.
   - The operation joins `bridge.cpp`'s allow-list and `HOST_OPERATIONS`.
     `source_boundary_test.py` keeps the two in agreement.
   - An OPFS conformance case (Chromium) duplicates a Project with an Asset and
     reopens the copy and the source from a second Core instance.
   - Declared files:
     - `packages/web-runtime-platform/src/control_runtime.cpp`
     - `packages/web-runtime-platform/src/bridge.cpp`
     - `packages/web-runtime-platform/web/protocol.mjs`
     - `packages/web-runtime-platform/web/runtime_session.mjs`
     - `packages/web-runtime-platform/test/control_runtime_test.cpp`
     - `packages/web-runtime-platform/test/protocol.test.mjs`
     - `packages/web-runtime-platform/test/runtime_session.test.mjs`
     - `tests/platform/web/project_io/project_io_web_test.cpp`
     - `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
     - `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
     - `apps/docs-site/docs/platform/web-runtime.mdx`
     - this plan
   - Lowest-tier tests:
     - `host.web_control_runtime`: copy listed with the open Project kept;
       another tab → `PROJECT_BUSY`; unfinished recording named; identity in
       use → `DUPLICATE_ID`; refused publication claim → no copy; pending Sample
       import refused; exact payload;
     - `runtime_session.test.mjs`: payload; result; invalid requests; not
       started; wrong identity; wrong revision;
     - `protocol.test.mjs`;
     - the OPFS conformance case.
   - A C++ change under `packages/web-runtime-platform/src` selects the core,
     creator and web-runtime families, so this Task runs in full mode: every
     batch-only lane runs on the exact head before merge.
4. **creator-web** (after #1660 Task 2): Project library Duplicate action. It
   opens the copy and decides how the copy is named. Browser journeys cover the
   normal, refused, failed, cancelled and reopened paths. #1684 closes here.

## Verification (Task 1)

```bash
scripts/core.sh configure dev && cmake --build build/core/dev --target lmdj_project_bundle_transfer_tests
ctest --test-dir build/core/dev -R 'project_io\.' --output-on-failure
scripts/core.sh test dev fast
scripts/core.sh configure asan && scripts/core.sh build asan && ctest --preset asan -R 'project_io\.'
scripts/docs-site.sh check
bash tests/build/test_active_tree.sh
```

Each guard was mutation-checked, and the named test failed each time:

- skipping recordings;
- skipping either journal refusal;
- ignoring cancellation;
- keeping residue;
- changing copied state;
- skipping the SHA-256 check;
- dropping the held source lease;
- skipping the abort on a forced failure.

Automation proves persistence behaviour only. It is not device or listening
acceptance.

## Version Management

Version impact: none in this Pull Request.

Owed MINOR bumps:

| Module | From | To | Task |
|---|---|---|---|
| `project-io` | 4.2.1 | 4.3.0 | Task 1 |
| `application-facade` | 6.2.1 | 6.3.0 | Task 2 (typed `duplicate_project`) |
| `web-runtime-platform` | 5.3.3 | 5.4.0 | Task 3 (`project.duplicate`, `duplicateProject`) |
| `creator-web` | 4.5.1 | 4.6.0 | Task 4 |

Each is a backward-compatible public capability. Under the owed-version
convention (#1550, settled by #1621), Assembly pins forbid folding a module
identity change into a feature Pull Request, so each bump is deferred to the
next version cut. Bumps already owed by #1686 are combined, not stacked.

No Contract change: the copy is written in the unchanged `lmdj.project.v5`
Project format and manifest format, so no migration is needed. No tag, release,
promotion or deployment. Rollback is a revert of the squash commit.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/project-io /platform/storage
Reason: the Project I/O module page and diagram describe the new duplicate
operation, its refusals and its publication; the Storage Platform page describes
duplicate staging and the held source lease.

## Pitfall Impact

Pitfall impact: required. `revert-proof-rebuild-skipped` gains a third
occurrence: a `cp` restore plus a discarded rebuild log ran one mutation proof
against a stale binary. It was caught by the failure line sitting outside the
test under proof, and every proof above was rerun with a forced rebuild whose
output was read. No test target is added, so
`coverage-target-list-omits-new-test` does not apply.
