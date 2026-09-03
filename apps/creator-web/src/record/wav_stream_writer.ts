import {
  encodePcm16Frames,
  encodePcm16WavHeader,
  PCM16_WAV_HEADER_BYTES,
} from "../capture/wav_encoder";

const SAMPLE_RATE = 48_000;
const CHANNELS = 2;
const FRAME_BYTES = CHANNELS * 2;

export interface PerformanceRecordingLimits {
  readonly perform_recording_frames: number;
  readonly perform_recording_queue_batches: number;
}

export type WavSealReason =
  | "frame-limit"
  | "writer-error"
  | "opfs-failure"
  | "backpressure"
  | "tap-failure"
  | "stopped";

export interface WavWriterSnapshot {
  readonly state: "active" | "sealed";
  readonly durableFrames: number;
  readonly byteLength: number;
  readonly reason: WavSealReason | null;
  readonly droppedFrames: number;
}

interface OpfsWritable {
  seek(position: number): Promise<void>;
  write(data: Uint8Array<ArrayBuffer>): Promise<void>;
  truncate(size: number): Promise<void>;
  close(): Promise<void>;
  abort(reason?: unknown): Promise<void>;
}

export interface OpfsWavFileHandle {
  createWritable(options?: {keepExistingData?: boolean}): Promise<OpfsWritable>;
}

function positiveInteger(value: unknown, name: string): number {
  if (!Number.isSafeInteger(value) || (value as number) <= 0) {
    throw new TypeError(`${name} is required and must be a positive integer`);
  }
  return value as number;
}

function validateLimits(limits: PerformanceRecordingLimits): PerformanceRecordingLimits {
  if (limits === null || typeof limits !== "object") {
    throw new TypeError("Performance recording Host limits are required");
  }
  return Object.freeze({
    perform_recording_frames: positiveInteger(
      limits.perform_recording_frames,
      "perform_recording_frames",
    ),
    perform_recording_queue_batches: positiveInteger(
      limits.perform_recording_queue_batches,
      "perform_recording_queue_batches",
    ),
  });
}

export class WavStreamWriter {
  readonly #file: OpfsWavFileHandle;
  readonly #limits: PerformanceRecordingLimits;
  #durableFrames = 0;
  #attemptedFrames = 0;
  #reason: WavSealReason | null = null;
  #writable: OpfsWritable | null = null;
  #pendingFrames = 0;
  #pendingBatches = 0;
  #droppedFrames = 0;

  constructor(file: OpfsWavFileHandle, limits: PerformanceRecordingLimits) {
    this.#file = file;
    this.#limits = validateLimits(limits);
  }

  get queueBatchLimit(): number {
    return this.#limits.perform_recording_queue_batches;
  }

  get attemptedFrames(): number {
    return this.#attemptedFrames;
  }

  get snapshot(): WavWriterSnapshot {
    return Object.freeze({
      state: this.#reason === null ? "active" : "sealed",
      durableFrames: this.#durableFrames,
      byteLength: PCM16_WAV_HEADER_BYTES + this.#durableFrames * FRAME_BYTES,
      reason: this.#reason,
      droppedFrames: this.#droppedFrames,
    });
  }

  async initialize(): Promise<void> {
    const writable = await this.#file.createWritable({keepExistingData: false});
    try {
      await writable.write(encodePcm16WavHeader(0, CHANNELS, SAMPLE_RATE));
      await writable.truncate(PCM16_WAV_HEADER_BYTES);
      await writable.close();
    } catch (error) {
      await writable.abort(error).catch(() => {});
      throw error;
    }
  }

  async appendChannels(channels: readonly Float32Array[]): Promise<WavWriterSnapshot> {
    if (channels.length !== CHANNELS) {
      throw new TypeError("Performance recording requires stereo channels");
    }
    return this.appendPcm16(encodePcm16Frames(channels));
  }

