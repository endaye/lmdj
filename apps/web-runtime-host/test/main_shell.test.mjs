import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testRoot = dirname(fileURLToPath(import.meta.url));
const hostRoot = resolve(testRoot, "..");

async function mainModule() {
  return import("../src/main.mjs");
}

class FakeTarget {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  dispatchEvent(event) {
    Object.defineProperty(event, "target", {
      configurable: true,
      value: event.target ?? this,
    });
    for (const listener of this.listeners.get(event.type) ?? []) {
      listener(event);
    }
    return true;
  }
}

class FakeElement extends FakeTarget {
  constructor(id, dataset = {}) {
    super();
    this.id = id;
    this.dataset = dataset;
    this.textContent = "";
    this.disabled = false;
    this.attributes = new Map();
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }
}

function fakeDom() {
  const elements = new Map();
  for (const id of [
    "host-state",
    "diagnostics",
    "diagnostic-project-load",
    "diagnostic-project-state",
    "audio-activate",
    "audio-suspend",
    "midi-enable",
  ]) {
    elements.set(id, new FakeElement(id));
  }
  const pads = [];
  for (let flatSlot = 0; flatSlot < 64; flatSlot += 1) {
    const pad = new FakeElement(`pad-${flatSlot}`, {
      bank: String(Math.floor(flatSlot / 16)),
      pad: String(flatSlot % 16),
    });
    pad.setAttribute("aria-pressed", "false");
    pads.push(pad);
    elements.set(pad.id, pad);
  }
  const document = new FakeTarget();
  document.visibilityState = "visible";
  document.getElementById = (id) => elements.get(id) ?? null;
  document.querySelectorAll = (selector) =>
    selector === "button[data-bank][data-pad]" ? pads : [];
  const window = new FakeTarget();
  return { document, window, elements, pads };
}

class FakeAudioContext extends FakeTarget {
  constructor(options) {
    super();
    this.options = options;
    this.sampleRate = options.sampleRate;
    this.state = "suspended";
    this.closeCalls = 0;
    this.suspendCalls = 0;
  }

  async resume() {
    this.state = "running";
    this.dispatchEvent(new Event("statechange"));
  }

  async suspend() {
    this.suspendCalls += 1;
    this.state = "suspended";
    this.dispatchEvent(new Event("statechange"));
  }

  async close() {
    this.closeCalls += 1;
    this.state = "closed";
  }
}

function uuidSource() {
  let next = 1;
  return {
    randomUUID() {
      const suffix = String(next).padStart(12, "0");
      next += 1;
      return `00000000-0000-0000-0000-${suffix}`;
    },
  };
}

function responseFor(request, result) {
  return {
    protocol_version: 1,
    request_id: request.request_id,
    ok: true,
    result,
  };
}

function errorResponseFor(request, code) {
  return {
    protocol_version: 1,
    request_id: request.request_id,
    ok: false,
    error: { code, message: code, details: {} },
  };
}

function localStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

function harness({ status = { control_generation: 7, acknowledged_generation: 7 }, timers } = {}) {
  const dom = fakeDom();
  const calls = [];
  const notifications = new Set();
  const contexts = [];
  const runtimeWorker = new FakeTarget();
  const worklet = new FakeTarget();
  let sequence = 1;
  let currentStatus = status;
  let cleanupCalls = 0;
  let projectRevision = 0;
  const project = {
    assets: {},
    banks: Array.from({ length: 4 }, (_, bank) => ({
      pads: Array.from({ length: 16 }, (_, pad) => ({
        bank,
        pad,
        asset_id: null,
      })),
    })),
  };
  const transport = {
    async send(request, options) {
      calls.push({ operation: request.operation, payload: request.payload, options });
      switch (request.operation) {
        case "project.open":
          return responseFor(request, { project_revision: projectRevision });
        case "project.inspect":
          return responseFor(request, { project_revision: projectRevision, project });
        case "asset.import":
          project.assets[request.payload.asset_id] = {
            asset_id: request.payload.asset_id,
          };
          projectRevision += 1;
          return responseFor(request, { project_revision: projectRevision });
        case "pad.assign":
          project.banks[request.payload.slot.bank].pads[
            request.payload.slot.pad
          ].asset_id = request.payload.asset_id;
          projectRevision += 1;
          return responseFor(request, { project_revision: projectRevision });
        case "snapshot.reload":
          return responseFor(request, { runtime_ready: true, generation: 7 });
        case "audio.activate":
          return responseFor(request, { state: "running", changed: true, generation: 7 });
        case "audio.suspend":
          return responseFor(request, { state: "audio-suspended", changed: true });
        case "host.status":
          return responseFor(request, currentStatus);
        case "trigger": {
          const admitted = sequence;
          sequence += 1;
          return responseFor(request, { sequence: admitted, status: "enqueued" });
        }
        case "take.begin":
          return responseFor(request, { take_id: request.payload.take_id });
        case "host.close":
          return responseFor(request, { state: "closed" });
        default:
          throw new Error(`unexpected operation: ${request.operation}`);
      }
    },
    subscribe(listener) {
      notifications.add(listener);
      return () => notifications.delete(listener);
    },
    emit(event, payload) {
      for (const listener of notifications) {
        listener({ protocol_version: 1, event, payload });
      }
    },
  };
  const storage = localStorage();
  const crypto = uuidSource();
  crypto.subtle = webcrypto.subtle;
  const capabilities = Object.fromEntries(
    [
      "secureContext",
      "crossOriginIsolated",
      "sharedArrayBuffer",
      "webAssembly",
      "audioWorklet",
      "opfs",
      "opfsSyncAccessHandle",
      "opfsWritableReplace",
    ].map((name) => [name, true]),
  );
  const options = {
    ...dom,
    navigator: { requestMIDIAccess: async () => ({ inputs: new Map() }) },
    capabilities,
    crypto,
    storage,
    verifyManifest: async () => ({
      product_build: "1.0.13.0",
      host_version: "1.0.0",
      protocol_version: 1,
    }),
    loadRuntime: async () => ({
      registerAudioContext: () => 1,
      startAudioWorklet: async () => ({ ok: true }),
      workers: [runtimeWorker],
      worklet,
    }),
    createAudioContext(options) {
      const context = new FakeAudioContext(options);
      contexts.push(context);
      return context;
    },
    transport,
    runtimeTerminator: async () => {
      cleanupCalls += 1;
    },
    timers,
  };
  return {
    options,
    calls,
    contexts,
    runtimeWorker,
    worklet,
    transport,
    dom,
    setStatus(value) {
      currentStatus = value;
    },
    get cleanupCalls() {
      return cleanupCalls;
    },
  };
}

