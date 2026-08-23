# Creator Capture Pre-commit Crop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close #213 by adding a real, atomic pre-commit Crop mutation that
rebases selected capture PCM, rebuilds waveform summaries, and exposes the
operation in Creator Product Build `1.0.30.0`.

**Architecture:** `CaptureBuffer.crop(startFrame, frameCount)` prepares
replacement channel data and peak summaries before atomically publishing a
new frame-zero buffer revision. `CapturePanel` invokes the method only from a
reducer-validated trimming selection; the reducer resets the view to the new
whole buffer while the existing Commit boundary remains unchanged.

**Tech Stack:** TypeScript, React, Vitest, Testing Library, generated LMDJ
Product Assembly identity, Docusaurus Architecture Portal, Python build and
conformance gates.

## Global Constraints

- Approved design authority:
  `docs/superpowers/specs/2026-08-23-creator-capture-precommit-crop-design.md`.
- Work only on `feat/issue-213-precommit-editing`; never modify `main`.
- Follow strict RED -> GREEN -> REFACTOR for every production behavior.
- Crop is destructive, synchronous, pre-commit, and has no Undo/redo/history.
- `crop(startFrame, frameCount): void` validates before mutation and publishes
  replacement PCM, chunk starts, frame count, block peaks, and cache state as
  one buffer revision.
- The existing `onCommit(buffer, selection)` interface, Facade, Contracts,
  Project Truth, Runtime Snapshot, Providers, and other Hosts do not change.
- Product Build becomes `1.0.30.0`; Creator Web Host becomes `1.4.0`; Host API
  version remains `1`; Stage 9 remains Product Build `1.0.31.0`.
- Product and Host identity changes require current Portal updates and an
  immutable `1.0.30.0 · canary` snapshot from a clean committed source.
- No tag, Release, deployment, publication, physical-device acceptance, or
  Channel promotion is authorized.

---

### Task 1: Add the atomic CaptureBuffer Crop contract

**Files:**

- Modify: `apps/creator-web/test/capture_buffer.test.ts`
- Modify: `apps/creator-web/src/capture/capture_buffer.ts`

**Interfaces:**

- Consumes: existing `slice(startFrame, frameCount)`, `#chunks`,
  `#chunkStarts`, `#frames`, `#blockPeaks`, and `#envelopeCache`.
- Produces: `CaptureBuffer.crop(startFrame: number, frameCount: number): void`.

- [ ] **Step 1: Write failing exact-data and rebase tests**

Add tests that split stereo input across arbitrary append chunks, Crop a range
crossing those chunks, and assert frame-zero PCM:

```ts
test("crops exact stereo frames across append chunks and rebases to zero", () => {
  const buffer = new CaptureBuffer(2);
  buffer.append([Float32Array.from([0, 1, 2]), Float32Array.from([10, 11, 12])]);
  buffer.append([Float32Array.from([3, 4, 5]), Float32Array.from([13, 14, 15])]);

  buffer.crop(2, 3);

  expect(buffer.frameCount).toBe(3);
  expect(buffer.slice(0, 3).map(Array.from)).toEqual([[2, 3, 4], [12, 13, 14]]);
});
```

Add a separate invalid-range test that captures `frameCount`, `slice()`, and a
cached envelope object before trying negative, fractional, empty, and
out-of-buffer crops, then proves all observable values and cached identity are
unchanged.

- [ ] **Step 2: Run the buffer test and verify RED**

Run:

```bash
npm --prefix apps/creator-web test -- --run test/capture_buffer.test.ts
```

Expected: TypeScript/Vitest fails because `CaptureBuffer.crop` does not exist.
Do not write production code until this failure is observed.

- [ ] **Step 3: Write stale-summary and repeated-edit tests while still RED**

Add one summary-path regression where a `1.0` peak lies outside the selected
range but in the same old 256-frame block, Crop retains only `0.25` samples,
and `envelope(2, 0, croppedFrames)` returns `[0.25, 0.25]`.

Add separate tests proving:

```ts
buffer.crop(firstStart, firstCount);
buffer.crop(secondStart, secondCount);
expect(buffer.slice(0, secondCount)).toEqual(expectedSecondCrop);

buffer.append([suffix]);
expect(buffer.slice(0, buffer.frameCount)).toEqual(expectedCropPlusSuffix);
expect(buffer.envelope(2, 0, buffer.frameCount)).toEqual(expectedPeaks);
```

