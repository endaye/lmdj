import {describe, expect, test, vi} from "vitest";

import {
  MasterTapBatchQueue,
  PERFORM_BACKPRESSURE_MESSAGE,
  PERFORM_BATCH_FRAMES,
  PERFORM_QUEUE_BATCHES,
  PERFORM_WORKLET_NAME,
  PERFORM_WORKLET_SOURCE,
} from "../src/record/master_tap_source";

const PERFORM_LIMIT_MESSAGE =
  "Recording reached the 30-minute limit. The durable WAV is ready to save.";

interface WorkletMessage { channels: Float32Array[] }
interface StubProcessor {
  port: {onmessage: ((event: {data: unknown}) => void) | null};
  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean;
}

function loadProcessorClass(
  onMessage: (message: WorkletMessage) => void,
  postMessage: ((message: WorkletMessage) => void) | null = null,
): new () => StubProcessor {
  class StubAudioWorkletProcessor {
    port = {
      onmessage: null as ((event: {data: unknown}) => void) | null,
      postMessage: (message: WorkletMessage) =>
        (postMessage ?? onMessage)(message),
    };
  }
  let registered: (new () => StubProcessor) | null = null;
  const registerProcessor = (name: string, ctor: new () => StubProcessor) => {
    expect(name).toBe(PERFORM_WORKLET_NAME);
    registered = ctor;
  };
  const factory = new Function(
    "AudioWorkletProcessor",
    "registerProcessor",
    PERFORM_WORKLET_SOURCE,
  );
  factory(StubAudioWorkletProcessor, registerProcessor);
  if (registered === null) throw new Error("registerProcessor was not called");
  return registered;
}