async function settle() {
  await new Promise((resolvePromise) => setImmediate(resolvePromise));
  await new Promise((resolvePromise) => setImmediate(resolvePromise));
}

function deferred() {
  let resolvePromise;
  let rejectPromise;
  const promise = new Promise((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  return { promise, resolve: resolvePromise, reject: rejectPromise };
}

test("static shell has only local external assets and 64 exact Pad identities", async () => {
  const html = await readFile(resolve(hostRoot, "index.html"), "utf8");
  assert.equal(/<script(?![^>]*\bsrc=)[^>]*>/i.test(html), false);
  assert.equal(/<style\b/i.test(html), false);
  assert.equal(/(?:src|href)=["'](?:https?:)?\/\//i.test(html), false);
  assert.equal(html.includes("\n+        <button"), false);
  assert.match(html, /<link[^>]+href=["']\.\/styles\.css["']/i);
  assert.match(html, /<script[^>]+src=["']\.\/src\/main\.mjs["']/i);

  const pads = [...html.matchAll(/<button\b([^>]*)>/gi)].filter((match) =>
    /\bid=["']pad-\d+["']/.test(match[1]),
  );
  assert.equal(pads.length, 64);
  pads.forEach((match, flatSlot) => {
    const attributes = match[1];
    assert.match(attributes, new RegExp(`\\bid=["']pad-${flatSlot}["']`));
    assert.match(attributes, new RegExp(`\\bdata-bank=["']${Math.floor(flatSlot / 16)}["']`));
    assert.match(attributes, new RegExp(`\\bdata-pad=["']${flatSlot % 16}["']`));
    assert.match(attributes, /\baria-pressed=["']false["']/);
  });
  for (const id of [
    "diagnostic-project-load",
    "diagnostic-project-state",
    "audio-activate",
    "audio-suspend",
    "midi-enable",
    "host-state",
    "diagnostics",
  ]) {
    assert.match(html, new RegExp(`\\bid=["']${id}["']`));
  }
  assert.match(
    html,
    /id=["']diagnostic-project-load["'][^>]*>[\s\S]*id=["']diagnostic-project-state["'][^>]*>[\s\S]*id=["']audio-activate["'][^>]*\bdisabled\b/,
  );
  assert.match(
    html,
    /id=["']diagnostic-project-state["'][^>]*\baria-live=["']polite["'][^>]*>idle</,
  );
  assert.match(html, /id=["']host-state["'][^>]*>cold</);
});

test("controller gates audio activation until the diagnostic project is ready", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);

  await controller.start();
  assert.equal(fixture.dom.elements.get("audio-activate").disabled, true);
  assert.equal(await controller.activateAudio(), false);
  assert.equal(fixture.contexts.length, 0);
  assert.equal(
    fixture.calls.some(({ operation }) => operation === "audio.activate"),
    false,
  );

  assert.equal(await controller.loadDiagnosticProject(), true);
  assert.equal(controller.diagnostics().diagnostic_project_state, "ready");
  assert.ok(controller.diagnostics().diagnostic_project_generation > 0);
  assert.equal(fixture.dom.elements.get("audio-activate").disabled, false);
  assert.equal(await controller.activateAudio(), true);

  const imported = fixture.calls.find(({ operation }) => operation === "asset.import");
  assert.ok(imported.options.sidecar instanceof Uint8Array);
  assert.equal(imported.options.sidecar.byteLength, 9_644);
  assert.equal(imported.payload.sidecar.sidecar_bytes, 9_644);
});

test("diagnostic project load serializes double clicks and renders loading state", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const originalSend = fixture.transport.send.bind(fixture.transport);
  const blocked = deferred();
  let openRequest = null;
  let openCalls = 0;
  fixture.transport.send = (request, options) => {
    if (request.operation === "project.open") {
      openCalls += 1;
      openRequest = request;
      return blocked.promise;
    }
    return originalSend(request, options);
  };
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();

  const first = controller.loadDiagnosticProject();
  const second = controller.loadDiagnosticProject();
  await settle();
  assert.equal(openCalls, 1);
  assert.equal(fixture.dom.elements.get("diagnostic-project-load").disabled, true);
  assert.equal(
    fixture.dom.elements.get("diagnostic-project-load").getAttribute("aria-busy"),
    "true",
  );
  assert.equal(fixture.dom.elements.get("diagnostic-project-state").textContent, "loading");

  blocked.resolve(responseFor(openRequest, { project_revision: 0 }));
  assert.deepEqual(await Promise.all([first, second]), [true, true]);
  assert.equal(fixture.dom.elements.get("diagnostic-project-load").disabled, false);
  assert.equal(
    fixture.dom.elements.get("diagnostic-project-load").getAttribute("aria-busy"),
    "false",
  );
});

test("diagnostic project errors remain retryable without consuming Host error_code", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const originalSend = fixture.transport.send.bind(fixture.transport);
  let attempts = 0;
  fixture.transport.send = (request, options) => {
    if (request.operation === "project.open" && attempts++ === 0) {
      return Promise.resolve(errorResponseFor(request, "IO_ERROR"));
    }
    return originalSend(request, options);
  };
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();

  assert.equal(await controller.loadDiagnosticProject(), false);
  assert.equal(controller.state, "audio-suspended");
  assert.equal(controller.diagnostics().error_code, null);
  assert.equal(controller.diagnostics().diagnostic_project_state, "error");
  assert.equal(controller.diagnostics().diagnostic_project_error_code, "IO_ERROR");
  assert.equal(fixture.dom.elements.get("diagnostic-project-load").disabled, false);
  assert.equal(fixture.dom.elements.get("audio-activate").disabled, true);

  assert.equal(await controller.loadDiagnosticProject(), true);
  assert.equal(controller.diagnostics().diagnostic_project_state, "ready");
  assert.equal(controller.diagnostics().diagnostic_project_error_code, undefined);
});

test("diagnostic restart-required is the only terminal preparation failure", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  fixture.transport.send = (request) =>
    Promise.resolve(errorResponseFor(request, "HOST_RESTART_REQUIRED"));
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();

  assert.equal(await controller.loadDiagnosticProject(), false);
  assert.equal(controller.state, "failed");
  assert.equal(controller.diagnostics().error_code, "HOST_RESTART_REQUIRED");
  assert.equal(
    controller.diagnostics().diagnostic_project_state,
    "restart-required",
  );
  assert.equal(
    fixture.dom.elements.get("diagnostic-project-state").textContent,
    "restart-required",
  );
});

test("diagnostic project diagnostics are allowlisted and pagehide invalidates readiness", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  assert.equal(await controller.loadDiagnosticProject(), true);

  const serialized = JSON.stringify(controller.diagnostics());
  assert.equal(serialized.includes("project_id"), false);
  assert.equal(serialized.includes("pattern_id"), false);
  assert.equal(serialized.includes("asset_id"), false);
  assert.equal(serialized.includes("00000000-0000-0000-0000"), false);

  await controller.observePageHide({ persisted: true });
  assert.equal(controller.diagnostics().diagnostic_project_state, "error");
  assert.equal(controller.diagnostics().diagnostic_project_generation, undefined);
  assert.equal(fixture.dom.elements.get("audio-activate").disabled, true);
});

test("diagnostic project transport errors do not disclose hostile codes", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const hostileCode = "/private/opfs/diagnostic-project-secret";
  const fixture = harness();
  fixture.transport.send = (request) =>
    Promise.resolve(errorResponseFor(request, hostileCode));
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();

  assert.equal(await controller.loadDiagnosticProject(), false);
  assert.equal(
    controller.diagnostics().diagnostic_project_error_code,
    "HOST_PROTOCOL_MISMATCH",
  );
  assert.equal(
    fixture.dom.elements.get("diagnostics").textContent.includes(hostileCode),
    false,
  );
});

test("source shell verifies manifest before loading runtime and exposes exact Host state", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const order = [];
  const fixture = harness();
  fixture.options.verifyManifest = async () => {
    order.push("manifest");
    return { product_build: "1.0.13.0", host_version: "1.0.0", protocol_version: 1 };
  };
  fixture.options.loadRuntime = async () => {
    order.push("runtime");
    return {
      registerAudioContext: () => 1,
      startAudioWorklet: async () => ({ ok: true }),
      workers: [fixture.runtimeWorker],
      worklet: fixture.worklet,
    };
  };
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  assert.deepEqual(order, ["manifest", "runtime"]);
  assert.equal(controller.state, "audio-suspended");
  assert.equal(fixture.dom.elements.get("host-state").textContent, "audio-suspended");
});

test("controller preserves a late authoritative transport success", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const scheduled = [];
  const fixture = harness({
    timers: {
      setTimeout(callback, milliseconds) {
        const record = { callback, milliseconds, cleared: false };
        scheduled.push(record);
        return record;
      },
      clearTimeout(record) {
        record.cleared = true;
      },
    },
  });
  const originalSend = fixture.options.transport.send.bind(
    fixture.options.transport);
  const late = deferred();
  let lateRequest = null;
  fixture.options.transport.send = (request, options) => {
    if (request.operation === "audio.activate") {
      lateRequest = request;
      assert.deepEqual(options, { deadlineMs: 1_000 });
      return late.promise;
    }
    return originalSend(request, options);
  };
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();

  const activation = controller.activateAudio();
  await settle();
  for (const timer of scheduled.filter((record) => !record.cleared)) {
    timer.callback();
  }
  await settle();
  late.resolve(responseFor(lateRequest, {
    state: "running",
    changed: true,
    generation: 7,
  }));

  assert.equal(await activation, true);
  assert.equal(controller.state, "running");
  assert.equal(scheduled.length, 0);
});

test("controller preserves a late authoritative transport error", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const scheduled = [];
  const fixture = harness({
    timers: {
      setTimeout(callback, milliseconds) {
        const record = { callback, milliseconds, cleared: false };
        scheduled.push(record);
        return record;
      },
      clearTimeout(record) {
        record.cleared = true;
      },
    },
  });
  const originalSend = fixture.options.transport.send.bind(
    fixture.options.transport);
  const late = deferred();
  let lateRequest = null;
  fixture.options.transport.send = (request, options) => {
    if (request.operation === "audio.activate") {
      lateRequest = request;
      assert.deepEqual(options, { deadlineMs: 1_000 });
      return late.promise;
    }
    return originalSend(request, options);
  };
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();

  const activation = controller.activateAudio();
  await settle();
  for (const timer of scheduled.filter((record) => !record.cleared)) {
    timer.callback();
  }
  await settle();
  late.resolve({
    protocol_version: 1,
    request_id: lateRequest.request_id,
    ok: false,
    error: { code: "IO_ERROR", message: "late rejection", details: {} },
  });

  assert.equal(await activation, false);
  assert.equal(controller.state, "failed");
  assert.equal(controller.diagnostics().error_code, "IO_ERROR");
  assert.equal(scheduled.length, 0);
});

test("default source-shell hash gate fails before runtime load on mismatch", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  for (const [digest, expectedState, expectedLoads] of [
    ["8751198714fa0a46eb42c0740550d1baaecf465c7e63f5d1d1ddfa6a2d61d4ed", "audio-suspended", 1],
    ["0".repeat(64), "failed", 0],
  ]) {
    const fixture = harness();
    let loads = 0;
    fixture.options.crypto = webcrypto;
    delete fixture.options.verifyManifest;
    fixture.options.document.querySelector = () => ({
      getAttribute: () => digest,
    });
    fixture.options.loadRuntime = async () => {
      loads += 1;
      return {
        registerAudioContext: () => 1,
        startAudioWorklet: async () => ({ ok: true }),
        workers: [],
      };
    };
    const controller = createWebRuntimeHostController(fixture.options);
    await controller.start();
    assert.equal(controller.state, expectedState);
    assert.equal(loads, expectedLoads);
  }
});

test("packaged runtime locator binds the verified AudioWorklet module and Wasm", async () => {
  const { createPackagedRuntimeLocator } = await mainModule();
  const locateFile = createPackagedRuntimeLocator({
    baseURI: "https://runtime.test/product/index.html",
    runtimeScriptURL:
      "https://runtime.test/product/assets/runtime.1111111111111111111111111111111111111111111111111111111111111111.js",
    runtimeWasmURL:
      "https://runtime.test/product/assets/runtime.2222222222222222222222222222222222222222222222222222222222222222.wasm",
  });

  assert.equal(
    locateFile("lmdj-web-runtime-host.js"),
    "https://runtime.test/product/assets/runtime.1111111111111111111111111111111111111111111111111111111111111111.js",
  );
  assert.equal(
    locateFile("runtime.2222222222222222222222222222222222222222222222222222222222222222.wasm"),
    "https://runtime.test/product/assets/runtime.2222222222222222222222222222222222222222222222222222222222222222.wasm",
  );
  assert.equal(
    locateFile("other.wasm"),
    "https://runtime.test/product/other.wasm",
  );
  assert.equal(
    locateFile("support.data"),
    "https://runtime.test/product/support.data",
  );
});

test("flattens Project Pad address exactly once immediately before the unified route", async () => {
  const { flattenPadSlot } = await mainModule();
  assert.equal(flattenPadSlot({ bank: 0, pad: 0 }), 0);
  assert.equal(flattenPadSlot({ bank: 2, pad: 5 }), 37);
  assert.equal(flattenPadSlot({ bank: 3, pad: 15 }), 63);
  assert.throws(() => flattenPadSlot({ bank: 4, pad: 0 }), RangeError);
  const source = await readFile(resolve(hostRoot, "src/main.mjs"), "utf8");
  assert.equal(source.match(/bank\s*\*\s*16\s*\+\s*pad/g)?.length, 1);
});

test("Pointer mouse fallback and cancellation own observable pressed state", async () => {
  const { createPointerAdapter } = await import("../src/input_adapters.mjs");
  const pointer = createPointerAdapter({
    trigger: () => {},
    velocity: 100,
    now: () => 0,
  });
  assert.equal(pointer.mouseDown({ button: 0 }, 3), true);
  assert.equal(pointer.diagnostics().pressed_count, 1);
  pointer.clearPressed();
  pointer.pointerDown({ isPrimary: true, button: 0, pointerId: 4 }, 4);
  assert.equal(pointer.diagnostics().pressed_count, 1);
  pointer.pointerCancel({ pointerId: 4 });
  assert.equal(pointer.diagnostics().pressed_count, 0);
});

test("DOM mouse fallback releases aria-pressed on mouseup", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  const down = new Event("mousedown");
  Object.defineProperty(down, "button", { value: 0 });
  fixture.dom.pads[0].dispatchEvent(down);
  assert.equal(fixture.dom.pads[0].getAttribute("aria-pressed"), "true");
  fixture.dom.pads[0].dispatchEvent(new Event("mouseup"));
  assert.equal(fixture.dom.pads[0].getAttribute("aria-pressed"), "false");
});

test("rejects Trigger and take.begin before initial activation without replay", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  assert.equal(await controller.trigger(0, 100), false);
  assert.equal(await controller.beginTake("00000000-0000-0000-0000-000000000123", 0), false);
  assert.equal(fixture.calls.some(({ operation }) => operation === "trigger"), false);
  assert.equal(fixture.calls.some(({ operation }) => operation === "take.begin"), false);

  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  assert.equal(controller.state, "running");
  assert.deepEqual(fixture.contexts[0].options, { sampleRate: 48_000 });
  assert.equal(fixture.calls.filter(({ operation }) => operation === "trigger").length, 0);
});

test("interruption closes admission synchronously, clears pressed state, and coalesces suspend", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  fixture.options.window.dispatchEvent(new Event("keydown", { bubbles: true }));
  controller.handleKeyDown({ code: "KeyA", repeat: false });
  assert.equal(controller.diagnostics().pressed_count, 1);

  controller.observeVisibility(true);
  assert.equal(controller.state, "interrupted");
  assert.equal(controller.diagnostics().pressed_count, 0);
  assert.equal(await controller.trigger(1, 100), false);
  controller.observePageHide({ persisted: true });
  await settle();
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.suspend").length, 1);
});

