# LMDJ Stage 6 Formal Web Runtime Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Product Build `1.0.12.0 · canary` with a formal product-neutral Web Runtime Host that opens Project Truth through Application Facade, persists it in OPFS, renders the shared C++ Realtime Engine in a Wasm AudioWorklet, captures Takes, and passes clean-distribution Chromium Proof without claiming the five deferred physical rows.

**Architecture:** One Emscripten shared-memory program is loaded on the browser main thread and runs its control `main()` on the `-sPROXY_TO_PTHREAD` worker. That Control Worker owns Application Facade, the Project writer lease, OPFS-backed Project I/O, immutable Runtime Snapshot and Sample Bank preparation, outcome drain, and Capture drain; the main thread owns only activation, DOM input, lifecycle observation, and request transport. Emscripten's Wasm AudioWorklet calls the existing `RealtimeEngine::render()` against the same fixed 512 MiB memory. Native and Web persistence share ProjectStore/TakeJournal transaction logic above a semantic `ProjectStoragePlatform` boundary.

**Tech Stack:** C++20, CMake 3.24+, CTest, Emscripten/emsdk `6.0.5`, WasmFS OPFS backend, pthreads, Wasm Workers, Wasm AudioWorklets, JavaScript ES modules, Node.js 22, Playwright `1.62.1`, Python 3.11, OPFS, SharedArrayBuffer, Web Audio, Web MIDI, existing LMDJ Foundation/Domain/Project I/O/Cooker/Audio Runtime/Application Facade/Assembly tooling.

## Global Constraints

- Execute only after this approved spec and plan are present on `origin/main`. Create `feat/formal-web-runtime-host` from the latest `origin/main` in `/Users/endaye/Projects/lmdj/.worktrees/formal-web-runtime-host`; never implement on `main` or on the retained design worktree.
- The authoritative design is `docs/superpowers/specs/2026-08-03-lmdj-formal-web-runtime-host-design.md`. Any failure of B1 through B6 returns to architecture review; implementation must not weaken a locked resolution.
- Task 0 is a committed pre-Product gate. Do not add or modify source below `apps/`, `packages/`, or `products/` until Task 0 passes in Chromium with the exact toolchain and required flag set.
- The formal Host uses Application Facade for Project-facing operations. It must not parse Project bundles, manifests, transaction files, Take journals, Assembly internals, or Artifact payload format.
- The Web Host and Product Assembly must not declare a direct `project-io` dependency. Product-specific Provider catalog wiring remains in `products/lmdj`.
- The Web build uses one shared, non-growing 536,870,912-byte memory. No fallback may grow memory, resample, drop Pads, shorten audio, switch to ScriptProcessor, use a JavaScript sampler, use IndexedDB Project Truth, or copy a bundle through MEMFS.
- Runtime audio is exactly 48,000 Hz, two non-interleaved float32 output channels, and exactly 128 frames per accepted Worklet callback. Any other realized rate or quantum is `UNSUPPORTED_WEB_RUNTIME`.
- Audio callback code may not allocate, deallocate, lock, perform I/O, call Facade, parse JSON, log, throw, wait, proxy to the main thread, or construct/reclaim Banks.
- Realtime capacities remain Queue 1,024, Voices 128, Bank Slots 4, Capture Ring 4,096, and Trigger Outcome Ring 4,096. Every dequeued Trigger produces exactly one `voice_started` or `voice_capacity` outcome.
- Project writer lease identity is SHA-256 of the normalized virtual Project path and is stored outside Project Truth. A competing writer returns immediately with Host-local `PROJECT_BUSY`.
- Web limits are exact: import 1,048,576 bytes; 240,000 decoded frames per Pad; 67,108,864 float PCM bytes per Bank; 134,217,728 float PCM bytes across all live/pending/retiring Banks.
- The private Host protocol remains same-build distribution transport with `protocol_version: 1`; no schema is added below `contracts/`.
- Capture operation names are only `take.begin`, `take.stop`, and `take.commit`. `record.*` aliases are forbidden in the Web Host.
- Existing public CLI, MCP, JSON Facade, C ABI, `lmdj.project.v1`, and Provider Contracts remain compatible. Retired `lmdj.patch.v1` and `lmdj.materials.v1` remain forbidden.
- The Web Runtime Lab remains independent experimental evidence tooling. Do not import its JavaScript sampler/worklet into the formal Host and do not rename or remove the Lab.
- Playwright WebKit automation is capability smoke only. It is never described as physical Safari evidence.
- The five physical rows remain `deferred / unverified`; they do not block canary implementation/merge/tag, but they block physical-pass, `beta`, and `stable` claims.
- Each Task is one reviewable Conventional Commit. Before every commit, run its stated checks, stage only its declared files, inspect `git diff --cached --name-only`, run `git diff --cached --check`, inspect the staged diff, commit, inspect `git show --stat --oneline HEAD`, and confirm `git status --short` contains no Task-related residue.
- This plan authorizes local implementation commits only. Push, PR, squash merge, signed tag, tag push, Release, publication, deployment, and Channel promotion remain separately authorized.

## File Map

### Pre-Product toolchain gate

- `tools/web-runtime/emscripten.lock.json`: exact emsdk, emsdk Git, emscripten-releases, flags, heap, Node, and Playwright identities.
- `tools/web-runtime/verify_emscripten.py`: fail-closed validation of the active SDK and build manifest identity.
- `tests/platform/web/package.json`, `tests/platform/web/package-lock.json`: pinned browser test runner dependency.
- `tests/platform/web/playwright.config.mjs`: Chromium and WebKit project definitions with one CI worker.
- `tests/platform/web/toolchain/`: minimal non-Product shared-memory, Wasm AudioWorklet, WasmFS OPFS, replacement, lease, and no-deadlock fixture.
- `scripts/web-toolchain-conformance.sh`: configure/build/serve/proof entry for Task 0 only.

### Shared Project I/O

- `packages/project-io/include/lmdj/project_io/storage_platform.hpp`: semantic storage obligations, writer lease, and platform factory.
- `packages/project-io/src/native/storage_platform.cpp`: current POSIX guarantees behind the semantic interface.
- `packages/project-io/src/web/storage_platform.cpp`: WasmFS path implementation and typed error conversion.
- `packages/project-io/src/web/library_opfs_storage.js`: OPFS handle, lease, sorted iteration, whole-file replacement, and fault bridge.
- `packages/project-io/src/project_store.cpp`, `packages/project-io/src/take_journal.cpp`: common format, validation, transaction, replay, and recovery logic only.
- `tests/core/project_io/storage_platform_contract_test.cpp`: Native semantic obligation contract.
- `tests/platform/web/project_io/`: Web Store/Journal parity, lease, interruption, restart, and fault conformance.

### Shared runtime and Facade

