# LMDJ Stage 7 Creator Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Product Build `1.0.16.0 · canary` with a formal Desktop/Tablet Creator Web Host that opens a browser-local Project or imports a portable `.lmdj` bundle, activates the shared C++ Web Runtime, and plays all four 16-Pad Banks without exposing Stage 8–10 authoring features.

**Architecture:** Add a deterministic `lmdj.project-bundle.v1` transfer envelope and atomic Project I/O importer, expose discovery/import only through Application Facade, and extract the Stage 6 browser runtime into product-neutral `packages/web-runtime-platform`. Both the diagnostic `web-runtime-host` and new React `creator-web` Host consume one Runtime Session; Creator owns only product UI, selection, and view state. Product Assembly, Portal current truth, an immutable canary snapshot, packaged browser Proof, and manual acceptance remain distinct gates.

**Tech Stack:** C++20, CMake 3.24+, Emscripten `6.0.5`, WasmFS OPFS, SharedArrayBuffer, Wasm AudioWorklet, JavaScript ES modules, React `19.2.8`, React DOM `19.2.8`, TypeScript `7.0.2`, Vite `8.2.1`, `@vitejs/plugin-react 6.0.5`, Vitest `4.1.10`, Testing Library React `16.3.2`, Testing Library User Event `14.6.3`, jsdom `30.0.1`, `@types/node 26.1.2`, Node.js 22, Playwright `1.62.1`, Python 3.11, JSON Schema, Docusaurus Architecture Portal.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`. A conflict returns to design review; implementation must not silently weaken it.
- Stage 7 development may be stacked on `99f3b81039f054bb8202c7b9e28208e1eca7be00`, but its Pull Request cannot merge until PR #94 is in `main` and the merged Stage 6 baseline passes its required Proof.
- Execute implementation on `feat/stage7-creator-editor` in `/Users/endaye/Projects/lmdj/.worktrees/stage7-creator-editor`, created from the approved design/plan commit. Never modify `main` or implement in the retained docs worktree.
- Before a Stage 7 PR, fetch `origin/main` and prove `git merge-base --is-ancestor 99f3b81039f054bb8202c7b9e28208e1eca7be00 origin/main`; if false, keep the branch stacked and do not open a merge-ready PR.
- Creator uses `web-runtime-platform` and Application Facade only. It must not parse a Project tree, call Project I/O, read OPFS directly, or construct a second Runtime Snapshot.
- `web-runtime-host` remains a product-neutral diagnostic/conformance Host. It must retain protocol `1`, its diagnostic Project journey, 500-trigger Proof, Take boundary Proof, and restart-required semantics.
- Stage 7 exposes only Project, Bank selection, 4×4 Pads, audio lifecycle, input enablement, and privacy-safe report export. Sample, Sequence, and Perform are visible disabled controls with no route, Command, Job, or storage mutation.
- Do not add blank Project creation, Project rename, WAV/MP3 import, Pad assignment, Take/Pattern editing, Momentary FX, Resample, Sound Sets, PWA, Service Worker, account, cloud sync, telemetry, deployment, `beta`, or `stable` behavior.
- Project Truth remains `lmdj.project.v1`. `lmdj.project-bundle.v1` is only a portable transfer envelope and never becomes persisted Project Truth.
- Native import publication uses same-filesystem no-overwrite directory rename. Web import publication uses the approved R1 writer-lease + publication-intent protocol; do not depend on `FileSystemDirectoryHandle.move()`, which shipping Chromium does not implement for directories.
- Web Runtime stays one non-growing `536,870,912`-byte shared Wasm memory. Do not add a JavaScript sampler, fallback AudioContext path, ScriptProcessor, alternate Project parser, or browser-specific Contract.
- Audio activation always begins in a current user gesture. Reload, restart-required, Project reopen, visibility recovery, or pageshow cannot reactivate audio automatically.
- Pointer, Keyboard, and Web MIDI converge on the same serialized Runtime Session `trigger()` call and use real admission/outcome evidence. A timer cannot manufacture sound success.
- WebKit automation is capability-boundary evidence only. The five physical Web rows remain `deferred / unverified` and continue to block physical-pass, `beta`, and `stable`.
- Every implementation Task is one reviewable Conventional Commit. Functional Tasks keep active manifests unchanged until the version-integration Task so the current `1.0.15.0` Assembly/Portal remains coherent between commits.
- Before each functional commit run the Task tests and `scripts/architecture-portal.sh check`, stage only declared files, inspect `git diff --cached --name-status`, run `git diff --cached --check`, inspect the staged diff, commit, inspect `git show --name-status --oneline HEAD`, and confirm no Task residue remains.
- Task 11 is the governed Portal roll-forward boundary: it runs `npm --prefix apps/architecture-portal run check:current` before its source commit because the old immutable snapshot cannot match the new Build. Task 12 starts from that clean commit, freezes `1.0.16.0`, runs the full `scripts/architecture-portal.sh check`, and commits only generated immutable snapshot files.
- This plan authorizes local commits only. Push, PR, squash merge, tag, tag push, GitHub Release, publication, deployment, and Channel promotion each require separate authorization.

## Locked Portable Bundle Format

Stage 7 mechanically selects one uncompressed cross-platform container:

```text
offset  size  value
0       8     ASCII "LMDJBND1"
8       4     unsigned big-endian canonical-index byte length
12      N     canonical UTF-8 JSON index, no BOM and no trailing newline
12+N    ...   raw regular-file payloads in index order
```

The canonical index shape is:

```json
{
  "bundle_digest": "64 lowercase hex characters",
  "compression": "none",
  "contract": "lmdj.project-bundle.v1",
  "contract_version": "1.0.0",
  "entries": [
    {
      "bytes": 123,
      "offset": 0,
      "path": "manifest.json",
      "sha256": "64 lowercase hex characters"
    }
  ],
  "project_contract": "lmdj.project.v1",
  "project_id": "lowercase UUID",
  "uncompressed_bytes": 123
}
```

`bundle_digest` is SHA-256 of the canonical index with only the `bundle_digest` member omitted. Because that document includes every ordered path, byte length, payload offset, and file SHA-256, the digest commits to the complete Project contents without loading a 512 MiB bundle into Wasm or JavaScript memory. Entry offsets start at zero, are contiguous, and follow unsigned UTF-8 path order.

Exact limits are: index `4,194,304` bytes, `4,096` entries, path `255` UTF-8 bytes, each regular file `67,108,864` bytes, total uncompressed payload `536,870,912` bytes, and bridge chunks `1,048,576` bytes. Project-internal paths are the portable ASCII subset `[A-Za-z0-9._/-]` of UTF-8 because managed LMDJ names are generated, not user filenames. Absolute paths, `..`, `.`, empty segments, backslash, NUL/non-ASCII bytes, duplicate paths, ASCII case-fold collisions, undeclared payload bytes, gaps, overlaps, symlinks, hardlinks, device nodes, and non-canonical JSON fail closed.

## Runtime Session Interface

`packages/web-runtime-platform/web/runtime_session.mjs` exports exactly this Host-neutral surface:

```js
export function createRuntimeSession({
  document,
  window,
  navigator,
  crypto,
  manifestSource,
  assemblyIdentity,
  inputConfiguration,
  seams,
}) {
  return Object.freeze({
    start,
    listLocalProjects,
    importProject,
    openProject,
    inspectProject,
    reloadSnapshot,
    activateAudio,
    suspendAudio,
    trigger,
    requestMidi,
    close,
    subscribeHostState,
    subscribeRuntimeOutcome,
    diagnostics,
  });
}
```

The public values crossing from Platform to a Host are:

```ts
export type HostState =
  | 'cold' | 'preflight' | 'storage-ready' | 'core-ready'
  | 'audio-suspended' | 'running' | 'interrupted' | 'recovering'
  | 'restart-required' | 'closed' | 'failed';

export interface LocalProjectSummary {
  projectId: string;
  patternId: string;
  revision: number;
  bpm: number;
  assetCount: number;
  assignedPadCount: number;
  bundleDigest: string;
}

export interface TriggerAdmission {
  sequence: number;
  slot: number;
  velocity: number;
  source: 'pointer' | 'keyboard' | 'midi';
}

export interface RuntimeOutcome {
  sequence: number;
  outcome: 'voice_started' | 'voice_capacity';
  runtimeFrame: number;
}

