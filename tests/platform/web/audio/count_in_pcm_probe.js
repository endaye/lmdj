// Proof-only observer. It never creates a musical signal or schedules a cue.
// Inputs are the real product output, real cue output and actual monitor bus;
// its sole output is silence, so observation adds no audible route.
class CountInPcmProbe extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const {header, samples, capacity} = options.processorOptions;
    this.header = new Int32Array(header);
    this.samples = new Float32Array(samples);
    this.capacity = capacity;
    this.port.onmessage = ({data}) => {
      if (data === "arm") {
        Atomics.store(this.header, 1, -1);
        Atomics.store(this.header, 2, 0);
        Atomics.store(this.header, 3, 0);
        Atomics.store(this.header, 0, 1);
        this.port.postMessage({type: "armed"});
      } else if (data === "freeze") {
        Atomics.store(this.header, 0, 0);
        this.port.postMessage({type: "frozen"});
      }
    };
  }

  process(inputs, outputs) {
    for (let output = 0; output < outputs.length; ++output) {
      for (let channel = 0; channel < outputs[output].length; ++channel) {
        outputs[output][channel].fill(0);
      }
    }
    if (Atomics.load(this.header, 0) !== 1) return true;
    const count = outputs[0][0].length;
    const written = Atomics.load(this.header, 2);
    if (written + count > this.capacity || currentFrame > 0x7fffffff) {
      Atomics.store(this.header, 3, 1);
      Atomics.store(this.header, 0, 0);
      return true;
    }
    const first = Atomics.load(this.header, 1);
    if (first < 0) Atomics.store(this.header, 1, currentFrame);
    else if (currentFrame !== first + written) {
      Atomics.store(this.header, 3, 2);
      Atomics.store(this.header, 0, 0);
      return true;
    }
    for (let input = 0; input < 3; ++input) {
      for (let channel = 0; channel < 2; ++channel) {
        const source = inputs[input]?.[channel];
        if (source !== undefined && source.length !== count) {
          Atomics.store(this.header, 3, 3);
          Atomics.store(this.header, 0, 0);
          return true;
        }
        const offset = (input * 2 + channel) * this.capacity + written;
        for (let frame = 0; frame < count; ++frame) {
          this.samples[offset + frame] = source?.[frame] ?? 0;
        }
      }
    }
    // Release publishes all six aligned channels; the reader freezes first.
    Atomics.store(this.header, 2, written + count);
    return true;
  }
}

registerProcessor("lmdj-count-in-pcm-probe", CountInPcmProbe);
