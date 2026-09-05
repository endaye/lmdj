# Safari Capture Focus-Loss Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep an ordinary Sample-mode capture's retained trim dialog visible after focus loss without changing the armed-Pad Sequence overlay contract.

**Architecture:** Make the Sequence reducer reject `trim-overlay` unless a live Sequence session is already recording or waiting for a Pattern boundary. Exercise that invariant with a RED reducer test, then add one packaged focus-loss journey that runs with deterministic non-zero capture input in Chromium and Playwright WebKit. Keep the CSS and capture lifecycle unchanged, and update only current Portal truth while the failed `1.0.41.0` evidence remains immutable.

**Tech Stack:** React 19, TypeScript 7, Vitest, Playwright 1.62.1, Web Audio API, Docusaurus Architecture Portal, Bash.

## Global Constraints

- Work only in `/Users/endaye/Projects/lmdj/.worktrees/issue-625-safari-capture-focus-loss` on `fix/625-safari-capture-focus-loss`; never edit protected `main`.
- `reduceSequence` is the authority for whether a Sequence trim overlay exists.
- Do not change Capture buffering, microphone ownership, audio recovery, trim math, modal layout, or `.sample-overlay-host` CSS.
- Do not change Project Truth, Runtime Snapshot, public Contracts, Providers, active manifests, Product Build, or immutable Portal snapshots.
- Version impact: required at integration, none in this functional task. Stage 10 Task 10 owns the planned `1.0.42.0` allocation.
- Documentation impact: required for `/hosts/creator-web/` and `/operations/testing-and-proof/` current routes.
- The failed `1.0.41.0` M7 evidence, Stage 8B acceptance row, manual TODO, and outstanding-work row stay unchanged until a fixed Build is deployed and #244 is rerun from the beginning.
- Chromium/WebKit automation proves state and rendering, not physical Safari microphone behavior or hearing.
- Stage only files declared by this plan; preserve all unrelated worktrees and user changes.

## File Structure

- `apps/creator-web/src/state/sequence_state.ts`: enforce the owner requirement for the existing `trim-overlay` transition.
- `apps/creator-web/test/sequence_state.test.ts`: prove an ownerless request is rejected and the existing owned Sequence transitions remain valid.
- `tests/platform/web/creator/creator_web_capture.spec.mjs`: drive ordinary Sample capture through non-zero frames and focus loss, then assert retained UI and exported Sequence state.
- `tests/platform/web/playwright.config.mjs`: add the focused WebKit capture project.
- `scripts/creator-web.sh`: include the WebKit regression project in the stable Creator proof.
- `apps/architecture-portal/docs/hosts/creator-web.mdx`: record that source automation covers the ownerless overlay while physical M7 remains failed.
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`: describe the Chromium/WebKit regression boundary and its physical-evidence limit.

---

### Task 1: Reject ownerless Sequence overlays and prove focus-loss recovery

**Files:**
- Modify: `apps/creator-web/src/state/sequence_state.ts`
- Modify: `apps/creator-web/test/sequence_state.test.ts`
- Modify: `tests/platform/web/creator/creator_web_capture.spec.mjs`
- Modify: `tests/platform/web/playwright.config.mjs`
- Modify: `scripts/creator-web.sh`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Interfaces:**
- Consumes: `reduceSequence(state: SequenceState, action: SequenceAction): SequenceState`, existing CapturePanel phase events, `report(page)`, `recordAtLeast(page, padLabel, seconds)`, and the packaged Creator proof server.
- Produces: the stronger invariant that `{type: "trim-overlay"}` changes state only from an owned `recording` or `switch-pending` Sequence; Playwright project `creator-capture-webkit`; one cross-browser journey titled `ordinary Sample focus loss keeps the retained trim dialog visible`.

- [ ] **Step 1: Write the failing reducer regression**

Replace the ownerless-overlay assertions inside `represents recovery and trimming while rejecting impossible transitions` with:

```ts
const ownerlessOverlay = reduceSequence(initialSequenceState, {type: "trim-overlay"});
expect(ownerlessOverlay).toBe(initialSequenceState);
expect(reduceSequence(ownerlessOverlay, {type: "trim-closed"}))
  .toBe(initialSequenceState);
```

Leave `keeps an active Sequence session beneath the armed-Pad trim overlay` and `keeps trim overlay while accepting only exact switch authority` unchanged; they are the preservation gates for the valid journey.

- [ ] **Step 2: Run the reducer test and confirm RED**

Run:

```bash
npm --prefix apps/creator-web test -- --run test/sequence_state.test.ts
```

Expected: FAIL because the current reducer changes the initial state to phase `trim-overlay`.

- [ ] **Step 3: Implement the minimal reducer guard**

Replace only the `trim-overlay` case in `apps/creator-web/src/state/sequence_state.ts`:

```ts
case "trim-overlay":
  return ["recording", "switch-pending"].includes(state.phase) &&
    state.sessionId !== null
    ? {...state, phase: "trim-overlay"}
    : state;
