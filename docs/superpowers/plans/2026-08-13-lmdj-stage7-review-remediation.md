# Stage 7 Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every Stage 7 review finding with production-path fixes, truthful automated evidence, an immutable Product Build snapshot, and explicit human/post-merge gates.

**Architecture:** Keep Project Truth authoritative, make Runtime Session the single lifecycle owner, and let Creator project Runtime/Attempt state through guarded transitions. Consolidate shared Web integrity and identity inputs instead of copying them between Hosts. Harden native and Web Project I/O at the storage boundary, then prove the exact packaged Creator journeys and bind the resulting Assembly to one Product Build.

**Tech Stack:** C++20/CMake/CTest, Emscripten 6.0.5, JavaScript ES modules/Node 22, TypeScript 7/React 19/Vitest, Playwright 1.62.1, Python 3, Docusaurus Architecture Portal, Git/GitHub release governance.

## Global Constraints

- Work only in `/Users/endaye/Projects/lmdj/.worktrees/stage7-review-remediation` on `fix/stage7-review-remediation`; abort any commit if `git branch --show-current` is `main`.
- Preserve `Project Truth -> immutable Runtime Snapshot`; error details remain Attempt/UI state and never enter a Project bundle.
- Do not restore `lmdj.patch.v1` or `lmdj.materials.v1`.
- Every Task uses RED -> minimal implementation -> GREEN and ends in one Conventional Commit. Before each commit: stage only the listed paths, inspect `git diff --cached --name-status`, run `git diff --cached --check`, commit, inspect `git show --stat --oneline HEAD`, and require `git status --short` to be empty.
- Local commits are authorized. Push, PR creation, merge, tag, Release, deployment, publication, and Channel promotion remain separately unauthorized.
- Never report synthetic persisted lifecycle, programmatic key repeat, headless audio, Safari, iPadOS, or physical MIDI/keyboard evidence as manual or physical-device passes.
- Re-fetch and re-check `origin/main`, all worktrees, tags, and the Stage 8 reservation immediately before allocating Product/module versions. If `1.0.18.0` or a target module version has become occupied, stop version editing and recalculate monotonically; never reuse an allocated identity.
- The approved design is `docs/superpowers/specs/2026-08-13-lmdj-stage7-review-remediation-design.md`; this plan must not broaden its product scope.

## Finding Closure Map

| Findings | Owning Tasks |
| --- | --- |
| D1, D2, D3, D4, D5 | 10 |
| D6, D7, D8, D9, D10 | 5, 6, 8, 9, 10 |
| F1, F2 | 2, 11 |
| F3, F4, F5, F6 | 5, 6, 7 |
| F7, F8 | 2, 3 |
| F9, F10, F11, F12, F13 | 3, 4, 5 |
| F14, F15 | 6 |
| T1 | 13 |
| T2, T3, T4, T5 | 8, 9 |
| T6, T7 | 9, 10 |
| G1 | 14 |
| G2, G3, G4 | 10, 12, 14 |
| G5 | 1 |
| N1, N2, N3, N4 | 2 |

## Task 1: Authenticate the Existing 1.0.16.9 Snapshot Provenance

**Files:**

- Create: `apps/architecture-portal/versioned_provenance/version-1.0.16.9-squash-witness.json`
- Test: `apps/architecture-portal/test/snapshot-provenance.test.mjs`

- [ ] Confirm the source pair is still exact before writing:

```bash
jq -r '.revision' apps/architecture-portal/versioned_metadata/version-1.0.16.9.json
git rev-list --all --objects | rg '^b2294005c09975d8414105861a0b4c0939cabd7f '
git rev-parse ea2293448b374d7963e029db6c0eb1fb11002e04^{commit}
test ! -e apps/architecture-portal/versioned_provenance/version-1.0.16.9-squash-witness.json
```

Expected: metadata revision is `b2294005c09975d8414105861a0b4c0939cabd7f`; the metadata path's single-parent introducing revision resolves to `ea2293448b374d7963e029db6c0eb1fb11002e04`; witness is absent. The later two-parent merge `3ebe27aa53bdc7c8221a01324c9e3862aa5a07eb` is current-history context, not the introducing revision accepted by the provenance validator.

- [ ] Run the current fail-closed check as RED:

```bash
scripts/architecture-portal.sh check
```

Expected: all portal content tests pass, then release-docs fails because 1.0.16.9 is neither a direct parent nor authenticated by a squash witness.

- [ ] Generate the witness using the existing authenticated generator only:

```bash
scripts/architecture-portal.sh witness \
  1.0.16.9 \
  ea2293448b374d7963e029db6c0eb1fb11002e04
```

Do not edit versioned metadata or immutable snapshot content.

- [ ] Run GREEN and inspect the binding:

```bash
node --test apps/architecture-portal/test/snapshot-provenance.test.mjs
scripts/architecture-portal.sh check
jq '{product_build,source_revision,introducing_revision}' \
  apps/architecture-portal/versioned_provenance/version-1.0.16.9-squash-witness.json
```

- [ ] Commit:

```bash
git add -- apps/architecture-portal/versioned_provenance/version-1.0.16.9-squash-witness.json
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(portal): authenticate 1.0.16.9 snapshot provenance"
```

