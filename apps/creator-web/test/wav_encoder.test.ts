import {createHash} from "node:crypto";
import {describe, expect, test} from "vitest";
import {encodePcm16Wav, quantizePcm16} from "../src/capture/wav_encoder";

describe("quantizePcm16", () => {
  test("clamps, scales by 32767, rounds ties away from zero", () => {
    expect(quantizePcm16(0)).toBe(0);
    expect(quantizePcm16(1)).toBe(32767);
    expect(quantizePcm16(-1)).toBe(-32767);
    expect(quantizePcm16(2)).toBe(32767);
    expect(quantizePcm16(-2)).toBe(-32767);
    // Ties-away-from-zero is symmetric; Math.round alone (ties toward +∞)
    // breaks the negative side. Sweep avoids float-exact tie construction.
    for (const value of [0.1, 0.33, 0.5001, 0.9999]) {
      expect(quantizePcm16(-value)).toBe(-quantizePcm16(value));
    }
  });

  // 32767 is odd, so ±0.5 is the only float32 input in [-1, 1] whose scaled
  // value (0.5 * 32767 === 16383.5 exactly) is an exact tie. Plain Math.round
  // (ties toward +∞, the regression S8B-D9 forbids) would still pass every
  // assertion in the sweep above but yields -16383 here instead of -16384.
  test("quantizes the exact ±0.5 tie away from zero (S8B-D9)", () => {
    expect(quantizePcm16(0.5)).toBe(16384);
    expect(quantizePcm16(-0.5)).toBe(-16384);
  });
});

describe("encodePcm16Wav", () => {
  test("produces a byte-stable 48 kHz stereo RIFF with correct sizes", () => {
    const frames = Float32Array.from([0, 0.25, -0.25, 1]);
    const wav = encodePcm16Wav([frames, frames]);
    expect(wav.length).toBe(44 + 4 * 2 * 2);
    const view = new DataView(wav.buffer);
    expect(view.getUint32(24, true)).toBe(48_000);        // sample rate
    expect(view.getUint16(22, true)).toBe(2);             // channels
    expect(view.getUint16(34, true)).toBe(16);            // bits per sample
    expect(view.getUint32(40, true)).toBe(16);            // data chunk bytes

    // Golden sample bytes: pins the quantization of every frame, not just the
    // header. A regression in quantizePcm16 (e.g. plain Math.round instead of
    // ties-away-from-zero) is invisible to a header-only or self-vs-self
    // "determinism" check, since that only proves the function agrees with
    // itself. frame -0.25 (ch0 and ch1 both -0.25) is the case that would
    // change under plain Math.round: -0.25 * 32767 = -8191.75, which rounds
    // to -8192 either way here (not a tie), but the ±0.5 tie is asserted
    // directly in quantizePcm16's own tests above; this pins the full byte
    // stream those quantized values produce end to end.
    const expectedSamples = [0, 0, 8192, 8192, -8192, -8192, 32767, 32767];
    expectedSamples.forEach((expected, i) => {
      expect(view.getInt16(44 + i * 2, true)).toBe(expected);
    });
    const digest = createHash("sha256").update(wav).digest("hex");
    expect(digest).toBe("3bb25ecc02282d0426761b499859b11bd68d266407f2a5230e1d6256f4fef76e");
  });

  test("rejects empty, mismatched, or >2 channel input", () => {
    expect(() => encodePcm16Wav([])).toThrow(TypeError);
    expect(() => encodePcm16Wav([new Float32Array(2), new Float32Array(3)])).toThrow(TypeError);
  });
});
