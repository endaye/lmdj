import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

import {createPerformanceMasterTap} from
  "../web/performance_master_capture.mjs";

class StubNode extends EventTarget {
  constructor(context, name, options) {
    super();
    this.context = context;
    this.name = name;
    this.options = options;
    this.connected = [];
    this.disconnected = [];
    this.messages = [];
    this.port = {
      onmessage: null,
      postMessage: (message) => this.messages.push(message),
    };
  }

  connect(destination) {
    this.connected.push(destination);
  }

  disconnect(destination) {
    this.disconnected.push(destination);
  }
}

async function fixture({controllerOptions, onPostMessage, monitor = false} = {}) {
  const previousLocation = globalThis.location;
  const previousNode = globalThis.AudioWorkletNode;
  const modules = [];
  const destination = {kind: "speakers"};
  const context = {
    destination,
    audioWorklet: {async addModule(url) { modules.push(url); }},
  };
  const monitorDestination = monitor ? {context, kind: "monitor-gain"} : undefined;
  let node = null;
  globalThis.location = new URL("https://example.test/creator/");
  const autoAck = controllerOptions?.autoStartAck ?? true;
  globalThis.AudioWorkletNode = class extends StubNode {
    constructor(...arguments_) {
      super(...arguments_);
      node = this;
      this.port.postMessage = (message) => {
        this.messages.push(message);
        if (autoAck && message.type === "start") {
          queueMicrotask(() => node.port.onmessage({data: {
            type: "started",
            generation: message.generation,
            binding: message.binding ?? null,
          }}));
        }
        onPostMessage?.(message, this);
      };
    }
  };
  try {
    const controller = await createPerformanceMasterTap(
      {
        context,
        processorUrl: "./perform-master-tap.js",
        ...(monitorDestination === undefined ? {} : {destination: monitorDestination}),
      },
      controllerOptions,
    );
    return {controller, context, destination: monitorDestination ?? destination, modules, node};
  } finally {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
    if (previousNode === undefined) delete globalThis.AudioWorkletNode;
    else globalThis.AudioWorkletNode = previousNode;
  }
}

async function integratedFixture() {
  const source = await readFile(path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../web/performance_master_tap_worklet.js",
  ), "utf8");
  let Processor = null;
  let hostNode = null;
  const processorMessages = [];
  class StubAudioWorkletProcessor {
    constructor() {
      this.port = {
        onmessage: null,
        postMessage(message) {
          processorMessages.push(message);
          hostNode?.port.onmessage({data: message});
        },
      };
    }
  }
  const clock = {
    AudioWorkletProcessor: StubAudioWorkletProcessor,
    Float32Array,
    Number,
    sampleRate: 48_000,
    currentFrame: 0,
    registerProcessor(name, constructor) {
      assert.equal(name, "lmdj-perform-master-tap");
      Processor = constructor;
    },
  };
  vm.runInNewContext(source, clock);
  const processor = new Processor();
  const result = await fixture({
    // The real processor answers the started ACK itself.
    controllerOptions: {autoStartAck: false},
    onPostMessage(message) {
      processor.port.onmessage({data: message});
    },
  });
  hostNode = result.node;
  return {...result, processor, processorMessages, clock};
}

const METER_A = "10000000-0000-4000-8000-000000000001";
const METER_B = "10000000-0000-4000-8000-000000000002";

function meterMessage(overrides = {}) {
  return {type: "meter", owner: METER_A, sampleRate: 48_000,
    windowStartFrame: "0", windowEndFrame: "2400", leftPeak: 0.5,
    rightPeak: 0.125, leftPeakFrame: "257", rightPeakFrame: "2387",
    renderQuantumFrames: 128, ...overrides};
}

test("inactive capture accepts an immutable meter and acknowledges its exact audio window", async () => {
  const {controller, node} = await fixture();
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "pending"});
  assert.equal(controller.setMeterOwner(METER_A), true);
  assert.deepEqual(node.messages, [{type: "meter-owner", owner: METER_A}]);
  node.port.onmessage({data: meterMessage()});
  const measurement = controller.meterMeasurement();
  const {type: _, ...expected} = meterMessage();
  assert.deepEqual(measurement, {state: "available", ...expected});
  assert.equal(Object.isFrozen(measurement), true);
  assert.deepEqual(node.messages.at(-1), {type: "meter-ack", owner: METER_A, windowEndFrame: "2400"});
  assert.equal(controller.setMeterOwner(METER_A), true);
  assert.equal(node.messages.length, 2);
  await controller.close();
});