## Task 2: Harden Native and Web Project I/O Ownership Semantics

**Files:**

- Modify: `packages/project-io/src/native/storage_platform.cpp`
- Modify: `packages/project-io/src/web/library_opfs_storage.js`
- Modify: `packages/project-io/src/web/storage_platform.cpp`
- Modify: `tests/core/project_io/storage_platform_contract_test.cpp`
- Modify: `tests/platform/web/project_io/project_io_web_test.cpp`
- Modify: `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`

- [ ] Add RED native coverage that creates two hard links to one managed regular file and requires validation to return `INVALID_PROJECT`. Add Web RED cases for:

```text
publishDirectoryIfAbsent(destination, wrongPlatformIdentity) -> PROJECT_BUSY
createImmutable(existing, no lease) -> ALREADY_EXISTS
createImmutable(absent, no lease) -> PROJECT_BUSY
every owner mismatch -> PROJECT_BUSY through one adapter
```

Run:

```bash
scripts/core.sh configure dev
cmake --build build/core/dev --target lmdj_project_storage_platform_tests --parallel
ctest --test-dir build/core/dev -R '^project_io\.storage_platform$' --output-on-failure
scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs
```

Expected: the new assertions fail on hard links, platform ownership, error priority, or scattered remapping.

- [ ] Reject aliased native files at the regular-file branch:

```cpp
if (!S_ISREG(metadata.st_mode) || metadata.st_nlink != 1) {
  return Error{ErrorCode::invalid_project,
               "managed Project file must be one regular inode"};
}
```

- [ ] Make the Web lease identity explicit and preserve non-mutating error priority:

```javascript
async publishDirectoryIfAbsent(source, destination, platformIdentity) {
  const lease = activeLease(destination, platformIdentity);
  if (!lease) return PROJECT_BUSY;
  // publish only after exact owner validation
}

async createImmutable(path, bytes, platformIdentity) {
  const state = await fileState(path);
  if (state === "file") return ALREADY_EXISTS;
  const lease = activeLease(path, platformIdentity);
  if (!lease) return PROJECT_BUSY;
  // create only after ownership is established
}
```

Map internal owner mismatch to public `PROJECT_BUSY` once in the JS status adapter and delete all seven inline `-7 -> -3` branches.

- [ ] Pass `platform_identity_` from the C++ Web platform to `publishDirectoryIfAbsent`, and replace duplicated JSON assembly with one generic helper:

```cpp
template <typename T>
nlohmann::json mutation_result(const foundation::Result<T>& result) {
  return result ? nlohmann::json{{"ok", true}}
                : nlohmann::json{{"ok", false},
                                 {"error", to_string(result.error().code)}};
}
```

- [ ] Run GREEN plus the PR #127 regression boundaries for F1/F2:

```bash
ctest --test-dir build/core/dev -R 'project_io\.(storage_platform_contract|fault_matrix|project_bundle_transfer)' --output-on-failure
scripts/web-toolchain-conformance.sh build-project-io
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs
npm --prefix tests/platform/web test -- --project=webkit \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs
```

- [ ] Commit:

```bash
git add -- packages/project-io/src/native/storage_platform.cpp \
  packages/project-io/src/web/library_opfs_storage.js \
  packages/project-io/src/web/storage_platform.cpp \
  tests/core/project_io/storage_platform_contract_test.cpp \
  tests/platform/web/project_io/project_io_web_test.cpp \
  tests/platform/web/project_io/project_io_web_conformance.spec.mjs
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(project-io): harden managed storage ownership"
```

## Task 3: Consolidate Web Integrity and Remove Inactive Take State

**Files:**

- Create: `packages/web-runtime-platform/web/integrity.mjs`
- Create: `packages/web-runtime-platform/test/integrity.test.mjs`
- Modify: `packages/web-runtime-platform/web/project_bundle_reader.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/state_machine.mjs`
- Modify: `packages/web-runtime-platform/test/project_bundle_reader.test.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `packages/web-runtime-platform/test/state_machine.test.mjs`
- Modify: `apps/web-runtime-host/tools/package.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `packages/web-runtime-platform/CMakeLists.txt`

- [ ] Add RED tests for exact canonical JSON/hash behavior and segment-aware paths. Required cases:

```javascript
assert.equal(validBundlePath("pads/...sample.wav"), true);
assert.equal(validBundlePath("foo/.hidden/sample.wav"), true);
assert.equal(validBundlePath("foo/../sample.wav"), false);
assert.equal(validBundlePath("./sample.wav"), false);
assert.equal(validBundlePath("foo/./sample.wav"), false);
```

Also assert `beginTake`, `stopTake`, `allowsOperation`, and `activeTake` no longer exist on the Web state machine/session surface.

Run:

```bash
node --test packages/web-runtime-platform/test/integrity.test.mjs \
  packages/web-runtime-platform/test/project_bundle_reader.test.mjs \
  packages/web-runtime-platform/test/state_machine.test.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs
```

- [ ] Implement one shared integrity module:

