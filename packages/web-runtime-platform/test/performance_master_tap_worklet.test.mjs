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

async function loadMasterTapProcessor({postMessage, sampleRate = 48_000, currentFrame = 0} = {}) {
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
  const clock = {
    AudioWorkletProcessor: StubAudioWorkletProcessor,
    Float32Array,
    Number,
    sampleRate,
    currentFrame,
    registerProcessor(name, constructor) {
      assert.equal(name, "lmdj-perform-master-tap");
      Processor = constructor;
    },
  };
  vm.runInNewContext(source, clock, {filename: PROCESSOR_PATH});
  assert.notEqual(Processor, null);
  return {Processor, messages, clock};
}

const METER_A = "10000000-0000-4000-8000-000000000001";
const METER_B = "10000000-0000-4000-8000-000000000002";

function renderMeterQuanta(processor, clock, quanta, sample = () => [0, 0]) {
  for (let quantum = 0; quantum < quanta; quantum += 1) {
    const input = [new Float32Array(128), new Float32Array(128)];
    for (let frame = 0; frame < 128; frame += 1) {
      const values = sample(clock.currentFrame + frame);
      input[0][frame] = values[0];
      input[1][frame] = values[1];
    }
    const output = [new Float32Array(128), new Float32Array(128)];
    assert.equal(processor.process([input], [output]), true);
    assert.deepEqual(output, input, "meter must retain transparent stereo output");
    clock.currentFrame += 128;
  }
}

function ackMeter(processor, message) {
  processor.port.onmessage({data: {type: "meter-ack", owner: message.owner,
    windowEndFrame: message.windowEndFrame}});
}

test("inactive capture retains independent one-frame peaks anywhere in the full meter window", async () => {
  const {Processor, messages, clock} = await loadMasterTapProcessor();
  const processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  renderMeterQuanta(processor, clock, 19, frame => [frame === 257 ? -0.5 : 0, frame === 2387 ? 1 : 0]);
  assert.deepEqual(messages.map(value => ({...value})), [{
    type: "meter", owner: METER_A, sampleRate: 48_000,
    windowStartFrame: "0", windowEndFrame: "2400",
    leftPeak: 0.5, rightPeak: 1, leftPeakFrame: "257", rightPeakFrame: "2387",
    renderQuantumFrames: 128,
  }]);
  ackMeter(processor, messages[0]);
  renderMeterQuanta(processor, clock, 19);
  assert.equal(messages[1].leftPeak, 0);
  assert.equal(messages[1].rightPeak, 0);
  assert.equal(messages[1].leftPeakFrame, "4799");
  assert.equal(messages[1].windowStartFrame, "2400");
  assert.equal(processor.generation, null);
});

test("one in-flight meter coalesces every pending frame until its exact ACK", async () => {
  const {Processor, messages, clock} = await loadMasterTapProcessor();
  const processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  renderMeterQuanta(processor, clock, 188, frame => [frame === 12800 ? 1.25 : 0, frame === 23999 ? -0.75 : 0]);
  assert.equal(messages.length, 1, "Main delay cannot queue all meter windows");
  ackMeter(processor, messages[0]);
  renderMeterQuanta(processor, clock, 19);
  assert.equal(messages.length, 2);
  assert.deepEqual({...messages[1]}, {
    type: "meter", owner: METER_A, sampleRate: 48_000,
    windowStartFrame: "2400", windowEndFrame: "26400",
    leftPeak: 1.25, rightPeak: 0.75, leftPeakFrame: "12800", rightPeakFrame: "23999",
    renderQuantumFrames: 128,
  });
});

test("owner replacement retains the old queued token and duplicate old ACK cannot release a new one", async () => {
  const {Processor, messages, clock} = await loadMasterTapProcessor();
  const processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  renderMeterQuanta(processor, clock, 19);
  const old = messages[0];
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_B}});
  renderMeterQuanta(processor, clock, 19);
  assert.equal(messages.length, 1);
  ackMeter(processor, old);
  renderMeterQuanta(processor, clock, 19);
  assert.equal(messages.length, 2);
  assert.equal(messages[1].owner, METER_B);
  assert.equal(messages[1].windowStartFrame, "2432");
  ackMeter(processor, old);
  renderMeterQuanta(processor, clock, 19);
  assert.equal(messages.length, 2, "a duplicate old token cannot drain the new packet");
});