test("same adverse condition coalesces but a new adverse edge creates a new epoch", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  controller.observeVisibility(true);
  await settle();
  assert.equal(controller.state, "recovering");
  controller.observeVisibility(true);
  await settle();
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.suspend").length, 1);

  controller.observeVisibility(false);
  controller.observeVisibility(true);
  await settle();
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.suspend").length, 2);
  assert.equal(controller.state, "recovering");
});

test("delayed persisted pagehide coalesces with the active hidden episode", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();

  controller.observeVisibility(true);
  await settle();
  assert.equal(controller.state, "recovering");
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.suspend").length, 1);

  await controller.observePageHide({ persisted: true });
  await settle();
  assert.equal(controller.state, "recovering");
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.suspend").length, 1);
});

test("a fresh Context adverse edge supersedes an active page episode and invalidates its probe", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();

  controller.observeVisibility(true);
  await settle();
  controller.observeRuntimeStatus({ control_generation: 7, acknowledged_generation: 7 });
  assert.equal(await controller.trigger(1, 100), true);

  const context = fixture.contexts[0];
  context.state = "suspended";
  context.dispatchEvent(new Event("statechange"));
  await settle();
  fixture.transport.emit("runtime.trigger_outcomes", {
    events: [{ sequence: 1, outcome: "voice_started", runtime_frame: 128 }],
  });
  await settle();

  assert.equal(controller.state, "audio-suspended");
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.suspend").length, 2);
  assert.equal(controller.diagnostics().trigger_outcome_count, 1);
});