```

Do not gate this in `CapturePanel`, add a new action, or modify CSS. The reducer must reject an invalid ownerless transition regardless of caller.

- [ ] **Step 4: Run the focused state and component tests and confirm GREEN**

Run:

```bash
npm --prefix apps/creator-web test -- --run \
  test/sequence_state.test.ts \
  test/capture_panel.test.tsx \
  test/workspace_shell.test.tsx
```

Expected: 3 files pass, including the new ownerless rejection and the existing blur/hidden message plus armed-Sequence preservation coverage.

- [ ] **Step 5: Add deterministic WebKit capture input at the browser boundary**

At the top of `tests/platform/web/creator/creator_web_capture.spec.mjs`, add:

```js
const WEBKIT_GRANTED = "creator-capture-webkit";

async function installSyntheticWebKitCapture(page) {
  await page.addInitScript(() => {
    const resources = new Set();
    Object.defineProperty(window, "__LMDJ_CAPTURE_TEST_RESOURCES__", {
      configurable: false,
      enumerable: false,
      value: resources,
      writable: false,
    });
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: async () => {
        const context = new AudioContext({sampleRate: 48_000});
        const oscillator = context.createOscillator();
        const destination = context.createMediaStreamDestination();
        oscillator.frequency.value = 440;
        oscillator.connect(destination);
        oscillator.start();
        await context.resume();
        const track = destination.stream.getAudioTracks()[0];
        const nativeStop = track.stop.bind(track);
        const resource = {context, oscillator};
        resources.add(resource);
        Object.defineProperty(track, "stop", {
          configurable: true,
          value: () => {
            nativeStop();
            try { oscillator.stop(); } catch { /* already stopped */ }
            void context.close();
            resources.delete(resource);
          },
        });
        return destination.stream;
      },
    });
  });
}
```

This seam exists only inside the Playwright page before the packaged app loads. It must not be added to `main.tsx`, `AppProps`, Runtime seams, or production globals.

- [ ] **Step 6: Let report export operate while the modal makes the background inert**

Change the existing helper to preserve its default behavior and add an explicit forced path:

```js
async function report(page, options = {}) {
  const downloadPromise = page.waitForEvent("download");
  const button = page.getByRole("button", {name: "Export report"});
  if (options.force === true) {
    await button.evaluate((element) => element.click());
  } else {
    await button.click();
  }
  return JSON.parse(await readFile(await (await downloadPromise).path(), "utf8"));
}
```

No existing caller needs to change.

- [ ] **Step 7: Add the integrated ordinary Sample focus-loss journey**

Add this test after `records, trims and commits a capture onto an empty Pad`:

```js
test("ordinary Sample focus loss keeps the retained trim dialog visible", async ({page}, testInfo) => {
  test.skip(![GRANTED, WEBKIT_GRANTED].includes(testInfo.project.name));
  test.setTimeout(600_000);
  if (testInfo.project.name === WEBKIT_GRANTED) {
    await installSyntheticWebKitCapture(page);
  }
  await page.goto("/index.html");
  await importV1SampleProject(page);
  await enterSampleEditor(page);
  await selectPadWithoutPress(page, "Pad A1 — empty");
  const panel = await recordAtLeast(page, "Pad A1", 1);

  await page.evaluate(() => window.dispatchEvent(new Event("blur")));

  await expect(panel).toContainText("Recording stopped: the window lost focus.");
  await expect(panel.getByRole("img", {name: "Pad A1 capture waveform"})).toBeVisible();
  await expect(panel.getByRole("slider", {name: "Pad A1 Selection length"})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Commit"})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Discard"})).toBeVisible();
  await expect(panel.getByRole("button", {name: "Close"})).toBeVisible();
  await expect(page.locator(".sample-overlay-host")).toHaveCount(0);

  const evidence = await report(page, {force: true});
  expect(evidence.sequence.semantic_state).toBe("stopped");
  expect(evidence.sequence.session_id).toBeNull();

  await panel.getByRole("button", {name: "Discard"}).click();
  await expect(panel.getByRole("button", {name: "Record into Pad A1"})).toBeVisible();
});
```

The test must use an empty Pad so Discard cannot be confused with replacement confirmation. Do not use wall-clock sleep; `recordAtLeast` is the non-zero-frame authority.

- [ ] **Step 8: Register the focused WebKit project**

Add this project immediately after `creator-capture-chromium` in `tests/platform/web/playwright.config.mjs`:

```js
{
  name: "creator-capture-webkit",
  testMatch: captureSpec,
  grep: /ordinary Sample focus loss keeps the retained trim dialog visible/,
  use: { ...devices["Desktop Safari"] },
},
```

The project has no Chromium fake-device flags and runs only the new journey. The test installs its deterministic Web Audio MediaStream before navigation.

- [ ] **Step 9: Add WebKit to the stable Creator proof**

In `run_browser_gate` in `scripts/creator-web.sh`, add this invocation after the granted Chromium capture project and before the denied Chromium project:

```bash
LMDJ_WEB_RESULTS_SLOT=capture-webkit \
  LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
  LMDJ_CREATOR_WEB_BASE_URL="http://127.0.0.1:$port" \
  LMDJ_CREATOR_WEB_BUNDLE="$bundle" \
  LMDJ_CREATOR_WEB_SAMPLE_BUNDLE="$sample_bundle" \
  npm --prefix "$web_test_root" test -- \
    --project=creator-capture-webkit "$capture_relative" || status=$?