test("meter controls and malformed meter traffic do not change capture generation, sequence or stop ACK", async () => {
  const {controller, node} = await fixture();
  const batches = [];
  const failures = [];
  let stopped = 0;
  const capture = await controller.start({onBatch: (pcm) => batches.push(pcm),
    onFailure: (...args) => failures.push(args), onStopped() { stopped += 1; }});
  controller.setMeterOwner(METER_A);
  node.port.onmessage({data: meterMessage()});
  node.port.onmessage({data: meterMessage({windowStartFrame: "2400", windowEndFrame: "4800",
    leftPeakFrame: "2400", rightPeakFrame: "4799", generation: 999})});
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "protocol-error"});
  const first = [Float32Array.of(0.5), Float32Array.of(0.125)];
  node.port.onmessage({data: {type: "batch", generation: 1, sequence: 1, channels: first}});
  const stop = capture.stop();
  const final = [Float32Array.of(-0.25), Float32Array.of(-0.0625)];
  node.port.onmessage({data: {type: "batch", generation: 1, sequence: 2, channels: final}});
  node.port.onmessage({data: {type: "stopped", generation: 1, finalSequence: 2}});
  await stop;
  assert.deepEqual(batches, [first, final]);
  assert.deepEqual(failures, []);
  assert.equal(stopped, 1);
  assert.deepEqual(node.messages.filter(({type}) => type === "start" || type === "stop"),
    [{type: "start", generation: 1, binding: null}, {type: "stop", generation: 1}]);
  await controller.close();
});

test("meter packets cannot settle or reject a pending capture started ACK", async () => {
  const {controller, node} = await fixture({controllerOptions: {autoStartAck: false}});
  controller.setMeterOwner(METER_A);
  let settled = null;
  const started = controller.start({onBatch() {}, onFailure() { assert.fail("meter cannot fail capture"); },
    onStopped() {}}).then(receipt => (settled = {receipt}), error => (settled = {error}));
  node.port.onmessage({data: meterMessage()});
  node.port.onmessage({data: meterMessage({leftPeak: NaN})});
  await Promise.resolve();
  assert.equal(settled, null);
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "protocol-error"});
  node.port.onmessage({data: {type: "started", generation: 1, binding: null}});
  const {receipt: capture} = await started;
  assert.ok(capture);
  assert.equal(capture.generation, 1);
  const stop = capture.stop();
  node.port.onmessage({data: {type: "stopped", generation: 1, finalSequence: 0}});
  await stop;
  await controller.close();
});

test("valid old-owner meter drains its token without adopting or poisoning the new owner", async () => {
  const {controller, node} = await fixture();
  controller.setMeterOwner(METER_A);
  controller.setMeterOwner(METER_B);
  node.port.onmessage({data: meterMessage()});
  assert.deepEqual(node.messages.at(-1), {type: "meter-ack", owner: METER_A, windowEndFrame: "2400"});
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "pending"});
  node.port.onmessage({data: meterMessage({leftPeak: NaN})});
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "pending"});
  node.port.onmessage({data: meterMessage({owner: METER_B, windowStartFrame: "2432",
    windowEndFrame: "4832", leftPeakFrame: "2500", rightPeakFrame: "4800"})});
  assert.equal(controller.meterMeasurement().owner, METER_B);
  assert.equal(controller.meterMeasurement().windowStartFrame, "2432");
  await controller.close();
});

test("old-owner ACK failure does not poison the current meter owner", async () => {
  const {controller, node} = await fixture({onPostMessage(message) {
    if (message.type === "meter-ack" && message.owner === METER_A) throw new Error("old ACK failed");
  }});
  controller.setMeterOwner(METER_A);
  controller.setMeterOwner(METER_B);
  node.port.onmessage({data: meterMessage()});
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "pending"});
  // Controller-level admitted traffic, not a claim that MessagePort retries
  // a failed ACK or the Worklet can bypass its single in-flight token.
  node.port.onmessage({data: meterMessage({owner: METER_B})});
  const current = controller.meterMeasurement();
  assert.equal(current.state, "available");
  assert.equal(current.owner, METER_B);
  node.port.onmessage({data: meterMessage()});
  assert.deepEqual(controller.meterMeasurement(), current);
  await controller.close();
});