- `packages/audio-runtime/include/lmdj/audio/runtime_preparation_limits.hpp`: immutable product-neutral preparation limits.
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`, `packages/audio-runtime/src/realtime_engine.cpp`: Trigger Outcome Ring and telemetry.
- `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`, `packages/audio-runtime/src/prepared_sample_bank.cpp`: bounded Bank construction and exact decoded byte accounting.
- `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`, `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`: Emscripten Worklet adapter around `RealtimeEngine::render()`.
- `packages/application-facade/include/lmdj/facade/application.hpp`, `packages/application-facade/src/application.cpp`: opaque writer lease, byte-backed import, limits, and Host-neutral realtime composition.
- Existing Cooker, Project I/O, Facade, Audio, Native Host, stress, and host tests: compatibility and regression coverage.

### Formal Web Runtime Host

- `apps/web-runtime-host/CMakeLists.txt`, `apps/web-runtime-host/module.json`: Emscripten target, source-boundary checks, and Host identity.
- `apps/web-runtime-host/src/control_runtime.hpp`, `apps/web-runtime-host/src/control_runtime.cpp`: Facade/lease/Snapshot/Bank/Engine/Take orchestration on the Control Worker.
- `apps/web-runtime-host/src/bridge.cpp`: bounded exported transport functions and C++ proxying queue.
- `apps/web-runtime-host/src/protocol.mjs`: strict private envelope, deadlines, duplicate IDs, sidecar validation, responses, and notifications.
- `apps/web-runtime-host/src/state_machine.mjs`: exact external lifecycle transitions and failure cleanup.
- `apps/web-runtime-host/src/preflight.mjs`: ordered mandatory capability checks.
- `apps/web-runtime-host/src/input_adapters.mjs`: Pointer, Keyboard, and Web MIDI normalization to one flat-slot Trigger route.
- `apps/web-runtime-host/src/main.mjs`: manifest validation, user activation, DOM wiring, lifecycle observation, and transport.
- `apps/web-runtime-host/index.html`, `apps/web-runtime-host/styles.css`: minimal diagnostic page with no inline or remote dependency.
- `apps/web-runtime-host/test/`: Node unit, C++ host, source-boundary, protocol, lifecycle, input, server, manifest, privacy, and distribution tests.
- `apps/web-runtime-host/tools/package.py`, `apps/web-runtime-host/tools/server.py`: deterministic package builder and proof-only isolated server.
- `scripts/web-runtime-host.sh`: stable configure/build/test/proof/serve/clean entry.

### Product, Proof, and CI

- `products/lmdj/CMakeLists.txt`, `products/lmdj/assembly.json`, `products/lmdj/assembly.lock.json`, `products/lmdj/version.json`, `products/lmdj/src/compiled_assembly.cpp`: Product wiring and exact `1.0.12.0` identity.
- Affected `module.json`, MCP Python identity, version tests, READMEs, Native Host identity, and Proof output: exact dependency propagation.
- `.github/workflows/ci.yml`: formal Web Host lane while retaining Lab, macOS, Ubuntu, ASan, and Coverage.
- `.github/workflows/core-nightly.yml`: retained TSan and Stress lanes.
- `tests/host/web_runtime_host_browser.spec.mjs`: Chromium full journey and WebKit capability smoke.
- `docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md`: automated evidence and explicitly deferred physical matrix.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Identity | Baseline | Target | API | Reason |
| --- | --- | --- | --- | --- |
| Product Build | `1.0.11.0` | `1.0.12.0` | n/a | Adds an Assembly-listed Formal Web Runtime Host. |
| `web-runtime-host` | absent | `1.0.0` | 1 | First formal same-build private Host surface. |
| `project-io` | `0.3.0` | `0.4.0` | stays 1 | Adds compatible semantic storage obligations, writer lease, byte import, and Web platform. |
| `audio-runtime` | `0.3.0` | `0.4.0` | stays 1 | Adds compatible runtime limits, Outcome Ring, byte accounting, and Web Worklet adapter. |
| `application-facade` | `1.1.0` | `1.2.0` | stays 2 | Adds compatible writer lease, byte import, and bounded realtime Host methods. |
| `core-cli` | `1.0.2` | `1.0.3` | stays 2 | Exact Facade dependency update only. |
| `core-mcp` | `1.0.2` | `1.0.3` | stays 2 | Exact Facade and Python package identity update only. |
| `native-test-host` | `1.0.0` | `1.0.1` | stays 1 | Exact Facade/Audio dependency update and Outcome drain. |
| `project-cooker` | `0.2.0` | unchanged | stays 1 | No public Cooker API change; limits are enforced by Facade and Audio Runtime. |
| Contracts | current | unchanged | unchanged | Private same-build transport creates no public Contract. |
| Providers / Models | current | unchanged | unchanged | No Capability, Provider, or model behavior change. |

- Update every exact dependency and every source assertion in one coherent version-integration Task after functional Tasks pass.
- Regenerate `products/lmdj/assembly.lock.json` only with `python3 scripts/version.py lock`; never hand-edit the generated lock.
- Candidate display is `1.0.12.0 · canary · g<short-sha>`.
- Rollback reuses immutable `1.0.11.0`; no tag is moved and no version is reused.
- The future Product tag is `lmdj-v1.0.12.0`, signed and annotated only after separate post-merge approval.

---

### Task 0: Prove the exact Web toolchain topology before Product source

**Files:**

- Create: `tools/web-runtime/emscripten.lock.json`
- Create: `tools/web-runtime/verify_emscripten.py`
- Create: `tests/platform/web/package.json`
- Create: `tests/platform/web/package-lock.json`
- Create: `tests/platform/web/playwright.config.mjs`
- Create: `tests/platform/web/toolchain/CMakeLists.txt`
- Create: `tests/platform/web/toolchain/probe.cpp`
- Create: `tests/platform/web/toolchain/probe-pre.js`
- Create: `tests/platform/web/toolchain/probe.html`
- Create: `tests/platform/web/toolchain/server.py`
- Create: `tests/platform/web/toolchain/toolchain_conformance.spec.mjs`
- Create: `tests/platform/web/toolchain/toolchain_identity_test.py`
- Create: `scripts/web-toolchain-conformance.sh`
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`

**Locked fixture identity:**

```json
{
  "emsdk_tag": "6.0.5",
  "emsdk_revision": "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190",
  "emscripten_releases_revision": "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
  "initial_memory": 536870912,
  "allow_memory_growth": false,
  "playwright": "1.62.1"
}
```

- [ ] **Step 1: Add failing identity and flag tests**

Write `toolchain_identity_test.py` to reject missing keys, wrong revisions, a heap other than 536,870,912, growth enabled, or absence of any required flag. The complete required linker flag array is:

```text
-pthread
-sWASMFS
-sAUDIO_WORKLET
-sWASM_WORKERS
-sPROXY_TO_PTHREAD
-sINITIAL_MEMORY=536870912
-sALLOW_MEMORY_GROWTH=0
```

Add `-sASYNCIFY=1` and this exact non-audio bridge list:

```text
-sASYNCIFY_IMPORTS=['lmdj_opfs_acquire_writer','lmdj_opfs_replace_complete','lmdj_opfs_list_names']
```

The test rejects Asyncify reachability from the audio callback object. Define the browser test package exactly as Node 22 plus `@playwright/test: 1.62.1`, with `"test": "playwright test"`; generate and track its lock with `npm install --package-lock-only --ignore-scripts`. Add `build/web/`, `tests/platform/web/test-results/`, and `tests/platform/web/playwright-report/` to `.gitignore`.

- [ ] **Step 2: Run RED**

```bash
python3 tests/platform/web/toolchain/toolchain_identity_test.py
```

Expected: fail because the lock, verifier, and fixture do not exist.

- [ ] **Step 3: Implement fail-closed SDK verification and fixture build**

`verify_emscripten.py` must check the lock shape, `git -C "$EMSDK" rev-parse HEAD`, `emscripten-releases-tags.json["releases"]["6.0.5"]`, that `command -v emcc` resolves below `$EMSDK/upstream/emscripten`, and that `emcc --version` reports `6.0.5`. It emits canonical JSON to `build/web/toolchain/toolchain-identity.json` and exits 2 on any mismatch.