export interface UserGestureToken {
  readonly kind: 'lmdj.web-runtime.user-gesture';
}
```

`createUserGestureToken(event)` is exported beside the input adapters, accepts
only a current trusted browser event, brands the token in a module-private
`WeakSet`, and is the only value accepted by `activateAudio(token)`.

## File Structure

### Transfer Contract and Project I/O

- `contracts/project/lmdj.project-bundle.v1.schema.json`: canonical index Contract `1.0.0`.
- `tools/project-bundle/project_bundle.py`: deterministic `pack` and `verify` CLI for Native fixtures; no Project mutation.
- `tests/conformance/project_bundle_contract_test.py`: binary header, canonical index, positive/negative Contract, and deterministic pack tests.
- `packages/project-io/include/lmdj/project_io/project_bundle_transfer.hpp`: discovery and bounded streaming import API.
- `packages/project-io/src/project_bundle_transfer.cpp`: inventory validation, staging, hash verification, collision handling, and atomic publish.
- `packages/project-io/include/lmdj/project_io/storage_platform.hpp`: direct-directory listing, recursive removal, and no-overwrite atomic-visibility directory publish obligations.
- Native/Web storage implementations and contract tests: identical externally visible obligations. Native uses directory rename; Web uses a hidden publication intent, bounded verified copy, and atomic file replacement as the visibility commit point.

### Application Facade and Shared Web Runtime

- `packages/application-facade/include/lmdj/facade/application.hpp`: Host-neutral Project discovery/import methods and types.
- `packages/application-facade/src/application.cpp`: validation and delegation to Project I/O transfer service.
- `packages/web-runtime-platform/include/lmdj/web_runtime/`: Control Runtime and manifest gate public headers.
- `packages/web-runtime-platform/src/`: shared Control Runtime, bridge, manifest gate, and Emscripten pre-JS.
- `packages/web-runtime-platform/web/`: protocol, preflight, loader, state machine, input adapters, bundle reader, and Runtime Session.
- `packages/web-runtime-platform/web/diagnostic_client.mjs`: explicit conformance-only mutation client; Creator source is forbidden from importing it.
- `packages/web-runtime-platform/test/`: C++, Node, source-boundary, lifecycle, transport, and bundle-streaming tests.
- `apps/web-runtime-host/`: diagnostic Project, diagnostic DOM adapter, styles, package ownership, and diagnostic-only tests.

### Creator Product Host

- `apps/creator-web/src/state/creator_state.ts`: orthogonal Project, Runtime, Audio, Import, Bank, and pressed-state reducer.
- `apps/creator-web/src/runtime/runtime_context.tsx`: one Runtime Session instance and lifecycle cleanup.
- `apps/creator-web/src/runtime/project_actions.ts`: list/import/open/reopen orchestration.
- `apps/creator-web/src/runtime/input_controller.ts`: Pointer/Keyboard/MIDI mapping to the selected Bank and admission/outcome reconciliation.
- `apps/creator-web/src/components/`: Status Bar, Mode Rail, Project Surface, Bank Selector, Pad Surface, and Error Panel.
- `apps/creator-web/src/report/acceptance_report.ts`: privacy-safe local JSON report; no network send.
- `apps/creator-web/src/app.tsx`, `main.tsx`, `styles.css`: complete Desktop/Tablet workspace composition.
- `apps/creator-web/test/`: reducer, view-model, component, disabled-mode, input, lifecycle, report, and responsive tests.
- `apps/creator-web/tools/package.py`: deterministic Creator distribution and ownership validation.
- `scripts/creator-web.sh`: stable configure/build/test/proof/package/serve/clean entry.
- `tests/platform/web/creator/creator_web_browser.spec.mjs`: packaged real Runtime Chromium journey and WebKit capability boundary.

## Documentation Impact

Documentation impact: required

Affected portal pages: `/` `/core/overview/` `/core/modules/application-facade/` `/core/modules/project-io/` `/core/modules/web-runtime-platform/` `/hosts/overview/` `/hosts/web-runtime/` `/hosts/creator-web/` `/contracts/project-bundle/` `/platform/web-runtime/` `/platform/input/` `/platform/storage/` `/assembly/lmdj/` `/operations/testing-and-proof/` `/operations/version-and-release/`

Reason: Stage 7 adds a public transfer Contract, compatible Project I/O and Facade APIs, a shared Web Runtime Platform Module, a formal Creator Host, a new Product Build/Assembly identity, packaged browser Proof, and an immutable canary documentation snapshot.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Identity | Baseline | Target | API | Reason |
| --- | --- | --- | --- | --- |
| Product Build | `1.0.15.0` | `1.0.16.0` | n/a | Adds Assembly-listed Creator Host, Runtime Platform Module, and transfer Contract. |
| `creator-web` | absent | `1.0.0` | 1 | First formal Creator Product Host. |
| `web-runtime-platform` | absent | `0.1.0` | 1 | First shared product-neutral Browser Runtime Session. |
| `web-runtime-host` | `1.1.0` | `1.2.0` | stays 1 | Compatible migration to the shared Platform; diagnostic protocol remains 1. |
| `project-io` | `0.4.0` | `0.5.0` | stays 1 | Compatible discovery and atomic transfer import. |
| `application-facade` | `1.2.0` | `1.3.0` | stays 2 | Compatible Project discovery/import API. |
| `core-cli` | `1.0.5` | `1.0.6` | stays 2 | Exact Facade dependency propagation only. |
| `core-mcp` | `1.1.2` | `1.1.3` | stays 2 | Exact Facade dependency and Python identity propagation only. |
| `native-test-host` | `1.0.3` | `1.0.4` | stays 1 | Exact Facade dependency propagation only. |
| `audio-runtime` | `0.4.0` | unchanged | stays 1 | No DSP, Voice, render, or realtime Contract change. |
| `lmdj.project.v1` | `1.0.0` | unchanged | unchanged | Project Truth shape and persistence remain unchanged. |
| `lmdj.project-bundle.v1` | absent | `1.0.0` | n/a | First portable transfer envelope. |
| Providers / Models | current | unchanged | unchanged | No Capability, Provider, or model change. |

- Before Task 11 writes any identity, verify `1.0.16.0` is still the next unused Build. If another approved Assembly change consumed it, replace every plan reference with the next unused Build before editing version files.
- Regenerate `products/lmdj/assembly.lock.json` only with `python3 scripts/version.py lock`; never hand-edit it.
- Candidate display is `1.0.16.0 · canary · g<short-sha>`.
- The future Product tag is `lmdj-v1.0.16.0`, signed and annotated only after merged-main Proof and separate approval.
- Rollback returns to immutable `1.0.15.0`; it does not delete imported OPFS Projects, reuse a Build number, or move a tag.

---

### Task 1: Define and prove the portable Project Bundle Contract

**Files:**

- Create: `contracts/project/lmdj.project-bundle.v1.schema.json`
- Create: `tools/project-bundle/project_bundle.py`
- Create: `tests/fixtures/contracts/project-bundle-valid.json`
- Create: `tests/fixtures/contracts/project-bundle-invalid-traversal.json`
- Create: `tests/conformance/project_bundle_contract_test.py`
- Modify: `tests/conformance/schema_contract_test.py`
- Modify: `tests/conformance/json_schema_test.py`

**Interfaces:**

- Produces: `canonical_json(value) -> bytes`, `bundle_digest(index) -> str`, `read_bundle(path) -> (index, payload_offset)`, `pack_directory(source, output) -> str`, and the exact binary format locked above.
- Consumes: existing `lmdj.project.v1` UUID, manifest, history, recovery, and Artifact constraints; it does not interpret Project state.

- [ ] **Step 1: Write failing Contract and container tests**

The positive test must assert the exact header and root digest rule:

```python
raw = bundle_path.read_bytes()
assert raw[:8] == b"LMDJBND1"
index_size = int.from_bytes(raw[8:12], "big")
index_bytes = raw[12 : 12 + index_size]
index = json.loads(index_bytes)
digest_source = dict(index)
del digest_source["bundle_digest"]
assert index_bytes == canonical_json(index)
assert index["bundle_digest"] == hashlib.sha256(
    canonical_json(digest_source)
).hexdigest()
```

Add parameterized negative cases for absolute path, `..`, `.`, empty segment, backslash, NUL, non-ASCII path byte, duplicate, ASCII case-fold collision, offset gap/overlap, wrong file hash, trailing bytes, 4,097 entries, 4 MiB+1 index, 64 MiB+1 entry, and 512 MiB+1 total.

- [ ] **Step 2: Run RED**

```bash
python3 tests/conformance/project_bundle_contract_test.py
```

Expected: FAIL because the schema and bundle tool do not exist.

- [ ] **Step 3: Implement the strict schema and deterministic tool**

The CLI is exact:

```text
project_bundle.py pack --source PROJECT_DIRECTORY --output FILE.lmdj
project_bundle.py verify FILE.lmdj
```

Packing uses `os.lstat`, permits regular files only, sorts by encoded UTF-8 bytes, writes a temporary sibling file, `fsync`s it, then `os.replace`s it. Verification streams payload entries in 1 MiB chunks and never extracts them.

- [ ] **Step 4: Run GREEN and determinism proof**

```bash
python3 tests/conformance/project_bundle_contract_test.py
python3 tests/conformance/json_schema_test.py
python3 tests/conformance/schema_contract_test.py
```

Expected: Contract/container tests PASS; two packs of one source directory are byte-identical; schema suites PASS.

- [ ] **Step 5: Run the current Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add contracts/project/lmdj.project-bundle.v1.schema.json \
  tools/project-bundle/project_bundle.py \
  tests/fixtures/contracts/project-bundle-valid.json \
  tests/fixtures/contracts/project-bundle-invalid-traversal.json \
  tests/conformance/project_bundle_contract_test.py \
  tests/conformance/schema_contract_test.py \
  tests/conformance/json_schema_test.py
git diff --cached --check
git commit -m "feat(project): define portable bundle contract"
```

### Task 2: Add bounded discovery and atomic import to Project I/O

**Files:**

