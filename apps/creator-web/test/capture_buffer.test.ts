import {describe, expect, test} from "vitest";
import {CAPTURE_MAX_FRAMES, CaptureBuffer} from "../src/capture/capture_buffer";

describe("CaptureBuffer", () => {
  test("appends batches and reports frame count", () => {
    const buffer = new CaptureBuffer(2);
    const accepted = buffer.append([new Float32Array(4800), new Float32Array(4800)]);
    expect(accepted).toBe(4800);
    expect(buffer.frameCount).toBe(4800);
    expect(buffer.atCapacity).toBe(false);
  });

  test("truncates the batch that crosses 60 s and reports capacity", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([new Float32Array(CAPTURE_MAX_FRAMES - 100)]);
    const accepted = buffer.append([new Float32Array(4800)]);
    expect(accepted).toBe(100);
    expect(buffer.frameCount).toBe(CAPTURE_MAX_FRAMES);
    expect(buffer.atCapacity).toBe(true);
  });

  test("rejects mismatched channel counts and invalid slices", () => {
    const buffer = new CaptureBuffer(2);
    expect(() => buffer.append([new Float32Array(8)])).toThrow(TypeError);
    buffer.append([new Float32Array(8), new Float32Array(8)]);
    expect(() => buffer.slice(4, 8)).toThrow(RangeError);
  });

  test("slices exact frames per channel and bins a max-abs envelope", () => {
    // Values k/8 are exact in float32, so equality assertions are stable.
    const left = Float32Array.from({length: 8}, (_, i) => (i + 1) / 8);
    const buffer = new CaptureBuffer(1);
    buffer.append([left]);
    const [mono] = buffer.slice(2, 3);
    if (mono === undefined) {
      throw new Error("expected slice to return one channel");
    }
    expect(Array.from(mono)).toEqual([0.375, 0.5, 0.625]);
    const envelope = buffer.envelope(2);
    expect(Array.from(envelope)).toEqual([0.5, 1]);
  });
});
