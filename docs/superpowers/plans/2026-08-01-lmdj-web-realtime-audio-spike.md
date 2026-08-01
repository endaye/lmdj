# LMDJ Web Realtime Audio Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a product-neutral browser lab that proves AudioWorklet, WebAssembly, SharedArrayBuffer, MIDI dispatch, and audio lifecycle measurement without changing Core behavior or claiming a physical Touch-to-Sound pass before the threshold is approved.

**Architecture:** A dependency-free ES module app sends pointer and MIDI triggers through one bounded SharedArrayBuffer/Atomics single-producer/single-consumer ring to an AudioWorkletProcessor. The processor instantiates and calls a minimal WebAssembly module on the rendering thread, emits a short bounded tone, and returns one raw render-frame acknowledgement per accepted record; pure report code retains every privacy-bounded browser estimate separately from later acoustic measurements. A loopback-first Python server supplies COOP/COEP and optional trusted TLS for physical iPad testing.

**Tech Stack:** HTML, CSS, ES2022 modules, Web Audio API, AudioWorklet, WebAssembly, SharedArrayBuffer/Atomics, Web MIDI, Node.js 22 built-in test runner, Python 3.11 standard library, Playwright CLI.

## Global Constraints

- Work only on `feat/web-runtime-lab` in `/Users/endaye/Projects/lmdj/.worktrees/web-runtime-lab`.
- Add the lab under `apps/web-runtime-lab/`; it is a product-neutral experimental Host and is not added to Product Assembly.
- Do not modify `packages/`, `providers/`, `products/lmdj/`, Core C ABI, Application Facade, or version identities.
- Do not use or emit retired `lmdj.patch.v1` or `lmdj.materials.v1` Contracts.
- The lab report is local evidence, not a formal cross-language Contract; use `reportVersion: 1`, not a `lmdj.*` Contract ID.
- The open Touch-to-Sound threshold remains pending approval. The app records raw observations and must not display product pass/fail.
- Browser-estimated dispatch/render latency is not physical Touch-to-Sound evidence. Acoustic onset is measured separately on real hardware.
- Default serving binds only to `127.0.0.1`. LAN serving requires explicit `--bind`, `--cert-file`, and `--key-file`; iPad acceptance requires trusted HTTPS.
- Every response includes `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`, and `Cross-Origin-Resource-Policy: same-origin`.
- Require `crossOriginIsolated`, `SharedArrayBuffer`, `Atomics`, `AudioWorkletNode`, and WebAssembly before enabling triggers.
- Create/resume `AudioContext` only inside the explicit Start button activation.
- Never assume a 128-frame render quantum; report the observed output length on every processor callback and fail the automated invariant if it is zero or changes without being recorded.
- Use a fixed 1024-record ring with monotonic write/read counters. Reject and report overflow; never overwrite an unread trigger.
- Use one bounded oscillator voice and clamp output below `0.15` peak to avoid unsafe playback.
- Do not store MIDI input names, manufacturers, serials, IDs, SysEx data, or raw messages. Record only support, permission result, input count, event count, note, velocity, and relative timing.
- Version impact: none. This is isolated measurement tooling and does not change Product Build, Module SemVer, Provider SemVer, or Contract SemVer.
- Implementation, commit, branch push, and ready PR creation are authorized by the active sequential implementation goal. Merge, Tag, Release, deployment, and channel promotion retain their existing separate gates.

## Source References

- Web Audio 1.1 processing model and latency surfaces: <https://webaudio.github.io/web-audio-api/>
- Emscripten Wasm Audio Worklets constraints: <https://emscripten.org/docs/api_reference/wasm_audio_worklets.html>
- Cross-origin isolation requirements: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy>
- WebKit interruption evidence to retain in the physical matrix: <https://bugs.webkit.org/show_bug.cgi?id=273511>

---

### Task 1: Record the Pending Threshold Decision and Evidence Boundary

**Files:**

- Create: `docs/architecture/2026-08-01-web-realtime-audio-threshold-decision.md`
- Modify: `docs/prd/open-questions.md`
- Create: `docs/quality/web-runtime-lab-acceptance.md`

**Interfaces:**

- Consumes: Core redesign §23 and the still-open Touch-to-Sound question.
- Produces: one explicitly proposed threshold set and one acceptance protocol without changing the decision log.

- [x] **Step 1: Write the proposal without marking it approved**

Create a decision document with `Status: Proposed - awaiting Product Owner approval`. Record the recommendation exactly:

```text
Physical non-Bluetooth Touch-to-Sound:
  p95 <= 50 ms
  p99 <= 80 ms
  500 triggers: 0 missed, 0 duplicate
Foreground stability:
  10 minutes: 0 detected underrun, 0 processor error
Lifecycle recovery:
  one explicit user activation after interruption
  p95 activation-to-running <= 500 ms
```