test("unsafe clocks, malformed peaks and discontinuous windows fail only their meter owner", async () => {
  const malformed = [
    {windowEndFrame: "9007199254740992"}, {windowStartFrame: "00"},
    {windowEndFrame: 2400}, {leftPeak: Infinity}, {rightPeak: -0.1},
    {sampleRate: 0}, {renderQuantumFrames: 2401}, {leftPeakFrame: "2400"},
    {rightPeakFrame: "-1"}, {extra: true},
  ];
  for (const overrides of malformed) {
    const {controller, node} = await fixture();
    controller.setMeterOwner(METER_A);
    node.port.onmessage({data: meterMessage(overrides)});
    assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "protocol-error"},
      JSON.stringify(overrides));
    controller.setMeterOwner(METER_B);
    node.port.onmessage({data: meterMessage({owner: METER_B})});
    assert.equal(controller.meterMeasurement().state, "available");
    await controller.close();
  }
  const {controller, node} = await fixture();
  controller.setMeterOwner(METER_A);
  node.port.onmessage({data: meterMessage()});
  node.port.onmessage({data: meterMessage({windowStartFrame: "2401", windowEndFrame: "4800",
    leftPeakFrame: "2500", rightPeakFrame: "4799"})});
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "protocol-error"});
  await controller.close();
});

test("meter ACK failure is contained while a capture still receives its final PCM and ACK", async () => {
  const {controller, node} = await fixture({onPostMessage(message) {
    if (message.type === "meter-ack") throw new Error("meter ACK delivery failed");
  }});
  const batches = [];
  const capture = await controller.start({onBatch: (pcm) => batches.push(pcm), onFailure() { assert.fail(); }, onStopped() {}});
  controller.setMeterOwner(METER_A);
  node.port.onmessage({data: meterMessage()});
  assert.deepEqual(controller.meterMeasurement(), {state: "unavailable", reason: "protocol-error"});
  const stop = capture.stop();
  const channels = [Float32Array.of(0.5), Float32Array.of(0.125)];
  node.port.onmessage({data: {type: "batch", generation: 1, sequence: 1, channels}});
  node.port.onmessage({data: {type: "stopped", generation: 1, finalSequence: 1}});
  await stop;
  assert.deepEqual(batches, [channels]);
  await controller.close();
});

test("real tap keeps full-frame stereo metering independent of capture start and partial stop", async () => {
  const {controller, processor, processorMessages, clock} = await integratedFixture();
  const render = (quanta) => {
    for (let i = 0; i < quanta; i += 1) {
      const left = new Float32Array(128).fill(0.5);
      const right = new Float32Array(128).fill(-0.125);
      const output = [new Float32Array(128), new Float32Array(128)];
      assert.equal(processor.process([[left, right]], [output]), true);
      assert.deepEqual(output, [left, right]);
      clock.currentFrame += 128;
    }
  };
  controller.setMeterOwner(METER_A);
  render(19);
  assert.equal(controller.meterMeasurement().leftPeak, 0.5);
  assert.equal(controller.meterMeasurement().rightPeak, 0.125);
  assert.equal(processorMessages.some(({type}) => type === "batch"), false);
  const batches = [];
  const capture = await controller.start({onBatch: (pcm) => batches.push(pcm), onFailure() { assert.fail(); }, onStopped() {}});
  render(38);
  await capture.stop();
  assert.deepEqual(batches.map(([left, right]) => [left.length, right.length]), [[4800, 4800], [64, 64]]);
  assert.equal(batches.every(([left, right]) => left.every((x) => x === 0.5) && right.every((x) => x === -0.125)), true);
  assert.deepEqual(processorMessages.filter(({type}) => type === "batch" || type === "stopped")
    .map(({type, generation, sequence, finalSequence}) => ({type, generation, sequence, finalSequence})), [
    {type: "batch", generation: 1, sequence: 1, finalSequence: undefined},
    {type: "batch", generation: 1, sequence: 2, finalSequence: undefined},
    {type: "stopped", generation: 1, sequence: undefined, finalSequence: 2},
  ]);
  render(19);
  assert.equal(controller.meterMeasurement().state, "available");
  assert.equal(processorMessages.filter(({type}) => type === "batch").length, 2);
  await controller.close();
});

