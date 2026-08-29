import {encodePcm16Wav} from "../capture/wav_encoder";

export type LongSourceContainer = "wav" | "mp3" | "m4a-aac" | "flac";

export interface LongSourceLimits {
  readonly sourceBytes: number;
  readonly decodedFrames: number;
  readonly channels: number;
  readonly artifactBytes: number;
}

export interface AudioBufferView {
  readonly length: number;
  readonly numberOfChannels: number;
  readonly sampleRate: number;
  getChannelData(channel: number): Float32Array;
}

interface LongSourceFile {
  readonly name: string;
  readonly size: number;
  arrayBuffer(): Promise<ArrayBuffer>;
}

interface LongSourceDependencies {
  decode(bytes: ArrayBuffer): Promise<AudioBufferView>;
}

export interface LongSourceErrorDetails {
  readonly resource: string;
  readonly observed: number | string;
  readonly limit: number | string;
}

export class LongSourceIngestError extends Error {
  readonly code: "UNSUPPORTED_AUDIO" | "WEB_RUNTIME_RESOURCE_LIMIT";
  readonly details: Readonly<LongSourceErrorDetails>;

  constructor(
    code: "UNSUPPORTED_AUDIO" | "WEB_RUNTIME_RESOURCE_LIMIT",
    message: string,
    details: LongSourceErrorDetails,
  ) {
    super(message);
    this.name = "LongSourceIngestError";
    this.code = code;
    this.details = Object.freeze({...details});
  }
}

interface SourceMetadata {
  readonly container: LongSourceContainer;
  readonly channels: number | null;
  readonly normalizedFrames: number | null;
}

function resourceError(
  resource: string,
  observed: number,
  limit: number,
  why: string,
  remedy: string,
): LongSourceIngestError {
  return new LongSourceIngestError(
    "WEB_RUNTIME_RESOURCE_LIMIT",
    `why: ${why}; remedy: ${remedy}`,
    {resource, observed, limit},
  );
}

function unsupported(
  resource: string,
  observed: string,
  limit: string,
  why: string,
  remedy: string,
): LongSourceIngestError {
  return new LongSourceIngestError(
    "UNSUPPORTED_AUDIO",
    `why: ${why}; remedy: ${remedy}`,
    {resource, observed, limit},
  );
}

function validLimit(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0;
}

function validateLimits(limits: LongSourceLimits): void {
  if (limits === null || typeof limits !== "object" ||
      !validLimit(limits.sourceBytes) || !validLimit(limits.decodedFrames) ||
      !validLimit(limits.channels) || !validLimit(limits.artifactBytes)) {
    throw new TypeError("Long-source limits are invalid");
  }
}

function hasAscii(bytes: Uint8Array, offset: number, value: string): boolean {
  if (offset < 0 || offset + value.length > bytes.byteLength) return false;
  for (let index = 0; index < value.length; index += 1) {
    if (bytes[offset + index] !== value.charCodeAt(index)) return false;
  }
  return true;
}

function ascii(bytes: Uint8Array, offset: number, length: number): string {
  return Array.from(bytes.subarray(offset, offset + length), (value) =>
    value >= 32 && value <= 126 ? String.fromCharCode(value) : ".").join("");
}

function normalizedFrames(frames: number, sampleRate: number): number {
  if (!validLimit(frames) || !validLimit(sampleRate)) {
    throw unsupported(
      "ingest_metadata",
      "invalid",
      "positive frame count and sample rate",
      "the source duration metadata is invalid",
      "export the source again with valid audio metadata",
    );
  }
  return Math.ceil(frames * 48_000 / sampleRate);
}

