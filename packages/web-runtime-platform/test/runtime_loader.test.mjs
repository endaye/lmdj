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

function actualBrowserRuntimePublication({Module, window, crypto, globals = {}}) {
  const channels = [];
  class BroadcastChannel {
    constructor(name) { this.name = name; this.posted = []; channels.push(this); }
    addEventListener() {}
    postMessage(message) { this.posted.push(message); }
    close() {}
  }
  runInNewContext(readFileSync(new URL("../src/web-runtime-pre.js", import.meta.url), "utf8"), {
    ENVIRONMENT_IS_PTHREAD: false,
    Module, window, crypto, BroadcastChannel, TextEncoder, TextDecoder, ...globals,
  }, {filename: "web-runtime-pre.js"});
  return channels;
}

test("actual count-in metronome entry point encodes a boolean and reports Native refusal", () => {
  const choices = [];
  let accepted = 1;
  const f = deadlineTransportFixture();
  f.Module._lmdj_web_audio_set_count_in_metronome = value => {
    choices.push(value); return accepted;
  };
  const host = f.host;
  host.runtimeInitialized = false;
  assert.equal(host.setCountInMetronome(true), false);
  assert.deepEqual(choices, [], "an uninitialized Runtime never reaches Native");
  host.runtimeInitialized = true;
  host.manifestReady = true;
  assert.equal(host.setCountInMetronome(true), true);
  assert.equal(host.setCountInMetronome(false), true);
  assert.deepEqual(choices, [1, 0]);
  accepted = 0;
  assert.equal(host.setCountInMetronome(true), false);
  assert.deepEqual(choices, [1, 0, 1]);
  assert.throws(() => host.setCountInMetronome(1), {name: "TypeError"});
  assert.deepEqual(choices, [1, 0, 1]);
  void host.transport.terminate();
  assert.equal(host.setCountInMetronome(false), false);
  assert.deepEqual(choices, [1, 0, 1], "a terminated owner cannot publish a later choice");
});

test("actual count-in metronome entry point refuses a Runtime without the native export", () => {
  const window = {Worker: class {}};
  actualBrowserRuntimePublication({Module: {}, window,
    crypto: {randomUUID: () => "00000000-0000-4000-8000-000000000001"}});
  const host = window.lmdjWebRuntimeHost;
  host.runtimeInitialized = true;
  host.manifestReady = true;
  assert.equal(host.setCountInMetronome(true), false);
});

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