State that Bluetooth is reported separately and never used to pass or fail the launch-platform gate. Define three evidence layers: capability/runtime telemetry, browser-estimated event-to-render timing, and physical touch/acoustic onset.

- [x] **Step 2: Link the open question without resolving it**

Keep status `待决`; add the proposal path and state that approval must precede pass/fail logic. Do not add anything to `docs/prd/decision-log.md`.

- [x] **Step 3: Specify the physical matrix**

Require at minimum:

```text
macOS Safari, built-in or wired output, pointer
macOS Chrome, built-in or wired output, pointer and one physical MIDI device
iPadOS Safari, built-in or wired output, touch
iPadOS Safari lifecycle: background/foreground, screen lock/unlock, route interruption
```

For every run record OS/browser version, device class, output route category, sample rate, base/output latency if exposed, 500-trigger CSV/JSON, lifecycle transitions, and high-speed-video or loopback measurement method. Do not record device serials or MIDI identifiers.

- [x] **Step 4: Verify documentation boundaries**

Run:

```bash
rg -n "Status: Proposed|待决|not.*pass|不.*通过" \
  docs/architecture/2026-08-01-web-realtime-audio-threshold-decision.md \
  docs/prd/open-questions.md \
  docs/quality/web-runtime-lab-acceptance.md
git diff --check
```

Expected: proposal and pending status are both explicit; no whitespace errors.

---

### Task 2: Add Pure Measurement and Report Logic with TDD

**Files:**

- Create: `apps/web-runtime-lab/package.json`
- Create: `apps/web-runtime-lab/src/probe-core.mjs`
- Create: `apps/web-runtime-lab/test/probe-core.test.mjs`

**Interfaces:**

- Consumes: raw browser capability values, AudioContext metadata, trigger acknowledgements, lifecycle events, and MIDI summaries.
- Produces: `preflight(capabilities)`, `percentile(values, percentileValue)`, and `createReport(session)`.

- [x] **Step 1: Write failing pure tests**

Use `node:test` and `node:assert/strict`. Cover:

```javascript
test("preflight requires every realtime primitive", () => {
  const result = preflight({
    secureContext: true,
    crossOriginIsolated: true,
    sharedArrayBuffer: true,
    atomics: true,
    audioContext: true,
    audioWorkletNode: true,
    webAssembly: true,
  });
  assert.deepEqual(result, { ready: true, missing: [] });
});

test("preflight names all missing primitives in stable order", () => {
  const result = preflight({});
  assert.equal(result.ready, false);
  assert.deepEqual(result.missing, [
    "secureContext",
    "crossOriginIsolated",
    "sharedArrayBuffer",
    "atomics",
    "audioContext",
    "audioWorkletNode",
    "webAssembly",
  ]);
});

test("percentile uses nearest-rank over finite non-negative values", () => {
  assert.equal(percentile([5, 1, 9, 3], 0.95), 9);
  assert.throws(() => percentile([1, Number.NaN], 0.95), /finite/);
});

test("report keeps estimates separate and has no pass field", () => {
  const report = createReport(fixtureSession());
  assert.equal(report.reportVersion, 1);
  assert.equal(report.decisionStatus, "pending-threshold-approval");
  assert.ok(report.browserEstimates);
  assert.equal("pass" in report, false);
  assert.equal(JSON.stringify(report).includes("MIDI Device Name"), false);
});
```

- [x] **Step 2: Run RED**

Run:

```bash
node --test apps/web-runtime-lab/test/probe-core.test.mjs
```

Expected: module-not-found for `src/probe-core.mjs`.

- [x] **Step 3: Implement the minimal pure module**

Implement fixed preflight key ordering, nearest-rank percentile, strict finite/non-negative validation, and a JSON-safe report builder. The report fields are exactly:

```text
reportVersion
decisionStatus
sessionId
startedAt
endedAt
environment
capabilities
audioContext
wasm
sharedControl
midi
lifecycle
triggerSummary
browserEstimates
physicalMeasurement
errors
```

`physicalMeasurement` defaults to `null`; `decisionStatus` is always `pending-threshold-approval` in this Task.

- [x] **Step 4: Run GREEN**

Run:

```bash
node --test apps/web-runtime-lab/test/probe-core.test.mjs
```

Expected: all tests pass with no warnings.

---

### Task 3: Add the Cross-Origin-Isolated Server with TDD

**Files:**

- Create: `apps/web-runtime-lab/server.py`
- Create: `apps/web-runtime-lab/test/server_test.py`
- Create: `scripts/web-runtime-lab.sh`

**Interfaces:**

- Consumes: `--bind`, `--port`, optional `--cert-file`, optional `--key-file`.
- Produces: a static server rooted only at `apps/web-runtime-lab/`, with mandatory isolation headers and optional TLS.