describe("Perform master tap", () => {
  test("ships as the exact same-origin source and posts stereo 4800-frame batches", () => {
    expect(PERFORM_BATCH_FRAMES).toBe(4_800);
    expect(PERFORM_QUEUE_BATCHES).toBe(32);
    expect(PERFORM_WORKLET_SOURCE).toContain(
      `const PERFORM_BATCH_FRAMES = ${PERFORM_BATCH_FRAMES};`,
    );
    const messages: WorkletMessage[] = [];
    const Processor = loadProcessorClass((message) => messages.push(message));
    const processor = new Processor();
    const left = new Float32Array(PERFORM_BATCH_FRAMES).fill(0.25);
    const right = new Float32Array(PERFORM_BATCH_FRAMES).fill(-0.5);
    const output = [new Float32Array(PERFORM_BATCH_FRAMES), new Float32Array(PERFORM_BATCH_FRAMES)];

    const result = processor.process([[left, right]], [output]);
    expect(result).toBe(true);
    expect(result).not.toBeInstanceOf(Promise);
    expect(messages).toHaveLength(1);
    expect(messages[0]?.channels).toHaveLength(2);
    expect(messages[0]?.channels[0]).toHaveLength(PERFORM_BATCH_FRAMES);
    expect(output[0]).toEqual(left);
    expect(output[1]).toEqual(right);
  });

  test("accepts only 32 pending batches, seals on the 33rd, and reports the dropped tail", async () => {
    let finishWrite: (() => void) | undefined;
    const firstWrite = new Promise<void>((resolve) => { finishWrite = resolve; });
    const writer = {
      queueBatchLimit: PERFORM_QUEUE_BATCHES,
      appendChannels: vi.fn(async () => {
        await firstWrite;
        return {
          state: "active", durableFrames: PERFORM_BATCH_FRAMES,
          byteLength: 44 + PERFORM_BATCH_FRAMES * 4, reason: null,
        };
      }),
      seal: vi.fn(async (reason: string) => ({
        state: "sealed", durableFrames: PERFORM_BATCH_FRAMES,
        byteLength: 44 + PERFORM_BATCH_FRAMES * 4, reason,
      })),
    };
    const onFailure = vi.fn();
    const queue = new MasterTapBatchQueue(writer as never, {onFailure});
    const batch = [
      new Float32Array(PERFORM_BATCH_FRAMES),
      new Float32Array(PERFORM_BATCH_FRAMES),
    ];

    for (let index = 0; index < PERFORM_QUEUE_BATCHES; index += 1) {
      const returned = queue.acceptBatch(batch);
      expect(returned).toBeUndefined();
    }
    expect(queue.pendingBatches).toBe(PERFORM_QUEUE_BATCHES);
    queue.acceptBatch(batch);
    expect(queue.sealed).toBe(true);
    expect(queue.droppedFrames).toBe(PERFORM_QUEUE_BATCHES * PERFORM_BATCH_FRAMES);
    expect(writer.appendChannels).toHaveBeenCalledTimes(1);

    finishWrite?.();
    const settled = await queue.settled;
    expect(writer.seal).toHaveBeenCalledWith("backpressure");
    expect(onFailure).toHaveBeenCalledWith({
      reason: "backpressure",
      message: PERFORM_BACKPRESSURE_MESSAGE,
      durableFrames: PERFORM_BATCH_FRAMES,
      droppedFrames: PERFORM_QUEUE_BATCHES * PERFORM_BATCH_FRAMES,
    });
    expect(settled).toMatchObject({
      reason: "backpressure",
      droppedFrames: PERFORM_QUEUE_BATCHES * PERFORM_BATCH_FRAMES,
    });
    expect(Object.isFrozen(settled)).toBe(true);
  });

  test("treats frame limit as terminal, drops queued tail, reports it, and settles", async () => {
    const writer = {
      queueBatchLimit: PERFORM_QUEUE_BATCHES,
      appendChannels: vi.fn(async () => ({
        state: "sealed", durableFrames: 86_400_000,
        byteLength: 345_600_044, reason: "frame-limit",
      })),
      seal: vi.fn(async (reason: string) => ({
        state: "sealed", durableFrames: 86_400_000,
        byteLength: 345_600_044, reason,
      })),
    };
    const onFailure = vi.fn();
    const queue = new MasterTapBatchQueue(writer as never, {onFailure});
    const batch = [
      new Float32Array(PERFORM_BATCH_FRAMES),
      new Float32Array(PERFORM_BATCH_FRAMES),
    ];
    queue.acceptBatch(batch);
    queue.acceptBatch(batch);

    await vi.waitFor(() => expect(queue.sealed).toBe(true));
    const settled = await queue.settled;
    expect(queue.sealed).toBe(true);
    expect(queue.droppedFrames).toBe(PERFORM_BATCH_FRAMES);
    expect(writer.appendChannels).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledWith({
      reason: "frame-limit",
      message: PERFORM_LIMIT_MESSAGE,
      durableFrames: 86_400_000,
      droppedFrames: PERFORM_BATCH_FRAMES,
    });
    expect(settled).toMatchObject({
      reason: "frame-limit",
      droppedFrames: PERFORM_BATCH_FRAMES,
    });
    queue.acceptBatch(batch);
    expect(writer.appendChannels).toHaveBeenCalledTimes(1);
  });

  test("stop request posts the lossless partial tail then stops recording without stopping audio", () => {
    const messages: Array<Record<string, unknown>> = [];
    const Processor = loadProcessorClass((message) =>
      messages.push(message as unknown as Record<string, unknown>));
    const processor = new Processor();
    const left = new Float32Array(127).fill(0.25);
    const right = new Float32Array(127).fill(-0.5);
    const beforeStopOutput = [new Float32Array(127), new Float32Array(127)];
    processor.process([[left, right]], [beforeStopOutput]);
    expect(messages).toHaveLength(0);

    processor.port.onmessage?.({data: {type: "stop"}});
    expect(messages).toHaveLength(2);
    expect(messages[0]).toMatchObject({type: "batch"});
    expect((messages[0]?.channels as Float32Array[])[0]).toHaveLength(127);
    expect(messages[1]).toEqual({type: "stopped"});

    const afterStopOutput = [new Float32Array(127), new Float32Array(127)];
    expect(processor.process([[left, right]], [afterStopOutput])).toBe(true);
    expect(afterStopOutput[0]).toEqual(left);
    expect(afterStopOutput[1]).toEqual(right);
    expect(messages).toHaveLength(2);
  });

  test("main-thread stop waits for every full or partial batch before sealing stopped", async () => {
    let finishWrite: (() => void) | undefined;
    const write = new Promise<void>((resolve) => { finishWrite = resolve; });
    const writer = {
      queueBatchLimit: PERFORM_QUEUE_BATCHES,
      appendChannels: vi.fn(async () => {
        await write;
        return {state: "active", durableFrames: 0, byteLength: 44, reason: null};
      }),
      seal: vi.fn(async (reason: string) => ({
        state: "sealed", durableFrames: 127, byteLength: 552, reason,
      })),
    };
    const port = {
      onmessage: null as ((event: {data: unknown}) => void) | null,
      postMessage: vi.fn(),
    };
    const queue = new MasterTapBatchQueue(writer as never, {onFailure: vi.fn()});
    const stoppable = queue as unknown as {
      connect(value: typeof port): void;
      stop(): Promise<unknown>;
    };
    expect(typeof stoppable.connect).toBe("function");
    expect(typeof stoppable.stop).toBe("function");
    stoppable.connect(port);
    const stopping = stoppable.stop();
    expect(port.postMessage).toHaveBeenCalledWith({type: "stop"});
    port.onmessage?.({data: {
      type: "batch",
      channels: [new Float32Array(127), new Float32Array(127)],
    }});
    port.onmessage?.({data: {type: "stopped"}});
    expect(writer.seal).not.toHaveBeenCalled();

    finishWrite?.();
    await expect(stopping).resolves.toMatchObject({reason: "stopped", durableFrames: 127});
    expect(writer.appendChannels).toHaveBeenCalledTimes(1);
    expect(writer.seal).toHaveBeenCalledWith("stopped");
  });

  test("latches a batch post failure and attempts a Host-visible failure without breaking render", () => {
    const messages: Array<Record<string, unknown>> = [];
    let posts = 0;
    const Processor = loadProcessorClass(
      () => {},
      (message) => {
        posts += 1;
        if (posts === 1) throw new Error("post failed");
        messages.push(message as unknown as Record<string, unknown>);
      },
    );
    const processor = new Processor();
    const left = new Float32Array(PERFORM_BATCH_FRAMES).fill(0.25);
    const right = new Float32Array(PERFORM_BATCH_FRAMES).fill(-0.5);
    const output = [new Float32Array(PERFORM_BATCH_FRAMES), new Float32Array(PERFORM_BATCH_FRAMES)];

    expect(() => processor.process([[left, right]], [output])).not.toThrow();
    expect(output[0]).toEqual(left);
    expect(output[1]).toEqual(right);
    expect(messages).toEqual([{
      type: "failed",
      reason: "post-message-failed",
      droppedFrames: PERFORM_BATCH_FRAMES,
    }]);
    processor.process([[left, right]], [output]);
    expect(posts).toBe(2);
  });

  test.each(["frame-limit", "writer-error", "opfs-failure"] as const)(
    "%s latches terminal state, stops the worklet once, and drops its ordered stale tail",
    async (reason) => {
      const writerDropped = reason === "frame-limit" ? 3 : 4_800;
      const writer = {
        queueBatchLimit: PERFORM_QUEUE_BATCHES,
        appendChannels: vi.fn(async () => ({
          state: "sealed", durableFrames: 9_600,
          byteLength: 38_444, reason, droppedFrames: writerDropped,
        })),
        seal: vi.fn(async () => ({
          state: "sealed", durableFrames: 9_600,
          byteLength: 38_444, reason, droppedFrames: writerDropped,
        })),
      };
      const port = {
        onmessage: null as ((event: {data: unknown}) => void) | null,
        postMessage: vi.fn(),
      };
      const onFailure = vi.fn();
      const queue = new MasterTapBatchQueue(writer as never, {onFailure});
      queue.connect(port);
      queue.acceptBatch([
        new Float32Array(PERFORM_BATCH_FRAMES),
        new Float32Array(PERFORM_BATCH_FRAMES),
      ]);
      await vi.waitFor(() => expect(port.postMessage).toHaveBeenCalledTimes(1));
      expect(port.postMessage).toHaveBeenCalledWith({type: "stop"});

      port.onmessage?.({data: {
        type: "batch",
        channels: [new Float32Array(127), new Float32Array(127)],
      }});
      expect(writer.appendChannels).toHaveBeenCalledTimes(1);
      port.onmessage?.({data: {type: "stopped"}});
      const settled = await queue.settled;

      expect(port.postMessage).toHaveBeenCalledTimes(1);
      expect(onFailure).toHaveBeenCalledTimes(1);
      expect(onFailure).toHaveBeenCalledWith(expect.objectContaining({
        reason,
        droppedFrames: writerDropped + 127,
      }));
      expect(settled).toMatchObject({
        reason,
        droppedFrames: writerDropped + 127,
      });
      expect(Object.isFrozen(settled)).toBe(true);
      port.onmessage?.({data: {
        type: "batch",
        channels: [new Float32Array(61), new Float32Array(61)],
      }});
      port.onmessage?.({data: {type: "stopped"}});
      expect(writer.appendChannels).toHaveBeenCalledTimes(1);
      expect(port.postMessage).toHaveBeenCalledTimes(1);
      expect(onFailure).toHaveBeenCalledTimes(1);
    },
  );

  test("backpressure stops once and counts rejected, queued, stale, and writer-pending frames", async () => {
    let finishWrite: (() => void) | undefined;
    const write = new Promise<void>((resolve) => { finishWrite = resolve; });
    const writer = {
      queueBatchLimit: 1,
      appendChannels: vi.fn(async () => {
        await write;
        return {state: "active", durableFrames: 0, byteLength: 44, reason: null};
      }),
      seal: vi.fn(async () => ({
        state: "sealed", durableFrames: 0, byteLength: 44,
        reason: "backpressure", droppedFrames: PERFORM_BATCH_FRAMES,
      })),
    };
    const port = {
      onmessage: null as ((event: {data: unknown}) => void) | null,
      postMessage: vi.fn(),
    };
    const onFailure = vi.fn();
    const queue = new MasterTapBatchQueue(writer as never, {onFailure});
    queue.connect(port);
    const batch = [
      new Float32Array(PERFORM_BATCH_FRAMES),
      new Float32Array(PERFORM_BATCH_FRAMES),
    ];
    queue.acceptBatch(batch);
    queue.acceptBatch(batch);
    expect(port.postMessage).toHaveBeenCalledTimes(1);
    port.onmessage?.({data: {
      type: "batch",
      channels: [new Float32Array(127), new Float32Array(127)],
    }});
    port.onmessage?.({data: {type: "stopped"}});
    finishWrite?.();
    const settled = await queue.settled;

    expect(writer.appendChannels).toHaveBeenCalledTimes(1);
    expect(writer.seal).toHaveBeenCalledWith("backpressure");
    expect(onFailure).toHaveBeenCalledWith(expect.objectContaining({
      reason: "backpressure",
      droppedFrames: PERFORM_BATCH_FRAMES * 2 + 127,
    }));
    expect(settled).toMatchObject({
      reason: "backpressure",
      droppedFrames: PERFORM_BATCH_FRAMES * 2 + 127,
    });
  });

  test("tap failure stops once, rejects later batches, and settles without a stopped echo", async () => {
    const writer = {
      queueBatchLimit: PERFORM_QUEUE_BATCHES,
      appendChannels: vi.fn(),
      seal: vi.fn(async () => ({
        state: "sealed", durableFrames: 0, byteLength: 44,
        reason: "tap-failure", droppedFrames: 0,
      })),
    };
    const port = {
      onmessage: null as ((event: {data: unknown}) => void) | null,
      postMessage: vi.fn(),
    };
    const onFailure = vi.fn();
    const queue = new MasterTapBatchQueue(writer as never, {onFailure});
    queue.connect(port);
    port.onmessage?.({data: {
      type: "failed", reason: "post-message-failed", droppedFrames: 73,
    }});
    await queue.settled;
    expect(port.postMessage).toHaveBeenCalledTimes(1);
    queue.acceptBatch([new Float32Array(61), new Float32Array(61)]);
    expect(writer.appendChannels).not.toHaveBeenCalled();
    expect(port.postMessage).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledWith(expect.objectContaining({
      reason: "tap-failure", droppedFrames: 73,
    }));
  });

  test("throwing failure listener cannot prevent one immutable terminal settlement", async () => {
    const writer = {
      queueBatchLimit: PERFORM_QUEUE_BATCHES,
      appendChannels: vi.fn(async () => ({
        state: "sealed", durableFrames: 4_800, byteLength: 19_244,
        reason: "writer-error", droppedFrames: 31,
      })),
      seal: vi.fn(async () => ({
        state: "sealed", durableFrames: 4_800, byteLength: 19_244,
        reason: "writer-error", droppedFrames: 31,
      })),
    };
    const onFailure = vi.fn(() => { throw new Error("listener failed"); });
    const queue = new MasterTapBatchQueue(writer as never, {onFailure});
    queue.acceptBatch([
      new Float32Array(PERFORM_BATCH_FRAMES),
      new Float32Array(PERFORM_BATCH_FRAMES),
    ]);

    const outcome = await Promise.race([
      queue.settled,
      new Promise<"timeout">((resolve) => setTimeout(() => resolve("timeout"), 50)),
    ]);
    expect(outcome).not.toBe("timeout");
    expect(outcome).toMatchObject({
      state: "sealed", reason: "writer-error", droppedFrames: 31,
    });
    expect(Object.isFrozen(outcome)).toBe(true);
    expect(onFailure).toHaveBeenCalledTimes(1);
  });
});