```javascript
import {HostProtocolError} from "./protocol.mjs";

export function canonicalJson(value) { /* sorted recursive JSON */ }
export function exactKeys(value, keys) { /* exact object shape */ }
export async function sha256Hex(bytes, crypto) {
  if (typeof crypto?.subtle?.digest !== "function") {
    throw new HostProtocolError(
      "HOST_PROTOCOL_MISMATCH", "SHA-256 is unavailable", {});
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
```

Use it from both consumers. The path pattern must reject dot segments by segment, not substrings:

```javascript
const PATH_PATTERN =
  /^(?!.*(?:^|\/)\.{1,2}(?:\/|$))[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*$/;
```

- [ ] Delete only the inactive Web-layer take API and its sealed-test branches. Keep Core/Facade take operations intact for their actual consumers.

- [ ] Add `integrity.mjs` to diagnostic Host packaging, hashed asset inventory, import rewriting, and conformance manifest fixtures. Run GREEN:

```bash
node --test packages/web-runtime-platform/test/*.test.mjs
python3 apps/web-runtime-host/test/package_test.py
python3 apps/web-runtime-host/test/web_host_source_boundary_test.py \
  apps/web-runtime-host \
  build/web/host/cmake/packages/web-runtime-platform/lmdj_web_runtime_host.link-libraries.txt
```

- [ ] Commit:

```bash
git add -- packages/web-runtime-platform/web/integrity.mjs \
  packages/web-runtime-platform/test/integrity.test.mjs \
  packages/web-runtime-platform/web/project_bundle_reader.mjs \
  packages/web-runtime-platform/web/runtime_session.mjs \
  packages/web-runtime-platform/web/state_machine.mjs \
  packages/web-runtime-platform/test/project_bundle_reader.test.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  packages/web-runtime-platform/test/state_machine.test.mjs \
  apps/web-runtime-host/tools/package.py \
  apps/web-runtime-host/test/package_test.py \
  packages/web-runtime-platform/CMakeLists.txt
git diff --cached --name-status
git diff --cached --check
git commit -m "refactor(web-runtime): consolidate integrity boundaries"
```

## Task 4: Establish Single Input Ownership and Awaitable Terminal Cleanup

**Files:**

- Modify: `packages/web-runtime-platform/web/input_adapters.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_loader.mjs`
- Modify: `packages/web-runtime-platform/src/web-runtime-pre.js`
- Modify: `packages/web-runtime-platform/test/input_adapters.test.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_loader.test.mjs`
- Modify: `apps/creator-web/src/main.tsx`
- Modify: `apps/creator-web/src/runtime/input_controller.ts`
- Modify: `apps/creator-web/test/input_controller.test.ts`

- [ ] Add RED tests proving the exact same exported keyboard map feeds both adapters, Creator-owned mode adds no Runtime window/MIDI/pointer listeners, diagnostic default remains session-owned, and terminal cleanup resolves only after transport/BroadcastChannel/Worker/AudioContext cleanup.

```bash
node --test packages/web-runtime-platform/test/input_adapters.test.mjs \
  packages/web-runtime-platform/test/runtime_loader.test.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs
npm --prefix apps/creator-web test -- --run test/input_controller.test.ts
```

- [ ] Export and freeze one mapping from `input_adapters.mjs`:

```javascript
export const DEFAULT_KEYBOARD_MAPPING = Object.freeze({
  KeyA: 0, KeyS: 1, KeyD: 2, KeyF: 3,
  KeyG: 4, KeyH: 5, KeyJ: 6, KeyK: 7,
  KeyQ: 8, KeyW: 9, KeyE: 10, KeyR: 11,
  KeyT: 12, KeyY: 13, KeyU: 14, KeyI: 15,
});
```

- [ ] Add one explicit session option:

```javascript
const inputOwnership = options.inputOwnership ?? "session";
if (!new Set(["session", "host"]).has(inputOwnership)) {
  throw new TypeError("Runtime Session input ownership is invalid");
}
```

`wireInputs()` and `requestMidi()` must create/register adapters only in `session` mode. Creator passes `inputOwnership: "host"`; remove the empty `inputConfiguration`. Diagnostic Host keeps the default.

- [ ] Make terminal closure awaitable. `transport.terminate()` returns one idempotent promise resolved after the main terminal channel has closed and the worker release has either acknowledged or reached its bounded watchdog. `defaultRuntimeTerminator()` awaits it before closing worklet and AudioContext. Expose no new Product operation.

- [ ] Run GREEN and resource cardinality assertions:

```bash
node --test packages/web-runtime-platform/test/*.test.mjs
npm --prefix apps/creator-web test -- --run test/input_controller.test.ts
```

- [ ] Commit:

```bash
git add -- packages/web-runtime-platform/web/input_adapters.mjs \
  packages/web-runtime-platform/web/runtime_session.mjs \
  packages/web-runtime-platform/web/runtime_loader.mjs \
  packages/web-runtime-platform/src/web-runtime-pre.js \
  packages/web-runtime-platform/test/input_adapters.test.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  packages/web-runtime-platform/test/runtime_loader.test.mjs \
  apps/creator-web/src/main.tsx \
  apps/creator-web/src/runtime/input_controller.ts \
  apps/creator-web/test/input_controller.test.ts
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(web-runtime): assign one input and cleanup owner"
```

