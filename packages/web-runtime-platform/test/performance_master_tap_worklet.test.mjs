import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import {fileURLToPath} from "node:url";

const PROCESSOR_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../web/performance_master_tap_worklet.js",
);

async function loadMasterTapProcessor({postMessage} = {}) {
  const source = await readFile(PROCESSOR_PATH, "utf8");
  const messages = [];
  let Processor = null;
  class StubAudioWorkletProcessor {
    constructor() {
      this.port = {
        onmessage: null,
        postMessage(message) {
          if (postMessage) postMessage(message);
          else messages.push(message);
        },
      };
    }
  }
  vm.runInNewContext(source, {
    AudioWorkletProcessor: StubAudioWorkletProcessor,
    Float32Array,
    Number,
    registerProcessor(name, constructor) {
      assert.equal(name, "lmdj-perform-master-tap");
      Processor = constructor;
    },
  }, {filename: PROCESSOR_PATH});
  assert.notEqual(Processor, null);
  return {Processor, messages};
}

test("processor is idle until start and isolates serial generations", async () => {
  const {Processor, messages} = await loadMasterTapProcessor();
  const processor = new Processor();
  const input = [
    new Float32Array(4_800).fill(0.25),
    new Float32Array(4_800).fill(-0.5),
  ];
  const output = [new Float32Array(4_800), new Float32Array(4_800)];

  assert.equal(processor.process([input], [output]), true);
  assert.deepEqual(output, input);
  assert.deepEqual(messages, []);

  processor.port.onmessage({data: {type: "start", generation: 7}});
  processor.process([input], [output]);
  assert.deepEqual(
    {...messages[0], channels: [...messages[0].channels]},
    {type: "batch", generation: 7, sequence: 1, channels: input},
  );
  processor.port.onmessage({data: {type: "stop", generation: 6}});
  assert.equal(messages.length, 1);
  processor.port.onmessage({data: {type: "stop", generation: 7}});
  assert.deepEqual({...messages.at(-1)}, {
    type: "stopped", generation: 7, finalSequence: 1,
  });

  processor.port.onmessage({data: {type: "start", generation: 8}});
  processor.process([[input[0].subarray(0, 127)]], [
    [new Float32Array(127), new Float32Array(127)],
  ]);
  processor.port.onmessage({data: {type: "stop", generation: 8}});
  assert.deepEqual({
    ...messages.at(-2),
    channels: [...messages.at(-2).channels],
  }, {
    type: "batch",
    generation: 8,
    sequence: 1,
    channels: [
      input[0].subarray(0, 127),
      input[0].subarray(0, 127),
    ],
  });
  assert.deepEqual({...messages.at(-1)}, {
    type: "stopped", generation: 8, finalSequence: 1,
  });
});

test("render remains transparent and non-throwing when batch delivery fails", async () => {
  const messages = [];
  let attempts = 0;
  const {Processor} = await loadMasterTapProcessor({
    postMessage(message) {
      attempts += 1;
      if (attempts === 1) throw new Error("post failed");
      messages.push(message);
    },
  });
  const processor = new Processor();
  const input = [
    new Float32Array(4_800).fill(0.25),
    new Float32Array(4_800).fill(-0.5),
  ];
  const output = [new Float32Array(4_800), new Float32Array(4_800)];
  processor.port.onmessage({data: {type: "start", generation: 9}});

  assert.doesNotThrow(() => processor.process([input], [output]));
  assert.deepEqual(output, input);
  assert.deepEqual(messages.map((message) => ({...message})), [{
    type: "failed",
    generation: 9,
    reason: "post-message-failed",
    droppedFrames: 4_800,
  }]);
  assert.equal(processor.process([input], [output]), true);
  assert.equal(attempts, 2);
});

test("accepts only exact nonnegative safe-integer control messages", async () => {
  const {Processor, messages} = await loadMasterTapProcessor();
  const processor = new Processor();
  for (const data of [
    null,
    {type: "start", generation: 1, extra: true},
    {type: "start", generation: -1},
    {type: "start", generation: Number.MAX_SAFE_INTEGER + 1},
    {type: "stop", generation: null},
    {type: "stop", generation: 1, extra: true},
  ]) {
    processor.port.onmessage({data});
  }
  assert.deepEqual(messages, []);

  const input = [
    new Float32Array(127).fill(0.25),
    new Float32Array(127).fill(-0.5),
  ];
  const output = [new Float32Array(127), new Float32Array(127)];
  processor.port.onmessage({data: {type: "start", generation: 7}});
  processor.process([input], [output]);
  for (const data of [
    {type: "start", generation: 7, extra: true},
    {type: "stop", generation: -1},
    {type: "stop", generation: Number.MAX_SAFE_INTEGER + 1},
    {type: "stop", generation: 7, extra: true},
  ]) {
    processor.port.onmessage({data});
  }
  assert.deepEqual(messages, []);

  processor.port.onmessage({data: {type: "stop", generation: 7}});
  assert.deepEqual({
    ...messages[0], channels: [...messages[0].channels],
  }, {
    type: "batch",
    generation: 7,
    sequence: 1,
    channels: input,
  });
  assert.deepEqual({...messages[1]}, {
    type: "stopped", generation: 7, finalSequence: 1,
  });
});

test("reports a stopped acknowledgement delivery failure exactly", async () => {
  const messages = [];
  let attempts = 0;
  const {Processor} = await loadMasterTapProcessor({
    postMessage(message) {
      attempts += 1;
      if (attempts === 1) throw new Error("stopped delivery failed");
      messages.push(message);
    },
  });
  const processor = new Processor();
  processor.port.onmessage({data: {type: "start", generation: 11}});

  assert.doesNotThrow(() => processor.port.onmessage({
    data: {type: "stop", generation: 11},
  }));
  assert.equal(attempts, 2);
  assert.deepEqual({...messages[0]}, {
    type: "failed",
    generation: 11,
    reason: "post-message-failed",
    droppedFrames: 0,
  });
});