Build the probe with `wasmfs_create_opfs_backend()` mounted below `/opfs`, one shared atomic word, and the documented Worklet callback signature:

```cpp
bool process_probe(int num_inputs,
                   const AudioSampleFrame* inputs,
                   int num_outputs,
                   AudioSampleFrame* outputs,
                   int num_params,
                   const AudioParamFrame* params,
                   void* user_data);
```

The callback stores `outputs[0].samplesPerChannel`, copies the shared atomic marker to an output sample, and returns `true`. It performs no other work.

- [ ] **Step 4: Implement the seven browser conformance assertions**

The Playwright test must prove:

1. exact identity/flags load successfully;
2. the Control pthread writes shared memory and the Worklet observes it;
3. the callback reports exactly 128 frames and two channels;
4. `wasmfs_create_opfs_backend()` supports synchronous C++ read/write/flush from the Control pthread;
5. direct OPFS lease, unsigned-UTF-8 sorted iteration, successful-close replacement, and interruption/restart old-or-new cases pass;
6. 1,000 control probes complete while the Worklet renders with no main-thread proxy deadlock;
7. Chromium passes; WebKit passes or returns an ordered missing-capability record and never a false pass.

The interruption matrix uses named fault points `before_write`, `during_write`, `before_close`, `after_close`, and `before_cleanup` and asserts the recovered value is exactly `old` or `new`, never a prefix or empty file.

- [ ] **Step 5: Add the CI pre-Product lane**

CI clones `emsdk` into `build/toolchains/emsdk`, checks out the locked revision, installs and activates `6.0.5`, runs `npm ci` in `tests/platform/web`, installs Chromium and WebKit before Proof, then runs:

```bash
scripts/web-toolchain-conformance.sh proof
```

The `proof` subcommand itself must perform no network fetch.

- [ ] **Step 6: Run GREEN**

```bash
python3 tests/platform/web/toolchain/toolchain_identity_test.py
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/toolchain/toolchain_conformance.spec.mjs
npm --prefix tests/platform/web test -- --project=webkit \
  tests/platform/web/toolchain/toolchain_conformance.spec.mjs
scripts/web-toolchain-conformance.sh proof
```

Expected: identity PASS; Chromium full PASS; WebKit PASS or explicit capability limitation; no Product source diff exists.

- [ ] **Step 7: Commit Task 0**

```bash
git commit -m "test(web): prove formal runtime toolchain topology"
```

If Chromium does not pass every mandatory assertion, stop. Do not begin Task 1.

### Task 1: Extract semantic Project storage while preserving Native behavior

**Files:**

- Create: `packages/project-io/include/lmdj/project_io/storage_platform.hpp`
- Create: `packages/project-io/src/native/storage_platform.cpp`
- Create: `tests/core/project_io/storage_platform_contract_test.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/include/lmdj/project_io/take_journal.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `packages/project-io/src/take_journal.cpp`
- Modify: `packages/project-io/CMakeLists.txt`
- Modify: `tests/core/project_io/project_store_test.cpp`
- Modify: `tests/core/project_io/take_journal_test.cpp`
- Modify: `tests/core/project_io/fault_matrix_test.cpp`
- Modify: `tests/core/facade/c_api_test.cpp`
- Modify: `CMakeLists.txt`

**Public semantic boundary:**

```cpp
class ProjectWriterLease {
 public:
  virtual ~ProjectWriterLease() = default;
};

class ProjectStoragePlatform {
 public:
  virtual ~ProjectStoragePlatform() = default;
  virtual foundation::Result<std::unique_ptr<ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& project_path) = 0;
  virtual foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) = 0;
  virtual foundation::Result<bool> exists(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) = 0;
  virtual foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) = 0;
  virtual foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> bytes) = 0;
  virtual foundation::Result<void> remove(
      const std::filesystem::path& path) = 0;
  virtual foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& root) const = 0;
};
```

- [ ] **Step 1: Write failing Native storage contract tests**

Test exclusive writer acquisition, immutable create collision, complete
read/write, repair-aware durable append, atomic replacement, removal,
unsigned-byte sorted regular-file names, symlink rejection, and typed
`io_error` conversion. Durable append coverage must include a clean prefix, a
torn-tail prefix, an arbitrary binary prefix that has no record semantics, an
oversized prefix that fails without mutation, and exactly one file flush.
Re-run every existing fault hook against the default Native platform.

- [ ] **Step 2: Run RED**

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target \
  lmdj_project_store_tests \
  lmdj_take_journal_tests \
  lmdj_project_io_fault_matrix_tests
```

Expected: compilation fails because the semantic interface and contract target do not exist.

- [ ] **Step 3: Move POSIX mechanics below the interface**

Move `flock`, `openat`, `O_DIRECTORY`, `O_NOFOLLOW`, `O_EXCL`, `fcntl`, `fsync`, `rename`, and symlink traversal rejection into `src/native/storage_platform.cpp`. `project_store.cpp` and `take_journal.cpp` retain JSON shape, command identity, revision, transaction naming, checkpoint ordering, replay, and recovery decisions but call semantic methods only.

`replace_complete()` on Native must write an opaque collision-safe sibling,
fsync it, rename it over the destination, and fail closed if syncing the
containing directory fails. For
`append_durable(path, valid_prefix_length, bytes)`, common `TakeJournal` reads
and validates the Journal and computes the byte offset after the last complete
durable record. Native holds the exclusive regular-file lock, rejects a prefix
beyond the current length without mutation, truncates exactly to a shorter
prefix, writes all bytes, and fsyncs exactly once. Native must not parse JSONL,
inspect newlines, or choose the recovery boundary.

Writer acquisition is reentrant only for the same normalized path on the same `ProjectStoragePlatform` instance. The outer Facade lease owns the platform handle for the Project lifetime; nested ProjectStore/TakeJournal operations receive reference-counted operation tokens. A separate platform instance always competes and must not inherit the lease.

- [ ] **Step 4: Add constructor injection without changing default callers**

```cpp
ProjectStore();
explicit ProjectStore(std::shared_ptr<ProjectStoragePlatform> platform);
TakeJournal();
explicit TakeJournal(std::shared_ptr<ProjectStoragePlatform> platform);
```

Application must later pass one shared platform instance to both classes. Existing default construction stays source-compatible.

- [ ] **Step 5: Prove common transaction semantics remain unchanged**

Run the full Native Store, Journal, replay, and fault matrix. Add a test that
injects a deterministic in-memory fake platform and proves the common layer
calls `create_immutable` for transaction/checkpoint payloads and
`replace_complete` only for published pointers. Use one ordered mutation log
for Store and Journal routing. Prove two `TakeJournal` instances sharing one
platform cannot both act on the same stale durable prefix; common code must
serialize the complete read-boundary-and-append operation per platform without
changing the fail-fast cross-platform writer lease. Recovery removes only
sealed temporary files whose destination matches the generated
`<take-uuid>-<sanitized-reason>(-N)?.json` grammar.

- [ ] **Step 6: Run GREEN**

```bash
cmake --build build/core/dev --target \
  lmdj_project_storage_platform_tests \
  lmdj_project_store_tests \
  lmdj_take_journal_tests \
  lmdj_project_io_fault_matrix_tests \
  lmdj_application_c_api_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^(project_io\.|facade\.c_api$)'
bash tests/build/test_active_tree.sh
scripts/core.sh proof
```

Expected: all selected tests and the complete Headless Core Proof pass; no POSIX
header remains in the common ProjectStore/TakeJournal sources; the C API
contention fixture proves the external fail-fast lease without depending on a
retired in-Project `.lock` file.