test("meter emits at most twenty full windows per rendered second with immediate ACK", async () => {
  const observed = [];
  let processor;
  const {Processor, clock} = await loadMasterTapProcessor({postMessage(message) {
    observed.push(message);
    if (message.type === "meter") ackMeter(processor, message);
  }});
  processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  renderMeterQuanta(processor, clock, 375);
  assert.equal(observed.length, 20);
  assert.equal(observed[0].windowEndFrame, "2400");
  assert.equal(observed.at(-1).windowEndFrame, "48000");
});

test("actual 44.1 kHz windows duplicate mono and then observe rendered missing-input silence", async () => {
  const observed = [];
  let processor;
  const {Processor, clock} = await loadMasterTapProcessor({sampleRate: 44_100, postMessage(message) {
    observed.push(message);
    if (message.type === "meter") ackMeter(processor, message);
  }});
  processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  for (let quantum = 0; quantum < 53; quantum += 1) {
    const mono = new Float32Array(128).fill(0.75);
    const input = quantum < 18 ? [mono] : [];
    const output = [new Float32Array(128), new Float32Array(128)];
    assert.equal(processor.process([input], [output]), true);
    assert.deepEqual(output, quantum < 18 ? [mono, mono] : [new Float32Array(128), new Float32Array(128)]);
    clock.currentFrame += 128;
  }
  assert.deepEqual(observed.map(({sampleRate, windowEndFrame, leftPeak, rightPeak}) =>
    [sampleRate, windowEndFrame, leftPeak, rightPeak]), [
    [44_100, "2205", 0.75, 0.75], [44_100, "4410", 0.75, 0.75], [44_100, "6615", 0, 0],
  ]);
  assert.equal(observed[2].leftPeakFrame, "6614");
  assert.equal(observed[2].rightPeakFrame, "6614");
});

test("unsafe meter clock reports unavailable without stopping capture or transparent rendering", async () => {
  const {Processor, messages, clock} = await loadMasterTapProcessor({currentFrame: Number.MAX_SAFE_INTEGER - 127});
  const processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  processor.port.onmessage({data: {type: "start", generation: 7, binding: null}});
  assert.deepEqual({...messages.shift()}, {type: "started", generation: 7, binding: null});
  renderMeterQuanta(processor, clock, 1, () => [0.25, -0.5]);
  processor.port.onmessage({data: {type: "stop", generation: 7}});
  assert.deepEqual({...messages[0]}, {type: "meter-unavailable", owner: METER_A, reason: "clock-invalid"});
  assert.equal(messages[1].type, "batch");
  assert.equal(messages[1].generation, 7);
  assert.equal(messages[1].sequence, 1);
  assert.equal(messages[1].channels[0].length, 128);
  assert.deepEqual({...messages[2]}, {type: "stopped", generation: 7, finalSequence: 1});
});

test("a nonfinite meter sample is unavailable once per owner rather than invented silence", async () => {
  const {Processor, messages, clock} = await loadMasterTapProcessor();
  const processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  renderMeterQuanta(processor, clock, 1, frame => [frame === 0 ? NaN : 0, 0]);
  renderMeterQuanta(processor, clock, 38);
  assert.deepEqual(messages.map(value => ({...value})), [{type: "meter-unavailable", owner: METER_A, reason: "non-finite-sample"}]);
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_B}});
  renderMeterQuanta(processor, clock, 19);
  assert.equal(messages[1].type, "meter");
  assert.equal(messages[1].owner, METER_B);
});

