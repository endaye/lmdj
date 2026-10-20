import {mkdtemp, rm, writeFile} from "node:fs/promises";
import {basename, join} from "node:path";

const PROCESSOR = "lmdj-tempo-onset-observer";
const SOURCE = `
class TempoOnsetObserver extends AudioWorkletProcessor {
  constructor() {
    super();
    this.onsets = [];
    this.active = false;
    this.throughFrame = 0;
    this.pending = [];
    this.failure = null;
    this.port.onmessage = ({data}) => {
      this.pending.push(data);
      this.reply();
    };
  }
  reply() {
    this.pending = this.pending.filter(request => {
      if (this.failure === null && this.throughFrame < request.throughFrame) return true;
      this.port.postMessage({id: request.id, throughFrame: this.throughFrame,
        onsets: this.onsets.slice(), error: this.failure});
      return false;
    });
  }
  process(inputs, outputs) {
    for (const output of outputs) for (const channel of output) channel.fill(0);
    const channels = inputs[0];
    const frames = channels[0]?.length ?? 0;
    if (frames !== 0) {
      if (this.throughFrame !== 0 && currentFrame !== this.throughFrame)
        this.failure = "non-contiguous observer callbacks";
      for (let index = 0; index < frames; ++index) {
        const active = channels.some(channel => Math.abs(channel[index]) > 1e-9);
        if (active && !this.active) this.onsets.push(currentFrame + index);
        this.active = active;
      }
      this.throughFrame = currentFrame + frames;
      if (this.onsets.length > 4096) this.failure = "observer capacity exhausted";
    }
    this.reply();
    return true;
  }
}
registerProcessor(${JSON.stringify(PROCESSOR)}, TempoOnsetObserver);
`;

export async function attachTempoOnsetProbe(page) {
  // A real same-origin Worklet fetch does not pass through page.route.
  // The unique owned module adds only a silent, downstream observation branch.
  const directory = await mkdtemp(new URL(
    "../../../../build/web/toolchain/lmdj-tempo-onset-", import.meta.url,
  ));
  try {
    await writeFile(join(directory, "probe.js"), SOURCE);
    await page.evaluate(async ({url, processor}) => {
      const destination = window.__lmdjTempoSession.monitorDestination();
      const context = destination.context;
      await context.audioWorklet.addModule(url);
      const node = new AudioWorkletNode(context, processor, {
        numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
        channelCount: 2, channelCountMode: "explicit",
      });
      const pending = new Map();
      let sequence = 0;
      node.port.onmessage = ({data}) => {
        const request = pending.get(data.id);
        if (!request) return;
        pending.delete(data.id); clearTimeout(request.timer);
        if (data.error) request.reject(new Error(data.error));
        else request.resolve(data);
      };
      destination.connect(node);
      node.connect(context.destination);
      window.__lmdjTempoOnsetProbe = {
        readThrough(throughFrame) {
          return new Promise((resolve, reject) => {
            const id = ++sequence;
            const timer = setTimeout(() => {
              pending.delete(id);
              reject(new Error(`Actual PCM did not reach context frame ${throughFrame}`));
            }, 5_000);
            pending.set(id, {resolve, reject, timer});
            node.port.postMessage({id, throughFrame});
          });
        },
        close() {
          for (const request of pending.values()) {
            clearTimeout(request.timer); request.reject(new Error("PCM observer closed"));
          }
          pending.clear(); destination.disconnect(node); node.disconnect(); node.port.close();
          delete window.__lmdjTempoOnsetProbe;
        },
      };
    }, {url: new URL(`/${basename(directory)}/probe.js`, page.url()).href, processor: PROCESSOR});
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
}

// Independent arithmetic: one quarter is960 ticks, each tick numerator has
// denominator60*48000. Do not import an Engine/SDK scheduling helper.
export function nextTempoQuarterFrames(anchor, count = 1, afterFrame = anchor.frame) {
  const quarter = 960n * 60n * 48_000n;
  const frame = BigInt(anchor.frame), tick = BigInt(anchor.tickNumerator);
  const slope = BigInt(anchor.bpm) * 960n;
  const cursor = BigInt(afterFrame) > frame ? BigInt(afterFrame) : frame;
  const cursorTick = tick + (cursor - frame) * slope;
  let target = (cursorTick / quarter + 1n) * quarter;
  return Array.from({length: count}, () => {
    const result = frame + (target - tick + slope - 1n) / slope;
    target += quarter;
    return result;
  });
}
