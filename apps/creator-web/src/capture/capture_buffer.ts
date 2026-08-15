export const CAPTURE_SAMPLE_RATE = 48_000;
export const CAPTURE_MAX_FRAMES = 2_880_000; // 60 s at 48 kHz (S8B-D3)
export const COMMIT_MAX_FRAMES = 240_000;    // manifest decoded_frames_per_pad

export class CaptureBuffer {
  readonly channelCount: number;
  #chunks: Float32Array[][];
  #frames = 0;
  // Finding 4: envelope() is called once per delivered batch (about 10x/sec)
  // and, unmemoized, walks every stored sample of every channel each time —
  // O(total frames) per call, growing toward ~5.76M sample visits per redraw
  // over a full 60 s stereo take. Memoizing on the only two inputs that can
  // change the result (frame count, bin count) makes repeated calls with an
  // unchanged buffer free; append() invalidates it below.
  #envelopeCache: {frames: number; bins: number; result: Float32Array} | null = null;

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
    const first = channels[0];
    if (channels.length !== this.channelCount || first === undefined ||
        channels.some((c) => !(c instanceof Float32Array) || c.length !== first.length)) {
      throw new TypeError("Capture batch shape is invalid");
    }
    const accepted = Math.min(first.length, CAPTURE_MAX_FRAMES - this.#frames);
    if (accepted <= 0) { return 0; }
    channels.forEach((c, i) => {
      const chunkList = this.#chunks[i];
      if (chunkList === undefined) {
        throw new TypeError("Capture batch shape is invalid");
      }
      chunkList.push(c.slice(0, accepted));
    });
    this.#frames += accepted;
    this.#envelopeCache = null;
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
    const cache = this.#envelopeCache;
    if (cache !== null && cache.frames === this.#frames && cache.bins === bins) {
      return cache.result;
    }
    const out = new Float32Array(bins);
    if (this.#frames > 0) {
      const perBin = this.#frames / bins;
      for (const chunks of this.#chunks) {
        let index = 0;
        for (const chunk of chunks) {
          const length = chunk.length;
          for (let i = 0; i < length; i += 1) {
            const bin = Math.min(Math.floor(index / perBin), bins - 1);
            const magnitude = Math.abs(chunk[i] ?? 0);
            const current = out[bin];
            if (current === undefined || magnitude > current) { out[bin] = magnitude; }
            index += 1;
          }
        }
      }
    }
    this.#envelopeCache = {frames: this.#frames, bins, result: out};
    return out;
  }
}
