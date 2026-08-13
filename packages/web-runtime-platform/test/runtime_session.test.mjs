import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import test from "node:test";

import {createDiagnosticClient} from "../web/diagnostic_client.mjs";
import {createUserGestureToken} from "../web/input_adapters.mjs";
import {createRuntimeSession} from "../web/runtime_session.mjs";


const API = [
  "activateAudio",
  "close",
  "diagnostics",
  "importProject",
  "inspectProject",
  "listLocalProjects",
  "openProject",
  "reloadSnapshot",
  "requestMidi",
  "start",
  "subscribeDiagnostics",
  "subscribeHostState",
  "subscribeRuntimeOutcome",
  "suspendAudio",
  "trigger",
].sort();

function fixture({
  send,
  browserWindow = {},
  navigator = {},
  capabilities,
  runtimeTransport,
  runtimeTerminator,
  inputOwnership,
} = {}) {
  let request = 0;
  let terminated = 0;
  let notificationListener = null;
  let failureListener = null;
  const context = {
    state: "suspended",
    async resume() {
      this.state = "running";
    },
    async suspend() {
      this.state = "suspended";
    },
  };
  const transport = {
    async send(envelope) {
      if (send) {
        return send(envelope);
      }
      const results = {
        "audio.activate": {},
        "audio.suspend": {},
        "host.close": {},
        "host.status": {
          acknowledged_generation: 1,
          control_generation: 1,
        },
      };
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result: results[envelope.operation] ?? {},
      };
    },
    subscribe() {
      notificationListener = arguments[0];
      return () => {};
    },
    subscribeFailure(listener) {
      failureListener = listener;
      return () => {};
    },
  };
  const session = createRuntimeSession({
    document: {},
    window: browserWindow,
    navigator,
    crypto: {
      randomUUID() {
        request += 1;
        return `00000000-0000-4000-8000-${String(request).padStart(12, "0")}`;
      },
      subtle: webcrypto.subtle,
    },
    manifestSource: {},
    assemblyIdentity: {
      distributionContract: "lmdj.web-runtime-host.distribution.v1",
      hostId: "web-runtime-host",
      hostVersion: "1.2.8",
      platformVersion: "0.2.1",
      productBuild: "1.0.21.0",
      protocolVersion: 1,
    },
    inputConfiguration: {},
    inputOwnership,
    seams: {
      ...(capabilities === undefined ? {} : {capabilities}),
      createAudioContext: () => context,
      loadRuntime: async () => ({
        registerAudioContext: () => 1,
        startAudioWorklet: async () => ({ok: true}),
        workers: [],
        ...(runtimeTransport === undefined
          ? {}
          : {transport: runtimeTransport}),
      }),
      preflight: async () => {},
      runtimeTerminator: async (...arguments_) => {
        terminated += 1;
        await runtimeTerminator?.(...arguments_);
      },
      transport,
      verifyManifest: async () => ({
        host_id: "web-runtime-host",
        host_version: "1.2.8",
        platform_version: "0.2.1",
        product_build: "1.0.21.0",
        protocol_version: 1,
      }),
    },
  });
  return {
    context,
    emitNotification(value) {
      notificationListener?.(value);
    },
    emitFailure(value) {
      failureListener?.(value);
    },
    session,
    terminated: () => terminated,
  };
}

function trackedEventTarget() {
  const listeners = new Map();
  return {
    addEventListener(type, listener) {
      const values = listeners.get(type) ?? new Set();
      values.add(listener);
      listeners.set(type, values);
    },
    removeEventListener(type, listener) {
      listeners.get(type)?.delete(listener);
    },
    count(type) {
      return listeners.get(type)?.size ?? 0;
    },
  };
}

test("reports the exact assembly identity and resolved browser capabilities", async () => {
  const capabilities = Object.fromEntries([
    "secureContext",
    "crossOriginIsolated",
    "sharedArrayBuffer",
    "webAssembly",
    "audioWorklet",
    "opfs",
    "opfsSyncAccessHandle",
    "opfsWritableReplace",
  ].map((name) => [name, true]));
  const {session} = fixture({
    capabilities,
    navigator: {requestMIDIAccess: async () => ({inputs: new Map()})},
  });
  await session.start();
  assert.deepEqual(session.diagnostics().capabilities, {
    secureContext: true,
    crossOriginIsolated: true,
    sharedArrayBuffer: true,
    webAssembly: true,
    audioWorklet: true,
    opfs: true,
    opfsSyncAccessHandle: true,
    opfsWritableReplace: true,
    webMidi: true,
  });
  assert.equal(session.diagnostics().host_id, "web-runtime-host");
  assert.equal(session.diagnostics().platform_version, "0.2.1");
});