test("gesture-required recovery returns audio-suspended to recovering without initial activation shortcut", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  const context = fixture.contexts[0];
  context.state = "suspended";
  context.dispatchEvent(new Event("statechange"));
  await settle();
  assert.equal(controller.state, "audio-suspended");

  await controller.activateAudio();
  assert.equal(controller.state, "recovering");
  assert.equal(await controller.trigger(1, 100), true);
  fixture.transport.emit("runtime.trigger_outcomes", {
    events: [{ sequence: 1, outcome: "voice_started", runtime_frame: 128 }],
  });
  assert.equal(controller.state, "running");
});

test("recovery opens one public probe only after positive exact generation acknowledgement", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  fixture.setStatus({ control_generation: null, acknowledged_generation: null });
  controller.observeVisibility(true);
  await settle();
  assert.equal(controller.state, "recovering");
  assert.equal(await controller.trigger(1, 100), false);

  controller.observeRuntimeStatus({ control_generation: 0, acknowledged_generation: 0 });
  assert.equal(await controller.trigger(1, 100), false);
  controller.observeRuntimeStatus({ control_generation: 8, acknowledged_generation: "8" });
  assert.equal(await controller.trigger(1, 100), false);
  controller.observeRuntimeStatus({ control_generation: 8, acknowledged_generation: 8 });

  const probe = controller.trigger(1, 101);
  assert.equal(await controller.trigger(2, 102), false);
  assert.equal(await probe, true);
  assert.equal(controller.state, "recovering");
  fixture.transport.emit("runtime.trigger_outcomes", {
    events: [{ sequence: 1, outcome: "voice_started", runtime_frame: 128 }],
  });
  assert.equal(controller.state, "running");
});

