import masterTapSource from "./master_tap_worklet.js?raw";
import masterTapUrl from "./master_tap_worklet.js?url&no-inline";

import type {
  WavSealReason,
  WavStreamWriter,
  WavWriterSnapshot,
} from "./wav_stream_writer";

export const PERFORM_WORKLET_NAME = "lmdj-perform-master-tap";
export const PERFORM_BATCH_FRAMES = 4_800;
export const PERFORM_QUEUE_BATCHES = 32;
export const PERFORM_WORKLET_SOURCE: string = masterTapSource;
export const PERFORM_WORKLET_URL: string = masterTapUrl;

export const PERFORM_BACKPRESSURE_MESSAGE =
  "Recording stopped because storage could not keep up. The durable WAV prefix is still available.";
export const PERFORM_LIMIT_MESSAGE =
  "Recording reached the 30-minute limit. The durable WAV is ready to save.";
export const PERFORM_WRITER_FAILURE_MESSAGE =
  "Recording stopped because storage failed. The durable WAV prefix is still available.";
export const PERFORM_TAP_FAILURE_MESSAGE =
  "Recording stopped because the audio tap could not deliver a batch. The durable WAV prefix is still available.";

export interface MasterTapFailure {
  readonly reason: Exclude<WavSealReason, "stopped">;
  readonly message: string;
  readonly durableFrames: number;
  readonly droppedFrames: number;
}

export interface MasterTapListener {
  onFailure(failure: MasterTapFailure): void;
}

type BatchWriter = Pick<WavStreamWriter,
  "appendChannels" | "queueBatchLimit" | "seal">;

export interface MasterTapPort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  postMessage(message: Readonly<{type: "stop"}>): void;
}

type TerminalReason = Exclude<WavSealReason, "stopped">;

export class MasterTapBatchQueue {
  readonly #writer: BatchWriter;
  readonly #listener: MasterTapListener;
  readonly #queue: Array<readonly Float32Array[]> = [];
  readonly #settledPromise: Promise<WavWriterSnapshot>;
  #resolveSettled: ((snapshot: WavWriterSnapshot) => void) | null = null;
  #port: MasterTapPort | null = null;
  #draining = false;
  #outstanding = 0;
  #sealed = false;
  #sealReason: WavSealReason | null = null;
  #droppedFrames = 0;
  #workletStopped = false;
  #stopRequested = false;
  #finishing = false;

  constructor(writer: BatchWriter, listener: MasterTapListener) {
    this.#writer = writer;
    this.#listener = listener;
    this.#settledPromise = new Promise((resolve) => { this.#resolveSettled = resolve; });
  }