test("meter delivery failure preserves capture batches and stop acknowledgement", async () => {
  const observed = [];
  const {Processor, clock} = await loadMasterTapProcessor({postMessage(message) {
    if (message.type === "meter") throw new Error("meter delivery failed");
    observed.push(message);
  }});
  const processor = new Processor();
  processor.port.onmessage({data: {type: "meter-owner", owner: METER_A}});
  processor.port.onmessage({data: {type: "start", generation: 1, binding: null}});
  assert.deepEqual({...observed.shift()}, {type: "started", generation: 1, binding: null});
  renderMeterQuanta(processor, clock, 38, () => [0.25, -0.5]);
  processor.port.onmessage({data: {type: "stop", generation: 1}});
  assert.deepEqual(observed.map(value => value.type), ["meter-unavailable", "batch", "batch", "stopped"]);
  assert.equal(observed[1].channels[0].length, 4800);
  assert.equal(observed[2].channels[0].length, 64);
  assert.deepEqual(observed.filter(value => value.type === "batch").map(value => [value.generation, value.sequence]), [[1, 1], [1, 2]]);
  assert.deepEqual({...observed[3]}, {type: "stopped", generation: 1, finalSequence: 2});
});

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

  // The worklet acknowledges the applied start before the next process().
  processor.port.onmessage({data: {type: "start", generation: 7, binding: null}});
  assert.deepEqual({...messages.at(-1)}, {
    type: "started", generation: 7, binding: null,
  });
  processor.process([input], [output]);
  assert.deepEqual(
    {...messages.at(-1), channels: [...messages.at(-1).channels]},
    {type: "batch", generation: 7, sequence: 1, channels: input},
  );
  processor.port.onmessage({data: {type: "stop", generation: 6}});
  assert.equal(messages.length, 2);
  processor.port.onmessage({data: {type: "stop", generation: 7}});
  assert.deepEqual({...messages.at(-1)}, {
    type: "stopped", generation: 7, finalSequence: 1,
  });

  processor.port.onmessage({data: {type: "start", generation: 8, binding: null}});
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
      if (attempts === 2) throw new Error("post failed");
      messages.push(message);
    },
  });
  const processor = new Processor();
  const input = [
    new Float32Array(4_800).fill(0.25),
    new Float32Array(4_800).fill(-0.5),
  ];
  const output = [new Float32Array(4_800), new Float32Array(4_800)];
  processor.port.onmessage({data: {type: "start", generation: 9, binding: null}});
  assert.deepEqual({...messages.at(-1)}, {
    type: "started", generation: 9, binding: null,
  });

  assert.doesNotThrow(() => processor.process([input], [output]));
  assert.deepEqual(output, input);
  assert.deepEqual(messages.map((message) => ({...message})), [{
    type: "started",
    generation: 9,
    binding: null,
  }, {
    type: "failed",
    generation: 9,
    reason: "post-message-failed",
    droppedFrames: 4_800,
  }]);
  assert.equal(processor.process([input], [output]), true);
  assert.equal(attempts, 3);
});

test("accepts only exact nonnegative safe-integer control messages", async () => {
  const {Processor, messages} = await loadMasterTapProcessor();
  const processor = new Processor();
  for (const data of [
    null,
    {type: "start", generation: 1, extra: true},
    {type: "start", generation: 1},
    {type: "start", generation: 1, binding: {}},
    {type: "start", generation: 1, binding: {control_epoch: "nope"}},
    {type: "start", generation: -1, binding: null},
    {type: "start", generation: Number.MAX_SAFE_INTEGER + 1, binding: null},
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
  processor.port.onmessage({data: {type: "start", generation: 7, binding: null}});
  const started = messages.at(-1);
  processor.process([input], [output]);
  for (const data of [
    {type: "start", generation: 7, extra: true},
    {type: "stop", generation: -1},
    {type: "stop", generation: Number.MAX_SAFE_INTEGER + 1},
    {type: "stop", generation: 7, extra: true},
  ]) {
    processor.port.onmessage({data});
  }
  // The invalid loop added nothing: only the started ACK is in the log.
  assert.equal(messages.length, 1);

  processor.port.onmessage({data: {type: "stop", generation: 7}});
  assert.deepEqual({...started}, {
    type: "started", generation: 7, binding: null,
  });
  assert.deepEqual({
    ...messages.at(-2), channels: [...messages.at(-2).channels],
  }, {
    type: "batch",
    generation: 7,
    sequence: 1,
    channels: input,
  });
  assert.deepEqual({...messages.at(-1)}, {
    type: "stopped", generation: 7, finalSequence: 1,
  });
});

test("reports a stopped acknowledgement delivery failure exactly", async () => {
  const messages = [];
  let attempts = 0;
  const {Processor} = await loadMasterTapProcessor({
    postMessage(message) {
      attempts += 1;
      if (attempts === 2) throw new Error("stopped delivery failed");
      messages.push(message);
    },
  });
  const processor = new Processor();
  processor.port.onmessage({data: {type: "start", generation: 11, binding: null}});

  assert.doesNotThrow(() => processor.port.onmessage({
    data: {type: "stop", generation: 11},
  }));
  assert.equal(attempts, 3);
  assert.deepEqual({...messages[0]}, {
    type: "started",
    generation: 11,
    binding: null,
  });
  assert.deepEqual({...messages[1]}, {
    type: "failed",
    generation: 11,
    reason: "post-message-failed",
    droppedFrames: 0,
  });
});