- [ ] **Step 7: Commit Task 1**

```bash
git commit -m "refactor(project-io): isolate semantic storage platform"
```

### Task 2: Implement OPFS storage, writer lease, and restart recovery

**Files:**

- Create: `packages/project-io/src/web/storage_platform.cpp`
- Create: `packages/project-io/src/web/library_opfs_storage.js`
- Create: `tests/platform/web/project_io/CMakeLists.txt`
- Create: `tests/platform/web/project_io/project_io_web_test.cpp`
- Create: `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- Create: `tests/platform/web/project_io/project_io_web_faults.mjs`
- Modify: `packages/project-io/CMakeLists.txt`
- Modify: `scripts/web-toolchain-conformance.sh`

**Web realization:**

- normal complete file access is rooted in a WasmFS OPFS backend mounted at `/lmdj-workspace`;
- the lease file is `/lmdj-workspace/.lmdj-host/leases/<sha256(normalized-project-path)>.lock`;
- the lease owns an exclusive `FileSystemSyncAccessHandle` until the opaque C++ lease object is destroyed;
- `replace_complete` uses `createWritable({keepExistingData: false})`, complete write, and successful `close()` as the publication point;
- directory iteration collects every name and sorts by unsigned UTF-8 bytes before returning to C++.

- [ ] **Step 1: Write failing Web parity and interruption tests**

Port meaningful Project Store, Take Journal, replay, recovery, and fault cases to `project_io_web_test.cpp`. Browser tests must add competing-tab lease, Worker termination/reacquire, and the five replacement fault points. Assert `storage_condition: "project_busy"` on lease contention; the Host-local code mapping comes later.

- [ ] **Step 2: Run RED**

```bash
scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs
```

Expected: build or browser test fails because the Web platform factory does not exist.

- [ ] **Step 3: Implement the WasmFS and OPFS bridge**

Expose only semantic imports such as:

```javascript
lmdj_opfs_acquire_writer: (...args) => Asyncify.handleAsync(async () => {}),
lmdj_opfs_replace_complete: (...args) =>
  Asyncify.handleAsync(async () => {}),
lmdj_opfs_list_names: (...args) => Asyncify.handleAsync(async () => {}),
lmdj_opfs_release_writer: (...args) => 0,
```

Reject `QuotaExceededError`, `NotFoundError`, `InvalidStateError`, and `NoModificationAllowedError` through one typed conversion table. Do not expose an OPFS handle, browser path, or DOMException message to Project Truth or diagnostics.

- [ ] **Step 4: Implement old-or-new recovery and deterministic discovery**

Each replacement fault hook terminates the Worker at the named point, restarts the page, opens through common ProjectStore logic, and asserts the exact previous or next revision. Orphan immutable payloads may remain but must be unreachable. Directory barrier is recorded as absent; no test may assert a fake POSIX ordering guarantee.

- [ ] **Step 5: Prove writer lease lifetime and reacquisition**

Open the same normalized Project path in two pages. The first holds the SyncAccessHandle; the second returns immediately. Terminate the first Worker, acquire from the second without deleting or modifying the stable lease file, and compare its file identity before/after.

- [ ] **Step 6: Run GREEN**

```bash
scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs
npm --prefix tests/platform/web test -- --project=webkit \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs
scripts/core.sh test dev full
```

Expected: Chromium full Web Project I/O PASS; WebKit PASS or explicit missing primitive; Native Core remains green.

- [ ] **Step 7: Commit Task 2**

```bash
git commit -m "feat(project-io): add opfs storage platform"
```

### Task 3: Add sequence-addressed Trigger outcomes to Audio Runtime

**Files:**

- Modify: `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `tests/core/audio/realtime_engine_test.cpp`
- Modify: `tests/core/audio/realtime_engine_stress_test.cpp`
- Modify: `apps/native-test-host/src/main.cpp`
- Modify: `tests/host/native_host_test.py`
- Modify: `CMakeLists.txt`

**Public types:**

```cpp
inline constexpr std::size_t kRealtimeTriggerOutcomeCapacity = 4'096;

enum class RuntimeTriggerOutcome : std::uint8_t {
  voice_started,
  voice_capacity,
};

struct RuntimeTriggerOutcomeEvent {
  std::uint64_t sequence;
  RuntimeTriggerOutcome outcome;
  std::uint64_t runtime_frame;
};

struct RuntimeTriggerOutcomeTelemetry {
  std::uint64_t published_outcomes;
  std::uint64_t drained_outcomes;
  std::uint64_t runtime_outcome_drops;
};
```

- [ ] **Step 1: Write failing exact-outcome and 128-frame tests**

Test a free Voice, 128 active Voices followed by one more dequeued Trigger, ordered mixed outcomes, ring capacity/drop telemetry, restart reset, and `render(..., 128)`. For every dequeued sequence assert exactly one outcome and `runtime_frame` equals the render callback's absolute start frame.

- [ ] **Step 2: Run RED**

```bash
cmake --build build/core/dev --target \
  lmdj_realtime_engine_tests lmdj_realtime_engine_stress_tests
```

Expected: compilation fails because outcome types and drain API are absent.

- [ ] **Step 3: Implement the lock-free SPSC outcome path**

Add:

```cpp
std::size_t drain_trigger_outcomes(
    std::span<RuntimeTriggerOutcomeEvent> output) noexcept;
RuntimeTriggerOutcomeTelemetry trigger_outcome_telemetry() const noexcept;
```

Inside the existing dequeue loop, push one event before `continue` on Voice capacity and one after Voice initialization on success. The callback performs no allocation or failure handling beyond incrementing `runtime_outcome_drops`.

- [ ] **Step 4: Keep Native Host behavior compatible and bounded**

Drain outcome batches of 64 before and after each Native Host request without adding new Native protocol operations or fields. Fail Native Host startup/status tests if its outcome-drop telemetry becomes nonzero. Existing Trigger responses remain admission-only.

- [ ] **Step 5: Extend stress invariants**

The producer records admitted sequences, the audio thread renders, and the consumer drains outcomes. After quiescence assert:

```cpp
dequeued_events == published_outcomes + runtime_outcome_drops;
started_voices + voice_drops == dequeued_events;
runtime_outcome_drops == 0;
```

- [ ] **Step 6: Run GREEN**

```bash
cmake --build build/core/dev --target \
  lmdj_realtime_engine_tests \
  lmdj_realtime_engine_stress_tests \
  lmdj_native_host
ctest --test-dir build/core/dev --output-on-failure \
  -R '^(audio\.realtime_engine|audio\.realtime_spsc_stress|host\.native)$'
```

- [ ] **Step 7: Commit Task 3**

```bash
git commit -m "feat(audio): publish realtime trigger outcomes"
```

### Task 4: Add bounded preparation, byte import, and opaque writer lease to Facade

**Files:**

- Create: `packages/audio-runtime/include/lmdj/audio/runtime_preparation_limits.hpp`
- Modify: `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- Modify: `packages/audio-runtime/src/prepared_sample_bank.cpp`
- Modify: `tests/core/audio/prepared_sample_bank_test.cpp`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `tests/core/project_io/project_store_test.cpp`
- Modify: `packages/application-facade/include/lmdj/facade/application.hpp`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `tests/core/facade/application_test.cpp`

**Limits and Facade extensions:**

```cpp
struct RuntimePreparationLimits {
  std::uint64_t maximum_artifact_bytes;
  std::uint64_t maximum_decoded_frames_per_pad;
  std::uint64_t maximum_prepared_bank_bytes;
  std::uint64_t maximum_live_bank_bytes;
};

