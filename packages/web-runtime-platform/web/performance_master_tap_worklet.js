const PERFORM_BATCH_FRAMES = 4_800;

// D0/W1: the start handshake carries the begin binding
// `{control_epoch, session_id, begin_command_id}` (null only for a legacy
// non-D04 caller) and the worklet answers `started` after actually applying
// it, before the next process().
function validTapBinding(binding) {
  if (binding === null) return true;
  if (binding === undefined || typeof binding !== "object") return false;
  const keys = Object.keys(binding).sort();
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  return keys.length === 3 &&
    keys[0] === "begin_command_id" && keys[1] === "control_epoch" &&
    keys[2] === "session_id" &&
    uuid.test(binding.begin_command_id) &&
    uuid.test(binding.control_epoch) && uuid.test(binding.session_id);
}

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
  if (type === "start") {
    return keys.length === 3 &&
      keys[0] === "binding" && keys[1] === "generation" && keys[2] === "type" &&
      validTapBinding(data.binding);
  }
  return keys.length === 2 &&
    keys[0] === "generation" && keys[1] === "type";
}

class PerformanceMasterTapProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.generation = null;
    this.binding = null;
    this.sequence = 0;
    this.frames = 0;
    this.left = new Float32Array(PERFORM_BATCH_FRAMES);
    this.right = new Float32Array(PERFORM_BATCH_FRAMES);
    this.port.onmessage = ({data}) => {
      if (isExactControlMessage(data, "start")) {
        this.generation = data.generation;
        this.binding = data.binding ?? null;
        this.sequence = 0;
        this.frames = 0;
        // The start is applied: acknowledge before the next process() so the
        // controller never treats a posted-but-unhandled start as armed.
        try {
          this.port.postMessage({
            type: "started",
            generation: this.generation,
            binding: this.binding,
          });
        } catch {
          this.generation = null;
          this.binding = null;
        }
      } else if (
        isExactControlMessage(data, "stop") &&
        this.generation !== null &&
        data.generation === this.generation
      ) {
        const generation = this.generation;
        if (!this.flush()) return;
        this.generation = null;
        this.binding = null;
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

// GLM large-input latency canary: comment-only; close this PR unmerged.