test("a valid late pre-epoch outcome cannot complete or fail the current recovery", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  assert.equal(await controller.trigger(0, 100), true);
  controller.observeVisibility(true);
  await settle();
  controller.observeRuntimeStatus({ control_generation: 7, acknowledged_generation: 7 });
  fixture.transport.emit("runtime.trigger_outcomes", {
    events: [{ sequence: 1, outcome: "voice_capacity", runtime_frame: 128 }],
  });
  assert.equal(controller.state, "recovering");

  assert.equal(await controller.trigger(1, 100), true);
  fixture.transport.emit("runtime.trigger_outcomes", {
    events: [{ sequence: 2, outcome: "voice_started", runtime_frame: 256 }],
  });
  assert.equal(controller.state, "running");
});

test("probe non-success and protocol-invalid outcomes fail with once-only cleanup", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  for (const scenario of [
    { sequence: 1, outcome: "voice_capacity", code: "HOST_STATE_INVALID" },
    { sequence: 999, outcome: "voice_started", code: "HOST_PROTOCOL_MISMATCH" },
  ]) {
    const fixture = harness();
    const controller = createWebRuntimeHostController(fixture.options);
    await controller.start();
    await controller.loadDiagnosticProject();
    await controller.activateAudio();
    controller.observeVisibility(true);
    await settle();
    controller.observeRuntimeStatus({ control_generation: 7, acknowledged_generation: 7 });
    assert.equal(await controller.trigger(1, 100), true);
    fixture.transport.emit("runtime.trigger_outcomes", {
      events: [{ sequence: scenario.sequence, outcome: scenario.outcome, runtime_frame: 128 }],
    });
    fixture.worklet.dispatchEvent(new Event("processorerror"));
    await settle();
    assert.equal(controller.state, "failed");
    assert.equal(controller.diagnostics().error_code, scenario.code);
    assert.equal(fixture.cleanupCalls, 1);
  }
});

