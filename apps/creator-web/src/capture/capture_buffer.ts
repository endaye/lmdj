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
  #envelopeCache: {
    frames: number;
    bins: number;
    startFrame: number;
    frameCount: number;
    result: Float32Array;
  } | null = null;
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

  #peakInRange(startFrame: number, endFrame: number): number {
    if (startFrame >= endFrame) return 0;
    let peak = 0;
    for (const chunks of this.#chunks) {
      let base = 0;
      for (const chunk of chunks) {
        const chunkEnd = base + chunk.length;
        if (chunkEnd <= startFrame) {
          base = chunkEnd;
          continue;
        }
        if (base >= endFrame) break;
        const from = Math.max(startFrame - base, 0);
        const to = Math.min(endFrame - base, chunk.length);
        for (let i = from; i < to; i += 1) {
          const magnitude = Math.abs(chunk[i] ?? 0);
          if (magnitude > peak) peak = magnitude;
        }
        base = chunkEnd;
      }
    }
    return peak;
  }

  envelope(bins: number, startFrame: number, frameCount: number): Float32Array {
    if (!Number.isInteger(bins) || bins <= 0) {
      throw new TypeError("Envelope bin count is invalid");
    }
    if (!Number.isInteger(startFrame) || !Number.isInteger(frameCount) ||
        startFrame < 0 || frameCount <= 0 || startFrame + frameCount > this.#frames) {
      throw new RangeError("Envelope range is out of bounds");
    }
    const cache = this.#envelopeCache;
    if (cache !== null && cache.frames === this.#frames && cache.bins === bins &&
        cache.startFrame === startFrame && cache.frameCount === frameCount) {
      return cache.result;
    }
    const out = new Float32Array(bins);
    const perBin = frameCount / bins;
    if (perBin >= ENVELOPE_BLOCK_FRAMES) {
      // Consume a summary only when the complete block belongs to this bin.
      // Boundary-straddling blocks are scanned exactly so a peak outside the
      // selected window or in an adjacent bin cannot leak into this result.
      for (let bin = 0; bin < bins; bin += 1) {
        const from = startFrame + Math.ceil(bin * perBin);
        const to = startFrame + Math.min(Math.ceil((bin + 1) * perBin), frameCount);
        const firstFullBlock = Math.ceil(from / ENVELOPE_BLOCK_FRAMES);
        const fullBlockEnd = Math.floor(to / ENVELOPE_BLOCK_FRAMES);
        const leadingEnd = Math.min(to, firstFullBlock * ENVELOPE_BLOCK_FRAMES);
        let peak = this.#peakInRange(from, leadingEnd);
        for (const peaks of this.#blockPeaks) {
          for (let block = firstFullBlock; block < fullBlockEnd; block += 1) {
            const value = peaks[block];
            if (value !== undefined && value > peak) { peak = value; }
          }
        }
        const trailingStart = Math.max(leadingEnd, fullBlockEnd * ENVELOPE_BLOCK_FRAMES);
        peak = Math.max(peak, this.#peakInRange(trailingStart, to));
        out[bin] = peak;
      }
    } else {
      for (let bin = 0; bin < bins; bin += 1) {
        const from = startFrame + Math.ceil(bin * perBin);
        const to = startFrame + Math.min(Math.ceil((bin + 1) * perBin), frameCount);
        out[bin] = this.#peakInRange(from, to);
      }
    }
    this.#envelopeCache = {frames: this.#frames, bins, startFrame, frameCount, result: out};
    return out;
  }
}
