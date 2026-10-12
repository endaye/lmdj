import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {runInNewContext} from "node:vm";

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

function terminalWorkerFixture({
  drain = () => true,
  pendingAuthorizations = 0,
  complete = () => 1,
} = {}) {
  const token = "00000000-0000-0000-0000-000000000001";
  const timers = [];
  const authorizations = [];
  const completions = [];
  const messages = [];
  const order = [];
  let nativeState = "ready";
  let releaseCalls = 0;
  let workerCloses = 0;
  let channelCloses = 0;
  let channelListener;
  let channels = 0;
  class BroadcastChannel {
    constructor(name) {
      assert.equal(name, "lmdj.web-runtime-host.terminal.v1");
      channels += 1;
    }
    addEventListener(type, listener) {
      assert.equal(type, "message");
      channelListener = listener;
    }
    postMessage(message) {
      messages.push({...message});
      order.push("receipt");
    }
    close() {
      channelCloses += 1;
      order.push("channel-close");
    }
  }
  const Module = {
    ccall(name, returnType, argumentTypes, args) {
      assert.equal(returnType, "number");
      if (name === "lmdj_web_host_authorize_terminal_release") {
        assert.deepEqual(Array.from(argumentTypes), ["string", "number"]);
        authorizations.push(Array.from(args));
        if (args[0] !== token || args[1] !== token.length ||
            nativeState !== "ready") return 0;
        if (pendingAuthorizations > 0) {
          pendingAuthorizations -= 1;
          return 2;
        }
        nativeState = "authorized";
        return 1;
      }
      assert.equal(name, "lmdj_web_host_complete_terminal_release");
      assert.deepEqual(Array.from(argumentTypes), ["string", "number", "number"]);
      assert.deepEqual(Array.from(args), [token, token.length, 1]);
      assert.equal(nativeState, "authorized");
      completions.push(Array.from(args));
      order.push("completion");
      const result = complete(completions.length);
      if (result === 1) nativeState = "completed";
      return result;
    },
  };
  const workerSource = readFileSync(
    new URL("../src/web-runtime-pre.js", import.meta.url), "utf8");
  runInNewContext(workerSource, {
    ENVIRONMENT_IS_PTHREAD: true,
    BroadcastChannel,
    Module,
    LmdjOpfs: {
      releaseAllWriters() {
        assert.equal(nativeState, "authorized");
        releaseCalls += 1;
        order.push("drain");
        return drain(releaseCalls);
      },
    },
    setTimeout(callback, delay) {
      assert.equal(delay, 2);
      timers.push(callback);
    },
    close() {
      workerCloses += 1;
      order.push("worker-close");
    },
  }, {filename: "web-runtime-pre.js"});
  assert.equal(channels, 1);
  return {
    token, timers, authorizations, completions, messages, order,
    get releaseCalls() { return releaseCalls; },
    get workerCloses() { return workerCloses; },
    get channelCloses() { return channelCloses; },
    get nativeState() { return nativeState; },
    send(value = token, type = "release-and-close") {
      channelListener({data: {type, token: value}});
    },
    step() {
      assert.equal(timers.length, 1, "exactly one terminal retry is pending");
      timers.shift()();
    },
  };
}

function assertTerminalWorkerRetained(fixture) {
  assert.equal(fixture.completions.length, 0);
  assert.deepEqual(fixture.messages, []);
  assert.equal(fixture.channelCloses, 0);
  assert.equal(fixture.workerCloses, 0);
}

test("terminal worker retains one authorization through pending physical drains", () => {
  const fixture = terminalWorkerFixture({drain: (call) => call === 3});
  fixture.send();
  assert.equal(fixture.releaseCalls, 1);
  assert.equal(fixture.authorizations.length, 1);
  assert.equal(fixture.nativeState, "authorized");
  assertTerminalWorkerRetained(fixture);
  fixture.step();
  assert.equal(fixture.releaseCalls, 2);
  assert.equal(fixture.authorizations.length, 1);
  assertTerminalWorkerRetained(fixture);
  fixture.step();
  assert.equal(fixture.releaseCalls, 3);
  assert.equal(fixture.authorizations.length, 1);
  assert.deepEqual(fixture.completions, [[fixture.token, fixture.token.length, 1]]);
  assert.deepEqual(fixture.messages, [{type: "released-and-closed", token: fixture.token}]);
  assert.equal(fixture.channelCloses, 1);
  assert.equal(fixture.workerCloses, 1);
  assert.equal(fixture.timers.length, 0);
  assert.deepEqual(fixture.order, ["drain", "drain", "drain", "completion",
    "receipt", "channel-close", "worker-close"]);
});

test("terminal worker retries a thrown drain without completing or closing", () => {
  const fixture = terminalWorkerFixture({drain() { throw new Error("pending owner"); }});
  fixture.send();
  fixture.step();
  assert.equal(fixture.releaseCalls, 2);
  assert.equal(fixture.authorizations.length, 1);
  assert.equal(fixture.nativeState, "authorized");
  assert.equal(fixture.timers.length, 1);
  assertTerminalWorkerRetained(fixture);
});

test("terminal worker requires literal true from the physical drain", () => {
  for (const result of [undefined, null, 1, {}]) {
    const fixture = terminalWorkerFixture({drain: () => result});
    fixture.send();
    fixture.step();
    assert.equal(fixture.releaseCalls, 2);
    assert.equal(fixture.authorizations.length, 1);
    assert.equal(fixture.nativeState, "authorized");
    assert.equal(fixture.timers.length, 1);
    assertTerminalWorkerRetained(fixture);
  }
});