struct RuntimeSnapshotRequest {
  std::filesystem::path project_path;
  foundation::PatternId pattern_id;
  std::optional<audio::RuntimePreparationLimits> limits = std::nullopt;
};

class RuntimeProjectWriterLease;

struct ArtifactBytesImportRequest {
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  foundation::AssetId asset_id;
  std::string media_type;
  std::span<const std::byte> bytes;
};

foundation::Result<RuntimeProjectWriterLease> acquire_project_writer(
    const std::filesystem::path& project_path);
foundation::Result<domain::AppliedCommand> import_artifact_bytes(
    const ArtifactBytesImportRequest& request);
```

- [ ] **Step 1: Write failing boundary and boundary-plus-one tests**

Cover 1,048,576/1,048,577 Artifact bytes, 240,000/240,001 decoded frames, 67,108,864/67,108,865 Bank bytes, and 134,217,728/134,217,729 live Bank bytes. Assert the prior Bank remains unchanged on every rejection and oversized Projects remain loadable/inspectable.

- [ ] **Step 2: Run RED**

```bash
cmake --build build/core/dev --target \
  lmdj_prepared_sample_bank_tests \
  lmdj_project_store_tests \
  lmdj_application_facade_tests
```

Expected: compilation fails because limits, byte import, and lease APIs do not exist.

- [ ] **Step 3: Enforce limits before the expensive stage**

Facade checks `ArtifactRef::byte_length` before `read_artifact`, validates decoded frame counts before returning the Snapshot, and calculates prospective mono float bytes with overflow-checked `std::uint64_t` arithmetic. `PreparedSampleBank::from_snapshot(snapshot, limits)` reserves only after the prospective Bank fits and exposes:

```cpp
std::uint64_t decoded_pcm_bytes() const noexcept;
```

The unbounded overload remains for Native callers.

- [ ] **Step 4: Add byte-backed import without a Host staging path**

ProjectStore validates and hashes the supplied byte span, writes the immutable Artifact through `ProjectStoragePlatform`, then executes the existing `ImportAsset` transaction. Application exposes the typed method; the public JSON operation list and C ABI remain byte-for-byte unchanged.

- [ ] **Step 5: Wrap the writer lease at the Facade boundary**

`RuntimeProjectWriterLease` is move-only with PImpl, exposes no Project I/O type, path, or browser handle, and releases on destruction. Application shares one storage platform between ProjectStore and TakeJournal. A lease error carries only `storage_condition: "project_busy"` for Host mapping.

- [ ] **Step 6: Run GREEN and compatibility checks**

```bash
cmake --build build/core/dev --target \
  lmdj_prepared_sample_bank_tests \
  lmdj_project_store_tests \
  lmdj_application_facade_tests \
  lmdj_application_c_api_tests \
  lmdj_application_dynamic_load_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^(audio\.prepared_sample_bank|project_io\.project_store|facade\.)'
