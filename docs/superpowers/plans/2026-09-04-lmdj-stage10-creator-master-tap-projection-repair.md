# LMDJ Stage 10 Creator Master-Tap and Projection Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the real Web Runtime master-bus capture graph before #435, then build the Creator Perform surface against one strict v3/v4 Project projection and activate the capability only at the `1.0.42.0` integration boundary.

**Architecture:** `web-runtime-platform` owns the tap processor, its private port protocol, the `AudioContext` graph, and a typed capture status/lifecycle API. Creator owns only the bounded WAV queue/store and Perform UI, while `project_actions.ts` remains its only Project Truth projection. Task 8A, revised Task 9, and Task 10 remain three independently reviewable commits and Pull Requests.

**Tech Stack:** C++20, Emscripten WebAudio API, JavaScript ES modules, AudioWorklet, TypeScript 7, React 19, Vitest 4, Node test runner, Playwright 1.62, OPFS, Python packaging tests, Docusaurus Architecture Portal.

## Global Constraints

- The approved repair design is `docs/superpowers/specs/2026-09-04-lmdj-stage10-creator-master-tap-projection-repair-design.md` (CMTP-D1–D5). Any conflict returns to design review.
- Work on a short-lived branch in an isolated worktree. Task 8A, revised Task 9, and Task 10 each produce one Conventional Commit and one Pull Request.
- Web Runtime platform is the only owner of the `AudioContext`, engine node, tap node, destination, Emscripten audio-object handles, processor source, and port protocol. Creator receives none of those objects.
- The audible graph is exactly `lmdj-realtime-engine stereo output → lmdj-perform-master-tap → AudioContext.destination`; without valid static tap configuration it remains `engine → destination`.
- Load the tap module and construct/connect its node before `startAudioWorklet`. Do not require the context to remain `suspended`; the same user gesture may already have moved it to `running`.
- A tap belongs to one `AudioContext` recovery epoch. Interruption, recovery, close, or processor failure terminates the current capture; a replacement context gets a fresh node, port, generation, listeners, and buffers.
- The processor starts idle and uses `4,800` frames per full stereo batch. `generation` and `sequence` are non-negative safe-integer platform transport metadata, never Performance timing/order or Project Truth.
- `perform_recording_frames = 86400000` and `perform_recording_queue_batches = 32` come only from injected Product identity. No source default or UI fallback is allowed.
- `1.0.41.0` is `unconfigured` and silently disables Perform recording. A configured Build with a failed capability/module/node/processor is `unavailable` with an actionable stable error.
- Production-shaped Browser tests may route-substitute candidate identity/module/manifest responses and may inject deterministic dependency failures only through the existing `window.__LMDJ_WEB_HOST_SEAMS__` table. They must not add a Perform-only global hook, replace Core transport, fabricate Facade receipts, or fabricate sealed Project/draft state.
- Creator obtains slots only from `project_actions.ts::projectView()`. v3 projects project to exactly 16 nulls; v4 projects must contain exactly 16 unique-or-null existing Pattern references.
- Active Assembly, manifests, module versions, and Product Build remain unchanged in Task 8A and revised Task 9. Task 10 is the only capability-activation and version/current-Portal boundary.
- Before each commit run the focused tests, `scripts/core.sh test dev full`, the stress tier when WebAudio/concurrency code changes, and `scripts/architecture-portal.sh check`; stage only the Task files and inspect `git diff --cached --check`.

---

## File and Responsibility Map

| File | Responsibility after this repair |
|---|---|
| `packages/web-runtime-platform/web/performance_master_tap_worklet.js` | Platform-owned transparent stereo processor and private generation/sequence protocol. |
| `packages/web-runtime-platform/web/performance_master_capture.mjs` | Browser-main tap node/port controller; validates messages, serializes captures, catches sink exceptions, and exposes no raw node/port. |
| `packages/web-runtime-platform/web/runtime_session.mjs` | Derives static capture config, owns status transitions and graph lifecycle, and exposes typed capture methods on the session. |
| `packages/web-runtime-platform/web/runtime_types.d.ts` | Canonical public `PerformanceMasterCapture*` and `WebPerformanceCaptureSession` declarations. |
| `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp` | Declares opaque output destination and direct-output fallback entry points. |
| `packages/audio-runtime/src/web/realtime_audio_worklet.cpp` | Connects the engine node to the supplied opaque destination and implements idempotent fallback. |
| `packages/web-runtime-platform/src/bridge.cpp` and `src/web-runtime-pre.js` | Carries context/destination handles between browser-main JS and Audio Runtime without exposing them through Creator. |
| `apps/creator-web/src/record/master_tap_source.ts` | Port-free bounded sink/queue that streams batches to the existing WAV writer and requests stop on Host failure. |
| `apps/creator-web/src/main.tsx` | Injects the same-origin platform processor URL and passes existing Host dependency seams through the production session path. |
| `apps/creator-web/src/runtime/project_actions.ts` | Sole strict v3/v4 Project-to-`ProjectView` projection. |
| `apps/creator-web/src/runtime/runtime_types.ts` | Extends the canonical platform capture session type and adds immutable `patternSlots`. |
| `apps/creator-web/src/state/perform_state.ts` | Creator-only UI/controller state; never parses a Project bundle or owns slot truth. |
| `apps/creator-web/src/components/*perform*` | Accessible Pattern/FX/HOLD/Pad/record/save/replay/resample presentation. |
| `apps/creator-web/tools/package.py` | Task 10 hashes and publishes the platform tap processor under the locked distribution role. |

## Locked Interfaces

The implementation uses these exact public declarations in
`packages/web-runtime-platform/web/runtime_types.d.ts`:

