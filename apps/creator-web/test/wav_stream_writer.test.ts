import {describe, expect, test} from "vitest";

import {
  openWavStreamWriter,
  type PerformanceRecordingLimits,
} from "../src/record/wav_stream_writer";

const LOCKED_LIMITS: PerformanceRecordingLimits = {
  perform_recording_frames: 86_400_000,
  perform_recording_queue_batches: 32,
};
const STEREO_FRAME_BYTES = 4;
const WAV_HEADER_BYTES = 44;

interface WritableTransaction {
  seek(position: number): Promise<void>;
  write(data: Uint8Array): Promise<void>;
  truncate(size: number): Promise<void>;
  close(): Promise<void>;
  abort(): Promise<void>;
}

class CountingOpfsFile {
  size = 0;
  header = new Uint8Array(WAV_HEADER_BYTES);
  opens = 0;
  writes = 0;
  commits: number[] = [];
  failOpenAt: number | null = null;
  failWriteNumber: number | null = null;
  failCloseAt: number | null = null;

  async createWritable(): Promise<WritableTransaction> {
    this.opens += 1;
    if (this.opens === this.failOpenAt) throw new Error("OPFS unavailable");
    const transaction = this.opens;
    let position = 0;
    let nextSize = this.size;
    let nextHeader = this.header.slice();
    let aborted = false;
    return {
      seek: async (next) => { position = next; },
      write: async (data) => {
        this.writes += 1;
        if (this.writes === this.failWriteNumber) throw new Error("write failed");
        if (position === 0 && data.length === WAV_HEADER_BYTES) {
          nextHeader = data.slice();
        }
        nextSize = Math.max(nextSize, position + data.length);
        position += data.length;
      },
      truncate: async (size) => { nextSize = size; },
      close: async () => {
        if (transaction === this.failCloseAt) throw new Error("close failed");
        if (!aborted) {
          this.size = nextSize;
          this.header = nextHeader;
          this.commits.push(nextSize);
        }
      },
      abort: async () => { aborted = true; },
    };
  }
}

function expectCanonicalStereoWav(
  file: CountingOpfsFile,
  frames: number,
): void {
  const view = new DataView(file.header.buffer);
  expect(new TextDecoder().decode(file.header.subarray(0, 4))).toBe("RIFF");
  expect(view.getUint32(4, true)).toBe(36 + frames * STEREO_FRAME_BYTES);
  expect(new TextDecoder().decode(file.header.subarray(8, 12))).toBe("WAVE");
  expect(view.getUint16(20, true)).toBe(1);
  expect(view.getUint16(22, true)).toBe(2);
  expect(view.getUint32(24, true)).toBe(48_000);
  expect(view.getUint16(34, true)).toBe(16);
  expect(view.getUint32(40, true)).toBe(frames * STEREO_FRAME_BYTES);
  expect(file.size).toBe(WAV_HEADER_BYTES + frames * STEREO_FRAME_BYTES);
}