  async appendPcm16(pcm: Uint8Array<ArrayBuffer>): Promise<WavWriterSnapshot> {
    if (!(pcm instanceof Uint8Array) || pcm.length === 0 || pcm.length % FRAME_BYTES !== 0) {
      throw new TypeError("Performance PCM16 input is invalid");
    }
    const frames = pcm.length / FRAME_BYTES;
    this.#attemptedFrames += frames;
    if (this.#reason !== null) {
      this.#droppedFrames += frames;
      return this.snapshot;
    }

    const remaining = this.#limits.perform_recording_frames - this.#durableFrames;
    const writableFrames = Math.max(0, remaining - this.#pendingFrames);
    const acceptedFrames = Math.min(writableFrames, frames);
    this.#droppedFrames += frames - acceptedFrames;
    if (acceptedFrames > 0) {
      const accepted = acceptedFrames === frames
        ? pcm
        : pcm.slice(0, acceptedFrames * FRAME_BYTES);
      const written = await this.#writePending(accepted, acceptedFrames);
      if (!written) return this.snapshot;
    }
    const atLimit = acceptedFrames < frames ||
      this.#durableFrames + this.#pendingFrames ===
        this.#limits.perform_recording_frames;
    if (this.#pendingBatches >= this.#limits.perform_recording_queue_batches || atLimit) {
      const checkpointed = await this.#checkpoint();
      if (!checkpointed) return this.snapshot;
    }
    if (atLimit) {
      this.#reason = "frame-limit";
    }
    return this.snapshot;
  }

  async seal(reason: WavSealReason = "stopped"): Promise<WavWriterSnapshot> {
    if (this.#reason !== null) return this.snapshot;
    if (reason === "stopped" || reason === "frame-limit") {
      const checkpointed = await this.#checkpoint();
      if (checkpointed) this.#reason = reason;
    } else {
      await this.#abortPending(reason);
      this.#reason = reason;
    }
    return this.snapshot;
  }

  async #openTransaction(): Promise<boolean> {
    if (this.#writable !== null) return true;
    try {
      this.#writable = await this.#file.createWritable({keepExistingData: true});
    } catch {
      this.#reason = "opfs-failure";
      return false;
    }
    try {
      await this.#writable.seek(
        PCM16_WAV_HEADER_BYTES + this.#durableFrames * FRAME_BYTES,
      );
      return true;
    } catch (error) {
      await this.#abortPending(error);
      this.#reason = "writer-error";
      return false;
    }
  }

  async #writePending(
    pcm: Uint8Array<ArrayBuffer>,
    frames: number,
  ): Promise<boolean> {
    if (!await this.#openTransaction()) {
      this.#droppedFrames += frames;
      return false;
    }
    try {
      await this.#writable!.write(pcm);
      this.#pendingFrames += frames;
      this.#pendingBatches += 1;
      return true;
    } catch (error) {
      await this.#abortPending(error, frames);
      this.#reason = "writer-error";
      return false;
    }
  }

  async #checkpoint(): Promise<boolean> {
    if (this.#pendingFrames === 0) return true;
    const writable = this.#writable;
    if (writable === null) {
      this.#reason = "writer-error";
      return false;
    }
    const nextFrames = this.#durableFrames + this.#pendingFrames;
    try {
      await writable.seek(0);
      await writable.write(encodePcm16WavHeader(nextFrames, CHANNELS, SAMPLE_RATE));
      await writable.truncate(PCM16_WAV_HEADER_BYTES + nextFrames * FRAME_BYTES);
      await writable.close();
      this.#writable = null;
      this.#durableFrames = nextFrames;
      this.#pendingFrames = 0;
      this.#pendingBatches = 0;
      return true;
    } catch (error) {
      await this.#abortPending(error);
      this.#reason = "writer-error";
      return false;
    }
  }

  async #abortPending(error: unknown, additionalFrames = 0): Promise<void> {
    const writable = this.#writable;
    this.#writable = null;
    this.#droppedFrames += this.#pendingFrames + additionalFrames;
    this.#pendingFrames = 0;
    this.#pendingBatches = 0;
    if (writable !== null) await writable.abort(error).catch(() => {});
  }
}

export async function openWavStreamWriter(
  file: OpfsWavFileHandle,
  limits: PerformanceRecordingLimits,
): Promise<WavStreamWriter> {
  const writer = new WavStreamWriter(file, limits);
  await writer.initialize();
  return writer;
}