```ts
export interface PerformanceMasterCaptureConfig {
  readonly performRecordingFrames: number;
  readonly performRecordingQueueBatches: number;
}

export interface PerformanceMasterCaptureError {
  readonly code:
    | "capture-unsupported"
    | "tap-initialization-failed"
    | "tap-processor-failed";
  readonly message: string;
}

export type PerformanceMasterCaptureStatus =
  | {readonly state: "unconfigured"; readonly config: null; readonly error: null}
  | {readonly state: "configured"; readonly config: PerformanceMasterCaptureConfig; readonly error: null}
  | {readonly state: "ready"; readonly config: PerformanceMasterCaptureConfig; readonly error: null}
  | {readonly state: "unavailable"; readonly config: PerformanceMasterCaptureConfig; readonly error: PerformanceMasterCaptureError};

export interface PerformanceMasterCaptureSink {
  onBatch(channels: readonly [Float32Array, Float32Array]): void;
  onStopped(): void;
  onFailure(reason: "tap-failure", droppedFrames: number): void;
}

export interface PerformanceMasterCapture {
  stop(): Promise<void>;
}

export interface WebPerformanceCaptureSession {
  performanceMasterCaptureStatus(): PerformanceMasterCaptureStatus;
  subscribePerformanceMasterCaptureStatus(
    listener: (status: PerformanceMasterCaptureStatus) => void,
  ): () => void;
  startPerformanceMasterCapture(
    sink: PerformanceMasterCaptureSink,
  ): Promise<PerformanceMasterCapture>;
}
```

The private processor messages are exact:

```ts
type MasterTapControlMessage =
  | {readonly type: "start"; readonly generation: number}
  | {readonly type: "stop"; readonly generation: number};

type MasterTapEventMessage =
  | {readonly type: "batch"; readonly generation: number; readonly sequence: number; readonly channels: readonly [Float32Array, Float32Array]}
  | {readonly type: "stopped"; readonly generation: number; readonly finalSequence: number}
  | {readonly type: "failed"; readonly generation: number; readonly reason: "post-message-failed"; readonly droppedFrames: number};
```

Task 10 locks the new distribution entry as:

```json
{
  "prefix": "assets/perform-master-tap.",
  "role": "perform_master_tap_worklet",
  "suffix": ".js"
}
```

---

### Task 1: Task 8A — Establish the Platform-Owned Master-Tap Graph

**Issue:** Create the prerequisite issue titled `Stage 10: connect the Web Runtime Perform master tap` before implementation and link it as a blocker of #435. Use branch `feat/stage10-perform-master-tap`; the Pull Request closes the allocated issue.

**Files:**

- Create: `packages/web-runtime-platform/web/performance_master_tap_worklet.js`
- Create: `packages/web-runtime-platform/web/performance_master_capture.mjs`
- Create: `packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs`
- Create: `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- Modify: `packages/web-runtime-platform/web/runtime_types.d.ts`
- Modify: `packages/web-runtime-platform/web/runtime_session.mjs`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `packages/web-runtime-platform/src/web-runtime-pre.js`
- Modify: `packages/web-runtime-platform/src/bridge.cpp`
- Modify: `packages/web-runtime-platform/test/performance_bridge_test.cpp`
- Modify: `packages/web-runtime-platform/CMakeLists.txt`
- Modify: `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`
- Modify: `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- Modify: `tests/platform/web/audio/realtime_audio_worklet.html`
- Modify: `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
- Delete: `apps/creator-web/src/record/master_tap_worklet.js`
- Modify: `apps/creator-web/src/record/master_tap_source.ts`
- Modify: `apps/creator-web/src/main.tsx`
- Modify: `apps/creator-web/test/master_tap.test.ts`

**Interfaces:**

- Consumes: `RealtimeAudioWorklet::start_on_browser_main`, `emscriptenRegisterAudioObject`, the exact Product `resource_limits`, `AudioWorkletNode`, and the existing `MasterTapBatchQueue`/WAV writer from #434.
- Produces: the locked `WebPerformanceCaptureSession` interface above; `startAudioWorklet(contextHandle, outputDestinationHandle)`; `connectAudioWorkletDirect(contextHandle)`; a Creator queue implementing `PerformanceMasterCaptureSink`; and a same-origin processor URL input named `performanceMasterTapUrl` in `manifestSource`.

- [ ] **Step 1: Write the processor protocol RED test**

Create `performance_master_tap_worklet.test.mjs`. Load the processor source in a VM with a stub `AudioWorkletProcessor`, then assert idle pass-through, generation isolation, monotonic sequences, final partial batch, and stale-stop rejection:

```js
test("processor is idle until start and isolates serial generations", async () => {
  const {Processor, messages} = await loadMasterTapProcessor();
  const processor = new Processor();
  const input = [new Float32Array(4_800).fill(0.25), new Float32Array(4_800).fill(-0.5)];
  const output = [new Float32Array(4_800), new Float32Array(4_800)];

  assert.equal(processor.process([input], [output]), true);
  assert.deepEqual(output, input);
  assert.deepEqual(messages, []);

  processor.port.onmessage({data: {type: "start", generation: 7}});
  processor.process([input], [output]);
  assert.deepEqual(messages[0], {
    type: "batch", generation: 7, sequence: 1, channels: input,
  });
  processor.port.onmessage({data: {type: "stop", generation: 6}});
  assert.equal(messages.length, 1);
  processor.port.onmessage({data: {type: "stop", generation: 7}});
  assert.deepEqual(messages.at(-1), {
    type: "stopped", generation: 7, finalSequence: 1,
  });
});
```

- [ ] **Step 2: Run the processor RED test**

Run:

```bash
node --test packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs
```

Expected: FAIL because `performance_master_tap_worklet.js` does not exist in the platform package.

- [ ] **Step 3: Move and implement the platform processor**

Create the platform-owned processor with an idle initial state and the exact message shapes. Its render function must copy both channels before any recording work and must never throw:

```js
const PERFORM_BATCH_FRAMES = 4_800;

class PerformanceMasterTapProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.generation = null;
    this.sequence = 0;
    this.frames = 0;
    this.left = new Float32Array(PERFORM_BATCH_FRAMES);
    this.right = new Float32Array(PERFORM_BATCH_FRAMES);
    this.port.onmessage = ({data}) => {
      if (data?.type === "start" && Number.isSafeInteger(data.generation) && data.generation >= 0) {
        this.generation = data.generation;
        this.sequence = 0;
        this.frames = 0;
      } else if (data?.type === "stop" && data.generation === this.generation) {
        const generation = this.generation;
        if (!this.flush()) return;
        this.generation = null;
        try {
          this.port.postMessage({type: "stopped", generation, finalSequence: this.sequence});
        } catch {}
      }
    };
  }

  flush() {
    if (this.generation === null || this.frames === 0) return true;
    const generation = this.generation;
    const droppedFrames = this.frames;
    const channels = [this.left.slice(0, this.frames), this.right.slice(0, this.frames)];
    this.sequence += 1;
    this.frames = 0;
    try {
      this.port.postMessage({type: "batch", generation, sequence: this.sequence, channels});
      return true;
    } catch {
      this.generation = null;
      try { this.port.postMessage({type: "failed", generation, reason: "post-message-failed", droppedFrames}); } catch {}
      return false;
    }
  }

  process(inputs, outputs) {
    const input = inputs[0] ?? [];
    const output = outputs[0] ?? [];
    const frames = output[0]?.length ?? 0;
    for (let channel = 0; channel < 2; channel += 1) {
      const source = input[channel] ?? input[0];
      if (source && output[channel]) output[channel].set(source);
    }
    if (this.generation === null) return true;
    for (let frame = 0; frame < frames; frame += 1) {
      this.left[this.frames] = input[0]?.[frame] ?? 0;
      this.right[this.frames] = input[1]?.[frame] ?? input[0]?.[frame] ?? 0;
      this.frames += 1;
      if (this.frames === PERFORM_BATCH_FRAMES && !this.flush()) break;
    }
    return true;
  }
}

registerProcessor("lmdj-perform-master-tap", PerformanceMasterTapProcessor);
```

Delete the Creator-owned processor file after the platform test consumes the new path.

- [ ] **Step 4: Write capture-controller and status RED tests**

Create `performance_master_capture.test.mjs` and extend `runtime_session.test.mjs` with these exact observations:

```js
assert.deepEqual(unconfigured.performanceMasterCaptureStatus(), {
  state: "unconfigured", config: null, error: null,
});

assert.deepEqual(configured.performanceMasterCaptureStatus(), {
  state: "configured",
  config: {performRecordingFrames: 86_400_000, performRecordingQueueBatches: 32},
  error: null,
});

const order = [];
const session = runtimeFixture({
  resourceLimits: {perform_recording_frames: 86_400_000, perform_recording_queue_batches: 32},
  performanceMasterTapUrl: "https://example.test/assets/perform-master-tap.js",
  createPerformanceMasterTap: async () => { order.push("tap"); return tapController; },
  startAudioWorklet: async (_context, destination) => { order.push(["engine", destination]); return {ok: true}; },
});
const seen = [];
const unsubscribe = session.subscribePerformanceMasterCaptureStatus((status) => seen.push(status.state));
await activate(session);
assert.deepEqual(order, ["tap", ["engine", 2]]);
assert.equal(session.performanceMasterCaptureStatus().state, "ready");
assert.deepEqual(seen, ["configured", "ready"]);
unsubscribe();
```

Also assert: an invalid resource value is `unconfigured`; module/node creation failure starts the engine against the context destination and yields `tap-initialization-failed`; `processorerror` stops the capture, disconnects the tap output, invokes the idempotent direct-output fallback, and yields `tap-processor-failed`; a sink throw is caught without stopping automatically; a second concurrent start is rejected; serial generations discard stale messages; interruption and close settle the active capture once.

- [ ] **Step 5: Run the controller/session RED tests**

Run:

```bash
node --test packages/web-runtime-platform/test/performance_master_capture.test.mjs packages/web-runtime-platform/test/runtime_session.test.mjs
```

Expected: FAIL because the capture module, status methods, destination registration, and graph ordering do not exist.

- [ ] **Step 6: Implement the browser-main capture controller**

In `performance_master_capture.mjs`, validate the same-origin URL, construct one transparent stereo node, own its port, and expose only the controller methods used by `runtime_session.mjs`:

```js
export async function createPerformanceMasterTap({context, processorUrl}) {
  const url = new URL(processorUrl, globalThis.location?.href);
  if (globalThis.location && url.origin !== globalThis.location.origin) {
    throw new TypeError("Perform master tap URL must be same-origin");
  }
  await context.audioWorklet.addModule(url.href);
  const node = new AudioWorkletNode(context, "lmdj-perform-master-tap", {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [2],
    channelCount: 2,
    channelCountMode: "explicit",
    channelInterpretation: "discrete",
  });
  node.connect(context.destination);
  return createPerformanceMasterCaptureController({node});
}
```

The returned controller must provide `destinationNode`, `start(sink)`, `failProcessor()`, and `close()`. `start` allocates the next safe generation, installs the sink before posting `start`, returns one idempotent `stop()`, validates every message field and sequence, wraps each sink call in `try/catch`, and never treats a sink return/throw as a stop signal.

- [ ] **Step 7: Add the canonical TypeScript declarations and session state machine**

Add the complete locked declarations from this plan to `runtime_types.d.ts`. In `runtime_session.mjs`, derive config only from the two positive safe-integer limits plus `manifestSource.performanceMasterTapUrl`, freeze every status value, and publish status transitions through a subscriber set:

```js
const captureConfig = isPositiveInteger(limits?.perform_recording_frames) &&
  isPositiveInteger(limits?.perform_recording_queue_batches) &&
  typeof manifestSource?.performanceMasterTapUrl === "string"
  ? Object.freeze({
      performRecordingFrames: limits.perform_recording_frames,
      performRecordingQueueBatches: limits.perform_recording_queue_batches,
    })
  : null;
