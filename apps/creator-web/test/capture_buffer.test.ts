import {describe, expect, test} from "vitest";
import {
  CAPTURE_MAX_FRAMES,
  COMMIT_MAX_FRAMES,
  CaptureBuffer,
  ENVELOPE_BLOCK_FRAMES,
} from "../src/capture/capture_buffer";
import {WEB_RUNTIME_IDENTITY} from
  "../../../products/lmdj/generated/web-runtime-identity.mjs";

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

  test("crops exact stereo frames across append chunks and rebases to zero", () => {
    const buffer = new CaptureBuffer(2);
    buffer.append([
      Float32Array.from([0, 1, 2]),
      Float32Array.from([10, 11, 12]),
    ]);
    buffer.append([
      Float32Array.from([3, 4, 5]),
      Float32Array.from([13, 14, 15]),
    ]);

    buffer.crop(2, 3);

    expect(buffer.frameCount).toBe(3);
    expect(buffer.slice(0, 3).map((channel) => Array.from(channel)))
      .toEqual([[2, 3, 4], [12, 13, 14]]);
  });

  test("rejects invalid crops atomically without invalidating the envelope cache", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from([0, 0.125, 0.25, 0.5])]);
    const beforeFrames = buffer.frameCount;
    const beforePcm = Array.from(buffer.slice(0, beforeFrames)[0] ?? []);
    const beforeEnvelope = buffer.envelope(2, 0, beforeFrames);

    for (const [startFrame, frameCount] of [
      [-1, 2],
      [0.5, 2],
      [0, 0],
      [3, 2],
    ]) {
      expect(() => buffer.crop(startFrame, frameCount)).toThrow(RangeError);
      expect(buffer.frameCount).toBe(beforeFrames);
      expect(Array.from(buffer.slice(0, beforeFrames)[0] ?? [])).toEqual(beforePcm);
      expect(buffer.envelope(2, 0, beforeFrames)).toBe(beforeEnvelope);
    }
  });

  test("rebuilds block peaks without retaining an excluded peak from the old block", () => {
    const cropStart = 10;
    const cropFrames = 4 * ENVELOPE_BLOCK_FRAMES;
    const data = new Float32Array(cropStart + cropFrames).fill(0.25);
    data[5] = 1;
    const buffer = new CaptureBuffer(1);
    buffer.append([data]);

    buffer.crop(cropStart, cropFrames);

    expect(Array.from(buffer.envelope(2, 0, cropFrames))).toEqual([0.25, 0.25]);
  });

  test("supports repeated crops and append after crop", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from([0, 0.125, 0.25, 0.375, 0.5, 0.625])]);

    buffer.crop(1, 5);
    buffer.crop(1, 3);
    expect(Array.from(buffer.slice(0, 3)[0] ?? [])).toEqual([0.25, 0.375, 0.5]);

    buffer.append([Float32Array.from([0.75, 1])]);
    expect(Array.from(buffer.slice(0, buffer.frameCount)[0] ?? []))
      .toEqual([0.25, 0.375, 0.5, 0.75, 1]);
    expect(Array.from(buffer.envelope(2, 0, buffer.frameCount))).toEqual([0.5, 1]);
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
    const envelope = buffer.envelope(2, 0, buffer.frameCount);
    expect(Array.from(envelope)).toEqual([0.5, 1]);
  });

  test("bins only the requested range across chunks and stereo channels", () => {
    const buffer = new CaptureBuffer(2);
    buffer.append([
      Float32Array.from([0, 0.125, 0.25]),
      Float32Array.from([0, -0.75, -0.875]),
    ]);
    buffer.append([
      Float32Array.from([0.375, 0.5, 0.625]),
      Float32Array.from([-0.125, -1, -0.25]),
    ]);

    expect(Array.from(buffer.envelope(3, 2, 3))).toEqual([0.875, 0.375, 1]);
  });

  test("uses exact integer bin boundaries for a 14-frame 400-bin window", () => {
    const data = new Float32Array(14);
    data[7] = 1;
    const buffer = new CaptureBuffer(1);
    buffer.append([data]);

    const envelope = buffer.envelope(400, 0, 14);
    expect(envelope[199]).toBe(0);
    expect(envelope[200]).toBe(1);
  });

  test("rejects malformed or out-of-buffer envelope ranges", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([new Float32Array(8)]);

    expect(() => buffer.envelope(0, 0, 8)).toThrow(TypeError);
    expect(() => buffer.envelope(2, -1, 2)).toThrow(RangeError);
    expect(() => buffer.envelope(2, 0.5, 2)).toThrow(RangeError);
    expect(() => buffer.envelope(2, 0, 0)).toThrow(RangeError);
    expect(() => buffer.envelope(2, 7, 2)).toThrow(RangeError);
  });

  // Finding 4: envelope() is called ~10x/sec from the panel on an unchanged
  // buffer between batches; memoizing on (frameCount, bins, start, count) must make a
  // repeated call with no intervening append return the identical cached
  // array instead of re-walking every sample.
  test("memoizes the envelope for an unchanged frame count and bin count", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from({length: 8}, (_, i) => (i + 1) / 8)]);
    const first = buffer.envelope(2, 0, 8);
    const second = buffer.envelope(2, 0, 8);
    expect(second).toBe(first);
    expect(Array.from(second)).toEqual([0.5, 1]);
  });

  test("does not reuse an envelope cached for another range", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from({length: 12}, (_, i) => (i + 1) / 16)]);

    const first = buffer.envelope(2, 0, 8);
    expect(buffer.envelope(2, 0, 8)).toBe(first);
    expect(buffer.envelope(2, 1, 8)).not.toBe(first);
    expect(buffer.envelope(2, 0, 7)).not.toBe(first);
  });

  test("append invalidates the memoized envelope", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from({length: 8}, (_, i) => (i + 1) / 8)]);
    const before = buffer.envelope(2, 0, 8);
    buffer.append([Float32Array.from({length: 8}, () => 1)]);
    const after = buffer.envelope(2, 0, 16);
    expect(after).not.toBe(before);
    expect(Array.from(after)).toEqual([1, 1]);
  });

  // Long-take redraw cost: once a bin spans at least one summary block, the
  // envelope must be served from incrementally maintained per-block peaks
  // (O(blocks) per redraw) instead of re-walking every stored sample
  // (O(total frames)). A boundary-straddling block must be scanned exactly at
  // each bin edge so its peak contributes only to the bin that contains it.
  test("summary-path bins scan unaligned edges exactly", () => {
    // 5 blocks (1280 frames), 2 bins => perBin = 640 = 2.5 blocks. The lone
    // 1.0 peak sits at frame 700 (block 2, truly inside bin 1). Block 2
    // straddles the 640-frame bin boundary, but frame 700 belongs only to bin 1.
    const frames = 5 * ENVELOPE_BLOCK_FRAMES;
    const data = Float32Array.from({length: frames}, () => 0.125);
    data[700] = 1;
    const buffer = new CaptureBuffer(1);
    buffer.append([data]);
    const envelope = buffer.envelope(2, 0, frames);
    expect(Array.from(envelope)).toEqual([0.125, 1]);
  });

  test("summary path excludes peaks outside a ranged window and partial bin edges", () => {
    const frames = 8 * ENVELOPE_BLOCK_FRAMES;
    const data = new Float32Array(frames);
    const start = ENVELOPE_BLOCK_FRAMES + 10;
    const count = 4 * ENVELOPE_BLOCK_FRAMES;

    data[start - 1] = 1;                                  // outside window
    data[start + 34] = 0.5;                               // bin 0, partial block
    data[2 * ENVELOPE_BLOCK_FRAMES + 20] = 0.625;         // bin 0, full block
    data[3 * ENVELOPE_BLOCK_FRAMES + 2] = 0.75;           // bin 0 edge
    data[3 * ENVELOPE_BLOCK_FRAMES + 12] = 0.375;         // bin 1 edge
    data[4 * ENVELOPE_BLOCK_FRAMES + 20] = 0.875;         // bin 1, full block
    data[start + count - 1] = 0.25;                       // bin 1, partial block
    data[start + count] = 0.9375;                         // outside window

    const buffer = new CaptureBuffer(1);
    buffer.append([data]);
    expect(Array.from(buffer.envelope(2, start, count))).toEqual([0.75, 0.875]);
  });

  test("summary path never underestimates and matches exact peaks on aligned bins", () => {
    // 4 blocks, 2 bins => each bin is exactly 2 blocks; no straddling block,
    // so the summary path must equal the exact per-bin maxima.
    const frames = 4 * ENVELOPE_BLOCK_FRAMES;
    const data = Float32Array.from({length: frames}, () => 0.25);
    data[100] = 0.5;                              // bin 0
    data[3 * ENVELOPE_BLOCK_FRAMES + 7] = 0.75;   // bin 1
    const buffer = new CaptureBuffer(1);
    buffer.append([data]);
    expect(Array.from(buffer.envelope(2, 0, frames))).toEqual([0.5, 0.75]);
  });

  test("summary path combines stereo block peaks", () => {
    const frames = 4 * ENVELOPE_BLOCK_FRAMES;
    const left = new Float32Array(frames).fill(0.125);
    const right = new Float32Array(frames).fill(-0.25);
    right[2 * ENVELOPE_BLOCK_FRAMES + 10] = -0.875;
    const buffer = new CaptureBuffer(2);
    buffer.append([left, right]);

    expect(Array.from(buffer.envelope(2, 0, frames))).toEqual([0.25, 0.875]);
  });

  test("reads a late narrow range across many append chunks", () => {
    const buffer = new CaptureBuffer(1);
    for (let frame = 0; frame < 2_000; frame += 1) {
      buffer.append([Float32Array.of(frame === 1_995 ? 0.75 : 0.125)]);
    }

    expect(Array.from(buffer.envelope(5, 1_990, 10)))
      .toEqual([0.125, 0.125, 0.75, 0.125, 0.125]);
  });

  test("block peaks accumulate identically across arbitrary append boundaries", () => {
    // The same samples split into uneven batches (crossing block boundaries
    // mid-batch) must produce the same envelope as one contiguous append.
    const frames = 6 * ENVELOPE_BLOCK_FRAMES;
    const data = Float32Array.from({length: frames}, (_, i) => ((i * 31) % 97) / 97);
    const whole = new CaptureBuffer(1);
    whole.append([data]);
    const pieces = new CaptureBuffer(1);
    for (let at = 0; at < frames;) {
      const take = Math.min(190 + (at % 3), frames - at); // never block-aligned
      pieces.append([data.slice(at, at + take)]);
      at += take;
    }
    expect(Array.from(pieces.envelope(3, 0, frames)))
      .toEqual(Array.from(whole.envelope(3, 0, frames)));
  });

  test("summary-path envelope is memoized like the exact path", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([new Float32Array(4 * ENVELOPE_BLOCK_FRAMES)]);
    expect(buffer.envelope(2, 0, buffer.frameCount))
      .toBe(buffer.envelope(2, 0, buffer.frameCount));
  });

  // Finding 3: COMMIT_MAX_FRAMES must never hand-enter a value that can drift
  // from the generated product manifest the Core actually enforces.
  test("COMMIT_MAX_FRAMES matches the generated manifest's decoded_frames_per_pad", () => {
    expect(COMMIT_MAX_FRAMES).toBe(WEB_RUNTIME_IDENTITY.resource_limits.decoded_frames_per_pad);
  });

  test("the worst-case encoded WAV at COMMIT_MAX_FRAMES fits the manifest's imported_wav_bytes", () => {
    const worstCaseBytes = COMMIT_MAX_FRAMES * 2 /* channels */ * 2 /* bytes/sample */ + 44;
    expect(worstCaseBytes).toBeLessThanOrEqual(
      WEB_RUNTIME_IDENTITY.resource_limits.imported_wav_bytes,
    );
  });
});