test("processor failure and close revoke meter adoption without admitting a later owner", async () => {
  const failed = await fixture();
  failed.controller.setMeterOwner(METER_A);
  failed.node.port.onmessage({data: meterMessage()});
  failed.controller.failProcessor();
  failed.node.port.onmessage({data: meterMessage({owner: METER_B})});
  assert.deepEqual(failed.controller.meterMeasurement(), {state: "unavailable", reason: "processor-failed"});
  assert.equal(failed.controller.setMeterOwner(METER_B), false);
  const closed = await fixture();
  closed.controller.setMeterOwner(METER_A);
  const handler = closed.node.port.onmessage;
  await closed.controller.close();
  handler({data: meterMessage()});
  assert.deepEqual(closed.controller.meterMeasurement(), {state: "unavailable", reason: "closed"});
  assert.equal(closed.controller.setMeterOwner(METER_B), false);
});

function fakeTimers() {
  let nextId = 1;
  const scheduled = new Map();
  const cleared = [];
  return {
    api: {
      setTimeout(callback, delay) {
        const id = nextId++;
        scheduled.set(id, {callback, delay});
        return id;
      },
      clearTimeout(id) {
        cleared.push(id);
        scheduled.delete(id);
      },
    },
    cleared,
    scheduled,
  };
}

test("creates one same-origin transparent stereo destination", async () => {
  const {controller, destination, modules, node} = await fixture();
  assert.deepEqual(modules, [
    "https://example.test/creator/perform-master-tap.js",
  ]);
  assert.equal(node.name, "lmdj-perform-master-tap");
  assert.deepEqual(node.options, {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [2],
    channelCount: 2,
    channelCountMode: "explicit",
    channelInterpretation: "discrete",
  });
  assert.equal(controller.destinationNode, node);
  assert.deepEqual(node.connected, [destination]);
  await controller.close();
  assert.deepEqual(node.disconnected, [destination]);
});

test("capture connects downstream to monitor while batches retain their original PCM", async () => {
  const {controller, destination, node} = await fixture({monitor: true});
  assert.deepEqual(node.connected, [destination]);
  const batches = [];
  await controller.start({onBatch: (channels) => batches.push(channels), onStopped() {}, onFailure() {}});
  const channels = [Float32Array.of(0.5, -0.25), Float32Array.of(-0.5, 0.25)];
  node.port.onmessage({data: {type: "batch", generation: 1, sequence: 1, channels}});
  assert.equal(batches[0], channels);
  assert.deepEqual([...batches[0][0]], [0.5, -0.25]);
  await controller.close();
});

test("rejects a cross-origin processor before module creation", async () => {
  const previousLocation = globalThis.location;
  globalThis.location = new URL("https://example.test/creator/");
  try {
    await assert.rejects(
      createPerformanceMasterTap({
        context: {audioWorklet: {addModule() { assert.fail(); }}},
        processorUrl: "https://cdn.example/perform-master-tap.js",
      }),
      {name: "TypeError", message: "Perform master tap URL must be same-origin"},
    );
  } finally {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  }
});

test("rejects a destination from another AudioContext before module creation", async () => {
  const context = {destination: {}, audioWorklet: {addModule() { assert.fail(); }}};
  await assert.rejects(createPerformanceMasterTap({context,
    destination: {context: {}}, processorUrl: "https://example.test/tap.js"}),
  {name: "TypeError", message: "Perform master tap destination must share its context"});
});