- [x] **Step 1: Write the failing server test**

Start an ephemeral server subprocess with `--port 0 --write-port <temp-file>`. Assert:

```python
assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
assert response.headers["Cache-Control"] == "no-store"
assert json.loads(urlopen(base_url + "/health.json").read()) == {
    "ok": True,
    "service": "web-runtime-lab",
}
```

Also require traversal attempts to return 404 and incomplete TLS arguments to exit `2` with `server error:`.

- [x] **Step 2: Run RED**

Run:

```bash
python3 apps/web-runtime-lab/test/server_test.py
```

Expected: failure because `server.py` is absent.

- [x] **Step 3: Implement the strict server**

Subclass `SimpleHTTPRequestHandler`, pass an explicit lab directory, add headers in `end_headers`, suppress request logs unless `--verbose`, expose the in-memory health response, and wrap the server socket with `ssl.SSLContext(PROTOCOL_TLS_SERVER)` only when both TLS files are supplied. Reject non-files, symlinks escaping the root, incomplete TLS arguments, and invalid ports.

Implement stable commands:

```text
scripts/web-runtime-lab.sh test
scripts/web-runtime-lab.sh serve
scripts/web-runtime-lab.sh serve --port 4173
scripts/web-runtime-lab.sh serve-lan --bind 0.0.0.0 --cert-file PATH --key-file PATH
```

- [x] **Step 4: Run GREEN**

Run:

```bash
python3 apps/web-runtime-lab/test/server_test.py
bash -n scripts/web-runtime-lab.sh
```

Expected: server tests pass and shell syntax is clean.

---

### Task 4: Implement AudioWorklet, WASM, Shared Control, MIDI, and Lifecycle UI

**Files:**

- Create: `apps/web-runtime-lab/index.html`
- Create: `apps/web-runtime-lab/styles.css`
- Create: `apps/web-runtime-lab/src/worklet.js`
- Create: `apps/web-runtime-lab/src/main.js`
- Create: `apps/web-runtime-lab/test/active_tree_test.py`

**Interfaces:**

- Consumes: `probe-core.mjs`, user activation, pointer/MIDI events, browser lifecycle events.
- Produces: audible bounded trigger, live raw metrics, privacy-bounded downloadable JSON report.

- [x] **Step 1: Write the failing active-tree test**

Require the exact five browser files, scan them for forbidden retired Contract IDs and absolute repository paths, and assert:

```python
assert "new SharedArrayBuffer" in main_source
assert "Atomics.add" in main_source
assert "audioWorklet.addModule" in main_source
assert "requestMIDIAccess" in main_source
assert "visibilitychange" in main_source
assert "WebAssembly.Module" in worklet_source
assert "currentFrame" in worklet_source
assert "outputs[0][0].length" in worklet_source
assert "128" not in worklet_source
assert "decisionStatus" in main_source
assert "pass" not in report_field_names
```

- [x] **Step 2: Run RED**

Run:

```bash
python3 apps/web-runtime-lab/test/active_tree_test.py
```

Expected: missing browser files.

- [x] **Step 3: Implement the processor**

Inside `AudioWorkletProcessor`:

- instantiate a valid minimal WebAssembly module exporting `level(): i32` and call it on every active render callback;
- receive one `SharedArrayBuffer`, expose an `Int32Array`, and drain every published trigger record between monotonic write/read counters through `Atomics.load`;
- for every accepted record, record `currentFrame`, begin or retrigger a fixed-duration sine burst, and post an acknowledgement containing sequence, source, note, velocity, render frame, current time, observed quantum length, and cumulative processor call count;
- derive quantum length only from `outputs[0][0].length`;
- clamp every sample to `[-0.15, 0.15]`;
- report `processorerror` through the node-side listener.

- [x] **Step 4: Implement the user-activation and control path**

The Start button must:

```javascript
const context = new AudioContext({ latencyHint: "interactive" });
await context.audioWorklet.addModule("./src/worklet.js");
const headerLength = 8;
const ringCapacity = 1024;
const recordLength = 3;
const control = new SharedArrayBuffer(
  Int32Array.BYTES_PER_ELEMENT
    * (headerLength + ringCapacity * recordLength),
);
const node = new AudioWorkletNode(context, "lmdj-web-runtime-probe", {
  processorOptions: { control, headerLength, ringCapacity, recordLength },
});
node.connect(context.destination);
await context.resume();
```

Pointer and MIDI handlers share one producer path: reject when the ring is full, write source/note/velocity into the next record, and publish it last with `Atomics.add`. Do not send raw MIDI messages to the report. Record AudioContext `statechange`, document `visibilitychange`, `pagehide`, `pageshow`, `freeze`, and `resume` where supported.

