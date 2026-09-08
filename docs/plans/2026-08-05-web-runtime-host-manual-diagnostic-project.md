# Web Runtime Host Manual Diagnostic Project Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task.

**Goal:** Make the shipped Web Runtime Host UI prepare a reusable 64-pad diagnostic Project before audio activation, so a fresh human journey reaches `running` instead of `HOST_STATE_INVALID`.

**Architecture:** Add a browser-only diagnostic-project coordinator beside the existing Host controller. It owns a versioned local locator, deterministic in-memory WAV generation, serialized Project inspection/repair, and Runtime Snapshot publication through the existing private transport. The Host state machine, Application Facade, Project Truth, mutation deadline arbitration, and public Contracts remain unchanged. The controller exposes one explicit `loadDiagnosticProject()` action, keeps audio activation gated until a positive published generation exists, and reports only allowlisted preparation facts.

**Tech Stack:** JavaScript ES modules, Node test runner, Playwright Chromium, Emscripten/Wasm AudioWorklet, Python package tests, JSON Product/Assembly manifests, Docusaurus Architecture Portal.

## Global Constraints

- Execute from the isolated worktree `/Users/endaye/Projects/lmdj/.worktrees/web-host-manual-activation` on `fix/web-host-manual-activation`; never edit `main`.
- The approved design is `docs/design/2026-08-05-web-runtime-host-manual-diagnostic-project-design.md`. A conflict returns to design review; implementation must not silently weaken it.
- The browser locator is not Project Truth. It stores only `{contract, project_id, pattern_id, asset_id}` under `lmdj.web-runtime-host.diagnostic-project.v1`.
- All Project reads and mutations go through the existing bounded Host transport. Do not parse an OPFS bundle or call Project I/O directly.
- Create no shipped WAV fixture. Generate a deterministic mono 48 kHz, 16-bit PCM WAV in memory and keep it below the manifest's 1 MiB import limit.
- Assign one diagnostic Asset to all 64 stable Pad Slots. Reopening an already-correct Project must not import or assign again.
- Do not weaken `HOST_RESTART_REQUIRED`, the 1,000 ms claimed-settlement watchdog, terminal cleanup, or page lifecycle rules.
- Keep runtime Host state and diagnostic preparation state separate. Preparation uses exactly `idle`, `loading`, `ready`, `error`, and `restart-required`.
- Do not expose Project, Pattern, Asset, command, path, or storage identifiers in DOM diagnostics or errors.
- Each Task below is one reviewable Conventional Commit except the clean-worktree Portal freeze, which is intentionally its own commit.
- Before every commit run Task-specific tests, `scripts/architecture-portal.sh check`, stage only declared files, inspect `git diff --cached --check`, and inspect the committed file list plus final status.
- No push, Pull Request, merge, tag, GitHub Release, deployment, publication, or Channel promotion is authorized by this plan.

## File Structure

- Create `apps/web-runtime-host/src/diagnostic_project.mjs`: locator validation, deterministic WAV generation, Project inspection/repair, serialization, lifecycle invalidation, typed preparation results.
- Create `apps/web-runtime-host/test/diagnostic_project.test.mjs`: pure coordinator tests with a scripted transport and storage seam.
- Modify `apps/web-runtime-host/src/main.mjs`: controller ownership, activation guard, diagnostics allowlist, DOM rendering, page lifecycle invalidation, and public controller method.
- Modify `apps/web-runtime-host/index.html`: explicit Load control and accessible preparation status.
- Modify `apps/web-runtime-host/styles.css`: loading/status presentation using the existing visual system.
- Modify `apps/web-runtime-host/test/main_shell.test.mjs`: controller and DOM regression tests.
- Modify `apps/web-runtime-host/tools/package.py`, `apps/web-runtime-host/test/package_test.py`, `apps/web-runtime-host/test/distribution_test.py`, and `apps/web-runtime-host/CMakeLists.txt`: hashed production-module inventory and exact identity fixtures for the additional module.
- Modify `tests/platform/web/host/web_runtime_host_browser.spec.mjs`: replace the hidden preparation prerequisite in the primary human journey with visible UI actions and add persistence/idempotence proof.
- Modify `apps/web-runtime-host/module.json`, `products/lmdj/version.json`, `products/lmdj/assembly.json`, `products/lmdj/assembly.lock.json`, `products/lmdj/src/compiled_assembly.cpp`, `scripts/core.sh`, `README.md`, and `products/lmdj/README.md`: Web Host `1.1.0` and Product Build `1.0.15.0` identity propagation.
- Modify exact identity assertions discovered by `rg -l '1\\.0\\.14\\.0|web-runtime-host.*1\\.0\\.0' tests apps/web-runtime-host products scripts README.md` while excluding immutable `apps/architecture-portal/versioned_*` and generated build output.
- Modify `docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md`: append the manual-path corrective evidence while retaining the five physical rows as deferred.
- Modify `apps/architecture-portal/docs/hosts/web-runtime.mdx`, `apps/architecture-portal/docs/platform/web-runtime.mdx`, `apps/architecture-portal/docs/operations/testing-and-proof.mdx`, and `apps/architecture-portal/docs/operations/version-and-release.mdx`: current truth for the visible preparation workflow and new Build.
- Create the generated immutable `1.0.15.0` canary Portal snapshot only through `scripts/architecture-portal.sh version 1.0.15.0 canary` after the identity/current-doc commit is clean.

