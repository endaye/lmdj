import {readFileSync} from "node:fs";
import {resolve} from "node:path";

import {describe, expect, test, vi} from "vitest";

import {
  MasterTapBatchQueue,
  PERFORM_BACKPRESSURE_MESSAGE,
  PERFORM_BATCH_FRAMES,
  PERFORM_LIMIT_MESSAGE,
  PERFORM_TAP_FAILURE_MESSAGE,
} from "../src/record/master_tap_source";

function batch(frames = PERFORM_BATCH_FRAMES) {
  return [new Float32Array(frames), new Float32Array(frames)] as const;
}

test("production Creator statically supplies the platform capture factory", () => {
  const source = readFileSync(
    resolve(process.cwd(), "src/main.tsx"),
    "utf8",
  );
  expect(source).toContain(
    'import {createPerformanceMasterTap} from\n' +
    '  "@lmdj/web-runtime-platform/performance_master_capture.mjs";',
  );
  expect(source).toContain(
    "seams: {\n      createPerformanceMasterTap,\n      ...seams,\n    },",
  );
});

describe("Perform master capture sink", () => {
  test("accepts 32 pending batches and asks its owner to stop once on the 33rd", async () => {
    let finishWrite: (() => void) | undefined;
    const firstWrite = new Promise<void>((resolve) => { finishWrite = resolve; });
    const writer = {
      queueBatchLimit: 32,
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
    const listener = {onFailure: vi.fn(), requestCaptureStop: vi.fn()};
    const queue = new MasterTapBatchQueue(writer as never, listener);

    for (let index = 0; index < 32; index += 1) queue.onBatch(batch());
    expect(queue.pendingBatches).toBe(32);
    queue.onBatch(batch());
    queue.onBatch(batch(127));
    expect(queue.sealed).toBe(true);
    expect(listener.requestCaptureStop).toHaveBeenCalledTimes(1);
    expect(writer.seal).not.toHaveBeenCalled();

    finishWrite?.();
    await vi.waitFor(() => expect(queue.pendingBatches).toBe(0));
    expect(writer.seal).not.toHaveBeenCalled();
    queue.onStopped();
    const settled = await queue.settled;
    expect(writer.seal).toHaveBeenCalledWith("backpressure");
    expect(listener.onFailure).toHaveBeenCalledWith({
      reason: "backpressure",
      message: PERFORM_BACKPRESSURE_MESSAGE,
      durableFrames: PERFORM_BATCH_FRAMES,
      droppedFrames: 32 * PERFORM_BATCH_FRAMES + 127,
    });
    expect(settled).toMatchObject({
      reason: "backpressure",
      droppedFrames: 32 * PERFORM_BATCH_FRAMES + 127,
    });
  });

  test("normal stop drains the final partial batch before sealing", async () => {
    let finishWrite: (() => void) | undefined;
    const writing = new Promise<void>((resolve) => { finishWrite = resolve; });
    const writer = {
      queueBatchLimit: 32,
      appendChannels: vi.fn(async () => {
        await writing;
        return {state: "active", durableFrames: 127, byteLength: 552, reason: null};
      }),
      seal: vi.fn(async (reason: string) => ({
        state: "sealed", durableFrames: 127, byteLength: 552, reason,
      })),
    };
    const queue = new MasterTapBatchQueue(writer as never, {
      onFailure: vi.fn(), requestCaptureStop: vi.fn(),
    });
    queue.onBatch(batch(127));
    queue.onStopped();
    expect(writer.seal).not.toHaveBeenCalled();
    finishWrite?.();
    await expect(queue.settled).resolves.toMatchObject({
      reason: "stopped", durableFrames: 127,
    });
    expect(writer.seal).toHaveBeenCalledWith("stopped");
  });

  test.each([
    ["frame-limit", PERFORM_LIMIT_MESSAGE],
    ["writer-error", expect.stringContaining("storage failed")],
  ] as const)("%s seals only after platform stop acknowledgement", async (reason, message) => {
    const writer = {
      queueBatchLimit: 32,
      appendChannels: vi.fn(async () => ({
        state: "sealed", durableFrames: 9_600, byteLength: 38_444,
        reason, droppedFrames: 3,
      })),
      seal: vi.fn(async () => ({
        state: "sealed", durableFrames: 9_600, byteLength: 38_444,
        reason, droppedFrames: 3,
      })),
    };
    const listener = {onFailure: vi.fn(), requestCaptureStop: vi.fn()};
    const queue = new MasterTapBatchQueue(writer as never, listener);
    queue.onBatch(batch());
    await vi.waitFor(() => expect(listener.requestCaptureStop).toHaveBeenCalledOnce());
    expect(writer.seal).not.toHaveBeenCalled();
    queue.onBatch(batch(127));
    queue.onStopped();
    const settled = await queue.settled;
    expect(settled).toMatchObject({reason, droppedFrames: 3 + 127});
    expect(listener.onFailure).toHaveBeenCalledWith(expect.objectContaining({
      reason, message,
    }));
  });

  test("platform tap failure requests control-path stop and contains listener exceptions", async () => {
    const writer = {
      queueBatchLimit: 32,
      appendChannels: vi.fn(),
      seal: vi.fn(async () => ({
        state: "sealed", durableFrames: 0, byteLength: 44,
        reason: "tap-failure", droppedFrames: 0,
      })),
    };
    const listener = {
      onFailure: vi.fn(() => { throw new Error("listener failed"); }),
      requestCaptureStop: vi.fn(() => { throw new Error("owner failed"); }),
    };
    const queue = new MasterTapBatchQueue(writer as never, listener);
    expect(() => queue.onFailure("tap-failure", 73)).not.toThrow();
    expect(listener.requestCaptureStop).toHaveBeenCalledOnce();
    expect(writer.seal).not.toHaveBeenCalled();
    queue.onStopped();
    await expect(queue.settled).resolves.toMatchObject({
      state: "sealed", reason: "tap-failure", droppedFrames: 73,
    });
    expect(listener.onFailure).toHaveBeenCalledWith({
      reason: "tap-failure",
      message: PERFORM_TAP_FAILURE_MESSAGE,
      durableFrames: 0,
      droppedFrames: 73,
    });
  });

  test("implements only the sink surface and never owns a worklet port", () => {
    const queue = new MasterTapBatchQueue({
      queueBatchLimit: 32,
      appendChannels: vi.fn(),
      seal: vi.fn(),
    } as never, {onFailure: vi.fn(), requestCaptureStop: vi.fn()});
    expect(typeof queue.onBatch).toBe("function");
    expect(typeof queue.onStopped).toBe("function");
    expect(typeof queue.onFailure).toBe("function");
    expect("connect" in queue).toBe(false);
    expect("port" in queue).toBe(false);
    expect("stop" in queue).toBe(false);
  });
});