test("probe outcome deadline is exactly 1000 ms and times out terminally", async () => {
  const scheduled = [];
  const timers = {
    setTimeout(callback, milliseconds) {
      const record = { callback, milliseconds, cancelled: false };
      scheduled.push(record);
      return record;
    },
    clearTimeout(record) {
      record.cancelled = true;
    },
  };
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness({ timers });
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  controller.observeVisibility(true);
  await settle();
  controller.observeRuntimeStatus({ control_generation: 7, acknowledged_generation: 7 });
  assert.equal(await controller.trigger(1, 100), true);
  const deadline = scheduled.find(
    ({ milliseconds, cancelled }) => milliseconds === 1_000 && !cancelled,
  );
  assert.ok(deadline);
  deadline.callback();
  await settle();
  assert.equal(controller.state, "failed");
  assert.equal(controller.diagnostics().error_code, "HOST_TIMEOUT");
  assert.equal(fixture.cleanupCalls, 1);
});

test("explicit suspend is synchronous and its expected statechange never starts an epoch", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  const suspended = controller.suspendAudio();
  assert.equal(controller.state, "audio-suspended");
  assert.equal(await controller.trigger(0, 100), false);
  await suspended;
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.suspend").length, 1);
  assert.equal(controller.diagnostics().recovery_epoch, undefined);
});

test("an admitted Take is reserved before transport and a late response cannot reopen it", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const takeResponse = deferred();
  const sealedTakes = [];
  const originalSend = fixture.options.transport.send.bind(fixture.options.transport);
  fixture.options.transport.send = async (request, options) => {
    if (request.operation !== "take.begin") {
      return originalSend(request, options);
    }
    fixture.calls.push({ operation: request.operation, payload: request.payload, options });
    await takeResponse.promise;
    return responseFor(request, { take_id: request.payload.take_id });
  };
  fixture.options.sealTake = (sealed) => sealedTakes.push(sealed);
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();

  const pendingTake = controller.beginTake(
    "00000000-0000-0000-0000-000000000321",
    0,
  );
  controller.observeVisibility(true);
  assert.equal(controller.state, "interrupted");
  assert.deepEqual(sealedTakes, [
    {
      take_id: "00000000-0000-0000-0000-000000000321",
      outcome: "capture_incomplete",
      reason: "visibilitychange",
    },
  ]);

  takeResponse.resolve();
  assert.equal(await pendingTake, false);
  await settle();
  assert.equal(controller.state, "recovering");
  assert.equal(sealedTakes.length, 1);
});

test("a late rejected take.begin preserves its typed code and fails once", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const takeResponse = deferred();
  const sealedTakes = [];
  const originalSend = fixture.options.transport.send.bind(fixture.options.transport);
  fixture.options.transport.send = async (request, options) => {
    if (request.operation !== "take.begin") {
      return originalSend(request, options);
    }
    fixture.calls.push({ operation: request.operation, payload: request.payload, options });
    await takeResponse.promise;
    return responseFor(request, { take_id: request.payload.take_id });
  };
  fixture.options.sealTake = (sealed) => sealedTakes.push(sealed);
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();

  const pendingTake = controller.beginTake(
    "00000000-0000-0000-0000-000000000654",
    0,
  );
  controller.observeVisibility(true);
  const rejection = new Error("typed transport rejection");
  rejection.code = "IO_ERROR";
  takeResponse.reject(rejection);

  assert.equal(await pendingTake, false);
  await settle();
  assert.equal(controller.state, "failed");
  assert.equal(controller.diagnostics().error_code, "IO_ERROR");
  assert.equal(fixture.cleanupCalls, 1);
  assert.equal(sealedTakes.length, 1);
});