## Version Management

| Identity | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.14.0` | `1.0.15.0` | Product Assembly selects the new Host and allocates a canary Build for manual team testing. |
| Web Runtime Host | `1.0.0` | `1.1.0` | Additive visible diagnostic-project preparation capability. |
| Host private protocol | `1` | `1` | Existing operations and envelopes are reused. |
| Application Facade | `1.2.0` | `1.2.0` | No Facade API change. |
| Audio Runtime | `0.4.0` | `0.4.0` | No realtime API or engine change. |
| Contracts and Providers | unchanged | unchanged | No public Contract, capability, or Provider semantic change. |
| Channel | `canary` | `canary` | No promotion. |

The future signed Product tag text is `lmdj-v1.0.15.0`, but tag creation and tag push are outside this plan's authority.

## Documentation Impact

Documentation impact: required for `/hosts/web-runtime/`, `/platform/web-runtime/`, `/operations/testing-and-proof/`, and `/operations/version-and-release/`. These current routes must describe the explicit Load-before-Activate journey, the automated versus physical evidence boundary, Host `1.1.0`, and Product Build `1.0.15.0`. Because this Build is allocated for team testing, Task 4 freezes an immutable `1.0.15.0 · canary` snapshot. The existing `1.0.14.0` snapshot is immutable and must not be edited or regenerated.

### Task 1: Build the diagnostic-project coordinator with pure TDD

**Files:**

- Create: `apps/web-runtime-host/src/diagnostic_project.mjs`
- Create: `apps/web-runtime-host/test/diagnostic_project.test.mjs`

**Documentation impact:** none in this Task; it implements a private Host helper and Task 3 updates all affected current routes.

**Version impact:** none in this Task; Task 3 propagates the approved Host and Product identities after behavior is proven.

- [ ] **Step 1: Write locator and WAV RED tests**

Create a scripted in-memory storage seam and assert:

```js
const descriptor = loadOrCreateDiagnosticDescriptor({ storage, crypto });
assert.deepEqual(Object.keys(descriptor).sort(), [
  "asset_id", "contract", "pattern_id", "project_id",
]);
assert.equal(descriptor.contract, DIAGNOSTIC_PROJECT_CONTRACT);

const wav = createDiagnosticWav();
assert.equal(new TextDecoder().decode(wav.slice(0, 4)), "RIFF");
assert.equal(new DataView(wav.buffer).getUint16(22, true), 1);
assert.equal(new DataView(wav.buffer).getUint32(24, true), 48_000);
assert.equal(new DataView(wav.buffer).getUint16(34, true), 16);
assert.ok(wav.byteLength < 1_048_576);
assert.deepEqual(createDiagnosticWav(), wav);
```

Also prove a valid descriptor is reused and a malformed JSON, wrong contract, extra key, or invalid UUID is replaced before any request is sent.

- [ ] **Step 2: Run RED**

```bash
node --test apps/web-runtime-host/test/diagnostic_project.test.mjs
```

Expected: fail because `diagnostic_project.mjs` and its exports do not exist.

- [ ] **Step 3: Implement bounded pure primitives**

Export these exact entry points:

```js
export const DIAGNOSTIC_PROJECT_CONTRACT =
  "lmdj.web-runtime-host.diagnostic-project.v1";