  get pendingBatches(): number { return this.#outstanding; }
  get droppedFrames(): number { return this.#droppedFrames; }
  get sealed(): boolean { return this.#sealed; }
  get settled(): Promise<WavWriterSnapshot> { return this.#settledPromise; }

  connect(port: MasterTapPort): void {
    if (this.#port !== null) throw new Error("Perform tap port is already connected");
    this.#port = port;
    port.onmessage = (event) => this.#acceptMessage(event.data);
  }

  stop(): Promise<WavWriterSnapshot> {
    if (this.#stopRequested || this.#sealed) return this.#settledPromise;
    if (this.#port === null) throw new Error("Perform tap port is not connected");
    this.#requestWorkletStop();
    return this.#settledPromise;
  }

  acceptBatch(channels: readonly Float32Array[]): void {
    if (this.#sealed) {
      this.#droppedFrames += channels[0]?.length ?? 0;
      return;
    }
    const frames = this.#validateBatch(channels);
    if (this.#outstanding >= this.#writer.queueBatchLimit) {
      this.#requestTerminal("backpressure", frames);
      return;
    }
    this.#queue.push(channels);
    this.#outstanding += 1;
    if (!this.#draining) void this.#drain();
  }

  #validateBatch(channels: readonly Float32Array[]): number {
    if (channels.length !== 2 ||
        channels.some((channel) =>
          !(channel instanceof Float32Array) ||
          channel.length !== channels[0]?.length) ||
        (channels[0]?.length ?? 0) < 1 ||
        (channels[0]?.length ?? 0) > PERFORM_BATCH_FRAMES) {
      throw new TypeError("Perform tap batch is invalid");
    }
    return channels[0]!.length;
  }

  #acceptMessage(value: unknown): void {
    if (value === null || typeof value !== "object") return;
    const message = value as Record<string, unknown>;
    if (message.type === "batch" && Array.isArray(message.channels)) {
      this.acceptBatch(message.channels as Float32Array[]);
      return;
    }
    if (message.type === "stopped") {
      this.#workletStopped = true;
      if (this.#sealed) this.#maybeFinishTerminal();
      else this.#maybeFinishNormalStop();
      return;
    }
    if (message.type === "failed" &&
        message.reason === "post-message-failed") {
      const dropped = Number.isSafeInteger(message.droppedFrames) &&
        (message.droppedFrames as number) >= 0
        ? message.droppedFrames as number
        : 0;
      this.#workletStopped = true;
      this.#requestTerminal("tap-failure", dropped);
    }
  }

  async #drain(): Promise<void> {
    this.#draining = true;
    while (!this.#sealed && this.#queue.length > 0) {
      const channels = this.#queue.shift();
      if (channels === undefined) break;
      let snapshot: WavWriterSnapshot;
      try {
        snapshot = await this.#writer.appendChannels(channels);
      } catch {
        this.#requestTerminal("writer-error", channels[0]?.length ?? 0);
        break;
      } finally {
        this.#outstanding -= 1;
      }
      if (snapshot.state === "sealed") {
        if (snapshot.reason === "stopped") {
          this.#sealed = true;
          this.#sealReason = "stopped";
        } else if (snapshot.reason !== null) {
          this.#requestTerminal(snapshot.reason, 0);
        }
      }
    }
    if (this.#sealed) {
      for (const queued of this.#queue) this.#droppedFrames += queued[0]?.length ?? 0;
      this.#outstanding -= this.#queue.length;
      this.#queue.splice(0);
    }
    this.#draining = false;
    if (this.#sealReason !== null) this.#maybeFinishTerminal();
    else this.#maybeFinishNormalStop();
  }

  #requestTerminal(reason: TerminalReason, additionalDroppedFrames: number): void {
    if (this.#sealed) {
      this.#droppedFrames += additionalDroppedFrames;
      this.#maybeFinishTerminal();
      return;
    }
    this.#sealed = true;
    this.#sealReason = reason;
    this.#droppedFrames += additionalDroppedFrames;
    for (const queued of this.#queue) this.#droppedFrames += queued[0]?.length ?? 0;
    this.#outstanding -= this.#queue.length;
    this.#queue.splice(0);
    this.#requestWorkletStop();
    this.#maybeFinishTerminal();
  }

  #requestWorkletStop(): void {
    if (this.#stopRequested) return;
    const port = this.#port;
    if (port === null) return;
    this.#stopRequested = true;
    try {
      port.postMessage({type: "stop"});
    } catch {
      this.#workletStopped = true;
      this.#requestTerminal("tap-failure", 0);
    }
  }

  #maybeFinishTerminal(): void {
    if (!this.#sealed || this.#sealReason === null || this.#draining ||
        this.#finishing || (this.#port !== null && !this.#workletStopped)) return;
    void this.#finishSeal();
  }

  #maybeFinishNormalStop(): void {
    if (!this.#workletStopped || this.#sealed || this.#draining ||
        this.#outstanding !== 0 || this.#queue.length !== 0) return;
    this.#sealed = true;
    this.#sealReason = "stopped";
    void this.#finishSeal();
  }

  async #finishSeal(): Promise<void> {
    const reason = this.#sealReason;
    if (reason === null || this.#resolveSettled === null || this.#finishing) return;
    this.#finishing = true;
    const snapshot = await this.#writer.seal(reason);
    const reportedReason = snapshot.reason ?? reason;
    const settled = Object.freeze({
      state: "sealed" as const,
      durableFrames: snapshot.durableFrames,
      byteLength: snapshot.byteLength,
      reason: reportedReason,
      droppedFrames: this.#droppedFrames + (snapshot.droppedFrames ?? 0),
    });
    if (reportedReason !== "stopped") {
      try {
        this.#listener.onFailure(Object.freeze({
          reason: reportedReason,
          message: this.#failureMessage(reportedReason),
          durableFrames: settled.durableFrames,
          droppedFrames: settled.droppedFrames,
        }));
      } catch {
        // Host notification code is outside recording ownership. A reporting
        // failure must not turn a sealed recording into an unhandled rejection.
      }
    }
    this.#resolveSettled(settled);
    this.#resolveSettled = null;
  }

  #failureMessage(reason: TerminalReason): string {
    if (reason === "backpressure") return PERFORM_BACKPRESSURE_MESSAGE;
    if (reason === "frame-limit") return PERFORM_LIMIT_MESSAGE;
    if (reason === "tap-failure") return PERFORM_TAP_FAILURE_MESSAGE;
    return PERFORM_WRITER_FAILURE_MESSAGE;
  }
}