test("activation is synchronously serialized", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const workletStarted = deferred();
  fixture.options.loadRuntime = async () => ({
    registerAudioContext: () => 1,
    startAudioWorklet: () => workletStarted.promise,
    workers: [fixture.runtimeWorker],
    worklet: fixture.worklet,
  });
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();

  const first = controller.activateAudio();
  const second = controller.activateAudio();
  assert.equal(await second, false);
  workletStarted.resolve({ ok: true });
  assert.equal(await first, true);
  assert.equal(controller.state, "running");
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.activate").length, 1);
});

test("backgrounding during activation cannot publish running", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const workletStarted = deferred();
  fixture.options.loadRuntime = async () => ({
    registerAudioContext: () => 1,
    startAudioWorklet: () => workletStarted.promise,
    workers: [fixture.runtimeWorker],
    worklet: fixture.worklet,
  });
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();

  const activation = controller.activateAudio();
  controller.observeVisibility(true);
  workletStarted.resolve({ ok: true });
  assert.equal(await activation, false);
  assert.equal(controller.state, "audio-suspended");
  assert.equal(fixture.calls.filter(({ operation }) => operation === "audio.activate").length, 0);
});

test("a fatal Worklet startup result wins over stale background activation and blocks retry", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const workletStarted = deferred();
  let workletStartCalls = 0;
  fixture.options.loadRuntime = async () => ({
    registerAudioContext: () => 1,
    startAudioWorklet() {
      workletStartCalls += 1;
      return workletStarted.promise;
    },
    workers: [fixture.runtimeWorker],
    worklet: fixture.worklet,
  });
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();

  const activation = controller.activateAudio();
  controller.observeVisibility(true);
  workletStarted.resolve({ ok: false });
  const activationResult = await activation;
  await settle();
  controller.observeVisibility(false);
  const retryResult = await controller.activateAudio();

  assert.deepEqual(
    {
      activationResult,
      retryResult,
      state: controller.state,
      errorCode: controller.diagnostics().error_code,
      cleanupCalls: fixture.cleanupCalls,
      workletStartCalls,
      controlActivations: fixture.calls.filter(({ operation }) => operation === "audio.activate").length,
    },
    {
      activationResult: false,
      retryResult: false,
      state: "failed",
      errorCode: "HOST_STATE_INVALID",
      cleanupCalls: 1,
      workletStartCalls: 1,
      controlActivations: 0,
    },
  );
});

test("off-Pad window release and blur clear Pointer pressed state", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  for (const [downType, upType, properties] of [
    ["pointerdown", "pointerup", { isPrimary: true, button: 0, pointerId: 41 }],
    ["mousedown", "mouseup", { button: 0 }],
  ]) {
    const fixture = harness();
    const controller = createWebRuntimeHostController(fixture.options);
    await controller.start();
    const down = new Event(downType);
    for (const [name, value] of Object.entries(properties)) {
      Object.defineProperty(down, name, { value });
    }
    fixture.dom.pads[0].dispatchEvent(down);
    assert.equal(fixture.dom.pads[0].getAttribute("aria-pressed"), "true");
    const up = new Event(upType);
    for (const [name, value] of Object.entries(properties)) {
      Object.defineProperty(up, name, { value });
    }
    fixture.dom.window.dispatchEvent(up);
    assert.equal(fixture.dom.pads[0].getAttribute("aria-pressed"), "false");

    fixture.dom.pads[0].dispatchEvent(down);
    fixture.dom.window.dispatchEvent(new Event("blur"));
    assert.equal(fixture.dom.pads[0].getAttribute("aria-pressed"), "false");
  }
});

async function assertHostileCodeMapped({ configure, exercise }) {
  const { createWebRuntimeHostController } = await mainModule();
  const hostileCode = "/private/opfs/provider-secret";
  const fixture = harness();
  configure?.(fixture, hostileCode);
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await exercise(controller, fixture, hostileCode);
  await settle();
  assert.equal(controller.state, "failed");
  assert.equal(controller.diagnostics().error_code, "HOST_PROTOCOL_MISMATCH");
  assert.equal(fixture.dom.elements.get("diagnostics").textContent.includes(hostileCode), false);
}

test("hostile runtime.warning code remains nonterminal and private", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const hostileCode = "/private/opfs/provider-secret";
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  fixture.transport.emit("runtime.warning", { fatal: true, code: hostileCode });
  await settle();

  assert.equal(controller.state, "audio-suspended");
  assert.equal(controller.diagnostics().error_code, null);
  assert.equal(fixture.dom.elements.get("diagnostics").textContent.includes(hostileCode), false);
  assert.equal(fixture.cleanupCalls, 0);
});