## Task 5: Push Diagnostics and Make Runtime Restart Retryable

**Files:**

- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `apps/creator-web/src/runtime/runtime_types.ts`
- Modify: `apps/creator-web/src/runtime/runtime_context.tsx`
- Modify: `apps/creator-web/test/runtime_context.test.tsx`

- [ ] Add RED tests for diagnostics subscriber delivery/unsubscribe, stale-generation rejection, one automatic restart per failure epoch, manual second retry, stable-ready reset, and zero 16 ms polling timers.

```bash
node --test packages/web-runtime-platform/test/runtime_session.test.mjs
npm --prefix apps/creator-web test -- --run test/runtime_context.test.tsx
```

- [ ] Add a push subscription to the public session surface:

```typescript
subscribeDiagnostics(listener: (value: RuntimeDiagnostics) => void): () => void;
```

`renderDiagnostics()` computes one immutable value, calls `options.onDiagnostics`, then notifies a snapshot of subscribers. Terminal cleanup clears the set after the final diagnostic edge.

- [ ] Preserve safe error details on Runtime/Host failure:

```typescript
export interface RuntimeIssue {
  code: string;
  details: Readonly<Record<string, unknown>>;
}
```

Host-state callbacks carry `{state, errorCode, errorDetails}`. Only structured details survive; raw message, stack, URL, local path, UUID, and device identity do not.

- [ ] Replace polling with generation-owned subscriptions and add `retryRuntime()` to the context. Required epoch rule:

```text
first terminal edge in epoch -> one automatic replacement
replacement reaches ready -> reset automatic allowance
replacement also fails -> visible restart-required, no loop
manual Retry -> close old generation, start a new epoch
late old-generation callbacks -> ignored
```

- [ ] Run GREEN:

```bash
node --test packages/web-runtime-platform/test/runtime_session.test.mjs
npm --prefix apps/creator-web test -- --run test/runtime_context.test.tsx
```

- [ ] Commit:

```bash
git add -- packages/web-runtime-platform/web/runtime_session.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  apps/creator-web/src/runtime/runtime_types.ts \
  apps/creator-web/src/runtime/runtime_context.tsx \
  apps/creator-web/test/runtime_context.test.tsx
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(creator): make runtime recovery observable and retryable"
```

## Task 6: Guard Creator State and Correct Its User Surface

**Files:**

- Modify: `apps/creator-web/src/state/creator_state.ts`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/components/error_panel.tsx`
- Modify: `apps/creator-web/src/components/project_surface.tsx`
- Modify: `apps/creator-web/src/runtime/project_actions.ts`
- Modify: `apps/creator-web/test/creator_state.test.ts`
- Modify: `apps/creator-web/test/project_actions.test.ts`
- Modify: `apps/creator-web/test/workspace_shell.test.tsx`
- Modify: `apps/creator-web/test/audio_lifecycle.test.tsx`
- Modify: `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`

- [ ] Add reducer RED tests for every illegal source-state/action pair. The reducer must return the exact same object when an action is illegal; lifecycle cleanup actions remain legal where needed to release pressed state.

```bash
npm --prefix apps/creator-web test -- --run \
  test/creator_state.test.ts \
  test/project_actions.test.ts \
  test/workspace_shell.test.tsx \
  test/audio_lifecycle.test.tsx
```

- [ ] Implement an exported transition predicate and guard the reducer:

```typescript
export function isCreatorActionAllowed(
  state: CreatorState,
  action: CreatorAction,
): boolean { /* explicit state/action table */ }

export function creatorReducer(state: CreatorState, action: CreatorAction) {
  if (!isCreatorActionAllowed(state, action)) return state;
  // existing legal transitions
}
```

- [ ] Route automatic reopen through the same generation-scoped project-action token as user import/open. Automatic reopen may claim a token without a click selector, but all completion/error callbacks must pass `ownsProjectAction(token)` before dispatch.

- [ ] Render typed, privacy-safe failures. Required UI projections:

```text
WEB_RUNTIME_RESOURCE_LIMIT -> resource + observed + limit
IO_ERROR -> storage_condition when present
HOST_PROTOCOL_MISMATCH -> protocol-safe generic message
INTERNAL_ERROR -> generic internal failure, no raw message
HOST_RESTART_REQUIRED/HOST_TIMEOUT -> visible Retry runtime control
```

Add BPM to the opened Project definition list. Remove the false `Save Local` promise from the Stage 7 design and document automatic local persistence without inventing a mutation/save command.

- [ ] Run GREEN:

```bash
npm --prefix apps/creator-web test -- --run
```

- [ ] Commit:

```bash
git add -- apps/creator-web/src/state/creator_state.ts \
  apps/creator-web/src/app.tsx \
  apps/creator-web/src/components/error_panel.tsx \
  apps/creator-web/src/components/project_surface.tsx \
  apps/creator-web/src/runtime/project_actions.ts \
  apps/creator-web/test/creator_state.test.ts \
  apps/creator-web/test/project_actions.test.ts \
  apps/creator-web/test/workspace_shell.test.tsx \
  apps/creator-web/test/audio_lifecycle.test.tsx \
  docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(creator): enforce editor transition contracts"