test("terminal worker denies foreign tokens without touching physical owners", () => {
  const fixture = terminalWorkerFixture({drain: () => false});
  fixture.send("00000000-0000-0000-0000-000000000002");
  assert.equal(fixture.authorizations.length, 1);
  assert.equal(fixture.releaseCalls, 0);
  assert.equal(fixture.timers.length, 0);
  assert.equal(fixture.nativeState, "ready");
  assertTerminalWorkerRetained(fixture);
  fixture.send();
  fixture.send("00000000-0000-0000-0000-000000000002");
  assert.equal(fixture.authorizations.length, 3);
  assert.equal(fixture.releaseCalls, 1);
  assert.equal(fixture.nativeState, "authorized");
  assert.equal(fixture.timers.length, 1);
  assertTerminalWorkerRetained(fixture);
});

test("duplicate terminal messages share one pending authorization and drain loop", () => {
  const fixture = terminalWorkerFixture({
    pendingAuthorizations: 1,
    drain: (call) => call === 2,
  });
  fixture.send();
  fixture.send();
  assert.equal(fixture.authorizations.length, 1);
  assert.equal(fixture.releaseCalls, 0);
  assert.equal(fixture.timers.length, 1);
  assertTerminalWorkerRetained(fixture);
  fixture.step();
  fixture.send();
  assert.equal(fixture.authorizations.length, 2);
  assert.equal(fixture.releaseCalls, 1);
  assert.equal(fixture.timers.length, 1);
  assertTerminalWorkerRetained(fixture);
  fixture.step();
  fixture.send();
  fixture.send();
  assert.equal(fixture.authorizations.length, 2);
  assert.equal(fixture.releaseCalls, 2);
  assert.equal(fixture.completions.length, 1);
  assert.equal(fixture.messages.length, 1);
  assert.equal(fixture.channelCloses, 1);
  assert.equal(fixture.workerCloses, 1);
  assert.equal(fixture.timers.length, 0);
});

test("terminal worker waits for native completion after a positive physical drain", () => {
  const fixture = terminalWorkerFixture({complete: (call) => call === 2 ? 1 : 0});
  fixture.send();
  assert.equal(fixture.releaseCalls, 1);
  assert.equal(fixture.completions.length, 1);
  assert.deepEqual(fixture.messages, []);
  assert.equal(fixture.channelCloses, 0);
  assert.equal(fixture.workerCloses, 0);
  assert.equal(fixture.nativeState, "authorized");
  assert.equal(fixture.timers.length, 1);
  fixture.step();
  assert.equal(fixture.authorizations.length, 1);
  assert.equal(fixture.releaseCalls, 1);
  assert.equal(fixture.completions.length, 2);
  assert.equal(fixture.nativeState, "completed");
  assert.equal(fixture.messages.length, 1);
  assert.equal(fixture.channelCloses, 1);
  assert.equal(fixture.workerCloses, 1);
  assert.equal(fixture.timers.length, 0);
});

function actualBrowserRuntimePublication({Module, window, crypto}) {
  const channels = [];
  class BroadcastChannel {
    constructor(name) { this.name = name; channels.push(this); }
    addEventListener() {}
    close() {}
  }
  runInNewContext(readFileSync(new URL("../src/web-runtime-pre.js", import.meta.url), "utf8"), {
    ENVIRONMENT_IS_PTHREAD: false,
    Module, window, crypto, BroadcastChannel, TextEncoder, TextDecoder,
  }, {filename: "web-runtime-pre.js"});
  return channels;
}

test("actual Host publisher reports its local owner to its original Module before global publication", () => {
  const priorHost = {prior: true};
  const foreignHost = {foreign: true};
  const foreignModule = {foreign: true};
  let callbackHost;
  let callbackModule;
  let callbackCalls = 0;
  const window = {lmdjWebRuntimeHost: priorHost, Worker: class {}};
  const Module = {lmdjRuntimeOwnerCreated(host, producerModule) {
    callbackCalls += 1;
    callbackHost = host;
    callbackModule = producerModule;
    assert.equal(window.lmdjWebRuntimeHost, priorHost, "registration precedes global publication");
    assert.equal(host.transport.terminalOwnerReleased, false,
      "creating a Host is no Native retirement or quiescence ACK");
    window.Module = foreignModule;
    window.lmdjWebRuntimeHost = foreignHost;
  }};
  window.Module = Module;
  const channels = actualBrowserRuntimePublication({Module, window,
    crypto: {randomUUID: () => "00000000-0000-4000-8000-000000000001"}});
  assert.equal(callbackCalls, 1);
  assert.equal(callbackModule, Module, "the actual producer reports its captured Module, not a global replacement");
  assert.equal(window.Module, foreignModule);
  assert.equal(window.lmdjWebRuntimeHost, callbackHost);
  assert.notEqual(callbackHost, priorHost);
  assert.notEqual(callbackHost, foreignHost);
  assert.equal(callbackHost.runtimeInitialized, false);
  assert.equal(callbackHost.transport.terminalOwnerReleased, false);
  assert.equal(channels.length, 1);
  assert.equal(Module.lmdjRuntimeOwnerCreated, undefined, "the configuration callback is captured once locally");
});

test("actual Host publisher preserves standalone behavior without an invocation registration hook", () => {
  const priorHost = {};
  const window = {lmdjWebRuntimeHost: priorHost, Worker: class {}};
  actualBrowserRuntimePublication({Module: {}, window,
    crypto: {randomUUID: () => "00000000-0000-4000-8000-000000000002"}});
  assert.notEqual(window.lmdjWebRuntimeHost, priorHost);
  assert.equal(window.lmdjWebRuntimeHost.runtimeInitialized, false);
  assert.equal(window.lmdjWebRuntimeHost.transport.terminalOwnerReleased, false);
});
