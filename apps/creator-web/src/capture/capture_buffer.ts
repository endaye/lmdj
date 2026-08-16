export const CAPTURE_SAMPLE_RATE = 48_000;
export const CAPTURE_MAX_FRAMES = 2_880_000; // 60 s at 48 kHz (S8B-D3)
export const COMMIT_MAX_FRAMES = 240_000;    // manifest decoded_frames_per_pad
// Summary granularity for the envelope's block path. 256 frames keeps a full
// 60 s stereo take at ~11,250 block peaks (~45 KB), so a redraw scans blocks,
// not samples, once bins are at least this wide.
export const ENVELOPE_BLOCK_FRAMES = 256;

export class CaptureBuffer {
  readonly channelCount: number;
  #chunks: Float32Array[][];
  #frames = 0;
  // Finding 4: envelope() is called once per delivered batch (about 10x/sec).
  // Memoization only helps between batches; each append() invalidates it, so
  // during recording every redraw still ran O(total frames), toward ~5.76M
  // sample visits per redraw over a full 60 s stereo take. append() therefore
  // also maintains per-block peak summaries (O(new frames), amortized free),
  // and envelope() serves wide bins from those blocks in O(blocks).
  #envelopeCache: {frames: number; bins: number; result: Float32Array} | null = null;
  // Per-channel max-abs peak of each ENVELOPE_BLOCK_FRAMES-sized block; the
  // last entry is a partial block that keeps accumulating. Correct only
  // because the buffer is append-only: slice() never mutates stored samples.
  // If pre-commit editing is ever added, these summaries need invalidation.
  #blockPeaks: number[][];

  constructor(channelCount: 1 | 2) {
    if (channelCount !== 1 && channelCount !== 2) {
      throw new TypeError("Capture channel count must be 1 or 2");
    }
    this.channelCount = channelCount;
    this.#chunks = Array.from({length: channelCount}, () => []);
    this.#blockPeaks = Array.from({length: channelCount}, () => []);
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
      const peaks = this.#blockPeaks[i];
      if (chunkList === undefined || peaks === undefined) {
        throw new TypeError("Capture batch shape is invalid");
      }
      chunkList.push(c.slice(0, accepted));
      // Fold the new samples into the block summaries as they arrive; batch
      // boundaries and block boundaries are independent, so the last block
      // stays partial and keeps accumulating across appends.
      for (let s = 0; s < accepted; s += 1) {
        const block = Math.floor((this.#frames + s) / ENVELOPE_BLOCK_FRAMES);
        const magnitude = Math.abs(c[s] ?? 0);
        const current = peaks[block];
        if (current === undefined || magnitude > current) { peaks[block] = magnitude; }
      }
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
    const perBin = this.#frames / bins;
    if (perBin >= ENVELOPE_BLOCK_FRAMES) {
      // Block path: every bin spans at least one summary block, so serve the
      // redraw from block peaks in O(blocks). Bin boundaries snap OUTWARD to
      // block edges: a boundary-straddling block contributes its peak to both
      // neighbouring bins, so edge values may overestimate but a peak can
      // never be dropped or undercounted. This renders the whole buffer; if a
      // zoom window is ever added (long-take trims), envelope() needs
      // (bins, startFrame, frameCount) and the exact/block decision must use
      // the window length, or narrow windows fall back to scanning the entire
      // buffer again.
      const lastBlock = Math.ceil(this.#frames / ENVELOPE_BLOCK_FRAMES) - 1;
      for (let bin = 0; bin < bins; bin += 1) {
        const from = Math.floor((bin * perBin) / ENVELOPE_BLOCK_FRAMES);
        const to = Math.min(
          Math.ceil(((bin + 1) * perBin) / ENVELOPE_BLOCK_FRAMES) - 1, lastBlock);
        let peak = 0;
        for (const peaks of this.#blockPeaks) {
          for (let block = from; block <= to; block += 1) {
            const value = peaks[block];
            if (value !== undefined && value > peak) { peak = value; }
          }
        }
        out[bin] = peak;
      }
    } else if (this.#frames > 0) {
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