Use exact binary fractions in all peak assertions.

- [ ] **Step 4: Implement replacement summary preparation and Crop**

Extract summary folding so append and Crop use the identical rule:

```ts
function foldBlockPeaks(peaks: number[], samples: Float32Array, startFrame: number): void {
  for (let sample = 0; sample < samples.length; sample += 1) {
    const block = Math.floor((startFrame + sample) / ENVELOPE_BLOCK_FRAMES);
    const magnitude = Math.abs(samples[sample] ?? 0);
    const current = peaks[block];
    if (current === undefined || magnitude > current) peaks[block] = magnitude;
  }
}

function buildBlockPeaks(channels: readonly Float32Array[]): number[][] {
  return channels.map((channel) => {
    const peaks: number[] = [];
    foldBlockPeaks(peaks, channel, 0);
    return peaks;
  });
}
```

Replace append's inline folding with `foldBlockPeaks(peaks, acceptedChunk,
this.#frames)`. Implement Crop so every fallible preparation completes before
field assignment:

```ts
crop(startFrame: number, frameCount: number): void {
  if (!Number.isInteger(startFrame) || !Number.isInteger(frameCount) ||
      startFrame < 0 || frameCount <= 0 || startFrame + frameCount > this.#frames) {
    throw new RangeError("Capture crop is out of range");
  }
  const replacement = this.slice(startFrame, frameCount);
  const replacementChunks = replacement.map((channel) => [channel]);
  const replacementPeaks = buildBlockPeaks(replacement);

  this.#chunks = replacementChunks;
  this.#chunkStarts = [0];
  this.#frames = frameCount;
  this.#blockPeaks = replacementPeaks;
  this.#envelopeCache = null;
}
```

Use the accepted copied chunk in append rather than re-slicing the source a
second time. Preserve the existing capacity and channel-shape behavior.

- [ ] **Step 5: Run RED tests GREEN and refactor without changing behavior**

Run:

```bash
npm --prefix apps/creator-web test -- --run test/capture_buffer.test.ts
```

Expected: all CaptureBuffer tests pass, including invalid atomicity,
stale-summary exclusion, repeated Crop, and append-after-Crop.

- [ ] **Step 6: Commit the buffer Task atomically**

```bash
git add apps/creator-web/src/capture/capture_buffer.ts \
  apps/creator-web/test/capture_buffer.test.ts
git diff --cached --check
git commit -m "feat(creator): crop capture buffer"
```

Inspect the committed file list and ensure no planning, version, UI, generated,
or unrelated file entered this commit.

---

### Task 2: Expose Crop through reducer-owned trimming state

**Files:**

- Modify: `apps/creator-web/test/capture_state.test.ts`
- Modify: `apps/creator-web/src/state/capture_state.ts`
- Modify: `apps/creator-web/test/capture_panel.test.tsx`
- Modify: `apps/creator-web/src/components/capture_panel.tsx`

**Interfaces:**

- Consumes: Task 1's `CaptureBuffer.crop(startFrame, frameCount): void`.
- Produces: `CaptureEvent` member `{kind: "crop"; frames: number}` and the
  visible **Crop to selection** control.

- [ ] **Step 1: Write reducer RED tests**

Add a test that enters `commit-error`, then crops the current selection:

```ts
const cropped = reduceCapture(failed, {kind: "crop", frames: 200_000});
expect(cropped).toMatchObject({
  phase: "trimming",
  frameCount: 200_000,
  selectionStart: 0,
  selectionFrames: 200_000,
  errorMessage: null,
  conflict: false,
  stopReason: "device-lost",
});
```

Add separate assertions that Crop is ignored outside `trimming` /
`commit-error`, and ignored when `frames` is not exactly the current
`selectionFrames`. This prevents reducer state from diverging from the buffer
revision that the panel just published.

- [ ] **Step 2: Run reducer tests and verify RED**

Run:

```bash
npm --prefix apps/creator-web test -- --run test/capture_state.test.ts
```

Expected: RED because `{kind: "crop"}` is not part of `CaptureEvent` and no
reducer branch exists.

- [ ] **Step 3: Implement the minimal reducer transition**

Add the event and case:

```ts
| {kind: "crop"; frames: number}
```

