// Same-origin distribution asset. Creator's hardened script-src rejects
// blob:/data: AudioWorklet module URLs.
const PERFORM_BATCH_FRAMES = 4800;

class LmdjPerformMasterTap extends AudioWorkletProcessor {
  constructor() {
    super();
    this.batch = null;
    this.filled = 0;
    this.recording = true;
    this.port.onmessage = (event) => {
      if (event.data && event.data.type === "stop") this.stopRecording();
    };
  }

  process(inputs, outputs) {
    const input = inputs[0];
    const output = outputs[0];
    if (!input || input.length === 0) return true;
    const left = input[0];
    const right = input[1] || left;
    if (!left) return true;

    // The node is transparent to the render graph. Recording failures are
    // deliberately one-way: process() never waits for or receives writer state.
    if (output) {
      if (output[0]) output[0].set(left.subarray(0, output[0].length));
      if (output[1]) output[1].set(right.subarray(0, output[1].length));
    }
    if (!this.recording) return true;

    let offset = 0;
    while (offset < left.length) {
      if (this.batch === null) {
        this.batch = [
          new Float32Array(PERFORM_BATCH_FRAMES),
          new Float32Array(PERFORM_BATCH_FRAMES),
        ];
      }
      const take = Math.min(
        left.length - offset,
        PERFORM_BATCH_FRAMES - this.filled,
      );
      this.batch[0].set(left.subarray(offset, offset + take), this.filled);
      this.batch[1].set(right.subarray(offset, offset + take), this.filled);
      this.filled += take;
      offset += take;
      if (this.filled === PERFORM_BATCH_FRAMES) {
        if (!this.postBatch()) return true;
      }
    }
    return true;
  }

  postBatch() {
    const frames = this.filled;
    const channels = frames === PERFORM_BATCH_FRAMES
      ? this.batch
      : this.batch.map((channel) => channel.slice(0, frames));
    try {
      this.port.postMessage(
        {type: "batch", channels},
        channels.map((channel) => channel.buffer),
      );
      this.batch = null;
      this.filled = 0;
      return true;
    } catch {
      this.recording = false;
      this.batch = null;
      this.filled = 0;
      try {
        this.port.postMessage({
          type: "failed",
          reason: "post-message-failed",
          droppedFrames: frames,
        });
      } catch {
        // The Host channel itself is unavailable. Render must still continue.
      }
      return false;
    }
  }

  stopRecording() {
    if (!this.recording) return;
    this.recording = false;
    if (this.filled > 0 && !this.postBatch()) return;
    try {
      this.port.postMessage({type: "stopped"});
    } catch {
      try {
        this.port.postMessage({
          type: "failed",
          reason: "post-message-failed",
          droppedFrames: 0,
        });
      } catch {
        // The Host channel itself is unavailable. Render must still continue.
      }
    }
  }
}

registerProcessor("lmdj-perform-master-tap", LmdjPerformMasterTap);
