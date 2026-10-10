import {mkdtemp, rm, writeFile} from "node:fs/promises";
import {basename, join} from "node:path";

const PROCESSOR_NAME = "lmdj-paired-energy-probe";
const PROCESSOR_SOURCE = `
class PairedEnergyProbe extends AudioWorkletProcessor {
  constructor() {
    super();
    this.pending = null;
    this.port.onmessage = ({data}) => {
      this.pending = {...data, firstFrame: null, frames: 0, master: 0, output: 0};
    };
  }

  process(inputs, outputs) {
    // Pull both observation inputs without creating another audible route.
    for (const output of outputs) {
      for (const channel of output) channel.fill(0);
    }
    const pending = this.pending;
    if (pending === null || currentFrame < pending.afterFrame) return true;
    const master = inputs[0];
    const output = inputs[1];
    const frames = master[0]?.length ?? 0;
    if (frames === 0 || master.length !== output.length ||
        [...master, ...output].some(channel => channel.length !== frames) ||
        pending.frames + frames > pending.frameCount ||
        (pending.firstFrame !== null &&
         currentFrame !== pending.firstFrame + pending.frames)) {
      this.port.postMessage({error: "incomplete or unaligned observation inputs"});
      this.pending = null;
      return true;
    }
    pending.firstFrame ??= currentFrame;
    for (let channel = 0; channel < master.length; ++channel) {
      for (let frame = 0; frame < frames; ++frame) {
        pending.master += master[channel][frame] * master[channel][frame];
        pending.output += output[channel][frame] * output[channel][frame];
      }
    }
    pending.frames += frames;
    if (pending.frames === pending.frameCount) {
      this.port.postMessage({master: pending.master, output: pending.output,
        firstFrame: pending.firstFrame, frames: pending.frames});
      this.pending = null;
    }
    return true;
  }
}
registerProcessor(${JSON.stringify(PROCESSOR_NAME)}, PairedEnergyProbe);
`;

export async function attachPairedEnergyProbe(page) {
  // Serve only this test observer from the owned origin; the Host's CSP,
  // production requests, Core, signal and gain remain real and unchanged.
  // Worklet fetches do not pass through page.route. Give the existing proof
  // server a unique static module, then remove only that owned directory.
  const directory = await mkdtemp(new URL(
    "../../../../build/web/toolchain/lmdj-paired-energy-", import.meta.url,
  ));
  const moduleURL = new URL(`/${basename(directory)}/probe.js`, page.url()).href;
  try {
    await writeFile(join(directory, "probe.js"), PROCESSOR_SOURCE);
    await page.evaluate(async ({moduleURL, processorName}) => {
      const {context, analyser, monitorAnalyser} = window.__lmdjFormalAudioGraph;
      await context.audioWorklet.addModule(moduleURL);
      const node = new AudioWorkletNode(context, processorName, {
        numberOfInputs: 2, numberOfOutputs: 1, outputChannelCount: [1],
        channelCount: 2, channelCountMode: "explicit",
      });
      analyser.connect(node, 0, 0);
      monitorAnalyser.connect(node, 0, 1);
      node.connect(context.destination);
      window.__lmdjPairedEnergyProbe = {
        read({frameCount, afterFrame}) {
          return new Promise((resolve, reject) => {
            node.port.onmessage = ({data}) => {
              node.port.onmessage = null;
              if (data.error) reject(new Error(data.error));
              else resolve(data);
            };
            node.port.postMessage({frameCount, afterFrame});
          });
        },
        close() {
          analyser.disconnect(node);
          monitorAnalyser.disconnect(node);
          node.disconnect();
          node.port.close();
          delete window.__lmdjPairedEnergyProbe;
        },
      };
    }, {moduleURL, processorName: PROCESSOR_NAME});
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
}
