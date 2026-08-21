# Web Capability Probe Timeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the packaged Web Runtime Host tolerate a genuinely supported Control Worker whose capability result is delayed beyond two seconds, while reporting an exhausted probe deadline as `HOST_TIMEOUT` and then completing Issue #166's fixed-session stress acceptance.

**Architecture:** Preserve one real Blob Control Worker and the existing OPFS operations. Replace the timeout-to-negative fallback with a named 15-second deadline that rejects a typed `HOST_TIMEOUT`, expose only a test seam for shortening that deadline, and prove both delayed success and deadline expiry in the packaged Chromium distribution. Update current Portal truth without changing identity manifests or freezing a Product Build snapshot.

**Tech Stack:** JavaScript ES modules, Node test runner, Playwright Chromium/WebKit, Emscripten packaged Web Runtime Host, Python source-boundary tests, Docusaurus Architecture Portal, GitHub Actions Integration Queue.

## Global Constraints

- Work from a fresh `fix/issue-247-capability-probe-timeout` branch in an isolated worktree based on the latest `origin/main`; never modify `main` directly.
- Follow strict TDD: add the packaged browser regressions and observe the expected RED before modifying `runtime_session.mjs`.
- Keep one probe attempt. Do not add retry, backoff, capability cache, fallback storage, or another Worker.
- The production default is exactly `15_000ms`; timeout is `HOST_TIMEOUT`; only an actual negative result is `UNSUPPORTED_WEB_RUNTIME`.
- Keep Project Truth, Runtime Snapshot, Application Facade, Product Assembly, manifest identity, Contract and Provider boundaries unchanged.
- Version impact: none. Do not edit any `module.json`, Host manifest, `products/lmdj/**`, Assembly/lock, schema, generated identity, tag, release intent or Channel state.
- Documentation impact: required for current `/core/modules/web-runtime-platform/`, `/platform/web-runtime/`, and `/operations/testing-and-proof/`; do not change diagrams or versioned snapshots.
- The implementation Task is one reviewable Conventional Commit. Do not commit the intermediate RED state.
- Push, Pull Request, review, required checks and Integration Queue merge are authorized for this Task; release, deployment and Channel promotion are not.

---

### Task 1: Implement and prove the bounded capability-probe classification

**Files:**
- Modify: `tests/platform/web/host/web_runtime_host_browser.spec.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Interfaces:**
- Consumes: existing `createRuntimeSession({seams})`, `window.__LMDJ_WEB_HOST_SEAMS__`, packaged Host `#host-state`, and Runtime Session `diagnostics()`.
- Produces: internal `capabilityProbeTimeoutMs: positive safe integer` seam, default `CONTROL_WORKER_CAPABILITY_PROBE_TIMEOUT_MS = 15_000`, delayed-response packaged proof, and exact `HOST_TIMEOUT` deadline classification.

- [ ] **Step 1: Create the isolated implementation worktree and establish a clean baseline**

```bash
git -C /Users/endaye/Projects/lmdj fetch origin --prune
git -C /Users/endaye/Projects/lmdj worktree add \
  /Users/endaye/Projects/lmdj/.worktrees/issue-247-capability-probe-timeout \
  -b fix/issue-247-capability-probe-timeout origin/main
cd /Users/endaye/Projects/lmdj/.worktrees/issue-247-capability-probe-timeout
scripts/web-runtime-host.sh build
node --test packages/web-runtime-platform/test/runtime_session.test.mjs
python3 apps/web-runtime-host/test/web_host_source_boundary_test.py
git status --short --branch
```

Expected: build/tests pass and the implementation worktree is clean on the declared `fix/` branch.

- [ ] **Step 2: Add the timeout-seam construction regression**

Replace the existing fixture header in
`packages/web-runtime-platform/test/runtime_session.test.mjs` with this header, then add the exact
conditional seam property below beside `capabilities`:

```javascript
function fixture({
  send,
  browserDocument = {},
  browserWindow = {},
  navigator = {},
  capabilities,
  capabilityProbeTimeoutMs,
  inputConfiguration = {},
  runtimeTransport,
  runtimeTerminator,
  inputOwnership,
  manifestSource = {
    resourceLimits: {imported_wav_bytes: 1_048_576},
  },
} = {}) {
```

```javascript
...(capabilityProbeTimeoutMs === undefined
  ? {}
  : {capabilityProbeTimeoutMs}),
```

Add the following focused regression after the assembly identity/capability test:

```javascript
test("accepts only a positive safe integer capability probe timeout seam", () => {
  for (const invalid of [
    0,
    -1,
    1.5,
    Number.MAX_SAFE_INTEGER + 1,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    null,
    "15000",
  ]) {
    assert.throws(
      () => fixture({capabilityProbeTimeoutMs: invalid}),
      /Capability probe timeout must be a positive safe integer/,
    );
  }
  const {session} = fixture({capabilityProbeTimeoutMs: 25});
  assert.equal(typeof session.start, "function");
});
```

Run it before production changes:

```bash
node --test --test-name-pattern='positive safe integer capability probe timeout' \
  packages/web-runtime-platform/test/runtime_session.test.mjs
```

Expected: RED because the current controller ignores every invalid value and `assert.throws`
reports a missing expected exception.

- [ ] **Step 3: Add the delayed real-Worker init-script helper**

Add a helper near `installTransportObservability(page)` that wraps only Blob Workers. The wrapper must delay delivery to the registered `message` listener while leaving the native Worker and its OPFS code intact, preserve existing seams, and expose cleanup counts:

```javascript
async function installCapabilityProbeScheduling(page, {
  delayMs,
  timeoutMs = null,
  workerErrorMs = null,
}) {
  await page.addInitScript(({ delayMs, timeoutMs, workerErrorMs }) => {
    const NativeWorker = globalThis.Worker;
    const nativeRevokeObjectURL = URL.revokeObjectURL.bind(URL);
    const observations = { revocations: 0, terminations: 0 };
    let capabilityProbeClaimed = false;
    let capabilityProbeUrl = null;
    globalThis.__lmdjCapabilityProbeScheduling = observations;
    globalThis.Worker = class ScheduledCapabilityWorker extends NativeWorker {
      constructor(url, options) {
        super(url, options);
        const candidateUrl = String(url);
        this.isCapabilityProbe =
          !capabilityProbeClaimed && candidateUrl.startsWith("blob:");
        if (this.isCapabilityProbe) {
          capabilityProbeClaimed = true;
          capabilityProbeUrl = candidateUrl;
        }
      }

      addEventListener(type, listener, options) {
        if (
          this.isCapabilityProbe &&
          type === "error" &&
          workerErrorMs !== null
        ) {
          setTimeout(() => listener.call(this, new Event("error")), workerErrorMs);
          return;
        }
        if (!this.isCapabilityProbe || type !== "message") {
          return super.addEventListener(type, listener, options);
        }
        return super.addEventListener(type, (event) => {
          setTimeout(() => listener.call(this, event), delayMs);
        }, options);
      }

      terminate() {
        if (this.isCapabilityProbe) observations.terminations += 1;
        return super.terminate();
      }
    };
    URL.revokeObjectURL = (url) => {
      if (String(url) === capabilityProbeUrl) observations.revocations += 1;
      return nativeRevokeObjectURL(url);
    };
    if (timeoutMs !== null) {
      globalThis.__LMDJ_WEB_HOST_SEAMS__ = {
        ...(globalThis.__LMDJ_WEB_HOST_SEAMS__ ?? {}),
        capabilityProbeTimeoutMs: timeoutMs,
      };
    }
  }, { delayMs, timeoutMs, workerErrorMs });
}
```

This exact first-claim rule is part of the regression contract: later Blob Workers and later Blob URL
revocations must not be delayed or counted. Production OPFS operations still execute inside the claimed
Worker.

- [ ] **Step 4: Write the three Chromium regressions before production code**

Add Chromium-only serial tests before the long packaged journey:

```javascript
test("Chromium packaged capability probe tolerates delayed Control Worker response", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await installCapabilityProbeScheduling(page, { delayMs: 2_500 });
  await openPackagedHost(page);
  expect(await page.evaluate(() => ({
    capabilities: window.lmdjWebRuntimeController.diagnostics().capabilities,
    cleanup: window.__lmdjCapabilityProbeScheduling,
  }))).toMatchObject({
    capabilities: {
      opfs: true,
      opfsSyncAccessHandle: true,
      opfsWritableReplace: true,
    },
    cleanup: { revocations: 1, terminations: 1 },
  });
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close()))
    .toBe(true);
});

test("Chromium packaged capability probe deadline reports HOST_TIMEOUT", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await installCapabilityProbeScheduling(page, {
    delayMs: 100,
    timeoutMs: 25,
  });
  await installTransportObservability(page);
  await page.goto("/index.html");
  await expect(page.locator("#host-state")).toHaveText("failed");
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "HOST_TIMEOUT",
  });
  await page.waitForTimeout(125);
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
    state: document.querySelector("#host-state").textContent,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "HOST_TIMEOUT",
    state: "failed",
  });
});

test("Chromium packaged capability probe Worker error fails closed and cleans up", async ({
  browserName,
  page,
}) => {
  test.skip(browserName !== "chromium");
  await installCapabilityProbeScheduling(page, {
    delayMs: 100,
    workerErrorMs: 0,
  });
  await installTransportObservability(page);
  await page.goto("/index.html");
  await expect(page.locator("#host-state")).toHaveText("failed");
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "UNSUPPORTED_WEB_RUNTIME",
  });
  await page.waitForTimeout(125);
  expect(await page.evaluate(() => ({
    cleanup: window.__lmdjCapabilityProbeScheduling,
    errorCode: window.lmdjWebRuntimeController.diagnostics().error_code,
    state: document.querySelector("#host-state").textContent,
  }))).toEqual({
    cleanup: { revocations: 1, terminations: 1 },
    errorCode: "UNSUPPORTED_WEB_RUNTIME",
    state: "failed",
  });
});
```

Keep equality assertions exact after observing the real packaged shape; do not weaken them to truthiness or accept both error codes.

- [ ] **Step 5: Run the focused regressions and verify RED**

```bash
node --test --test-name-pattern='positive safe integer capability probe timeout' \
  packages/web-runtime-platform/test/runtime_session.test.mjs
scripts/web-runtime-host.sh proof
```

Expected: the Node case is RED because invalid seams are accepted, and packaged proof is RED in
`Chromium packaged capability probe tolerates delayed Control Worker response` because the Host reaches
`failed`/`UNSUPPORTED_WEB_RUNTIME` at the old 2-second boundary. Neither failure may be a syntax,
fixture, browser-setup or unrelated existing error.

- [ ] **Step 6: Implement the minimal production deadline semantics**

In `packages/web-runtime-platform/web/runtime_session.mjs`, add the constant near the other Host budgets:

```javascript
const CONTROL_WORKER_CAPABILITY_PROBE_TIMEOUT_MS = 15_000;
```

Replace `probeControlWorkerCapabilities` and `defaultCapabilities` with this complete block:

```javascript
async function probeControlWorkerCapabilities(scope, timeoutMs) {
  if (typeof scope.Worker !== "function" || typeof scope.Blob !== "function") {
    return {
      opfs: false,
      opfsSyncAccessHandle: false,
      opfsWritableReplace: false,
    };
  }
  const source = `
    self.onmessage = async (event) => {
      const probeName = event.data;
      let root = null;
      let sync = null;
      let writable = null;
      const result = {
        opfs: false,
        opfsSyncAccessHandle: false,
        opfsWritableReplace: false,
      };
      try {
        root = await navigator.storage.getDirectory();
        result.opfs = true;
        const file = await root.getFileHandle(probeName, {create: true});
        sync = await file.createSyncAccessHandle();
        result.opfsSyncAccessHandle = true;
        sync.close();
        sync = null;
        writable = await file.createWritable({keepExistingData: false});
        await writable.close();
        writable = null;
        result.opfsWritableReplace = true;
      } catch {}
      try { sync?.close(); } catch {}
      try { await writable?.abort(); } catch {}
      try { await root?.removeEntry(probeName); } catch {}
      self.postMessage(result);
    };
  `;
  const url = scope.URL.createObjectURL(new scope.Blob([source], {
    type: "text/javascript",
  }));
  const worker = new scope.Worker(url);
  const probeName = `.lmdj-capability-probe-${scope.crypto.randomUUID()}`;
  try {
    return await new Promise((resolvePromise, rejectPromise) => {
      const timeout = scope.setTimeout(() => {
        rejectPromise(typedError(
          "HOST_TIMEOUT",
          "Control Worker capability probe timed out",
        ));
      }, timeoutMs);
      worker.addEventListener("message", (event) => {
        scope.clearTimeout(timeout);
        resolvePromise(event.data);
      }, { once: true });
      worker.addEventListener("error", () => {
        scope.clearTimeout(timeout);
        resolvePromise({
          opfs: false,
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
        });
      }, { once: true });
      worker.postMessage(probeName);
    });
  } finally {
    worker.terminate();
    scope.URL.revokeObjectURL(url);
  }
}

async function defaultCapabilities(scope, timeoutMs) {
  const controlWorker = await probeControlWorkerCapabilities(scope, timeoutMs);
  return {
    secureContext: scope.isSecureContext === true,
    crossOriginIsolated: scope.crossOriginIsolated === true,
    sharedArrayBuffer: typeof scope.SharedArrayBuffer === "function",
    webAssembly: typeof scope.WebAssembly === "object",
    audioWorklet:
      typeof scope.AudioContext === "function" &&
      "audioWorklet" in scope.AudioContext.prototype,
    ...controlWorker,
  };
}
```

In `createRuntimeSessionController(options = {})`, resolve and validate the internal seam before `start()` can use it:

```javascript
const capabilityProbeTimeoutMs =
  options.capabilityProbeTimeoutMs === undefined
    ? CONTROL_WORKER_CAPABILITY_PROBE_TIMEOUT_MS
    : options.capabilityProbeTimeoutMs;
if (!isPositiveInteger(capabilityProbeTimeoutMs)) {
  throw new TypeError(
    "Capability probe timeout must be a positive safe integer",
  );
}
```

Pass it only to the existing formal default-capability path:

```javascript
const capabilities =
  options.capabilities ??
  (preflight === runPreflight
    ? await defaultCapabilities(window, capabilityProbeTimeoutMs)
    : {});
```

Do not modify the Worker probe body, actual-negative result, worker-error result, preflight capability set or Runtime Session state machine.

- [ ] **Step 7: Run focused GREEN checks**

```bash
node --test packages/web-runtime-platform/test/runtime_session.test.mjs
python3 apps/web-runtime-host/test/web_host_source_boundary_test.py
scripts/web-runtime-host.sh build
```

Expected: all commands PASS, including every invalid timeout value and the valid positive-safe-integer
construction case.

- [ ] **Step 8: Update current Architecture Portal truth**

Append this exact paragraph to `## 6. 状态、错误与并发` in
`apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`:

```markdown
Runtime Session 启动只运行一次真实 Control Worker/OPFS capability probe，默认等待预算为 15 秒。明确缺少 Worker/Blob、Worker 返回 negative 或 Worker error 继续 fail closed 为 `UNSUPPORTED_WEB_RUNTIME`；纯调度预算耗尽精确进入 `HOST_TIMEOUT`，不能伪造 `opfs`、`opfsSyncAccessHandle` 或 `opfsWritableReplace` 缺失。message、error 与 timeout 三条 settlement 路径都由同一 `finally` terminate Worker 并 revoke Blob URL。
```

Append this exact paragraph to `## 共享 Platform` in
`apps/architecture-portal/docs/platform/web-runtime.mdx`:

```markdown
Host preflight 的单次 Control Worker capability probe 使用 15 秒有界预算。CPU 或文件 I/O contention 可以推迟结果，但不能被解释成 OPFS primitive 缺失；明确 primitive 缺失、actual negative 或 Worker error 仍 fail closed 为 `UNSUPPORTED_WEB_RUNTIME`，deadline expiry 则为 `HOST_TIMEOUT`。无论 settle 原因如何，临时 Worker 与 Blob URL 都由 probe owner 清理。
```

Append this exact paragraph after the first paragraph of `## Web Runtime Host Proof` in
`apps/architecture-portal/docs/operations/testing-and-proof.mdx`:

```markdown
Packaged Chromium 还用真实 capability Worker 覆盖 2.5 秒 delayed result 与 test-only shortened deadline：前者必须保留三项 OPFS capability 并进入 `audio-suspended`，后者必须精确报告 `HOST_TIMEOUT`，两者都验证 Worker/Blob cleanup。Issue #166 的 branch/PR proof 之外还要求一个 pinned Linux runner 在同一固定 CPU + file-I/O contention session 中连续三次完整 `scripts/web-runtime-host.sh proof` 全部通过；不得从更大样本挑选成功运行。
```

Do not hand-enter a new Product Build, Module/Host identity, snapshot or diagram fact.

- [ ] **Step 9: Run complete local verification**

```bash
scripts/web-runtime-host.sh proof
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
git diff --check
```

Expected: packaged Chromium delayed-success, timeout and Worker-error cleanup cases pass; existing
Chromium cases pass; WebKit reports its existing structured limitation or completes smoke;
active-tree/version/Portal gates all pass.

- [ ] **Step 10: Inspect and create the one implementation commit**

```bash
set -euo pipefail
git status --short --branch
test "$(git branch --show-current)" = "fix/issue-247-capability-probe-timeout"
git diff -- \
  packages/web-runtime-platform/web/runtime_session.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  tests/platform/web/host/web_runtime_host_browser.spec.mjs \
  apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx \
  apps/architecture-portal/docs/platform/web-runtime.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git add -- \
  packages/web-runtime-platform/web/runtime_session.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  tests/platform/web/host/web_runtime_host_browser.spec.mjs \
  apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx \
  apps/architecture-portal/docs/platform/web-runtime.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --name-only
git diff --cached --check
git commit -m "fix(web-runtime): distinguish capability probe timeout"
git show --stat --oneline --decorate HEAD
git status --short --branch
```

Expected: the commit contains only the declared implementation/test/current-doc files, and the final worktree is clean.

---

### Task 2: Integrate #247 and complete #166's pressure acceptance

**Files:**
- Read: `.github/pull_request_template.md`
- Read: `.github/workflows/ci.yml`
- Read: `.github/workflows/merge-queue.yml`
- Evidence only: retained runner logs outside tracked source

**Interfaces:**
- Consumes: clean Task 1 commit, Issue #247, current `origin/main`, required-check manifest, Integration Queue report, pinned Linux Web toolchain.
- Produces: merged #247 exact SHA/tree and one auditable #166 pressure session containing three consecutive successful full proofs.

- [ ] **Step 1: Obtain independent review before publication**

Run the `requesting-code-review` skill against the exact base/head diff. Resolve every critical or important finding, rerun affected checks, and create a new atomic commit only if review requires a tracked-file modification.

Expected: reviewer reports zero unresolved critical/important findings and records the exact reviewed commit.

- [ ] **Step 2: Push and create one non-draft Pull Request**

```bash
set -euo pipefail
issue247_reviewed_head="$(git rev-parse HEAD)"
[[ "$issue247_reviewed_head" =~ ^[0-9a-f]{40}$ ]]
test "$(git branch --show-current)" = "fix/issue-247-capability-probe-timeout"
test "$(gh pr list --state open \
  --head fix/issue-247-capability-probe-timeout \
  --json number --jq 'length')" -eq 0
git push -u origin fix/issue-247-capability-probe-timeout
test "$(git ls-remote --heads origin \
  refs/heads/fix/issue-247-capability-probe-timeout | awk '{print $1}')" = \
  "$issue247_reviewed_head"
gh pr create --base main --head fix/issue-247-capability-probe-timeout \
  --title "fix(web-runtime): distinguish capability probe timeout" \
  --body '## Summary

- distinguish a delayed Control Worker capability result from an exhausted deadline
- prove delayed success, exact `HOST_TIMEOUT`, and once-only Worker/Blob cleanup in packaged Chromium
- update current Web Runtime Platform, Web Runtime, and Testing/Proof Portal truth
- relates to #166 by removing the independently diagnosed blocker to its fixed-session stress acceptance

## Related Issue

Related issue: Relates to #247

## Verification

- TDD RED: focused timeout-seam Node regression rejected no invalid values before production code
- TDD RED: packaged delayed-success case reached `failed` / `UNSUPPORTED_WEB_RUNTIME` at the old 2-second boundary
- `node --test packages/web-runtime-platform/test/runtime_session.test.mjs`
- `python3 apps/web-runtime-host/test/web_host_source_boundary_test.py`
- `scripts/web-runtime-host.sh proof`
- `bash tests/build/test_active_tree.sh`
- `python3 tests/build/version_test.py`
- `python3 scripts/version.py verify --version-file products/lmdj/version.json`
- `scripts/architecture-portal.sh check`

## CI Scope

Expected mode: focused
Expected selected lanes: portal web_toolchain web_runtime_host
Expected skipped lanes: docs_static ci_contract core_ubuntu core_asan core_coverage core_macos creator web_runtime_lab deploy_contract chameleon_lab package
`ci:full` required: no
Reason: Platform Web source selects Portal, Web Toolchain, and Web Runtime Host; Portal `.mdx` paths remain in the portal lane.

## Version Management

Version impact: none
Reason: internal timeout classification fix only; no public API/ABI, Contract, manifest, Assembly, lock, package publication, or Product Build allocation changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/ /platform/web-runtime/ /operations/testing-and-proof/
Reason: current preflight timeout behavior and packaged Proof evidence change without an architecture-boundary or identity change.

## Release Impact

Release impact: none
Candidate tag: none
Profile: none
Channel: none
Intent disposition: none
Release assets: none
Release gates: none
Reason: this Pull Request does not authorize or perform release, deployment, publication, or Channel mutation.

## Transition authority

- [x] Push/PR only; no tag, Release, deploy, publication, or Channel promotion is implied.'
issue247_pr_number="$(gh pr list --state open \
  --head fix/issue-247-capability-probe-timeout \
  --json number --jq 'if length == 1 then .[0].number else empty end')"
[[ "$issue247_pr_number" =~ ^[1-9][0-9]*$ ]]
test "$(gh pr view "$issue247_pr_number" --json headRefOid,isDraft,baseRefName \
  --jq '.headRefOid + " " + (.isDraft | tostring) + " " + .baseRefName')" = \
  "$issue247_reviewed_head false main"
```

Expected: one non-draft PR with the exact reviewed template sections and no duplicate open PR for the
branch.

- [ ] **Step 3: Verify required checks and merge through the authorized queue**