```ts
case "crop":
  return (state.phase === "trimming" || state.phase === "commit-error") &&
         Number.isInteger(event.frames) && event.frames > 0 &&
         event.frames === state.selectionFrames
    ? {...state, phase: "trimming", frameCount: event.frames,
       selectionStart: 0, selectionFrames: event.frames,
       errorMessage: null, conflict: false}
    : state;
```

Run the reducer file again and require GREEN.

- [ ] **Step 4: Write component RED tests against real buffer behavior**

Add a component test using non-uniform PCM. Record, Stop, choose a strict
subset, and assert the button is enabled. Click **Crop to selection**, then
assert:

```ts
expect(envelopeSpy).toHaveBeenLastCalledWith(400, 0, croppedLength);
expect(startSlider).toHaveValue("0");
expect(lengthSlider).toHaveValue(String(croppedLength));
expect(cropButton).toBeDisabled();
```

Click Commit and inspect the existing mock call:

```ts
expect(committedBuffer).toBe(originalBuffer);
expect(committedBuffer.frameCount).toBe(croppedLength);
expect(Array.from(committedBuffer.slice(0, croppedLength)[0]!)).toEqual(expectedPcm);
expect(selection).toEqual({startFrame: 0, frameCount: croppedLength});
```

Add a second test that reaches `commit-error`, changes to a strict selection,
clicks Crop, and proves the alert disappears and another Crop/Commit remains
possible.

- [ ] **Step 5: Run component tests and verify RED**

Run:

```bash
npm --prefix apps/creator-web test -- --run test/capture_panel.test.tsx
```

Expected: RED because the Crop control is absent.

- [ ] **Step 6: Implement the explicit Crop control**

Add the handler:

```ts
const handleCrop = () => {
  const buffer = bufferRef.current;
  if (buffer === null) return;
  buffer.crop(state.selectionStart, state.selectionFrames);
  dispatch({kind: "crop", frames: buffer.frameCount});
};
```

Render before Commit:

```tsx
<button
  type="button"
  disabled={state.selectionStart === 0 && state.selectionFrames === state.frameCount}
  onClick={handleCrop}
>
  Crop to selection
</button>
```

Do not add confirmation, Undo state, a new Commit signature, or a persisted
mutation.

- [ ] **Step 7: Run focused and complete Creator tests GREEN**

```bash
npm --prefix apps/creator-web test -- --run \
  test/capture_buffer.test.ts test/capture_state.test.ts test/capture_panel.test.tsx
npm --prefix apps/creator-web test -- --run
npm --prefix apps/creator-web run build
```

Expected: every test and the production TypeScript/Vite build passes.

- [ ] **Step 8: Commit the reducer/UI Task atomically**

```bash
git add apps/creator-web/src/state/capture_state.ts \
  apps/creator-web/src/components/capture_panel.tsx \
  apps/creator-web/test/capture_state.test.ts \
  apps/creator-web/test/capture_panel.test.tsx
git diff --cached --check
git commit -m "feat(creator): expose precommit crop"
```

Inspect the commit and final worktree status.

---

### Task 3: Integrate Product Build 1.0.30.0 and current documentation

**Files:**

- Modify: `apps/creator-web/module.json`
- Modify: `apps/creator-web/package.json`
- Modify: `apps/creator-web/package-lock.json`
- Modify: Creator test files containing the active Host version literal
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/assembly.lock.json` through stable tooling
- Modify: `products/lmdj/src/compiled_assembly.cpp` through stable tooling
- Modify: `products/lmdj/CMakeLists.txt`
- Modify: `products/lmdj/README.md`
- Modify: `products/lmdj/generated/web-runtime-identity.json`
- Modify: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/module_graph_test.py`
- Modify: `docs/quality/2026-08-17-machine-task-todo.md`
- Create: `docs/quality/2026-08-24-creator-capture-precommit-crop.md`
- Modify: current Portal pages listed in the design Documentation Impact
  section, including `apps/architecture-portal/docs/product/workflows.mdx`
- Modify: `apps/architecture-portal/test/repo-facts.test.mjs`

**Interfaces:**

- Consumes: completed Tasks 1-2 and approved version allocation.
- Produces: coherent Product `1.0.30.0` / Creator `1.4.0` source identity and
  current documentation ready for snapshot freezing.