test("serializes generations, validates sequences, and contains sink errors", async () => {
  const {controller, node} = await fixture();
  const batches = [];
  let stopped = 0;
  const capture = await controller.start({
    onBatch(channels) {
      batches.push(channels);
      throw new Error("sink failed");
    },
    onStopped() { stopped += 1; },
    onFailure() { assert.fail("capture should not fail"); },
  });
  assert.deepEqual(node.messages, [{type: "start", generation: 1, binding: null}]);
  await assert.rejects(controller.start({
    onBatch() {}, onStopped() {}, onFailure() {},
  }), /already active/);

  const channels = [new Float32Array(4_800), new Float32Array(4_800)];
  node.port.onmessage({data: {
    type: "batch", generation: 0, sequence: 1, channels,
  }});
  node.port.onmessage({data: {
    type: "batch", generation: 1, sequence: 1, channels,
  }});
  assert.equal(batches.length, 1);

  const firstStop = capture.stop();
  assert.equal(firstStop, capture.stop());
  assert.deepEqual(node.messages.at(-1), {type: "stop", generation: 1});
  node.port.onmessage({data: {
    type: "stopped", generation: 1, finalSequence: 1,
  }});
  await firstStop;
  assert.equal(stopped, 1);

  const second = await controller.start({
    onBatch() {}, onStopped() { stopped += 1; }, onFailure() {},
  });
  assert.deepEqual(node.messages.at(-1), {type: "start", generation: 2, binding: null});
  node.port.onmessage({data: {
    type: "stopped", generation: 1, finalSequence: 1,
  }});
  assert.equal(stopped, 1);
  const secondStop = second.stop();
  node.port.onmessage({data: {
    type: "stopped", generation: 2, finalSequence: 0,
  }});
  await secondStop;
  assert.equal(stopped, 2);
});

test("processor failure and close settle an active capture exactly once", async () => {
  const {controller} = await fixture();
  const failures = [];
  let stopped = 0;
  const capture = await controller.start({
    onBatch() {},
    onStopped() { stopped += 1; },
    onFailure(...arguments_) { failures.push(arguments_); },
  });
  controller.failProcessor();
  controller.failProcessor();
  await capture.stop();
  assert.deepEqual(failures, [["tap-failure", 0]]);
  assert.equal(stopped, 1);

  const closingFixture = await fixture();
  const secondFailures = [];
  let closeStopped = 0;
  const second = await closingFixture.controller.start({
    onBatch() {}, onStopped() { closeStopped += 1; },
    onFailure(...arguments_) { secondFailures.push(arguments_); },
  });
  await closingFixture.controller.close();
  await second.stop();
  assert.deepEqual(secondFailures, [["tap-failure", 0]]);
  assert.equal(closeStopped, 1);
});

test("current malformed traffic fails closed while stale traffic stays isolated", async () => {
  const {controller, node} = await fixture();
  const terminals = [];
  const first = await controller.start({
    onBatch() { assert.fail("malformed batch must not be delivered"); },
    onFailure(...arguments_) { terminals.push(["failure", ...arguments_]); },
    onStopped() { terminals.push(["stopped"]); },
  });
  const channels = [new Float32Array(8), new Float32Array(8)];
  node.port.onmessage({data: {
    type: "batch", generation: 0, sequence: 2, channels,
  }});
  assert.deepEqual(terminals, []);
  node.port.onmessage({data: {
    type: "batch", generation: 1, sequence: 2, channels,
  }});
  assert.deepEqual(node.messages, [
    {type: "start", generation: 1, binding: null},
    {type: "stop", generation: 1},
  ]);
  assert.deepEqual(terminals, [
    ["failure", "tap-failure", 0],
    ["stopped"],
  ]);
  await first.stop();

  const second = await controller.start({
    onBatch() {},
    onFailure(...arguments_) { terminals.push(["failure", ...arguments_]); },
    onStopped() { terminals.push(["stopped"]); },
  });
  const stopping = second.stop();
  node.port.onmessage({data: {
    type: "stopped", generation: 2, finalSequence: 0, extra: true,
  }});
  assert.deepEqual(terminals.slice(-2), [
    ["failure", "tap-failure", 0],
    ["stopped"],
  ]);
  await stopping;
});

