import assert from "node:assert/strict";
import test from "node:test";

import {
  createPackagedRuntimeLocator,
  defaultRuntimeTerminator,
} from "../web/runtime_loader.mjs";


test("locates the content-hashed packaged Runtime assets", () => {
  const locate = createPackagedRuntimeLocator({
    baseURI: "https://example.test/release/index.html",
    runtimeScriptURL: "./assets/runtime.script.js",
    runtimeWasmURL: "./assets/runtime.binary.wasm",
  });

  assert.equal(
    locate("lmdj-web-runtime.js"),
    "https://example.test/release/assets/runtime.script.js",
  );
  assert.equal(
    locate("runtime.binary.wasm"),
    "https://example.test/release/assets/runtime.binary.wasm",
  );
  assert.equal(
    locate("worker.js"),
    "https://example.test/release/worker.js",
  );
});

test("terminates unique workers and releases worklet and audio resources", async () => {
  let workerTerminations = 0;
  let workletDisconnects = 0;
  let portCloses = 0;
  let audioCloses = 0;
  let closeOperation = null;
  const worker = {terminate() { workerTerminations += 1; }};
  const runtime = {
    workers: [worker, worker],
    transport: {
      async send(request, options) {
        closeOperation = {request, options};
        return {};
      },
    },
    worklet: {
      disconnect() { workletDisconnects += 1; },
      port: {close() { portCloses += 1; }},
    },
  };
  const audioContext = {
    state: "running",
    close() { audioCloses += 1; this.state = "closed"; },
  };

  await defaultRuntimeTerminator({
    runtime,
    audioContext,
    window: {
      crypto: {
        randomUUID: () => "00000000-0000-0000-0000-000000000001",
      },
    },
  });

  assert.equal(workerTerminations, 1);
  assert.equal(closeOperation.request.operation, "host.close");
  assert.equal(closeOperation.options.deadlineMs, 10_000);
  assert.equal(workletDisconnects, 1);
  assert.equal(portCloses, 1);
  assert.equal(audioCloses, 1);
});

test("uses transport termination without directly terminating its workers", async () => {
  let transportTerminations = 0;
  let workerTerminations = 0;
  const runtime = {
    workers: [{terminate() { workerTerminations += 1; }}],
    transport: {
      terminate() { transportTerminations += 1; },
      async send() {},
    },
  };

  await defaultRuntimeTerminator({
    runtime,
    audioContext: null,
    window: {
      crypto: {
        randomUUID: () => "00000000-0000-0000-0000-000000000001",
      },
    },
  });

  assert.equal(transportTerminations, 1);
  assert.equal(workerTerminations, 0);
});

test("awaits transport terminal ownership before closing audio resources", async () => {
  const order = [];
  let resolveTransport;
  const transportClosed = new Promise((resolve) => {
    resolveTransport = resolve;
  });
  const pending = defaultRuntimeTerminator({
    runtime: {
      workers: [{terminate() { order.push("direct-worker"); }}],
      transport: {
        terminate() {
          order.push("transport");
          return transportClosed;
        },
        async send() {},
      },
      worklet: {
        disconnect() { order.push("worklet"); },
        port: {close() { order.push("port"); }},
      },
    },
    audioContext: {
      state: "running",
      close() { order.push("audio"); this.state = "closed"; },
    },
    window: {
      crypto: {
        randomUUID: () => "00000000-0000-0000-0000-000000000001",
      },
    },
  });

  await Promise.resolve();
  assert.deepEqual(order, ["transport"]);
  resolveTransport();
  await pending;
  assert.deepEqual(order, ["transport", "worklet", "port", "audio"]);
});

function retainedBackendFixture(terminate) {
  const order = [];
  const audioContext = {
    state: "running",
    async close() { order.push("audio"); this.state = "closed"; },
  };
  const runtime = {
    workers: [{terminate() { order.push("direct-worker"); }}],
    transport: {
      terminate,
      terminalOwnerReleased: false,
      async send() {},
    },
    worklet: {
      disconnect() { order.push("worklet"); },
      port: {close() { order.push("port"); }},
    },
  };
  const resources = {runtime, audioContext, window: {crypto: {
    randomUUID: () => "00000000-0000-0000-0000-000000000001",
  }}};
  return {order, runtime, audioContext, resources};
}

test("formal retirement rejection preserves the original error and backend", async () => {
  const original = Object.assign(new Error("original physical drain failed"), {
    code: "HOST_TIMEOUT", details: Object.freeze({pending: true}),
  });
  const fixture = retainedBackendFixture(() => Promise.reject(original));
  await assert.rejects(defaultRuntimeTerminator(fixture.resources),
    (error) => error === original);
  assert.deepEqual(fixture.order, []);
  assert.equal(fixture.audioContext.state, "running");
  assert.equal(fixture.runtime.transport.terminalOwnerReleased, false);
});

test("a resolved formal terminator without owner release cannot detach", async () => {
  const fixture = retainedBackendFixture(async () => {});
  await assert.rejects(defaultRuntimeTerminator(fixture.resources),
    (error) => error.code === "HOST_STATE_INVALID" && error.details.pending === true);
  assert.deepEqual(fixture.order, []);
  assert.equal(fixture.audioContext.state, "running");
});

test("actual backend close rejection remains a failure after owner release", async () => {
  const fixture = retainedBackendFixture(async () => {});
  fixture.runtime.transport.terminalOwnerReleased = true;
  const original = new Error("actual browser close failed");
  fixture.audioContext.close = async () => {
    fixture.order.push("audio");
    throw original;
  };
  await assert.rejects(defaultRuntimeTerminator(fixture.resources),
    (error) => error === original);
  assert.deepEqual(fixture.order, ["worklet", "port", "audio"]);
  assert.equal(fixture.audioContext.state, "running");
});

test("resolved close must confirm the backend actually reached closed", async () => {
  const fixture = retainedBackendFixture(async () => {});
  fixture.runtime.transport.terminalOwnerReleased = true;
  fixture.audioContext.close = async () => { fixture.order.push("audio"); };
  await assert.rejects(defaultRuntimeTerminator(fixture.resources),
    (error) => error.code === "HOST_STATE_INVALID" && error.details.pending === true);
  assert.deepEqual(fixture.order, ["worklet", "port", "audio"]);
  assert.equal(fixture.audioContext.state, "running");
});
