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

  // Finding 4: envelope() is called ~10x/sec from the panel on an unchanged
  // buffer between batches; memoizing on (frameCount, bins) must make a
  // repeated call with no intervening append return the identical cached
  // array instead of re-walking every sample.
  test("memoizes the envelope for an unchanged frame count and bin count", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from({length: 8}, (_, i) => (i + 1) / 8)]);
    const first = buffer.envelope(2);
    const second = buffer.envelope(2);
    expect(second).toBe(first);
    expect(Array.from(second)).toEqual([0.5, 1]);
  });

  test("append invalidates the memoized envelope", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([Float32Array.from({length: 8}, (_, i) => (i + 1) / 8)]);
    const before = buffer.envelope(2);
    buffer.append([Float32Array.from({length: 8}, () => 1)]);
    const after = buffer.envelope(2);
    expect(after).not.toBe(before);
    expect(Array.from(after)).toEqual([1, 1]);
  });

  // Long-take redraw cost: once a bin spans at least one summary block, the
  // envelope must be served from incrementally maintained per-block peaks
  // (O(blocks) per redraw) instead of re-walking every stored sample
  // (O(total frames)). The block path snaps bin boundaries outward to block
  // edges, so a boundary-straddling block contributes its peak to BOTH
  // neighbouring bins: values may overestimate at bin edges but can never
  // underestimate, and a peak is never dropped.
  test("summary-path bins report block peaks, overestimating only at unaligned edges", () => {
    // 5 blocks (1280 frames), 2 bins => perBin = 640 = 2.5 blocks. The lone
    // 1.0 peak sits at frame 700 (block 2, truly inside bin 1). Block 2
    // straddles the 640-frame bin boundary, so bin 0 also reports 1.0.
    const frames = 5 * ENVELOPE_BLOCK_FRAMES;
    const data = Float32Array.from({length: frames}, () => 0.125);
    data[700] = 1;
    const buffer = new CaptureBuffer(1);
    buffer.append([data]);
    const envelope = buffer.envelope(2);
    expect(Array.from(envelope)).toEqual([1, 1]);
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
    expect(Array.from(buffer.envelope(2))).toEqual([0.5, 0.75]);
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
    expect(Array.from(pieces.envelope(3))).toEqual(Array.from(whole.envelope(3)));
  });

  test("summary-path envelope is memoized like the exact path", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([new Float32Array(4 * ENVELOPE_BLOCK_FRAMES)]);
    expect(buffer.envelope(2)).toBe(buffer.envelope(2));
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