```

## Task 7: Generate Web Runtime Identity from Active Sources

**Files:**

- Create: `tools/web-runtime/runtime-identity.json`
- Create: `tools/web-runtime/generate_runtime_identity.py`
- Create: `products/lmdj/generated/web-runtime-identity.json`
- Create: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: `tools/web-runtime/emscripten.lock.json`
- Modify: `tools/web-runtime/verify_emscripten.py`
- Modify: `apps/creator-web/src/main.tsx`
- Modify: `apps/creator-web/tools/package.py`
- Modify: `apps/creator-web/test/package_test.py`
- Modify: `apps/web-runtime-host/src/main.mjs`
- Modify: `apps/web-runtime-host/tools/package.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `packages/web-runtime-platform/CMakeLists.txt`
- Modify: `packages/web-runtime-platform/test/manifest_gate_test.cpp`
- Modify: `tests/build/version_test.py`

- [ ] Add RED tests that mutate a copied Product version, Host manifest, platform manifest, Assembly lock, resource limit, and Emscripten identity independently; each mutation must make generated output differ or verification fail. Also assert the old literal identity blocks are absent from both Host mains and package tools.

```bash
python3 tests/build/version_test.py
python3 apps/creator-web/test/package_test.py
python3 apps/web-runtime-host/test/package_test.py
```

- [ ] Move the exact `emcc_version` line into `emscripten.lock.json`; `verify_emscripten.py` compares live output to that field instead of its own literal. Define only product-neutral manifest policy in `runtime-identity.json`: protocol, heap, resource limits, Host distribution contracts, compatible Host relation, and expected asset roles.

- [ ] Implement deterministic generation:

```python
def generate(repo_root: Path) -> dict:
    return {
        "product_build": read_product_build(repo_root),
        "assembly_sha256": read_lock_identity(repo_root),
        "platform": read_module(repo_root, "web-runtime-platform"),
        "hosts": {
            "creator-web": read_host(repo_root, "creator-web"),
            "web-runtime-host": read_host(repo_root, "web-runtime-host"),
        },
        "emscripten": read_exact_lock(repo_root),
        **read_runtime_policy(repo_root),
    }
```

The generator validates exact keys, exact Assembly membership/version agreement, safe identities, and fixed-heap consistency, then writes canonical JSON plus an `Object.freeze` ES module. A `--check` mode compares bytes and fails on stale output.

- [ ] Import the MJS output from both Host mains. Package tools read the JSON output and derive Host/version/platform/product/protocol/limits/toolchain expectations. CMake conformance manifest reads the same generated JSON at configure time; do not introduce another copied CMake identity.

- [ ] Preserve the existing `window.__LMDJ_WEB_HOST_SEAMS__` injection boundary when Creator creates its session so the exact packaged artifact can exercise lifecycle faults without a source-modified test build.

- [ ] Run GREEN and stale-output checks:

```bash
python3 tools/web-runtime/generate_runtime_identity.py --check
python3 tests/build/version_test.py
python3 apps/creator-web/test/package_test.py
python3 apps/web-runtime-host/test/package_test.py
node --test packages/web-runtime-platform/test/*.test.mjs
```

- [ ] Commit:

```bash
git add -- tools/web-runtime/runtime-identity.json \
  tools/web-runtime/generate_runtime_identity.py \
  tools/web-runtime/emscripten.lock.json \
  tools/web-runtime/verify_emscripten.py \
  products/lmdj/generated/web-runtime-identity.json \
  products/lmdj/generated/web-runtime-identity.mjs \
  apps/creator-web/src/main.tsx \
  apps/creator-web/tools/package.py \
  apps/creator-web/test/package_test.py \
  apps/web-runtime-host/src/main.mjs \
  apps/web-runtime-host/tools/package.py \
  apps/web-runtime-host/test/package_test.py \
  packages/web-runtime-platform/CMakeLists.txt \
  packages/web-runtime-platform/test/manifest_gate_test.cpp \
  tests/build/version_test.py
git diff --cached --name-status
git diff --cached --check
git commit -m "refactor(product): generate web runtime identity"
```

## Task 8: Bound Busy Retry and Complete Keyboard/Visibility Coverage

**Files:**

- Modify: `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- Modify: `apps/creator-web/test/input_controller.test.ts`

- [ ] Replace the unbounded wall-clock loop with a deterministic attempt cap and transition-based waits:

```javascript
const MAX_BUSY_RETRIES = 8;
for (let attempt = 0; attempt < MAX_BUSY_RETRIES; attempt += 1) {
  await expect.poll(async () =>
    await heading.isVisible() ? "ready" : await alert.textContent(),
  {timeout: 35_000}).not.toBe("");
  if (await heading.isVisible()) break;
  await expect(alert).toContainText("PROJECT_BUSY");
  await page.getByRole("button", {name: "Retry"}).click();
}
await expect(heading).toBeVisible();
await expect(alert).toHaveCount(0);
```

Do not use a fixed `waitForTimeout(250)`.

- [ ] Add an end-to-end keyboard journey: keyboard-focus and Enter on Import, use only keyboard to invoke Open after reload, and keyboard-select a different Bank. FileChooser automation may provide the selected file after the user-facing button is activated by keyboard.

- [ ] Add component coverage that both `visibilitychange(hidden)` and `blur` clear a held key, repeated cleanup is idempotent, and a later keydown is admitted.

- [ ] Run RED, implement only the needed test helpers/input cleanup correction, then GREEN:

```bash
npm --prefix apps/creator-web test -- --run test/input_controller.test.ts
scripts/creator-web.sh build
scripts/creator-web.sh package
npm --prefix tests/platform/web test -- --project=chromium \
  tests/platform/web/creator/creator_web_accessibility.spec.mjs \
  tests/platform/web/creator/creator_web_lifecycle.spec.mjs
