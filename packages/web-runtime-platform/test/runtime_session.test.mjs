import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import test from "node:test";

import {createDiagnosticClient} from "../web/diagnostic_client.mjs";
import {createUserGestureToken} from "../web/input_adapters.mjs";
import {createRuntimeSession} from "../web/runtime_session.mjs";

const TEST_PRODUCT_BUILD = "9.8.7.6";

const API = [
  "activateAudio",
  "applySequenceRecovery",
  "beginSequence",
  "clearSamplePreview",
  "close",
  "createPattern",
  "diagnostics",
  "discardSequenceRecovery",
  "flushSequence",
  "importProject",
  "importAssignSample",
  "inspectSample",
  "inspectProject",
  "listLocalProjects",
  "listSequenceRecovery",
  "openProject",
  "querySampleQuota",
  "queryWaveform",
  "querySequenceStatus",
  "recordSequenceEvent",
  "release",
  "reloadSnapshot",
  "requestMidi",
  "requestPatternSwitch",
  "resetPad",
  "retryPrepare",
  "setSamplePreview",
  "sampleIngestLimits",
  "start",
  "subscribeDiagnostics",
  "stopAll",
  "stopSequence",
  "stopPad",
  "subscribeHostState",
  "subscribeRuntimeOutcome",
  "subscribeSequenceBarBoundary",
  "subscribeVoiceState",
  "suspendAudio",
  "trigger",
  "updatePad",
  "updateSequenceSettings",
].sort();

const PLAYBACK = Object.freeze({
  trimStartFrame: 10,
  trimEndFrame: 90,
  triggerMode: "gate",
  gainMillidb: -1_200,
  muted: false,
});

const WIRE_PLAYBACK = Object.freeze({
  trim_start_frame: 10,
  trim_end_frame: 90,
  trigger_mode: "gate",
  gain_millidb: -1_200,
  muted: false,
});

const RESOURCE_LIMITS = Object.freeze({
  decoded_float_pcm_bytes_per_bank: 67_108_864,
  decoded_float_pcm_bytes_total: 134_217_728,
  decoded_float_pcm_bytes_resident: 268_435_456,
  ingest_source_bytes: 104_857_600,
  ingest_decoded_frames: 43_200_000,
  ingest_channels: 2,
  imported_wav_bytes: 68_157_440,
});

function success(envelope, result = {}) {
  return {
    protocol_version: 1,
    request_id: envelope.request_id,
    ok: true,
    result,
  };
}

function defaultResult(operation) {
  const results = {
    "audio.activate": {},
    "audio.suspend": {},
    "host.close": {},
    "host.status": {
      acknowledged_generation: 1,
      control_generation: 1,
    },
    "sample.preview.set": {accepted: true},
    "sample.preview.clear": {accepted: true},
    "sample.stop": {accepted: true, scope: "all"},
    trigger: {accepted: true},
  };
  return results[operation] ?? {};
}

function browserEvent(type, properties = {}) {
  const event = new Event(type);
  for (const [name, value] of Object.entries(properties)) {
    Object.defineProperty(event, name, {value});
  }
  return event;
}

async function drainTasks() {
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
}