// Actual pre-JS transport, controlled monotonic time, modeled Bridge replies.
// This observes local Error provenance; it supplies no Native retirement ACK.
function deadlineTransportFixture({cancel = () => 1, queryCancel = () => 1,
  onSubmit = () => {}, diagnosticConsole, terminalCompleted = () => 0,
  consumeTerminal = () => 0} = {}) {
  let now = 100;
  let timerId = 0;
  let pointer = 8;
  const heap = new Uint8Array(1024 * 1024);
  const heap32 = new Uint32Array(heap.buffer);
  const timers = new Map();
  const submissions = [];
  const cancellations = [];
  const responses = [];
  const diagnosticLines = [];
  const window = {Worker: class {},
    setTimeout(callback, delay) {
      const id = ++timerId;
      timers.set(id, {callback, at: now + delay});
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
  };
  const Module = {ccall(name, _returnType, _types, args) {
    if (name === "lmdj_web_host_submit") {
      const envelope = JSON.parse(new TextDecoder().decode(
        heap.slice(args[0], args[0] + args[1])));
      submissions.push({envelope, deadlineAt: args[4]});
      onSubmit(envelope);
      return 0;
    }
    if (name === "lmdj_web_host_cancel_request" || name === "lmdj_web_host_cancel_query") {
      cancellations.push({name, requestId: args[0]});
      return name === "lmdj_web_host_cancel_query" ? queryCancel() : cancel(args[0]);
    }
    if (name === "lmdj_web_host_terminal_release_completed") return terminalCompleted();
    assert.equal(name, "lmdj_web_host_consume_terminal_release");
    return consumeTerminal();
  }};
  const channels = actualBrowserRuntimePublication({Module, window,
    crypto: {randomUUID: () => "00000000-0000-4000-8000-000000000099"},
    globals: {
      performance: {now: () => now, timeOrigin: 10_000},
      console: diagnosticConsole === undefined
        ? {warn(line) { diagnosticLines.push(line); }} : diagnosticConsole,
      HEAPU8: heap, HEAPU32: heap32,
      _malloc(size) { const result = pointer; pointer += (size + 7) & ~7; return result; },
      _free() {},
      _lmdj_web_host_poll(output, _capacity, requiredPointer) {
        const response = responses.shift();
        if (!response) return 0;
        const bytes = new TextEncoder().encode(JSON.stringify(response));
        heap.set(bytes, output);
        heap32[requiredPointer >> 2] = bytes.length;
        return 1;
      },
    },
  });
  const host = window.lmdjWebRuntimeHost;
  host.runtimeInitialized = true;
  return {host, Module, transport: host.transport, submissions, cancellations, responses, diagnosticLines,
    releaseRequests: () => channels.flatMap((channel) => channel.posted)
      .filter((message) => message.type === "release-and-close").length,
    advance(to) {
      // Simulate a delayed browser timer without changing any product budget.
      now = to;
      const due = [...timers].filter(([, timer]) => timer.at <= now);
      for (const [id, timer] of due) {
        if (!timers.delete(id)) continue;
        timer.callback();
      }
    },
  };
}

const deadlineRequestId = "00000000-0000-4000-8000-000000000001";
function deadlineRequest(operation = "project.inspect", request_id = deadlineRequestId) {
  return {protocol_version: 1, request_id, operation, payload: {private: "not diagnostics"}};
}
function deadlineDetails(operation = "project.inspect", cancel_return = 1) {
  return {operation, request_id: deadlineRequestId, deadline_ms: 1000,
    deadline_at_ms: 1100, cancel_return};
}

test("actual transport keeps the originating deadline Error for pending and late callers", async () => {
  const request = deadlineRequest();
  const f = deadlineTransportFixture({onSubmit() { request.operation = "history.inspect"; }});
  const failures = [];
  f.transport.subscribeFailure((error) => failures.push(error));
  const first = f.transport.send(request, {deadlineMs: 1000}).catch((error) => error);
  const other = f.transport.send(deadlineRequest("sample.inspect",
    "00000000-0000-4000-8000-000000000002"), {deadlineMs: 30_000}).catch((error) => error);
  f.advance(1100);
  const original = await first;
  assert.equal(original.code, "HOST_TIMEOUT");
  assert.deepEqual({...original.details}, deadlineDetails(), "the first timed-out RPC must be identifiable");
  assert.equal(await other, original);
  assert.equal(await f.transport.send(deadlineRequest()).catch((error) => error), original);
  assert.deepEqual(failures, [original]);
  assert.equal(f.diagnosticLines.length, 1, "the first fatal deadline must be captured without System navigation");
  const prefix = "lmdj-web-host-deadline-diagnostic ";
  assert.ok(f.diagnosticLines[0].startsWith(prefix));
  assert.deepEqual(JSON.parse(f.diagnosticLines[0].slice(prefix.length)),
    {code: "HOST_TIMEOUT", ...deadlineDetails()});
  assert.equal(Object.isFrozen(original.details), true);
  assert.equal(f.submissions[0].envelope.operation, "project.inspect");
  assert.equal(f.submissions[0].deadlineAt, 11_100);
  assert.equal(f.transport.terminalOwnerReleased, false);
});

test("an owner that never confirms its release is ended by force after the grace period", async () => {
  const f = deadlineTransportFixture();
  let cleaned = false;
  void f.transport.terminate().then(() => { cleaned = true; });
  const retained = f.transport.sendRetained({...deadlineRequest("pattern.transport.input.inspect",
    "00000000-0000-4000-8000-000000000003"), payload: {
    command_id: "00000000-0000-4000-8000-000000000004", runtime_generation: "1",
    frame_epoch: "1", ticket: "1", consume: false,
  }}, {deadlineMs: 30_000}).catch((error) => error);
  f.advance(5099);
  await Promise.resolve();
  assert.equal(cleaned, false, "the real release keeps its full grace period");
  assert.equal(f.transport.terminalOwnerEnded, false);
  f.advance(5100);
  await Promise.resolve();
  assert.equal(cleaned, true, "a blocked owner must not hold its storage forever");
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.transport.terminalOwnerEnded, true, "a forced end is reported without a release receipt");
  const error = await retained;
  assert.equal(error.code, "HOST_RESTART_REQUIRED");
  assert.deepEqual([error.details.operation, error.details.terminal_state,
    error.details.mutation_outcome, error.details.pending],
  ["pattern.transport.input.inspect", "restart-required", "unknown", true],
  "a forced end reports the documented restart-required shape");
});