- [ ] **Step 1: Update authoritative JSON identities first**

Set only these public identities:

```json
// products/lmdj/version.json
{"milestone": 1, "minor": 0, "build": 30, "patch": 0}

// apps/creator-web/module.json and package.json
{"version": "1.4.0"}

// products/lmdj/assembly.json fragments
{"product": {"id": "lmdj", "version": "1.0.30.0"}}
{"id": "creator-web", "version": "1.4.0"}
```

Use `npm --prefix apps/creator-web install --package-lock-only` to update the
lockfile; do not hand-edit lock integrity or package graph fields.

- [ ] **Step 2: Regenerate compiled Assembly, lock, and Web identity**

Run the repository's stable commands:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py --repo-root .
```

Do not hand-enter Assembly hashes or generated identity payloads.

- [ ] **Step 3: Update exact version consumers and current truth**

Replace active `1.3.6` / `1.0.29.0` assertions with `1.4.0` / `1.0.30.0` only
where they describe current authority. Preserve historical `1.0.29.0` and
rejected `1.0.28.0` evidence as history.

Current Portal prose must state:

- Crop is implemented only for ephemeral pre-commit capture;
- buffer PCM and peaks are atomically rebuilt and rebased;
- persisted Asset editing, Undo, automatic silence trimming, and other DSP are
  not implemented;
- automated tests do not claim new physical microphone/hearing/platform QA;
- tag, Release, deploy, publication, and Channel states remain unclaimed.

Mark E3 implemented by #213 in the machine ledger. The new quality record must
map every design acceptance row to named unit/component/Proof evidence without
claiming remote merge or main CI before those events occur.

- [ ] **Step 4: Run identity and current-document gates**

```bash
python3 scripts/version.py verify --version-file products/lmdj/version.json
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
npm --prefix apps/creator-web test -- --run
npm --prefix apps/creator-web run build
scripts/architecture-portal.sh check
```

Expected: every command passes and Portal reports Product `1.0.30.0`, Creator
`1.4.0`, 37 valid pages, deterministic diagrams, and valid current routes.

- [ ] **Step 5: Commit Product/version/current-doc integration**

Stage only the declared version, generated identity, current Portal, quality,
and literal-consumer files. Inspect `git diff --cached --name-only` and
`git diff --cached --check`, then commit:

```bash
git commit -m "chore(product): allocate precommit crop build"
```

The source must be clean after the commit so snapshot provenance can bind this
exact revision.

---

### Task 4: Run complete source verification

**Files:** none unless a test-first correction is required.

**Interfaces:**

- Consumes: clean committed Product `1.0.30.0` source from Tasks 1-3.
- Produces: local source proof suitable for immutable snapshot generation.

- [ ] **Step 1: Run complete Creator Proof**

```bash
scripts/creator-web.sh proof
```

Expected: clean-source build, reproducible package, Python host checks,
platform tests, Chromium lane, and declared WebKit boundary all pass.

- [ ] **Step 2: Run Core and Portal proof layers**

```bash
scripts/core.sh proof
scripts/architecture-portal.sh check
python3 scripts/version.py verify --version-file products/lmdj/version.json
```

Expected: all pass. If any failure reveals a product defect, add a focused
failing regression test before changing production code and commit only the
bounded correction.

- [ ] **Step 3: Verify source commit boundary**

```bash
git status --short
git log -1 --oneline
```

Expected: empty status and the exact source revision that will be recorded by
the `1.0.30.0` snapshot.

---

### Task 5: Freeze immutable Product Build 1.0.30.0 evidence

**Files:** generated immutable Portal snapshot, sidebar, diagram, versions
manifest, and provenance files only.

**Interfaces:**

- Consumes: Task 4's clean committed exact source revision.
- Produces: immutable `/versions/1.0.30.0/` canary documentation evidence.

- [ ] **Step 1: Generate the snapshot from the clean source**

```bash
scripts/architecture-portal.sh version 1.0.30.0 canary
```

Expected: the command records Product `1.0.30.0`, Creator `1.4.0`, exact source
commit/tree/time, Assembly lock hash, complete document/sidebar/diagram
inventory, and refuses any existing snapshot path.

- [ ] **Step 2: Verify immutable provenance and all identities**

```bash
scripts/architecture-portal.sh check
python3 scripts/version.py verify --version-file products/lmdj/version.json
git diff --check
```

Inspect metadata and confirm the source revision is the Task 3/4 source commit,
not the later snapshot commit.

- [ ] **Step 3: Commit only generated immutable evidence**

```bash
git add apps/architecture-portal/versions.json \
  apps/architecture-portal/versioned_docs/version-1.0.30.0 \
  apps/architecture-portal/versioned_sidebars/version-1.0.30.0-sidebars.json \
  apps/architecture-portal/static/versions/1.0.30.0 \
  apps/architecture-portal/versioned_metadata/version-1.0.30.0.json