test("accepts only the declared compatible Host inventory in packaged manifests", async () => {
  const canonical = (value) => {
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    if (value !== null && typeof value === "object") {
      return `{${Object.keys(value).sort().map((key) =>
        `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
    }
    return JSON.stringify(value);
  };
  const assemblyIdentity = {
    distributionContract: "lmdj.creator-web.distribution.v1",
    hostId: "creator-web",
    hostVersion: "1.1.3",
    platformVersion: "0.2.1",
    productBuild: "1.0.21.0",
    protocolVersion: 1,
  };
  const manifestSource = {
    heapBytes: 536_870_912,
    resourceLimits: {imported_wav_bytes: 1_048_576},
    emscripten: {
      emcc_version: "emcc",
      emscripten_releases_revision: "a".repeat(40),
      emsdk_revision: "b".repeat(40),
      emsdk_tag: "6.0.5",
    },
    compatibleHosts: [{host_id: "web-runtime-host", host_version: "1.2.8"}],
    expectedAssets: [{
      prefix: "assets/main.", suffix: ".js", role: "host_main",
    }],
  };
  const baseManifest = {
    assets: [{
      bytes: 1,
      path: `assets/main.${"c".repeat(64)}.js`,
      role: "host_main",
      sha256: "c".repeat(64),
    }],
    compatible_hosts: manifestSource.compatibleHosts,
    distribution_contract: assemblyIdentity.distributionContract,
    emscripten: manifestSource.emscripten,
    heap_bytes: manifestSource.heapBytes,
    host_id: assemblyIdentity.hostId,
    host_version: assemblyIdentity.hostVersion,
    manifest_version: 1,
    platform_version: assemblyIdentity.platformVersion,
    product_build: assemblyIdentity.productBuild,
    protocol_version: 1,
    resource_limits: manifestSource.resourceLimits,
  };

  async function packagedSession(manifest) {
    const text = canonical(manifest);
    const digest = [...new Uint8Array(
      await webcrypto.subtle.digest("SHA-256", new TextEncoder().encode(text)),
    )].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const metadata = new Map([
      ["lmdj-host-manifest-path", "./host-manifest.json"],
      ["lmdj-host-manifest-sha256", digest],
      ["lmdj-product-build", assemblyIdentity.productBuild],
      ["lmdj-host-id", assemblyIdentity.hostId],
      ["lmdj-host-version", assemblyIdentity.hostVersion],
      ["lmdj-web-runtime-platform-version", assemblyIdentity.platformVersion],
      ["lmdj-host-protocol-version", "1"],
    ]);
    const browserWindow = new EventTarget();
    browserWindow.fetch = async () => new Response(text);
    const session = createRuntimeSession({
      document: {
        baseURI: "http://127.0.0.1:4175/",
        visibilityState: "visible",
        addEventListener() {},
        removeEventListener() {},
        querySelector(selector) {
          const name = selector.match(/meta\[name='([^']+)'\]/)?.[1];
          const value = metadata.get(name);
          return value === undefined ? null : {getAttribute: () => value};
        },
      },
      window: browserWindow,
      navigator: {},
      crypto: webcrypto,
      manifestSource,
      assemblyIdentity,
      seams: {
        createAudioContext: () => ({state: "suspended"}),
        loadRuntime: async () => ({workers: []}),
        preflight: async () => {},
        runtimeTerminator: async () => {},
        transport: {
          async send(envelope) {
            return {
              protocol_version: 1,
              request_id: envelope.request_id,
              ok: true,
              result: {},
            };
          },
          subscribe: () => () => {},
          subscribeFailure: () => () => {},
        },
      },
    });
    return session;
  }

  const accepted = await packagedSession(baseManifest);
  assert.equal(await accepted.start(), true);
  const rejected = await packagedSession({
    ...baseManifest,
    compatible_hosts: [{host_id: "web-runtime-host", host_version: "9.9.9"}],
  });
  assert.equal(await rejected.start(), false);
  assert.equal(rejected.diagnostics().error_code, "HOST_PROTOCOL_MISMATCH");
});