- [x] **Step 5: Implement measurement display and export**

Display separate cards for:

```text
Isolation/secure-context preflight
AudioContext state/sampleRate/baseLatency/outputLatency
WASM-in-worklet status and observed quantum sizes
Shared control sequence/ack counts
MIDI permission/input/event counts
Lifecycle transitions
Browser-estimated event-to-ack values
Physical measurement: Not recorded in browser
Decision: Pending threshold approval
```

Export only canonical JSON created by `createReport`; retain every privacy-bounded acknowledgement record plus the latest `getOutputTimestamp()` mapping, use a random per-session UUID and timestamps, and use no persistent local storage.

- [x] **Step 6: Run GREEN**

Run:

```bash
scripts/web-runtime-lab.sh test
```

Expected: Node, Python server, active-tree, and shell tests all pass.

---

### Task 5: Document Operation and Add the Automated Repository Gate

**Files:**

- Create: `apps/web-runtime-lab/README.md`
- Modify: `apps/README.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**

- Consumes: stable lab scripts and acceptance protocol.
- Produces: reproducible local/CI test commands and honest browser/device evidence boundaries.

- [ ] **Step 1: Document local and device operation**

Document:

```bash
scripts/web-runtime-lab.sh test
scripts/web-runtime-lab.sh serve --port 4173
scripts/web-runtime-lab.sh serve-lan \
  --bind 0.0.0.0 \
  --port 4173 \
  --cert-file /absolute/path/to/trusted-cert.pem \
  --key-file /absolute/path/to/key.pem
```

State that a visible page or a successful automated browser smoke is not physical latency evidence. Include the exact report privacy exclusions and the threshold-pending state.

- [ ] **Step 2: Add the CI job**

Add one `web-runtime-lab` job using Ubuntu, Python 3.11, and Node 22. It runs only:

```bash
scripts/web-runtime-lab.sh test
```

Do not install browser binaries in Core CI; physical and real-browser matrices remain separate acceptance evidence.

- [ ] **Step 3: Run complete automated verification**

Run:

```bash
scripts/web-runtime-lab.sh test
scripts/core.sh proof
git diff --check
```

Expected: lab tests pass, Core Proof remains 23/23 with Product Build `1.0.9.0`, and the diff is clean.

---

### Task 6: Perform a Real Desktop Browser Smoke and Prepare Review

**Files:** none

**Interfaces:**

- Consumes: the local isolated server and implemented UI.
- Produces: current-browser evidence for capability startup and report export; no physical latency conclusion.

- [ ] **Step 1: Start the isolated server**

Run:

```bash
scripts/web-runtime-lab.sh serve --port 4173
```

Expected: loopback URL printed once; COOP/COEP enabled.

- [ ] **Step 2: Run Playwright CLI smoke**

Use the bundled Playwright CLI wrapper to open `http://127.0.0.1:4173`, snapshot, click Start, trigger the pad, snapshot again, and export a report. Require visible evidence that:

```text
crossOriginIsolated is true
AudioContext is running
WASM in AudioWorklet is ready
Shared control acknowledgements increase
observed render quantum is non-zero
decision remains Pending threshold approval
```

This smoke may use Chromium automation and does not count as Safari, iPad, MIDI-device, or acoustic evidence.

- [ ] **Step 3: Commit and publish review branch**

Verify the branch is not `main`, stage only the files declared in Tasks 1-5 plus this plan, inspect staged paths and `git diff --cached --check`, then commit with:

```bash
git commit -m "feat(web): add realtime audio measurement lab"
```

Push `feat/web-runtime-lab`, create a ready PR to `main`, require every configured CI job, and retain the worktree for review iteration. Do not merge, tag, release, or deploy without the corresponding gate.

## Final Review Checklist

- [ ] The threshold proposal is explicit and remains unapproved in the open-question record.
- [ ] No Product Build, Module, Provider, Contract, Assembly, Facade, or Core source changed.
- [ ] Start/resume occurs only from explicit user activation.
- [ ] AudioWorklet instantiates and calls WebAssembly on the rendering thread.
- [ ] Pointer and MIDI use the same SharedArrayBuffer/Atomics trigger path.
- [ ] Render quantum size is observed dynamically and never hard-coded.
- [ ] Reports separate browser estimates from physical measurements and contain no pass/fail field.
- [ ] Reports exclude MIDI/device identifiers and do not persist locally.
- [ ] Loopback server is isolated by default; LAN mode requires explicit trusted TLS inputs.
- [ ] Automated lab tests and Core Proof pass.
- [ ] Desktop Chromium smoke passes without being misreported as Safari/iPad/acoustic evidence.
- [ ] Physical macOS Safari/Chrome, MIDI, iPad Safari, lifecycle, and acoustic gates remain visibly pending.