git diff --cached --check
git commit -m "docs(portal): snapshot Product Build 1.0.30.0"
```

Adjust the exact generated path list to the command's output, but stage no
mutable current docs or unrelated files in this snapshot commit.

---

### Task 6: Review, push, queue, and prove the merged result

**Files:** only targeted test-first corrections from review findings.

**Interfaces:**

- Consumes: complete clean branch with verified source and immutable snapshot.
- Produces: merged #213, closed Issue/Done Project state, and exact-main CI
  evidence without crossing release boundaries.

- [ ] **Step 1: Perform an independent branch review**

Review `origin/main...HEAD` for correctness, atomicity, stale-summary leakage,
state/buffer divergence, version drift, documentation truth, and generated
snapshot provenance. Resolve every actionable finding through a focused RED ->
GREEN cycle and a separate bounded commit.

- [ ] **Step 2: Rerun final local gates and inspect Git state**

```bash
npm --prefix apps/creator-web test -- --run
npm --prefix apps/creator-web run build
scripts/creator-web.sh proof
scripts/core.sh proof
scripts/architecture-portal.sh check
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: all gates pass and the worktree is clean.

- [ ] **Step 3: Push and open the exact-head Pull Request**

Push only the feature branch. The PR body must include:

```text
Documentation impact: required
Affected portal pages: /overview/ /assembly/lmdj/ /core/modules/web-runtime-platform/ /hosts/overview/ /hosts/creator-web/ /hosts/web-runtime/ /platform/input/ /platform/web-runtime/ /product/capability-map/ /product/workflows/ /operations/testing-and-proof/ /operations/version-and-release/
Reason: Creator adds pre-commit Crop and Product/Host identities plus immutable evidence change.
```

Also declare Product `1.0.30.0`, Creator `1.4.0`, exact verification, release
boundaries, and `Closes #213`.

- [ ] **Step 4: Merge only through `merge:queue`**

Add the authorized label, require full exact-head CI and the queue's closed
report, then verify independently:

- PR state and squash merge SHA;
- validated head tree equals merge tree;
- `origin/main` equals the merge SHA;
- #213 is CLOSED and Project status is Done; and
- a full post-merge main CI run succeeds on the exact merge SHA.

Do not create or push a tag, Release, deployment, publication, or Channel
promotion.

## Version Management

- Product Build: `1.0.29.0 -> 1.0.30.0` for the approved #213 Crop capability.
- Creator Web Host: `1.3.6 -> 1.4.0`, backwards-compatible capability MINOR.
- Creator Host API: remains `1`.
- Core Modules, Providers, Contracts, persisted Project, Formal Web Runtime
  Host, CLI, MCP, and Native Test Host: version impact none because their
  public boundaries and identities do not change.
- Stage 9 remains Product Build `1.0.31.0`.
- Snapshot generation records `1.0.30.0 · canary` evidence only; it does not
  authorize or prove a tag, Release, deployment, publication, or promotion.

## Documentation Impact

Documentation impact: required.

Affected Portal pages:

- `/overview/`
- `/assembly/lmdj/`
- `/core/modules/web-runtime-platform/`
- `/hosts/overview/`
- `/hosts/creator-web/`
- `/hosts/web-runtime/`
- `/platform/input/`
- `/platform/web-runtime/`
- `/product/capability-map/`
- `/product/workflows/`
- `/operations/testing-and-proof/`
- `/operations/version-and-release/`

Reason: Creator gains real pre-commit Crop, Product/Creator identities and
automated evidence change, and Product Build `1.0.30.0` requires a matching
immutable Portal snapshot. Architecture diagrams do not change because no
Host/Platform/Facade/Contract/Provider/Project boundary changes.