```

- [ ] Commit:

```bash
git add -- tests/platform/web/creator/creator_web_lifecycle.spec.mjs \
  tests/platform/web/creator/creator_web_accessibility.spec.mjs \
  apps/creator-web/test/input_controller.test.ts
git diff --cached --name-status
git diff --cached --check
git commit -m "test(creator): cover bounded retry and keyboard lifecycle"
```

## Task 9: Prove Packaged Creator Recovery, Burst, Resize, and Cleanup

**Files:**

- Modify: `tests/platform/web/creator/creator_web_browser.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- Modify: `scripts/creator-web.sh`

- [ ] Add a RED packaged test that instruments the existing session transport seam before navigation, suppresses one recovery trigger outcome, and observes the real path:

```text
ready Project + running Audio
synthetic persisted pagehide (contract boundary only)
recovery probe admission with outcome suppressed
HOST_TIMEOUT -> restart-required
exact old Runtime generation cleanup completes
automatic session replacement and Project reopen
Audio remains inactive until visible Activate audio click
```

The test must run against `build/web/creator/dist`, not a diagnostic Host or source-dev server.

- [ ] Instrument resource cardinality in the page before app startup. Count page-owned BroadcastChannels, AudioContexts, MIDI listeners, window lifecycle listeners, and Runtime generations. After replacement, assert the old generation reaches zero open resources before the new generation becomes the only owner.

- [ ] Strengthen the existing held-key burst assertion to the full tuple `[16 admissions, 16 outcomes, 0 rejected, running]` and label programmatic key repeat as synthetic.

- [ ] Add ready/active viewport continuity: capture report identity/counters, resize to `768x1024`, then `1024x768`, and assert Project heading, `Audio running`, Project revision, and Runtime counters remain continuous.

- [ ] Ensure `scripts/creator-web.sh proof` selects every tracked `creator_web_*.spec.mjs` or lists the complete explicit set. Run GREEN:

```bash
scripts/creator-web.sh proof
```

- [ ] Commit:

```bash
git add -- tests/platform/web/creator/creator_web_browser.spec.mjs \
  tests/platform/web/creator/creator_web_lifecycle.spec.mjs \
  scripts/creator-web.sh
git diff --cached --name-status
git diff --cached --check
git commit -m "test(creator): prove packaged recovery and continuity"
```

## Task 10: Reconcile Stage 7 Specifications and Release Governance

**Files:**

- Modify: `docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md`
- Modify: `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`
- Modify: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`
- Modify: `docs/quality/2026-08-12-stage7-creator-editor-review.md`
- Modify: `docs/governance/version-management.md`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/platform/storage.mdx`
- Modify: portal documentation tests selected by `scripts/architecture-portal.sh check`

- [ ] Add/adjust docs tests first so RED detects every stale statement: duplicate/inverted R1, fixed `1.0.16.0`, incorrect pagehide closure, unstructured `.2/.4/.5` corrections, generic UTF-8 path claim, missing reload/burst/resize/error/cleanup mapping, stale external state, and ambiguous PATCH/Assembly language.

- [ ] Write a retrospective correction addendum without pretending it was a pre-execution plan. It must bind each D1-D10 correction to actual Task/commit evidence and state:

```text
persisted pagehide -> shared Runtime retained and recovery contract exercised
non-persisted terminal pagehide -> close
managed Bundle paths -> ASCII segment subset; Project payload text remains UTF-8
synthetic lifecycle/key repeat -> automated contract only
physical/hearing/Safari/iPadOS/MIDI -> deferred or unverified until performed
```

- [ ] Clarify governance:

```text
PATCH may not change Product Assembly identity or assembly.lock.
Any module/provider/Host/dependency identity change allocates a new BUILD.
Historical 1.0.16.x events remain historical facts and are not rewritten.
New Product tags require merged-main Proof first.
```

Document the authoritative chain: Product Build -> signed tag -> tag revision -> merged PR -> source revision -> snapshot provenance/witness -> merged-main Proof revision -> evidence-only documentation revision.

- [ ] Update acceptance external state from live Git evidence, separating historical state from current state. Do not label branch-local candidate Proof as merged-main Proof.

- [ ] Run GREEN:

```bash
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
rg -n 'TO''DO|TB''D|FIX''ME|PLACE''HOLDER' \
  docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md \
  docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md \
  docs/quality/2026-08-07-stage7-creator-editor-acceptance.md \
  docs/quality/2026-08-12-stage7-creator-editor-review.md \
  docs/governance/version-management.md
```