python3 tests/conformance/module_graph_test.py
```

- [ ] **Step 7: Commit Task 4**

```bash
git commit -m "feat(facade): bound web runtime preparation"
```

### Task 5: Implement the strict private protocol, state machine, preflight, and inputs

**Files:**

- Create: `apps/web-runtime-host/src/protocol.mjs`
- Create: `apps/web-runtime-host/src/state_machine.mjs`
- Create: `apps/web-runtime-host/src/preflight.mjs`
- Create: `apps/web-runtime-host/src/input_adapters.mjs`
- Create: `apps/web-runtime-host/test/protocol.test.mjs`
- Create: `apps/web-runtime-host/test/state_machine.test.mjs`
- Create: `apps/web-runtime-host/test/preflight.test.mjs`
- Create: `apps/web-runtime-host/test/input_adapters.test.mjs`

**Protocol constants:**

```javascript
export const PROTOCOL_VERSION = 1;
export const MAX_ENVELOPE_BYTES = 65_536;
export const MAX_ASSET_BYTES = 1_048_576;
export const DEADLINES_MS = Object.freeze({
  short: 1_000,
  project: 30_000,
  close: 10_000,
});
```

- [ ] **Step 1: Write strict envelope and deadline tests**

Reject malformed UTF-8, non-lowercase UUID, duplicate request ID, wrong version, unknown/extra fields, unknown operation, oversized JSON, wrong state, late reply, sidecar length mismatch, and sidecar SHA mismatch. Assert a timeout terminates the transport and ignores any later mutation response.

- [ ] **Step 2: Write complete state-transition tests**

Exercise every table row from `cold` through `closed`/`failed`, repeated interruption recovery, idempotent suspend, terminal-state immutability, and active-Take sealing on interruption/failure. Assert `closed` never overwrites `failed`.

- [ ] **Step 3: Write input normalization tests**

Pointer tests cover primary activation and compatibility mouse suppression. Keyboard tests cover `code`, repeat, editable focus, and pressed-state cleanup. MIDI tests cover explicit permission, `sysex: false`, Note On velocity zero, velocity preservation, disconnect cleanup, and privacy redaction. All successful inputs call exactly `trigger(flatSlot, velocity)`.

- [ ] **Step 4: Run RED**

```bash
node --test apps/web-runtime-host/test/*.test.mjs
```

Expected: module resolution fails because implementations do not exist.

- [ ] **Step 5: Implement pure deterministic modules**

Keep modules free of global listeners at import time. Inject `crypto`, monotonic clock, timer functions, MIDI access, notification sink, and Trigger sink so Node tests control time and capabilities. The ordered preflight list is exactly:

```text
secureContext, crossOriginIsolated, sharedArrayBuffer, webAssembly,
audioWorklet, opfs, opfsSyncAccessHandle, opfsWritableReplace
```

- [ ] **Step 6: Run GREEN**

```bash
node --test apps/web-runtime-host/test/*.test.mjs
if rg -n 'record\.(begin|stop|commit)|lmdj\.patch\.v1|lmdj\.materials\.v1' \
  apps/web-runtime-host/src; then
  echo "forbidden Web Host surface found" >&2
  exit 1
fi
```

- [ ] **Step 7: Commit Task 5**

```bash
git commit -m "feat(web): define formal host control protocol"
```

### Task 6: Build the Control Worker runtime through Application Facade

**Files:**

- Create: `apps/web-runtime-host/CMakeLists.txt`
- Create: `apps/web-runtime-host/src/control_runtime.hpp`
- Create: `apps/web-runtime-host/src/control_runtime.cpp`
- Create: `apps/web-runtime-host/src/bridge.cpp`
- Create: `apps/web-runtime-host/test/control_runtime_test.cpp`
- Create: `apps/web-runtime-host/test/web_host_source_boundary_test.py`
- Modify: `CMakeLists.txt`
- Modify: `products/lmdj/CMakeLists.txt`

**Control API:**

```cpp
class ControlRuntime final {
 public:
  static foundation::Result<std::unique_ptr<ControlRuntime>> create(
      std::filesystem::path workspace_root,
      facade::Application application,
      audio::RuntimePreparationLimits limits);
  nlohmann::json dispatch(std::string_view operation,
                          const nlohmann::json& payload,
                          std::span<const std::byte> sidecar);
  std::vector<audio::RuntimeTriggerOutcomeEvent> drain_outcomes();
  foundation::Result<void> drain_capture();
  void fail_and_seal(std::string_view cause) noexcept;
  audio::RealtimeEngine& engine() noexcept;
};
```

- [ ] **Step 1: Write failing C++ orchestration and source-boundary tests**

Use a temporary Native workspace and deterministic `render(..., 128)` driver. Cover Project create/open/inspect, byte import, pad assign, Snapshot publish/reject with prior Bank retention, Trigger admission/outcome, Take begin/stop/commit, recoverable list, and close. The boundary test rejects Project parsers, POSIX/OPFS calls, direct `project-io` includes/links, retired contracts, and Product-specific Provider includes.

- [ ] **Step 2: Run RED**

```bash
cmake --build build/core/dev --target lmdj_web_control_runtime_tests
```

Expected: target and runtime do not exist.

- [ ] **Step 3: Implement one Facade-owned Project session**

`project.open` acquires and retains `RuntimeProjectWriterLease`, runs `project.inspect` through Facade, prepares a limited Snapshot, constructs a bounded Bank, reserves aggregate Bank bytes, and publishes atomically. `project.create` acquires the stable path lease before mutation. A competing lease maps `storage_condition: project_busy` to private `PROJECT_BUSY`.

- [ ] **Step 4: Implement exact operation delegation**

Delegate Project mutations/queries to Application; call typed byte import for the verified sidecar; use existing typed realtime Take append/seal methods for Capture. Host operations `audio.activate`, `audio.suspend`, `trigger`, and `host.close` orchestrate Engine/adapter state only.

- [ ] **Step 5: Implement bounded main-to-control proxy transport**

The exported main-thread function validates only byte bounds, copies into a fixed request slot, and calls:

```cpp
emscripten_proxy_async(queue, control_thread, process_request, request);
```

`process_request` owns parsing and dispatch on the Control pthread. Responses and notifications return through a bounded shared response queue. Duplicate in-flight IDs are rejected before dispatch. No Facade call executes on the browser main thread.

- [ ] **Step 6: Run GREEN**

```bash
cmake --build build/core/dev --target lmdj_web_control_runtime_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^host\.web_control_runtime$'
python3 apps/web-runtime-host/test/web_host_source_boundary_test.py \
  apps/web-runtime-host
```

- [ ] **Step 7: Commit Task 6**

```bash
git commit -m "feat(web): compose facade control runtime"
```

### Task 7: Run the shared C++ Realtime Engine inside Wasm AudioWorklet

**Files:**

- Create: `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`
- Create: `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- Create: `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
- Modify: `packages/audio-runtime/CMakeLists.txt`
- Modify: `apps/web-runtime-host/CMakeLists.txt`
- Modify: `apps/web-runtime-host/src/control_runtime.cpp`

**Adapter callback:**

```cpp
static bool process(int num_inputs,
                    const AudioSampleFrame* inputs,
                    int num_outputs,
                    AudioSampleFrame* outputs,
                    int num_params,
                    const AudioParamFrame* params,
                    void* user_data) noexcept;
```

- [ ] **Step 1: Write failing browser audio tests**

From a real click, create `new AudioContext({sampleRate: 48000})`, register it with the Emscripten runtime, start the Wasm AudioWorklet, and assert two channels, 128 frames, current Bank generation acknowledged, C++ outcome emitted, and nonzero output energy. Add negative tests for realized 44.1 kHz, 127/256 frames, processor error, and generation mismatch.

`probe-pre.js` and the formal main module expose exactly one registration helper that calls `emscriptenRegisterAudioObject(audioContext)` and returns the Emscripten handle; the Control pthread receives only that numeric handle, never the JavaScript object.

- [ ] **Step 2: Run RED**

```bash
scripts/web-toolchain-conformance.sh build-audio-runtime
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/audio/realtime_audio_worklet.spec.mjs
```

Expected: formal adapter and Host target are absent.

- [ ] **Step 3: Implement Worklet initialization**

Use `emscripten_start_wasm_audio_worklet_thread_async`, `emscripten_create_wasm_audio_worklet_processor_async`, and `emscripten_create_wasm_audio_worklet_node`. Configure zero inputs, one output, and two output channels. The main-thread gesture creates/resumes the context; the Control pthread owns Engine state.

- [ ] **Step 4: Implement the callback as a thin adapter**

Reject any shape other than one two-channel output with 128 samples per channel by atomically publishing a fatal adapter code and returning `false`. Otherwise call:

```cpp
engine.render(outputs[0].data,
              outputs[0].data + outputs[0].samplesPerChannel,
              128);
```

No JavaScript sampler, per-callback allocation, logging, or proxy call is permitted.

- [ ] **Step 5: Prove one shared memory and exact outcome flow**

The browser test checks the `.wasm` memory is shared/non-growing, Bank data written on Control is heard by Worklet rendering, and each admitted sequence is returned by `drain_trigger_outcomes()` with the Worklet's absolute `runtime_frame`.

- [ ] **Step 6: Run GREEN**

```bash
scripts/web-toolchain-conformance.sh build-audio-runtime
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/audio/realtime_audio_worklet.spec.mjs
scripts/core.sh test dev full
```

- [ ] **Step 7: Commit Task 7**

```bash
git commit -m "feat(audio): adapt realtime engine to wasm worklet"
```

### Task 8: Complete Trigger, outcome, Capture, Take, and failure orchestration

**Files:**

- Modify: `apps/web-runtime-host/src/control_runtime.hpp`
- Modify: `apps/web-runtime-host/src/control_runtime.cpp`
- Modify: `apps/web-runtime-host/src/bridge.cpp`
- Modify: `apps/web-runtime-host/test/control_runtime_test.cpp`
- Create: `apps/web-runtime-host/test/realtime_session_test.cpp`
- Create: `tests/platform/web/audio/realtime_failure.spec.mjs`

- [ ] **Step 1: Write failing end-to-end realtime session tests**

Test Trigger admission vs execution, ordered outcome batches, 128-Voice capacity, Queue full, Outcome Ring drop, Capture Ring drop, Take exact membership, final drain, interruption seal, Worklet error seal, and prior Bank retention. For 20+1 capture, committed Take contains only the 20 pre-stop events.

- [ ] **Step 2: Run RED**

```bash
cmake --build build/core/dev --target lmdj_web_realtime_session_tests
```

Expected: session target or required failure behavior is absent.

- [ ] **Step 3: Implement bounded control drains**

Drain outcomes and Capture in batches of 64. Emit only non-empty ordered `runtime.trigger_outcomes` notifications. If outcome drops become nonzero, atomically stop Trigger acceptance, seal an active Take as `capture_incomplete`, transition to `failed`, and never resume that session.

- [ ] **Step 4: Implement Take stop and close barriers**

`take.stop` disarms Capture, waits for Worklet acknowledgement, drains the final Capture batch, persists it through Facade, and only then makes the Take committable. `host.close` either completes that barrier or seals; then it stops audio, releases Banks, flushes Project mutations, releases the writer lease, and reports `closed`.

- [ ] **Step 5: Implement timeout cancellation semantics**

Each request carries a monotonic deadline into the Control queue. Before any mutating publish point, recheck cancellation. After a timeout, terminate the Worker so no late Project success can be published. A blocked competing OPFS handle returns `PROJECT_BUSY` instead of consuming the 30-second deadline.

- [ ] **Step 6: Run GREEN**

```bash
cmake --build build/core/dev --target \
  lmdj_web_control_runtime_tests lmdj_web_realtime_session_tests
ctest --test-dir build/core/dev --output-on-failure \
  -R '^host\.web_'
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/audio/realtime_failure.spec.mjs
```

- [ ] **Step 7: Commit Task 8**

```bash
git commit -m "feat(web): persist realtime takes and failures"
```

### Task 9: Add the diagnostic shell, activation, lifecycle, and unified inputs

**Files:**

- Create: `apps/web-runtime-host/index.html`
- Create: `apps/web-runtime-host/styles.css`
- Create: `apps/web-runtime-host/src/main.mjs`
- Create: `apps/web-runtime-host/test/main_shell.test.mjs`
- Create: `tests/host/web_runtime_host_lifecycle.spec.mjs`
- Modify: `apps/web-runtime-host/src/input_adapters.mjs`
- Modify: `apps/web-runtime-host/src/state_machine.mjs`

- [ ] **Step 1: Write failing shell and lifecycle tests**

Assert no inline/remote scripts or styles, 64 stable Pad buttons, exact state text, explicit audio and MIDI buttons, privacy-safe diagnostics, no input before `running`, interruption immediately stops input, and recovery requires Context running + generation acknowledgement + first post-recovery `voice_started` outcome.

- [ ] **Step 2: Run RED**

```bash
node --test apps/web-runtime-host/test/main_shell.test.mjs
npm --prefix tests/platform/web test -- --project=chromium \
  tests/host/web_runtime_host_lifecycle.spec.mjs
```

Expected: page and main controller do not exist.

- [ ] **Step 3: Implement minimal main-thread ownership**

Main owns preflight, manifest verification, `AudioContext({sampleRate: 48000})`, user gesture, DOM input, Web MIDI permission, lifecycle listeners, and transport only. It never opens OPFS, calls Facade, accesses WasmFS, decodes audio, or mixes samples.

- [ ] **Step 4: Implement exact lifecycle observations**

Handle `AudioContext.statechange`, `visibilitychange`, `pagehide`, `pageshow`, Worker error/messageerror, Worklet `processorerror`, MIDI connect/disconnect, and storage/control notifications. Interruption seals the active Take and never resumes it.

- [ ] **Step 5: Route every input through one function**

Pointer, Keyboard, and MIDI adapters call:

```javascript
trigger(flatSlot, velocity)
```

Flatten Project `{bank, pad}` exactly once as `bank * 16 + pad` immediately before realtime enqueue. Mapping, velocity setting, and pressed state remain Host/Workspace settings, never Project Truth.

- [ ] **Step 6: Run GREEN**

```bash
node --test apps/web-runtime-host/test/*.test.mjs
npm --prefix tests/platform/web test -- --project=chromium \
  tests/host/web_runtime_host_lifecycle.spec.mjs
```

- [ ] **Step 7: Commit Task 9**

```bash
git commit -m "feat(web): add diagnostic host lifecycle shell"
```

### Task 10: Add deterministic build, package, CSP server, and stable operator command

**Files:**

- Create: `apps/web-runtime-host/tools/package.py`
- Create: `apps/web-runtime-host/tools/server.py`
- Create: `apps/web-runtime-host/test/package_test.py`
- Create: `apps/web-runtime-host/test/server_test.py`
- Create: `apps/web-runtime-host/test/distribution_test.py`
- Create: `scripts/web-runtime-host.sh`
- Modify: `apps/web-runtime-host/CMakeLists.txt`
- Modify: `tests/build/test_active_tree.sh`

**Stable commands:**

```text
scripts/web-runtime-host.sh configure
scripts/web-runtime-host.sh build
scripts/web-runtime-host.sh test
scripts/web-runtime-host.sh proof
scripts/web-runtime-host.sh serve
scripts/web-runtime-host.sh clean
```

- [ ] **Step 1: Write failing command, server, and distribution tests**

Test wrong arity, unsafe clean path, toolchain mismatch, missing hashed asset, manifest mismatch, path traversal, directory listing, Range, unknown method, wrong MIME, missing isolation header, weakened CSP, blanket `no-store`, source map, source file, absolute path, test fixture, proof server, and development dependency in dist.

- [ ] **Step 2: Run RED**

```bash
python3 apps/web-runtime-host/test/package_test.py
python3 apps/web-runtime-host/test/server_test.py
python3 apps/web-runtime-host/test/distribution_test.py
```

Expected: tools and distribution are absent.

- [ ] **Step 3: Implement deterministic packaging and identity**

Write content-hashed runtime assets to `build/web/host/dist`, then canonical `host-manifest.json` binding Product Build, Host SemVer, protocol 1, all three Emscripten identities, 536,870,912-byte heap, four resource limits, `emcc --version`, and every asset path/byte length/SHA-256. Main and Control validate the manifest hash before OPFS mount.

- [ ] **Step 4: Implement the proof-only server**

Serve only a supplied dist root. Apply COOP, COEP, CORP, correct WASM MIME, exact design CSP, `no-store` only to `index.html` and manifest, and immutable caching to hashed assets. Return 404/405 for traversal, directory, Range, and unsupported methods.

- [ ] **Step 5: Implement clean-room Proof orchestration**

`proof` cleans and rebuilds, runs Node/Python/C++ Web tests, packages, copies dist to `mktemp -d`, starts the server from that directory, unsets `NODE_PATH` and `PYTHONPATH`, disables package fetch, runs browser tests, and verifies inventory. `clean` removes only the resolved `build/web/host` subtree.

- [ ] **Step 6: Run GREEN**

```bash
scripts/web-runtime-host.sh configure
scripts/web-runtime-host.sh build
scripts/web-runtime-host.sh test
python3 apps/web-runtime-host/test/distribution_test.py
```

- [ ] **Step 7: Commit Task 10**

```bash
git commit -m "build(web): package isolated runtime host"
```

### Task 11: Add Chromium full Browser Proof and WebKit capability smoke

**Files:**

- Create: `tests/host/web_runtime_host_browser.spec.mjs`
- Create: `tests/fixtures/audio/web-runtime-host-short.wav`
- Create: `tests/fixtures/audio/web-runtime-host-fixture.json`
- Modify: `tests/fixtures/audio/make_fixtures.py`
- Modify: `tests/platform/web/playwright.config.mjs`
- Modify: `scripts/web-runtime-host.sh`

- [ ] **Step 1: Write the failing full journey**

Implement the exact twelve design journey steps. Derive admission count against exported Core constants, assert `500 < kRealtimeQueueCapacity` and `500 < kRealtimeTriggerOutcomeCapacity`, and record fixture frame count/pacing that keeps concurrent Voices below 128.

- [ ] **Step 2: Run RED**

```bash
scripts/web-runtime-host.sh proof
```

Expected: full Browser Proof fails because the complete journey and fixture are absent.

- [ ] **Step 3: Implement 500 sequence-addressed Trigger proof**

Store every admitted sequence, drain until all outcomes arrive, and assert one-to-one equality with no missing/duplicate/unknown sequence, all `voice_started`, zero `voice_capacity`, `voice_drops`, queue drops, Bank transition rejection, and Outcome Ring drops.

- [ ] **Step 4: Implement 20+1 Take and restart proof**

Begin a Take, admit 20 paced Triggers, stop and fully drain, admit one further Trigger, commit, and inspect through Facade. Assert committed Take contains exactly 20 events. Reload page/Worker, reopen the same OPFS Project, reproduce revision, list recoverable Takes, republish, reactivate, and trigger again.

- [ ] **Step 5: Implement failure and lifecycle proof**

Exercise suspend/recovery, one-gesture recovery when required, Snapshot rejection with prior generation, lease contention, protocol mismatch before mutation, timeout termination, and clean close. WebKit runs capability, protocol, OPFS, restart, and lifecycle smoke; a missing primitive produces an explicit limitation record.

- [ ] **Step 6: Run GREEN**

```bash
scripts/web-runtime-host.sh proof
```

Expected: Chromium complete PASS; WebKit PASS or explicit limitation; clean dist passes without source-tree lookup or network fetch.

- [ ] **Step 7: Commit Task 11**

```bash
git commit -m "test(web): prove formal browser runtime journey"
```

### Task 12: Propagate versions, Product Assembly, full CI, and acceptance evidence

**Files:**

- Create: `apps/web-runtime-host/module.json`
- Create: `docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md`
- Modify: `packages/project-io/module.json`
- Modify: `packages/audio-runtime/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `apps/native-test-host/module.json`
- Modify: `apps/native-test-host/src/main.cpp`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/assembly.lock.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `products/lmdj/CMakeLists.txt`
- Modify: `products/lmdj/README.md`
- Modify: `README.md`
- Modify: `scripts/core.sh`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `tests/core/facade/assembly_loader_test.cpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: affected CLI/MCP/Native Host version assertions
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/core-nightly.yml` only if required to preserve the existing TSan/Stress commands

- [ ] **Step 1: Write failing exact identity assertions**

Assert the target table in this plan, `web-runtime-host` presence in Assembly and compiled catalog, exact module dependency graph, `1.0.12.0` Product tag/display strings, and no Contract/Provider version change.

- [ ] **Step 2: Run RED**

```bash
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
```

Expected: fail against baseline identities and missing Web Host manifest.

- [ ] **Step 3: Update exact identities and Product wiring**

Set Product `1.0.12.0`, Project I/O `0.4.0`, Audio Runtime `0.4.0`, Facade `1.2.0`, CLI/MCP `1.0.3`, Native Host `1.0.1`, and Web Host `1.0.0`. Add Web Host to Assembly hosts and link the Product compiled catalog object only from `products/lmdj/CMakeLists.txt` when the Emscripten target exists.

- [ ] **Step 4: Regenerate and verify the Assembly lock**

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

- [ ] **Step 5: Finalize CI and acceptance record**

Retain Web Runtime Lab, macOS, Ubuntu, ASan, Coverage, TSan, and Stress lanes. Add the formal Web Host lane with exact emsdk verification, `npm ci`, explicit Playwright browser installation, and `scripts/web-runtime-host.sh proof`. Record exact local commands/results, CI URLs only after available, and the five physical rows as `deferred / unverified`—never PASS.

- [ ] **Step 6: Run all local release-candidate gates**

```bash
scripts/web-runtime-host.sh proof
scripts/web-runtime-lab.sh test
scripts/core.sh proof
scripts/core.sh configure asan
scripts/core.sh build asan
scripts/core.sh test asan full
scripts/core.sh configure tsan
scripts/core.sh build tsan
scripts/core.sh test tsan full
scripts/core.sh configure release
scripts/core.sh build release
scripts/core.sh test release stress
scripts/core-coverage.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
git diff --check
```

Expected: every automated gate passes; physical rows remain deferred; Product reports `1.0.12.0 · canary` and exact Assembly lock match.

- [ ] **Step 7: Commit Task 12**

```bash
git commit -m "feat(product): assemble formal web runtime host"
```

### Task 13: Review, PR, squash merge, merged-main Proof, and separately approved tag

**Files:**

- Modify only files required by concrete review findings; each finding gets a focused test and follow-up commit.
- Update: `docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md` only with verified PR/CI/merged-main evidence.

- [ ] **Step 1: Self-review spec and source coverage**

Map every design section and B1–B6 to a named test/implementation. Inspect placeholder hits in changed files, then fail automatically on forbidden contracts, `record.*` in formal source, direct Host Project I/O, Web Runtime Lab runtime imports, unbounded allocations, source maps, and physical PASS claims.

```bash
git diff --name-only -z origin/main...HEAD | \
  xargs -0 rg -n 'TODO|FIXME|TBD|placeholder' || true
if rg -n 'record\.(begin|stop|commit)|lmdj\.patch\.v1|lmdj\.materials\.v1' \
  apps/web-runtime-host/src; then
  echo "forbidden Web Host source found" >&2
  exit 1
fi
python3 tests/conformance/module_graph_test.py
scripts/web-runtime-host.sh proof
scripts/core.sh proof
```

- [ ] **Step 2: Request code review**

Use `requesting-code-review` against the complete branch diff. Resolve only evidenced findings, one focused regression path per defect, and rerun affected plus full Proof gates.

- [ ] **Step 3: Push and open PR only after explicit authorization**

Push `feat/formal-web-runtime-host`, open a PR to `main`, and include exact local evidence, toolchain identities, WebKit limitation status, rollback statement, and physical deferral. Do not create a tag or Release.

- [ ] **Step 4: Require and inspect all configured CI**

Required evidence includes Web Host, Web Lab, macOS, Ubuntu, ASan, Coverage, TSan, and Stress. A skipped or missing required job is not green. If the branch is behind, update from latest `main` under the canonical workflow and rerun.

- [ ] **Step 5: Squash merge only after explicit authorization**

Verify PR merge state and resulting `main` SHA. Clean the task branch/worktree only after patch equivalence and clean status are proven.

- [ ] **Step 6: Re-run merged-main Proof**

From a clean worktree at the merged `main` SHA, run at least:

```bash
scripts/web-runtime-host.sh proof
scripts/core.sh proof
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

Record the full SHA and outputs in the acceptance document.

- [ ] **Step 7: Create and push the signed Product tag only after separate approval**

Resolve the exact merged SHA, create signed annotated `lmdj-v1.0.12.0`, verify tag object/signature/target, then push only that tag if tag push is separately authorized. GitHub Release, deployment, publication, and Channel promotion remain unperformed.

## Plan Self-review Checklist

- [ ] Every approved scope item in design §3 maps to at least one Task and named test.
- [ ] Every B1–B6 resolution maps to an executable gate; Task 0 stops Product work if B3 fails.
- [ ] No step assumes WebKit automation equals physical Safari.
- [ ] No step marks any deferred physical row passed.
- [ ] No Host file parses Project Truth or links Project I/O directly.
- [ ] No Web persistence path copies bundles through MEMFS or invents a second Project algorithm.
- [ ] OPFS absence of directory durability is tested through old-or-new recovery rather than claimed away.
- [ ] Every dequeued Trigger has one sequence-addressed outcome; admission, execution, and physical onset remain distinct.
- [ ] Runtime limits are exact, checked before expensive allocation/read, and retain the previous Bank on rejection.
- [ ] Audio callback work is bounded and allocation/lock/I/O/Facade/JSON/logging free.
- [ ] Same-build private protocol creates no public Contract or compatibility negotiation.
- [ ] Product, Module, dependency, manifest, Assembly, lock, and Host identities are internally consistent.
- [ ] Every Task has RED, implementation, GREEN, exact staging, and one commit boundary.
- [ ] Push, PR, merge, tag, tag push, Release, deployment, and Channel promotion are separately authorized.

## References

- `docs/superpowers/specs/2026-08-03-lmdj-formal-web-runtime-host-design.md`
- `docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
- `docs/superpowers/specs/2026-08-02-lmdj-formal-native-realtime-host-design.md`
- `docs/governance/git-workflow.md`
- `docs/governance/version-management.md`
- [Emscripten Wasm Audio Worklets API](https://emscripten.org/docs/api_reference/wasm_audio_worklets.html)
- [Emscripten File System API](https://emscripten.org/docs/api_reference/Filesystem-API.html)
- [Playwright browser installation and version coupling](https://playwright.dev/docs/browsers)
