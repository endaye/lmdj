import { mkdirSync, existsSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export const CAPTURE_FIXTURE_SAMPLE_RATE = 48_000;
export const CAPTURE_FIXTURE_SECONDS = 2;
export const CAPTURE_FIXTURE_HZ = 440;

// Same rule as apps/creator-web/src/capture/wav_encoder.ts: clamp, scale by
// 32767, round ties away from zero, no dither. Chromium replays this file
// through --use-file-for-fake-audio-capture, so keeping the two quantizations
// identical means the fixture is byte-reproducible and the committed Sample is
// a known signal rather than whatever the host machine's microphone heard.
function quantizePcm16(value) {
  const clamped = Math.min(1, Math.max(-1, value));
  const scaled = clamped * 32767;
  return Math.sign(scaled) * Math.round(Math.abs(scaled));
}

function encodeMonoPcm16Wav(samples, sampleRate) {
  const dataBytes = samples.length * 2;
  const bytes = new Uint8Array(44 + dataBytes);
  const view = new DataView(bytes.buffer);
  const ascii = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) bytes[offset + i] = text.charCodeAt(i);
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < samples.length; i += 1) {
    view.setInt16(44 + i * 2, quantizePcm16(samples[i]), true);
  }
  return bytes;
}

/**
 * Write the deterministic capture fixture to `path` if it is absent and return
 * `path`. Called at Playwright config load time so the file exists before the
 * browser launches with --use-file-for-fake-audio-capture.
 */
export function ensureCaptureFixture(path) {
  if (existsSync(path)) return path;
  const frames = CAPTURE_FIXTURE_SAMPLE_RATE * CAPTURE_FIXTURE_SECONDS;
  const samples = new Float32Array(frames);
  for (let i = 0; i < frames; i += 1) {
    // 0.5 amplitude keeps the level meter clearly non-zero without clipping,
    // so a stuck-at-silence capture is visibly distinguishable from success.
    samples[i] = 0.5 * Math.sin(
      (2 * Math.PI * CAPTURE_FIXTURE_HZ * i) / CAPTURE_FIXTURE_SAMPLE_RATE,
    );
  }
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, encodeMonoPcm16Wav(samples, CAPTURE_FIXTURE_SAMPLE_RATE));
  return path;
}