let captureStatus = captureConfig === null
  ? Object.freeze({state: "unconfigured", config: null, error: null})
  : Object.freeze({state: "configured", config: captureConfig, error: null});
```

`activateAudio` must create/register/connect the tap before calling
`runtime.startAudioWorklet(contextHandle, outputDestinationHandle)`. If tap creation fails, pass `contextHandle` as the destination and set `unavailable`; do not fail live audio solely because capture failed. On `processorerror`, fail/stop the capture, disconnect the tap node from destination, call `runtime.connectAudioWorkletDirect(contextHandle)`, and publish `unavailable`.

- [ ] **Step 8: Inject the platform URL through the production Creator path**

In `main.tsx`, import the platform asset and add it to `manifestSource`; keep the existing seam table as the only dependency override surface:

```ts
import performanceMasterTapUrl from
  "@lmdj/web-runtime-platform/performance_master_tap_worklet.js?url&no-inline";

manifestSource: {
  heapBytes: WEB_RUNTIME_IDENTITY.heap_bytes,
  resourceLimits: WEB_RUNTIME_IDENTITY.resource_limits,
  performanceMasterTapUrl,
  // existing Emscripten, compatibility, and expected-asset fields remain
},
```

Do not add the two limits or a new expected asset to the active identity in this Task; therefore `1.0.41.0` remains `unconfigured`.

- [ ] **Step 9: Write the opaque-destination and direct-fallback RED witnesses**

Extend the Emscripten conformance page/spec and `performance_bridge_test.cpp` so the browser registers a transparent test destination, starts the engine with its handle, proves rendered energy crosses that destination exactly once, then triggers the direct fallback and proves audible output continues without reconnecting the Creator graph. Add invalid/duplicate destination-handle cases:

```js
const tapHandle = runtime.registerAudioNode(tapNode);
const started = await runtime.startAudioWorklet(contextHandle, tapHandle);
expect(started).toMatchObject({ok: true, inputs: 0, outputs: 1, channels: 2});
expect(await analyzerEnergy(tapNode)).toBeGreaterThan(0);
expect(runtime.connectAudioWorkletDirect(contextHandle)).toBe(true);
```

- [ ] **Step 10: Run the WebAudio RED witness**

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/dev -R 'host.web_performance_bridge' --output-on-failure
scripts/web-runtime-host.sh proof
```

Expected: FAIL because the Audio Runtime start signature has no destination handle and no direct-output fallback.

- [ ] **Step 11: Carry opaque handles through C++, C bridge, and pre-JS**

Change the Audio Runtime signatures to:

```cpp
RealtimeAudioWorkletStart start_on_browser_main(
    std::int32_t audio_context_handle,
    std::int32_t output_destination_handle) noexcept;
bool connect_direct_output_on_browser_main(
    std::int32_t audio_context_handle) noexcept;
```

Store the destination handle during accepted start, connect the engine node with
`emscripten_audio_node_connect(node, output_destination_handle, 0, 0)`, and make direct fallback validate the original context, require `node_ready` or `ready`, and connect the engine node to the context at most once. Export corresponding C functions from `bridge.cpp`. In `web-runtime-pre.js`, add `registerAudioNode(node)`, validate both handles in `startAudioWorklet`, call `_lmdj_web_audio_start(contextHandle, outputDestinationHandle)`, and expose the idempotent `connectAudioWorkletDirect(contextHandle)`.

- [ ] **Step 12: Refactor the Creator queue from port ownership to sink ownership**

Remove the processor raw/URL imports, `MasterTapPort`, `connect(port)`, and port message parser from `master_tap_source.ts`. Implement the canonical sink directly and request control-path stop through its owner:

```ts
export interface MasterTapListener {
  onFailure(failure: MasterTapFailure): void;
  requestCaptureStop(): void;
}

export class MasterTapBatchQueue implements PerformanceMasterCaptureSink {
  onBatch(channels: readonly [Float32Array, Float32Array]): void {
    this.acceptBatch(channels);
  }
  onStopped(): void {
    this.workletStopped = true;
    this.finishWhenDrained();
  }
  onFailure(_reason: "tap-failure", droppedFrames: number): void {
    this.#requestTerminal("tap-failure", droppedFrames);
  }
  #requestTerminal(reason: TerminalReason, droppedFrames: number): void {
    if (this.#sealReason !== null) {
      this.#droppedFrames += droppedFrames;
      return;
    }
    this.#sealed = true;
    this.#sealReason = reason;
    this.#droppedFrames += droppedFrames;
    for (const queued of this.#queue.splice(0)) {
      this.#droppedFrames += queued[0]?.length ?? 0;
    }
    this.#outstanding = 0;
    this.#listener.requestCaptureStop();
    this.#maybeFinishTerminal();
  }
}
```

Rewrite `master_tap.test.ts` to call `onBatch`, `onStopped`, and `onFailure` directly. Assert the 33rd batch requests capture stop once, a listener exception is contained, terminal sealing waits for the platform `onStopped` acknowledgement, and the queue never touches a port.

- [ ] **Step 13: Run Task 8A GREEN verification**

Run:

```bash
node --test packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs packages/web-runtime-platform/test/performance_master_capture.test.mjs packages/web-runtime-platform/test/runtime_session.test.mjs
npm --prefix apps/creator-web test -- --run test/master_tap.test.ts
scripts/core.sh test dev full
scripts/core.sh test dev stress
scripts/web-runtime-host.sh proof
scripts/architecture-portal.sh check
```

Expected: all commands PASS; the active Product identity remains `1.0.41.0`, has neither Perform recording resource key, and reports `unconfigured`.

- [ ] **Step 14: Commit Task 8A atomically**

Run:

```bash
git add packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp \
  packages/audio-runtime/src/web/realtime_audio_worklet.cpp \
  packages/web-runtime-platform/web/performance_master_tap_worklet.js \
  packages/web-runtime-platform/web/performance_master_capture.mjs \
  packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs \
  packages/web-runtime-platform/test/performance_master_capture.test.mjs \
  packages/web-runtime-platform/web/runtime_types.d.ts \
  packages/web-runtime-platform/web/runtime_session.mjs \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  packages/web-runtime-platform/src/web-runtime-pre.js \
  packages/web-runtime-platform/src/bridge.cpp \
  packages/web-runtime-platform/test/performance_bridge_test.cpp \
  packages/web-runtime-platform/CMakeLists.txt apps/creator-web/src/main.tsx \
  apps/creator-web/src/record/master_tap_source.ts \
  apps/creator-web/src/record/master_tap_worklet.js \
  apps/creator-web/test/master_tap.test.ts \
  tests/platform/web/audio/realtime_audio_worklet.html \
  tests/platform/web/audio/realtime_audio_worklet.spec.mjs
git diff --cached --name-status
git diff --cached --check
git commit -m "feat(web-runtime): connect the Perform master tap"
```

Inspect `git show --name-status --oneline HEAD` and require a clean Task worktree before shipping through `issue-done`; use the allocated issue number in the Pull Request closing footer.

---

### Task 2: Revised Task 9 — Build #435 on Real Capture and One Project Projection

**Issue:** #435. Hard dependencies: merged #431, #433, #434, and Task 8A.

**Files:**

- Create: `apps/creator-web/src/components/perform_surface.tsx`
- Create: `apps/creator-web/src/components/fx_slider_bank.tsx`
- Create: `apps/creator-web/src/components/pattern_launch_strip.tsx`
- Create: `apps/creator-web/src/state/perform_state.ts`
- Modify: `apps/creator-web/src/components/mode_rail.tsx`
- Modify: `apps/creator-web/src/app.tsx`
- Modify: `apps/creator-web/src/runtime/runtime_types.ts`
- Modify: `apps/creator-web/src/runtime/project_actions.ts`
- Modify: `apps/creator-web/src/state/creator_state.ts`
- Modify: `apps/creator-web/src/state/view_model.ts`
- Modify: `apps/creator-web/src/styles.css`
- Test: `apps/creator-web/test/project_actions.test.ts`
- Test: `apps/creator-web/test/perform_surface.test.tsx`
- Test: `tests/platform/web/creator/creator_web_perform.spec.mjs`

**Interfaces:**

- Consumes: Task 8A `WebPerformanceCaptureSession`, `MasterTapBatchQueue`, #434 `WavStreamWriter`/`PerformanceRecordingStore`, #433 Performance runtime operations, and one `ProjectView.patternSlots` projection.
- Produces: the complete P10-D17 Creator surface and production Browser journeys that Task 10 reruns unchanged against the formal `1.0.42.0` package.

- [ ] **Step 1: Rewrite the Project projection RED tests**

Extend `project_actions.test.ts` with one v3 fixture and strict v4 cases:

```ts
test("projects v3 to sixteen immutable empty Pattern slots", async () => {
  const view = await openProjectJourney(sessionFor(inspectV3()), summary);
  expect(view.patternSlots).toEqual(Array(16).fill(null));
  expect(Object.isFrozen(view.patternSlots)).toBe(true);
});

test.each([
  {name: "wrong length", slots: Array(15).fill(null)},
  {name: "duplicate", slots: [PATTERN_ID, PATTERN_ID, ...Array(14).fill(null)]},
  {name: "dangling", slots: [UNKNOWN_PATTERN_ID, ...Array(15).fill(null)]},
])("rejects v4 $name without keeping stale slot truth", async ({slots}) => {
  await expect(openProjectJourney(sessionFor(inspectV4(slots)), summary))
    .rejects.toMatchObject({code: "HOST_PROTOCOL_MISMATCH"});
});
```

Also assert that v3 rejects pre-existing `pattern_slots`/`performances`, unknown contracts fail, and a valid v4 preserves exactly 16 ordered values.

- [ ] **Step 2: Run the projection RED test**

Run:

```bash
npm --prefix apps/creator-web test -- --run test/project_actions.test.ts
```

Expected: FAIL because `projectView()` rejects v4 and `ProjectView` has no `patternSlots`.

- [ ] **Step 3: Implement the only v3/v4 projection**

Add `readonly patternSlots: readonly (string | null)[]` to `ProjectView`. In
`project_actions.ts`, branch only on the declared contract, validate the v3 key absence and v4 slot array, and freeze the projection:

```ts
function patternSlotsFor(project: Record<string, unknown>): readonly (string | null)[] {
  if (project.contract === "lmdj.project.v3") {
    if ("pattern_slots" in project || "performances" in project) {
      throw protocolMismatch("Project v3 contains v4 fields");
    }
    return Object.freeze(Array<string | null>(16).fill(null));
  }
  if (project.contract !== "lmdj.project.v4" ||
      !Array.isArray(project.pattern_slots) || project.pattern_slots.length !== 16) {
    throw protocolMismatch("Project Pattern slots are invalid");
  }
  const occupied = new Set<string>();
  const slots = project.pattern_slots.map((value) => {
    if (value === null) return null;
    if (typeof value !== "string" || !UUID_PATTERN.test(value) ||
        occupied.has(value) || !Object.hasOwn(project.patterns, value)) {
      throw protocolMismatch("Project Pattern slot reference is invalid");
    }
    occupied.add(value);
    return value;
  });
  return Object.freeze(slots);
}
```

Every open/import/mutation/reload path must call the existing projection refresh; no reducer may edit `patternSlots` from a mutation receipt.

- [ ] **Step 4: Rewrite the Perform unit RED tests against capture status**

Replace the current untracked #435 RED fixture with a session implementing the canonical status methods:

```ts
performanceMasterCaptureStatus: () => ({
  state: "ready",
  config: {performRecordingFrames: 86_400_000, performRecordingQueueBatches: 32},
  error: null,
}),
subscribePerformanceMasterCaptureStatus: (listener) => {
  listener(session.performanceMasterCaptureStatus());
  return () => {};
},
startPerformanceMasterCapture: vi.fn(async (sink) => ({
  stop: vi.fn(async () => sink.onStopped()),
})),
```