test("malformed stale-shaped events stop the current capture", async () => {
  const {controller, node} = await fixture();
  const stereo = () => [new Float32Array(8), new Float32Array(8)];
  const malformed = [
    {type: "unknown", generation: 0},
    {type: "stopped", generation: 1, finalSequence: 0, extra: true},
    {
      type: "batch", generation: 2, sequence: 1,
      channels: [new Float32Array(8), new Float32Array(7)],
    },
    {type: "batch", generation: 3, sequence: -1, channels: stereo()},
    {type: "stopped", generation: 4, finalSequence: -1},
    {
      type: "failed", generation: 5,
      reason: "unknown-reason", droppedFrames: 0,
    },
    {
      type: "failed", generation: 6,
      reason: "post-message-failed",
      droppedFrames: Number.MAX_SAFE_INTEGER + 1,
    },
  ];
  const terminals = [];
  for (const [index, data] of malformed.entries()) {
    const generation = index + 1;
    const capture = await controller.start({
      onBatch() { assert.fail("malformed stale batch must not be delivered"); },
      onFailure(...arguments_) {
        terminals.push([generation, "failure", ...arguments_]);
      },
      onStopped() { terminals.push([generation, "stopped"]); },
    });
    node.port.onmessage({data});
    assert.deepEqual(terminals.slice(-2), [
      [generation, "failure", "tap-failure", 0],
      [generation, "stopped"],
    ]);
    assert.deepEqual(node.messages.slice(-2), [
      {type: "start", generation, binding: null},
      {type: "stop", generation},
    ]);
    await capture.stop();
  }

  const finalTerminals = [];
  const final = await controller.start({
    onBatch() { assert.fail("legal stale batch must be discarded"); },
    onFailure(...arguments_) { finalTerminals.push(["failure", ...arguments_]); },
    onStopped() { finalTerminals.push(["stopped"]); },
  });
  node.port.onmessage({data: {
    type: "batch", generation: 7, sequence: 1, channels: stereo(),
  }});
  assert.deepEqual(finalTerminals, []);
  assert.deepEqual(node.messages.at(-1), {type: "start", generation: 8, binding: null});
  const stopping = final.stop();
  node.port.onmessage({data: {
    type: "stopped", generation: 8, finalSequence: 0,
  }});
  await stopping;
  assert.deepEqual(finalTerminals, [["stopped"]]);
});

test("malformed active traffic stops processor work and leaves the next generation clean", async () => {
  const {controller, node, processor, processorMessages} =
    await integratedFixture();
  const terminals = [];
  const first = await controller.start({
    onBatch() { assert.fail("malformed capture must not deliver a batch"); },
    onFailure(...arguments_) { terminals.push(["failure", ...arguments_]); },
    onStopped() { terminals.push(["stopped"]); },
  });
  node.port.onmessage({data: {type: "batch"}});
  await first.stop();
  assert.deepEqual(node.messages, [
    {type: "start", generation: 1, binding: null},
    {type: "stop", generation: 1},
  ]);
  assert.deepEqual(terminals, [
    ["failure", "tap-failure", 0],
    ["stopped"],
  ]);

  const input = [new Float32Array(16).fill(0.25)];
  const output = [new Float32Array(16), new Float32Array(16)];
  processor.process([input], [output]);
  assert.deepEqual(processorMessages.map(({type}) => type),
    ["started", "stopped"]);

  const batches = [];
  const second = await controller.start({
    onBatch(channels) { batches.push(channels); },
    onFailure() { assert.fail("next generation must stay clean"); },
    onStopped() { terminals.push(["second-stopped"]); },
  });
  processor.process([input], [output]);
  const secondStopping = second.stop();
  await secondStopping;
  assert.equal(batches.length, 1);
  assert.deepEqual(node.messages.slice(-2), [
    {type: "start", generation: 2, binding: null},
    {type: "stop", generation: 2},
  ]);
  assert.equal(processorMessages.at(-2).generation, 2);
  assert.equal(processorMessages.at(-2).sequence, 1);
  assert.deepEqual({...processorMessages.at(-1)}, {
    type: "stopped", generation: 2, finalSequence: 1,
  });
});

test("malformed termination settles even when posting processor stop throws", async () => {
  const {controller, node} = await fixture({
    onPostMessage(message) {
      if (message.type === "stop") throw new Error("port closed");
    },
  });
  const terminals = [];
  const capture = await controller.start({
    onBatch() {},
    onFailure(...arguments_) { terminals.push(["failure", ...arguments_]); },
    onStopped() { terminals.push(["stopped"]); },
  });
  node.port.onmessage({data: {
    type: "batch", generation: 1, sequence: 2,
    channels: [new Float32Array(8), new Float32Array(8)],
  }});
  await capture.stop();
  assert.deepEqual(node.messages, [
    {type: "start", generation: 1, binding: null},
    {type: "stop", generation: 1},
  ]);
  assert.deepEqual(terminals, [
    ["failure", "tap-failure", 0],
    ["stopped"],
  ]);
});

