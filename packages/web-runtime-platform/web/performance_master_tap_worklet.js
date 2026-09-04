const PERFORM_BATCH_FRAMES = 4_800;

function isExactControlMessage(data, type) {
  if (
    data === null ||
    typeof data !== "object" ||
    data.type !== type ||
    !Number.isSafeInteger(data.generation) ||
    data.generation < 0
  ) {
    return false;
  }
  const keys = Object.keys(data).sort();
  return keys.length === 2 &&
    keys[0] === "generation" && keys[1] === "type";
}

class PerformanceMasterTapProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.generation = null;
    this.sequence = 0;
    this.frames = 0;
    this.left = new Float32Array(PERFORM_BATCH_FRAMES);
    this.right = new Float32Array(PERFORM_BATCH_FRAMES);
    this.port.onmessage = ({data}) => {
      if (isExactControlMessage(data, "start")) {
        this.generation = data.generation;
        this.sequence = 0;
        this.frames = 0;
      } else if (
        isExactControlMessage(data, "stop") &&
        this.generation !== null &&
        data.generation === this.generation
      ) {
        const generation = this.generation;
        if (!this.flush()) return;
        this.generation = null;
        try {
          this.port.postMessage({
            type: "stopped",
            generation,
            finalSequence: this.sequence,
          });
        } catch {
          try {
            this.port.postMessage({
              type: "failed",
              generation,
              reason: "post-message-failed",
              droppedFrames: 0,
            });
          } catch {}
        }
      }
    };
  }

  flush() {
    if (this.generation === null || this.frames === 0) return true;
    const generation = this.generation;
    const droppedFrames = this.frames;
    const channels = [
      this.left.slice(0, this.frames),
      this.right.slice(0, this.frames),
    ];
    this.sequence += 1;
    this.frames = 0;
    try {
      this.port.postMessage({
        type: "batch",
        generation,
        sequence: this.sequence,
        channels,
      });
      return true;
    } catch {
      this.generation = null;
      try {
        this.port.postMessage({
          type: "failed",
          generation,
          reason: "post-message-failed",
          droppedFrames,
        });
      } catch {}
      return false;
    }
  }

  process(inputs, outputs) {
    const input = inputs[0] ?? [];
    const output = outputs[0] ?? [];
    const frames = output[0]?.length ?? 0;
    for (let channel = 0; channel < 2; channel += 1) {
      const source = input[channel] ?? input[0];
      if (source && output[channel]) output[channel].set(source);
    }
    if (this.generation === null) return true;
    for (let frame = 0; frame < frames; frame += 1) {
      this.left[this.frames] = input[0]?.[frame] ?? 0;
      this.right[this.frames] = input[1]?.[frame] ?? input[0]?.[frame] ?? 0;
      this.frames += 1;
      if (this.frames === PERFORM_BATCH_FRAMES && !this.flush()) break;
    }
    return true;
  }
}

registerProcessor("lmdj-perform-master-tap", PerformanceMasterTapProcessor);
