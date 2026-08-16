// The capture recorder AudioWorklet processor. This is a real same-origin
// distribution asset, not an inlined string: the hardened distribution CSP is
// `script-src 'self' 'wasm-unsafe-eval'`, and AudioWorklet module loading is
// governed by script-src, so blob: and data: module URLs are rejected at
// addModule() in the packaged Creator. The name and batch width are mirrored
// in capture_worklet_source.ts and pinned equal by a unit test.
const CAPTURE_BATCH_FRAMES = 4800;

class LmdjCaptureRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.batch = null;
    this.filled = 0;
    // 0 means "not yet decided". Decided once, from the first non-empty
    // input, and never revisited: the delivered audio is the single
    // authority on channel width (mono or stereo only), so every posted
    // batch has the same width for the processor's whole lifetime even if
    // the input's reported channel count changes later.
    this.channelCount = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) { return true; }
    if (this.channelCount === 0) {
      this.channelCount = input.length >= 2 ? 2 : 1;
    }
    const frames = input[0].length;
    let offset = 0;
    while (offset < frames) {
      // Allocate inside the loop: a quantum that crosses a batch boundary
      // posts (and nulls) the batch mid-loop, then keeps writing.
      if (this.batch === null) {
        this.batch = Array.from(
          {length: this.channelCount}, () => new Float32Array(CAPTURE_BATCH_FRAMES));
      }
      const take = Math.min(frames - offset, CAPTURE_BATCH_FRAMES - this.filled);
      for (let channel = 0; channel < this.batch.length; channel += 1) {
        const data = input[channel] ?? input[0];
        this.batch[channel].set(data.subarray(offset, offset + take), this.filled);
      }
      this.filled += take;
      offset += take;
      if (this.filled === CAPTURE_BATCH_FRAMES) {
        let peak = 0;
        for (const channel of this.batch) {
          for (const value of channel) {
            const magnitude = Math.abs(value);
            if (magnitude > peak) { peak = magnitude; }
          }
        }
        this.port.postMessage(
          {channels: this.batch, peak},
          this.batch.map((channel) => channel.buffer));
        this.batch = null;
        this.filled = 0;
      }
    }
    return true;
  }
}
registerProcessor("lmdj-capture-recorder", LmdjCaptureRecorder);