- Create: `packages/project-io/include/lmdj/project_io/project_bundle_transfer.hpp`
- Create: `packages/project-io/src/project_bundle_transfer.cpp`
- Create: `tests/core/project_io/project_bundle_transfer_test.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/storage_platform.hpp`
- Modify: `packages/project-io/src/native/storage_platform.cpp`
- Modify: `packages/project-io/src/web/storage_platform.cpp`
- Modify: `packages/project-io/src/web/library_opfs_storage.js`
- Modify: `packages/project-io/CMakeLists.txt`
- Modify: `tests/core/project_io/storage_platform_contract_test.cpp`
- Modify: `tests/platform/web/project_io/project_io_web_test.cpp`
- Modify: `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- Modify: `tests/platform/web/project_io/CMakeLists.txt`

**Interfaces:**

- Produces:

```cpp
struct LocalProjectSummary {
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t revision;
  std::uint16_t bpm;
  std::size_t asset_count;
  std::size_t assigned_pad_count;
  std::string bundle_digest;
  friend bool operator==(const LocalProjectSummary&, const LocalProjectSummary&)
      = default;
};

struct BundleImportSession {
  std::string token;
  std::uint64_t expected_index_bytes;
};

struct BundleImportIdentity {
  foundation::ProjectId project_id;
  std::string bundle_digest;
  std::uint32_t entry_count;
};