Assert P10-D17 order, eight FX sliders in fixed order, one HOLD, instant Bank view changes with zero runtime request, raw input with identities but no Host clock/order, Pattern pending/ack state, and these gates: `unconfigured` is silently disabled, `configured` is waiting, `unavailable` renders its actionable message, and only `ready` plus playable Project/running audio/OPFS enables Record.

- [ ] **Step 5: Run the Perform unit RED test**

Run:

```bash
npm --prefix apps/creator-web test -- --run test/perform_surface.test.tsx
```

Expected: FAIL because the Perform components/state and capture-status integration do not exist.

- [ ] **Step 6: Implement the typed Creator session and Perform state**

Import `PerformanceRuntimeSession` and `WebPerformanceCaptureSession` as types from the platform declarations and compose them into the Creator type rather than copying the capture API:

```ts
export interface CreatorPerformanceRuntimeSession
  extends CreatorSampleRuntimeSession,
    PerformanceRuntimeSession,
    WebPerformanceCaptureSession {}
```

Model Perform state as one immutable reducer/controller containing `bank`, `captureStatus`, `recording`, `pendingLaunch`, `hold`, `fx`, `performances`, and `error`. The controller must start the queue/writer before `beginPerformanceRecording`, install the queue sink before capture start, call `capture.stop()` on queue/writer failure, and refresh Project Truth after every Project mutation.

- [ ] **Step 7: Implement the accessible Perform components**

Build the surface in exact DOM order and keep all controls wired through the controller:

```tsx
<main aria-label="Perform">
  <PatternLaunchStrip slots={project.patternSlots} pending={pendingLaunch} />
  <FxSliderBank order={FX_CHAIN_ORDER} values={fxValues} />
  <button type="button" aria-pressed={hold} onClick={toggleHold}>HOLD</button>
  <section aria-label="Perform instrument"><PadSurface bank={bank} /></section>
  <PerformanceRecordingPanel state={recording} onRecord={record} onFlush={flush} onStop={stop} onSave={save} onDiscard={discard} />
  <PerformanceReplayPanel performances={performances} replay={replay} onReplay={beginReplay} onStop={stopReplay} onResample={commitResample} />
</main>
```

Pointer, touch, keyboard, and MIDI paths generate stable event/gesture IDs and forward every raw value without tick, runtime frame, input sequence, semantic deduplication, or Host timer.

- [ ] **Step 8: Replace the Browser RED test’s prohibited hooks**

Rewrite `creator_web_perform.spec.mjs` so candidate identity and modules are supplied with `page.route`, following `web_runtime_host_lifecycle.spec.mjs`. Install only dependency factories on the existing seam before navigation:

```js
await routeCandidateIdentity(page, {
  resource_limits: {
    ...WEB_RUNTIME_IDENTITY.resource_limits,
    perform_recording_frames: 86_400_000,
    perform_recording_queue_batches: 32,
  },
  expected_assets: [
    ...creator.expected_assets,
    {prefix: "assets/perform-master-tap.", role: "perform_master_tap_worklet", suffix: ".js"},
  ],
});

await page.addInitScript(() => {
  window.__LMDJ_WEB_HOST_SEAMS__ = {
    ...window.__LMDJ_WEB_HOST_SEAMS__,
    createPerformanceRecordingStore: window.__candidateFactories.realStore,
    createWavStreamWriter: window.__candidateFactories.realWriter,
    createPerformanceMasterTap: window.__candidateFactories.realTap,
  };
});
```

For writer fault, tap fault, and 33rd-batch backpressure, replace only the named factory for that test and let the real production controller observe the failure. Remove `window.__LMDJ_PERFORM_TEST__` and the `lmdjWebRuntimeHost.transport` wrapper. Assert far-side truth through real project inspection/status/replay, OPFS bytes, UI receipts, and exported WAV parsing.

- [ ] **Step 9: Complete the production Browser journeys**

The main journey must perform and verify, in order: v3 open with 16 null slots; assign and move causing v4 refresh; record begin; Pad press/release; Pattern request then actual ack; FX engage/move/release; HOLD on/off; instant Bank switch; flush; stop with tail; PCM16/48 kHz/stereo WAV parse; save/name/bind; Sample replace; replay against current Project; resample commit. Independent tests cover discard cleanup, owner-loss recovery apply/discard, writer failure, tap failure, 33rd-batch backpressure, bind retry, empty-slot silent ack, interruption/close, and replay-stop neutral reset.

- [ ] **Step 10: Run revised Task 9 GREEN verification**

Run:

```bash
npm --prefix apps/creator-web test -- --run
git add -N tests/platform/web/creator/creator_web_perform.spec.mjs
scripts/creator-web.sh proof
scripts/core.sh test dev full
scripts/architecture-portal.sh check
```

Expected: all commands PASS with the routed Stage 10 candidate; an unmodified `1.0.41.0` source/package remains disabled and creates no draft or WAV.

- [ ] **Step 11: Commit revised Task 9 atomically**

Run:

```bash
git add apps/creator-web/src/components/perform_surface.tsx \
  apps/creator-web/src/components/fx_slider_bank.tsx \
  apps/creator-web/src/components/pattern_launch_strip.tsx \
  apps/creator-web/src/state/perform_state.ts \
  apps/creator-web/src/components/mode_rail.tsx apps/creator-web/src/app.tsx \
  apps/creator-web/src/runtime/runtime_types.ts apps/creator-web/src/runtime/project_actions.ts \
  apps/creator-web/src/state/creator_state.ts apps/creator-web/src/state/view_model.ts \
  apps/creator-web/src/styles.css apps/creator-web/test/project_actions.test.ts \
  apps/creator-web/test/perform_surface.test.tsx \
  tests/platform/web/creator/creator_web_perform.spec.mjs
git diff --cached --name-status
git diff --cached --check
git commit -m "feat(creator): build the Perform surface (fixes #435)"
```