Expected: no unresolved placeholder in the changed documents and Portal check passes.

- [ ] Commit:

```bash
git add -- docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md \
  docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md \
  docs/quality/2026-08-07-stage7-creator-editor-acceptance.md \
  docs/quality/2026-08-12-stage7-creator-editor-review.md \
  docs/governance/version-management.md \
  apps/architecture-portal/docs/operations/version-and-release.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx \
  apps/architecture-portal/docs/hosts/creator-web.mdx \
  apps/architecture-portal/docs/platform/web-runtime.mdx \
  apps/architecture-portal/docs/platform/storage.mdx \
  apps/architecture-portal/test
git diff --cached --name-status
git diff --cached --check
git commit -m "docs(stage7): reconcile review and release contracts"
```

## Task 11: Allocate and Propagate the Product Assembly Identity

**Files:**

- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Regenerate: `products/lmdj/assembly.lock.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `packages/project-io/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `apps/native-test-host/module.json`
- Modify: `apps/native-test-host/src/main.cpp`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/creator-web/module.json`
- Modify: `apps/creator-web/package.json`
- Modify: `apps/creator-web/package-lock.json`
- Regenerate: `products/lmdj/generated/web-runtime-identity.json`
- Regenerate: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: all exact identity assertions found by `rg`
- Modify: current Architecture Portal pages derived from active manifests
- Modify: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`

### Version Management

Candidate allocation, subject to the mandatory live re-check:

| Identity | Current | Candidate | Reason |
| --- | ---: | ---: | --- |
| Product Build | 1.0.16.9 | 1.0.18.0 | Assembly changes; local unpublished Stage 8 already reserves 1.0.17.0 |
| project-io | 0.5.3 | 0.5.4 | compatible storage correctness fix |
| application-facade | 1.3.4 | 1.3.5 | exact project-io dependency propagation |
| web-runtime-platform | 0.1.6 | 0.2.0 | additive public diagnostics/input/error/cleanup surface |
| core-cli | 1.0.10 | 1.0.11 | exact application-facade dependency propagation |
| core-mcp | 1.1.7 | 1.1.8 | exact application-facade dependency propagation |
| native-test-host | 1.0.8 | 1.0.9 | exact application-facade dependency propagation |
| web-runtime-host | 1.2.6 | 1.2.7 | compatible platform dependency and lifecycle correction |
| creator-web | 1.0.6 | 1.1.0 | additive visible retry/details/continuity behavior |

The unpublished Stage 8 branch currently also uses `web-runtime-platform 0.2.0` and `creator-web 1.1.0`; after this branch lands, Stage 8 must rebase and allocate the next compatible versions (normally `0.3.0` and `1.2.0`). Do not mutate its worktree in this Task.

### Documentation Impact

Documentation impact: required. Update current Portal routes for Product Assembly, `project-io`, `application-facade`, `web-runtime-platform`, Creator Host, Web Runtime Host, storage, input, testing/Proof, and version/release governance. Freeze the immutable Product Build snapshot in Task 12 only.

- [ ] Re-fetch and inventory before editing:

```bash
git fetch --prune origin
git worktree list --porcelain
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
git tag --list 'lmdj-v*' --sort=-v:refname | head -20
for tree in .worktrees/*; do
  test -f "$tree/products/lmdj/version.json" && \
    printf '%s ' "$tree" && jq -r '[.milestone,.minor,.build,.patch]|join(".")' \
      "$tree/products/lmdj/version.json"
done
```

Expected: no newer allocation conflicts. If assumptions changed, revise the table and this plan before code edits.

- [ ] Update manifests/assertions, regenerate Assembly lock, then regenerate Runtime identity only through. The identity generator validates the lock first and must fail closed while it is stale:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

- [ ] Run identity/Portal/current-source GREEN:

```bash
python3 tools/web-runtime/generate_runtime_identity.py --check
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
bash tests/build/test_active_tree.sh
npm --prefix apps/architecture-portal run check:current
```

- [ ] Commit the complete identity/current-doc update while the snapshot is still absent:

```bash
git add -- products/lmdj packages/project-io/module.json \
  packages/application-facade/module.json \
  packages/web-runtime-platform/module.json \
  apps/core-cli apps/core-mcp apps/native-test-host \
  apps/web-runtime-host/module.json apps/creator-web \
  tests docs/quality/2026-08-07-stage7-creator-editor-acceptance.md \
  apps/architecture-portal/docs
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(product): assemble Stage 7 remediation candidate"
```

## Task 12: Freeze the Immutable 1.0.18.0 Canary Snapshot

**Files:**

- Create: Docusaurus versioned docs/sidebars/diagrams/metadata for the final Product Build
- Modify: `apps/architecture-portal/versions.json`

- [ ] Require a clean tree and run the current-source Portal preflight. The full
  release-doc check intentionally remains unavailable until this Task creates
  the matching immutable snapshot:

```bash
test -z "$(git status --porcelain=v1 --untracked-files=all)"
npm --prefix apps/architecture-portal run check:current
```

- [ ] Freeze the exact current Product Build from a clean commit:

```bash
PRODUCT_BUILD="$(jq -r \
  '[.milestone, .minor, .build, .patch] | join(".")' \
  products/lmdj/version.json)"
test "$PRODUCT_BUILD" = "1.0.18.0"
scripts/architecture-portal.sh version "$PRODUCT_BUILD" canary
```

- [ ] Verify immutable metadata binds the pre-snapshot source commit and exact Assembly lock hash:

```bash
scripts/architecture-portal.sh check
jq '{product_build,revision,assembly_lock_sha256,channel}' \
  apps/architecture-portal/versioned_metadata/version-1.0.18.0.json
```

- [ ] Commit only generated snapshot paths:

```bash
git add -- apps/architecture-portal/versioned_docs/version-1.0.18.0 \
  apps/architecture-portal/versioned_sidebars/version-1.0.18.0-sidebars.json \
  apps/architecture-portal/static/versions/1.0.18.0 \
  apps/architecture-portal/versioned_metadata/version-1.0.18.0.json \
  apps/architecture-portal/versions.json
git diff --cached --name-status
git diff --cached --check
git commit -m "docs(portal): freeze 1.0.18.0 canary snapshot"
```

## Task 13: Run Candidate Proof and Prepare Honest Canary Evidence

**Files:**

- Modify: `scripts/core.sh` if candidate Proof reports an identity different from the verified manifest
- Modify: `tests/build/core_script_test.py` for the corresponding identity regression
- Modify: `apps/web-runtime-host/test/distribution_test.py` if the generated Host inventory and built-distribution assertion drift
- Modify: `tests/platform/web/host/web_runtime_host_lifecycle.spec.mjs` if the source-shell fixture omits a generated identity dependency
- Modify: `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`
- Modify: `docs/quality/2026-08-12-stage7-creator-editor-review.md`
- Create: `docs/release-evidence/2026-08-13-stage7-remediation-canary.md`

- [ ] Run the full candidate gates from a clean committed tree:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev full
scripts/core.sh test dev stress
scripts/core.sh coverage check
scripts/core.sh proof
scripts/web-toolchain-conformance.sh proof
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

Expected: every automated gate passes. Record exact revision, toolchain identity, commands, and result. A failure is fixed in the owning Task with a new atomic commit; do not edit evidence to mask it.

The Core Proof summary must derive Product Build from `products/lmdj/version.json`; a literal or stale reported identity is a gate failure even when the underlying tests exit zero.

- [ ] Produce a human canary sheet containing revision, Product Build, host manifest SHA-256, browser/version, ten manual steps from Stage 7 §13.3, heard/not-heard results, duplicate/missing/stuck press observations, autoplay behavior, Project data preservation, and privacy-safe report hash.

- [ ] Mark T1 exactly `open — awaiting human execution`. Keep physical MIDI, physical keyboard, Safari, iPadOS, and hearing rows `deferred / unverified` until the named human actually performs them.

- [ ] Commit automated evidence and the unexecuted canary sheet:

```bash
git add -- docs/quality/2026-08-07-stage7-creator-editor-acceptance.md \
  docs/quality/2026-08-12-stage7-creator-editor-review.md \
  docs/release-evidence/2026-08-13-stage7-remediation-canary.md
git diff --cached --name-status
git diff --cached --check
git commit -m "docs(stage7): record remediation candidate proof"
```

- [ ] Pause for the user/human operator to run and sign the manual canary. Do not manufacture a pass. After signed results are supplied, validate the evidence fields and commit only that evidence update as `docs(stage7): record manual remediation canary`.

## Task 14: Post-Merge Proof and Final Binding (Integration Owner)

This Task is intentionally blocked until the user separately authorizes push, PR, and merge, and the protected-branch PR Gate succeeds. It is not performed from the feature branch.

**Files after merge:**

- Create or modify: a Stage 7 merged-main Proof addendum under `docs/release-evidence/`
- Modify: Stage 7 acceptance/review status only with observed merged-main evidence

- [ ] With separate authorization, push the branch, create the PR, wait for all required checks, and merge through the protected workflow. Do not create a Product tag yet.

- [ ] Fetch the exact merged `main` revision into a fresh isolated worktree and repeat every command in Task 13. Bind the log to:

```text
product/source merge revision
Product Build and Assembly lock hash
required checks and runner/toolchain identity
merged-main Proof result
```

- [ ] Commit an evidence-only addendum that clearly separates the verified merge revision from the later documentation revision. Run Portal check again.

- [ ] Only after the evidence-only change is itself merged and separately authorized may release work create a signed annotated `lmdj-v1.0.18.0` tag, GitHub Release, deployment, or Channel promotion. Each is a distinct action and verification boundary.

## Final Closure Audit

- [ ] Use `rg` to enumerate D1-D10, F1-F15, T1-T7, G1-G5, and N1-N4 in the review and prove that every ID has one current status plus evidence link.
- [ ] Confirm there are no unexplained tracked/untracked changes in any modified worktree.
- [ ] Confirm the task is not reported complete while T1 or G1 is open.
- [ ] Confirm no push/tag/Release/deployment/Channel action occurred without explicit authorization.
