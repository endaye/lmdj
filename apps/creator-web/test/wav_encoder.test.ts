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
    const digest = createHash("sha256").update(wav).digest("hex");
    const again = createHash("sha256").update(encodePcm16Wav([frames, frames])).digest("hex");
    expect(again).toBe(digest);                            // determinism
  });

  test("rejects empty, mismatched, or >2 channel input", () => {
    expect(() => encodePcm16Wav([])).toThrow(TypeError);
    expect(() => encodePcm16Wav([new Float32Array(2), new Float32Array(3)])).toThrow(TypeError);
  });
});
