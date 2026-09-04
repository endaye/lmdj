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

async function fixture({controllerOptions, onPostMessage} = {}) {
  const previousLocation = globalThis.location;
  const previousNode = globalThis.AudioWorkletNode;
  const modules = [];
  const destination = {kind: "speakers"};
  const context = {
    destination,
    audioWorklet: {async addModule(url) { modules.push(url); }},
  };
  let node = null;
  globalThis.location = new URL("https://example.test/creator/");
  globalThis.AudioWorkletNode = class extends StubNode {
    constructor(...arguments_) {
      super(...arguments_);
      node = this;
      this.port.postMessage = (message) => {
        this.messages.push(message);
        onPostMessage?.(message, this);
      };
    }
  };
  try {
    const controller = await createPerformanceMasterTap(
      {
        context,
        processorUrl: "./perform-master-tap.js",
      },
      controllerOptions,
    );
    return {controller, context, destination, modules, node};
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
  vm.runInNewContext(source, {
    AudioWorkletProcessor: StubAudioWorkletProcessor,
    Float32Array,
    Number,
    registerProcessor(name, constructor) {
      assert.equal(name, "lmdj-perform-master-tap");
      Processor = constructor;
    },
  });
  const processor = new Processor();
  const result = await fixture({
    onPostMessage(message) {
      processor.port.onmessage({data: message});
    },
  });
  hostNode = result.node;
  return {...result, processor, processorMessages};
}

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
  assert.deepEqual(node.messages, [{type: "start", generation: 1}]);
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
  assert.deepEqual(node.messages.at(-1), {type: "start", generation: 2});
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
    {type: "start", generation: 1},
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
      {type: "start", generation},
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
  assert.deepEqual(node.messages.at(-1), {type: "start", generation: 8});
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
    {type: "start", generation: 1},
    {type: "stop", generation: 1},
  ]);
  assert.deepEqual(terminals, [
    ["failure", "tap-failure", 0],
    ["stopped"],
  ]);

  const input = [new Float32Array(16).fill(0.25)];
  const output = [new Float32Array(16), new Float32Array(16)];
  processor.process([input], [output]);
  assert.deepEqual(processorMessages.map(({type}) => type), ["stopped"]);

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
    {type: "start", generation: 2},
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
    {type: "start", generation: 1},
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
    {type: "start", generation: 1},
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
  assert.deepEqual(timers.cleared, [1]);
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
