import {CAPTURE_SAMPLE_RATE} from "./capture_buffer";

export const PCM16_WAV_HEADER_BYTES = 44;

export function quantizePcm16(value: number): number {
  const clamped = Math.min(1, Math.max(-1, value));
  const scaled = clamped * 32767;
  // Deterministic ties-away-from-zero (JS Math.round alone is ties-toward-+∞).
  return Math.sign(scaled) * Math.round(Math.abs(scaled));
}

export function encodePcm16WavHeader(
  frames: number,
  channelCount: 1 | 2,
  sampleRate: number = CAPTURE_SAMPLE_RATE,
): Uint8Array<ArrayBuffer> {
  const dataBytes = frames * channelCount * 2;
  if (!Number.isSafeInteger(frames) || frames < 0 ||
      !Number.isSafeInteger(sampleRate) || sampleRate <= 0 ||
      dataBytes > 0xffff_ffff - 36) {
    throw new TypeError("WAV header input is invalid");
  }
  const bytes = new Uint8Array(PCM16_WAV_HEADER_BYTES);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      bytes[offset + index] = text.charCodeAt(index);
    }
  };
  ascii(0, "RIFF"); view.setUint32(4, 36 + dataBytes, true); ascii(8, "WAVE");
  ascii(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channelCount * 2, true);
  view.setUint16(32, channelCount * 2, true); view.setUint16(34, 16, true);
  ascii(36, "data"); view.setUint32(40, dataBytes, true);
  return bytes;
}

export function encodePcm16Frames(
  channels: readonly Float32Array[],
): Uint8Array<ArrayBuffer> {
  const first = channels[0];
  if (channels.length < 1 || channels.length > 2 || first === undefined ||
      channels.some((channel) =>
        !(channel instanceof Float32Array) || channel.length !== first.length)) {
    throw new TypeError("PCM16 encode input is invalid");
  }
  const bytes = new Uint8Array(first.length * channels.length * 2);
  const view = new DataView(bytes.buffer);
  let offset = 0;
  for (let frame = 0; frame < first.length; frame += 1) {
    for (const channel of channels) {
      const sample = channel[frame];
      if (sample === undefined) throw new TypeError("PCM16 encode input is invalid");
      view.setInt16(offset, quantizePcm16(sample), true);
      offset += 2;
    }
  }
  return bytes;
}

// The returned view is always backed by a fresh ArrayBuffer (never a
// SharedArrayBuffer), which the type states so callers can hand the bytes
// straight to a Blob or File without copying or casting.
export function encodePcm16Wav(
  channels: readonly Float32Array[],
  sampleRate: number = CAPTURE_SAMPLE_RATE,
): Uint8Array<ArrayBuffer> {
  const first = channels[0];
  if (channels.length < 1 || channels.length > 2 || first === undefined ||
      channels.some((c) => !(c instanceof Float32Array) || c.length !== first.length) ||
      first.length === 0) {
    throw new TypeError("WAV encode input is invalid");
  }
  const channelCount = channels.length;
  const frames = first.length;
  const header = encodePcm16WavHeader(frames, channelCount as 1 | 2, sampleRate);
  const pcm = encodePcm16Frames(channels);
  const bytes = new Uint8Array(header.length + pcm.length);
  bytes.set(header);
  bytes.set(pcm, header.length);
  return bytes;
}