```bash
set -euo pipefail
issue247_pr_number="$(gh pr list --state open \
  --head fix/issue-247-capability-probe-timeout \
  --json number --jq '.[0].number')"
test -n "$issue247_pr_number"
git fetch origin --prune
issue247_local_head="$(git rev-parse HEAD)"
issue247_current_base="$(git rev-parse origin/main)"
issue247_pr_json="$(gh pr view "$issue247_pr_number" \
  --json state,isDraft,baseRefName,baseRefOid,headRefOid,mergeable,reviewDecision)"
jq -e \
  --arg base "$issue247_current_base" \
  --arg head "$issue247_local_head" \
  '.state == "OPEN" and .isDraft == false and .baseRefName == "main" and
   .baseRefOid == $base and .headRefOid == $head and .mergeable == "MERGEABLE" and
   .reviewDecision != "CHANGES_REQUESTED"' <<<"$issue247_pr_json"
gh pr checks "$issue247_pr_number" --required --watch --fail-fast --interval 20
if gh pr diff "$issue247_pr_number" --name-only | rg -q \
  '^(\.github/(actionlint\.yaml|workflows/(ci|merge-queue)\.yml)|scripts/ci/(change_scope|github_queue_api|merge_queue|merge_queue_watchdog|pr_gate)\.py|scripts/ci/scope_policy\.json)$'; then
  echo "queue control-plane path changed" >&2
  exit 1
fi
issue247_label_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gh pr edit "$issue247_pr_number" --add-label merge:queue
issue247_queue_run_id=""
for issue247_poll in {1..120}; do
  issue247_queue_run_id="$(gh run list --workflow merge-queue.yml \
    --event pull_request_target --limit 30 \
    --json databaseId,displayTitle,createdAt \
    --jq ".[] | select(.displayTitle == \"Merge queue / pull_request_target / PR $issue247_pr_number\" and .createdAt >= \"$issue247_label_started\") | .databaseId" \
    | head -1)"
  if [[ "$issue247_queue_run_id" =~ ^[1-9][0-9]*$ ]]; then
    break
  fi
  sleep 5
done
[[ "$issue247_queue_run_id" =~ ^[1-9][0-9]*$ ]]
gh run watch "$issue247_queue_run_id" --exit-status --interval 20
issue247_queue_evidence="/tmp/lmdj-issue247-queue-$issue247_queue_run_id"
test ! -e "$issue247_queue_evidence"
mkdir -m 700 "$issue247_queue_evidence"
gh run download "$issue247_queue_run_id" \
  --name "merge-queue-report-$issue247_queue_run_id" \
  --dir "$issue247_queue_evidence/report"
issue247_queue_report="$issue247_queue_evidence/report/merge-queue-report.json"
jq -e \
  '.ok == true and .status == "merged" and .code == "merged" and
   (.observed_base_sha | test("^[0-9a-f]{40}$")) and
   (.observed_head_sha | test("^[0-9a-f]{40}$")) and
   (.merge_sha | test("^[0-9a-f]{40}$")) and
   (.validation_run_ids | length >= 1)' "$issue247_queue_report"
issue247_validated_head="$(jq -r .observed_head_sha "$issue247_queue_report")"
issue247_validated_base="$(jq -r .observed_base_sha "$issue247_queue_report")"
issue247_validation_run_id="$(jq -r '.validation_run_ids[-1]' "$issue247_queue_report")"
issue247_validation_meta="$(gh run view "$issue247_validation_run_id" \
  --json event,headSha,status,conclusion,workflowName)"
jq -e --arg head "$issue247_validated_head" \
  '.headSha == $head and .status == "completed" and .conclusion == "success" and
   .workflowName == "Core CI" and (.event == "pull_request" or .event == "workflow_dispatch")' \
  <<<"$issue247_validation_meta"
mkdir "$issue247_queue_evidence/scope"
gh run download "$issue247_validation_run_id" \
  --name "ci-scope-$issue247_validated_head" \
  --dir "$issue247_queue_evidence/scope"
jq -e --arg base "$issue247_validated_base" --arg head "$issue247_validated_head" \
  '.schema == "lmdj.ci-scope.v2" and .base_sha == $base and .head_sha == $head and
   .mode == "full" and .trusted_head == true' \
  "$issue247_queue_evidence/scope/ci-scope.json"
issue247_validation_event="$(jq -r .event <<<"$issue247_validation_meta")"
if [[ "$issue247_validation_event" == "workflow_dispatch" ]]; then
  mkdir "$issue247_queue_evidence/validation"
  gh run download "$issue247_validation_run_id" \
    --name "queue-validation-$issue247_validation_run_id" \
    --dir "$issue247_queue_evidence/validation"
  jq -e \
    --arg prefix "mq:$issue247_queue_run_id:" \
    --argjson pr "$issue247_pr_number" \
    --arg base "$issue247_validated_base" \
    --arg head "$issue247_validated_head" \
    '.schema == "lmdj.queue-validation.v1" and .classification == "valid" and
     .queue_pr_number == $pr and (.queue_ticket | startswith($prefix)) and
     .queue_base_sha == $base and .observed_base_sha == $base and
     .queue_head_sha == $head and .observed_head_sha == $head and
     .manifest_mode == "full" and
     .trusted_head == true' \
    "$issue247_queue_evidence/validation/queue-validation.json"
fi
gh api "repos/endaye/lmdj/commits/$issue247_validated_head/check-runs?per_page=100" \
  >"$issue247_queue_evidence/check-runs.json"
jq -e '
  . as $document |
  ["core (ubuntu-latest)", "core (macos-latest)", "PR Gate"] as $expected |
  all($expected[]; . as $name |
    any($document.check_runs[];
      .name == $name and .app.id == 15368 and .conclusion == "success"))
' "$issue247_queue_evidence/check-runs.json"
issue247_merge_sha="$(jq -r .merge_sha "$issue247_queue_report")"
issue247_merge_parent="$(gh api "repos/endaye/lmdj/git/commits/$issue247_merge_sha" \
  --jq '.parents[0].sha')"
test "$issue247_validated_base" = "$issue247_merge_parent"
git fetch origin --prune
test "$(gh pr view "$issue247_pr_number" --json state,mergeCommit \
  --jq '.state + " " + .mergeCommit.oid')" = "MERGED $issue247_merge_sha"
git merge-base --is-ancestor "$issue247_current_base" "$issue247_merge_sha"
test "$(gh api "repos/endaye/lmdj/git/commits/$issue247_validated_head" --jq .tree.sha)" = \
  "$(gh api "repos/endaye/lmdj/git/commits/$issue247_merge_sha" --jq .tree.sha)"
test "$(git rev-parse origin/main)" = "$issue247_merge_sha"
```

Expected: every pre-label assertion passes, the captured queue run is numeric, the retained report is
`merged`, its final validation is exact-head/full/trusted, the three required checks come from GitHub
Actions App ID `15368` and are successful, and the squash merge tree equals the exact validated head tree.
Any failed assertion stops before the next mutation.

- [ ] **Step 4: Prepare one fixed runner pressure session from exact merged main**

Select Netcup only if its documented `vienna` SSH alias is reachable and grants non-interactive control
of its Actions runner services; otherwise use the already audited Contabo `sg` alias with the same
service-control precondition. Create a dedicated checkout without modifying an Actions checkout:

```bash
set -euo pipefail
issue247_pr_number="$(gh pr list --state merged \
  --head fix/issue-247-capability-probe-timeout \
  --json number --jq '.[0].number')"
[[ "$issue247_pr_number" =~ ^[1-9][0-9]*$ ]]
issue247_merge_sha="$(gh pr view "$issue247_pr_number" \
  --json mergeCommit --jq '.mergeCommit.oid')"
[[ "$issue247_merge_sha" =~ ^[0-9a-f]{40}$ ]]
issue247_merge_tree="$(gh api "repos/endaye/lmdj/git/commits/$issue247_merge_sha" \
  --jq .tree.sha)"
[[ "$issue247_merge_tree" =~ ^[0-9a-f]{40}$ ]]
issue247_queue_run_id="$(gh run list --workflow merge-queue.yml \
  --event pull_request_target --limit 30 \
  --json databaseId,displayTitle,conclusion \
  --jq ".[] | select(.displayTitle == \"Merge queue / pull_request_target / PR $issue247_pr_number\" and .conclusion == \"success\") | .databaseId" \
  | head -1)"
[[ "$issue247_queue_run_id" =~ ^[1-9][0-9]*$ ]]
issue247_queue_evidence="/tmp/lmdj-issue247-queue-$issue247_queue_run_id"
test -f "$issue247_queue_evidence/report/merge-queue-report.json"
if ssh -o BatchMode=yes -o ConnectTimeout=8 vienna true && \
   ssh vienna sudo -n true && \
   ssh vienna "systemd-run --help | grep -q -- '--expand-environment'"; then
  issue247_pressure_host=vienna
  issue247_runner_pattern=netcup
else
  ssh -o BatchMode=yes -o ConnectTimeout=8 sg true
  ssh sg sudo -n true
  ssh sg "systemd-run --help | grep -q -- '--expand-environment'"
  issue247_pressure_host=sg
  issue247_runner_pattern=contabo
fi
issue247_pressure_path="/tmp/lmdj-issue247-pressure-${issue247_merge_sha:0:12}"
issue247_runner_units_file="$issue247_queue_evidence/runner-units.txt"
ssh "$issue247_pressure_host" bash -s -- "$issue247_runner_pattern" \
  >"$issue247_runner_units_file" <<'REMOTE_RUNNER_UNITS'
set -euo pipefail
runner_pattern="$1"
systemctl list-unit-files 'actions.runner.endaye-lmdj.*.service' \
  --no-legend --no-pager \
  | awk -v pattern="$runner_pattern" '$1 ~ pattern {print $1}'
REMOTE_RUNNER_UNITS
test -s "$issue247_runner_units_file"
if rg -v '^actions\.runner\.endaye-lmdj\.[A-Za-z0-9_.-]+\.service$' \
  "$issue247_runner_units_file"; then
  echo "unsafe runner service name" >&2
  exit 1
fi
issue247_runner_unit_count="$(wc -l <"$issue247_runner_units_file" | tr -d ' ')"
[[ "$issue247_runner_unit_count" =~ ^[1-9][0-9]*$ ]]
test "$(sort -u "$issue247_runner_units_file" | wc -l | tr -d ' ')" -eq \
  "$issue247_runner_unit_count"
issue247_service_runner_names="$issue247_queue_evidence/service-runner-names.txt"
sed -E \
  -e 's/^actions\.runner\.endaye-lmdj\.//' \
  -e 's/\.service$//' \
  "$issue247_runner_units_file" | sort -u \
  >"$issue247_service_runner_names"
test "$(wc -l <"$issue247_service_runner_names" | tr -d ' ')" -eq \
  "$issue247_runner_unit_count"
while read -r issue247_runner_unit; do
  ssh "$issue247_pressure_host" systemctl is-active --quiet \
    "$issue247_runner_unit"
done <"$issue247_runner_units_file"
gh api 'repos/endaye/lmdj/actions/runners?per_page=100' \
  >"$issue247_queue_evidence/runners-before.json"
jq -e --arg pattern "$issue247_runner_pattern" \
  --argjson expected "$issue247_runner_unit_count" '
  [.runners[] | select(.name | ascii_downcase | contains($pattern))] as $selected |
  ($selected | length) == $expected and
  all($selected[]; .status == "online" and .busy == false)
' "$issue247_queue_evidence/runners-before.json"
issue247_api_runner_names="$issue247_queue_evidence/api-runner-names-before.txt"
jq -r --arg pattern "$issue247_runner_pattern" \
  '.runners[] | select(.name | ascii_downcase | contains($pattern)) | .name' \
  "$issue247_queue_evidence/runners-before.json" | sort -u \
  >"$issue247_api_runner_names"
cmp "$issue247_service_runner_names" "$issue247_api_runner_names"
ssh "$issue247_pressure_host" bash -s -- \
  "$issue247_merge_sha" "$issue247_pressure_path" <<'REMOTE_PREPARE'
set -euo pipefail
pressure_sha="$1"
pressure_path="$2"
test ! -e "$pressure_path"
git clone --filter=blob:none https://github.com/endaye/lmdj.git "$pressure_path"
git -C "$pressure_path" checkout --detach "$pressure_sha"
git -C "$pressure_path" lfs pull
test "$(git -C "$pressure_path" rev-parse HEAD)" = "$pressure_sha"
test -z "$(git -C "$pressure_path" status --porcelain)"
git -C "$pressure_path" rev-parse HEAD^{tree}
uname -a
node --version
python3 --version
git lfs version
REMOTE_PREPARE
printf 'issue247_pressure_host=%q\nissue247_runner_pattern=%q\nissue247_pressure_path=%q\nissue247_merge_sha=%q\nissue247_merge_tree=%q\nissue247_queue_run_id=%q\nissue247_runner_unit_count=%q\n' \
  "$issue247_pressure_host" "$issue247_runner_pattern" "$issue247_pressure_path" \
  "$issue247_merge_sha" "$issue247_merge_tree" "$issue247_queue_run_id" \
  "$issue247_runner_unit_count" \
  >"$issue247_queue_evidence/pressure-target.env"
```

Expected: all selected-pool runner services have safe exact names, are active, and map one-to-one to
online idle GitHub runners before the session; the host grants non-interactive service control; the
dedicated checkout is detached at the exact merge SHA, LFS hydrated and clean; runner/kernel/tool
identities are recorded.

- [ ] **Step 5: Run exactly three consecutive full proofs under one contention session**

Use the selected host's Actions runner services as the authoritative overlap boundary: compare the exact
service-derived and API runner-name sets, arm a three-hour automatic restoration watchdog, snapshot each
Runner diagnostic log, recheck idle state, then install a runtime condition lease and stop all mapped
services. Audit the log
delta to reject any job accepted in the idle-query/stop window and wait until GitHub reports the exact pool
offline/not busy before starting proof. Local and remote traps both remove the runtime lease and restore the exact services;
normal completion cancels the watchdog only after GitHub reports the exact pool online. The remote session
retains logs outside the checkout, checks leased/inactive isolation and contender liveness before and after
every proof, and stops at the first failure:

```bash
set -euo pipefail
issue247_pr_number="$(gh pr list --state merged \
  --head fix/issue-247-capability-probe-timeout \
  --json number --jq '.[0].number')"
[[ "$issue247_pr_number" =~ ^[1-9][0-9]*$ ]]
issue247_queue_run_id="$(gh run list --workflow merge-queue.yml \
  --event pull_request_target --limit 30 \
  --json databaseId,displayTitle,conclusion \
  --jq ".[] | select(.displayTitle == \"Merge queue / pull_request_target / PR $issue247_pr_number\" and .conclusion == \"success\") | .databaseId" \
  | head -1)"
[[ "$issue247_queue_run_id" =~ ^[1-9][0-9]*$ ]]
issue247_queue_evidence="/tmp/lmdj-issue247-queue-$issue247_queue_run_id"
test -f "$issue247_queue_evidence/pressure-target.env"
source "$issue247_queue_evidence/pressure-target.env"
[[ "$issue247_merge_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$issue247_merge_tree" =~ ^[0-9a-f]{40}$ ]]
[[ "$issue247_runner_unit_count" =~ ^[1-9][0-9]*$ ]]
issue247_runner_units_file="$issue247_queue_evidence/runner-units.txt"
test -f "$issue247_runner_units_file"
issue247_runner_units=()
while read -r issue247_runner_unit; do
  [[ "$issue247_runner_unit" =~ ^actions\.runner\.endaye-lmdj\.[A-Za-z0-9_.-]+\.service$ ]]
  issue247_runner_units+=("$issue247_runner_unit")
done <"$issue247_runner_units_file"
test "${#issue247_runner_units[@]}" -eq "$issue247_runner_unit_count"
issue247_service_runner_names="$issue247_queue_evidence/service-runner-names.txt"
test -f "$issue247_service_runner_names"
test "$(wc -l <"$issue247_service_runner_names" | tr -d ' ')" -eq \
  "$issue247_runner_unit_count"
issue247_runner_lease_root="/tmp/lmdj-issue247-runner-lease-${issue247_merge_sha:0:12}"
issue247_runner_watchdog="lmdj-issue247-runner-restore-${issue247_merge_sha:0:12}"
issue247_runner_lease_dropin="90-lmdj-issue247-pressure-lease.conf"
issue247_runner_enable_marker="/run/lmdj-issue247-runner-enable-${issue247_merge_sha:0:12}"
issue247_runners_restored=false
issue247_watchdog_created=false
restore_pressure_runners() {
  issue247_restore_status=0
  ssh "$issue247_pressure_host" bash -s -- \
    "$issue247_runner_lease_dropin" "${issue247_runner_units[@]}" \
    <<'REMOTE_RESTORE_RUNNERS' || issue247_restore_status=$?
set +e
lease_dropin="$1"
shift
runner_units=("$@")
restore_status=0
for runner_unit in "${runner_units[@]}"; do
  sudo -n rm -f -- \
    "/run/systemd/system/$runner_unit.d/$lease_dropin" \
    || restore_status=1
done
sudo -n systemctl daemon-reload || restore_status=1
sudo -n systemctl start -- "${runner_units[@]}" || restore_status=1
for runner_unit in "${runner_units[@]}"; do
  systemctl is-active --quiet "$runner_unit" || restore_status=1
  test ! -e "/run/systemd/system/$runner_unit.d/$lease_dropin" \
    || restore_status=1
done
exit "$restore_status"
REMOTE_RESTORE_RUNNERS
  if [[ "$issue247_restore_status" -ne 0 ]]; then
    echo "CRITICAL: failed to restore one or more Actions runner services; watchdog remains armed" >&2
    return 1
  fi
  issue247_runners_restored=true
}
on_pressure_exit() {
  issue247_original_status=$?
  trap - EXIT INT TERM
  set +e
  if ! restore_pressure_runners; then
    [[ "$issue247_original_status" -ne 0 ]] || issue247_original_status=2
  fi
  if [[ "$issue247_watchdog_created" == true ]]; then
    echo "runner restoration watchdog remains armed for crash recovery" >&2
  fi
  exit "$issue247_original_status"
}
trap on_pressure_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
ssh "$issue247_pressure_host" bash -s -- \
  "$issue247_runner_watchdog" "$issue247_runner_lease_dropin" \
  "${issue247_runner_units[@]}" <<'REMOTE_WATCHDOG'
set -euo pipefail
watchdog_unit="$1"
lease_dropin="$2"
shift 2
runner_units=("$@")
sudo -n systemd-run \
  --unit="$watchdog_unit" \
  --on-active=180m \
  --timer-property=AccuracySec=1min \
  --property=Type=exec \
  --expand-environment=no \
  /bin/bash -c \
  'lease_dropin="$1"; shift; for attempt in {1..10}; do for runner_unit in "$@"; do rm -f -- "/run/systemd/system/$runner_unit.d/$lease_dropin"; done; systemctl daemon-reload; systemctl start -- "$@"; all_active=true; for runner_unit in "$@"; do systemctl is-active --quiet "$runner_unit" || all_active=false; done; [[ "$all_active" == true ]] && exit 0; sleep 30; done; exit 1' \
  _ "$lease_dropin" "${runner_units[@]}"
systemctl is-active --quiet "$watchdog_unit.timer"
REMOTE_WATCHDOG
issue247_watchdog_created=true
ssh "$issue247_pressure_host" bash -s -- \
  "$issue247_runner_lease_root" "${issue247_runner_units[@]}" \
  <<'REMOTE_DIAGNOSTIC_BASELINE'
set -euo pipefail
lease_root="$1"
shift
runner_units=("$@")
test ! -e "$lease_root"
mkdir -m 700 "$lease_root"
baseline="$lease_root/runner-log-baseline.tsv"
: >"$baseline"
for runner_unit in "${runner_units[@]}"; do
  workdir="$(systemctl show "$runner_unit" -p WorkingDirectory --value)"
  [[ "$workdir" =~ ^/opt/actions-runner(-[0-9]+)?$ ]]
  sudo -n find "$workdir/_diag" -maxdepth 1 -type f \
    -name 'Runner_*.log' \
    -printf "${runner_unit}\t%p\t%i\t%s\n" >>"$baseline"
done
test -s "$baseline"
sort -o "$baseline" "$baseline"
REMOTE_DIAGNOSTIC_BASELINE
gh api 'repos/endaye/lmdj/actions/runners?per_page=100' \
  >"$issue247_queue_evidence/runners-pre-quiesce.json"
jq -e --arg pattern "$issue247_runner_pattern" \
  --argjson expected "$issue247_runner_unit_count" '
  [.runners[] | select(.name | ascii_downcase | contains($pattern))] as $selected |
  ($selected | length) == $expected and
  all($selected[]; .status == "online" and .busy == false)
' "$issue247_queue_evidence/runners-pre-quiesce.json"
issue247_pre_quiesce_names="$issue247_queue_evidence/api-runner-names-pre-quiesce.txt"
jq -r --arg pattern "$issue247_runner_pattern" \
  '.runners[] | select(.name | ascii_downcase | contains($pattern)) | .name' \
  "$issue247_queue_evidence/runners-pre-quiesce.json" | sort -u \
  >"$issue247_pre_quiesce_names"
cmp "$issue247_service_runner_names" "$issue247_pre_quiesce_names"
ssh "$issue247_pressure_host" bash -s -- \
  "$issue247_runner_lease_dropin" "$issue247_runner_enable_marker" \
  "${issue247_runner_units[@]}" <<'REMOTE_ACQUIRE_RUNNER_LEASE'
set -euo pipefail
lease_dropin="$1"
enable_marker="$2"
shift 2
runner_units=("$@")
test ! -e "$enable_marker"
for runner_unit in "${runner_units[@]}"; do
  dropin_dir="/run/systemd/system/$runner_unit.d"
  sudo -n mkdir -p "$dropin_dir"
  printf '[Unit]\nConditionPathExists=%s\n' "$enable_marker" \
    | sudo -n tee "$dropin_dir/$lease_dropin" >/dev/null
done
sudo -n systemctl daemon-reload
sudo -n systemctl stop -- "${runner_units[@]}"
for runner_unit in "${runner_units[@]}"; do
  expected="$(printf '[Unit]\nConditionPathExists=%s' "$enable_marker")"
  actual="$(sudo -n cat "/run/systemd/system/$runner_unit.d/$lease_dropin")"
  [[ "$actual" == "$expected" ]]
  ! systemctl is-active --quiet "$runner_unit"
done
REMOTE_ACQUIRE_RUNNER_LEASE
ssh "$issue247_pressure_host" bash -s -- \
  "$issue247_runner_lease_root" "${issue247_runner_units[@]}" \
  <<'REMOTE_DIAGNOSTIC_AUDIT'
set -euo pipefail
lease_root="$1"
shift
runner_units=("$@")
baseline="$lease_root/runner-log-baseline.tsv"
audit_log="$lease_root/runner-assignment-window.log"
declare -A baseline_inode baseline_size observed
while IFS=$'\t' read -r _ log_path log_inode log_size; do
  baseline_inode["$log_path"]="$log_inode"
  baseline_size["$log_path"]="$log_size"
done <"$baseline"
: >"$audit_log"
assignment_found=0
for runner_unit in "${runner_units[@]}"; do
  workdir="$(systemctl show "$runner_unit" -p WorkingDirectory --value)"
  while IFS=$'\t' read -r log_path log_inode log_size; do
    observed["$log_path"]=1
    start_byte=1
    if [[ -n "${baseline_inode[$log_path]+present}" ]]; then
      [[ "${baseline_inode[$log_path]}" == "$log_inode" ]]
      ((log_size >= baseline_size[$log_path]))
      start_byte=$((baseline_size[$log_path] + 1))
    fi
    log_delta="$(sudo -n tail -c +"$start_byte" -- "$log_path")"
    printf 'unit=%s log=%s inode=%s start_byte=%s\n%s\n' \
      "$runner_unit" "$log_path" "$log_inode" "$start_byte" "$log_delta" \
      >>"$audit_log"
    if grep -Fq 'Send job request message to worker for job' <<<"$log_delta"; then
      assignment_found=1
    fi
  done < <(sudo -n find "$workdir/_diag" -maxdepth 1 -type f \
    -name 'Runner_*.log' -printf '%p\t%i\t%s\n' | sort)
done
for log_path in "${!baseline_inode[@]}"; do
  [[ -n "${observed[$log_path]+present}" ]]
done
[[ "$assignment_found" -eq 0 ]]
REMOTE_DIAGNOSTIC_AUDIT
issue247_pool_quiesced=false
for issue247_poll in {1..60}; do
  gh api 'repos/endaye/lmdj/actions/runners?per_page=100' \
    >"$issue247_queue_evidence/runners-quiesced.json"
  if jq -e --arg pattern "$issue247_runner_pattern" \
    --argjson expected "$issue247_runner_unit_count" '
    [.runners[] | select(.name | ascii_downcase | contains($pattern))] as $selected |
    ($selected | length) == $expected and
    all($selected[]; .status == "offline" and .busy == false)
  ' "$issue247_queue_evidence/runners-quiesced.json" >/dev/null; then
    issue247_pool_quiesced=true
    break
  fi
  sleep 2
done
test "$issue247_pool_quiesced" = true
issue247_quiesced_runner_names="$issue247_queue_evidence/api-runner-names-quiesced.txt"
jq -r --arg pattern "$issue247_runner_pattern" \
  '.runners[] | select(.name | ascii_downcase | contains($pattern)) | .name' \
  "$issue247_queue_evidence/runners-quiesced.json" | sort -u \
  >"$issue247_quiesced_runner_names"
cmp "$issue247_service_runner_names" "$issue247_quiesced_runner_names"
issue247_remote_evidence="/tmp/lmdj-issue166-pressure-${issue247_merge_sha:0:12}"
issue247_pressure_status=0
ssh "$issue247_pressure_host" bash -s -- \
  "$issue247_pressure_path" "$issue247_remote_evidence" \
  "$issue247_merge_sha" "$issue247_merge_tree" \
  "$issue247_runner_lease_root" "$issue247_runner_watchdog" \
  "$issue247_runner_lease_dropin" "$issue247_runner_enable_marker" \
  "${issue247_runner_units[@]}" \
  <<'REMOTE_PRESSURE' || issue247_pressure_status=$?
set -euo pipefail
pressure_path="$1"
evidence_root="$2"
expected_sha="$3"
expected_tree="$4"
lease_root="$5"
watchdog_unit="$6"
lease_dropin="$7"
enable_marker="$8"
shift 8
runner_units=("$@")
((${#runner_units[@]} > 0))
test ! -e "$evidence_root"
mkdir -m 700 "$evidence_root"
session_log="$evidence_root/session.log"
stress_file="$evidence_root/stress.bin"
cpu_pid=""
io_pid=""
cleanup() {
  original_status=$?
  trap - EXIT INT TERM
  set +e
  cleanup_status=0
  cleanup_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'cleanup_start=%s\n' "$cleanup_started" \
    | tee -a "$session_log" || cleanup_status=1
  [[ -z "$cpu_pid" ]] || kill "$cpu_pid" 2>/dev/null || true
  [[ -z "$io_pid" ]] || kill "$io_pid" 2>/dev/null || true
  [[ -z "$cpu_pid" ]] || wait "$cpu_pid" 2>/dev/null || true
  [[ -z "$io_pid" ]] || wait "$io_pid" 2>/dev/null || true
  rm -f -- "$stress_file" || cleanup_status=1
  runner_restore_status=0
  for runner_unit in "${runner_units[@]}"; do
    sudo -n rm -f -- \
      "/run/systemd/system/$runner_unit.d/$lease_dropin" \
      || runner_restore_status=1
  done
  sudo -n systemctl daemon-reload || runner_restore_status=1
  sudo -n systemctl start -- "${runner_units[@]}" \
    || runner_restore_status=1
  for runner_unit in "${runner_units[@]}"; do
    if ! systemctl is-active --quiet "$runner_unit"; then
      runner_restore_status=1
    fi
    if [[ -e "/run/systemd/system/$runner_unit.d/$lease_dropin" ]]; then
      runner_restore_status=1
    fi
  done
  printf 'cleanup_end=%s cleanup_count=1 runner_restore_status=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$runner_restore_status" \
    | tee -a "$session_log" || cleanup_status=1
  final_status="$original_status"
  if [[ "$final_status" -eq 0 && \
        ("$runner_restore_status" -ne 0 || "$cleanup_status" -ne 0) ]]; then
    final_status=2
  fi
  exit "$final_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cd "$pressure_path" || exit 2
observed_sha="$(git rev-parse HEAD)"
observed_tree="$(git rev-parse HEAD^{tree})"
observed_status="$(git status --porcelain)"
printf 'runner=%s kernel=%s\n' "$(hostname -f)" "$(uname -srmo)" | tee "$session_log"
printf 'runner_watchdog=%s diagnostic_lease=%s\n' \
  "$watchdog_unit.timer" "$lease_root" | tee -a "$session_log"
printf 'expected_commit=%s observed_commit=%s expected_tree=%s observed_tree=%s worktree_clean=%s\n' \
  "$expected_sha" "$observed_sha" "$expected_tree" "$observed_tree" \
  "$([[ -z "$observed_status" ]] && printf true || printf false)" \
  | tee -a "$session_log"
test "$observed_sha" = "$expected_sha" || exit 2
test "$observed_tree" = "$expected_tree" || exit 2
test -z "$observed_status" || exit 2
cp "$lease_root/runner-log-baseline.tsv" \
  "$evidence_root/runner-log-baseline.tsv"
cp "$lease_root/runner-assignment-window.log" \
  "$evidence_root/runner-assignment-window.log"
assert_runner_isolation() {
  for runner_unit in "${runner_units[@]}"; do
    expected="$(printf '[Unit]\nConditionPathExists=%s' "$enable_marker")"
    actual="$(sudo -n cat "/run/systemd/system/$runner_unit.d/$lease_dropin")"
    [[ "$actual" == "$expected" ]]
    ! systemctl is-active --quiet "$runner_unit"
  done
}
for runner_unit in "${runner_units[@]}"; do
  runner_state="$(systemctl is-active "$runner_unit" || true)"
  printf 'runner_service=%s initial_state=%s condition_lease=present\n' \
    "$runner_unit" "$runner_state" | tee -a "$session_log"
  [[ "$runner_state" == "inactive" || "$runner_state" == "failed" ]] || exit 2
done
printf 'node=%s python=%s git_lfs=%s\n' \
  "$(node --version)" "$(python3 --version 2>&1)" "$(git lfs version)" | tee -a "$session_log"
session_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'session_start=%s\n' "$session_started" | tee -a "$session_log"
printf 'cpu_command=nice -n 5 yes > /dev/null\n' | tee -a "$session_log"
nice -n 5 yes >/dev/null &
cpu_pid=$!
printf 'io_command=ionice -c 2 -n 7 dd bs=1M count=64 conv=fsync loop\n' | tee -a "$session_log"
ionice -c 2 -n 7 sh -c \
  'while :; do dd if=/dev/zero of="$1" bs=1M count=64 conv=fsync status=none || exit; done' \
  _ "$stress_file" &
io_pid=$!
printf 'cpu_pid=%s io_pid=%s\n' "$cpu_pid" "$io_pid" | tee -a "$session_log"
kill -0 "$cpu_pid" && kill -0 "$io_pid" || exit 2
proof_count=0
for proof_run in 1 2 3; do
  kill -0 "$cpu_pid" && kill -0 "$io_pid" || exit 2
  assert_runner_isolation || exit 2
  printf 'proof=%s runner_services_pre=leased-inactive\n' \
    "$proof_run" | tee -a "$session_log"
  proof_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  proof_log="$evidence_root/proof-${proof_run}.log"
  printf 'proof=%s start=%s log=%s\n' \
    "$proof_run" "$proof_started" "$proof_log" | tee -a "$session_log"
  if scripts/web-runtime-host.sh proof 2>&1 | tee "$proof_log"; then
    proof_status=0
  else
    proof_status=${PIPESTATUS[0]}
  fi
  post_isolation_status=0
  assert_runner_isolation || post_isolation_status=1
  proof_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'proof=%s end=%s status=%s runner_services_post=%s\n' \
    "$proof_run" "$proof_finished" "$proof_status" \
    "$([[ "$post_isolation_status" -eq 0 ]] && printf leased-inactive || printf invalid)" \
    | tee -a "$session_log"
  toolchain_identity_status=0
  if [[ -f build/web/toolchain/toolchain-identity.json ]]; then
    cp build/web/toolchain/toolchain-identity.json \
      "$evidence_root/toolchain-identity-proof-${proof_run}.json" \
      || toolchain_identity_status=$?
  else
    toolchain_identity_status=1
  fi
  printf 'proof=%s toolchain_identity_status=%s\n' \
    "$proof_run" "$toolchain_identity_status" | tee -a "$session_log"
  [[ "$proof_status" -eq 0 ]] || exit "$proof_status"
  [[ "$post_isolation_status" -eq 0 ]] || exit 2
  [[ "$toolchain_identity_status" -eq 0 ]] || exit 2
  grep -q '^Web Runtime Host Proof: PASS$' "$proof_log" || exit 2
  kill -0 "$cpu_pid" && kill -0 "$io_pid" || exit 2
  proof_count=$proof_run
done
[[ "$proof_count" -eq 3 ]] || exit 2
printf 'session_end=%s proofs=3 status=0\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$session_log"
REMOTE_PRESSURE
if ! restore_pressure_runners; then
  echo "CRITICAL: runner restoration failed after pressure session" >&2
  exit 2
fi
for issue247_runner_unit in "${issue247_runner_units[@]}"; do
  ssh "$issue247_pressure_host" systemctl is-active --quiet \
    "$issue247_runner_unit"
done
issue247_pool_online=false
for issue247_poll in {1..60}; do
  gh api 'repos/endaye/lmdj/actions/runners?per_page=100' \
    >"$issue247_queue_evidence/runners-after.json"
  if jq -e --arg pattern "$issue247_runner_pattern" \
    --argjson expected "$issue247_runner_unit_count" '
    [.runners[] | select(.name | ascii_downcase | contains($pattern))] as $selected |
    ($selected | length) == $expected and
    all($selected[]; .status == "online")
  ' "$issue247_queue_evidence/runners-after.json" >/dev/null; then
    issue247_pool_online=true
    break
  fi
  sleep 2
done
test "$issue247_pool_online" = true
issue247_after_runner_names="$issue247_queue_evidence/api-runner-names-after.txt"
jq -r --arg pattern "$issue247_runner_pattern" \
  '.runners[] | select(.name | ascii_downcase | contains($pattern)) | .name' \
  "$issue247_queue_evidence/runners-after.json" | sort -u \
  >"$issue247_after_runner_names"
cmp "$issue247_service_runner_names" "$issue247_after_runner_names"
ssh "$issue247_pressure_host" sudo -n systemctl stop \
  "$issue247_runner_watchdog.timer"
if ssh "$issue247_pressure_host" systemctl is-active --quiet \
  "$issue247_runner_watchdog.timer"; then
  echo "runner restoration watchdog remained active" >&2
  exit 1
fi
issue247_watchdog_created=false
trap - EXIT INT TERM
issue247_local_pressure_evidence="/tmp/lmdj-issue166-pressure-copy-${issue247_merge_sha:0:12}"
test ! -e "$issue247_local_pressure_evidence"
mkdir -m 700 "$issue247_local_pressure_evidence"
scp -r "$issue247_pressure_host:$issue247_remote_evidence" \
  "$issue247_local_pressure_evidence/"
issue247_session_log="$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/session.log"
test "$issue247_pressure_status" -eq 0
test -f "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/runner-log-baseline.tsv"
test -f "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/runner-assignment-window.log"
! grep -Fq 'Send job request message to worker for job' \
  "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/runner-assignment-window.log"
grep -q '^session_end=.* proofs=3 status=0$' "$issue247_session_log"
test "$(grep -c '^proof=[123] end=.* status=0 runner_services_post=leased-inactive$' \
  "$issue247_session_log")" -eq 3
test "$(grep -c '^proof=[123] runner_services_pre=leased-inactive$' \
  "$issue247_session_log")" -eq 3
test "$(grep -c '^runner_service=.* initial_state=\(inactive\|failed\) condition_lease=present$' "$issue247_session_log")" \
  -eq "$issue247_runner_unit_count"
test "$(grep -c '^cleanup_end=.* cleanup_count=1 runner_restore_status=0$' \
  "$issue247_session_log")" -eq 1
issue247_cpu_pid="$(sed -n 's/^cpu_pid=\([0-9][0-9]*\) io_pid=.*/\1/p' "$issue247_session_log")"
issue247_io_pid="$(sed -n 's/^cpu_pid=[0-9][0-9]* io_pid=\([0-9][0-9]*\).*/\1/p' "$issue247_session_log")"
[[ "$issue247_cpu_pid" =~ ^[1-9][0-9]*$ ]]
[[ "$issue247_io_pid" =~ ^[1-9][0-9]*$ ]]
ssh "$issue247_pressure_host" \
  "test ! -e '$issue247_remote_evidence/stress.bin' && ! kill -0 '$issue247_cpu_pid' 2>/dev/null && ! kill -0 '$issue247_io_pid' 2>/dev/null"
cmp \
  "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/toolchain-identity-proof-1.json" \
  "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/toolchain-identity-proof-2.json"
cmp \
  "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/toolchain-identity-proof-1.json" \
  "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/toolchain-identity-proof-3.json"
jq -c . \
  "$issue247_local_pressure_evidence/$(basename "$issue247_remote_evidence")/toolchain-identity-proof-1.json" \
  | tee "$issue247_queue_evidence/pressure-toolchain-identity.json"
```