Inspect the commit and clean worktree, then ship through `issue-done`.

---

### Task 3: Task 10 — Activate the Capability in Product Build 1.0.42.0

**Issue:** #436. Hard dependency: every Stage 10 functional issue, including merged Task 8A and #435.

**Files:**

- Modify: `packages/authoring-domain/module.json`
- Modify: `packages/project-io/module.json`
- Modify: `packages/project-cooker/module.json`
- Modify: `packages/audio-runtime/module.json`
- Modify: `packages/application-facade/module.json`
- Modify: `packages/web-runtime-platform/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/module.json`
- Modify: `apps/native-host/module.json`
- Modify: `apps/web-runtime-host/module.json`
- Modify: `apps/creator-web/module.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/version.json`
- Modify: `packages/web-runtime-platform/src/manifest_gate.cpp`
- Modify: `packages/web-runtime-platform/test/manifest_gate_test.cpp`
- Modify: `packages/web-runtime-platform/test/runtime_session.test.mjs`
- Modify: `packages/web-runtime-platform/CMakeLists.txt`
- Modify: `apps/web-runtime-host/tools/package.py`
- Modify: `apps/web-runtime-host/test/package_test.py`
- Modify: `apps/web-runtime-host/test/distribution_test.py`
- Modify: `apps/creator-web/tools/package.py`
- Modify: `apps/creator-web/test/package_test.py`
- Modify: `apps/creator-web/test/deployment_smoke_test.py`
- Modify: `apps/creator-web/test/server_test.py`
- Modify: `products/lmdj/generated/web-runtime-identity.json`
- Modify: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`
- Modify: `apps/architecture-portal/docs/contracts/project.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/authoring-domain.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-io.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/project-cooker.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/audio-runtime.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- Modify: `apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx`
- Modify: `apps/architecture-portal/docs/hosts/core-cli.mdx`
- Modify: `apps/architecture-portal/docs/hosts/core-mcp.mdx`
- Modify: `apps/architecture-portal/docs/hosts/native-host.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/product/workflows.mdx`
- Modify: `apps/architecture-portal/docs/product/capability-map.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/diagrams/lmdj-product.architecture.json`
- Modify: `apps/architecture-portal/diagrams/lmdj-core.architecture.json`
- Modify: `apps/architecture-portal/diagrams/authoring-domain.architecture.json`
- Modify: `apps/architecture-portal/diagrams/project-io.architecture.json`
- Modify: `apps/architecture-portal/diagrams/project-cooker.architecture.json`
- Modify: `apps/architecture-portal/diagrams/audio-runtime.architecture.json`
- Modify: `apps/architecture-portal/diagrams/application-facade.architecture.json`
- Modify: `apps/architecture-portal/diagrams/web-runtime-platform.architecture.json`
- Create: `docs/quality/2026-08-30-stage10-perform-acceptance.md`

**Interfaces:**

- Consumes: the Task 8A platform processor/status API and revised #435 Browser journeys without test-only production code.
- Produces: exact resource keys, exactly one `perform_master_tap_worklet` distribution asset, versioned module/Host identities, Product Build `1.0.42.0`, current Portal truth, and formal package acceptance evidence.

- [ ] **Step 1: Repeat the fresh allocation audit before mutation**

Read protected `origin/main`, active manifests, `products/lmdj/version.json`, Assembly, local/remote tags, Releases, release intents, and open PRs. Expected: every target in the main plan version table remains unoccupied. If any target is consumed, stop and amend the version table through design review.

- [ ] **Step 2: Write manifest/package RED tests**

Require both new resource keys and exactly one new asset role:

```python
assert identity["resource_limits"]["perform_recording_frames"] == 86_400_000
assert identity["resource_limits"]["perform_recording_queue_batches"] == 32
perform_taps = [asset for asset in manifest["assets"]
                if asset["role"] == "perform_master_tap_worklet"]
assert len(perform_taps) == 1
assert perform_taps[0]["path"].startswith("assets/perform-master-tap.")
assert perform_taps[0]["path"].endswith(".js")
```

Add negative cases for either missing/wrong resource key, duplicate/missing role, wrong prefix/suffix, digest mismatch, and a main bundle URL that does not resolve to the exact hashed asset.

- [ ] **Step 3: Run integration RED tests**

Run:

```bash
python3 apps/creator-web/test/package_test.py
python3 apps/creator-web/test/deployment_smoke_test.py
python3 apps/creator-web/test/server_test.py
ctest --test-dir build/dev -R 'host.web_manifest_gate' --output-on-failure
```

Expected: FAIL because `1.0.41.0` intentionally lacks the keys and role.

- [ ] **Step 4: Apply versions, Assembly keys, and the locked asset role**

Apply the exact version table from the main plan. Add these exact Assembly values and regenerate identity:

```json
"perform_recording_frames": 86400000,
"perform_recording_queue_batches": 32
```

Append the locked `perform_master_tap_worklet` expected asset to Creator only. Update `package.py` to locate the Vite-emitted processor, hash it as `assets/perform-master-tap.<sha256>.js`, rewrite the single main-bundle reference to that path, include the entry in canonical manifest order, and refuse zero/multiple matches.

- [ ] **Step 5: Make the manifest gate require the formal capability**

For Product Build `1.0.42.0`, validate both positive safe-integer limits and exactly one `perform_master_tap_worklet` role in addition to the existing runtime script/wasm requirements. The gate must reject extra defaults and duplicate role entries. Keep older immutable package verification scoped to its own exact identity rather than retroactively requiring Stage 10 fields.

- [ ] **Step 6: Rerun the unchanged Browser journeys on the formal package**

