const WRITE_INDEX = 0;
const READ_INDEX = 1;
const ACK_COUNT = 2;
const PROCESS_CALLS = 3;
const LAST_QUANTUM = 4;

const SOURCE_OFFSET = 0;
const NOTE_OFFSET = 1;
const VELOCITY_OFFSET = 2;

const WASM_BYTES = Uint8Array.from([
  0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
  0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7f,
  0x03, 0x02, 0x01, 0x00,
  0x07, 0x09, 0x01, 0x05, 0x6c, 0x65, 0x76, 0x65, 0x6c, 0x00, 0x00,
  0x0a, 0x06, 0x01, 0x04, 0x00, 0x41, 0x01, 0x0b,
]);


class RuntimeProbeProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const {
      control,
      headerLength,
      ringCapacity,
      recordLength,
    } = options.processorOptions;
    this.control = new Int32Array(control);
    this.headerLength = headerLength;
    this.ringCapacity = ringCapacity;
    this.recordLength = recordLength;
    this.phase = 0;
    this.remainingFrames = 0;
    this.processorCalls = 0;

    const module = new WebAssembly.Module(WASM_BYTES);
    this.wasm = new WebAssembly.Instance(module);
    this.port.postMessage({ type: "wasm-ready" });
  }

  process(_inputs, outputs) {
    if (!outputs[0] || !outputs[0][0]) {
      return true;
    }

    const quantumSize = outputs[0][0].length;
    const wasmLevel = this.wasm.exports.level();
    this.processorCalls += 1;
    Atomics.store(this.control, PROCESS_CALLS, this.processorCalls);
    Atomics.store(this.control, LAST_QUANTUM, quantumSize);

    const writeIndex = Atomics.load(this.control, WRITE_INDEX);
    let readIndex = Atomics.load(this.control, READ_INDEX);
    while (readIndex < writeIndex) {
      const recordOffset = this.headerLength
        + (readIndex % this.ringCapacity) * this.recordLength;
      const source = Atomics.load(
        this.control,
        recordOffset + SOURCE_OFFSET,
      );
      const note = Atomics.load(this.control, recordOffset + NOTE_OFFSET);
      const velocity = Atomics.load(
        this.control,
        recordOffset + VELOCITY_OFFSET,
      );
      const sequence = readIndex + 1;

      this.phase = 0;
      this.remainingFrames = Math.ceil(sampleRate * 0.025);
      this.port.postMessage({
        type: "acknowledgement",
        sequence,
        source,
        note,
        velocity,
        renderFrame: currentFrame,
        contextTime: currentTime,
        quantumSize,
        processorCalls: this.processorCalls,
      });

      readIndex += 1;
      Atomics.store(this.control, READ_INDEX, readIndex);
      Atomics.add(this.control, ACK_COUNT, 1);
    }

    const firstChannel = outputs[0][0];
    const gain = 0.12 * wasmLevel;
    const phaseStep = (2 * Math.PI * 880) / sampleRate;
    for (let frame = 0; frame < quantumSize; frame += 1) {
      let value = 0;
      if (this.remainingFrames > 0) {
        value = Math.sin(this.phase) * gain;
        this.phase += phaseStep;
        this.remainingFrames -= 1;
      }
      firstChannel[frame] = Math.min(0.15, Math.max(-0.15, value));
    }
    for (let channel = 1; channel < outputs[0].length; channel += 1) {
      outputs[0][channel].set(firstChannel);
    }
    return true;
  }
}


registerProcessor("lmdj-web-runtime-probe", RuntimeProbeProcessor);
