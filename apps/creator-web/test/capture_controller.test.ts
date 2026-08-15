import {describe, expect, test, vi} from "vitest";
import {CaptureController, CapturePermissionError} from "../src/capture/capture_controller";
import {CAPTURE_WORKLET_SOURCE} from "../src/capture/capture_worklet_source";

function makeDeps(overrides: Record<string, unknown> = {}) {
  const track = {
    stopped: 0, stop() { this.stopped += 1; },
    onended: null as (() => void) | null,
    addEventListener(name: string, handler: () => void) { if (name === "ended") this.onended = handler; },
    removeEventListener() {},
    getSettings: () => ({channelCount: 1}),
  };
  const stream = {getAudioTracks: () => [track]};
  // connect is a spy, not a counter: the test must be able to prove the source
  // is wired to the worklet node and NOT to any output (S8B-D4 anti-feedback).
  const source = {connect: vi.fn(), disconnect: vi.fn()};
  const node = {
    port: {onmessage: null as ((event: {data: {channels: Float32Array[]; peak: number}}) => void) | null},
    disconnect: vi.fn(),
  };
  const context = {
    sampleRate: 48_000, closed: 0,
    audioWorklet: {added: [] as string[], async addModule(url: string) { this.added.push(url); }},
    createMediaStreamSource: () => source,
    async close() { this.closed += 1; },
  };
  return {
    track, stream, source, node, context,
    deps: {
      getUserMedia: vi.fn(async () => stream),
      createContext: () => context,
      createNode: () => node,
      createModuleUrl: vi.fn(() => "blob:capture"),
      revokeModuleUrl: vi.fn(),
      ...overrides,
    },
  };
}

describe("CaptureController", () => {
  test("requests raw audio constraints and wires the graph", async () => {
    const {deps, context, source, node} = makeDeps();
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await controller.start();
    expect(deps.getUserMedia).toHaveBeenCalledWith({audio: {
      echoCancellation: false, noiseSuppression: false, autoGainControl: false,
    }});
    expect(deps.createModuleUrl).toHaveBeenCalledWith(CAPTURE_WORKLET_SOURCE);
    expect(context.audioWorklet.added).toEqual(["blob:capture"]);
    // S8B-D4: wired to the worklet node, never to an output.
    expect(source.connect).toHaveBeenCalledTimes(1);
    expect(source.connect).toHaveBeenCalledWith(node);
    expect(controller.channelCount).toBe(1);
  });

  test("releases the microphone when setup fails after getUserMedia", async () => {
    const {deps, track, context} = makeDeps();
    context.audioWorklet.addModule = async () => { throw new Error("CSP blocked"); };
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await expect(controller.start()).rejects.toThrow("CSP blocked");
    // The stream was live; it must not be left running with no owner.
    expect(track.stopped).toBe(1);
    expect(context.closed).toBe(1);
    expect(deps.revokeModuleUrl).toHaveBeenCalledTimes(1);
    // stop() afterwards stays a safe no-op, releasing nothing a second time.
    await controller.stop();
    expect(track.stopped).toBe(1);
  });

  test("keeps the original setup error when cleanup itself fails", async () => {
    const {deps, context} = makeDeps();
    context.audioWorklet.addModule = async () => { throw new Error("CSP blocked"); };
    context.close = async () => { throw new Error("close failed"); };
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    // The setup failure is the real cause; a failing close() must not mask it.
    await expect(controller.start()).rejects.toThrow("CSP blocked");
    expect(deps.revokeModuleUrl).toHaveBeenCalledTimes(1);
  });

  test("maps getUserMedia rejection to CapturePermissionError", async () => {
    const {deps} = makeDeps({getUserMedia: vi.fn(async () => { throw new DOMException("denied", "NotAllowedError"); })});
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await expect(controller.start()).rejects.toBeInstanceOf(CapturePermissionError);
  });

  test("forwards worklet batches to the listener", async () => {
    const {deps, node} = makeDeps();
    const onBatch = vi.fn();
    const controller = new CaptureController(deps as never, {onBatch, onEnded: vi.fn()});
    await controller.start();
    node.port.onmessage?.({data: {channels: [new Float32Array(4800)], peak: 0.7}});
    expect(onBatch).toHaveBeenCalledWith([expect.any(Float32Array)], 0.7);
  });

  test("stops once as the single owner and is idempotent", async () => {
    const {deps, track, node, source, context} = makeDeps();
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await controller.start();
    await controller.stop();
    await controller.stop();
    expect(track.stopped).toBe(1);
    expect(node.disconnect).toHaveBeenCalledTimes(1);
    expect(source.disconnect).toHaveBeenCalledTimes(1);
    expect(context.closed).toBe(1);
    expect(deps.revokeModuleUrl).toHaveBeenCalledTimes(1);
  });

  test("still revokes the module URL when stop()'s context.close() rejects", async () => {
    const {deps, context} = makeDeps();
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await controller.start();
    context.close = async () => { throw new Error("close failed"); };
    // stop() may still reject (its own error is not swallowed); what must be
    // guaranteed is that the Blob URL revoke runs regardless. Catch here so
    // the rejection doesn't surface as an unhandled promise rejection.
    await controller.stop().catch(() => undefined);
    expect(deps.revokeModuleUrl).toHaveBeenCalledTimes(1);
  });

  test("reports track end as device loss", async () => {
    const {deps, track} = makeDeps();
    const onEnded = vi.fn();
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded});
    await controller.start();
    track.onended?.();
    expect(onEnded).toHaveBeenCalledWith("device-lost");
  });
});

