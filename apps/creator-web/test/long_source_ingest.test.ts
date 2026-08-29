import {describe, expect, test, vi} from "vitest";

import {
  LongSourceIngestError,
  openLongSource,
  type AudioBufferView,
  type LongSourceLimits,
} from "../src/ingest/long_source_ingest";

const LIMITS: LongSourceLimits = Object.freeze({
  sourceBytes: 104_857_600,
  decodedFrames: 43_200_000,
  channels: 2,
  artifactBytes: 68_157_440,
});

function fakeFile(bytes: Uint8Array, size = bytes.byteLength) {
  return {
    name: "source.bin",
    size,
    arrayBuffer: vi.fn(async () => new Uint8Array(bytes).buffer),
  };
}

function ascii(bytes: Uint8Array, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    bytes[offset + index] = value.charCodeAt(index);
  }
}

function flacStreamInfo(totalSamples: number, channels = 2, sampleRate = 48_000) {
  const bytes = new Uint8Array(42);
  ascii(bytes, 0, "fLaC");
  bytes[4] = 0x80;
  bytes[7] = 34;
  const packed = (BigInt(sampleRate) << 44n) |
    (BigInt(channels - 1) << 41n) |
    (15n << 36n) |
    BigInt(totalSamples);
  const view = new DataView(bytes.buffer);
  view.setBigUint64(18, packed, false);
  return bytes;
}

function mp4Aac(channelCount: number, duration = 48_000, timescale = 48_000) {
  const bytes = new Uint8Array(84);
  const view = new DataView(bytes.buffer);
  view.setUint32(0, 24, false); ascii(bytes, 4, "ftyp"); ascii(bytes, 8, "M4A ");
  view.setUint32(24, 32, false); ascii(bytes, 28, "mdhd");
  bytes[32] = 0;
  view.setUint32(44, timescale, false);
  view.setUint32(48, duration, false);
  view.setUint32(56, 28, false); ascii(bytes, 60, "mp4a");
  view.setUint16(80, channelCount, false);
  return bytes;
}

function decodedBuffer(length: number, channels = 2, sampleRate = 48_000): AudioBufferView {
  const data = Array.from({length: channels}, (_, channel) => {
    // Dimension-boundary tests intentionally do not allocate hundreds of MiB;
    // native AudioBuffer guarantees channel-data length matches `length`.
    const samples = new Float32Array(Math.min(length, 16));
    if (samples.length > 0) {
      samples[Math.min(channel, samples.length - 1)] = channel === 0 ? 0.5 : -0.75;
    }
    return samples;
  });
  return {
    length,
    numberOfChannels: channels,
    sampleRate,
    getChannelData: (channel) => data[channel]!,
  };
}