test("an unsettled claimed publication ends its blocked owner without the grace wait", async () => {
  let calls = 0;
  const f = deadlineTransportFixture({cancel: () => ++calls === 1 ? 0 : -1});
  const pending = f.transport.send(deadlineRequest(), {deadlineMs: 1000}).catch((error) => error);
  f.advance(1100);
  f.advance(2100);
  assert.equal((await pending).code, "HOST_RESTART_REQUIRED");
  let cleaned = false;
  void f.transport.terminate().then(() => { cleaned = true; });
  f.advance(2116);
  await Promise.resolve();
  assert.equal(cleaned, true, "a receipt that can never arrive must not hold storage for 5 s");
  assert.equal(f.transport.terminalOwnerReleased, false);
});

test("a retained request stuck in a claimed publication also ends the blocked owner promptly", async () => {
  // The normal request is cancelled; the retained one's publication is claimed.
  const f = deadlineTransportFixture({cancel: (requestId) =>
    requestId === "00000000-0000-4000-8000-000000000003" ? 0 : 1});
  let cleaned = false;
  const first = f.transport.send(deadlineRequest(), {deadlineMs: 1000}).catch((error) => error);
  f.advance(1100);
  assert.equal((await first).code, "HOST_TIMEOUT");
  void f.transport.terminate().then(() => { cleaned = true; });
  const retained = f.transport.sendRetained({...deadlineRequest("pattern.transport.input.inspect",
    "00000000-0000-4000-8000-000000000003"), payload: {
    command_id: "00000000-0000-4000-8000-000000000004", runtime_generation: "1",
    frame_epoch: "1", ticket: "1", consume: false,
  }}, {deadlineMs: 1000}).catch((error) => error);
  f.advance(2100);
  f.advance(3100);
  assert.equal((await retained).code, "HOST_RESTART_REQUIRED");
  f.advance(3116);
  await Promise.resolve();
  assert.equal(cleaned, true, "the 5 s grace scheduled at 1100 must not hold a blocked owner");
  assert.equal(f.transport.terminalOwnerReleased, false);
});

test("terminate requests the release before any terminal consume", async () => {
  let consumes = 0;
  const f = deadlineTransportFixture({consumeTerminal: () => { consumes += 1; return -1; }});
  void f.transport.terminate();
  await Promise.resolve();
  assert.equal(f.releaseRequests(), 1);
  assert.equal(consumes, 0, "Native cannot have completed a release that was never requested");
});

test("a released owner draining retained requests is not asked to release again", async () => {
  let completed = 0;
  const f = deadlineTransportFixture({terminalCompleted: () => completed,
    consumeTerminal: () => completed});
  void f.transport.terminate();
  const retained = f.transport.sendRetained({...deadlineRequest("pattern.transport.input.inspect",
    "00000000-0000-4000-8000-000000000003"), payload: {
    command_id: "00000000-0000-4000-8000-000000000004", runtime_generation: "1",
    frame_epoch: "1", ticket: "1", consume: false,
  }}, {deadlineMs: 30_000}).catch((error) => error);
  completed = 1;
  f.advance(200);
  assert.equal(f.transport.terminalOwnerReleased, true);
  f.advance(5100);
  f.advance(10_100);
  assert.equal(f.releaseRequests(), 1, "the closed control worker needs no repeated release request");
  f.advance(31_000);
  await retained;
});

test("an owner that confirms its release completes cleanup without force", async () => {
  const f = deadlineTransportFixture({terminalCompleted: () => 1, consumeTerminal: () => 1});
  let cleaned = false;
  void f.transport.terminate().then(() => { cleaned = true; });
  await Promise.resolve();
  assert.equal(cleaned, true);
  assert.equal(f.transport.terminalOwnerReleased, true);
});

test("actual settlement watchdog retains the first cancel result without another deadline cancellation", async () => {
  let calls = 0;
  const f = deadlineTransportFixture({cancel: () => ++calls === 1 ? 0 : -1});
  const pending = f.transport.send(deadlineRequest(), {deadlineMs: 1000}).catch((error) => error);
  f.advance(1100);
  f.advance(1500);
  assert.equal(f.cancellations.length, 1, "settlement observation must not repeat cancellation");
  f.advance(2100);
  const error = await pending;
  assert.equal(error.code, "HOST_RESTART_REQUIRED");
  assert.deepEqual({...error.details}, {...deadlineDetails("project.inspect", 0),
    terminal_state: "restart-required", mutation_outcome: "unknown"});
  assert.ok(calls > 1, "terminal cleanup made a later cancellation; it must not overwrite provenance");
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.diagnosticLines.length, 1, "settlement failure emits exactly one first-fault capsule");
  assert.equal(JSON.parse(f.diagnosticLines[0].slice("lmdj-web-host-deadline-diagnostic ".length)).code,
    "HOST_RESTART_REQUIRED");
});