function fixture({
  send,
  browserDocument = {},
  browserWindow = {},
  navigator = {},
  capabilities,
  capabilityProbeTimeoutMs,
  inputConfiguration = {},
  runtimeTransport,
  runtimeTerminator,
  inputOwnership,
  manifestSource = {
    resourceLimits: RESOURCE_LIMITS,
  },
} = {}) {
  let request = 0;
  let terminated = 0;
  let notificationListener = null;
  let failureListener = null;
  const context = Object.assign(new EventTarget(), {
    state: "suspended",
    async resume() {
      this.state = "running";
    },
    async suspend() {
      this.state = "suspended";
    },
  });
  const transport = {
    async send(envelope, transportOptions) {
      if (send) {
        return send(envelope, transportOptions);
      }
      return success(envelope, defaultResult(envelope.operation));
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
    document: browserDocument,
    window: browserWindow,
    navigator,
    crypto: {
      randomUUID() {
        request += 1;
        return `00000000-0000-4000-8000-${String(request).padStart(12, "0")}`;
      },
      subtle: webcrypto.subtle,
    },
    manifestSource: {
      ...manifestSource,
      resourceLimits: {
        ...RESOURCE_LIMITS,
        ...manifestSource.resourceLimits,
      },
    },
    assemblyIdentity: {
      distributionContract: "lmdj.web-runtime-host.distribution.v1",
      hostId: "web-runtime-host",
      hostVersion: "1.2.15",
      platformVersion: "0.3.6",
      productBuild: TEST_PRODUCT_BUILD,
      protocolVersion: 1,
    },
    inputConfiguration,
    inputOwnership,
    seams: {
      ...(capabilities === undefined ? {} : {capabilities}),
      ...(capabilityProbeTimeoutMs === undefined
        ? {}
        : {capabilityProbeTimeoutMs}),
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
        host_version: "1.2.15",
        platform_version: "0.3.6",
        product_build: TEST_PRODUCT_BUILD,
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
    emitTransportFailure(value) {
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
  assert.equal(session.diagnostics().platform_version, "0.3.6");
});

test("accepts only a positive safe integer capability probe timeout seam", () => {
  for (const invalid of [
    0,
    -1,
    1.5,
    Number.MAX_SAFE_INTEGER + 1,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    null,
    "15000",
  ]) {
    assert.throws(
      () => fixture({capabilityProbeTimeoutMs: invalid}),
      /Capability probe timeout must be a positive safe integer/,
    );
  }
  const {session} = fixture({capabilityProbeTimeoutMs: 25});
  assert.equal(typeof session.start, "function");
});

test("default capability probe timeout fails startup without restart-required", async () => {
  let terminated = 0;
  let revoked = 0;
  const session = createRuntimeSession({
    document: {},
    window: {
      Blob,
      Worker: class {
        addEventListener() {}
        postMessage() {}
        terminate() {
          terminated += 1;
        }
      },
      URL: {
        createObjectURL() {
          return "blob:capability-probe";
        },
        revokeObjectURL() {
          revoked += 1;
        },
      },
      crypto: webcrypto,
      setTimeout,
      clearTimeout,
    },
    navigator: {},
    crypto: webcrypto,
    manifestSource: {resourceLimits: RESOURCE_LIMITS},
    assemblyIdentity: {
      distributionContract: "lmdj.web-runtime-host.distribution.v1",
      hostId: "web-runtime-host",
      hostVersion: "1.2.15",
      platformVersion: "0.3.6",
      productBuild: TEST_PRODUCT_BUILD,
      protocolVersion: 1,
    },
    seams: {
      capabilityProbeTimeoutMs: 1,
      createAudioContext: () => ({state: "suspended"}),
      loadRuntime: async () => ({workers: []}),
      runtimeTerminator: async () => {},
      transport: {send: async () => {}, subscribe: () => () => {}},
      verifyManifest: async () => ({
        host_id: "web-runtime-host",
        host_version: "1.2.15",
        platform_version: "0.3.6",
        product_build: TEST_PRODUCT_BUILD,
        protocol_version: 1,
      }),
    },
  });
  assert.equal(await session.start(), false);
  await drainTasks();
  assert.deepEqual(session.diagnostics(), {
    ...session.diagnostics(),
    error_code: "HOST_TIMEOUT",
    state: "failed",
  });
  assert.equal(terminated, 1);
  assert.equal(revoked, 1);
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
    hostVersion: "1.2.0",
    platformVersion: "0.3.6",
    productBuild: TEST_PRODUCT_BUILD,
    protocolVersion: 1,
  };
  const manifestSource = {
    heapBytes: 536_870_912,
    resourceLimits: RESOURCE_LIMITS,
    emscripten: {
      emcc_version: "emcc",
      emscripten_releases_revision: "a".repeat(40),
      emsdk_revision: "b".repeat(40),
      emsdk_tag: "6.0.5",
    },
    compatibleHosts: [{host_id: "web-runtime-host", host_version: "1.2.15"}],
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

test("bridges Sequence authority without browser musical-clock math", async () => {
  const sessionId = "10000000-0000-4000-8000-000000000001";
  const patternId = "20000000-0000-4000-8000-000000000002";
  const nextPatternId = "20000000-0000-4000-8000-000000000003";
  const commandId = "30000000-0000-4000-8000-000000000004";
  const operations = [];
  const baseStatus = {
    state: "active",
    session_id: sessionId,
    pattern_id: patternId,
    pending_pattern_id: null,
    expected_revision: 5,
    next_flush_seq: 0,
    pending_event_count: 0,
    effective_runtime_frame: null,
  };
  const mutation = {
    ...baseStatus,
    committed_revision: null,
    replayed: false,
    project_revision: 5,
  };
  let switchRequested = false;
  let switchFlushed = false;
  const {session, emitNotification} = fixture({
    send: async (envelope) => {
      operations.push({operation: envelope.operation, payload: envelope.payload});
      switch (envelope.operation) {
        case "sequence.record.begin":
          return success(envelope, {
            ...mutation,
            transport_anchor: {
              runtime_frame: 48_000,
              tick_numerator: 0,
              bpm: 120,
            },
          });
        case "sequence.record.event":
          return success(envelope, {
            ...mutation,
            ...(switchFlushed ? {pattern_id: nextPatternId} : {}),
            pending_event_count: 1,
            runtime_frame: 48_120,
            input_sequence: 1,
          });
        case "sequence.record.flush":
        case "sequence.record.stop":
          if (switchRequested) switchFlushed = true;
          return success(envelope, {
            ...mutation,
            ...(switchRequested ? {
              pattern_id: nextPatternId,
              pending_pattern_id: null,
              effective_runtime_frame: null,
            } : {}),
            runtime_frame: 48_240,
            pattern_publication: null,
          });
        case "sequence.record.switch-request":
          switchRequested = true;
          return success(envelope, {
            ...mutation,
            state: "switching",
            pending_pattern_id: nextPatternId,
            effective_runtime_frame: 96_000,
            pattern_publication: {
              generation: 2,
              activation_frame: 96_000,
            },
          });
        case "pattern.create":
          return success(envelope, {
            committed_revision: 6,
            pattern_id: nextPatternId,
            bars: 4,
            replayed: false,
            project_revision: 6,
          });
        case "sequence.settings.update":
          return success(envelope, {
            committed_revision: 6,
            bpm: 132,
            quantize_enabled: false,
            swing_percent: 60,
            replayed: false,
            pattern_publication: null,
            project_revision: 6,
          });
        case "sequence.record.status":
          return success(envelope, {...baseStatus, project_revision: null});
        case "sequence.recovery.list":
          return success(envelope, {
            candidates: [{
              session_id: sessionId,
              pattern_id: patternId,
              bars: 1,
              reason: "owner_lost",
              event_count: 1,
            }],
            project_revision: null,
          });
        case "sequence.recovery.apply":
          return success(envelope, mutation);
        case "sequence.recovery.discard":
          return success(envelope, {
            session_id: sessionId,
            discarded: true,
            project_revision: null,
          });
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    },
  });
  await session.start();
  const boundaries = [];
  session.subscribeSequenceBarBoundary((value) => boundaries.push(value));
  const begun = await session.beginSequence({
    sessionId,
    patternId,
    expectedRevision: 5,
  });
  assert.deepEqual(begun.transportAnchor, {
    runtimeFrame: 48_000,
    tickNumerator: 0,
    bpm: 120,
  });
  const event = await session.recordSequenceEvent({
    sessionId,
    slot: 17,
    velocity: 100,
    pressed: true,
  });
  assert.equal(event.runtimeFrame, 48_120);
  assert.equal(event.inputSequence, 1);
  await session.flushSequence({sessionId, commandId});
  const switched = await session.requestPatternSwitch({
    sessionId,
    nextPatternId,
  });
  assert.equal(switched.pendingPatternId, nextPatternId);
  assert.equal(switched.effectiveRuntimeFrame, 96_000);
  emitNotification({
    protocol_version: 1,
    event: "sequence.bar_boundary",
    payload: {
      session_id: sessionId,
      pattern_id: nextPatternId,
      runtime_frame: 95_999,
      generation: 2,
    },
  });
  emitNotification({
    protocol_version: 1,
    event: "sequence.bar_boundary",
    payload: {
      session_id: sessionId,
      pattern_id: nextPatternId,
      runtime_frame: 96_000,
      generation: 2,
    },
  });
  emitNotification({
    protocol_version: 1,
    event: "sequence.bar_boundary",
    payload: {
      session_id: sessionId,
      pattern_id: nextPatternId,
      runtime_frame: 96_000,
      generation: 2,
    },
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(boundaries, [{
    sessionId,
    patternId: nextPatternId,
    runtimeFrame: 96_000,
    generation: 2,
  }]);
  assert.equal(Object.isFrozen(boundaries[0]), true);
  emitNotification({
    protocol_version: 1,
    event: "sequence.bar_boundary",
    payload: {
      session_id: sessionId,
      pattern_id: nextPatternId,
      runtime_frame: 96_000,
      generation: 2,
    },
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(operations.filter(({operation}) =>
    operation === "sequence.record.flush").length, 2);
  const boundaryFlush = operations.filter(({operation}) =>
    operation === "sequence.record.flush").at(-1).payload;
  assert.equal(boundaryFlush.session_id, sessionId);
  assert.match(
    boundaryFlush.command_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
  );
  const postBoundaryEvent = await session.recordSequenceEvent({
    sessionId,
    slot: 18,
    velocity: 90,
    pressed: true,
  });
  assert.equal(postBoundaryEvent.patternId, nextPatternId);
  assert.deepEqual(
    operations.slice(-2).map(({operation}) => operation),
    ["sequence.record.flush", "sequence.record.event"],
  );
  const settings = await session.updateSequenceSettings({
    expectedRevision: 5,
    sessionId,
    bpm: 132,
    quantizeEnabled: false,
    swingPercent: 60,
  });
  assert.deepEqual(settings, {
    committedRevision: 6,
    bpm: 132,
    quantizeEnabled: false,
    swingPercent: 60,
    replayed: false,
    patternPublication: null,
    projectRevision: 6,
  });
  const created = await session.createPattern({
    patternId: nextPatternId,
    bars: 4,
    expectedRevision: 5,
  });
  assert.deepEqual(created, {
    committedRevision: 6,
    patternId: nextPatternId,
    bars: 4,
    replayed: false,
    projectRevision: 6,
  });
  assert.equal((await session.querySequenceStatus()).state, "active");
  assert.deepEqual(await session.listSequenceRecovery(), [{
    sessionId,
    patternId,
    bars: 1,
    reason: "owner_lost",
    eventCount: 1,
  }]);
  await session.applySequenceRecovery({
    sessionId,
    destinationPatternId: null,
  });
  assert.equal(await session.discardSequenceRecovery(sessionId), true);
  await session.requestPatternSwitch({sessionId, nextPatternId});
  await session.stopSequence({sessionId, commandId});
  const flushCountAfterStop = operations.filter(({operation}) =>
    operation === "sequence.record.flush").length;
  emitNotification({
    protocol_version: 1,
    event: "sequence.bar_boundary",
    payload: {
      session_id: sessionId,
      pattern_id: nextPatternId,
      runtime_frame: 96_000,
      generation: 2,
    },
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(boundaries.length, 1);
  assert.equal(operations.filter(({operation}) =>
    operation === "sequence.record.flush").length, flushCountAfterStop);

  const eventPayload = operations.find(
    ({operation}) => operation === "sequence.record.event",
  ).payload.event;
  assert.deepEqual(eventPayload, {
    slot: {bank: 1, pad: 1},
    velocity: 100,
    pressed: true,
  });
  assert.equal(Object.hasOwn(eventPayload, "runtime_frame"), false);
  assert.equal(Object.hasOwn(eventPayload, "input_sequence"), false);
  const settingsPayload = operations.find(
    ({operation}) => operation === "sequence.settings.update",
  ).payload;
  assert.match(
    settingsPayload.command_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
  );
  delete settingsPayload.command_id;
  assert.deepEqual(settingsPayload, {
    expected_revision: 5,
    session_id: sessionId,
    bpm: 132,
    quantize_enabled: false,
    swing_percent: 60,
  });
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
      resource: "ingest_decoded_frames",
      observed: 43_200_001,
      limit: 43_200_000,
      storage_condition: "quota_exceeded",
      path: "/Users/private/project",
      request_id: "11111111-1111-4111-8111-111111111111",
      device_name: "Private MIDI",
    },
  }));
  await drainTasks();

  assert.deepEqual(states.at(-1), {
    state: "failed",
    errorCode: "WEB_RUNTIME_RESOURCE_LIMIT",
    errorDetails: {
      resource: "ingest_decoded_frames",
      observed: 43_200_001,
      limit: 43_200_000,
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

test("host-owned input keeps lifecycle listeners but creates no input adapter", async () => {
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
    "keydown",
    "keyup",
  ]) {
    assert.equal(browserWindow.count(type), 0, type);
  }
  assert.equal(browserWindow.count("blur"), 1);
  assert.equal(browserWindow.count("focus"), 1);
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

test("Sample queries bind flat slots to the current Project and validate typed results", async () => {
  const calls = [];
  const assetId = "11111111-1111-4111-8111-111111111111";
  const {session} = fixture({
    send: async (envelope, transportOptions) => {
      calls.push({envelope, transportOptions});
      if (envelope.operation === "sample.inspect") {
        return success(envelope, {
          project_revision: 7,
          slot: {bank: 2, pad: 1},
          asset_id: assetId,
          playback: WIRE_PLAYBACK,
          metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
          waveform_cache_identity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
        });
      }
      if (envelope.operation === "sample.waveform") {
        return success(envelope, {
          metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
          algorithm_version: 1,
          buckets: [
            {start_frame: 10, end_frame: 20, peak_magnitude: 32_768},
            {start_frame: 20, end_frame: 30, peak_magnitude: 12},
          ],
          project_revision: 7,
        });
      }
      if (envelope.operation === "sample.quota") {
        return success(envelope, {
          project_revision: 7,
          slot: {bank: 2, pad: 1},
          bank_quota_bytes: 67_108_864,
          bank_used_bytes: 4_000,
          bank_remaining_bytes: 67_104_864,
          project_quota_bytes: 134_217_728,
          project_used_bytes: 8_000,
          project_remaining_bytes: 134_209_728,
          effective_remaining_bytes: 67_104_864,
          effective_remaining_frames: 16_776_216,
          consumed: [{
            slot: {bank: 2, pad: 0},
            prepared_bytes: 4_000,
            prepared_frames: 1_000,
          }],
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  assert.deepEqual(await session.inspectSample(33), {
    projectRevision: 7,
    slot: 33,
    assetId,
    playback: PLAYBACK,
    metadata: {sampleRate: 48_000, channels: 2, sourceFrames: 100},
    waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
  });
  assert.deepEqual(await session.queryWaveform({
    slot: 33,
    window: {startFrame: 10, endFrame: 30, bucketCount: 2},
  }), {
    metadata: {sampleRate: 48_000, channels: 2, sourceFrames: 100},
    algorithmVersion: 1,
    buckets: [
      {startFrame: 10, endFrame: 20, peakMagnitude: 32_768},
      {startFrame: 20, endFrame: 30, peakMagnitude: 12},
    ],
    projectRevision: 7,
  });
  assert.deepEqual(await session.querySampleQuota(33), {
    projectRevision: 7,
    slot: 33,
    bankQuotaBytes: 67_108_864,
    bankUsedBytes: 4_000,
    bankRemainingBytes: 67_104_864,
    projectQuotaBytes: 134_217_728,
    projectUsedBytes: 8_000,
    projectRemainingBytes: 134_209_728,
    effectiveRemainingBytes: 67_104_864,
    effectiveRemainingFrames: 16_776_216,
    consumed: [{slot: 32, preparedBytes: 4_000, preparedFrames: 1_000}],
  });
  assert.deepEqual(session.sampleIngestLimits(), {
    sourceBytes: 104_857_600,
    decodedFrames: 43_200_000,
    channels: 2,
    artifactBytes: 68_157_440,
  });
  assert.deepEqual(calls.map(({envelope}) => ({
    operation: envelope.operation,
    payload: envelope.payload,
  })), [
    {operation: "sample.inspect", payload: {slot: {bank: 2, pad: 1}}},
    {
      operation: "sample.waveform",
      payload: {
        slot: {bank: 2, pad: 1},
        window: {start_frame: 10, end_frame: 30, bucket_count: 2},
      },
    },
    {operation: "sample.quota", payload: {slot: {bank: 2, pad: 1}}},
  ]);
  assert.deepEqual(
    calls.map(({transportOptions}) => transportOptions.deadlineMs),
    [30_000, 30_000, 30_000],
  );
});

test("Sample queries never overlap on the packaged Host request lane", async () => {
  let releaseFirst;
  const firstGate = new Promise((resolvePromise) => {
    releaseFirst = resolvePromise;
  });
  const calls = [];
  let inFlight = 0;
  let maximumInFlight = 0;
  const {session} = fixture({
    send: async (envelope) => {
      if (envelope.operation !== "sample.inspect") {
        return success(envelope, defaultResult(envelope.operation));
      }
      calls.push(envelope.payload.slot);
      inFlight += 1;
      maximumInFlight = Math.max(maximumInFlight, inFlight);
      if (calls.length === 1) await firstGate;
      inFlight -= 1;
      return success(envelope, {
        project_revision: 7,
        slot: envelope.payload.slot,
        asset_id: "11111111-1111-4111-8111-111111111111",
        playback: WIRE_PLAYBACK,
        metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
        waveform_cache_identity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
      });
    },
  });
  await session.start();

  const first = session.inspectSample(0);
  await drainTasks();
  const second = session.inspectSample(1);
  await drainTasks();
  assert.deepEqual(calls, [{bank: 0, pad: 0}]);
  assert.equal(maximumInFlight, 1);

  releaseFirst();
  const values = await Promise.all([first, second]);
  assert.deepEqual(values.map(({slot}) => slot), [0, 1]);
  assert.deepEqual(calls, [{bank: 0, pad: 0}, {bank: 0, pad: 1}]);
  assert.equal(maximumInFlight, 1);
});

test("Sample query rejects malformed Host output instead of exposing partial truth", async () => {
  const {session} = fixture({
    send: async (envelope) => success(envelope, {
      project_revision: 0,
      slot: {bank: 0, pad: 0},
      asset_id: null,
      playback: WIRE_PLAYBACK,
      metadata: null,
      waveform_cache_identity: null,
      project_path: "/private/project.lmdj",
    }),
  });
  await session.start();
  await assert.rejects(
    session.inspectSample(0),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
});

test("Sample query rejects noncanonical cache identity and waveform buckets", async () => {
  const assetId = "11111111-1111-4111-8111-111111111111";
  const snapshotError = (envelope, result) => success(envelope, result);
  const inspect = fixture({
    send: async (envelope) => snapshotError(envelope, {
      project_revision: 7,
      slot: {bank: 0, pad: 0},
      asset_id: assetId,
      playback: WIRE_PLAYBACK,
      metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
      waveform_cache_identity: `${"a".repeat(64)}/1/wrong-fold/1`,
    }),
  });
  await inspect.session.start();
  await assert.rejects(
    inspect.session.inspectSample(0),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );

  let queryCount = 0;
  const waveform = fixture({
    send: async (envelope) => {
      queryCount += 1;
      return success(envelope, {
        metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
        algorithm_version: queryCount === 1 ? 2 : 1,
        buckets: queryCount === 1
          ? [
              {start_frame: 0, end_frame: 4, peak_magnitude: 1},
              {start_frame: 4, end_frame: 8, peak_magnitude: 2},
              {start_frame: 8, end_frame: 10, peak_magnitude: 3},
            ]
          : [
              {start_frame: 0, end_frame: 3, peak_magnitude: 1},
              {start_frame: 3, end_frame: 7, peak_magnitude: 2},
              {start_frame: 7, end_frame: 10, peak_magnitude: 3},
            ],
        project_revision: 7,
      });
    },
  });
  await waveform.session.start();
  const query = {
    slot: 0,
    window: {startFrame: 0, endFrame: 10, bucketCount: 3},
  };
  await assert.rejects(
    waveform.session.queryWaveform(query),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
  await assert.rejects(
    waveform.session.queryWaveform(query),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
});

test("Project open and Sample mutations share one lane without conflict retry", async () => {
  const calls = [];
  let releaseOpen;
  const openGate = new Promise((resolvePromise) => {
    releaseOpen = resolvePromise;
  });
  const {session} = fixture({
    send: async (envelope) => {
      calls.push(envelope);
      if (envelope.operation === "project.open") {
        await openGate;
        return success(envelope, {});
      }
      if (envelope.operation === "sample.update_pad") {
        return {
          protocol_version: 1,
          request_id: envelope.request_id,
          ok: false,
          error: {
            code: "REVISION_CONFLICT",
            message: "Project revision changed",
            details: {actual_revision: 9, expected_revision: 8},
          },
        };
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  const opening = session.openProject(
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
  );
  const updating = session.updatePad({
    slot: 17,
    expectedRevision: 8,
    playback: PLAYBACK,
  });
  await Promise.resolve();
  assert.deepEqual(calls.map(({operation}) => operation), ["project.open"]);
  releaseOpen();
  await opening;
  await assert.rejects(
    updating,
    (error) => error.code === "REVISION_CONFLICT" &&
      error.details.actual_revision === 9 &&
      error.details.expected_revision === 8,
  );
  assert.deepEqual(calls.map(({operation}) => operation), [
    "project.open",
    "sample.update_pad",
  ]);
  assert.match(calls[1].payload.command_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  assert.deepEqual({...calls[1].payload, command_id: "<generated>"}, {
    command_id: "<generated>",
    expected_revision: 8,
    slot: {bank: 1, pad: 1},
    playback: WIRE_PLAYBACK,
  });
});

test("Sample mutations preserve committed and stale Runtime truth after Cook failure", async () => {
  const operations = [];
  const snapshotError = {
    code: "COOK_FAILED",
    message: "Sample runtime preparation failed",
    details: {},
  };
  const {session} = fixture({
    send: async (envelope) => {
      operations.push({operation: envelope.operation, payload: envelope.payload});
      if (envelope.operation === "sample.update_pad") {
        return success(envelope, {
          committed_revision: 12,
          runtime_revision: 11,
          runtime_published: false,
          snapshot_error: snapshotError,
        });
      }
      if (envelope.operation === "sample.reset_pad") {
        return success(envelope, {
          committed_revision: 13,
          runtime_revision: 13,
          runtime_published: true,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  assert.deepEqual(await session.updatePad({
    slot: 0,
    expectedRevision: 11,
    playback: PLAYBACK,
  }), {
    committedRevision: 12,
    runtimeRevision: 11,
    runtimePublished: false,
    snapshotError,
  });
  assert.deepEqual(await session.resetPad({slot: 0, expectedRevision: 12}), {
    committedRevision: 13,
    runtimeRevision: 13,
    runtimePublished: true,
    snapshotError: null,
  });
  assert.equal(operations.filter(({operation}) =>
    operation === "sample.update_pad").length, 1);
  assert.match(operations[1].payload.command_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  assert.deepEqual({
    ...operations[1],
    payload: {...operations[1].payload, command_id: "<generated>"},
  }, {
    operation: "sample.reset_pad",
    payload: {
      command_id: "<generated>",
      expected_revision: 12,
      slot: {bank: 0, pad: 0},
    },
  });
});

test("unassigned Pad mutations accept unpublished truth without a Cook error", async () => {
  const {session} = fixture({
    send: async (envelope) => {
      if (envelope.operation === "sample.update_pad") {
        return success(envelope, {
          committed_revision: 7,
          runtime_revision: 6,
          runtime_published: false,
        });
      }
      if (envelope.operation === "sample.reset_pad") {
        return success(envelope, {
          committed_revision: 8,
          runtime_revision: null,
          runtime_published: false,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  assert.deepEqual(await session.updatePad({
    slot: 0,
    expectedRevision: 6,
    playback: PLAYBACK,
  }), {
    committedRevision: 7,
    runtimeRevision: 6,
    runtimePublished: false,
    snapshotError: null,
  });
  assert.deepEqual(await session.resetPad({
    slot: 0,
    expectedRevision: 7,
  }), {
    committedRevision: 8,
    runtimeRevision: null,
    runtimePublished: false,
    snapshotError: null,
  });
});

test("Sample mutation output rejects incoherent truth and preserves delayed replay", async () => {
  const error = {
    code: "COOK_FAILED",
    message: "Sample runtime preparation failed",
    details: {},
  };
  const results = [
    {committed_revision: 2, runtime_revision: null, runtime_published: true},
    {
      committed_revision: 2,
      runtime_revision: 2,
      runtime_published: true,
      snapshot_error: error,
    },
    {committed_revision: 2, runtime_revision: 1, runtime_published: true},
    {committed_revision: 2, runtime_revision: 3, runtime_published: true},
    {
      committed_revision: 2,
      runtime_revision: 3,
      runtime_published: false,
      snapshot_error: error,
    },
  ];
  const {session} = fixture({
    send: async (envelope) => success(envelope, results.shift()),
  });
  await session.start();
  const request = {slot: 0, expectedRevision: 1, playback: PLAYBACK};
  for (let index = 0; index < 3; index += 1) {
    await assert.rejects(
      session.updatePad(request),
      (failure) => failure.code === "HOST_PROTOCOL_MISMATCH",
    );
  }
  assert.deepEqual(await session.updatePad(request), {
    committedRevision: 2,
    runtimeRevision: 3,
    runtimePublished: true,
    snapshotError: null,
  });
  assert.deepEqual(await session.updatePad(request), {
    committedRevision: 2,
    runtimeRevision: 3,
    runtimePublished: false,
    snapshotError: error,
  });
});

test("Snapshot retry output enforces ready generation Runtime and error coherence", async () => {
  const projectId = "11111111-1111-4111-8111-111111111111";
  const patternId = "22222222-2222-4222-8222-222222222222";
  const error = {
    code: "COOK_FAILED",
    message: "Sample runtime preparation failed",
    details: {},
  };
  const result = (overrides) => ({
    project_id: projectId,
    project_revision: 9,
    pattern_id: patternId,
    runtime_ready: true,
    generation: 4,
    snapshot_error: null,
    runtime_revision: 9,
    ...overrides,
  });
  const invalidResults = [
    result({generation: null}),
    result({runtime_revision: null}),
    result({snapshot_error: error}),
    result({runtime_ready: false, generation: 4, runtime_revision: 8,
      snapshot_error: error}),
    result({runtime_ready: false, generation: null, runtime_revision: 8,
      snapshot_error: null}),
  ];
  const retry = async (wireResult) => {
    const {session} = fixture({
      send: async (envelope) => success(
        envelope,
        envelope.operation === "snapshot.retry"
          ? wireResult
          : defaultResult(envelope.operation),
      ),
    });
    await session.start();
    return {session, pending: session.retryPrepare(patternId)};
  };
  for (const invalid of invalidResults) {
    const attempt = await retry(invalid);
    await assert.rejects(
      attempt.pending,
      (failure) => failure.code === "HOST_PROTOCOL_MISMATCH",
    );
    await drainTasks();
    assert.equal(attempt.session.diagnostics().state, "failed");
  }
  const ready = await retry(result({}));
  assert.deepEqual(await ready.pending, {
    projectId,
    projectRevision: 9,
    patternId,
    runtimeReady: true,
    generation: 4,
    snapshotError: null,
    runtimeRevision: 9,
  });
  const rejected = await retry(result({
    runtime_ready: false,
    generation: null,
    runtime_revision: 8,
    snapshot_error: error,
  }));
  assert.deepEqual(await rejected.pending, {
    projectId,
    projectRevision: 9,
    patternId,
    runtimeReady: false,
    generation: null,
    snapshotError: error,
    runtimeRevision: 8,
  });
});

test("non-positive or unsafe ready generation fails through Runtime safety", async () => {
  const patternId = "22222222-2222-4222-8222-222222222222";
  for (const generation of [0, Number.MAX_SAFE_INTEGER + 1]) {
    const operations = [];
    const {emitNotification, session} = fixture({
      send: async (envelope) => {
        operations.push(envelope.operation);
        if (envelope.operation === "snapshot.retry") {
          return success(envelope, {
            project_id: "11111111-1111-4111-8111-111111111111",
            project_revision: 9,
            pattern_id: patternId,
            runtime_ready: true,
            generation,
            snapshot_error: null,
            runtime_revision: 9,
          });
        }
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await session.start();
    emitNotification({
      protocol_version: 1,
      event: "snapshot.published",
      payload: {generation: 6, project_revision: 9},
    });
    await session.setSamplePreview(0, PLAYBACK);
    operations.length = 0;

    await assert.rejects(
      session.retryPrepare(patternId),
      (error) => error.code === "HOST_PROTOCOL_MISMATCH",
    );
    assert.equal(session.diagnostics().state, "audio-suspended");
    assert.equal(session.diagnostics().control_generation, 6);
    await drainTasks();
    await drainTasks();
    assert.deepEqual(operations, [
      "snapshot.retry",
      "sample.preview.clear",
      "sample.stop",
    ]);
    assert.equal(session.diagnostics().state, "failed");
    assert.equal(session.diagnostics().error_code, "HOST_PROTOCOL_MISMATCH");
    assert.equal(session.diagnostics().control_generation, 6);
  }
});

test("Sample import streams one bounded hashed sidecar and commits one typed result", async () => {
  const bytes = new Uint8Array(1_048_576);
  bytes[0] = 0x52;
  bytes[bytes.length - 1] = 0x7f;
  const slices = [];
  const file = {
    name: "private-source-name.wav",
    size: bytes.byteLength,
    slice(start, end) {
      slices.push([start, end]);
      return new Blob([bytes.subarray(start, end)]);
    },
  };
  const calls = [];
  const progress = [];
  let importToken = null;
  const {session} = fixture({
    send: async (envelope, transportOptions) => {
      calls.push({envelope, transportOptions});
      if (envelope.operation === "sample.import.begin") {
        importToken = envelope.payload.import_token;
        return success(envelope, {
          token: importToken,
          expected_bytes: bytes.byteLength,
        });
      }
      if (envelope.operation === "sample.import.chunk") {
        return success(envelope, {
          received_bytes: bytes.byteLength,
          final: true,
        });
      }
      if (envelope.operation === "sample.import.commit") {
        return success(envelope, {
          committed_revision: 4,
          runtime_revision: 4,
          runtime_published: true,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  assert.deepEqual(await session.importAssignSample(file, {
    slot: 63,
    expectedRevision: 3,
    onProgress(value) {
      progress.push(value);
    },
  }), {
    committedRevision: 4,
    runtimeRevision: 4,
    runtimePublished: true,
    snapshotError: null,
  });
  assert.deepEqual(slices, [[0, 1_048_576]]);
  assert.deepEqual(calls.map(({envelope}) => envelope.operation), [
    "sample.import.begin",
    "sample.import.chunk",
    "sample.import.commit",
  ]);
  const begin = calls[0].envelope.payload;
  assert.deepEqual(Object.keys(begin).sort(), [
    "asset_id", "byte_length", "command_id", "expected_revision",
    "import_token", "slot",
  ]);
  assert.equal(begin.import_token, importToken);
  assert.equal(begin.expected_revision, 3);
  assert.deepEqual(begin.slot, {bank: 3, pad: 15});
  assert.equal(begin.byte_length, 1_048_576);
  assert.notEqual(begin.command_id, begin.import_token);
  assert.notEqual(begin.asset_id, begin.import_token);
  assert.notEqual(begin.asset_id, begin.command_id);
  const chunk = calls[1];
  assert.deepEqual(chunk.envelope.payload, {
    import_token: importToken,
    offset: 0,
    final: true,
    sidecar: {
      sidecar_bytes: 1_048_576,
      sidecar_sha256:
        "44c0f55ba202bf8354b1427354c2f6d08b1bc4f2d31a21c810ef15cf51aa8e9a",
    },
  });
  assert.equal(chunk.transportOptions.deadlineMs, 30_000);
  assert.equal(chunk.transportOptions.sidecar.byteLength, 1_048_576);
  assert.equal(chunk.transportOptions.sidecar[0], 0x52);
  assert.equal(chunk.transportOptions.sidecar.at(-1), 0x7f);
  assert.equal(JSON.stringify(calls.map(({envelope}) => envelope)).includes(
    file.name,
  ), false);
  assert.deepEqual(progress, [
    {completedBytes: 0, totalBytes: 1_048_576},
    {completedBytes: 1_048_576, totalBytes: 1_048_576},
  ]);
});

test("Sample import enforces the verified manifest total before begin", async () => {
  const operations = [];
  const file = new Blob([Uint8Array.of(1, 2, 3, 4)]);
  const {session} = fixture({
    manifestSource: {
      resourceLimits: {imported_wav_bytes: 3},
    },
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  await assert.rejects(
    session.importAssignSample(file, {slot: 0, expectedRevision: 0}),
    (error) => error.code === "WEB_RUNTIME_RESOURCE_LIMIT" &&
      error.details.limit === 3 &&
      error.details.observed === 4,
  );
  assert.deepEqual(operations, []);
});

test("Sample import cancellation before begin is a no-op and after begin aborts once", async () => {
  const before = new AbortController();
  before.abort();
  const beforeCalls = [];
  const file = new Blob([Uint8Array.of(1, 2, 3, 4)]);
  const first = fixture({
    send: async (envelope) => {
      beforeCalls.push(envelope.operation);
      return success(envelope, {});
    },
  });
  await first.session.start();
  await assert.rejects(
    first.session.importAssignSample(file, {
      slot: 0,
      expectedRevision: 0,
      signal: before.signal,
    }),
    (error) => error.name === "AbortError",
  );
  assert.deepEqual(beforeCalls, []);

  const during = new AbortController();
  const duringCalls = [];
  const second = fixture({
    send: async (envelope, transportOptions) => {
      duringCalls.push({
        operation: envelope.operation,
        signal: transportOptions.signal,
      });
      if (envelope.operation === "sample.import.begin") {
        return success(envelope, {
          token: envelope.payload.import_token,
          expected_bytes: file.size,
        });
      }
      if (envelope.operation === "sample.import.chunk") {
        during.abort();
        return success(envelope, {received_bytes: file.size, final: true});
      }
      if (envelope.operation === "sample.import.abort") {
        return success(envelope, {aborted: true});
      }
      throw new Error(`unexpected operation ${envelope.operation}`);
    },
  });
  await second.session.start();
  await assert.rejects(
    second.session.importAssignSample(file, {
      slot: 0,
      expectedRevision: 0,
      signal: during.signal,
    }),
    (error) => error.name === "AbortError",
  );
  assert.deepEqual(duringCalls.map(({operation}) => operation), [
    "sample.import.begin",
    "sample.import.chunk",
    "sample.import.abort",
  ]);
  assert.equal(duringCalls[0].signal, during.signal);
  assert.equal(duringCalls[1].signal, during.signal);
  assert.equal(duringCalls[2].signal, undefined);
});

test("Sample import keeps the primary Host failure while aborting once", async () => {
  const operations = [];
  const file = new Blob([Uint8Array.of(1, 2, 3, 4)]);
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      if (envelope.operation === "sample.import.begin") {
        return success(envelope, {
          token: envelope.payload.import_token,
          expected_bytes: file.size,
        });
      }
      if (envelope.operation === "sample.import.chunk") {
        return {
          protocol_version: 1,
          request_id: envelope.request_id,
          ok: false,
          error: {
            code: "IO_ERROR",
            message: "Sample storage operation failed",
            details: {},
          },
        };
      }
      if (envelope.operation === "sample.import.abort") {
        return success(envelope, {aborted: true});
      }
      throw new Error(`unexpected operation ${envelope.operation}`);
    },
  });
  await session.start();
  await assert.rejects(
    session.importAssignSample(file, {slot: 0, expectedRevision: 0}),
    (error) => error.code === "IO_ERROR",
  );
  assert.deepEqual(operations, [
    "sample.import.begin",
    "sample.import.chunk",
    "sample.import.abort",
  ]);
});

test("malformed Sample abort response fails the session without hiding the primary error", async () => {
  const operations = [];
  const file = new Blob([Uint8Array.of(1, 2, 3, 4)]);
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      if (envelope.operation === "sample.import.begin") {
        return success(envelope, {
          token: envelope.payload.import_token,
          expected_bytes: file.size,
        });
      }
      if (envelope.operation === "sample.import.chunk") {
        return {
          protocol_version: 1,
          request_id: envelope.request_id,
          ok: false,
          error: {
            code: "IO_ERROR",
            message: "Sample storage operation failed",
            details: {},
          },
        };
      }
      if (envelope.operation === "sample.import.abort") {
        return success(envelope, {aborted: false});
      }
      if (envelope.operation === "sample.stop") {
        return success(envelope, {accepted: true, scope: "all"});
      }
      throw new Error(`unexpected operation ${envelope.operation}`);
    },
  });
  await session.start();
  await assert.rejects(
    session.importAssignSample(file, {slot: 0, expectedRevision: 0}),
    (error) => error.code === "IO_ERROR",
  );
  await drainTasks();
  assert.deepEqual(operations, [
    "sample.import.begin",
    "sample.import.chunk",
    "sample.import.abort",
    "sample.stop",
  ]);
  assert.equal(session.diagnostics().state, "failed");
  assert.equal(
    session.diagnostics().error_code,
    "HOST_PROTOCOL_MISMATCH",
  );
});

test("Sample preview, release, stop, and retry use exact Runtime-only envelopes", async () => {
  const calls = [];
  const projectId = "11111111-1111-4111-8111-111111111111";
  const patternId = "22222222-2222-4222-8222-222222222222";
  const {session} = fixture({
    send: async (envelope, transportOptions) => {
      calls.push({envelope, transportOptions});
      if (envelope.operation === "sample.preview.set" ||
          envelope.operation === "sample.preview.clear") {
        return success(envelope, {accepted: true});
      }
      if (envelope.operation === "trigger") {
        return success(envelope, {accepted: true});
      }
      if (envelope.operation === "sample.stop") {
        return success(envelope, {
          accepted: true,
          scope: Object.hasOwn(envelope.payload, "slot") ? "slot" : "all",
        });
      }
      if (envelope.operation === "snapshot.retry") {
        return success(envelope, {
          project_id: projectId,
          project_revision: 9,
          pattern_id: patternId,
          runtime_ready: false,
          generation: null,
          snapshot_error: {
            code: "COOK_FAILED",
            message: "Sample runtime preparation failed",
            details: {},
          },
          runtime_revision: 8,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  assert.equal(await session.setSamplePreview(18, PLAYBACK), true);
  assert.equal(await session.clearSamplePreview(18), true);
  assert.equal(await session.clearSamplePreview(18), false);
  assert.equal(await session.release(18, "keyboard"), true);
  assert.equal(await session.stopPad(18), true);
  assert.equal(await session.stopAll(), true);
  assert.deepEqual(await session.retryPrepare(patternId), {
    projectId,
    projectRevision: 9,
    patternId,
    runtimeReady: false,
    generation: null,
    snapshotError: {
      code: "COOK_FAILED",
      message: "Sample runtime preparation failed",
      details: {},
    },
    runtimeRevision: 8,
  });
  assert.deepEqual(calls.map(({envelope}) => ({
    operation: envelope.operation,
    payload: envelope.payload,
  })), [
    {
      operation: "sample.preview.set",
      payload: {slot: {bank: 1, pad: 2}, playback: WIRE_PLAYBACK},
    },
    {
      operation: "sample.preview.clear",
      payload: {slot: {bank: 1, pad: 2}},
    },
    {operation: "trigger", payload: {slot: 18, kind: "release"}},
    {operation: "sample.stop", payload: {slot: {bank: 1, pad: 2}}},
    {operation: "sample.stop", payload: {}},
    {operation: "snapshot.retry", payload: {pattern_id: patternId}},
  ]);
  assert.deepEqual(calls.map(({transportOptions}) =>
    transportOptions.deadlineMs), [1_000, 1_000, 1_000, 1_000, 1_000, 30_000]);
});

test("Sample preview ownership is bounded to 64 slots and idempotent on clear", async () => {
  const operations = [];
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, {accepted: true});
    },
  });
  await session.start();
  for (let slot = 0; slot < 64; slot += 1) {
    assert.equal(await session.setSamplePreview(slot, PLAYBACK), true);
  }
  await assert.rejects(session.setSamplePreview(64, PLAYBACK), RangeError);
  assert.equal(await session.clearSamplePreview(0), true);
  assert.equal(await session.clearSamplePreview(0), false);
  assert.equal(operations.filter((value) =>
    value === "sample.preview.set").length, 64);
  assert.equal(operations.filter((value) =>
    value === "sample.preview.clear").length, 1);
});

test("Voice state subscriptions deliver validated events in transport order", async () => {
  const {emitNotification, session} = fixture();
  await session.start();
  const first = [];
  const second = [];
  const unsubscribeFirst = session.subscribeVoiceState((event) => {
    first.push(event);
  });
  const unsubscribeSecond = session.subscribeVoiceState((event) => {
    second.push(event);
  });
  emitNotification({
    protocol_version: 1,
    event: "runtime.voice_state",
    payload: {
      events: [
        {
          sequence: 9,
          slot: 17,
          state: "started",
          runtime_frame: 100,
          source_frame: 20,
        },
        {
          sequence: 9,
          slot: 17,
          state: "completed",
          runtime_frame: 180,
          source_frame: 100,
        },
      ],
    },
  });
  unsubscribeFirst();
  unsubscribeFirst();
  emitNotification({
    protocol_version: 1,
    event: "runtime.voice_state",
    payload: {
      events: [{
        sequence: 10,
        slot: 3,
        state: "stopped",
        runtime_frame: 181,
        source_frame: 44,
      }],
    },
  });
  unsubscribeSecond();
  assert.deepEqual(first, [
    {sequence: 9, slot: 17, state: "started", runtimeFrame: 100, sourceFrame: 20},
    {sequence: 9, slot: 17, state: "completed", runtimeFrame: 180, sourceFrame: 100},
  ]);
  assert.deepEqual(second, [
    ...first,
    {sequence: 10, slot: 3, state: "stopped", runtimeFrame: 181, sourceFrame: 44},
  ]);
});

test("Voice listener count is bounded and malformed events fail closed", async () => {
  const {emitNotification, session} = fixture();
  await session.start();
  const unsubscribers = [];
  for (let index = 0; index < 64; index += 1) {
    unsubscribers.push(session.subscribeVoiceState(() => {}));
  }
  assert.throws(
    () => session.subscribeVoiceState(() => {}),
    (error) => error.code === "WEB_RUNTIME_RESOURCE_LIMIT",
  );
  emitNotification({
    protocol_version: 1,
    event: "runtime.voice_state",
    payload: {events: [{sequence: 1, slot: 64, state: "started",
      runtime_frame: 0, source_frame: 0}]},
  });
  await drainTasks();
  assert.equal(session.diagnostics().state, "failed");
  assert.equal(session.diagnostics().error_code, "HOST_PROTOCOL_MISMATCH");
  for (const unsubscribe of unsubscribers) unsubscribe();
});

test("Snapshot notifications accept only the exact legacy and Task 6 variants", async () => {
  const snapshotError = {
    code: "COOK_FAILED",
    message: "Sample runtime preparation failed",
    details: {},
  };
  const {emitNotification, session} = fixture();
  await session.start();

  emitNotification({
    protocol_version: 1,
    event: "snapshot.published",
    payload: {generation: 5},
  });
  assert.equal(session.diagnostics().control_generation, 5);
  emitNotification({
    protocol_version: 1,
    event: "snapshot.published",
    payload: {generation: 6, project_revision: 9},
  });
  assert.equal(session.diagnostics().control_generation, 6);
  emitNotification({
    protocol_version: 1,
    event: "snapshot.rejected",
    payload: {error: snapshotError},
  });
  emitNotification({
    protocol_version: 1,
    event: "snapshot.rejected",
    payload: {
      project_revision: 10,
      runtime_revision: 9,
      error: snapshotError,
    },
  });
  await drainTasks();
  assert.equal(session.diagnostics().state, "audio-suspended");
  assert.equal(session.diagnostics().control_generation, 6);
});

test("non-positive or unsafe published generations fail without mutation", async () => {
  const payloads = [
    {generation: 0},
    {generation: 0, project_revision: 7},
    {generation: Number.MAX_SAFE_INTEGER + 1},
    {
      generation: Number.MAX_SAFE_INTEGER + 1,
      project_revision: 7,
    },
  ];
  for (const payload of payloads) {
    const operations = [];
    const {emitNotification, session} = fixture({
      send: async (envelope) => {
        operations.push(envelope.operation);
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await session.start();
    emitNotification({
      protocol_version: 1,
      event: "snapshot.published",
      payload: {generation: 6, project_revision: 6},
    });
    await session.setSamplePreview(0, PLAYBACK);
    operations.length = 0;

    emitNotification({
      protocol_version: 1,
      event: "snapshot.published",
      payload,
    });

    assert.equal(session.diagnostics().state, "audio-suspended");
    assert.equal(session.diagnostics().control_generation, 6);
    await drainTasks();
    await drainTasks();
    assert.deepEqual(operations, ["sample.preview.clear", "sample.stop"]);
    assert.equal(session.diagnostics().state, "failed");
    assert.equal(session.diagnostics().error_code, "HOST_PROTOCOL_MISMATCH");
    assert.equal(session.diagnostics().control_generation, 6);
  }
});

test("malformed Snapshot notifications fail after safety without partial state", async () => {
  const snapshotError = {
    code: "COOK_FAILED",
    message: "Sample runtime preparation failed",
    details: {},
  };
  const cases = [
    {
      event: "snapshot.published",
      payload: {generation: "7"},
    },
    {
      event: "snapshot.published",
      payload: {
        generation: 7,
        project_revision: 7,
        project_path: "/private/project.lmdj",
      },
    },
    {
      event: "snapshot.rejected",
      payload: {error: snapshotError, extra: true},
    },
    {
      event: "snapshot.rejected",
      payload: {
        project_revision: 7,
        runtime_revision: "6",
        error: snapshotError,
      },
    },
    {
      event: "snapshot.rejected",
      payload: {
        project_revision: 7,
        runtime_revision: 6,
        error: {...snapshotError, extra: true},
      },
    },
  ];
  for (const malformed of cases) {
    const operations = [];
    const {emitNotification, session} = fixture({
      send: async (envelope) => {
        operations.push(envelope.operation);
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await session.start();
    emitNotification({
      protocol_version: 1,
      event: "snapshot.published",
      payload: {generation: 6, project_revision: 6},
    });
    await session.setSamplePreview(0, PLAYBACK);
    operations.length = 0;

    emitNotification({protocol_version: 1, ...malformed});

    assert.equal(session.diagnostics().state, "audio-suspended");
    assert.equal(session.diagnostics().control_generation, 6);
    await drainTasks();
    await drainTasks();
    assert.deepEqual(operations, ["sample.preview.clear", "sample.stop"]);
    assert.equal(session.diagnostics().state, "failed");
    assert.equal(
      session.diagnostics().error_code,
      "HOST_PROTOCOL_MISMATCH",
    );
  }
});

test("wired Pointer and Keyboard inputs emit one press and exact-source release", async () => {
  const browserWindow = new EventTarget();
  const pad = new EventTarget();
  const calls = [];
  let sequence = 0;
  const {session} = fixture({
    browserWindow,
    inputConfiguration: {
      padBindings: [{element: pad, slot: {bank: 1, pad: 1}}],
      keyboardMapping: {KeyA: 17},
    },
    send: async (envelope) => {
      calls.push(envelope);
      if (envelope.operation === "trigger" &&
          Object.hasOwn(envelope.payload, "velocity")) {
        sequence += 1;
        return success(envelope, {sequence});
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));

  pad.dispatchEvent(browserEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 7,
    clientX: 1,
    clientY: 2,
  }));
  pad.dispatchEvent(browserEvent("pointerup", {pointerId: 7, button: 0}));
  browserWindow.dispatchEvent(browserEvent("keydown", {
    code: "KeyA",
    repeat: false,
  }));
  browserWindow.dispatchEvent(browserEvent("keydown", {
    code: "KeyA",
    repeat: true,
  }));
  browserWindow.dispatchEvent(browserEvent("keyup", {code: "KeyA"}));
  await drainTasks();

  assert.deepEqual(calls.filter(({operation}) => operation === "trigger")
    .map(({payload}) => payload), [
    {slot: 17, velocity: 100},
    {slot: 17, kind: "release"},
    {slot: 17, velocity: 100},
    {slot: 17, kind: "release"},
  ]);
});

test("wired Pointer ignores unavailable presses without a later release", async () => {
  const browserWindow = new EventTarget();
  const pad = new EventTarget();
  const calls = [];
  const {session} = fixture({
    browserWindow,
    inputConfiguration: {
      padBindings: [{element: pad, slot: {bank: 0, pad: 0}}],
    },
    send: async (envelope) => {
      calls.push(envelope);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  pad.dispatchEvent(browserEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 1,
  }));
  browserWindow.dispatchEvent(browserEvent("pointerup", {
    button: 0,
    pointerId: 1,
  }));
  await drainTasks();

  assert.deepEqual(calls.filter(({operation}) => operation === "trigger"), []);
  assert.equal(session.diagnostics().pressed_count, 0);
});

test("foreign pointerup cannot release the Pointer that owns the Pad", async () => {
  const browserWindow = new EventTarget();
  const pad = new EventTarget();
  const triggerPayloads = [];
  const {session} = fixture({
    browserWindow,
    inputConfiguration: {
      padBindings: [{element: pad, slot: {bank: 0, pad: 4}}],
    },
    send: async (envelope) => {
      if (envelope.operation === "trigger") {
        triggerPayloads.push(envelope.payload);
        return success(envelope, Object.hasOwn(envelope.payload, "velocity")
          ? {sequence: 1}
          : {accepted: true});
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));

  pad.dispatchEvent(browserEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 7,
  }));
  pad.dispatchEvent(browserEvent("pointerup", {button: 0, pointerId: 8}));
  await drainTasks();
  assert.deepEqual(triggerPayloads, [{slot: 4, velocity: 100}]);
  assert.equal(session.diagnostics().pressed_count, 1);

  pad.dispatchEvent(browserEvent("pointerup", {button: 0, pointerId: 7}));
  await drainTasks();
  assert.deepEqual(triggerPayloads, [
    {slot: 4, velocity: 100},
    {slot: 4, kind: "release"},
  ]);
  assert.equal(session.diagnostics().pressed_count, 0);
});

test("foreign pointercancel cannot release the owner or clear its preview", async () => {
  const browserWindow = new EventTarget();
  const pad = new EventTarget();
  const operations = [];
  const {session} = fixture({
    browserWindow,
    inputConfiguration: {
      padBindings: [{element: pad, slot: {bank: 0, pad: 5}}],
    },
    send: async (envelope) => {
      operations.push({operation: envelope.operation, payload: envelope.payload});
      if (
        envelope.operation === "trigger" &&
        Object.hasOwn(envelope.payload, "velocity")
      ) {
        return success(envelope, {sequence: 1});
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.setSamplePreview(5, PLAYBACK);
  pad.dispatchEvent(browserEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 7,
  }));
  await drainTasks();
  operations.length = 0;

  pad.dispatchEvent(browserEvent("pointercancel", {pointerId: 8}));
  await drainTasks();
  assert.deepEqual(operations, []);
  assert.equal(session.diagnostics().pressed_count, 1);

  pad.dispatchEvent(browserEvent("pointercancel", {pointerId: 7}));
  await drainTasks();
  assert.deepEqual(operations.map(({operation}) => operation), [
    "trigger",
    "sample.preview.clear",
  ]);
  assert.equal(session.diagnostics().pressed_count, 0);
});

test("pointercancel and Escape clear previews without an Authoring mutation", async () => {
  const browserWindow = new EventTarget();
  const pad = new EventTarget();
  const calls = [];
  const {session} = fixture({
    browserWindow,
    inputConfiguration: {
      padBindings: [{element: pad, slot: {bank: 0, pad: 2}}],
    },
    send: async (envelope) => {
      calls.push(envelope);
      if (envelope.operation === "trigger" &&
          Object.hasOwn(envelope.payload, "velocity")) {
        return success(envelope, {sequence: 1});
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.setSamplePreview(2, PLAYBACK);
  pad.dispatchEvent(browserEvent("pointerdown", {
    isPrimary: true,
    button: 0,
    pointerId: 8,
    clientX: 1,
    clientY: 2,
  }));
  pad.dispatchEvent(browserEvent("pointercancel", {pointerId: 8}));
  await drainTasks();

  await session.setSamplePreview(3, PLAYBACK);
  browserWindow.dispatchEvent(browserEvent("keydown", {
    code: "Escape",
    repeat: false,
  }));
  await drainTasks();

  assert.deepEqual(calls.filter(({operation}) =>
    operation === "sample.preview.clear").map(({payload}) => payload), [
    {slot: {bank: 0, pad: 2}},
    {slot: {bank: 0, pad: 3}},
  ]);
  assert.deepEqual(calls.filter(({operation}) =>
    ["sample.import.begin", "sample.update_pad", "sample.reset_pad"]
      .includes(operation)), []);
});

test("host-owned input still drains an in-flight preview before adverse stop", async () => {
  const browserWindow = new EventTarget();
  const operations = [];
  let previewStarted;
  const previewWasStarted = new Promise((resolvePromise) => {
    previewStarted = resolvePromise;
  });
  let finishPreview;
  const {session} = fixture({
    browserWindow,
    inputOwnership: "host",
    send: async (envelope) => {
      operations.push(envelope.operation);
      if (envelope.operation === "sample.preview.set" && finishPreview === undefined) {
        previewStarted();
        return new Promise((resolvePromise) => {
          finishPreview = () => resolvePromise(success(envelope, {accepted: true}));
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  operations.length = 0;

  const setting = session.setSamplePreview(4, PLAYBACK);
  await previewWasStarted;
  browserWindow.dispatchEvent(new Event("blur"));
  const lateSetting = session.setSamplePreview(5, PLAYBACK);
  finishPreview();

  assert.equal(await setting, true);
  assert.equal(await lateSetting, false);
  await drainTasks();
  assert.deepEqual(operations.slice(0, 4), [
    "sample.preview.set",
    "sample.preview.clear",
    "sample.stop",
    "audio.suspend",
  ]);
  assert.equal(operations.filter((value) =>
    value === "sample.preview.set").length, 1);
});

test("adverse cleanup cancels an in-flight Sample query before the safety stop", async () => {
  const browserWindow = new EventTarget();
  const operations = [];
  const querySignals = [];
  const queryCancellations = [];
  let releaseQuery;
  let waveformAttempts = 0;
  const {session} = fixture({
    browserWindow,
    send: async (envelope, transportOptions) => {
      operations.push(envelope.operation);
      if (envelope.operation === "sample.waveform") {
        waveformAttempts += 1;
        querySignals.push(transportOptions.signal);
        queryCancellations.push(transportOptions.cancelQuery);
        if (waveformAttempts > 1) {
          return success(envelope, {
            metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
            algorithm_version: 1,
            buckets: [{
              start_frame: 0,
              end_frame: 100,
              peak_magnitude: 1,
            }],
            project_revision: 7,
          });
        }
        return new Promise((resolvePromise, rejectPromise) => {
          releaseQuery = () => resolvePromise(success(envelope, {
            metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
            algorithm_version: 1,
            buckets: [{
              start_frame: 0,
              end_frame: 100,
              peak_magnitude: 1,
            }],
            project_revision: 7,
          }));
          transportOptions.signal.addEventListener("abort", () => {
            rejectPromise(new DOMException("cancelled", "AbortError"));
          }, {once: true});
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.setSamplePreview(4, PLAYBACK);
  operations.length = 0;

  const query = session.queryWaveform({
    slot: 4,
    window: {startFrame: 0, endFrame: 100, bucketCount: 1},
  });
  const queryResult = query.then(
    (value) => ({value}),
    (error) => ({error}),
  );
  await drainTasks();
  browserWindow.dispatchEvent(new Event("blur"));
  await drainTasks();
  await drainTasks();

  try {
    assert.equal(querySignals[0]?.aborted, true);
    assert.equal(queryCancellations[0], true);
    const settled = await queryResult;
    assert.equal(settled.error, undefined);
    assert.equal(settled.value.projectRevision, 7);
    assert.deepEqual(operations.slice(0, 4), [
      "sample.waveform",
      "sample.preview.clear",
      "sample.stop",
      "audio.suspend",
    ]);
    assert.equal(operations.filter((operation) =>
      operation === "sample.waveform").length, 2);
    assert.equal(queryCancellations[1], true);
  } finally {
    releaseQuery?.();
    await query.catch(() => {});
  }
});

test("adverse cleanup interrupts Project reads and retries them after the safety stop", async () => {
  const summary = {
    project_id: "10000000-0000-4000-8000-000000000001",
    pattern_id: "20000000-0000-4000-8000-000000000002",
    revision: 7,
    bpm: 120,
    asset_count: 1,
    assigned_pad_count: 1,
    bundle_digest: "a".repeat(64),
  };
  const cases = [
    {
      operation: "project.inspect",
      query: (session) => session.inspectProject(),
      result: {project_revision: 7},
    },
    {
      operation: "project.list",
      query: (session) => session.listLocalProjects(),
      result: {projects: [summary]},
    },
  ];

  for (const item of cases) {
    const browserWindow = new EventTarget();
    const operations = [];
    const querySignals = [];
    let attempts = 0;
    let releaseQuery;
    const {session} = fixture({
      browserWindow,
      send: async (envelope, transportOptions) => {
        operations.push(envelope.operation);
        if (envelope.operation === item.operation) {
          attempts += 1;
          querySignals.push(transportOptions.signal);
          if (attempts > 1) return success(envelope, item.result);
          return new Promise((resolvePromise, rejectPromise) => {
            releaseQuery = () => resolvePromise(success(envelope, item.result));
            transportOptions.signal?.addEventListener("abort", () => {
              rejectPromise(new DOMException("cancelled", "AbortError"));
            }, {once: true});
          });
        }
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await session.start();
    await session.activateAudio(createUserGestureToken({isTrusted: true}));
    await session.setSamplePreview(4, PLAYBACK);
    operations.length = 0;

    const query = item.query(session);
    const queryResult = query.then(
      (value) => ({value}),
      (error) => ({error}),
    );
    await drainTasks();
    browserWindow.dispatchEvent(new Event("blur"));
    await drainTasks();
    await drainTasks();

    try {
      assert.equal(querySignals[0]?.aborted, true, item.operation);
      const settled = await queryResult;
      assert.equal(settled.error, undefined, item.operation);
      assert.equal(attempts, 2, item.operation);
      const stopIndex = operations.indexOf("sample.stop");
      const retryIndex = operations.lastIndexOf(item.operation);
      assert.ok(stopIndex >= 0, item.operation);
      assert.ok(retryIndex > stopIndex, item.operation);
    } finally {
      releaseQuery?.();
      await query.catch(() => {});
      await session.close();
    }
  }
});

test("fatal observations clear preview and stop voices before failed is observable", async () => {
  const operations = [];
  const {emitNotification, emitTransportFailure, session, terminated} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      if (
        envelope.operation === "trigger" &&
        Object.hasOwn(envelope.payload, "velocity")
      ) {
        return success(envelope, {sequence: 1});
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.setSamplePreview(7, PLAYBACK);
  await session.trigger(7, 100, "pointer");
  operations.length = 0;
  const failedObservations = [];
  session.subscribeHostState(({state}) => {
    if (state === "failed") {
      failedObservations.push([...operations]);
    }
  });

  const malformedVoice = {
    protocol_version: 1,
    event: "runtime.voice_state",
    payload: {events: [{
      sequence: 1,
      slot: 64,
      state: "started",
      runtime_frame: 0,
      source_frame: 0,
    }]},
  };
  emitNotification(malformedVoice);
  emitNotification(malformedVoice);
  emitTransportFailure({code: "IO_ERROR"});

  assert.equal(session.diagnostics().state, "running");
  await drainTasks();
  await drainTasks();
  assert.deepEqual(operations, ["sample.preview.clear", "sample.stop"]);
  assert.equal(session.diagnostics().state, "failed");
  assert.deepEqual(failedObservations, [["sample.preview.clear", "sample.stop"]]);
  assert.equal(terminated(), 1);
});

test("suspend and close clear inputs then previews then stop once before transition", async () => {
  const browserWindow = new EventTarget();
  const operations = [];
  let sequence = 0;
  const {session} = fixture({
    browserWindow,
    inputConfiguration: {keyboardMapping: {KeyA: 0}},
    send: async (envelope) => {
      operations.push(envelope.operation);
      if (envelope.operation === "trigger" &&
          Object.hasOwn(envelope.payload, "velocity")) {
        sequence += 1;
        return success(envelope, {sequence});
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.setSamplePreview(0, PLAYBACK);
  browserWindow.dispatchEvent(browserEvent("keydown", {
    code: "KeyA",
    repeat: false,
  }));
  await drainTasks();
  operations.length = 0;

  assert.equal(await session.suspendAudio(), true);
  assert.deepEqual(operations, [
    "sample.preview.clear",
    "sample.stop",
    "audio.suspend",
  ]);
  assert.equal(session.diagnostics().state, "audio-suspended");
  operations.length = 0;

  assert.equal(await session.close(), true);
  assert.deepEqual(operations, ["sample.stop", "host.close"]);
  assert.equal(session.diagnostics().state, "closed");
});

test("explicit suspend keeps the AudioContext rendering until Host quiescence", async () => {
  let releaseHostSuspend;
  let hostSuspendStartedResolve;
  const hostSuspendStarted = new Promise((resolvePromise) => {
    hostSuspendStartedResolve = resolvePromise;
  });
  const {context, session} = fixture({
    send: async (envelope) => {
      if (envelope.operation === "audio.suspend") {
        hostSuspendStartedResolve();
        return new Promise((resolvePromise) => {
          releaseHostSuspend = () => resolvePromise(success(envelope, {}));
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));

  const suspending = session.suspendAudio();
  await hostSuspendStarted;
  assert.equal(context.state, "running");

  releaseHostSuspend();
  assert.equal(await suspending, true);
  assert.equal(context.state, "suspended");
});

test("visibility cleanup is once per adverse edge and repeats after a later edge", async () => {
  const browserWindow = new EventTarget();
  const browserDocument = new EventTarget();
  browserDocument.visibilityState = "visible";
  const operations = [];
  const {session} = fixture({
    browserDocument,
    browserWindow,
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  operations.length = 0;

  browserDocument.visibilityState = "hidden";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  await drainTasks();
  assert.equal(operations.filter((value) => value === "sample.stop").length, 1);

  browserDocument.visibilityState = "visible";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  browserDocument.visibilityState = "hidden";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  await drainTasks();
  assert.equal(operations.filter((value) => value === "sample.stop").length, 2);
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
      if (envelope.operation === "sample.stop") {
        lifecycle.push("stop-all");
        return success(envelope, {accepted: true, scope: "all"});
      }
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
  await drainTasks();

  assert.equal(forcedTerminations, 0);
  assert.deepEqual(lifecycle, ["stop-all", "clean-close"]);
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

test("recovery probe readiness waits until Runtime safety releases", async () => {
  const browserWindow = new EventTarget();
  const {session} = fixture({
    browserWindow,
    send: async (envelope) => success(
      envelope,
      envelope.operation === "trigger"
        ? {sequence: 8}
        : envelope.operation === "host.status"
          ? {acknowledged_generation: 1, control_generation: 1}
          : defaultResult(envelope.operation),
    ),
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));

  browserWindow.dispatchEvent(browserEvent("pagehide", {persisted: true}));
  for (let attempt = 0; attempt < 100; ++attempt) {
    if (session.diagnostics().recovery_probe_ready === true) break;
    await Promise.resolve();
  }

  assert.equal(session.diagnostics().recovery_probe_ready, true);
  assert.deepEqual(await session.trigger(0, 100, "keyboard"), {
    sequence: 8,
    slot: 0,
    velocity: 100,
    source: "keyboard",
  });
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
  await drainTasks();
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
  await drainTasks();
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
