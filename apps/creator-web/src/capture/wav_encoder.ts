import {CAPTURE_SAMPLE_RATE} from "./capture_buffer";

export function quantizePcm16(value: number): number {
  const clamped = Math.min(1, Math.max(-1, value));
  const scaled = clamped * 32767;
  // Deterministic ties-away-from-zero (JS Math.round alone is ties-toward-+∞).
  return Math.sign(scaled) * Math.round(Math.abs(scaled));
}

export function encodePcm16Wav(
  channels: readonly Float32Array[],
  sampleRate: number = CAPTURE_SAMPLE_RATE,
): Uint8Array {
  const first = channels[0];
  if (channels.length < 1 || channels.length > 2 || first === undefined ||
      channels.some((c) => !(c instanceof Float32Array) || c.length !== first.length) ||
      first.length === 0) {
    throw new TypeError("WAV encode input is invalid");
  }
  const channelCount = channels.length;
  const frames = first.length;
  const dataBytes = frames * channelCount * 2;
  const bytes = new Uint8Array(44 + dataBytes);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) { bytes[offset + i] = text.charCodeAt(i); }
  };
  ascii(0, "RIFF"); view.setUint32(4, 36 + dataBytes, true); ascii(8, "WAVE");
  ascii(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channelCount * 2, true);
  view.setUint16(32, channelCount * 2, true); view.setUint16(34, 16, true);
  ascii(36, "data"); view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (let frame = 0; frame < frames; frame += 1) {
    for (const c of channels) {
      const sample = c[frame];
      if (sample === undefined) {
        // Invariant: every channel's length equals `frames` (validated above), so
        // indexing any channel with a frame index in [0, frames) always succeeds.
        throw new TypeError("WAV encode input is invalid");
      }
      view.setInt16(offset, quantizePcm16(sample), true);
      offset += 2;
    }
  }
  return bytes;
}
