import {afterEach, beforeEach, expect, test, vi} from "vitest";
import {createPadCapture} from "../src/capture/pad_capture";
import {createPadCaptureSources} from "../src/capture/pad_capture_sources";
import type {CreatorPerformanceRuntimeSession} from "../src/runtime/runtime_types";
import type {PadCaptureHandle} from "../src/capture/pad_capture";

const resources = vi.hoisted(() => ({live: false, stopped: vi.fn(), started: vi.fn()}));
vi.mock("../src/capture/capture_controller", () => ({
  browserCaptureDeps: () => ({}),
  CaptureController: class {
    async start() {resources.live = true; resources.started();}
    async stop() {resources.live = false; resources.stopped();}
  },
}));
const settle = async () => {for (let i = 0; i < 40; i++) await Promise.resolve();};
const closed = vi.fn(async () => {});
const resumed = vi.fn(() => new Promise<void>(() => {}));
beforeEach(() => {
  vi.clearAllMocks(); resources.live = false;
  vi.stubGlobal("AudioContext", class {
    resume = resumed;
    close = closed;
  });
});
afterEach(() => vi.unstubAllGlobals());

test.each(["release", "cancel"])("%s closes microphone resources even while resume never settles", async action => {
  const sources = createPadCaptureSources();
  const commit = vi.fn(async () => {});
  const capture = createPadCapture({microphoneGranted: () => true,
    prepareMicrophone: async () => {}, canStart: () => true, changed: () => {}, commit,
    start: (source, batch, failed, signal) => sources.start(source, null,
      Promise.resolve(true), batch, failed, signal),
  }, "microphone");
  const key = {};
  capture.press({projectId: "original", slot: 17, revision: 4}, key);
  await settle();
  expect(resources.live).toBe(true);
  expect(resumed).toHaveBeenCalledOnce();
  if (action === "release") capture.release(key);
  else void capture.cancel();
  await settle();
  expect(resources.live).toBe(false);
  expect(resources.stopped).toHaveBeenCalledOnce();
  expect(closed).toHaveBeenCalledOnce();
  expect(capture.getState().phase).toBe("review");
  expect(commit).not.toHaveBeenCalled();
});

test("cold touch activation does not create microphone resources before its legal release", async () => {
  const sources = createPadCaptureSources();
  const controller = new AbortController();
  const wake = new Promise<boolean>(() => {});
  const started = sources.start("microphone", null, wake, () => {}, () => {}, controller.signal, true);
  const refused = expect(started).rejects.toMatchObject({name: "AbortError"});
  await settle();
  expect(resumed).not.toHaveBeenCalled();
  expect(resources.started).not.toHaveBeenCalled();
  controller.abort();
  await refused;
  expect(resumed).not.toHaveBeenCalled();
  expect(resources.live).toBe(false);
});

test.each(["pending", "refused"])("legal native microphone press resumes synchronously with %s Runtime activation", async activation => {
  const sources = createPadCaptureSources();
  const runtime = activation === "pending" ? new Promise<boolean>(() => {}) : Promise.resolve(false);
  resumed.mockResolvedValueOnce(undefined);
  const started = sources.start("microphone", null, runtime, () => {}, () => {});
  // Check the same call stack, before any microtask or permission await.
  expect(resumed).toHaveBeenCalledOnce();
  const handle = await started;
  expect(resources.live).toBe(true);
  await handle.stop();
  expect(resources.live).toBe(false);
});

test("cancel waits for a late master handle to finish stopping before permitting another take", async () => {
  let acquire!: (handle: PadCaptureHandle) => void;
  let finishStop!: () => void;
  const stop = vi.fn(() => new Promise<void>(resolve => {finishStop = resolve;}));
  const session = {startPerformanceMasterCapture: () => new Promise<PadCaptureHandle>(resolve => {
    acquire = resolve;
  })} as unknown as CreatorPerformanceRuntimeSession;
  const sources = createPadCaptureSources();
  const commit = vi.fn(async () => {});
  const capture = createPadCapture({microphoneGranted: () => true,
    prepareMicrophone: async () => {}, canStart: () => true, changed: () => {}, commit,
    start: (source, batch, failed, signal) => sources.start(source, session,
      null, batch, failed, signal),
  }, "master");
  const target = {projectId: "original", slot: 17, revision: 4};
  capture.press(target, {});
  await settle();
  const cancelled = capture.cancel();
  await settle();
  expect(capture.getState().phase).toBe("stopping");
  capture.discard();
  expect(capture.press(target, {})).toBe(false);
  acquire({stop});
  await settle();
  expect(stop).toHaveBeenCalledOnce();
  expect(capture.getState().phase).toBe("stopping");
  finishStop();
  await cancelled;
  expect(capture.getState().phase).toBe("review");
  expect(commit).not.toHaveBeenCalled();
  capture.discard();
  expect(capture.getState().phase).toBe("idle");
});