export const DIAGNOSTIC_PROJECT_STORAGE_KEY =
  "lmdj.web-runtime-host.diagnostic-project.v1";
export function loadOrCreateDiagnosticDescriptor({ storage, crypto }) {}
export function createDiagnosticWav() {}
export function createDiagnosticProjectCoordinator(options) {}
```

Generate a short sine-like PCM signal with fixed sample count, frequency, amplitude, and integer attack/release ramp. Write RIFF/WAVE, `fmt `, and `data` chunks explicitly with `DataView`; never use `OfflineAudioContext`, randomness, time, fetch, or a repository fixture.

- [ ] **Step 4: Write coordinator RED tests**

The transport seam accepts `send(request, {deadlineMs, sidecar})`. Script and assert the exact fresh flow:

```text
project.open -> NOT_FOUND
project.create -> revision 0
project.inspect -> authoritative Project Truth
asset.import -> revision 1
pad.assign x64 -> revisions 2..65
snapshot.reload -> runtime_ready true, generation > 0
```

Add cases for:

- an existing correct Project: `project.open`, then `snapshot.reload`, with zero mutations;
- a partially prepared Project: import only if Asset is absent and assign only missing or wrong slots using each returned revision;
- duplicate create/open race: reopen and inspect authoritative truth;
- concurrent calls: both callers receive one shared result and only one request sequence runs;
- retry after typed pre-publication error: state becomes `error`, then a second call inspects and repairs;
- `HOST_RESTART_REQUIRED`: state becomes `restart-required`, outcome remains unknown, and no automatic retry occurs;
- invalidation after `pagehide`: a later completion cannot publish `ready`; the next explicit call reopens and inspects;
- privacy: result and diagnostic projection contain no locator UUIDs.

- [ ] **Step 5: Run RED, implement, and run GREEN**

```bash
node --test apps/web-runtime-host/test/diagnostic_project.test.mjs
```

Expected before implementation: request-order and state assertions fail. Implement one frozen coordinator exposing `load()`, `invalidate()`, and `diagnostics()`. After `project.open` or `project.create`, call `project.inspect` and treat its `project` plus `project_revision` as authoritative; derive Asset and Pad correctness from that response rather than a local revision counter. Require `runtime_ready === true` and a positive integer `generation` before returning `ready`.

Expected after implementation: all coordinator tests pass.

- [ ] **Step 6: Verify and commit Task 1**

```bash
node --test apps/web-runtime-host/test/diagnostic_project.test.mjs
node --test apps/web-runtime-host/test/*.test.mjs
scripts/architecture-portal.sh check
git diff --check
git add apps/web-runtime-host/src/diagnostic_project.mjs \
  apps/web-runtime-host/test/diagnostic_project.test.mjs
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(web): prepare diagnostic project"
git show --stat --oneline HEAD
git status --short
```

### Task 2: Gate activation, wire the visible UI, and package the module

**Files:**

- Modify: `apps/web-runtime-host/src/main.mjs`
- Modify: `apps/web-runtime-host/index.html`
- Modify: `apps/web-runtime-host/styles.css`
- Modify: `apps/web-runtime-host/test/main_shell.test.mjs`
- Modify: `apps/web-runtime-host/tools/package.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `apps/web-runtime-host/test/distribution_test.py`
- Modify: `apps/web-runtime-host/CMakeLists.txt`

**Documentation impact:** none in this Task; current documentation is synchronized with final identity in Task 3.

**Version impact:** none in this Task; package identity remains locked until Task 3.

- [ ] **Step 1: Write controller and DOM RED tests**

Extend `fakeDom()` with `diagnostic-project-load` and `diagnostic-project-state`. Add a `disabled` property to `FakeElement`. Inject `storage` and a scripted transport into the harness. Assert:

```js
await controller.start();
assert.equal(elements.get("audio-activate").disabled, true);
assert.equal(await controller.activateAudio(), false);
assert.equal(contexts.length, 0);
assert.equal(calls.some(({ operation }) => operation === "audio.activate"), false);

assert.equal(await controller.loadDiagnosticProject(), true);
assert.equal(controller.diagnostics().diagnostic_project_state, "ready");
assert.ok(controller.diagnostics().diagnostic_project_generation > 0);
assert.equal(elements.get("audio-activate").disabled, false);
assert.equal(await controller.activateAudio(), true);
```

Also assert double-click serialization, `aria-busy` during loading, retryability after typed error, `restart-required` rendering, privacy-safe diagnostics, and pagehide invalidation.

- [ ] **Step 2: Run RED**

```bash
node --test apps/web-runtime-host/test/main_shell.test.mjs
```

Expected: fail because the UI elements, coordinator wiring, activation guard, and diagnostics fields do not exist.

- [ ] **Step 3: Wire the controller without changing Host lifecycle semantics**

Import `createDiagnosticProjectCoordinator`. Create it only after runtime/transport load, using `window.localStorage`, the injected crypto seam, `boundedRequest`, and a sidecar-aware request adapter. Add `loadDiagnosticProject()` to the frozen controller surface.

At the first line of `activateAudio()`, require diagnostic state `ready` and a positive published generation in addition to the existing lifecycle guards. A rejected direct call returns `false` without constructing `AudioContext`, starting AudioWorklet, sending `audio.activate`, or transitioning Host state.

Extend the diagnostic object with only:

```js
diagnostic_project_state
diagnostic_project_error_code
diagnostic_project_generation
```

Keep `error_code` reserved for terminal Host failures. Map coordinator `restart-required` to the existing terminal `fail("HOST_RESTART_REQUIRED")`; ordinary preparation errors remain retryable and keep Host state `audio-suspended`.

- [ ] **Step 4: Add the visible accessible control**

Before `Activate audio`, add:

```html
<button id="diagnostic-project-load" type="button">
  Load diagnostic project
</button>
<output id="diagnostic-project-state" aria-live="polite">idle</output>
```

Disable Activate in the source markup. While loading, disable Load and set `aria-busy="true"`; on `ready`, re-enable Load for explicit reinspection and enable Activate. Style the output and disabled/loading states with the existing palette and focus treatment.

- [ ] **Step 5: Update exact package inventory**

Add `diagnostic_project.mjs` to `leaf_assets` and `EXPECTED_ASSETS`, rewrite its exact import in `main.mjs`, and update the CMake canonical-manifest fixture plus Python inventory assertions from eight to nine production assets. Preserve the rules that dist contains no fixture, source map, development server, absolute path, or network dependency.

- [ ] **Step 6: Run GREEN and distribution regression**

```bash
node --test apps/web-runtime-host/test/main_shell.test.mjs
node --test apps/web-runtime-host/test/*.test.mjs
python3 apps/web-runtime-host/test/package_test.py
python3 apps/web-runtime-host/test/distribution_test.py
```

Expected: controller, package, and clean-distribution tests pass; the generated manifest contains exactly one hashed `diagnostic-project.<sha256>.mjs` host module and no WAV asset.

- [ ] **Step 7: Verify and commit Task 2**

```bash
scripts/architecture-portal.sh check
git diff --check
git add apps/web-runtime-host/src/main.mjs \
  apps/web-runtime-host/index.html \
  apps/web-runtime-host/styles.css \
  apps/web-runtime-host/test/main_shell.test.mjs \
  apps/web-runtime-host/tools/package.py \
  apps/web-runtime-host/test/package_test.py \
  apps/web-runtime-host/test/distribution_test.py \
  apps/web-runtime-host/CMakeLists.txt
git diff --cached --name-only
git diff --cached --check
git commit -m "fix(web): gate audio on diagnostic project"
git show --stat --oneline HEAD
git status --short
```

### Task 3: Prove the human Chromium journey and propagate current identity

**Files:**

- Modify: `tests/platform/web/host/web_runtime_host_browser.spec.mjs`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/assembly.lock.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `scripts/core.sh`
- Modify: `README.md`
- Modify: `products/lmdj/README.md`
- Modify: exact active identity tests returned by the scoped `rg -l` command in File Structure
- Modify: `docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`

**Documentation impact:** required for `/hosts/web-runtime/`, `/platform/web-runtime/`, `/operations/testing-and-proof/`, and `/operations/version-and-release/`. Update current truth here; Task 4 freezes it.

**Version impact:** Web Runtime Host `1.0.0 -> 1.1.0`; Product Build `1.0.14.0 -> 1.0.15.0`; all other identities unchanged.

- [ ] **Step 1: Replace the hidden primary prerequisite with a RED human journey**

For the primary fresh-origin Chromium test, do not call `createPreparedProject()` or `hostRequest()` before activation. Drive only visible controls:

```js
await openPackagedHost(page);
await expect(page.locator("#host-state")).toHaveText("audio-suspended");
await expect(page.locator("#audio-activate")).toBeDisabled();
await page.locator("#diagnostic-project-load").click();
await expect(page.locator("#diagnostic-project-state")).toHaveText("ready");
await expect(page.locator("#audio-activate")).toBeEnabled();
await page.locator("#audio-activate").click();
await expect(page.locator("#host-state")).toHaveText("running");
```

Trigger one pad by pointer and one mapped pad by keyboard, then prove exact admitted outcomes. Inspect all 64 slots through the test-only Host request seam only after the visible flow completes. Reload the page, click Load again, and prove the same stored locator is reopened, the Project revision is unchanged, no duplicate import/assignment occurs, and activation reaches `running` again.

Keep `createPreparedProject()` only for lower-level protocol/failure tests whose subject is not the human UI prerequisite. Rename the primary test so the shipped journey is obvious in Proof output.

- [ ] **Step 2: Run RED**

```bash
scripts/web-runtime-host.sh configure
scripts/web-runtime-host.sh build
npx playwright test tests/platform/web/host/web_runtime_host_browser.spec.mjs \
  --project=chromium --grep "visible diagnostic project"
```

Expected: fail until the packaged UI owns the complete preparation path.

- [ ] **Step 3: Make the browser proof GREEN**

Fix only behavior exposed by the new test. Assert the browser-local descriptor contains the exact contract and three UUID fields, while the DOM diagnostic JSON contains none of their values. Prove the first Project revision reflects one import plus 64 assignments and the reload revision remains identical.

- [ ] **Step 4: Write failing identity assertions and propagate versions**

Update active tests first to expect Product `1.0.15.0`, Host `1.1.0`, unchanged private protocol `1`, unchanged dependency versions, and no Contract/Provider changes. Run:

```bash
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
```

Expected before manifest edits: exact identity failures.

Then update active source manifests and generated compiled identity. Regenerate the lock:

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

Do not edit immutable `versioned_docs/version-1.0.14.0`, its metadata/sidebar, or its version-scoped diagrams.

- [ ] **Step 5: Update current documentation and acceptance evidence**

Document the exact human sequence `Load diagnostic project -> ready -> Activate audio -> running -> trigger`. State that automated Chromium proves preparation, persistence, pointer/keyboard routing, and audio outcomes, but does not prove acoustic latency, a physical MIDI device, Safari/iPad touch, or subjective audio quality. Keep all five deferred physical rows explicitly `deferred / unverified`. Record only commands and results actually observed in this Task; leave PR/CI/merge evidence unclaimed.

- [ ] **Step 6: Run the full candidate gates**

Use the locked EMSDK environment required by `scripts/web-runtime-host.sh`:

```bash
scripts/web-runtime-host.sh proof
scripts/web-runtime-lab.sh test
scripts/core.sh proof
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git diff --check
```

Expected: every automated gate passes except the precise missing immutable `1.0.15.0` snapshot, if the Portal release-document gate checks for it before Task 4. Physical rows remain deferred.

- [ ] **Step 7: Commit Task 3**

Stage only the files declared by Task 3 after verifying the scoped identity search did not include generated Portal build output:

```bash
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(product): assemble manual web diagnostic flow"
git show --stat --oneline HEAD
git status --short
```

### Task 4: Freeze the immutable `1.0.15.0` canary Portal snapshot

**Files:**

- Create: `apps/architecture-portal/versioned_docs/version-1.0.15.0/`
- Create: `apps/architecture-portal/versioned_sidebars/version-1.0.15.0-sidebars.json`
- Create: `apps/architecture-portal/versioned_metadata/version-1.0.15.0.json`
- Create: `apps/architecture-portal/static/versions/1.0.15.0/diagrams/`
- Modify: `apps/architecture-portal/versions.json`

**Documentation impact:** required. This freezes the approved current routes and all Portal-governed pages/diagrams as the immutable `1.0.15.0 · canary` snapshot.

**Version impact:** none. The snapshot records the already-allocated Build and changes no Product, Host, Module, Provider, Contract, or Channel identity.

- [ ] **Step 1: Verify the clean source boundary**

```bash
git status --short
scripts/architecture-portal.sh check
```

Expected: clean worktree; current truth reports Product `1.0.15.0`, Host `1.1.0`, and no `1.0.15.0` snapshot exists.

- [ ] **Step 2: Generate only through the governed command**

```bash
scripts/architecture-portal.sh version 1.0.15.0 canary
```

Expected: schema-2 metadata records the clean Task 3 source commit, source projection, 34 source docs, sidebar, nine diagram IDs/18 assets, Product/Assembly facts, and canary channel.

- [ ] **Step 3: Verify generated boundary and commit**

```bash
scripts/architecture-portal.sh check
git diff --check
git status --short
git add apps/architecture-portal/versioned_docs/version-1.0.15.0 \
  apps/architecture-portal/versioned_sidebars/version-1.0.15.0-sidebars.json \
  apps/architecture-portal/versioned_metadata/version-1.0.15.0.json \
  apps/architecture-portal/static/versions/1.0.15.0/diagrams \
  apps/architecture-portal/versions.json
git diff --cached --name-only
git diff --cached --check
git commit -m "docs(product): freeze 1.0.15.0 canary architecture snapshot"
git show --stat --oneline HEAD
git status --short
scripts/architecture-portal.sh check
```

Expected: Portal provenance passes in post-commit mode and `1.0.14.0` paths are byte-for-byte unchanged.

### Task 5: Final review and handoff boundary

**Files:**

- Modify only files required by concrete review findings. Each finding receives a focused regression test and a separate atomic commit.

**Documentation impact:** determined by each concrete finding; do not rewrite immutable snapshots.

**Version impact:** none unless a discovered public or versioned semantic change requires a new design decision.

- [ ] **Step 1: Review the complete branch diff**

```bash
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

Check every approved design invariant: explicit action, all 64 Pads, idempotence, descriptor-before-request, authoritative revisions, pagehide invalidation, activation no-op before readiness, privacy allowlist, unchanged restart semantics, and no shipped fixture.

- [ ] **Step 2: Run final verification**

```bash
scripts/web-runtime-host.sh proof
scripts/web-runtime-lab.sh test
scripts/core.sh proof
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
git status --short
```

Expected: all automated gates pass and the worktree is clean. Report automated evidence separately from the five still-deferred physical tests.

- [ ] **Step 3: Stop at the local branch boundary**

Report the exact commits and verification results. Ask separately for authorization before push, Pull Request creation, squash merge, tag, release, deployment, publication, or Channel promotion.

## Plan Self-Review

- The fresh human journey no longer depends on hidden `createPreparedProject()` setup.
- Direct early activation is proven inert rather than terminal.
- Project Truth remains authoritative and all mutations use returned revisions.
- The local descriptor is versioned, minimal, reusable, and absent from diagnostics.
- The deterministic WAV is generated at runtime and excluded from dist inventory.
- All 64 Pad Slots, retry, restart-required, reload, lifecycle invalidation, pointer, and keyboard paths have named tests.
- Host `1.1.0`, Product `1.0.15.0`, current docs, acceptance evidence, and immutable canary snapshot have explicit ownership.
- Existing `1.0.14.0` frozen assets and the five deferred physical rows remain unchanged.
- Remote and release state transitions remain outside the authorized boundary.