test("non-object active traffic also stops and settles fail-closed", async () => {
  const {controller, node} = await fixture();
  const terminals = [];
  const capture = await controller.start({
    onBatch() {},
    onFailure(...arguments_) { terminals.push(["failure", ...arguments_]); },
    onStopped() { terminals.push(["stopped"]); },
  });
  assert.doesNotThrow(() => node.port.onmessage({data: null}));
  await capture.stop();
  assert.deepEqual(node.messages, [
    {type: "start", generation: 1, binding: null},
    {type: "stop", generation: 1},
  ]);
  assert.deepEqual(terminals, [
    ["failure", "tap-failure", 0],
    ["stopped"],
  ]);
});

test("stop acknowledgement uses the Host-aligned thirty-second deadline", async () => {
  const timers = fakeTimers();
  const {controller, node} = await fixture({
    controllerOptions: {timers: timers.api},
  });
  const capture = await controller.start({
    onBatch() {}, onFailure() {}, onStopped() {},
  });
  const stopping = capture.stop();
  assert.deepEqual(
    [...timers.scheduled.values()].map(({delay}) => delay),
    [30_000],
  );
  node.port.onmessage({data: {
    type: "stopped", generation: 1, finalSequence: 0,
  }});
  await stopping;
});

test("stop acknowledgement deadline is injected, cleared, and generation-safe", async () => {
  const timers = fakeTimers();
  const {controller, node} = await fixture({
    controllerOptions: {timers: timers.api, stopAckTimeoutMs: 37},
  });
  const terminals = [];
  const first = await controller.start({
    onBatch() {},
    onFailure() { assert.fail("acknowledged capture must not fail"); },
    onStopped() { terminals.push(["first-stopped"]); },
  });
  const stopping = first.stop();
  assert.equal(stopping, first.stop());
  assert.deepEqual(
    [...timers.scheduled.values()].map(({delay}) => delay),
    [37],
  );
  const lateCallback = [...timers.scheduled.values()][0].callback;
  node.port.onmessage({data: {
    type: "stopped", generation: 1, finalSequence: 0,
  }});
  await stopping;
  assert.deepEqual(terminals, [["first-stopped"]]);
  assert.equal(timers.scheduled.size, 0);
  // The start ACK timer (id 1) cleared at the started ACK; the stop timer
  // (id 2) cleared at the stopped ACK.
  assert.deepEqual(timers.cleared, [1, 2]);
  lateCallback();
  assert.deepEqual(terminals, [["first-stopped"]]);

  const second = await controller.start({
    onBatch() {},
    onFailure(...arguments_) { terminals.push(["failure", ...arguments_]); },
    onStopped() { terminals.push(["second-stopped"]); },
  });
  const secondStopping = second.stop();
  const deadline = [...timers.scheduled.values()][0].callback;
  deadline();
  await secondStopping;
  assert.deepEqual(terminals.slice(-2), [
    ["failure", "tap-failure", 0],
    ["second-stopped"],
  ]);
  node.port.onmessage({data: {
    type: "stopped", generation: 2, finalSequence: 0,
  }});
  assert.equal(terminals.filter(([kind]) => kind === "failure").length, 1);

  const third = await controller.start({
    onBatch() {},
    onFailure() { assert.fail("next generation must remain available"); },
    onStopped() { terminals.push(["third-stopped"]); },
  });
  const thirdStopping = third.stop();
  node.port.onmessage({data: {
    type: "stopped", generation: 3, finalSequence: 0,
  }});
  await thirdStopping;
  assert.deepEqual(terminals.at(-1), ["third-stopped"]);
  assert.equal(timers.scheduled.size, 0);
});


// ---------------------------------------------------------------------------
// D0/W1 started-ACK oracle: the start promise stays pending until the real
// applied ACK; wrong binding/generation, duplicates, early batches, close,
// processor failure and timeout all reject without arming; a late ACK is
// never inherited.
// ---------------------------------------------------------------------------

const kBinding = Object.freeze({
  control_epoch: "10000000-0000-4000-8000-000000000001",
  session_id: "10000000-0000-4000-8000-000000000002",
  begin_command_id: "10000000-0000-4000-8000-000000000003",
});
const kSink = () => ({onBatch() {}, onStopped() {}, onFailure() {}});

