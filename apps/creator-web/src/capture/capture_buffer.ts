export const CAPTURE_SAMPLE_RATE = 48_000;
export const CAPTURE_MAX_FRAMES = 2_880_000; // 60 s at 48 kHz (S8B-D3)
export const COMMIT_MAX_FRAMES = 240_000;    // manifest decoded_frames_per_pad

export class CaptureBuffer {
  readonly channelCount: number;
  #chunks: Float32Array[][];
  #frames = 0;

  constructor(channelCount: 1 | 2) {
    if (channelCount !== 1 && channelCount !== 2) {
      throw new TypeError("Capture channel count must be 1 or 2");
    }
    this.channelCount = channelCount;
    this.#chunks = Array.from({length: channelCount}, () => []);
  }

  get frameCount(): number { return this.#frames; }
  get atCapacity(): boolean { return this.#frames >= CAPTURE_MAX_FRAMES; }

  append(channels: readonly Float32Array[]): number {
    if (channels.length !== this.channelCount ||
        channels.some((c) => !(c instanceof Float32Array) || c.length !== channels[0].length)) {
      throw new TypeError("Capture batch shape is invalid");
    }
    const accepted = Math.min(channels[0].length, CAPTURE_MAX_FRAMES - this.#frames);
    if (accepted <= 0) { return 0; }
    channels.forEach((c, i) => this.#chunks[i].push(c.slice(0, accepted)));
    this.#frames += accepted;
    return accepted;
  }

  slice(startFrame: number, frameCount: number): Float32Array[] {
    if (!Number.isInteger(startFrame) || !Number.isInteger(frameCount) ||
        startFrame < 0 || frameCount <= 0 || startFrame + frameCount > this.#frames) {
      throw new RangeError("Capture slice is out of range");
    }
    return this.#chunks.map((chunks) => {
      const out = new Float32Array(frameCount);
      let base = 0, written = 0;
      for (const chunk of chunks) {
        const from = Math.max(startFrame - base, 0);
        if (from < chunk.length && written < frameCount) {
          const take = Math.min(chunk.length - from, frameCount - written);
          out.set(chunk.subarray(from, from + take), written);
          written += take;
        }
        base += chunk.length;
        if (written === frameCount) { break; }
      }
      return out;
    });
  }

  envelope(bins: number): Float32Array {
    if (!Number.isInteger(bins) || bins <= 0) {
      throw new TypeError("Envelope bin count is invalid");
    }
    const out = new Float32Array(bins);
    if (this.#frames === 0) { return out; }
    const perBin = this.#frames / bins;
    for (const chunks of this.#chunks) {
      let index = 0;
      for (const chunk of chunks) {
        for (const value of chunk) {
          const bin = Math.min(Math.floor(index / perBin), bins - 1);
          const magnitude = Math.abs(value);
          if (magnitude > out[bin]) { out[bin] = magnitude; }
          index += 1;
        }
      }
    }
    return out;
  }
}