Expected: the same two contender PIDs stay live across proofs 1, 2 and 3; all three statuses are `0` and
each log ends in `Web Runtime Host Proof: PASS`; the diagnostic delta proves no job assignment in the
idle-query/lease window; every mapped Actions runner service retains its runtime condition lease and remains inactive before and
after all three proofs; restoration attempts every cleanup action with `errexit` disabled; the remote
watchdog remains armed until the exact service/name set is active and GitHub reports the same pool online.
Do not run extra proofs and select three successes.

- [ ] **Step 6: Audit closure without crossing release boundaries**

Perform a read-only closure audit. The reviewed PR uses `Relates to #247`, so neither Issue is mutated
by merge; do not comment on or close #247 or #166 in this Task:

```bash
set -euo pipefail
issue247_pr_number="$(gh pr list --state merged \
  --head fix/issue-247-capability-probe-timeout \
  --json number --jq '.[0].number')"
[[ "$issue247_pr_number" =~ ^[1-9][0-9]*$ ]]
git -C /Users/endaye/Projects/lmdj fetch origin --prune
git -C /Users/endaye/Projects/lmdj status --short --branch
gh pr view "$issue247_pr_number" --json state,mergedAt,mergeCommit,url
gh issue view 247 --json state,url
gh issue view 166 --json state,url
```

Report designed, planned, committed, pushed, merged, required-check, pressure-proof and issue states
separately. If both Issues satisfy their acceptance items, report them as ready for explicit Issue
comment/closure authorization; do not perform those mutations. Do not create or push tags, Releases,
deployments or Channel promotions.

## Version Management

Version impact: none

Reason: the implementation corrects an internal timeout classification without changing public API/ABI, Contract, Project, Provider, Model, Host/Module manifest, Product Assembly or Assembly Lock. It does not publish a package, allocate a Product Build, create a tag or mutate a release intent. Any later Product Build allocation is a separate exact-main, CI-verified version Task.

## Documentation Impact

Documentation impact: required

Update current `/core/modules/web-runtime-platform/`, `/platform/web-runtime/`, and `/operations/testing-and-proof/`. No diagram boundary changes and no immutable Product Build snapshot are permitted in this Task.