class ProjectBundleTransfer final {
 public:
  explicit ProjectBundleTransfer(
      std::shared_ptr<ProjectStoragePlatform> platform);
  foundation::Result<std::vector<LocalProjectSummary>> list_local_projects(
      const std::filesystem::path& workspace_root) const;
  foundation::Result<BundleImportSession> begin(
      const std::filesystem::path& workspace_root,
      std::string token,
      std::uint64_t index_bytes,
      std::string index_sha256);
  foundation::Result<std::optional<BundleImportIdentity>> append_index(
      std::string_view token,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<void> append_entry(
      std::string_view token,
      std::uint32_t entry_index,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<LocalProjectSummary> commit(std::string_view token);
  foundation::Result<void> abort(std::string_view token);
  foundation::Result<void> cleanup_incomplete(
      const std::filesystem::path& workspace_root);
};
```

- Extends `ProjectStoragePlatform` with `list_directories(path)`, `remove_tree(path)`, and `publish_directory_if_absent(staging, destination)`.
- Native publish uses a same-filesystem no-overwrite directory rename. Web publish uses the R1 journaled-copy protocol below; raw destination existence never implies discoverability while its publication intent is pending.

- [ ] **Step 1: Write failing storage and transfer tests**

Cover sorted Project discovery, ignoring `.lmdj-host/import-staging`, multi-chunk index/entry writes, canonical/hash validation, 64 MiB and 512 MiB limits, abort cleanup, startup cleanup, interruption before publish, publish failure, same-ID/same-digest idempotency, same-ID/different-digest `DUPLICATE_ID`, and writer contention. Web conformance additionally faults initial intent persistence, bounded copy, verification, atomic commit replacement, source cleanup, and intent cleanup; before the commit point Project list equals its prior value, and after it Project list contains the complete validated Project.

The central atomicity assertion is:

```cpp
const auto before = transfer.list_local_projects(workspace);
faults.fail_next_publish = true;
const auto failed = transfer.commit(session.token);
LMDJ_CHECK(!failed.has_value());
LMDJ_CHECK(transfer.list_local_projects(workspace).value() == before.value());
```

- [ ] **Step 2: Run RED**

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^core\.project_io\.(storage_platform_contract|project_bundle_transfer)$'
```

Expected: compile/test failure because the storage obligations and transfer type are absent.

- [ ] **Step 3: Implement Native semantics and common transfer state machine**

Staging lives only below:

```text
WORKSPACE/.lmdj-host/import-staging/<128-bit-token>/project.lmdj
```

Visible Projects live only below:

```text
WORKSPACE/projects/<project-id>.lmdj
```

`commit()` verifies every declared byte/hash, calls `ProjectStore::load()` on staging, verifies `manifest.project_id`, releases the staging writer lease, and performs one no-overwrite atomic publish. No absolute path enters returned details.

- [ ] **Step 4: Implement the Web storage obligations**

Reuse the existing OPFS cross-tab writer lease and storage-intent recovery. The exact publication record is stored at:

```text
WORKSPACE/.lmdj-host/storage-intents/<destination-scope>/directory-publication.json
```

It has exact canonical fields `{contract, destination, source, state}` with
contract `lmdj.storage.directory-publication.v1` and state `pending` or
`committed`. `publish_directory_if_absent()` performs, in order:

1. require the destination writer lease and recover any prior exact-destination intent;
2. reject an existing destination without a recoverable intent;
3. persist and read back `pending` before creating destination;
4. copy regular files in at most 1 MiB slices and recursively create directories;
5. compare source/destination names, kinds, lengths, and every byte in at most 1 MiB slices;
6. replace the intent atomically with `committed` through `createWritable()` + `close()`;
7. remove source, then remove intent.

`list_directories()` filters an exact child whose publication intent is pending
or malformed, includes committed children, and keeps legacy/no-intent Projects
compatible. Destination-lease recovery removes pending partial destinations;
committed recovery keeps destination and removes source/intent residue. A
failure after the commit point returns the complete Project on authoritative
reopen rather than deleting it. Neither marker nor internal path enters errors,
Bundle inventory, Project Truth, or Host diagnostics.

- [ ] **Step 5: Run Native and Web GREEN**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^core\.project_io\.(storage_platform_contract|project_bundle_transfer)$'
scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  project_io/project_io_web_conformance.spec.mjs
```

Expected: Native and Chromium storage/import matrices PASS; Chromium does not require directory `move()`; every R1 fault point exposes either the prior Project list or the complete new Project, never a partial Project.

- [ ] **Step 6: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add packages/project-io tests/core/project_io \
  tests/platform/web/project_io
git diff --cached --check
git commit -m "feat(project-io): import project bundles atomically"
```

### Task 3: Expose discovery and import through Application Facade

**Files:**

- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/c_api_test.cpp`

**Interfaces:**

- Produces:

```cpp
struct ProjectBundleImportBeginRequest {
  std::string import_token;
  std::uint64_t index_bytes;
  std::string index_sha256;
};

struct LocalProjectSummary {
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t revision;
  std::uint16_t bpm;
  std::size_t asset_count;
  std::size_t assigned_pad_count;
  std::string bundle_digest;
};

struct ProjectBundleImportSession {
  std::string token;
  std::uint64_t expected_index_bytes;
};

struct ProjectBundleImportIdentity {
  foundation::ProjectId project_id;
  std::string bundle_digest;
  std::uint32_t entry_count;
};

class Application {
 public:
  foundation::Result<std::vector<LocalProjectSummary>>
  list_local_projects();
  foundation::Result<ProjectBundleImportSession>
  begin_project_bundle_import(const ProjectBundleImportBeginRequest& request);
  foundation::Result<std::optional<ProjectBundleImportIdentity>>
  append_project_bundle_index(std::string_view token,
                              std::uint64_t offset,
                              std::span<const std::byte> bytes,
                              bool final);
  foundation::Result<void> append_project_bundle_entry(
      std::string_view token,
      std::uint32_t entry_index,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<LocalProjectSummary>
  commit_project_bundle_import(std::string_view token);
  foundation::Result<void> abort_project_bundle_import(
      std::string_view token);
};
```

- The Facade supplies its configured `workspace_root`; Hosts never pass a Project or staging path.
- No new JSON CLI/MCP operation or C ABI symbol is added in Stage 7. Existing C ABI compatibility is proved unchanged.

- [ ] **Step 1: Write failing Facade tests**

```cpp
auto application = make_application(workspace);
const auto session = application.begin_project_bundle_import(
    {.import_token = uuid(900),
     .index_bytes = index.size(),
     .index_sha256 = sha256(index)});
LMDJ_CHECK(session.has_value());
stream_bundle(application, session.value(), index, entries);
const auto committed =
    application.commit_project_bundle_import(session.value().token);
LMDJ_CHECK(committed.has_value());
LMDJ_CHECK(application.list_local_projects().value().size() == 1);
```

Also assert invalid hash/offset/token and wrong project identity are typed failures; C API symbol and behavior snapshots remain identical.

- [ ] **Step 2: Run RED**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^core\.facade\.(application|c_api)$'
```

Expected: compile failure because the Facade methods are absent.

- [ ] **Step 3: Implement minimal validated delegation**

Construct one `ProjectBundleTransfer` beside the existing `ProjectStore` in `Application::Impl`. Validate index sizes, hashes, tokens, offsets, chunk lengths, and final flags before delegation. Preserve existing exception-to-typed-error conversion and never return `workspace_root` or staging paths.

- [ ] **Step 4: Run GREEN, Portal gate, and commit**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^core\.facade\.(application|c_api)$'
scripts/architecture-portal.sh check
git add packages/application-facade tests/core/facade
git diff --cached --check
git commit -m "feat(facade): expose project bundle import"
```

### Task 4: Extract the shared C++ Web Runtime Platform

**Files:**

- Create: `packages/web-runtime-platform/CMakeLists.txt`
- Create: `packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`
- Create: `packages/web-runtime-platform/include/lmdj/web_runtime/manifest_gate.hpp`
- Move: `apps/web-runtime-host/src/control_runtime.cpp` → `packages/web-runtime-platform/src/control_runtime.cpp`
- Move: `apps/web-runtime-host/src/bridge.cpp` → `packages/web-runtime-platform/src/bridge.cpp`
- Move: `apps/web-runtime-host/src/manifest_gate.cpp` → `packages/web-runtime-platform/src/manifest_gate.cpp`
- Move: `apps/web-runtime-host/src/web-runtime-pre.js` → `packages/web-runtime-platform/src/web-runtime-pre.js`
- Move: `apps/web-runtime-host/test/control_runtime_test.cpp` → `packages/web-runtime-platform/test/control_runtime_test.cpp`
- Move: `apps/web-runtime-host/test/realtime_session_test.cpp` → `packages/web-runtime-platform/test/realtime_session_test.cpp`
- Move: `apps/web-runtime-host/test/manifest_gate_test.cpp` → `packages/web-runtime-platform/test/manifest_gate_test.cpp`
- Create: `packages/web-runtime-platform/test/source_boundary_test.py`
- Modify: `apps/web-runtime-host/CMakeLists.txt`
- Modify: `apps/web-runtime-host/src/main.mjs`
- Modify: `apps/web-runtime-host/tools/package.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `apps/web-runtime-host/test/distribution_test.py`
- Modify: `CMakeLists.txt`
- Modify: `scripts/web-runtime-host.sh`

**Interfaces:**

- Produces CMake targets `lmdj::web_runtime_control`, `lmdj::web_runtime_manifest_gate`, and the compatibility-named Emscripten target `lmdj_web_runtime_host` with shared output `lmdj-web-runtime.js/.wasm`. Retaining the target name keeps the still-frozen `1.0.15.0` Product CMake/Assembly Lock coherent until Task 11; ownership and output identity are already Platform-neutral.
- App CMake may select a distribution manifest, but no app owns Control Runtime, bridge, Wasm pre-JS, Project orchestration, or AudioWorklet startup.
- C++ namespace changes from `lmdj::web_host` to `lmdj::web_runtime`; no runtime semantics change in this Task.

- [ ] **Step 1: Add the failing ownership test**

The test must fail if any of these remain below an app:

```python
FORBIDDEN_APP_FILES = {
    "control_runtime.cpp", "control_runtime.hpp", "bridge.cpp",
    "manifest_gate.cpp", "manifest_gate.hpp", "web-runtime-pre.js",
}
assert not any(
    path.name in FORBIDDEN_APP_FILES
    for path in (repo / "apps").rglob("*") if path.is_file()
)
```

It also rejects React/DOM/CSS/product IDs from `packages/web-runtime-platform` and direct Project I/O use from either Host.

- [ ] **Step 2: Run RED**

```bash
python3 packages/web-runtime-platform/test/source_boundary_test.py
```

Expected: FAIL because shared sources still belong to `apps/web-runtime-host`.

- [ ] **Step 3: Move sources and establish shared build targets**

Preserve the fixed heap/link flags and all exported bridge functions. Generalize manifest expectation to:

```cpp
struct ManifestExpectation {
  struct ComponentIdentity {
    std::string_view id;
    std::string_view version;
  };
  std::string_view distribution_contract;
  std::string_view product_build;
  std::string_view platform_version;
  std::span<const ComponentIdentity> allowed_hosts;
  std::uint32_t protocol_version;
};
```

The compatibility target receives Product Build and allowed Host identities from its Product-owned link configuration, then validates the canonical manifest before creating Control/Facade resources. Task 4 temporarily preserves the current Web Host identity supplied by `apps/web-runtime-host/CMakeLists.txt`; Task 11 moves the generated two-Host allowlist into `products/lmdj/CMakeLists.txt`. Creator and Diagnostic distributions never require separate Wasm binaries.

The shared C++ manifest gate no longer hardcodes the diagnostic app's nine
assets. It accepts `1..64` unique content-hashed relative assets, validates
exact `{bytes,path,role,sha256}` keys, positive safe lengths, path/hash
agreement, total manifest size, and exactly one `runtime_script` plus one
`runtime_wasm`. Each app package verifier owns its stricter complete inventory;
the Product-owned allowlist binds distribution contract, Host ID/version, and
Platform version before Control resources exist.

- [ ] **Step 4: Run shared C++ and diagnostic regression tests**

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^host\.web_(control_runtime|realtime_session|manifest_gate)$'
python3 packages/web-runtime-platform/test/source_boundary_test.py
scripts/web-runtime-host.sh build
scripts/web-runtime-host.sh test
```

Expected: all moved tests PASS; the diagnostic Host still builds and uses `lmdj-web-runtime.js/.wasm`.

- [ ] **Step 5: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add CMakeLists.txt \
  packages/web-runtime-platform apps/web-runtime-host scripts/web-runtime-host.sh
git diff --cached --check
git commit -m "refactor(web): extract shared runtime platform"
```

### Task 5: Extract the browser Runtime Session and migrate the diagnostic Host

**Files:**

- Move: `apps/web-runtime-host/src/protocol.mjs` → `packages/web-runtime-platform/web/protocol.mjs`
- Move: `apps/web-runtime-host/src/preflight.mjs` → `packages/web-runtime-platform/web/preflight.mjs`
- Move: `apps/web-runtime-host/src/state_machine.mjs` → `packages/web-runtime-platform/web/state_machine.mjs`
- Move: `apps/web-runtime-host/src/input_adapters.mjs` → `packages/web-runtime-platform/web/input_adapters.mjs`
- Create: `packages/web-runtime-platform/web/runtime_loader.mjs`
- Create: `packages/web-runtime-platform/web/runtime_session.mjs`
- Move corresponding Node tests to: `packages/web-runtime-platform/test/*.test.mjs`
- Create: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Create: `packages/web-runtime-platform/web/diagnostic_client.mjs`
- Create: `packages/web-runtime-platform/test/diagnostic_client.test.mjs`
- Modify: `apps/web-runtime-host/src/main.mjs`
- Modify: `apps/web-runtime-host/src/diagnostic_project.mjs`
- Modify: `apps/web-runtime-host/test/diagnostic_project.test.mjs`
- Modify: `apps/web-runtime-host/test/main_shell.test.mjs`
- Modify: `apps/web-runtime-host/tools/package.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `apps/web-runtime-host/test/distribution_test.py`
- Modify: `tests/platform/web/host/web_runtime_host_browser.spec.mjs`
- Modify: `tests/platform/web/host/web_runtime_host_lifecycle.spec.mjs`

**Interfaces:**

- Produces the locked Runtime Session API and types above.
- Diagnostic `main.mjs` owns only DOM selection/rendering, diagnostic Project preparation, diagnostic counts, and visible buttons.
- `runtime_session.mjs` owns manifest verification, preflight, Runtime loader, Host state, bounded transport, audio lifecycle, outcome ledger, and terminal cleanup.
- `createDiagnosticClient(session)` exposes only `createProject`, `importAsset`, and `assignPad` through a module-private transport symbol. `packages/web-runtime-platform/test/source_boundary_test.py` rejects this import anywhere below `apps/creator-web`.

- [ ] **Step 1: Write failing Runtime Session ownership/lifecycle tests**

```js
const session = createRuntimeSession(seams);
assert.equal(await session.start(), true);
assert.equal(session.diagnostics().state, 'audio-suspended');
const states = [];
const unsubscribe = session.subscribeHostState((value) => states.push(value));
const token = createUserGestureToken({isTrusted: true});
await session.activateAudio(token);
assert.equal(session.diagnostics().state, 'running');
await session.close();
unsubscribe();
assert.deepEqual(states.at(-1), {state: 'closed', errorCode: null});
```

Add tests for duplicate start, untrusted activation, timeout→restart-required, late response suppression, pagehide cleanup, MIDI listener disposal, and one terminal notification.

- [ ] **Step 2: Run RED**

```bash
node --test packages/web-runtime-platform/test/*.test.mjs
```

Expected: FAIL because `runtime_session.mjs` does not exist.

- [ ] **Step 3: Extract the session and reduce diagnostic Main**

The diagnostic Host creates one session, subscribes to state/outcomes, and invokes only public methods. Keep `createDiagnosticProjectCoordinator` in the app, but replace its raw transport seam with `openProject`, `inspectProject`, `reloadSnapshot`, plus the separate conformance-only client. The Runtime Session object does not expose raw `send()` and Creator cannot import the conformance client.

- [ ] **Step 4: Prove byte ownership and full diagnostic behavior**

```bash
node --test packages/web-runtime-platform/test/*.test.mjs
node --test apps/web-runtime-host/test/*.test.mjs
python3 apps/web-runtime-host/test/package_test.py
scripts/web-runtime-host.sh proof
```

Expected: Platform/Host unit tests PASS; packaged diagnostic Host retains Load→ready→Activate→running, 500/500 outcomes, Take boundary, reload, restart-required, and WebKit limitation behavior.

- [ ] **Step 5: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add packages/web-runtime-platform apps/web-runtime-host \
  tests/platform/web/host
git diff --cached --check
git commit -m "refactor(web): share browser runtime session"
```

### Task 5R1: Replace the unavailable Web directory move with journaled publication

**Files:**

- Modify: `packages/project-io/src/web/library_opfs_storage.js`
- Modify: `tests/platform/web/project_io/project_io_web_test.cpp`
- Modify: `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- Modify if the common fault seam requires it: `packages/project-io/src/web/storage_platform.cpp`
- Modify if the public storage contract requires clarification: `packages/project-io/include/lmdj/project_io/storage_platform.hpp`
- Modify: `tests/core/project_io/storage_platform_contract_test.cpp`
- Modify: `tests/core/project_io/project_bundle_transfer_test.cpp`

**Interfaces:**

- `publish_directory_if_absent(staging, destination)` keeps the same C++ API and
  externally visible Native/Web contract.
- Web adds no new browser capability. It consumes the already mandatory
  `opfsSyncAccessHandle` and `opfsWritableReplace` primitives.
- The private publication record is exactly
  `{contract, destination, source, state}` with contract
  `lmdj.storage.directory-publication.v1` and state `pending | committed`.
- Internal copy and comparison buffers never exceed `1,048,576` bytes.
- Pending/malformed publication is invisible; committed/no-intent publication is
  visible. Recovery owns the same destination writer lease as publication.

- [ ] **Step 1: Write failing Chromium crash-boundary tests**

Add deterministic fault points:

```text
before_intent_write
during_intent_write
after_pending_intent
during_directory_copy
after_directory_copy
during_directory_verify
before_commit_close
after_commit_close
before_source_cleanup
before_intent_cleanup
```

For every point, terminate the publishing page/Worker, reopen in a new page,
and assert the authoritative Project list. The first seven points must expose
the prior list; the final three must expose the complete Project. Also prove:

- pending and malformed intents hide partial destination directories;
- recovery removes pending destination and allows retry;
- committed recovery preserves destination and makes same-digest retry idempotent;
- a different digest remains `DUPLICATE_ID`;
- legacy no-intent Projects remain discoverable;
- copy/verify slices are at most 1 MiB;
- no internal marker/path appears in Host errors or Project inventory.

- [ ] **Step 2: Run RED**

```bash
scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  project_io/project_io_web_conformance.spec.mjs
```

Expected: FAIL because shipping Chromium has no directory move and journaled
publication/fault recovery is absent.

- [ ] **Step 3: Implement the minimal R1 publication state machine**

Extend the existing lease-scoped storage-intent machinery rather than adding a
second catalog. Persist/read back pending before destination creation; copy and
compare ordered trees using bounded slices; atomically replace the intent with
committed; then clean source and intent. Filter pending/malformed destinations
from Web directory enumeration and recover exact-destination intent on writer
lease acquisition.

- [ ] **Step 4: Run GREEN and cross-platform regressions**

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^core\.project_io\.(storage_platform_contract|project_bundle_transfer)$'
scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  project_io/project_io_web_conformance.spec.mjs
scripts/web-runtime-host.sh proof
```

Expected: common Native tests, the full Chromium publication fault matrix, and
the unchanged diagnostic Host Proof PASS without a directory-move capability.

- [ ] **Step 5: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add packages/project-io/src/web \
  packages/project-io/include/lmdj/project_io/storage_platform.hpp \
  tests/core/project_io/storage_platform_contract_test.cpp \
  tests/core/project_io/project_bundle_transfer_test.cpp \
  tests/platform/web/project_io
git diff --cached --check
git commit -m "fix(project-io): journal web project publication"
```

### Task 6: Stream Project Bundle import through the shared Web transport

**Files:**

- Create: `packages/web-runtime-platform/web/project_bundle_reader.mjs`
- Create: `packages/web-runtime-platform/test/project_bundle_reader.test.mjs`
- Modify: `packages/web-runtime-platform/web/protocol.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/src/bridge.cpp`
- Modify: `packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`
- Modify: `packages/web-runtime-platform/test/control_runtime_test.cpp`
- Modify: `packages/web-runtime-platform/test/realtime_session_test.cpp`
- Modify: `packages/web-runtime-platform/test/protocol.test.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`

**Interfaces:**

- Adds private protocol-1 operations `project.list`, `project.import.begin`, `project.import.index`, `project.import.entry`, `project.import.commit`, and `project.import.abort`.
- `project.import.begin` payload is `{import_token, index_bytes, index_sha256}`; Runtime Session creates the lowercase UUID with `crypto.randomUUID()` and Project I/O rejects reuse.
- `project.import.index` payload is `{import_token, offset, final, sidecar}`.
- `project.import.entry` payload is `{import_token, entry_index, offset, final, sidecar}`.
- `project.import.commit` and `.abort` payloads are `{import_token}`.
- `RuntimeSession.importProject(file, {signal, onProgress})` reads only the 12-byte header and at most one 1 MiB chunk at a time, streams index then payload, aborts exactly once on failure/cancel, and returns `LocalProjectSummary`.

- [ ] **Step 1: Write failing reader/protocol tests**

```js
const calls = [];
const result = await importProject(bundleFile, {
  send: async (operation, payload, sidecar) => {
    calls.push({operation, payload, bytes: sidecar?.byteLength ?? 0});
    return fakeResponse(operation);
  },
});
assert.equal(result.projectId, PROJECT_ID);
assert.ok(calls.every((call) => call.bytes <= 1_048_576));
assert.equal(calls.at(-1).operation, 'project.import.commit');
```

Negative tests cover wrong magic, non-canonical index, limit breach before runtime mutation, cancel, chunk offset mismatch, typed rejection, and abort failure without hiding the primary error.

- [ ] **Step 2: Run RED**

```bash
node --test packages/web-runtime-platform/test/project_bundle_reader.test.mjs \
  packages/web-runtime-platform/test/protocol.test.mjs
```

Expected: FAIL because the reader and operations are absent.

- [ ] **Step 3: Implement serialized streaming and Control/Fascade delegation**

Keep the bridge sidecar capacity `1,048,576`; do not enlarge 16 request slots. Map Project I/O limit details to `WEB_RUNTIME_RESOURCE_LIMIT`, storage contention to `PROJECT_BUSY`, identity collision to `DUPLICATE_ID`, and invalid transfer/tree to `INVALID_PROJECT`. R1 publication consumes the already mandatory `opfsWritableReplace`; it adds no directory-move capability and does not weaken preflight.

- [ ] **Step 4: Run GREEN and diagnostic regression**

```bash
node --test packages/web-runtime-platform/test/*.test.mjs
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^host\.web_(control_runtime|realtime_session)$'
scripts/web-runtime-host.sh proof
```

Expected: streaming tests and all diagnostic regressions PASS; Chromium Host startup remains supported. WebKit reports only capabilities it actually lacks from the pre-R1 mandatory list and never reports a synthetic directory-move requirement.

- [ ] **Step 5: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add packages/web-runtime-platform
git diff --cached --check
git commit -m "feat(web): stream project bundle imports"
```

### Task 7: Build the Creator workspace shell and orthogonal state model

**Files:**

- Create: `apps/creator-web/package.json`
- Create: `apps/creator-web/package-lock.json`
- Create: `apps/creator-web/tsconfig.json`
- Create: `apps/creator-web/vite.config.ts`
- Create: `apps/creator-web/index.html`
- Create: `apps/creator-web/src/main.tsx`
- Create: `apps/creator-web/src/app.tsx`
- Create: `apps/creator-web/src/styles.css`
- Create: `apps/creator-web/src/state/creator_state.ts`
- Create: `apps/creator-web/src/state/view_model.ts`
- Create: `apps/creator-web/src/components/status_bar.tsx`
- Create: `apps/creator-web/src/components/mode_rail.tsx`
- Create: `apps/creator-web/src/components/project_surface.tsx`
- Create: `apps/creator-web/src/components/bank_selector.tsx`
- Create: `apps/creator-web/src/components/pad_surface.tsx`
- Create: `apps/creator-web/src/components/error_panel.tsx`
- Create: `apps/creator-web/test/setup.ts`
- Create: `apps/creator-web/test/creator_state.test.ts`
- Create: `apps/creator-web/test/workspace_shell.test.tsx`

**Interfaces:**

- Produces `CreatorState`, `CreatorAction`, `creatorReducer`, `initialCreatorState`, and selectors `selectCreatorPhase`, `selectVisiblePads`, `selectCanActivateAudio`, and `selectCanTrigger`.
- Runtime is injected as a typed fake in this Task; no OPFS or Wasm call exists in component code.

- [ ] **Step 1: Write failing reducer and accessibility tests**

The state is orthogonal:

```ts
export interface CreatorState {
  project: {phase: 'listing' | 'empty' | 'opening' | 'ready' | 'error';
            projects: LocalProjectSummary[]; current: ProjectView | null};
  runtime: {phase: 'booting' | 'unsupported' | 'ready' | 'restart-required' | 'failed' | 'closed';
            errorCode: string | null};
  audio: {phase: 'inactive' | 'activating' | 'running' | 'suspended'};
  transfer: {phase: 'idle' | 'importing'; completedBytes: number; totalBytes: number};
  activeBank: 0 | 1 | 2 | 3;
  pressed: ReadonlyMap<number, 'admitted' | 'started' | 'capacity'>;
}
```

`selectCreatorPhase` applies this exact priority: `failed`, `closed`,
`restart-required`, `unsupported`, `booting`, `importing`, `opening`, `empty`,
`activating`, `running`, `suspended`, then `ready`. Initial post-open audio is
`inactive` and derives `ready`; only an explicit suspend derives `suspended`.

Testing Library must assert Project is enabled, Sample/Sequence/Perform are native `disabled`, future modes are absent from tab order, Key renders `—`, and no project name is invented.

- [ ] **Step 2: Run RED**

```bash
npm --prefix apps/creator-web test -- --run
```

Expected: FAIL because the Creator package and components do not exist.

- [ ] **Step 3: Add pinned package identity and minimal components**

Use exact dependencies from the Tech Stack and lock with:

```bash
npm --prefix apps/creator-web install --package-lock-only --ignore-scripts
```

`package.json` uses this exact dependency surface:

```json
{
  "name": "@lmdj/creator-web",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "engines": {"node": ">=22.13.0 <23"},
  "scripts": {
    "build": "tsc --noEmit && vite build",
    "test": "vitest"
  },
  "dependencies": {
    "react": "19.2.8",
    "react-dom": "19.2.8"
  },
  "devDependencies": {
    "@testing-library/react": "16.3.2",
    "@testing-library/user-event": "14.6.3",
    "@types/node": "26.1.2",
    "@types/react": "19.2.18",
    "@types/react-dom": "19.2.4",
    "@vitejs/plugin-react": "6.0.5",
    "jsdom": "30.0.1",
    "typescript": "7.0.2",
    "vite": "8.2.1",
    "vitest": "4.1.10"
  }
}
```

`vite.config.ts` resolves `@lmdj/web-runtime-platform` to the repository
package with `fileURLToPath(new URL('../../packages/web-runtime-platform/web',
import.meta.url))`; Creator tests replace only the Runtime Session factory,
never its Project data parser.

`tsconfig.json` uses `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `jsx: react-jsx`, `moduleResolution: Bundler`, `allowJs: true`, and `checkJs: false`; `vite.config.ts` remains inside the same no-emit typecheck.

The layout CSS uses top status, left mode rail, center surface, and bottom Pads:

```css
.workspace {
  min-height: 100dvh;
  display: grid;
  grid-template: "status status" auto "rail surface" minmax(0, 1fr)
                 "pads pads" auto / 11rem minmax(0, 1fr);
}
.pad-grid {display: grid; grid-template-columns: repeat(4, minmax(44px, 1fr));}
@media (max-width: 900px) {
  .workspace {grid-template-columns: 4rem minmax(0, 1fr);}
  .mode-label {position: absolute; inline-size: 1px; block-size: 1px; overflow: hidden;}
}
```

- [ ] **Step 4: Run GREEN at all locked viewports**

```bash
npm --prefix apps/creator-web ci
npm --prefix apps/creator-web test -- --run
npm --prefix apps/creator-web run build
```

Expected: reducer/component tests PASS; TypeScript/Vite production build succeeds with no runtime asset or network fallback.

- [ ] **Step 5: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web
git diff --cached --check
git commit -m "feat(creator): add project workspace shell"
```

### Task 8: Connect local Project discovery, import, open, and inspect

**Files:**

- Create: `apps/creator-web/src/runtime/runtime_context.tsx`
- Create: `apps/creator-web/src/runtime/project_actions.ts`
- Create: `apps/creator-web/src/runtime/runtime_types.ts`
- Create: `apps/creator-web/test/runtime_context.test.tsx`
- Create: `apps/creator-web/test/project_actions.test.ts`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/components/project_surface.tsx`
- Modify: `apps/creator-web/src/components/status_bar.tsx`
- Modify: `apps/creator-web/src/state/creator_state.ts`
- Modify: `apps/creator-web/test/workspace_shell.test.tsx`

**Interfaces:**

- `openProjectJourney(session, summary)` calls `openProject`, `inspectProject`, `reloadSnapshot(summary.patternId)`, then emits one ready View Model.
- `importProjectJourney(session, file, signal, progress)` calls `importProject` then the same open journey.
- React creates exactly one Runtime Session and closes it once on terminal unmount/pagehide.

```ts
export interface ProjectView extends LocalProjectSummary {
  key: '—';
  pads: readonly {slot: number; assetId: string | null}[];
}
```

- [ ] **Step 1: Write failing Project journey tests**

```ts
const view = await importProjectJourney(
  fakeSession,
  new File([bundleBytes], 'beat.lmdj'),
  abortController.signal,
  (value) => progress.push(value),
);
expect(fakeSession.calls).toEqual([
  'importProject', 'openProject', 'inspectProject', 'reloadSnapshot',
]);
expect(view.projectId).toBe(PROJECT_ID);
expect(view.key).toBe('—');
```

Also test empty local list, sorted list, invalid import, duplicate ID, abort, busy retry presentation, resource rejection, restart-required, and no Project mutation from disabled modes.

- [ ] **Step 2: Run RED**

```bash
npm --prefix apps/creator-web test -- --run \
  test/project_actions.test.ts test/runtime_context.test.tsx
```

Expected: FAIL because the journeys/provider are absent.

- [ ] **Step 3: Implement the user-visible Project Surface**

Use one hidden file input with:

```tsx
<input
  ref={fileInput}
  type="file"
  accept=".lmdj,application/vnd.lmdj.project-bundle"
  onChange={onImportFile}
  tabIndex={-1}
  aria-hidden="true"
/>
```

The visible `Import .lmdj` button invokes it; `Open local` renders summaries by short Project ID, revision, BPM, assigned Pads, and Assets. Do not render filename after import, absolute path, asset name, or inferred key.

- [ ] **Step 4: Run GREEN and source-boundary checks**

```bash
npm --prefix apps/creator-web test -- --run
npm --prefix apps/creator-web run build
python3 packages/web-runtime-platform/test/source_boundary_test.py
bash scripts/verify-core-dependencies.sh
```

Expected: all Creator tests/build pass; Creator has no Project I/O/OPFS/bundle parser import.

- [ ] **Step 5: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web
git diff --cached --check
git commit -m "feat(creator): open and import local projects"
```

### Task 9: Connect playable Pads, audio lifecycle, MIDI, and recovery

**Files:**

- Create: `apps/creator-web/src/runtime/input_controller.ts`
- Create: `apps/creator-web/src/report/acceptance_report.ts`
- Create: `apps/creator-web/test/input_controller.test.ts`
- Create: `apps/creator-web/test/audio_lifecycle.test.tsx`
- Create: `apps/creator-web/test/acceptance_report.test.ts`
- Modify: `apps/creator-web/src/runtime/runtime_context.tsx`
- Modify: `apps/creator-web/src/components/pad_surface.tsx`
- Modify: `apps/creator-web/src/components/bank_selector.tsx`
- Modify: `apps/creator-web/src/components/status_bar.tsx`
- Modify: `apps/creator-web/src/state/creator_state.ts`
- Modify: `packages/web-runtime-platform/web/input_adapters.mjs`
- Modify: `packages/web-runtime-platform/test/input_adapters.test.mjs`

**Interfaces:**

- `createCreatorInputController({session, getActiveBank, isAssigned, dispatch})` exposes `pointerDown/up/cancel`, `keyDown/up`, `enableMidi`, `clearPressed`, and `dispose`.
- Keyboard codes `KeyA KeyS KeyD KeyF KeyG KeyH KeyJ KeyK KeyQ KeyW KeyE KeyR KeyT KeyY KeyU KeyI` map to local Pads `0..15`; active Bank adds `bank * 16`.
- MIDI notes `36..51` map to the selected Bank. Other notes/channels are ignored; velocity remains `1..127`.
- `createAcceptanceReport()` emits only contract, Product/Host/Platform/protocol versions, capability booleans, state, Bank/Pad counts, admission/outcome/rejection counts, typed error code, and physical rows fixed to `deferred / unverified`.

- [ ] **Step 1: Write failing input/outcome/lifecycle tests**

```ts
controller.keyDown({code: 'KeyA', repeat: false, target: body});
await flushPromises();
expect(session.trigger).toHaveBeenCalledWith({
  slot: 32, velocity: 100, source: 'keyboard',
});
session.emitOutcome({sequence: 7, outcome: 'voice_started', runtimeFrame: 128});
expect(state.pressed.get(32)).toBe('started');
controller.keyUp({code: 'KeyA'});
expect(state.pressed.has(32)).toBe(false);
```

Add Pointer correlation, compatibility-mouse suppression, key repeat rejection, editable-target rejection, MIDI permission rejection, note-on velocity zero as release, blur/visibility clear, 16 simultaneous admissions/outcomes, capacity outcome, suspend→activate, reload→ready, restart-required→new session→Project reopen→ready, and no automatic activation.

- [ ] **Step 2: Run RED**

```bash
npm --prefix apps/creator-web test -- --run \
  test/input_controller.test.ts test/audio_lifecycle.test.tsx \
  test/acceptance_report.test.ts
```

Expected: FAIL because the input controller/report do not exist.

- [ ] **Step 3: Implement admission/outcome-driven UI and recovery**

On gesture, set `admitted` only after a positive `TriggerAdmission`. Promote to `started` or `capacity` only for the matching sequence. Pointer/key/note release clears the visual state; a late outcome for a released gesture updates counts but does not re-press the Pad.

On `HOST_RESTART_REQUIRED`, close the old session, construct one new session, rerun preflight/list/open/inspect/reload for the retained Project ID, and stop at `audio-suspended`. The Activate button is the only transition back to running.

- [ ] **Step 4: Run GREEN**

```bash
npm --prefix apps/creator-web test -- --run
node --test packages/web-runtime-platform/test/input_adapters.test.mjs
npm --prefix apps/creator-web run build
```

Expected: unit/component tests PASS; every Bank has 16 stable addresses; 16+16 burst counts match; lifecycle never auto-activates.

- [ ] **Step 5: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web packages/web-runtime-platform/web/input_adapters.mjs \
  packages/web-runtime-platform/test/input_adapters.test.mjs
git diff --cached --check
git commit -m "feat(creator): connect playable web runtime"
```

### Task 10: Add deterministic Creator packaging, browser Proof, and CI

**Files:**

- Create: `apps/creator-web/tools/package.py`
- Create: `apps/creator-web/test/package_test.py`
- Create: `apps/creator-web/test/server_test.py`
- Create: `scripts/creator-web.sh`
- Create: `tests/platform/web/creator/creator_web_browser.spec.mjs`
- Create: `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- Create: `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- Modify: `apps/web-runtime-host/tools/server.py`
- Create: `tools/web-runtime/serve_distribution.py`
- Modify: `scripts/web-runtime-host.sh`
- Modify: `apps/web-runtime-host/test/server_test.py`
- Modify: `tests/platform/web/playwright.config.mjs`
- Modify: `.github/workflows/ci.yml`
- Modify: `.gitignore`

**Interfaces:**

- `scripts/creator-web.sh` supports exactly `configure`, `build`, `test`, `proof`, `package`, `serve --port PORT`, and `clean`.
- Creator package contract is `lmdj.creator-web.distribution.v1`; manifest includes Product Build, Creator Host, Platform, compatible diagnostic Host, private protocol, heap/resource limits, Emscripten identity, and exact hashed asset inventory.
- Shared server binds only `127.0.0.1`, serves one validated root, rejects traversal/symlinks, sends COOP/COEP/CORP/CSP and exact Wasm MIME, and distinguishes no-store identity files from immutable hashed assets.

- [ ] **Step 1: Write failing package/server/Playwright tests**

Browser Proof must use visible controls only:

```js
await page.getByRole('button', {name: 'Import .lmdj'}).click();
await fileChooser.setFiles(bundleFixture);
await expect(page.getByText(shortProjectId)).toBeVisible();
await page.getByRole('button', {name: 'Activate audio'}).click();
await expect(page.getByTestId('audio-state')).toHaveText('running');
for (const bank of ['A', 'B', 'C', 'D']) {
  await page.getByRole('button', {name: `Bank ${bank}`}).click();
  await expect(page.getAllByRole('button', {name: /Pad/})).toHaveCount(16);
}
```

The tests must reject `page.evaluate()` calls into Runtime/Bridge for the positive journey.
They select each Bank and activate every visible Pad once, then assert 64 unique
flat-slot admissions, 64 matching outcomes, zero rejection, and final Host
state `running`. A separate synchronous Bank-A burst asserts 16 admissions and
16 outcomes. Synthetic Web MIDI proves notes `36..51`, permission rejection,
and listener cleanup.

`creator_web_accessibility.spec.mjs` runs at `768×1024`, `1024×768`, and
`1440×900`, asserts no workspace overflow, 16 visible `44×44` or larger Pads,
stable focus names/order, disabled future modes outside the tab sequence, and
captures the Project-empty and Project-ready screenshots only after behavior
assertions pass. It also rejects `innerHTML`, remote URLs, source maps, test
fixtures, undeclared files, and any runtime asset outside the manifest.

- [ ] **Step 2: Run RED**

```bash
python3 apps/creator-web/test/package_test.py
python3 apps/creator-web/test/server_test.py
npm --prefix tests/platform/web test -- --project=chromium \
  creator/creator_web_browser.spec.mjs
```

Expected: FAIL because package/script/server/specs are absent.

- [ ] **Step 3: Implement build/package/server entrypoints**

`configure` validates emsdk, Node 22, Creator lockfile, and Playwright. `build` produces the shared Emscripten Runtime plus Vite UI. `package` refuses a dirty worktree and atomically writes `build/web/creator/dist`. `proof` generates a valid Project with Core, packs it twice, compares bundle bytes, builds Creator twice from clean roots, compares both distributions, owns an ephemeral server, and runs all tracked Creator specs in Chromium plus the WebKit capability boundary.

- [ ] **Step 4: Add the CI lane**

Add `creator-web` after Web toolchain and Core prerequisites. It installs the locked emsdk, `npm ci` in both `apps/creator-web` and `tests/platform/web`, installs Chromium/WebKit, and runs only:

```bash
scripts/creator-web.sh proof
```

No proof command performs network fetches.

- [ ] **Step 5: Run focused packaging/build GREEN before clean-source Proof**

```bash
scripts/creator-web.sh configure
scripts/creator-web.sh test
scripts/creator-web.sh build
python3 apps/creator-web/test/package_test.py
python3 apps/creator-web/test/server_test.py
node --test packages/web-runtime-platform/test/*.test.mjs
```

Expected: Creator tests/build and isolated package/server determinism tests PASS, including unsafe clean-root, symlink, traversal, headers, inventory, and dirty-source rejection. `scripts/creator-web.sh proof` intentionally waits for the clean committed source boundary in Task 13 because production packaging rejects a dirty source tree.

- [ ] **Step 6: Run Portal gate and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web apps/web-runtime-host/tools/server.py \
  apps/web-runtime-host/test/server_test.py tools/web-runtime \
  scripts/creator-web.sh scripts/web-runtime-host.sh \
  tests/platform/web .github/workflows/ci.yml .gitignore
git diff --cached --check
git commit -m "test(creator): add packaged web proof"
```

### Task 11: Integrate versions, Product Assembly, and Portal current truth

**Files:**

- Create: `packages/web-runtime-platform/module.json`
- Create: `apps/creator-web/module.json`
- Modify: `packages/project-io/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/web-runtime-host/CMakeLists.txt`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/native-test-host/module.json`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/CMakeLists.txt`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Regenerate: `products/lmdj/assembly.lock.json`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `tests/conformance/module_graph_test.py`
- Modify: `tests/core/facade/application_test.cpp`
- Modify exact dependency assertions in: `tests/host/cli_test.py`, `tests/host/mcp_stdio_test.py`, `tests/host/native_host_source_boundary_test.py`
- Create: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Create: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Create: `apps/architecture-portal/docs/contracts/project-bundle.mdx`
- Create: `apps/architecture-portal/diagrams/web-runtime-platform.architecture.json`
- Modify: `apps/architecture-portal/diagrams/application-facade.architecture.json`
- Modify: `apps/architecture-portal/diagrams/project-io.architecture.json`
- Modify: `apps/architecture-portal/diagrams/lmdj-core.architecture.json`
- Modify: `apps/architecture-portal/diagrams/lmdj-product.architecture.json`
- Generate: `apps/architecture-portal/static/diagrams/web-runtime-platform.html`
- Generate: `apps/architecture-portal/static/diagrams/web-runtime-platform.svg`
- Regenerate the matching HTML/SVG outputs for the four modified diagrams.
- Modify: `apps/architecture-portal/docs/overview/index.mdx`
- Modify: `apps/architecture-portal/docs/core/overview.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-io.mdx`
- Modify: `apps/architecture-portal/docs/hosts/overview.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/platform/input.mdx`
- Modify: `apps/architecture-portal/docs/platform/storage.mdx`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/sidebars.ts`
- Modify: `apps/architecture-portal/scripts/check-build.mjs`
- Modify: `apps/architecture-portal/test/build-check.test.mjs`
- Modify: `apps/architecture-portal/test/content-inventory.test.mjs`
- Modify: `apps/architecture-portal/test/diagram.test.mjs`
- Modify: `apps/architecture-portal/test/snapshot-provenance.test.mjs`
- Modify: `apps/architecture-portal/test/version-docs.test.mjs`
- Modify: `products/lmdj/README.md`

**Interfaces:**

- Assembly module order adds `web-runtime-platform 0.1.0` after `application-facade`; Host inventory adds `creator-web 1.0.0` beside `web-runtime-host 1.2.0`; Contract inventory adds `lmdj.project-bundle.v1 1.0.0`.
- Host manifests depend only on `web-runtime-platform 0.1.0`; the Platform depends on `application-facade 1.3.0` and `audio-runtime 0.4.0`.
- Product CMake supplies the shared Runtime target with the exact allowed Host pairs `creator-web 1.0.0` and `web-runtime-host 1.2.0`; the diagnostic app CMake no longer owns Product Build or Host allowlist definitions.
- Portal inventory grows from 34 to 37 current pages and from 9 diagram sources/18 outputs to 10 sources/20 outputs.

- [ ] **Step 1: Verify Build allocation and write failing identity expectations**

```bash
git tag --list 'lmdj-v1.0.16.*'
git log --all -G '"build"[[:space:]]*:[[:space:]]*16' -- products/lmdj/version.json
```

Expected: no allocated `1.0.16.*`. If either command proves prior allocation, stop and revise the plan/spec to the next unused Build.

Update tests first so they expect the exact Version Management table and new Portal inventory, then run:

```bash
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
```

Expected: FAIL on stale manifests/Assembly.

- [ ] **Step 2: Apply all manifest and Assembly identities coherently**

Set Product Build `1.0.16.0`, update every exact dependency, add new Module/Host/Contract inventory, update compiled Assembly, then generate the lock:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
```

- [ ] **Step 3: Update current Portal pages and source diagrams**

Every new Assembly identity has exactly one current page front-matter declaration. The Platform diagram shows Creator and Diagnostic Host entering one Runtime Session, then Facade; Project Bundle is labeled transfer-only and does not point directly to Creator internals.

Generate diagrams with the repository renderer, never hand-edit HTML/SVG:

```bash
npm --prefix apps/architecture-portal run diagrams
```

- [ ] **Step 4: Run identity, Core, Host, Creator, and current-source gates**

```bash
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/module_graph_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
scripts/core.sh proof
scripts/web-runtime-host.sh proof
npm --prefix apps/creator-web test -- --run
npm --prefix apps/creator-web run build
npm --prefix apps/architecture-portal run check:current
```

Expected: identity, Core, diagnostic Host, Creator test/build, and current-source gates PASS. Creator packaged Proof waits for the clean committed tree in Task 13. Full Portal release-doc check is expected to remain red only because `1.0.16.0` has not yet been frozen.

- [ ] **Step 5: Commit the clean current-truth source boundary**

```bash
git add packages/web-runtime-platform/module.json \
  packages/project-io/module.json packages/application-facade/module.json \
  apps/creator-web/module.json apps/web-runtime-host/module.json \
  apps/web-runtime-host/CMakeLists.txt \
  apps/core-cli/module.json apps/core-mcp/module.json \
  apps/native-test-host/module.json products/lmdj/version.json \
  products/lmdj/assembly.json products/lmdj/assembly.lock.json \
  products/lmdj/CMakeLists.txt products/lmdj/src/compiled_assembly.cpp \
  products/lmdj/README.md \
  tests/build/version_test.py tests/conformance/version_lock_test.py \
  tests/conformance/module_graph_test.py tests/core/facade/application_test.cpp \
  tests/host/cli_test.py tests/host/mcp_stdio_test.py \
  tests/host/native_host_source_boundary_test.py \
  apps/architecture-portal/docs apps/architecture-portal/diagrams \
  apps/architecture-portal/static/diagrams apps/architecture-portal/sidebars.ts \
  apps/architecture-portal/scripts/check-build.mjs \
  apps/architecture-portal/test/build-check.test.mjs \
  apps/architecture-portal/test/content-inventory.test.mjs \
  apps/architecture-portal/test/diagram.test.mjs \
  apps/architecture-portal/test/snapshot-provenance.test.mjs \
  apps/architecture-portal/test/version-docs.test.mjs
git diff --cached --check
git commit -m "feat(product): assemble stage 7 creator editor"
```

Confirm the worktree is clean before Task 12.

### Task 12: Freeze the immutable `1.0.16.0 · canary` Portal snapshot

**Files:**

- Generate: `apps/architecture-portal/versioned_docs/version-1.0.16.0/**`
- Generate: `apps/architecture-portal/versioned_sidebars/version-1.0.16.0-sidebars.json`
- Generate: `apps/architecture-portal/versioned_metadata/version-1.0.16.0.json`
- Generate: `apps/architecture-portal/static/versions/1.0.16.0/diagrams/**`
- Modify generated version registry files required by `version-docs.mjs`

**Interfaces:**

- The snapshot source revision is exactly the clean Task 11 commit.
- Snapshot metadata schema 2 records 37 source docs, one sidebar, 10 diagram IDs/20 outputs, Product/Assembly facts, canonical source commit/tree/time, projection hashes, and `canary`.

- [ ] **Step 1: Prove the freeze preconditions**

```bash
test -z "$(git status --porcelain)"
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
test ! -e apps/architecture-portal/versioned_docs/version-1.0.16.0
```

Expected: clean source, exact `1.0.16.0`, no existing snapshot.

- [ ] **Step 2: Freeze once and run the full Portal gate**

```bash
scripts/architecture-portal.sh version 1.0.16.0 canary
scripts/architecture-portal.sh check
```

Expected: freeze succeeds once; full check proves current truth plus immutable snapshot provenance, 37 pages, and 10 diagram sources/20 outputs.

- [ ] **Step 3: Commit only generated snapshot state**

```bash
git add apps/architecture-portal/versioned_docs/version-1.0.16.0 \
  apps/architecture-portal/versioned_sidebars/version-1.0.16.0-sidebars.json \
  apps/architecture-portal/versioned_metadata/version-1.0.16.0.json \
  apps/architecture-portal/static/versions/1.0.16.0 \
  apps/architecture-portal/versions.json
git diff --cached --check
git commit -m "docs(product): freeze 1.0.16.0 canary architecture snapshot"
```

If the generator changes a different registry path, stage that exact generated file after inspecting it; do not stage build output or node_modules.

### Task 13: Record automated acceptance and run the final clean-source audit

**Files:**

- Create: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`

**Interfaces:**

- Acceptance separates local automated Proof, GitHub CI, merge state, manual listening, and five physical rows.
- Unknown evidence is written as `pending`, `not run`, or `deferred / unverified`; it is never inferred from a different gate.

- [ ] **Step 1: Run all clean-source automated gates and capture exact facts**

```bash
test -z "$(git status --porcelain)"
scripts/core.sh proof
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
```

Expected: all six commands PASS. Record command, timestamp, Git SHA, counts, browser projects, package digests, and any explicit WebKit limitation from actual output only.

- [ ] **Step 2: Write the evidence document without upgrading external state**

The five physical rows remain exactly:

```markdown
| macOS Safari Pointer | deferred / unverified |
| macOS Chrome Pointer | deferred / unverified |
| macOS Chrome physical MIDI | deferred / unverified |
| iPadOS Safari Touch | deferred / unverified |
| iPadOS Safari lifecycle | deferred / unverified |
```

GitHub CI is `not run` until a pushed PR produces current checks. Merge, tag, deploy, and promotion are `not authorized`.

- [ ] **Step 3: Run docs gate and commit evidence**

```bash
scripts/architecture-portal.sh check
git add docs/quality/2026-08-07-stage7-creator-editor-acceptance.md \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx \
  apps/architecture-portal/docs/hosts/creator-web.mdx
git diff --cached --check
git commit -m "docs(quality): record stage 7 creator proof"
```

- [ ] **Step 4: Re-run final proof from the committed evidence tree**

```bash
test -z "$(git status --porcelain)"
scripts/core.sh proof
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
scripts/architecture-portal.sh check
git status --short --branch
```

Expected: all Proof gates PASS and the feature worktree is clean.

### Task 14: Perform manual canary acceptance without changing physical-row claims

**Files:**

- Modify after actual run: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`

**Interfaces:**

- Consumes a clean packaged Creator served by `scripts/creator-web.sh serve --port 4175`.
- Produces a locally exported `lmdj.creator-web.acceptance.v1` JSON report and a human PASS/FAIL decision; it does not promote any physical row unless that row's exact device/input/browser procedure was performed.

- [ ] **Step 1: Start the owned package server**

```bash
scripts/creator-web.sh build
scripts/creator-web.sh serve --port 4175
```

Expected: server reports `http://127.0.0.1:4175/` and serves the validated distribution with cross-origin isolation.

- [ ] **Step 2: Run the visible user journey**

In the browser: import the generated `.lmdj` fixture; verify short Project ID, revision, BPM, `Key —`, Asset/Pad occupancy; activate audio; play all 16 Bank A Pads by Pointer and Keyboard; select Banks B/C/D and sample all addresses; enable MIDI only when a device is intentionally under test; suspend→activate; reload→reopen→activate; export the acceptance report.

Expected: correct sounds/addresses, no missed or duplicate admissions/outcomes, no stuck visual state, no automatic audio, no Project loss, and report counts match the visible run.

- [ ] **Step 3: Record the actual manual result and commit separately**

Update only the manual canary section and report digest. Keep unperformed physical rows `deferred / unverified`, then run:

```bash
scripts/architecture-portal.sh check
git add docs/quality/2026-08-07-stage7-creator-editor-acceptance.md
git diff --cached --check
git commit -m "docs(quality): record stage 7 manual canary"
```

## Requirement-to-Task Coverage

| Approved requirement | Evidence Task |
| --- | --- |
| Independent Creator Host and shared Platform | 4, 5, 7, 11 |
| Browser-local discovery and `.lmdj` import | 1, 2, 3, 6, 8 |
| Bounded/path-safe/atomic/idempotent transfer | 1, 2, 5R1, 6, 10 |
| Full workspace, Project-only active, future modes disabled | 7, 8, 10 |
| 4 Banks / 64 stable Slots | 7, 9, 10, 14 |
| Pointer/Keyboard/MIDI one Trigger path | 5, 9, 10 |
| User-gesture audio, suspend, reload, restart recovery | 5, 9, 10, 14 |
| Desktop/Tablet accessibility and responsive behavior | 7, 8, 9, 10 |
| Privacy/security/cleanup | 1, 2, 5, 6, 9, 10 |
| Deterministic package and clean Chromium/WebKit boundary Proof | 10, 13 |
| Core and diagnostic Host regressions | 4, 5, 6, 10, 11, 13 |
| Versions, Assembly, current docs, diagrams, immutable snapshot | 11, 12 |
| Manual canary report and honest physical evidence | 13, 14 |
| No Stage 8–10/PWA/cloud/deploy/promotion scope | Global Constraints, 7–14 |

## Pull Request and Completion Boundary

After Task 14, inspect every commit/file and use `superpowers:requesting-code-review` before requesting push authorization. A Stage 7 PR must declare the Documentation Impact block above, depend on merged PR #94, and require Core CI, Web Runtime Host, Creator Web, and Architecture Portal checks.

Local commits do not authorize push or PR. A green pushed PR does not authorize merge. Squash merge does not authorize tag, Release, deployment, or Channel promotion. Stage 7 is complete only after the approved PR is squash-merged, required checks are green on current code, merged `main` reruns Core/Web Host/Creator/Portal Proof, manual canary is recorded, and the five unperformed physical rows remain accurately deferred.