describe("openLongSource", () => {
  test("publishes the exact A9 physical-fixture inventory and sha256 identities", () => {
    const manifest = JSON.parse(readFileSync(
      "../../tests/fixtures/long-material/hashes.json",
      "utf8",
    )) as {fixtures: Array<Record<string, unknown>>; lifecycle_sequences: string[]};
    expect(manifest.fixtures.map((fixture) => fixture.name)).toEqual([
      "LM-OK-BOUNDARY-INGEST",
      "LM-OK-COMMIT-BOUNDARY",
      "LM-OK-SONG",
      "LM-REJ-CH",
      "LM-REJ-COMMIT-PLUS-4B",
      "LM-REJ-FRAMES",
      "LM-REJ-SOURCE",
    ]);
    expect(manifest.fixtures.every((fixture) =>
      typeof fixture.sha256 === "string" && /^[0-9a-f]{64}$/.test(fixture.sha256)
    )).toBe(true);
    expect(manifest.lifecycle_sequences).toEqual([
      "cancel", "replace", "re-import", "background-recovery",
    ]);
  });

  test("rejects source_bytes + 1 before reading or decoding", async () => {
    const file = fakeFile(new Uint8Array(), LIMITS.sourceBytes + 1);
    const decode = vi.fn();

    await expect(openLongSource(file, LIMITS, {decode})).rejects.toMatchObject({
      code: "WEB_RUNTIME_RESOURCE_LIMIT",
      details: {resource: "ingest_source_bytes", observed: 104_857_601, limit: 104_857_600},
    });
    expect(file.arrayBuffer).not.toHaveBeenCalled();
    expect(decode).not.toHaveBeenCalled();
  });

  test("sniffs content and fails closed before decode", async () => {
    const file = fakeFile(new TextEncoder().encode("OggSunsupported"));
    const decode = vi.fn();

    await expect(openLongSource(file, LIMITS, {decode})).rejects.toBeInstanceOf(
      LongSourceIngestError,
    );
    expect(decode).not.toHaveBeenCalled();
  });

  test("rejects exact FLAC metadata at decoded_frames + 1 before decode", async () => {
    const file = fakeFile(flacStreamInfo(LIMITS.decodedFrames + 1));
    const decode = vi.fn();

    await expect(openLongSource(file, LIMITS, {decode})).rejects.toMatchObject({
      code: "WEB_RUNTIME_RESOURCE_LIMIT",
      details: {
        resource: "ingest_decoded_frames",
        observed: 43_200_001,
        limit: 43_200_000,
      },
    });
    expect(decode).not.toHaveBeenCalled();
  });

  test("rejects six-channel MP4 AAC metadata before decode", async () => {
    const file = fakeFile(mp4Aac(6));
    const decode = vi.fn();

    await expect(openLongSource(file, LIMITS, {decode})).rejects.toMatchObject({
      code: "WEB_RUNTIME_RESOURCE_LIMIT",
      details: {resource: "ingest_channels", observed: 6, limit: 2},
    });
    expect(decode).not.toHaveBeenCalled();
  });

  test("accepts the exact ingest boundary", async () => {
    const audio = decodedBuffer(LIMITS.decodedFrames);
    const decode = vi.fn(async () => audio);
    const source = await openLongSource(
      fakeFile(flacStreamInfo(LIMITS.decodedFrames)),
      LIMITS,
      {decode},
    );

    expect(source).toMatchObject({
      container: "flac",
      frameCount: LIMITS.decodedFrames,
      channelCount: 2,
      released: false,
    });
    source.release();
    expect(source.released).toBe(true);
    expect(() => source.envelope(1, 0, 1)).toThrow("released");
  });

  test("derives a bounded waveform from the owned decoded copy", async () => {
    const source = await openLongSource(
      fakeFile(flacStreamInfo(4)),
      {...LIMITS, decodedFrames: 4},
      {decode: async () => decodedBuffer(4)},
    );
    expect(source.envelope(2, 0, 4)).toEqual(new Float32Array([0.75, 0]));
  });

  test.each([
    ["frames", decodedBuffer(LIMITS.decodedFrames + 1), "ingest_decoded_frames"],
    ["channels", decodedBuffer(48_000, 3), "ingest_channels"],
    ["sample rate", decodedBuffer(48_000, 2, 44_100), "ingest_sample_rate"],
  ] as const)("releases a post-decode %s rejection", async (_name, audio, resource) => {
    const source = openLongSource(fakeFile(flacStreamInfo(48_000)), LIMITS, {
      decode: async () => audio,
    });
    await expect(source).rejects.toMatchObject({
      code: "WEB_RUNTIME_RESOURCE_LIMIT",
      details: {resource},
    });
  });

  test("encodes an exact quota-bound selection and keeps the source after refusal", async () => {
    const source = await openLongSource(
      fakeFile(flacStreamInfo(4)),
      {...LIMITS, decodedFrames: 4},
      {decode: async () => decodedBuffer(4)},
    );

    const file = source.encodeSelection({startFrame: 1, frameCount: 3}, 3);
    expect(file.name).toBe("source-selection.wav");
    expect(file.size).toBe(44 + 3 * 2 * 2);
    expect(source.released).toBe(false);
    expect(() => source.encodeSelection({startFrame: 0, frameCount: 4}, 3))
      .toThrow("quota");
    expect(source.released).toBe(false);
  });
});
import {readFileSync} from "node:fs";