```

Keep the existing Chromium granted and denied projects unchanged.

- [ ] **Step 10: Update current Portal truth without rewriting failed evidence**

After the current M7 failure paragraph in `apps/architecture-portal/docs/hosts/creator-web.mdx`, add:

```mdx
#625 的 current-source 修复门要求 Sequence reducer 拒绝没有 active session 的
`trim-overlay`，并由 Chromium 与 Playwright WebKit 的确定性非零 Capture journey
验证 focus loss 后 retained waveform、stop reason、selection、Commit/Discard/Close
仍可见。该自动化只证明状态与渲染边界；在修复进入已部署 Product Build 并从头
重跑 #244 前，M7 仍为 `FAIL`，不能升级为物理 Safari `PASS`。
```

After the current M7 failure paragraph in `apps/architecture-portal/docs/operations/testing-and-proof.mdx`, add:

```mdx
#625 增加 ownerless Sequence-overlay 回归门：普通 Sample Capture 在 Chromium 与
Playwright WebKit 收到非零帧后触发 focus loss，必须继续显示 retained waveform、
明确 stop reason、selection 与 Commit/Discard/Close，导出报告保持 Sequence
`stopped` / `session_id: null`；active armed-Pad Sequence overlay 的既有 gate 保持
不变。此门不使用真实 Safari 麦克风，也不替代修复部署后 #244 的完整 M7 重跑。
```

Do not edit `docs/release-evidence/2026-09-04-stage8b-m7-macos-safari-capture-1.0.41.0.md`, `docs/quality/2026-08-16-stage8b-pad-capture-acceptance.md`, `docs/quality/2026-08-17-manual-verification-todo.md`, or `docs/quality/2026-08-16-outstanding-work-before-stage9.md` in this task.

- [ ] **Step 11: Run all pre-commit verification**

Run:

```bash
npm --prefix apps/creator-web test -- --run
scripts/creator-web.sh build
scripts/creator-web.sh test
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
```

Expected: every command exits 0; Product Build remains `1.0.41.0`; Portal reports the current snapshot still matches repository truth. If WebKit setup or build prerequisites fail, diagnose and fix the test boundary without weakening or skipping the required WebKit journey.

- [ ] **Step 12: Stage exactly the declared files and inspect the atomic diff**

Run:

```bash
git add \
  apps/creator-web/src/state/sequence_state.ts \
  apps/creator-web/test/sequence_state.test.ts \
  tests/platform/web/creator/creator_web_capture.spec.mjs \
  tests/platform/web/playwright.config.mjs \
  scripts/creator-web.sh \
  apps/architecture-portal/docs/hosts/creator-web.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --name-only
git diff --cached --check
git diff --cached
```

Expected: exactly seven declared files are staged; no version, Assembly, immutable snapshot, failed evidence, manual ledger, or unrelated worktree file appears.

- [ ] **Step 13: Commit the verified implementation**

Run:

```bash
git commit -m "fix(creator): keep capture recovery visible after focus loss (refs #625)"
```

Expected: one Conventional Commit containing only the seven declared files. Use `refs #625`, not `fixes #625`, because deployment and physical M7 remain outstanding.

- [ ] **Step 14: Run the clean-tree packaged browser proof**

Run:

```bash
scripts/creator-web.sh proof
```

Expected: two clean distributions are byte-identical; Creator tests pass; the granted Chromium, focused WebKit, denied Chromium, and other packaged Creator browser gates pass; final output includes `Creator Web Proof: PASS`.

If proof fails, do not push or report completion. Reproduce the failing project directly against the retained proof server/output, return to the RED/GREEN cycle, make a separate corrective commit only after its focused checks pass, then rerun the complete proof.

- [ ] **Step 15: Inspect the committed boundary and final worktree**

Run:

```bash
git show --stat --oneline --decorate HEAD
git show --format= --name-only HEAD
git status --short --branch
```

Expected: the implementation commit lists exactly the declared files; the worktree is clean and ahead of `origin/main`; no push, PR, merge, deployment, Issue closure, or physical acceptance mutation has occurred.