Build/package Creator, serve the formal output, and run
`creator_web_perform.spec.mjs` without candidate identity routing. Expected:
status transitions `configured → ready`, real engine audio crosses the tap, the exported WAV contains the deterministic left/right witness, and every normal/exception journey reaches the same far-side truth as Task 9.

- [ ] **Step 7: Update current Portal truth and acceptance evidence**

Update every route/source diagram declared in the main plan. Record exact commands, revision, CI run IDs, package digest, manifest digest, processor digest, WAV headers/frame witnesses, Project revisions, and deferred physical rows. Do not claim physical hearing/device acceptance from automation.

- [ ] **Step 8: Run Task 10 GREEN verification**

Run:

```bash
scripts/core.sh test dev full
scripts/core.sh test dev stress
scripts/core.sh coverage check
scripts/core.sh proof
python3 scripts/version.py verify --version-file products/lmdj/version.json
bash tests/build/test_active_tree.sh
python3 apps/creator-web/test/package_test.py
python3 apps/creator-web/test/deployment_smoke_test.py
python3 apps/creator-web/test/server_test.py
scripts/creator-web.sh proof
scripts/architecture-portal.sh check
```

Expected: all commands PASS against Product Build `1.0.42.0` and the package manifest contains exactly one hashed Perform tap asset.

- [ ] **Step 9: Commit Task 10 atomically**

Stage the exact Task 10 file inventory above, inspect the staged diff, and commit:

```bash
git add packages/authoring-domain/module.json packages/project-io/module.json \
  packages/project-cooker/module.json packages/audio-runtime/module.json \
  packages/application-facade/module.json packages/web-runtime-platform/module.json \
  apps/core-cli/module.json apps/core-mcp/module.json apps/native-host/module.json \
  apps/web-runtime-host/module.json apps/creator-web/module.json \
  products/lmdj/assembly.json products/lmdj/version.json \
  packages/web-runtime-platform/src/manifest_gate.cpp \
  packages/web-runtime-platform/test/manifest_gate_test.cpp \
  packages/web-runtime-platform/test/runtime_session.test.mjs \
  packages/web-runtime-platform/CMakeLists.txt \
  apps/web-runtime-host/tools/package.py apps/web-runtime-host/test/package_test.py \
  apps/web-runtime-host/test/distribution_test.py apps/creator-web/tools/package.py \
  apps/creator-web/test/package_test.py apps/creator-web/test/deployment_smoke_test.py \
  apps/creator-web/test/server_test.py products/lmdj/generated/web-runtime-identity.json \
  products/lmdj/generated/web-runtime-identity.mjs \
  apps/architecture-portal/docs/assembly/lmdj.mdx \
  apps/architecture-portal/docs/contracts/project.mdx \
  apps/architecture-portal/docs/core/modules/authoring-domain.mdx \
  apps/architecture-portal/docs/core/modules/project-io.mdx \
  apps/architecture-portal/docs/core/modules/project-cooker.mdx \
  apps/architecture-portal/docs/core/modules/audio-runtime.mdx \
  apps/architecture-portal/docs/core/modules/application-facade.mdx \
  apps/architecture-portal/docs/core/modules/web-runtime-platform.mdx \
  apps/architecture-portal/docs/hosts/core-cli.mdx \
  apps/architecture-portal/docs/hosts/core-mcp.mdx \
  apps/architecture-portal/docs/hosts/native-host.mdx \
  apps/architecture-portal/docs/hosts/web-runtime.mdx \
  apps/architecture-portal/docs/hosts/creator-web.mdx \
  apps/architecture-portal/docs/platform/web-runtime.mdx \
  apps/architecture-portal/docs/product/workflows.mdx \
  apps/architecture-portal/docs/product/capability-map.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx \
  apps/architecture-portal/diagrams/lmdj-product.architecture.json \
  apps/architecture-portal/diagrams/lmdj-core.architecture.json \
  apps/architecture-portal/diagrams/authoring-domain.architecture.json \
  apps/architecture-portal/diagrams/project-io.architecture.json \
  apps/architecture-portal/diagrams/project-cooker.architecture.json \
  apps/architecture-portal/diagrams/audio-runtime.architecture.json \
  apps/architecture-portal/diagrams/application-facade.architecture.json \
  apps/architecture-portal/diagrams/web-runtime-platform.architecture.json \
  docs/quality/2026-08-30-stage10-perform-acceptance.md
git diff --cached --name-status
git diff --cached --check
git commit -m "feat(product): integrate Stage 10 Perform versions and current truth (fixes #436)"
```

Inspect the commit and clean worktree, then ship through `issue-done`. Task 11 remains the separate post-merge immutable Portal snapshot boundary.

## Version Management

Version impact: none for this plan document, Task 8A, and revised Task 9.

Task 10 retains the main Stage 10 targets: Product Build `1.0.42.0`,
audio-runtime `3.0.0`, web-runtime-platform `3.0.0`, creator-web `3.0.0`, and
the other module/Host/Contract targets in the main plan table. The opaque
destination/fallback methods are part of audio-runtime `3.0.0`; capture status,
processor ownership, and exact manifest gating are part of
web-runtime-platform `3.0.0`; the Perform surface and package asset are part of
creator-web `3.0.0`. Task 10 must repeat the allocation audit before writing
any identity.

## Documentation Impact

Documentation impact: none for Task 8A and revised Task 9 because active
`1.0.41.0` remains unconfigured and current Product/Portal truth does not
change. Task 10 has `Documentation impact: required` for every current route
and source diagram listed in the main Stage 10 plan; Task 11 creates the
separate immutable `1.0.42.0` snapshot after Task 10 merges.

## Execution Order

```text
merged #434
  → Task 8A platform master-tap graph
      → revised #435 Creator projection + Perform surface
          → #436 Product Build 1.0.42.0 integration
              → #438 immutable snapshot
                  → #468 audited canary release
```

Do not reuse the two untracked #435 RED files unchanged: rewrite their session
API and injection strategy in Task 2 before treating them as executable RED
evidence.