describe("WavStreamWriter", () => {
  test("requires both named Host limits and publishes a valid zero-frame WAV", async () => {
    await expect(openWavStreamWriter(new CountingOpfsFile() as never, {
      perform_recording_frames: 86_400_000,
    } as never)).rejects.toThrow("perform_recording_queue_batches");

    const file = new CountingOpfsFile();
    const writer = await openWavStreamWriter(file as never, LOCKED_LIMITS);
    expect(writer.snapshot).toEqual({
      state: "active",
      durableFrames: 0,
      byteLength: WAV_HEADER_BYTES,
      reason: null,
      droppedFrames: 0,
    });
    expectCanonicalStereoWav(file, 0);
  });

  test("keeps one transaction across 32 batches and publishes valid WAV checkpoints", async () => {
    const file = new CountingOpfsFile();
    const writer = await openWavStreamWriter(file as never, LOCKED_LIMITS);
    const pcm = new Uint8Array(4_800 * STEREO_FRAME_BYTES);

    for (let batch = 0; batch < 31; batch += 1) await writer.appendPcm16(pcm);
    expect(file.opens).toBe(2); // initial header + one still-open stream transaction
    expect(file.commits).toHaveLength(1);
    expectCanonicalStereoWav(file, 0);

    await writer.appendPcm16(pcm);
    expect(file.opens).toBe(2);
    expect(file.commits).toHaveLength(2);
    expectCanonicalStereoWav(file, 32 * 4_800);

    await writer.appendPcm16(pcm);
    expect(file.opens).toBe(3);
    expectCanonicalStereoWav(file, 32 * 4_800);
    await writer.seal("stopped");
    expect(file.commits).toHaveLength(3);
    expectCanonicalStereoWav(file, 33 * 4_800);
  });

  test("accepts exactly 86400000 frames and seals the canonical 345600044-byte WAV", async () => {
    const file = new CountingOpfsFile();
    const writer = await openWavStreamWriter(file as never, LOCKED_LIMITS);
    const pcm = new Uint8Array(4_800 * STEREO_FRAME_BYTES);
    for (let batch = 0; batch < 18_000; batch += 1) {
      await writer.appendPcm16(pcm);
    }
    expect(writer.snapshot).toEqual({
      state: "sealed",
      durableFrames: 86_400_000,
      byteLength: 345_600_044,
      reason: "frame-limit",
      droppedFrames: 0,
    });
    expect(file.opens).toBe(564); // initial header + ceil(18000 / 32) checkpoints
    expectCanonicalStereoWav(file, 86_400_000);

    await writer.appendPcm16(new Uint8Array(STEREO_FRAME_BYTES));
    expect(writer.attemptedFrames).toBe(86_400_001);
    expect(writer.snapshot.byteLength).toBe(345_600_044);
    expectCanonicalStereoWav(file, 86_400_000);
  }, 20_000);

  test("a write error after pending batches aborts their transaction and preserves the checkpoint", async () => {
    const file = new CountingOpfsFile();
    const writer = await openWavStreamWriter(file as never, LOCKED_LIMITS);
    const pcm = new Uint8Array(4_800 * STEREO_FRAME_BYTES);
    for (let batch = 0; batch < 32; batch += 1) await writer.appendPcm16(pcm);
    expectCanonicalStereoWav(file, 153_600);

    await writer.appendPcm16(pcm); // pending in the next open transaction
    file.failWriteNumber = file.writes + 1;
    await writer.appendPcm16(pcm);
    expect(writer.snapshot).toEqual({
      state: "sealed",
      durableFrames: 153_600,
      byteLength: 614_444,
      reason: "writer-error",
      droppedFrames: 9_600,
    });
    expectCanonicalStereoWav(file, 153_600);
  });

  test.each(["backpressure", "tap-failure"] as const)(
    "%s aborts the non-durable checkpoint window and reports every dropped frame",
    async (reason) => {
      const file = new CountingOpfsFile();
      const writer = await openWavStreamWriter(file as never, LOCKED_LIMITS);
      const pcm = new Uint8Array(4_800 * STEREO_FRAME_BYTES);
      for (let batch = 0; batch < 32; batch += 1) await writer.appendPcm16(pcm);
      await writer.appendPcm16(pcm);
      await writer.appendPcm16(pcm);

      const snapshot = await writer.seal(reason);

      expect(snapshot).toMatchObject({
        state: "sealed",
        durableFrames: 153_600,
        byteLength: 614_444,
        reason,
        droppedFrames: 9_600,
      });
      expectCanonicalStereoWav(file, 153_600);
    },
  );

  test("frame limit commits through the exact limit and reports only overflow", async () => {
    const file = new CountingOpfsFile();
    const writer = await openWavStreamWriter(file as never, LOCKED_LIMITS);
    const pcm = new Uint8Array(4_800 * STEREO_FRAME_BYTES);
    for (let batch = 0; batch < 17_999; batch += 1) {
      await writer.appendPcm16(pcm);
    }

    const snapshot = await writer.appendPcm16(
      new Uint8Array(4_801 * STEREO_FRAME_BYTES),
    );

    expect(snapshot).toMatchObject({
      state: "sealed",
      durableFrames: 86_400_000,
      byteLength: 345_600_044,
      reason: "frame-limit",
      droppedFrames: 1,
    });
    expectCanonicalStereoWav(file, 86_400_000);
  }, 20_000);

  test.each([
    ["opfs-failure", "open"],
    ["writer-error", "close"],
  ] as const)("%s while checkpointing retains the prior durable WAV", async (
    reason,
    failure,
  ) => {
    const file = new CountingOpfsFile();
    const writer = await openWavStreamWriter(file as never, LOCKED_LIMITS);
    const pcm = new Uint8Array(4_800 * STEREO_FRAME_BYTES);
    for (let batch = 0; batch < 32; batch += 1) await writer.appendPcm16(pcm);
    expectCanonicalStereoWav(file, 153_600);

    if (failure === "open") file.failOpenAt = file.opens + 1;
    else file.failCloseAt = file.opens + 1;
    await writer.appendPcm16(pcm);
    await writer.seal("stopped");
    expect(writer.snapshot).toEqual({
      state: "sealed",
      durableFrames: 153_600,
      byteLength: 614_444,
      reason,
      droppedFrames: 4_800,
    });
    expectCanonicalStereoWav(file, 153_600);
  });
});