function wavMetadata(bytes: Uint8Array): SourceMetadata {
  if (bytes.byteLength < 12 || !hasAscii(bytes, 0, "RIFF") ||
      !hasAscii(bytes, 8, "WAVE")) {
    throw unsupported(
      "ingest_container", ascii(bytes, 0, 12), "RIFF/WAVE",
      "the source is not a valid WAV container",
      "export PCM16/24/32 or float32 WAV",
    );
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let channels: number | null = null;
  let sampleRate: number | null = null;
  let blockAlign: number | null = null;
  let dataBytes: number | null = null;
  for (let offset = 12; offset + 8 <= bytes.byteLength;) {
    const size = view.getUint32(offset + 4, true);
    const payload = offset + 8;
    if (hasAscii(bytes, offset, "fmt ") && size >= 16 && payload + 16 <= bytes.byteLength) {
      const format = view.getUint16(payload, true);
      channels = view.getUint16(payload + 2, true);
      sampleRate = view.getUint32(payload + 4, true);
      blockAlign = view.getUint16(payload + 12, true);
      const bits = view.getUint16(payload + 14, true);
      let resolvedFormat = format;
      if (format === 0xfffe && size >= 40 && payload + 26 <= bytes.byteLength) {
        resolvedFormat = view.getUint16(payload + 24, true);
      }
      const validPcm = resolvedFormat === 1 && [16, 24, 32].includes(bits);
      const validFloat = resolvedFormat === 3 && bits === 32;
      if (!validPcm && !validFloat) {
        throw unsupported(
          "ingest_codec", `${resolvedFormat}/${bits}`, "PCM16/24/32 or float32",
          "the WAV codec or sample width is unsupported",
          "export PCM16/24/32 or float32 WAV",
        );
      }
    } else if (hasAscii(bytes, offset, "data")) {
      dataBytes = size;
    }
    const next = payload + size + (size & 1);
    if (!Number.isSafeInteger(next) || next <= offset) break;
    offset = next;
  }
  if (channels === null || sampleRate === null || blockAlign === null ||
      dataBytes === null || channels < 1 || blockAlign < 1 || dataBytes < blockAlign) {
    throw unsupported(
      "ingest_metadata", "missing", "WAV fmt and data chunks",
      "required WAV metadata is missing",
      "export the source again as a complete WAV file",
    );
  }
  return Object.freeze({
    container: "wav",
    channels,
    normalizedFrames: normalizedFrames(Math.floor(dataBytes / blockAlign), sampleRate),
  });
}

function flacMetadata(bytes: Uint8Array): SourceMetadata {
  let offset = 4;
  while (offset + 4 <= bytes.byteLength) {
    const header = bytes[offset] ?? 0;
    const type = header & 0x7f;
    const size = ((bytes[offset + 1] ?? 0) << 16) |
      ((bytes[offset + 2] ?? 0) << 8) | (bytes[offset + 3] ?? 0);
    const payload = offset + 4;
    if (type === 0) {
      if (size !== 34 || payload + size > bytes.byteLength) {
        throw unsupported(
          "ingest_metadata", "invalid", "FLAC STREAMINFO",
          "the FLAC STREAMINFO block is invalid",
          "export the source again as a complete FLAC file",
        );
      }
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const packed = view.getBigUint64(payload + 10, false);
      const sampleRate = Number((packed >> 44n) & 0xfffffn);
      const channels = Number((packed >> 41n) & 0x7n) + 1;
      const frames = Number(packed & 0xfffffffffn);
      return Object.freeze({
        container: "flac",
        channels,
        normalizedFrames: normalizedFrames(frames, sampleRate),
      });
    }
    offset = payload + size;
    if ((header & 0x80) !== 0) break;
  }
  throw unsupported(
    "ingest_metadata", "missing", "FLAC STREAMINFO",
    "the FLAC STREAMINFO block is missing",
    "export the source again as a complete FLAC file",
  );
}

const MP3_BITRATES = Object.freeze({
  mpeg1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
  mpeg2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
});

function synchsafe(bytes: Uint8Array, offset: number): number {
  return ((bytes[offset] ?? 0) << 21) | ((bytes[offset + 1] ?? 0) << 14) |
    ((bytes[offset + 2] ?? 0) << 7) | (bytes[offset + 3] ?? 0);
}

function mp3Metadata(bytes: Uint8Array): SourceMetadata {
  let searchStart = 0;
  if (hasAscii(bytes, 0, "ID3") && bytes.byteLength >= 10) {
    searchStart = 10 + synchsafe(bytes, 6);
  }
  const end = Math.min(bytes.byteLength - 4, searchStart + 65_536);
  for (let offset = searchStart; offset <= end; offset += 1) {
    const b0 = bytes[offset] ?? 0;
    const b1 = bytes[offset + 1] ?? 0;
    if (b0 !== 0xff || (b1 & 0xe0) !== 0xe0) continue;
    const versionBits = (b1 >> 3) & 0x3;
    const layerBits = (b1 >> 1) & 0x3;
    if ((versionBits !== 3 && versionBits !== 2) || layerBits !== 1) continue;
    const b2 = bytes[offset + 2] ?? 0;
    const bitrateIndex = (b2 >> 4) & 0xf;
    const rateIndex = (b2 >> 2) & 0x3;
    if (bitrateIndex === 0 || bitrateIndex === 15 || rateIndex === 3) continue;
    const mpeg1 = versionBits === 3;
    const baseRates = [44_100, 48_000, 32_000];
    const sampleRate = (baseRates[rateIndex] ?? 0) / (mpeg1 ? 1 : 2);
    const bitrate = (mpeg1 ? MP3_BITRATES.mpeg1 : MP3_BITRATES.mpeg2)[bitrateIndex] ?? 0;
    const channelMode = ((bytes[offset + 3] ?? 0) >> 6) & 0x3;
    const channels = channelMode === 3 ? 1 : 2;
    const sideInfo = mpeg1 ? (channels === 1 ? 17 : 32) : (channels === 1 ? 9 : 17);
    const xing = offset + 4 + sideInfo;
    if ((hasAscii(bytes, xing, "Xing") || hasAscii(bytes, xing, "Info")) &&
        xing + 12 <= bytes.byteLength) {
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const flags = view.getUint32(xing + 4, false);
      if ((flags & 1) !== 0) {
        const frameCount = view.getUint32(xing + 8, false);
        const samplesPerFrame = mpeg1 ? 1152 : 576;
        return Object.freeze({
          container: "mp3", channels,
          normalizedFrames: normalizedFrames(frameCount * samplesPerFrame, sampleRate),
        });
      }
    }
    const vbri = offset + 4 + 32;
    if (hasAscii(bytes, vbri, "VBRI") && vbri + 18 <= bytes.byteLength) {
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const frameCount = view.getUint32(vbri + 14, false);
      const samplesPerFrame = mpeg1 ? 1152 : 576;
      return Object.freeze({
        container: "mp3", channels,
        normalizedFrames: normalizedFrames(frameCount * samplesPerFrame, sampleRate),
      });
    }
    const estimatedFrames = bitrate === 0
      ? null
      : Math.ceil(bytes.byteLength * 8 * 48_000 / (bitrate * 1000));
    return Object.freeze({container: "mp3", channels, normalizedFrames: estimatedFrames});
  }
  throw unsupported(
    "ingest_codec", "invalid", "MPEG-1/2 Layer III",
    "no supported MP3 audio frame was found",
    "export MPEG-1 or MPEG-2 Layer III audio",
  );
}

function findBox(bytes: Uint8Array, type: string): number {
  for (let offset = 4; offset + 4 <= bytes.byteLength; offset += 1) {
    if (hasAscii(bytes, offset, type)) return offset - 4;
  }
  return -1;
}

function mp4Metadata(bytes: Uint8Array): SourceMetadata {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const mdhd = findBox(bytes, "mdhd");
  const mp4a = findBox(bytes, "mp4a");
  if (mdhd < 0 || mp4a < 0 || mdhd + 12 > bytes.byteLength ||
      mp4a + 26 > bytes.byteLength) {
    throw unsupported(
      "ingest_metadata", "missing", "MP4 mdhd and AAC mp4a",
      "required M4A/AAC metadata is missing",
      "export AAC-LC or HE-AAC in an M4A container",
    );
  }
  const version = bytes[mdhd + 8];
  let timescale: number;
  let duration: number;
  if (version === 0 && mdhd + 28 <= bytes.byteLength) {
    timescale = view.getUint32(mdhd + 20, false);
    duration = view.getUint32(mdhd + 24, false);
  } else if (version === 1 && mdhd + 40 <= bytes.byteLength) {
    timescale = view.getUint32(mdhd + 28, false);
    const rawDuration = view.getBigUint64(mdhd + 32, false);
    if (rawDuration > BigInt(Number.MAX_SAFE_INTEGER)) {
      throw resourceError(
        "ingest_decoded_frames", Number.MAX_SAFE_INTEGER,
        Number.MAX_SAFE_INTEGER - 1,
        "the M4A duration exceeds safe numeric bounds",
        "shorten or re-export the source",
      );
    }
    duration = Number(rawDuration);
  } else {
    throw unsupported(
      "ingest_metadata", `mdhd-v${String(version)}`, "mdhd version 0 or 1",
      "the M4A duration metadata is invalid",
      "export AAC-LC or HE-AAC in a standard M4A container",
    );
  }
  const channels = view.getUint16(mp4a + 24, false);
  return Object.freeze({
    container: "m4a-aac",
    channels,
    normalizedFrames: normalizedFrames(duration, timescale),
  });
}

function sniffMetadata(bytes: Uint8Array): SourceMetadata {
  if (hasAscii(bytes, 0, "RIFF") && hasAscii(bytes, 8, "WAVE")) {
    return wavMetadata(bytes);
  }
  if (hasAscii(bytes, 0, "fLaC")) return flacMetadata(bytes);
  if (bytes.byteLength >= 8 && hasAscii(bytes, 4, "ftyp")) return mp4Metadata(bytes);
  if (hasAscii(bytes, 0, "ID3") ||
      (bytes[0] === 0xff && ((bytes[1] ?? 0) & 0xe0) === 0xe0)) {
    return mp3Metadata(bytes);
  }
  throw unsupported(
    "ingest_container",
    ascii(bytes, 0, Math.min(12, bytes.byteLength)),
    "WAV, MP3, M4A/AAC, or FLAC",
    "the source container is not supported",
    "choose WAV, MP3, M4A/AAC, or FLAC audio",
  );
}

function enforceMetadata(metadata: SourceMetadata, limits: LongSourceLimits): void {
  if (metadata.channels !== null && metadata.channels > limits.channels) {
    throw resourceError(
      "ingest_channels", metadata.channels, limits.channels,
      "the source has too many channels",
      `export mono or stereo audio with at most ${limits.channels} channels`,
    );
  }
  if (metadata.normalizedFrames !== null &&
      metadata.normalizedFrames > limits.decodedFrames) {
    throw resourceError(
      "ingest_decoded_frames", metadata.normalizedFrames, limits.decodedFrames,
      "the decoded source would exceed the 48 kHz frame limit",
      "shorten the source before importing it",
    );
  }
}

async function decodeAt48Khz(bytes: ArrayBuffer): Promise<AudioBufferView> {
  const Context = globalThis.OfflineAudioContext;
  if (typeof Context !== "function") {
    throw unsupported(
      "ingest_decoder", "unavailable", "OfflineAudioContext at 48 kHz",
      "the browser cannot create the required offline decoder",
      "use a supported current browser",
    );
  }
  const context = new Context(2, 1, 48_000);
  try {
    return await context.decodeAudioData(bytes);
  } finally {
    // OfflineAudioContext owns no live output device and exposes no close().
  }
}

export class DecodedLongSource {
  readonly container: LongSourceContainer;
  readonly sourceName: string;
  #buffer: AudioBufferView | null;
  #previewContext: AudioContext | null = null;
  #previewNode: AudioBufferSourceNode | null = null;

  constructor(container: LongSourceContainer, sourceName: string, buffer: AudioBufferView) {
    this.container = container;
    this.sourceName = sourceName;
    this.#buffer = buffer;
  }

  get released(): boolean { return this.#buffer === null; }
  get frameCount(): number { return this.#requireBuffer().length; }
  get channelCount(): number { return this.#requireBuffer().numberOfChannels; }
  get sampleRate(): number { return this.#requireBuffer().sampleRate; }

  #requireBuffer(): AudioBufferView {
    if (this.#buffer === null) throw new Error("Long source has been released");
    return this.#buffer;
  }

  envelope(bins: number, startFrame: number, frameCount: number): Float32Array {
    const buffer = this.#requireBuffer();
    if (!validLimit(bins) || !Number.isSafeInteger(startFrame) || startFrame < 0 ||
        !validLimit(frameCount) || startFrame + frameCount > buffer.length) {
      throw new RangeError("Long-source waveform range is invalid");
    }
    const output = new Float32Array(bins);
    for (let bin = 0; bin < bins; bin += 1) {
      const from = startFrame + Math.floor(bin * frameCount / bins);
      const to = startFrame + Math.floor((bin + 1) * frameCount / bins);
      const step = Math.max(1, Math.floor(Math.max(1, to - from) / 4_096));
      let peak = 0;
      for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
        const samples = buffer.getChannelData(channel);
        for (let frame = from; frame < to; frame += step) {
          const magnitude = Math.abs(samples[frame] ?? 0);
          if (magnitude > peak) peak = magnitude;
        }
      }
      output[bin] = peak;
    }
    return output;
  }

  encodeSelection(
    selection: {startFrame: number; frameCount: number},
    quotaFrames: number,
  ): File {
    const buffer = this.#requireBuffer();
    if (!Number.isSafeInteger(selection.startFrame) || selection.startFrame < 0 ||
        !validLimit(selection.frameCount) || !validLimit(quotaFrames) ||
        selection.frameCount > quotaFrames ||
        selection.startFrame + selection.frameCount > buffer.length) {
      throw new RangeError("Long-source selection exceeds the effective quota");
    }
    const channels = Array.from({length: buffer.numberOfChannels}, (_, channel) =>
      buffer.getChannelData(channel).subarray(
        selection.startFrame,
        selection.startFrame + selection.frameCount,
      ));
    const wav = encodePcm16Wav(channels, 48_000);
    return new File([wav], "source-selection.wav", {type: "audio/wav"});
  }

  async preview(selection: {startFrame: number; frameCount: number}): Promise<void> {
    const buffer = this.#requireBuffer();
    if (!Number.isSafeInteger(selection.startFrame) || selection.startFrame < 0 ||
        !validLimit(selection.frameCount) ||
        selection.startFrame + selection.frameCount > buffer.length) {
      throw new RangeError("Long-source preview range is invalid");
    }
    this.stopPreview();
    const Context = globalThis.AudioContext;
    if (typeof Context !== "function") {
      throw unsupported(
        "ingest_preview", "unavailable", "AudioContext",
        "browser audio preview is unavailable",
        "continue without preview or use a supported current browser",
      );
    }
    const context = new Context({sampleRate: 48_000});
    const node = context.createBufferSource();
    node.buffer = buffer as AudioBuffer;
    node.connect(context.destination);
    node.addEventListener("ended", () => {
      if (this.#previewNode !== node) return;
      this.#previewNode = null;
      this.#previewContext = null;
      void context.close();
    }, {once: true});
    this.#previewContext = context;
    this.#previewNode = node;
    if (context.state === "suspended") await context.resume();
    node.start(
      0,
      selection.startFrame / 48_000,
      selection.frameCount / 48_000,
    );
  }

  stopPreview(): void {
    const node = this.#previewNode;
    const context = this.#previewContext;
    this.#previewNode = null;
    this.#previewContext = null;
    try { node?.stop(); } catch {}
    try { node?.disconnect(); } catch {}
    if (context !== null) void context.close().catch(() => {});
  }

  release(): void {
    this.stopPreview();
    this.#buffer = null;
  }
}

export async function openLongSource(
  file: LongSourceFile,
  limits: LongSourceLimits,
  dependencies: LongSourceDependencies = {decode: decodeAt48Khz},
): Promise<DecodedLongSource> {
  validateLimits(limits);
  if (file === null || typeof file !== "object" || typeof file.name !== "string" ||
      !validLimit(file.size) || typeof file.arrayBuffer !== "function") {
    throw unsupported(
      "ingest_source", "invalid", "non-empty browser File",
      "the selected source is invalid",
      "choose a non-empty local audio file",
    );
  }
  if (file.size > limits.sourceBytes) {
    throw resourceError(
      "ingest_source_bytes", file.size, limits.sourceBytes,
      "the compressed source exceeds the import byte limit",
      "choose a smaller source file",
    );
  }
  let bytes: ArrayBuffer;
  try {
    bytes = await file.arrayBuffer();
  } catch {
    throw unsupported(
      "ingest_source", "unreadable", "readable browser File",
      "the selected source could not be read",
      "choose the file again or export a new copy",
    );
  }
  const metadata = sniffMetadata(new Uint8Array(bytes));
  enforceMetadata(metadata, limits);
  let decoded: AudioBufferView;
  try {
    // The same source ArrayBuffer used for metadata admission is transferred to
    // decodeAudioData. No second source copy is retained by the Host.
    decoded = await dependencies.decode(bytes);
  } catch (error) {
    if (error instanceof LongSourceIngestError) throw error;
    throw unsupported(
      "ingest_decoder", "failed", "successful browser decode",
      "the browser could not decode this supported container",
      "re-export the source with a supported codec",
    );
  }
  if (decoded.sampleRate !== 48_000) {
    throw resourceError(
      "ingest_sample_rate", decoded.sampleRate, 48_000,
      "the offline decoder did not produce 48 kHz audio",
      "retry in a supported browser",
    );
  }
  if (decoded.numberOfChannels > limits.channels) {
    throw resourceError(
      "ingest_channels", decoded.numberOfChannels, limits.channels,
      "the decoded source has too many channels",
      `export mono or stereo audio with at most ${limits.channels} channels`,
    );
  }
  if (decoded.length > limits.decodedFrames) {
    throw resourceError(
      "ingest_decoded_frames", decoded.length, limits.decodedFrames,
      "the decoded source exceeds the 48 kHz frame limit",
      "shorten the source before importing it",
    );
  }
  if (!validLimit(decoded.length) || decoded.numberOfChannels < 1) {
    throw unsupported(
      "ingest_decoder", "empty", "non-empty mono or stereo audio",
      "the decoded source contains no usable audio",
      "choose a non-empty mono or stereo source",
    );
  }
  return new DecodedLongSource(metadata.container, file.name, decoded);
}