test("hostile typed runtime observation code is mapped before entering diagnostics", async () => {
  await assertHostileCodeMapped({
    exercise(controller, _fixture, hostileCode) {
      controller.observeRuntime({ fatal: true, code: hostileCode });
    },
  });
});

test("hostile transport response code is mapped before entering diagnostics", async () => {
  await assertHostileCodeMapped({
    configure(fixture, hostileCode) {
      const originalSend = fixture.options.transport.send.bind(fixture.options.transport);
      fixture.options.transport.send = async (request, options) => {
        if (request.operation !== "audio.activate") {
          return originalSend(request, options);
        }
        return {
          protocol_version: 1,
          request_id: request.request_id,
          ok: false,
          error: { code: hostileCode, message: "rejected", details: {} },
        };
      };
    },
    async exercise(controller) {
      await controller.activateAudio();
    },
  });
});

test("a synchronously throwing runtime terminator cannot escape terminal cleanup", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  fixture.options.runtimeTerminator = () => {
    throw new Error("terminator failed");
  };
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  assert.doesNotThrow(() => controller.observeRuntime({ fatal: true, code: "IO_ERROR" }));
  await settle();
  assert.equal(controller.state, "failed");
  assert.equal(controller.diagnostics().error_code, "IO_ERROR");
});

test("default terminal cleanup terminates Workers before best-effort Host close", async () => {
  const { defaultRuntimeTerminator } = await mainModule();
  const cases = [
    ["resolved", () => Promise.resolve({ ok: true })],
    ["rejected", () => Promise.reject(new Error("close rejected"))],
    ["already-failed", () => Promise.resolve({
      ok: false,
      error: { code: "HOST_STATE_INVALID" },
    })],
    ["synchronous-throw", () => {
      throw new Error("close threw");
    }],
    ["timeout", () => new Promise(() => {})],
  ];

  for (const [label, close] of cases) {
    const events = [];
    const duplicateWorker = {
      terminate() {
        events.push("worker:duplicate");
      },
    };
    const runtime = {
      transport: {
        send(request, options) {
          events.push("host.close");
          assert.deepEqual(request, {
            protocol_version: 1,
            request_id: "00000000-0000-0000-0000-000000000001",
            operation: "host.close",
            payload: {},
          });
          assert.deepEqual(options, { deadlineMs: 10_000 });
          return close();
        },
      },
      worklet: {
        disconnect() {
          events.push("worklet.disconnect");
        },
        port: {
          close() {
            events.push("worklet.port.close");
          },
        },
      },
      workers: [duplicateWorker, {
        terminate() {
          events.push("worker:runtime");
        },
      }],
    };
    const window = { crypto: uuidSource() };
    const audioContext = {
      state: "running",
      async close() {
        events.push("audio.close");
        this.state = "closed";
      },
    };

    await assert.doesNotReject(defaultRuntimeTerminator({
      runtime,
      audioContext,
      window,
    }), label);
    assert.deepEqual(events, [
      "worker:duplicate",
      "worker:runtime",
      "host.close",
      "worklet.disconnect",
      "worklet.port.close",
      "audio.close",
    ], label);
  }
});

test("fatal runtime observations and clean close use once-only terminal cleanup", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  await controller.loadDiagnosticProject();
  await controller.activateAudio();
  controller.observeRuntime({ fatal: true, code: "IO_ERROR" });
  fixture.runtimeWorker.dispatchEvent(new Event("error"));
  fixture.worklet.dispatchEvent(new Event("processorerror"));
  await settle();
  assert.equal(controller.state, "failed");
  assert.equal(controller.diagnostics().error_code, "IO_ERROR");
  assert.equal(fixture.cleanupCalls, 1);

  const closingFixture = harness();
  const closing = createWebRuntimeHostController(closingFixture.options);
  await closing.start();
  await closing.loadDiagnosticProject();
  await closing.activateAudio();
  await closing.observePageHide({ persisted: false });
  assert.equal(closing.state, "closed");
  assert.equal(closingFixture.calls.filter(({ operation }) => operation === "host.close").length, 1);
  assert.equal(closingFixture.cleanupCalls, 1);
});

test("diagnostics expose only the privacy allowlist", async () => {
  const { createWebRuntimeHostController } = await mainModule();
  const fixture = harness();
  const controller = createWebRuntimeHostController(fixture.options);
  await controller.start();
  const diagnostic = controller.diagnostics();
  assert.deepEqual(Object.keys(diagnostic).sort(), [
    "acknowledged_generation",
    "connected_input_count",
    "control_generation",
    "diagnostic_project_state",
    "error_code",
    "host_version",
    "midi_permission",
    "pressed_count",
    "product_build",
    "protocol_version",
    "state",
    "trigger_admitted_count",
    "trigger_outcome_count",
    "trigger_rejected_count",
  ]);
  const serialized = JSON.stringify({ diagnostic, dom: fixture.dom.elements.get("diagnostics").textContent });
  for (const secret of [
    "provider-secret",
    "/private/opfs/project",
    "Private Controller",
    "Private Manufacturer",
    "stable-private-id",
    "144,36,99",
    "imported-audio-bytes",
  ]) {
    assert.equal(serialized.includes(secret), false);
  }
});