test("start stays pending until the exact started ACK, then arms", async () => {
  const {controller, node} = await fixture({
    controllerOptions: {autoStartAck: false},
  });
  let settled = null;
  const starting = controller.start(kSink(), kBinding).then(
    (capture) => { settled = capture; return capture; });
  await Promise.resolve();
  assert.equal(settled, null);
  assert.deepEqual(node.messages, [
    {type: "start", generation: 1, binding: kBinding},
  ]);
  // A second start while the first is pending is refused outright.
  await assert.rejects(controller.start(kSink(), kBinding), /already active/);
  node.port.onmessage({data: {type: "started", generation: 1, binding: kBinding}});
  const capture = await starting;
  assert.equal(capture.binding, kBinding);
  assert.equal(capture.generation, 1);
  const stopping = capture.stop();
  node.port.onmessage({data: {type: "stopped", generation: 1, finalSequence: 0}});
  await stopping;
});

test("wrong-binding, duplicate and early-batch ACKs fail the pending start", async () => {
  for (const bad of [
    {type: "started", generation: 1, binding: null},
    {type: "started", generation: 1, binding: kBinding, extra: true},
    {type: "batch", generation: 1, sequence: 1,
     channels: [new Float32Array(8), new Float32Array(8)]},
  ]) {
    const {controller, node} = await fixture({
      controllerOptions: {autoStartAck: false},
    });
    const terminals = [];
    const starting = controller.start({
      onBatch() {}, onStopped() { terminals.push("stopped"); },
      onFailure() {},
    }, kBinding);
    await Promise.resolve();
    node.port.onmessage({data: bad});
    await assert.rejects(starting, /not acknowledged/);
    // The cleanup ran the bounded stop: the processor was told to stop.
    assert.deepEqual(node.messages.at(-1), {type: "stop", generation: 1});
    // The pending slot is released: the next generation can start.
    const retry = controller.start(kSink(), kBinding);
    await Promise.resolve();
    assert.deepEqual(node.messages.at(-1), {
      type: "start", generation: 2, binding: kBinding,
    });
    node.port.onmessage({data: {type: "started", generation: 2, binding: kBinding}});
    const capture = await retry;
    // The first start's late ACK is not inherited by the second.
    node.port.onmessage({data: {type: "started", generation: 1, binding: kBinding}});
    assert.equal(capture.generation, 2);
    const stopping = capture.stop();
    node.port.onmessage({data: {type: "stopped", generation: 2, finalSequence: 0}});
    await stopping;
    await controller.close();
  }
});

test("close, processor failure and timeout reject the pending start", async () => {
  // close during pending
  {
    const {controller} = await fixture({
      controllerOptions: {autoStartAck: false},
    });
    const starting = controller.start(kSink(), kBinding);
    await Promise.resolve();
    await controller.close();
    await assert.rejects(starting, /not acknowledged/);
  }
  // processor failure during pending
  {
    const {controller} = await fixture({
      controllerOptions: {autoStartAck: false},
    });
    const starting = controller.start(kSink(), kBinding);
    await Promise.resolve();
    controller.failProcessor();
    await assert.rejects(starting, /not acknowledged/);
    await assert.rejects(controller.start(kSink(), kBinding), /unavailable/);
  }
  // the independent start timeout budget
  {
    const timers = fakeTimers();
    const {controller} = await fixture({
      controllerOptions: {autoStartAck: false, timers: timers.api, startAckTimeoutMs: 37},
    });
    const starting = controller.start(kSink(), kBinding);
    await Promise.resolve();
    assert.deepEqual(
      [...timers.scheduled.values()].map(({delay}) => delay), [37]);
    [...timers.scheduled.values()][0].callback();
    await assert.rejects(starting, /not acknowledged/);
  }
});

test("a legacy null binding still arms, and a malformed binding is refused", async () => {
  const {controller, node} = await fixture();
  await assert.rejects(
    controller.start(kSink(), {control_epoch: "not-a-uuid"}),
    {name: "TypeError"});
  const capture = await controller.start(kSink());
  assert.equal(capture.binding, null);
  const stopping = capture.stop();
  node.port.onmessage({data: {type: "stopped", generation: 1, finalSequence: 0}});
  await stopping;
});