test("owns the exact Host-neutral surface and lifecycle", async () => {
  const {session, terminated} = fixture();
  assert.deepEqual(Object.keys(session).sort(), API);
  assert.equal(await session.start(), true);
  assert.equal(await session.start(), false);
  assert.equal(session.diagnostics().state, "audio-suspended");

  const states = [];
  const unsubscribe = session.subscribeHostState((value) => states.push(value));
  assert.throws(() => createUserGestureToken({isTrusted: false}), TypeError);
  assert.equal(await session.activateAudio({kind: "lmdj.web-runtime.user-gesture"}), false);
  const token = createUserGestureToken({isTrusted: true});
  assert.equal(await session.activateAudio(token), true);
  assert.equal(session.diagnostics().state, "running");
  assert.equal(await session.close(), true);
  unsubscribe();

  assert.deepEqual(states.at(-1), {
    state: "closed",
    errorCode: null,
    errorDetails: {},
  });
  assert.equal(terminated(), 1);
});

test("pushes immutable diagnostics and honors unsubscribe", async () => {
  const {session} = fixture();
  const values = [];
  const unsubscribe = session.subscribeDiagnostics((value) => values.push(value));
  assert.equal(await session.start(), true);
  assert.equal(values.length > 0, true);
  assert.equal(Object.isFrozen(values.at(-1)), true);
  assert.equal(values.at(-1).state, "audio-suspended");
  const delivered = values.length;
  unsubscribe();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  assert.equal(values.length, delivered);
});

test("Host-state failures expose only allowlisted structured details", async () => {
  const {emitFailure, session} = fixture();
  const states = [];
  session.subscribeHostState((value) => states.push(value));
  await session.start();
  emitFailure(Object.assign(new Error("/Users/private/project"), {
    code: "WEB_RUNTIME_RESOURCE_LIMIT",
    stack: "private stack",
    details: {
      resource: "decoded_frames_per_pad",
      observed: 240_001,
      limit: 240_000,
      storage_condition: "quota_exceeded",
      path: "/Users/private/project",
      request_id: "11111111-1111-4111-8111-111111111111",
      device_name: "Private MIDI",
    },
  }));

  assert.deepEqual(states.at(-1), {
    state: "failed",
    errorCode: "WEB_RUNTIME_RESOURCE_LIMIT",
    errorDetails: {
      resource: "decoded_frames_per_pad",
      observed: 240_001,
      limit: 240_000,
      storage_condition: "quota_exceeded",
    },
  });
  assert.deepEqual(session.diagnostics().error_details, states.at(-1).errorDetails);
});

test("defaults diagnostics to session-owned input listeners", async () => {
  const browserWindow = trackedEventTarget();
  const {session} = fixture({browserWindow});
  assert.equal(await session.start(), true);
  for (const type of [
    "pointerup",
    "pointercancel",
    "mouseup",
    "blur",
    "keydown",
    "keyup",
  ]) {
    assert.equal(browserWindow.count(type), 1, type);
  }
  await session.close();
  assert.equal(browserWindow.count("keydown"), 0);
});

test("host-owned input creates no session input listeners or MIDI adapter", async () => {
  const browserWindow = trackedEventTarget();
  let midiRequests = 0;
  const {session} = fixture({
    browserWindow,
    inputOwnership: "host",
    navigator: {
      async requestMIDIAccess() {
        midiRequests += 1;
        return {};
      },
    },
  });
  assert.equal(await session.start(), true);
  for (const type of [
    "pointerup",
    "pointercancel",
    "mouseup",
    "blur",
    "keydown",
    "keyup",
  ]) {
    assert.equal(browserWindow.count(type), 0, type);
  }
  assert.equal(browserWindow.count("pagehide"), 1);
  assert.equal(await session.requestMidi(), false);
  assert.equal(midiRequests, 0);
});

test("rejects an unknown input owner", () => {
  assert.throws(
    () => fixture({inputOwnership: "both"}),
    /input ownership is invalid/,
  );
});