test("actual query abort watchdog preserves the original deadline and query cancellation result", async () => {
  const f = deadlineTransportFixture({queryCancel: () => 0});
  const abort = new AbortController();
  const pending = f.transport.send(deadlineRequest(), {deadlineMs: 1000,
    cancelQuery: true, signal: abort.signal}).catch((error) => error);
  abort.abort();
  f.advance(600);
  assert.deepEqual(f.cancellations.map((entry) => entry.name), ["lmdj_web_host_cancel_query"]);
  f.advance(1100);
  const error = await pending;
  assert.equal(error.code, "HOST_RESTART_REQUIRED");
  assert.deepEqual({...error.details}, {...deadlineDetails("project.inspect", 0),
    terminal_state: "restart-required", mutation_outcome: "unknown"});
});

test("actual retained deadline preserves its own provenance without replacing the sealed first fault", async () => {
  const f = deadlineTransportFixture();
  const first = f.transport.send(deadlineRequest(), {deadlineMs: 1000}).catch((error) => error);
  f.advance(1100);
  const original = await first;
  const retained = f.transport.sendRetained({...deadlineRequest("pattern.transport.input.inspect",
    "00000000-0000-4000-8000-000000000003"), payload: {
    command_id: "00000000-0000-4000-8000-000000000004", runtime_generation: "1",
    frame_epoch: "1", ticket: "1", consume: false,
  }}, {deadlineMs: 1000}).catch((error) => error);
  f.advance(2100);
  const error = await retained;
  assert.equal(error.code, "HOST_TIMEOUT");
  assert.deepEqual({...error.details}, {operation: "pattern.transport.input.inspect",
    request_id: "00000000-0000-4000-8000-000000000003", deadline_ms: 1000,
    deadline_at_ms: 2100, cancel_return: 1, pending: true});
  assert.equal(await f.transport.send(deadlineRequest()).catch((error) => error), original);
  assert.equal(f.diagnosticLines.length, 1, "retained timeout cannot emit a second fatal capsule");
  assert.equal(f.transport.terminalOwnerReleased, false);
});

test("actual successful transport reply and intentional termination keep their original behavior", async () => {
  const f = deadlineTransportFixture();
  const pending = f.transport.send(deadlineRequest(), {deadlineMs: 1000});
  const response = {request_id: deadlineRequestId, ok: true, result: {revision: 7}};
  f.responses.push(response);
  f.advance(116);
  assert.deepEqual(JSON.parse(JSON.stringify(await pending)), response);
  const failures = [];
  f.transport.subscribeFailure((error) => failures.push(error));
  void f.transport.terminate();
  assert.equal(failures.length, 1);
  assert.equal(failures[0].code, "HOST_STATE_INVALID");
  assert.equal(failures[0].message, "formal Web Host transport is terminated");
  assert.deepEqual({...failures[0].details}, {});
  assert.deepEqual(f.diagnosticLines, [], "normal terminate is not a fatal deadline diagnostic");
  assert.equal(f.transport.terminalOwnerReleased, false);
});

for (const diagnosticConsole of [null, {warn() { throw new Error("console unavailable"); }}]) {
test(`actual fatal deadline still rejects and starts cleanup when diagnostic console ${diagnosticConsole === null ? "is missing" : "throws"}`, async () => {
  const f = deadlineTransportFixture({diagnosticConsole});
  const failures = [];
  f.transport.subscribeFailure((error) => failures.push(error));
  const pending = f.transport.send(deadlineRequest(), {deadlineMs: 1000}).catch((error) => error);
  f.advance(1100);
  const original = await pending;
  assert.equal(original.code, "HOST_TIMEOUT");
  assert.deepEqual({...original.details}, deadlineDetails());
  assert.deepEqual(failures, [original]);
  assert.equal(await f.transport.send(deadlineRequest()).catch((error) => error), original);
  assert.ok(f.cancellations.length >= 2, "fatal cleanup still attempts the original pending owner");
  assert.equal(f.transport.terminalOwnerReleased, false);
});
}