describe("CAPTURE_WORKLET_SOURCE", () => {
  interface WorkletMessage {
    channels: Float32Array[];
    peak: number;
  }
  interface StubProcessor {
    process(inputs: Float32Array[][]): boolean;
  }

  function loadProcessorClass(
    onMessage: (message: WorkletMessage) => void,
  ): new () => StubProcessor {
    class StubAudioWorkletProcessor {
      port: {postMessage: (message: WorkletMessage, transfer?: ArrayBuffer[]) => void};
      constructor() {
        this.port = {
          postMessage: (message, _transfer) => {
            // Capture the batch contents now: the real runtime detaches the
            // transferred ArrayBuffers immediately after postMessage returns.
            onMessage({channels: message.channels, peak: message.peak});
          },
        };
      }
    }
    let registered: (new () => StubProcessor) | null = null;
    const registerProcessor = (_name: string, ctor: new () => StubProcessor) => {
      registered = ctor;
    };
    // The processor ships as a source string, so evaluating it is the only
    // way to test it directly; the stub globals stand in for the real
    // AudioWorkletGlobalScope.
    const factory = new Function("AudioWorkletProcessor", "registerProcessor", CAPTURE_WORKLET_SOURCE);
    factory(StubAudioWorkletProcessor, registerProcessor);
    if (registered === null) { throw new Error("registerProcessor was not called"); }
    return registered;
  }

  test("posts no message before 4,800 frames accumulate, then exactly one with the correct peak", () => {
    const messages: WorkletMessage[] = [];
    const Processor = loadProcessorClass((message) => messages.push(message));
    const processor = new Processor();
    const quantum = new Float32Array(128).fill(0.25);
    for (let i = 0; i < 37; i += 1) {
      processor.process([[quantum]]); // 37 * 128 = 4,736 frames
    }
    expect(messages).toHaveLength(0);
    processor.process([[quantum]]); // 38 * 128 = 4,864 frames, crosses the 4,800 edge
    expect(messages).toHaveLength(1);
    expect(messages[0]?.channels[0]).toHaveLength(4_800);
    expect(messages[0]?.peak).toBeCloseTo(0.25);
  });

  test("a quantum straddling the batch edge posts correctly and keeps accepting frames", () => {
    const messages: WorkletMessage[] = [];
    const Processor = loadProcessorClass((message) => messages.push(message));
    const processor = new Processor();
    const filler = new Float32Array(128).fill(0.25);
    for (let i = 0; i < 37; i += 1) {
      processor.process([[filler]]); // fills the first batch to 4,736 frames
    }
    // This quantum straddles the edge: its first 64 frames complete batch 1
    // (peak 0.9), its last 64 frames start a freshly reallocated batch 2
    // (peak 0.3). If the batch were allocated outside the while loop instead
    // of inside it, writing this second half would throw on a null buffer.
    const straddle = new Float32Array(128);
    straddle.fill(0.9, 0, 64);
    straddle.fill(0.3, 64, 128);
    expect(() => processor.process([[straddle]])).not.toThrow();
    expect(messages).toHaveLength(1);
    expect(messages[0]?.channels[0]).toHaveLength(4_800);
    expect(messages[0]?.peak).toBeCloseTo(0.9);

    // Keep feeding frames: batch 2 needs 4,736 more frames (37 quanta of 0.4)
    // to reach 4,800 and confirm the controller keeps working post-straddle.
    const tail = new Float32Array(128).fill(0.4);
    for (let i = 0; i < 37; i += 1) {
      expect(() => processor.process([[tail]])).not.toThrow();
    }
    expect(messages).toHaveLength(2);
    expect(messages[1]?.channels[0]).toHaveLength(4_800);
    expect(messages[1]?.peak).toBeCloseTo(0.4);
  });
});