test("returns typed admission and publishes normalized Runtime outcomes", async () => {
  const {emitNotification, session} = fixture({
    send: async (envelope) => ({
      protocol_version: 1,
      request_id: envelope.request_id,
      ok: true,
      result: envelope.operation === "trigger"
        ? {sequence: 9}
        : envelope.operation === "host.status"
          ? {acknowledged_generation: 1, control_generation: 1}
          : {},
    }),
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const outcomes = [];
  session.subscribeRuntimeOutcome((value) => outcomes.push(value));
  assert.deepEqual(await session.trigger(3, 99, "keyboard"), {
    sequence: 9,
    slot: 3,
    velocity: 99,
    source: "keyboard",
  });
  emitNotification({
    protocol_version: 1,
    event: "runtime.trigger_outcomes",
    payload: {
      events: [{sequence: 9, outcome: "voice_started", runtime_frame: 42}],
    },
  });
  assert.deepEqual(outcomes, [
    {sequence: 9, outcome: "voice_started", runtimeFrame: 42},
  ]);
});

test("suppresses a late Trigger response after pagehide close", async () => {
  const browserWindow = new EventTarget();
  let settleTrigger;
  const triggerResponse = new Promise((resolvePromise) => {
    settleTrigger = resolvePromise;
  });
  const {session, terminated} = fixture({
    browserWindow,
    send: async (envelope) => {
      if (envelope.operation === "trigger") {
        return triggerResponse;
      }
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result: envelope.operation === "host.status"
          ? {acknowledged_generation: 1, control_generation: 1}
          : {},
      };
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const pending = session.trigger(0, 100, "pointer");
  browserWindow.dispatchEvent(new Event("pagehide"));
  settleTrigger({
    protocol_version: 1,
    request_id: "00000000-0000-4000-8000-000000000003",
    ok: true,
    result: {sequence: 1},
  });
  assert.equal(await pending, false);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  assert.equal(session.diagnostics().state, "closed");
  assert.equal(session.diagnostics().trigger_admitted_count, 0);
  assert.equal(terminated(), 1);
});

test("non-persisted pagehide submits clean close without forced termination", async () => {
  const browserWindow = new EventTarget();
  let closeEnvelope;
  let settleClose;
  let forcedTerminations = 0;
  const lifecycle = [];
  const closeResponse = new Promise((resolvePromise) => {
    settleClose = resolvePromise;
  });
  const {session} = fixture({
    browserWindow,
    runtimeTransport: {
      terminate() {
        forcedTerminations += 1;
        lifecycle.push("forced-termination");
      },
    },
    send: async (envelope) => {
      if (envelope.operation === "host.close") {
        lifecycle.push("clean-close");
        closeEnvelope = envelope;
        return closeResponse;
      }
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result: {},
      };
    },
  });
  await session.start();

  browserWindow.dispatchEvent(new Event("pagehide"));

  assert.equal(forcedTerminations, 0);
  assert.deepEqual(lifecycle, ["clean-close"]);
  settleClose({
    protocol_version: 1,
    request_id: closeEnvelope.request_id,
    ok: true,
    result: {},
  });
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  assert.equal(session.diagnostics().state, "closed");
});

test("diagnostics expose only the armed recovery probe window", async () => {
  const browserWindow = new EventTarget();
  const {emitNotification, session} = fixture({
    browserWindow,
    send: async (envelope) => ({
      protocol_version: 1,
      request_id: envelope.request_id,
      ok: true,
      result: envelope.operation === "trigger"
        ? {sequence: 7}
        : envelope.operation === "host.status"
          ? {acknowledged_generation: 1, control_generation: 1}
          : {},
    }),
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  assert.equal(session.diagnostics().recovery_probe_ready, false);

  const pagehide = new Event("pagehide");
  Object.defineProperty(pagehide, "persisted", {value: true});
  browserWindow.dispatchEvent(pagehide);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  assert.equal(session.diagnostics().state, "recovering");
  assert.equal(session.diagnostics().recovery_probe_ready, true);

  assert.deepEqual(await session.trigger(0, 100, "keyboard"), {
    sequence: 7,
    slot: 0,
    velocity: 100,
    source: "keyboard",
  });
  assert.equal(session.diagnostics().recovery_probe_ready, false);
  emitNotification({
    protocol_version: 1,
    event: "runtime.trigger_outcomes",
    payload: {
      events: [{sequence: 7, outcome: "voice_started", runtime_frame: 42}],
    },
  });
  assert.equal(session.diagnostics().state, "running");
  assert.equal(session.diagnostics().recovery_probe_ready, false);
});

test("close disposes MIDI input listeners exactly once", async () => {
  let added = 0;
  let removed = 0;
  const input = {
    type: "input",
    state: "connected",
    addEventListener(type) {
      assert.equal(type, "midimessage");
      added += 1;
    },
    removeEventListener(type) {
      assert.equal(type, "midimessage");
      removed += 1;
    },
  };
  const access = new EventTarget();
  access.inputs = new Map([["private", input]]);
  const {session} = fixture({
    navigator: {
      async requestMIDIAccess(options) {
        assert.deepEqual(options, {sysex: false});
        return access;
      },
    },
  });
  await session.start();
  assert.equal(await session.requestMidi(), true);
  assert.equal(added, 1);
  await session.close();
  assert.equal(removed, 1);
});

test("timeout becomes one terminal restart-required notification", async () => {
  const failure = Object.assign(new Error("timeout"), {code: "HOST_TIMEOUT"});
  const {session, terminated} = fixture({
    send: async (envelope) => {
      if (envelope.operation === "project.create") {
        throw failure;
      }
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result: {},
      };
    },
  });
  await session.start();
  const states = [];
  session.subscribeHostState((value) => states.push(value));
  const diagnostic = createDiagnosticClient(session);

  await assert.rejects(diagnostic.createProject({}), failure);
  assert.equal(session.diagnostics().state, "restart-required");
  assert.equal(session.diagnostics().error_code, "HOST_TIMEOUT");
  assert.deepEqual(states, [
    {state: "restart-required", errorCode: "HOST_TIMEOUT", errorDetails: {}},
  ]);
  await Promise.resolve();
  assert.equal(terminated(), 1);
});

test("close after a terminal edge awaits the owned cleanup", async () => {
  let releaseCleanup;
  const cleanup = new Promise((resolvePromise) => {
    releaseCleanup = resolvePromise;
  });
  const {emitFailure, session} = fixture({
    runtimeTerminator: () => cleanup,
  });
  await session.start();
  emitFailure(Object.assign(new Error("timeout"), {code: "HOST_TIMEOUT"}));
  assert.equal(session.diagnostics().state, "restart-required");

  let settled = false;
  const closing = session.close().then((value) => {
    settled = true;
    return value;
  });
  await Promise.resolve();
  assert.equal(settled, false);
  releaseCleanup();
  assert.equal(await closing, false);
});

async function oneEntryBundle() {
  const canonical = (value) => {
    if (Array.isArray(value)) {
      return `[${value.map(canonical).join(",")}]`;
    }
    if (value !== null && typeof value === "object") {
      return `{${Object.keys(value).sort().map((key) =>
        `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
    }
    return JSON.stringify(value);
  };
  const hash = async (bytes) => [...new Uint8Array(
    await webcrypto.subtle.digest("SHA-256", bytes),
  )].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  const payload = new TextEncoder().encode("project");
  const digestSource = {
    compression: "none",
    contract: "lmdj.project-bundle.v1",
    contract_version: "1.0.0",
    entries: [{
      bytes: payload.byteLength,
      offset: 0,
      path: "manifest.json",
      sha256: await hash(payload),
    }],
    project_contract: "lmdj.project.v1",
    project_id: "11111111-1111-4111-8111-111111111111",
    uncompressed_bytes: payload.byteLength,
  };
  const index = {
    bundle_digest: await hash(new TextEncoder().encode(canonical(digestSource))),
    ...digestSource,
  };
  const indexBytes = new TextEncoder().encode(canonical(index));
  const header = new Uint8Array(12);
  header.set(new TextEncoder().encode("LMDJBND1"));
  new DataView(header.buffer).setUint32(8, indexBytes.byteLength, false);
  return {file: new Blob([header, indexBytes, payload]), index};
}

test("lists and imports Projects through the public typed surface", async () => {
  const {file, index} = await oneEntryBundle();
  const operations = [];
  const summary = {
    project_id: index.project_id,
    pattern_id: "22222222-2222-4222-8222-222222222222",
    revision: 3,
    bpm: 120,
    asset_count: 1,
    assigned_pad_count: 8,
    bundle_digest: index.bundle_digest,
  };
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      let result = {};
      if (envelope.operation === "project.list") {
        result = {projects: [summary]};
      } else if (
        envelope.operation === "project.import.index" &&
        envelope.payload.final
      ) {
        result = {
          project_id: index.project_id,
          bundle_digest: index.bundle_digest,
          entry_count: 1,
        };
      } else if (envelope.operation === "project.import.commit") {
        result = summary;
      }
      return {
        protocol_version: 1,
        request_id: envelope.request_id,
        ok: true,
        result,
      };
    },
  });
  await session.start();
  const expected = {
    projectId: index.project_id,
    patternId: summary.pattern_id,
    revision: 3,
    bpm: 120,
    assetCount: 1,
    assignedPadCount: 8,
    bundleDigest: index.bundle_digest,
  };
  assert.deepEqual(await session.listLocalProjects(), [expected]);
  assert.deepEqual(await session.importProject(file), expected);
  assert.deepEqual(operations, [
    "project.list",
    "project.import.begin",
    "project.import.index",
    "project.import.entry",
    "project.import.commit",
  ]);
});
