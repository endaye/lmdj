export const CAPTURE_WORKLET_NAME = "lmdj-capture-recorder";
export const CAPTURE_BATCH_FRAMES = 4_800;

export const CAPTURE_WORKLET_SOURCE = `
class LmdjCaptureRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.batch = null;
    this.filled = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) { return true; }
    const frames = input[0].length;
    let offset = 0;
    while (offset < frames) {
      // Allocate inside the loop: a quantum that crosses a batch boundary
      // posts (and nulls) the batch mid-loop, then keeps writing.
      if (this.batch === null) {
        this.batch = input.map(() => new Float32Array(${CAPTURE_BATCH_FRAMES}));
      }
      const take = Math.min(frames - offset, ${CAPTURE_BATCH_FRAMES} - this.filled);
      for (let channel = 0; channel < this.batch.length; channel += 1) {
        const data = input[channel] ?? input[0];
        this.batch[channel].set(data.subarray(offset, offset + take), this.filled);
      }
      this.filled += take;
      offset += take;
      if (this.filled === ${CAPTURE_BATCH_FRAMES}) {
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
registerProcessor("${CAPTURE_WORKLET_NAME}", LmdjCaptureRecorder);
`;
