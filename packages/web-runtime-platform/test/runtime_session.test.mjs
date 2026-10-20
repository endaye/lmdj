import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

import {MasterTapBatchQueue} from
  "../../../apps/creator-web/src/record/master_tap_source.ts";
import {createDiagnosticClient} from "../web/diagnostic_client.mjs";
import {createUserGestureToken} from "../web/input_adapters.mjs";
import {createPerformanceMasterTap} from "../web/performance_master_capture.mjs";
import {createRuntimeSession} from "../web/runtime_session.mjs";
import {decodeLegacyPatternTransportStatus} from "./fixtures/legacy_pattern_transport_status.mjs";

const TEST_PRODUCT_BUILD = "9.8.7.6";

const API = [
  "monitorDestination",
  "monitorVolume",
  "setMonitorVolume",
  "runCandidateJob", "inspectCandidateJob", "cancelCandidateJob", "discardCandidateSet",
  "auditionCandidate", "stopCandidateAudition", "adoptCandidates",
  "listProviders",
  "configureProviderPermissions",
  "selectProvider",
  "runProvider",
  "inspectAttempt",
  "activateAudio",
  "applyFxGesture",
  "applyPerformanceLiveControl",
  "applyPerformanceRecovery",
  "applySequenceRecovery",
  "assignPatternSlot",
  "assignPad",
  "beginPerformanceRecording",
  "beginPerformanceReplay",
  "beginSequence",
  "bindPerformanceRecording",
  "clearSamplePreview",
  "clearPatternSlot",
  "close",
  "waitForTerminalCleanup",
  "commitPerformanceResample",
  "createPattern",
  "editPatternEvents",
  "resizePattern",
  "doubleUpPattern",
  "copyPattern",
  "deletePerformance",
  "diagnostics",
  "discardPerformance",
  "discardPerformanceRecovery",
  "discardSequenceRecovery",
  "disarmSequenceCapture",
  "flushSequence",
  "createProject",
  "duplicateProject",
  "importProject",
  "installSoundSet",
  "importAssignSample",
  "inspectSample",
  "inspectSoundSet",
  "inspectPerformance",
  "inspectProject",
  "inspectAuthoringHistory",
  "undoAuthoring",
  "redoAuthoring",
  "listPerformanceRecovery",
  "listPerformances",
  "listLocalProjects",
  "listSequenceRecovery",
  "auditionSoundSet",
  "listSoundSets",
  "describeSoundSetCatalog",
  "acquireSoundSetSlot",
  "installSoundSetSlot",
  "openProject",
  "performanceMasterCaptureStatus",
  "movePatternSlot",
  "previewSoundSetMap",
  "stopSoundSetAudition",
  "queryPerformanceLiveStatus",
  "queryPerformanceRecordingStatus",
  "queryPerformanceReplayStatus",
  "querySampleQuota",
  "queryWaveform",
  "querySequenceStatus",
  "recordSequenceEvent",
  "recordPerformanceEvent",
  "preparePerformancePadEvent",
  "reserveInputGesture",
  "renamePerformance",
  "release",
  "reloadSnapshot",
  "requestMidi",
  "requestPerformancePatternLaunch",
  "requestPatternSwitch",
  "requestPatternTransport",
  "requestPatternInput",
  "inspectPatternInput",
  "inspectPatternTransport",
  "queryPatternCountInCapabilities",
  "setCountInMetronome",
  "requestPatternCountIn",
  "inspectPatternCountIn",
  "cancelPatternCountIn",
  "requestTransportPatternSwitch",
  "resetPad",
  "deletePad",
  "setPadColour",
  "retryPrepare",
  "setSamplePreview",
  "sampleAudioClock",
  "sampleIngestLimits",
  "start",
  "savePerformance",
  "startPerformanceMasterCapture",
  "subscribeDiagnostics",
  "stopAll",
  "stopPerformanceRecording",
  "stopPerformanceReplay",
  "stopSequence",
  "stopPad",
  "subscribeHostState",
  "subscribePerformanceMasterCaptureStatus",
  "subscribeRuntimeOutcome",
  "subscribeSequenceBarBoundary",
  "subscribeVoiceState",
  "suspendAudio",
  "trigger",
  "flushPerformanceRecording",
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

// A session playback always carries every field; parity fields default, and
// every EQ band is bypassed.
const SESSION_PLAYBACK = Object.freeze({
  ...PLAYBACK,
  reverse: false,
  pitchCents: 0,
  pan: 0,
  loopMode: "forward",
  loopStartFrame: null,
  loopCrossfadeFrames: 0,
  attackMs: 0,
  releaseMs: 0,
  tone: 0,
  eq: {low: null, mid: null, high: null},
});

// lmdj.project.v5 5.1.0: the shared fixture holds every PadPlayback copy to
// one shape (.agents/pitfalls/parity-check-between-agreeing-copies.md).
const PAD_PLAYBACK_FULL = JSON.parse(
  readFileSync(
    new URL("../../../tests/fixtures/contracts/pad-playback-full.json", import.meta.url),
    "utf8",
  ),
);

function sessionPlaybackFrom(wire) {
  return {
    trimStartFrame: wire.trim_start_frame,
    trimEndFrame: wire.trim_end_frame,
    triggerMode: wire.trigger_mode,
    gainMillidb: wire.gain_millidb,
    muted: wire.muted,
    reverse: wire.reverse ?? false,
    pitchCents: wire.pitch_cents ?? 0,
    pan: wire.pan ?? 0,
    loopMode: wire.loop_mode ?? "forward",
    loopStartFrame: wire.loop_start_frame ?? null,
    loopCrossfadeFrames: wire.loop_crossfade_frames ?? 0,
    attackMs: wire.attack_ms ?? 0,
    releaseMs: wire.release_ms ?? 0,
    tone: wire.tone ?? 0,
    eq: {
      low: wire.eq?.low === undefined ? null : {
        kind: wire.eq.low.kind,
        freqHz: wire.eq.low.freq_hz,
        gainMillidb: wire.eq.low.gain_millidb,
      },
      mid: wire.eq?.mid === undefined ? null : {
        freqHz: wire.eq.mid.freq_hz,
        gainMillidb: wire.eq.mid.gain_millidb,
        qMilli: wire.eq.mid.q_milli,
      },
      high: wire.eq?.high === undefined ? null : {
        kind: wire.eq.high.kind,
        freqHz: wire.eq.high.freq_hz,
        gainMillidb: wire.eq.high.gain_millidb,
      },
    },
  };
}

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
  perform_recording_frames: 86_400_000,
  perform_recording_queue_batches: 32,
});

function success(envelope, result = {}) {
  return {
    protocol_version: 1,
    request_id: envelope.request_id,
    ok: true,
    result,
  };
}

function resolveThen(response, action) {
  return {
    then(resolvePromise) {
      resolvePromise(response);
      action();
    },
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
    "pattern.transport.count-in.capabilities": {supported: true, negotiated: true, output_ready: true,
      runtime_generation: "1", frame_epoch: "1", next_serial: "1", input_capacity: 1024},
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
  patternTransport,
  runtimeTransport,
  sessionTransport,
  timers,
  publishRuntime = false,
  runtimeTerminator,
  audioCallbackHeartbeat,
  audioEngineEpochHeartbeat,
  startAudioWorklet,
  startAudioWorkletWithCountIn,
  setCountInMetronome,
  registerAudioNode,
  createPerformanceMasterTap,
  connectAudioWorkletDirect,
  preflight,
  beforeRuntimeLoad,
  beforeManifest,
  useDefaultRuntimeLoader = false,
  verifiedManifest,
  now,
  inputOwnership,
  onPressedChange,
  soundsetCatalog,
  manifestSource = {
    resourceLimits: RESOURCE_LIMITS,
  },
} = {}) {
  let request = 0;
  let terminated = 0;
  let notificationListener = null;
  let failureListener = null;
  let defaultAudioCallbackHeartbeat = 0;
  const context = Object.assign(new EventTarget(), {
    state: "suspended",
    currentTime: 0,
    destination: {kind: "speakers"},
    createGain() {
      const calls = [];
      return {
        context: this,
        connected: [],
        disconnected: [],
        gain: {
          value: 1, calls,
          setValueAtTime(value, time) { this.value = value; calls.push(["set", value, time]); },
          cancelAndHoldAtTime(time) { calls.push(["hold", time]); },
          linearRampToValueAtTime(value, time) { this.value = value; calls.push(["ramp", value, time]); },
        },
        connect(destination) { this.connected.push(destination); },
        disconnect() { this.disconnected.push(true); },
      };
    },
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
    inputConfiguration: {
      ...inputConfiguration,
      ...(onPressedChange === undefined ? {} : {onPressedChange}),
    },
    inputOwnership,
    ...(patternTransport === undefined ? {} : {patternTransport}),
    soundsetCatalog,
    seams: {
      ...(capabilities === undefined ? {} : {capabilities}),
      ...(capabilityProbeTimeoutMs === undefined
        ? {}
        : {capabilityProbeTimeoutMs}),
      createAudioContext: () => context,
      ...(useDefaultRuntimeLoader ? {} : {loadRuntime: async (_manifest, invocation) => {
        if (beforeRuntimeLoad !== undefined) await beforeRuntimeLoad(invocation);
        const loaded = {
        registerAudioContext: () => 1,
        registerAudioNode: registerAudioNode ?? (() => 2),
        audioCallbackHeartbeat:
          audioCallbackHeartbeat ??
          (() => ++defaultAudioCallbackHeartbeat),
        ...(audioEngineEpochHeartbeat === undefined ? {} : {audioEngineEpochHeartbeat}),
        startAudioWorklet:
          startAudioWorklet ?? (async () => ({ok: true})),
        ...(startAudioWorkletWithCountIn === undefined ? {} : {
          startAudioWorkletWithCountIn,
        }),
        ...(setCountInMetronome === undefined ? {} : {setCountInMetronome}),
        connectAudioWorkletDirect:
          connectAudioWorkletDirect ?? (() => true),
        workers: [],
        ...(runtimeTransport === undefined
          ? {}
          : {transport: runtimeTransport}),
        };
        invocation?.onRuntimeOwnerCreated?.(loaded);
        if (publishRuntime) browserWindow.lmdjWebRuntimeHost = loaded;
        return loaded;
      }}),
      preflight: preflight ?? (async () => {}),
      ...(createPerformanceMasterTap === undefined
        ? {}
        : {createPerformanceMasterTap}),
      runtimeTerminator: async (...arguments_) => {
        terminated += 1;
        await runtimeTerminator?.(...arguments_);
      },
      transport: sessionTransport ?? transport,
      verifyManifest: async () => {
        if (beforeManifest !== undefined) await beforeManifest();
        return verifiedManifest ?? {
        host_id: "web-runtime-host",
        host_version: "1.2.15",
        platform_version: "0.3.6",
        product_build: TEST_PRODUCT_BUILD,
        protocol_version: 1,
        };
      },
      ...(now === undefined ? {} : {now}),
      ...(timers === undefined ? {} : {timers}),
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

test("monitor volume is applied before audio starts and changes no Project or capture request", async () => {
  const registered = [];
  const starts = [];
  const requests = [];
  const {session, context} = fixture({
    registerAudioNode: (node) => { registered.push(node); return 2; },
    startAudioWorklet: (...args) => { starts.push(args); return {ok: true}; },
    send: async (request) => { requests.push(request); return success(request, defaultResult(request.operation)); },
  });
  await session.start();
  const before = requests.length;
  assert.equal(session.monitorVolume(), 100);
  assert.equal(session.monitorDestination(), null);
  session.setMonitorVolume(25);
  assert.equal(requests.length, before);
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const monitor = session.monitorDestination();
  assert.deepEqual(registered, [monitor]);
  assert.deepEqual(starts, [[1, 2]]);
  assert.deepEqual(monitor.connected, [context.destination]);
  assert.deepEqual(monitor.gain.calls[0], ["set", 0.25, 0]);
  const activated = requests.length;
  context.currentTime = 2;
  session.setMonitorVolume(0);
  assert.equal(session.monitorVolume(), 0);
  assert.deepEqual(monitor.gain.calls.slice(-2), [["hold", 2], ["ramp", 0, 2.02]]);
  assert.equal(requests.length, activated);
  for (const value of [-1, 101, NaN, Infinity, "25"]) {
    assert.throws(() => session.setMonitorVolume(value));
  }
  assert.equal(session.monitorVolume(), 0);
  await session.close();
  assert.deepEqual(monitor.disconnected, [true]);
  assert.equal(session.monitorDestination(), null);
  assert.throws(() => session.setMonitorVolume(100));
});

test("capture failure recovers through the same monitor instead of bypassing volume", async () => {
  const tapNode = Object.assign(new EventTarget(), {disconnect(destination) { this.disconnected = destination; }});
  const direct = [];
  let captureDestination;
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {perform_recording_frames: 86_400_000, perform_recording_queue_batches: 32},
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    registerAudioNode: (node) => node === tapNode ? 3 : 2,
    createPerformanceMasterTap: async ({destination}) => {
      captureDestination = destination;
      return {destinationNode: tapNode, failProcessor() {}, async close() {}, async start() { return {async stop() {}}; }};
    },
    connectAudioWorkletDirect: (...args) => { direct.push(args); return true; },
  });
  await session.start();
  session.setMonitorVolume(0);
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  assert.equal(captureDestination, session.monitorDestination());
  tapNode.dispatchEvent(new Event("processorerror"));
  tapNode.dispatchEvent(new Event("processorerror"));
  await drainTasks();
  assert.deepEqual(direct, [[1, 2]]);
  assert.equal(tapNode.disconnected, session.monitorDestination());
  assert.equal(session.monitorDestination().gain.value, 0);
});

test("closing while the context parks cannot create a late monitor graph", async () => {
  const {session, context} = fixture();
  const parked = Promise.withResolvers();
  context.suspend = () => parked.promise;
  context.createGain = () => { assert.fail("closed bootstrap must not create a gain"); };
  await session.start();
  const activation = session.activateAudio(createUserGestureToken({isTrusted: true}));
  await drainTasks();
  await session.close();
  parked.resolve();
  assert.equal(await activation, false);
  assert.equal(session.monitorDestination(), null);
});

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

test("derives immutable Perform capture configuration only from exact injected limits and URL", () => {
  const unconfigured = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
  }).session;
  assert.deepEqual(unconfigured.performanceMasterCaptureStatus(), {
    state: "unconfigured", config: null, error: null,
  });

  for (const invalid of [0, -1, 1.5, "32", Number.MAX_SAFE_INTEGER + 1]) {
    const candidate = fixture({
      browserDocument: {baseURI: "https://example.test/creator/"},
      manifestSource: {
        resourceLimits: {
          perform_recording_frames: 86_400_000,
          perform_recording_queue_batches: invalid,
        },
        performanceMasterTapUrl: "./assets/perform-master-tap.js",
      },
    }).session;
    assert.equal(candidate.performanceMasterCaptureStatus().state, "unconfigured");
  }

  const configured = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
  }).session;
  assert.deepEqual(configured.performanceMasterCaptureStatus(), {
    state: "configured",
    config: {
      performRecordingFrames: 86_400_000,
      performRecordingQueueBatches: 32,
    },
    error: null,
  });
  assert.equal(Object.isFrozen(configured.performanceMasterCaptureStatus()), true);
  assert.equal(Object.isFrozen(configured.performanceMasterCaptureStatus().config), true);

  const crossOrigin = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "https://cdn.example/perform-master-tap.js",
    },
  }).session;
  assert.equal(crossOrigin.performanceMasterCaptureStatus().state, "unconfigured");
});

test("publishes capture unsupported before configured capability preflight failure", async () => {
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    preflight: async () => { throw new Error("capability missing"); },
  });
  const seen = [];
  const unsubscribe = session.subscribePerformanceMasterCaptureStatus(
    (status) => seen.push(status),
  );

  assert.equal(await session.start(), false);
  assert.deepEqual(seen, [
    {
      state: "configured",
      config: {
        performRecordingFrames: 86_400_000,
        performRecordingQueueBatches: 32,
      },
      error: null,
    },
    {
      state: "unavailable",
      config: {
        performRecordingFrames: 86_400_000,
        performRecordingQueueBatches: 32,
      },
      error: {
        code: "capture-unsupported",
        message: "Use a browser with the required secure audio and storage capabilities.",
      },
    },
  ]);
  assert.equal(session.performanceMasterCaptureStatus(), seen[1]);
  unsubscribe();
});

test("contains an initial capture status listener failure and returns idempotent unsubscribe", () => {
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
  });
  let calls = 0;
  let unsubscribe;
  assert.doesNotThrow(() => {
    unsubscribe = session.subscribePerformanceMasterCaptureStatus(() => {
      calls += 1;
      throw new Error("observer failed");
    });
  });
  assert.equal(calls, 1);
  assert.equal(typeof unsubscribe, "function");
  assert.doesNotThrow(() => {
    unsubscribe();
    unsubscribe();
  });
});

test("constructs and registers the tap before starting the engine", async () => {
  const order = [];
  const destinationNode = new EventTarget();
  destinationNode.disconnect = () => {};
  const tapController = {
    destinationNode,
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "https://example.test/assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => {
      order.push("tap");
      return tapController;
    },
    startAudioWorklet: async (_context, destination) => {
      order.push(["engine", destination]);
      return {ok: true};
    },
  });
  const seen = [];
  const unsubscribe = session.subscribePerformanceMasterCaptureStatus(
    (status) => seen.push(status.state),
  );
  await session.start();
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(order, ["tap", ["engine", 2]]);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");
  assert.deepEqual(seen, ["configured", "ready"]);
  unsubscribe();
});

test("native cue bypasses the master tap and shares only the downstream monitor gain", async () => {
  const nodes = [];
  const starts = [];
  const destinationNode = new EventTarget();
  destinationNode.disconnect = () => {};
  let tapMonitor;
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    registerAudioNode(node) { nodes.push(node); return nodes.length + 10; },
    createPerformanceMasterTap: async ({destination}) => {
      tapMonitor = destination;
      return {
        destinationNode,
        async start() { return {stop: async () => {}}; },
        failProcessor() {},
        async close() {},
      };
    },
    startAudioWorklet() { assert.fail("two-output Host must use its native cue entry point"); },
    startAudioWorkletWithCountIn(...args) { starts.push(args); return {ok: true, outputs: 2}; },
  });
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(starts, [[1, 13, 11]]);
  assert.equal(nodes[2], destinationNode);
  assert.equal(nodes[0], tapMonitor);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");
  await session.setMonitorVolume(37);
  assert.equal(tapMonitor.gain.value, 0.37);
  assert.deepEqual(starts, [[1, 13, 11]], "volume changes do not reconnect either stream");
  await session.close();
  assert.equal(nodes[1].disconnected.length, 1, "terminal cleanup retires the fallback product bus");
});

test("native cue remains separate from product output without a master tap", async () => {
  const nodes = [];
  const starts = [];
  const {context, session} = fixture({
    registerAudioNode(node) { nodes.push(node); return nodes.length + 10; },
    startAudioWorkletWithCountIn(...args) { starts.push(args); return {ok: true, outputs: 2}; },
  });
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(starts, [[1, 12, 11]]);
  assert.deepEqual(nodes[1].connected, [nodes[0]]);
  assert.deepEqual(nodes[0].connected, [context.destination]);
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), false);
  assert.equal(starts.length, 1);
  await session.close();
  assert.equal(nodes[1].disconnected.length, 1);
});

test("tap initialization failure preserves both native outputs with distinct product and cue routes", async () => {
  const nodes = [];
  const starts = [];
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    registerAudioNode(node) { nodes.push(node); return nodes.length + 10; },
    createPerformanceMasterTap: async () => { throw new Error("module missing"); },
    startAudioWorkletWithCountIn(...args) { starts.push(args); return {ok: true, outputs: 2}; },
  });
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(starts, [[1, 12, 11]]);
  assert.deepEqual(nodes[1].connected, [nodes[0]]);
  assert.equal(session.performanceMasterCaptureStatus().state, "unavailable");
  await session.close();
});

test("loads both AudioWorklet modules on a parked context so the device starts once, at the resume edge", async () => {
  const order = [];
  const destinationNode = new EventTarget();
  destinationNode.disconnect = () => {};
  const tapController = {
    destinationNode,
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  const {context, session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "https://example.test/assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => {
      order.push(["tap", context.state]);
      return tapController;
    },
    startAudioWorklet: async () => {
      order.push(["engine", context.state]);
      return {ok: true};
    },
  });
  // A context created inside the activation gesture is already running.
  // Chromium restarts a running destination when a Worklet module becomes
  // ready, which costs a second output-device start inside the budget.
  context.state = "running";
  const resume = context.resume;
  context.resume = async function () {
    order.push(["resume", this.state]);
    return resume.call(this);
  };
  await session.start();
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(order, [
    ["tap", "suspended"],
    ["engine", "suspended"],
    ["resume", "suspended"],
  ]);
});

test("tap initialization failure preserves direct live audio and publishes unavailable", async () => {
  const destinations = [];
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => {
      throw new Error("module missing");
    },
    startAudioWorklet: async (_context, destination) => {
      destinations.push(destination);
      return {ok: true};
    },
  });
  await session.start();
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(destinations, [2]);
  assert.deepEqual(session.performanceMasterCaptureStatus(), {
    state: "unavailable",
    config: {
      performRecordingFrames: 86_400_000,
      performRecordingQueueBatches: 32,
    },
    error: {
      code: "tap-initialization-failed",
      message: "Reload the page and activate audio again before retrying Perform capture",
    },
  });
  await assert.rejects(
    session.startPerformanceMasterCapture({
      onBatch() {}, onStopped() {}, onFailure() {},
    }),
    /capture is unavailable/,
  );
});

test("capture state refusals are typed while invalid sinks remain argument errors", async () => {
  const invalid = fixture().session;
  await assert.rejects(
    invalid.startPerformanceMasterCapture({}),
    {
      name: "TypeError",
      message: "A Performance master capture sink is required",
    },
  );
  const validSink = {onBatch() {}, onStopped() {}, onFailure() {}};
  await assert.rejects(
    invalid.startPerformanceMasterCapture(validSink),
    (error) => {
      assert.equal(error.code, "HOST_STATE_INVALID");
      assert.equal(
        error.message,
        "Performance master capture is unavailable; activate audio or reload before retrying",
      );
      return true;
    },
  );

  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.startPerformanceMasterCapture(validSink);
  await assert.rejects(
    session.startPerformanceMasterCapture(validSink),
    (error) => {
      assert.equal(error.code, "HOST_STATE_INVALID");
      assert.equal(
        error.message,
        "Performance master capture is already active; stop the current capture before starting another",
      );
      return true;
    },
  );
});

test("normalizes an underlying capture start race to a stable state error", async () => {
  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    async start() { throw new Error("Performance master capture is already active"); },
    failProcessor() {},
    async close() {},
  };
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await assert.rejects(
    session.startPerformanceMasterCapture({
      onBatch() {}, onStopped() {}, onFailure() {},
    }),
    (error) => {
      assert.equal(error.code, "HOST_STATE_INVALID");
      assert.equal(
        error.message,
        "Performance master capture state changed; retry after the current capture settles or reload",
      );
      return true;
    },
  );
});

test("closes a late tap factory result without publishing or starting the engine", async () => {
  let resolveFactory;
  let factoryStarted;
  const factoryStartedPromise = new Promise((resolve) => {
    factoryStarted = resolve;
  });
  const factoryResult = new Promise((resolve) => {
    resolveFactory = resolve;
  });
  const destinationNode = Object.assign(trackedEventTarget(), {
    disconnect() {},
  });
  let closes = 0;
  let registrations = 0;
  let engineStarts = 0;
  const tapController = {
    destinationNode,
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() { closes += 1; },
  };
  const {session} = fixture({
    browserDocument: Object.assign(new EventTarget(), {
      baseURI: "https://example.test/creator/",
      visibilityState: "visible",
    }),
    browserWindow: Object.assign(new EventTarget(), {
      performance: globalThis.performance,
    }),
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => {
      factoryStarted();
      return factoryResult;
    },
    registerAudioNode: (node) => {
      // Only late capture-node registration is forbidden; the monitor node
      // is installed before the asynchronous tap factory starts.
      if (node === destinationNode) registrations += 1;
      return 2;
    },
    startAudioWorklet: async () => { engineStarts += 1; return {ok: true}; },
  });
  const seen = [];
  session.subscribePerformanceMasterCaptureStatus(
    (status) => seen.push(status.state),
  );
  await session.start();
  const activation = session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  await factoryStartedPromise;
  const closing = session.close();
  resolveFactory(tapController);

  assert.equal(await activation, false);
  await closing;
  assert.equal(closes, 1);
  assert.equal(registrations, 0);
  assert.equal(engineStarts, 0);
  assert.equal(destinationNode.count("processorerror"), 0);
  assert.deepEqual(seen, ["configured"]);
  assert.equal(session.performanceMasterCaptureStatus().state, "configured");
});

test("finishes tap bootstrap while hidden and resumes on the next foreground gesture", async () => {
  let resolveFactory;
  let markFactoryStarted;
  const factoryStarted = new Promise((resolve) => {
    markFactoryStarted = resolve;
  });
  const factoryResult = new Promise((resolve) => { resolveFactory = resolve; });
  const browserDocument = Object.assign(new EventTarget(), {
    baseURI: "https://example.test/creator/",
    visibilityState: "visible",
  });
  const browserWindow = Object.assign(new EventTarget(), {
    performance: globalThis.performance,
  });
  const destinationNode = Object.assign(new EventTarget(), {disconnect() {}});
  const tapController = {
    destinationNode,
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  let engineStarts = 0;
  const {session} = fixture({
    browserDocument,
    browserWindow,
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => {
      markFactoryStarted();
      return factoryResult;
    },
    startAudioWorklet: async () => { engineStarts += 1; return {ok: true}; },
  });
  await session.start();
  const firstActivation = session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  await factoryStarted;
  browserDocument.visibilityState = "hidden";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  resolveFactory(tapController);

  assert.equal(await firstActivation, false);
  assert.equal(engineStarts, 1);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");

  browserDocument.visibilityState = "visible";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.equal(engineStarts, 1);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");
});

test("finishes engine bootstrap while hidden and resumes on the next foreground gesture", async () => {
  let resolveEngine;
  let markEngineStarted;
  const engineStarted = new Promise((resolve) => { markEngineStarted = resolve; });
  const engineResult = new Promise((resolve) => { resolveEngine = resolve; });
  const browserDocument = Object.assign(new EventTarget(), {
    baseURI: "https://example.test/creator/",
    visibilityState: "visible",
  });
  const browserWindow = Object.assign(new EventTarget(), {
    performance: globalThis.performance,
  });
  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  let engineStarts = 0;
  const {session} = fixture({
    browserDocument,
    browserWindow,
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
    startAudioWorklet: () => {
      engineStarts += 1;
      markEngineStarted();
      return engineResult;
    },
  });
  await session.start();
  const firstActivation = session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  await engineStarted;
  browserWindow.dispatchEvent(browserEvent("pagehide", {persisted: true}));
  resolveEngine({ok: true});

  assert.equal(await firstActivation, false);
  assert.equal(engineStarts, 1);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");

  browserWindow.dispatchEvent(new Event("pageshow"));
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.equal(engineStarts, 1);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");
});

test("hide-show during deferred tap bootstrap cannot revive the old gesture", async () => {
  let resolveFactory;
  let markFactoryStarted;
  const factoryStarted = new Promise((resolve) => {
    markFactoryStarted = resolve;
  });
  const factoryResult = new Promise((resolve) => { resolveFactory = resolve; });
  const browserDocument = Object.assign(new EventTarget(), {
    baseURI: "https://example.test/creator/",
    visibilityState: "visible",
  });
  const browserWindow = Object.assign(new EventTarget(), {
    performance: globalThis.performance,
  });
  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  let engineStarts = 0;
  const {session, context} = fixture({
    browserDocument,
    browserWindow,
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => {
      markFactoryStarted();
      return factoryResult;
    },
    startAudioWorklet: async () => { engineStarts += 1; return {ok: true}; },
  });
  let resumeCalls = 0;
  const resume = context.resume.bind(context);
  context.resume = async () => { resumeCalls += 1; await resume(); };
  await session.start();
  const firstActivation = session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  await factoryStarted;
  browserDocument.visibilityState = "hidden";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  browserDocument.visibilityState = "visible";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  resolveFactory(tapController);

  assert.equal(await firstActivation, false);
  assert.equal(resumeCalls, 0);
  assert.equal(engineStarts, 1);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.equal(resumeCalls, 1);
  assert.equal(engineStarts, 1);
});

test("pagehide-show during deferred engine bootstrap cannot revive the old gesture", async () => {
  let resolveEngine;
  let markEngineStarted;
  const engineStarted = new Promise((resolve) => { markEngineStarted = resolve; });
  const engineResult = new Promise((resolve) => { resolveEngine = resolve; });
  const browserDocument = Object.assign(new EventTarget(), {
    baseURI: "https://example.test/creator/",
    visibilityState: "visible",
  });
  const browserWindow = Object.assign(new EventTarget(), {
    performance: globalThis.performance,
  });
  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  let engineStarts = 0;
  const {session, context} = fixture({
    browserDocument,
    browserWindow,
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
    startAudioWorklet: () => {
      engineStarts += 1;
      markEngineStarted();
      return engineResult;
    },
  });
  let resumeCalls = 0;
  const resume = context.resume.bind(context);
  context.resume = async () => { resumeCalls += 1; await resume(); };
  await session.start();
  const firstActivation = session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  await engineStarted;
  browserWindow.dispatchEvent(browserEvent("pagehide", {persisted: true}));
  browserWindow.dispatchEvent(new Event("pageshow"));
  resolveEngine({ok: true});

  assert.equal(await firstActivation, false);
  assert.equal(resumeCalls, 0);
  assert.equal(engineStarts, 1);
  assert.equal(session.performanceMasterCaptureStatus().state, "ready");
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.equal(resumeCalls, 1);
  assert.equal(engineStarts, 1);
});

test("processor failure settles capture, detaches the tap, and connects direct output once", async () => {
  const destinationNode = new EventTarget();
  const disconnected = [];
  destinationNode.disconnect = (value) => disconnected.push(value);
  let failed = 0;
  let stopped = 0;
  let direct = 0;
  const tapController = {
    destinationNode,
    async start(sink) {
      return {
        async stop() {
          stopped += 1;
          sink.onFailure("tap-failure", 0);
        },
      };
    },
    failProcessor() { failed += 1; },
    async close() {},
  };
  const {session, context} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
    connectAudioWorkletDirect: () => { direct += 1; return true; },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.startPerformanceMasterCapture({
    onBatch() {}, onStopped() {}, onFailure() {},
  });

  destinationNode.dispatchEvent(new Event("processorerror"));
  destinationNode.dispatchEvent(new Event("processorerror"));
  await drainTasks();
  assert.equal(failed, 1);
  assert.equal(stopped, 1);
  assert.deepEqual(disconnected, [session.monitorDestination()]);
  assert.equal(direct, 1);
  assert.equal(session.performanceMasterCaptureStatus().state, "unavailable");
  assert.equal(
    session.performanceMasterCaptureStatus().error.code,
    "tap-processor-failed",
  );
  assert.equal(
    session.performanceMasterCaptureStatus().error.message,
    "Live audio recovery was required; reload the page and activate audio again before retrying Perform capture",
  );
});

test("early processor failure retries direct output after engine readiness before detaching the tap", async () => {
  let resolveEngineStart;
  let markEngineStarted;
  const engineStarted = new Promise((resolve) => { markEngineStarted = resolve; });
  const engineStart = new Promise((resolve) => { resolveEngineStart = resolve; });
  const order = [];
  const destinationNode = new EventTarget();
  destinationNode.disconnect = () => order.push("disconnect");
  const tapController = {
    destinationNode,
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  let directAttempts = 0;
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
    startAudioWorklet: () => {
      markEngineStarted();
      return engineStart;
    },
    connectAudioWorkletDirect: () => {
      directAttempts += 1;
      const connected = directAttempts === 2;
      order.push(`direct:${connected}`);
      return connected;
    },
  });
  await session.start();
  const activation = session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  await engineStarted;
  destinationNode.dispatchEvent(new Event("processorerror"));
  await drainTasks();
  assert.deepEqual(order, ["direct:false"]);

  resolveEngineStart({ok: true});
  assert.equal(await activation, true);
  assert.deepEqual(order, ["direct:false", "direct:true", "disconnect"]);
  assert.equal(session.performanceMasterCaptureStatus().state, "unavailable");
});

test("processor failure fails closed when direct output remains unavailable after readiness", async () => {
  let resolveEngineStart;
  let markEngineStarted;
  const engineStarted = new Promise((resolve) => { markEngineStarted = resolve; });
  const engineStart = new Promise((resolve) => { resolveEngineStart = resolve; });
  const destinationNode = Object.assign(new EventTarget(), {
    disconnect() { assert.fail("failed recovery must preserve the tap edge"); },
  });
  const tapController = {
    destinationNode,
    async start() { return {stop: async () => {}}; },
    failProcessor() {},
    async close() {},
  };
  let directAttempts = 0;
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
    startAudioWorklet: () => {
      markEngineStarted();
      return engineStart;
    },
    connectAudioWorkletDirect: () => { directAttempts += 1; return false; },
  });
  await session.start();
  const activation = session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  await engineStarted;
  destinationNode.dispatchEvent(new Event("processorerror"));
  await drainTasks();
  resolveEngineStart({ok: true});

  assert.equal(await activation, false);
  assert.equal(directAttempts, 2);
  assert.equal(session.diagnostics().error_code, "HOST_STATE_INVALID");
  await drainTasks();
  assert.equal(session.diagnostics().state, "failed");
});

test("underlying terminal acknowledgement releases session capture ownership", async () => {
  const underlyingSinks = [];
  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    async start(sink) {
      underlyingSinks.push(sink);
      return {stop: async () => { sink.onStopped(); }};
    },
    failProcessor() {},
    async close() {},
  };
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const terminals = [];
  await session.startPerformanceMasterCapture({
    onBatch() {},
    onFailure(...arguments_) { terminals.push(["failure", ...arguments_]); },
    onStopped() { terminals.push(["stopped"]); },
  });
  underlyingSinks[0].onFailure("tap-failure", 0);
  underlyingSinks[0].onStopped();

  const second = await session.startPerformanceMasterCapture({
    onBatch() {}, onFailure() {}, onStopped() {},
  });
  assert.equal(underlyingSinks.length, 2);
  assert.deepEqual(terminals, [
    ["failure", "tap-failure", 0],
    ["stopped"],
  ]);
  await second.stop();
});

// Use the existing capture factory and actual processor, as in the capture
// controller suite. The port/context stand-ins do not prove browser scheduling
// or physical audio; explicit ACK delivery exposes the SDK ownership window.
function masterCaptureFixture({send, holdStarted = false} = {}) {
  const commands = [];
  const messages = [];
  const pendingStarted = [];
  const order = [];
  let node;
  let Processor;
  let lowerStarts = 0;
  class ProcessorBase {
    constructor() {
      this.port = {
        onmessage: null,
        postMessage(message) {
          messages.push(message);
          order.push(`tap:${message.type}:${message.generation}`);
          if (holdStarted && message.type === "started") {
            pendingStarted.push(message);
          } else {
            node.port.onmessage({data: message});
          }
        },
      };
    }
  }
  vm.runInNewContext(readFileSync(
    new URL("../web/performance_master_tap_worklet.js", import.meta.url), "utf8",
  ), {
    AudioWorkletProcessor: ProcessorBase,
    Float32Array,
    Number,
    registerProcessor(name, constructor) {
      assert.equal(name, "lmdj-perform-master-tap");
      Processor = constructor;
    },
  });
  const processor = new Processor();
  const runtime = fixture({
    send,
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: RESOURCE_LIMITS,
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    async createPerformanceMasterTap(options) {
      options.context.audioWorklet = {async addModule() {}};
      const previousNode = globalThis.AudioWorkletNode;
      globalThis.AudioWorkletNode = class extends EventTarget {
        constructor() {
          super();
          node = this;
          this.port = {
            onmessage: null,
            postMessage(message) {
              commands.push(message);
              order.push(`host:${message.type}:${message.generation}`);
              processor.port.onmessage({data: message});
            },
          };
        }
        connect() {}
        disconnect() {}
      };
      try {
        const controller = await createPerformanceMasterTap(options);
        return {
          ...controller,
          start(...arguments_) {
            lowerStarts += 1;
            return controller.start(...arguments_);
          },
        };
      } finally {
        if (previousNode === undefined) delete globalThis.AudioWorkletNode;
        else globalThis.AudioWorkletNode = previousNode;
      }
    },
  });
  return {
    ...runtime, processor, commands, messages, order,
    get lowerStarts() { return lowerStarts; },
    receive(message) { node.port.onmessage({data: message}); },
    acknowledgeStart() {
      assert.equal(pendingStarted.length, 1);
      node.port.onmessage({data: pendingStarted.shift()});
    },
  };
}

test("a terminal capture's first late stop preserves a newer pending SDK owner", async () => {
  const runtime = masterCaptureFixture({holdStarted: true});
  const {session} = runtime;
  const terminals = [];
  const sink = {
    onBatch() { assert.fail("no PCM was rendered"); },
    onFailure(...values) { terminals.push(["failure", ...values]); },
    onStopped() { terminals.push(["stopped"]); },
  };
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const firstStart = session.startPerformanceMasterCapture(sink);
  runtime.acknowledgeStart();
  const first = await firstStart;
  // Malformed current-generation traffic terminates A before its wrapper's
  // first stop; the real lower controller retains A's settled stop promise.
  runtime.receive({type: "batch", generation: 1, sequence: 1, channels: []});
  assert.deepEqual(terminals, [["failure", "tap-failure", 0], ["stopped"]]);
  let secondStarted = false;
  const secondStart = session.startPerformanceMasterCapture(sink).then((value) => {
    secondStarted = true;
    return value;
  });
  await drainTasks();
  assert.equal(runtime.lowerStarts, 2);
  assert.equal(secondStarted, false);

  const firstStop = first.stop();
  assert.equal(first.stop(), firstStop);
  await firstStop;
  await assert.rejects(session.startPerformanceMasterCapture(sink), (error) => {
    assert.equal(error.code, "HOST_STATE_INVALID");
    assert.equal(error.message,
      "Performance master capture is already active; stop the current capture before starting another");
    return true;
  });
  assert.equal(runtime.lowerStarts, 2, "C must be refused before the lower start");
  assert.equal(runtime.commands.filter(({type}) => type === "start").length, 2);

  // A's late ACK cannot release B; only B's matching ACK completes its start.
  runtime.receive(runtime.messages.find(({type}) => type === "started"));
  await drainTasks();
  assert.equal(secondStarted, false);
  runtime.acknowledgeStart();
  const second = await secondStart;
  assert.equal(Object.isFrozen(second), true);
  const secondStop = second.stop();
  assert.equal(second.stop(), secondStop);
  await secondStop;
  assert.deepEqual(runtime.commands.filter(({type}) => type === "stop"), [
    {type: "stop", generation: 1}, {type: "stop", generation: 2},
  ]);
  assert.deepEqual(terminals, [
    ["failure", "tap-failure", 0], ["stopped"], ["stopped"],
  ]);
  await session.close();
  assert.equal(runtime.commands.filter(({type}) => type === "stop").length, 2);
});

test("interruption and close each settle the active capture once", async () => {
  const browserWindow = Object.assign(new EventTarget(), {
    performance: globalThis.performance,
  });
  let stops = 0;
  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    async start() {
      return {stop: async () => { stops += 1; }};
    },
    failProcessor() {},
    async close() {},
  };
  const {session} = fixture({
    browserWindow,
    browserDocument: Object.assign(new EventTarget(), {
      baseURI: "https://example.test/creator/",
      visibilityState: "visible",
    }),
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  await session.startPerformanceMasterCapture({
    onBatch() {}, onStopped() {}, onFailure() {},
  });
  browserWindow.dispatchEvent(new Event("blur"));
  await drainTasks();
  assert.equal(stops, 1);
  await session.close();
  assert.equal(stops, 1);
});

test("bridges raw Performance identities and values without Host timing authority", async () => {
  const operations = [];
  const sessionId = "00000000-0000-4000-8000-000000000101";
  const performanceId = "00000000-0000-4000-8000-000000000102";
  const eventId = "00000000-0000-4000-8000-000000000103";
  const gestureId = "00000000-0000-4000-8000-000000000104";
  const launchRequestId = "00000000-0000-4000-8000-000000000105";
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope);
      switch (envelope.operation) {
        case "performance.record.begin":
          return success(envelope, {
            performance_id: performanceId,
            committed_revision: 1,
            replayed: false,
            project_revision: 1,
          });
        case "performance.record.event":
          return success(envelope, {
            event_id: eventId,
            accepted_tick: 17,
            input_sequence: 1,
            coalesced: false,
            replayed: false,
            project_revision: null,
          });
        case "performance.record.launch-request":
          return success(envelope, {
            request_id: launchRequestId,
            state: "pending",
            target_tick: 3840,
            project_revision: null,
          });
        case "performance.record.status":
          return success(envelope, {
            state: "active",
            session_id: sessionId,
            performance_id: performanceId,
            journal_revision: 1,
            next_flush_seq: 1,
            pending_event_count: 1,
            open_pad_gestures: 1,
            open_fx_gestures: 0,
            hold: false,
            pending_launch: {
              request_id: launchRequestId,
              pattern_slot: 2,
              target_tick: 3840,
              claimed: false,
            },
            last_launch_ack: null,
            project_revision: null,
          });
        case "performance.resample.commit":
          return success(envelope, {
            performance_id: performanceId,
            committed_revision: 2,
            runtime_prepare_required: true,
            project_revision: 2,
          });
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    },
  });
  await session.start();
  await session.beginPerformanceRecording({
    sessionId,
    performanceId,
    expectedRevision: 0,
  });
  assert.deepEqual(await session.recordPerformanceEvent({
    sessionId,
    eventId,
    event: {kind: "pad_press", gestureId, slot: 7, velocity: 100},
  }), {
    eventId,
    acceptedTick: 17,
    inputSequence: 1,
    coalesced: false,
    replayed: false,
    projectRevision: null,
  });
  assert.deepEqual(await session.requestPerformancePatternLaunch({
    sessionId,
    requestId: launchRequestId,
    patternSlot: 2,
  }), {
    requestId: launchRequestId,
    state: "pending",
    targetTick: 3840,
    projectRevision: null,
  });
  const projected = await session.queryPerformanceRecordingStatus();
  assert.equal(projected.pendingLaunch.targetTick, 3840);
  assert.equal(projected.lastLaunchAck, null);
  assert.deepEqual(await session.commitPerformanceResample({
    expectedRevision: 1,
    performanceId,
    sourceStartFrame: 0,
    sourceEndFrame: 48_000,
    targetSlot: 18,
  }), {
    performanceId,
    committedRevision: 2,
    runtimePrepareRequired: true,
    projectRevision: 2,
  });

  const raw = operations.find(({operation}) =>
    operation === "performance.record.event").payload;
  assert.deepEqual(raw, {
    session_id: sessionId,
    event_id: eventId,
    event: {kind: "pad_press", gesture_id: gestureId, slot: 7, velocity: 100},
  });
  for (const forbidden of ["tick", "runtime_frame", "input_sequence"]) {
    assert.equal(JSON.stringify(raw).includes(forbidden), false);
  }
  const resample = operations.find(({operation}) =>
    operation === "performance.resample.commit").payload;
  assert.deepEqual(resample, {
    command_id: resample.command_id,
    expected_revision: 1,
    performance_id: performanceId,
    source_start_frame: 0,
    source_end_frame: 48_000,
    target_slot: {bank: 1, pad: 2},
  });
});

test("applyFxGesture wires session-free FX gestures without recording identity", async () => {
  const operations = [];
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope);
      if (envelope.operation === "performance.fx.gesture") {
        return success(envelope, {applied: true, project_revision: null});
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  assert.deepEqual(
    await session.applyFxGesture({kind: "fx_engage", fx: "filter", value: 500}),
    {applied: true},
  );
  assert.deepEqual(
    await session.applyFxGesture({kind: "fx_move", fx: "filter", value: 630}),
    {applied: true},
  );
  assert.deepEqual(await session.applyFxGesture({kind: "hold_on"}), {applied: true});
  assert.deepEqual(await session.applyFxGesture({kind: "hold_off"}), {applied: true});
  assert.deepEqual(
    await session.applyFxGesture({kind: "fx_release", fx: "filter"}),
    {applied: true},
  );

  const wired = operations.map(({operation, payload}) => ({operation, payload}));
  assert.deepEqual(wired, [
    {operation: "performance.fx.gesture",
     payload: {event: {kind: "fx_engage", fx: "filter", value: 500}}},
    {operation: "performance.fx.gesture",
     payload: {event: {kind: "fx_move", fx: "filter", value: 630}}},
    {operation: "performance.fx.gesture", payload: {event: {kind: "hold_on"}}},
    {operation: "performance.fx.gesture", payload: {event: {kind: "hold_off"}}},
    {operation: "performance.fx.gesture",
     payload: {event: {kind: "fx_release", fx: "filter"}}},
  ]);
  for (const forbidden of ["gesture_id", "session_id", "event_id", "tick"]) {
    assert.equal(JSON.stringify(wired).includes(forbidden), false);
  }

  await assert.rejects(
    session.applyFxGesture({kind: "fx_engage", fx: "filter", value: 1001}),
    TypeError,
  );
  await assert.rejects(
    session.applyFxGesture({kind: "fx_engage", gestureId: "x", fx: "filter", value: 500}),
    TypeError,
  );
  await assert.rejects(session.applyFxGesture({kind: "fx_release"}), TypeError);
  await assert.rejects(session.applyFxGesture({kind: "pad_press"}), TypeError);
  assert.equal(operations.length, 5);
});

test("audio clock sampling refuses before activation and outside running", async () => {
  let heartbeat = 0;
  const {context, session} = fixture({
    audioCallbackHeartbeat: () => heartbeat,
  });
  const refusal = (error) => error?.code === "HOST_STATE_INVALID";
  assert.throws(() => session.sampleAudioClock(), refusal);
  await session.start();
  assert.throws(() => session.sampleAudioClock(), refusal);

  const first = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  assert.throws(() => session.sampleAudioClock(), refusal);
  heartbeat = 1;
  assert.equal(await first, true);

  context.currentTime = 2.5;
  assert.deepEqual(session.sampleAudioClock(), {
    contextTimeSeconds: 2.5,
    callbackHeartbeat: 1,
    engineEpochHeartbeat: 1,
  });

  await session.suspendAudio();
  assert.throws(() => session.sampleAudioClock(), refusal);
});

test("audio clock epoch re-anchors on every activation", async () => {
  let heartbeat = 0;
  const {context, session} = fixture({
    audioCallbackHeartbeat: () => heartbeat,
  });
  await session.start();

  const first = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  heartbeat = 4;
  assert.equal(await first, true);
  assert.equal(session.sampleAudioClock().engineEpochHeartbeat, 4);

  heartbeat = 9;
  context.currentTime = 7.75;
  assert.deepEqual(session.sampleAudioClock(), {
    contextTimeSeconds: 7.75,
    callbackHeartbeat: 9,
    engineEpochHeartbeat: 4,
  });

  assert.equal(await session.suspendAudio(), true);
  const second = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  heartbeat = 12;
  assert.equal(await second, true);
  const resampled = session.sampleAudioClock();
  assert.equal(resampled.engineEpochHeartbeat, 12);
  assert.equal(resampled.callbackHeartbeat, 12);
});

for (const resumed of [false, true]) for (const nativeEpoch of [false, true]) {
  test(`audio clock excludes asynchronous delays from its ${resumed ? "resumed" : "initial"} ${nativeEpoch ? "Native" : "legacy"} epoch`, {timeout: 5_000}, async () => {
    let heartbeat = 0;
    let epoch = 0;
    let active = false;
    let activations = 0;
    const target = resumed ? 2 : 1;
    let releaseReply, replyStarted, releaseRefresh, refreshStarted;
    const reply = new Promise(resolve => {releaseReply = resolve;});
    const originalApplied = new Promise(resolve => {replyStarted = resolve;});
    const refresh = new Promise(resolve => {releaseRefresh = resolve;});
    const started = new Promise(resolve => {refreshStarted = resolve;});
    let handle = 1;
    const {context, session} = fixture({patternTransport: true,
      registerAudioNode: () => ++handle,
      audioCallbackHeartbeat: () => active ? heartbeat : ++heartbeat,
      ...(nativeEpoch ? {audioEngineEpochHeartbeat: () => epoch} : {}),
      startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
      send: async envelope => {
        if (envelope.operation === "audio.activate") {
          activations++;
          active = true;
          epoch = heartbeat = activations * 100;
          if (nativeEpoch && activations === target) {
            replyStarted();
            await reply; // Native already rendered; Browser has no reply yet.
          }
        }
        if (envelope.operation === "pattern.transport.count-in.capabilities" &&
            !envelope.payload.negotiate && activations === target) {
          refreshStarted();
          await refresh;
        }
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await session.start();
    if (resumed) {
      assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
      assert.equal(await session.suspendAudio(), true);
      active = false;
    }
    const activation = session.activateAudio(createUserGestureToken({isTrusted: true}));
    if (nativeEpoch) {
      await originalApplied;
      heartbeat += 6;
      releaseReply();
    }
    await Promise.race([started, activation.then(value => {
      throw new Error(`activation settled before refresh: ${value} ${JSON.stringify(session.diagnostics())}`);
    })]);
    assert.equal(session.diagnostics().state, "audio-suspended");
    heartbeat += 10;
    context.currentTime = 3;
    releaseRefresh();
    assert.equal(await activation, true);
    assert.deepEqual(session.sampleAudioClock(), {contextTimeSeconds: 3,
      callbackHeartbeat: target * 100 + (nativeEpoch ? 16 : 10), engineEpochHeartbeat: target * 100});
    await session.close();
  });
}

test("activation waits for a resumed AudioWorklet callback within its original budget", async () => {
  let heartbeat = 7;
  const activations = [];
  const {session} = fixture({
    audioCallbackHeartbeat: () => heartbeat,
    send: async (envelope, options) => {
      if (envelope.operation === "audio.activate") {
        activations.push(options.deadlineMs);
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  const first = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  assert.deepEqual(activations, []);
  heartbeat = 8;
  assert.equal(await first, true);
  assert.equal(activations.length, 1);
  assert.ok(activations[0] > 0 && activations[0] <= 1_000);

  assert.equal(await session.suspendAudio(), true);
  const second = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  assert.equal(activations.length, 1);
  heartbeat = 9;
  assert.equal(await second, true);
  assert.equal(activations.length, 2);
  assert.ok(activations[1] > 0 && activations[1] <= 1_000);

  assert.equal(await session.suspendAudio(), true);
  heartbeat = 0xffff_ffff;
  const wrapped = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  assert.equal(activations.length, 2);
  heartbeat = 0;
  assert.equal(await wrapped, true);
  assert.equal(activations.length, 3);
});

test("a slow output-device start does not consume the Control activation budget", async () => {
  let monotonicTime = 0;
  let resumed = false;
  const activations = [];
  const {context, session} = fixture({
    now: () => monotonicTime,
    // The first callback arrives 900 ms after the resume edge.
    audioCallbackHeartbeat: () => {
      if (!resumed) return 0;
      monotonicTime += 300;
      return monotonicTime >= 900 ? 1 : 0;
    },
    send: async (envelope, options) => {
      if (envelope.operation === "audio.activate") {
        activations.push(options.deadlineMs);
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  const resume = context.resume;
  context.resume = async function () {
    resumed = true;
    return resume.call(this);
  };
  await session.start();
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(activations, [1_000]);
});

test("an output device that does not start within its bound refuses activation without sealing the Runtime", async () => {
  let monotonicTime = 0;
  let deviceStarts = false;
  let beats = 0;
  const operations = [];
  const {context, session} = fixture({
    now: () => monotonicTime,
    audioCallbackHeartbeat: () => {
      monotonicTime += 1_000;
      return deviceStarts ? ++beats : beats;
    },
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  operations.length = 0;
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), false);
  assert.equal(session.diagnostics().state, "audio-suspended");
  assert.equal(session.diagnostics().error_code, null);
  assert.equal(session.diagnostics().activation_refusal, "audio_output_start_timeout");
  assert.equal(operations.includes("audio.activate"), false);
  assert.equal(context.state, "suspended");

  // The next gesture retries normally once the device starts.
  deviceStarts = true;
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.equal(session.diagnostics().state, "running");
  assert.equal(session.diagnostics().activation_refusal, null);
});

test("a resume that never settles is refused within the device bound and withdrawn", async () => {
  let monotonicTime = 0;
  let resumeSettles = false;
  const operations = [];
  const {context, session} = fixture({
    // Time passes only while the attempt waits on its pending resume().
    now: () => (resumeSettles ? monotonicTime : (monotonicTime += 250)),
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  const resume = context.resume;
  let suspendsAfterResume = 0;
  let resumeRequested = false;
  context.resume = function () {
    resumeRequested = true;
    return resumeSettles ? resume.call(this) : new Promise(() => {});
  };
  const suspend = context.suspend;
  context.suspend = function () {
    if (resumeRequested) suspendsAfterResume += 1;
    return suspend.call(this);
  };
  await session.start();
  operations.length = 0;
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), false);
  assert.equal(session.diagnostics().state, "audio-suspended");
  assert.equal(session.diagnostics().error_code, null);
  assert.equal(session.diagnostics().activation_refusal, "audio_output_start_timeout");
  assert.equal(operations.includes("audio.activate"), false);
  assert.equal(suspendsAfterResume, 1);

  resumeSettles = true;
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.equal(session.diagnostics().state, "running");
});

test("withdrawing a pending resume leaves a later context suspension observable", async () => {
  let monotonicTime = 0;
  let resumeSettles = false;
  const {context, session} = fixture({
    now: () => (resumeSettles ? monotonicTime : (monotonicTime += 250)),
  });
  const resume = context.resume;
  context.resume = function () {
    return resumeSettles ? resume.call(this) : new Promise(() => {});
  };
  await session.start();
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), false);
  resumeSettles = true;
  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.equal(session.diagnostics().state, "running");

  // The withdrawal changed no state, so it must not absorb this one.
  context.dispatchEvent(new Event("statechange"));
  context.state = "suspended";
  context.dispatchEvent(new Event("statechange"));
  await drainTasks();
  await drainTasks();
  assert.equal(session.diagnostics().state, "audio-suspended");
});

test("automatic recovery gives the output device its own bound before the Control budget", async () => {
  const browserWindow = new EventTarget();
  let monotonicTime = 0;
  let heartbeat = 0;
  let slowDevice = false;
  let slowSince = null;
  const activations = [];
  const runtime = fixture({
    browserWindow,
    now: () => monotonicTime,
    // During recovery the device calls back 1.5 s after the first read.
    audioCallbackHeartbeat: () => {
      if (!slowDevice) return ++heartbeat;
      monotonicTime += 500;
      slowSince ??= monotonicTime;
      return monotonicTime - slowSince >= 1_500 ? ++heartbeat : heartbeat;
    },
    send: async (envelope, options) => {
      if (envelope.operation === "audio.activate") {
        activations.push(options.deadlineMs);
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await runtime.session.start();
  assert.equal(await runtime.session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  slowDevice = true;
  activations.length = 0;
  browserWindow.dispatchEvent(browserEvent("pagehide", {persisted: true}));
  for (let attempt = 0; attempt < 50; ++attempt) {
    if (runtime.session.diagnostics().recovery_probe_ready === true) break;
    await drainTasks();
  }
  assert.equal(runtime.session.diagnostics().state, "recovering");
  assert.equal(runtime.session.diagnostics().recovery_probe_ready, true);
  assert.deepEqual(activations, [1_000]);
});

test("foreground loss while recovery waits for heartbeat invalidates the old gesture", async () => {
  const browserDocument = new EventTarget();
  browserDocument.visibilityState = "visible";
  let heartbeat = 0;
  const activations = [];
  const {context, session} = fixture({
    browserDocument,
    audioCallbackHeartbeat: () => heartbeat,
    send: async (envelope) => {
      if (envelope.operation === "audio.activate") {
        activations.push(envelope.request_id);
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  const initial = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  heartbeat = 1;
  assert.equal(await initial, true);
  assert.equal(session.diagnostics().state, "running");

  context.dispatchEvent(new Event("statechange"));
  context.state = "suspended";
  context.dispatchEvent(new Event("statechange"));
  await drainTasks();
  await drainTasks();
  assert.equal(session.diagnostics().state, "audio-suspended");
  activations.length = 0;

  const stale = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  browserDocument.visibilityState = "hidden";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  browserDocument.visibilityState = "visible";
  browserDocument.dispatchEvent(new Event("visibilitychange"));
  heartbeat = 2;

  assert.equal(await stale, false);
  assert.equal(session.diagnostics().state, "audio-suspended");
  assert.deepEqual(activations, []);

  const current = session.activateAudio(
    createUserGestureToken({isTrusted: true}));
  await drainTasks();
  heartbeat = 3;
  assert.equal(await current, true);
  assert.equal(session.diagnostics().state, "recovering");
  assert.equal(activations.length, 1);
});

test("initial AudioWorklet bootstrap does not consume the activation budget", async () => {
  let monotonicTime = 0;
  const activations = [];
  const {session} = fixture({
    now: () => monotonicTime,
    startAudioWorklet: async () => {
      monotonicTime += 5_000;
      return {ok: true};
    },
    send: async (envelope, options) => {
      if (envelope.operation === "audio.activate") {
        activations.push(options.deadlineMs);
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  assert.equal(await session.activateAudio(
    createUserGestureToken({isTrusted: true})), true);
  assert.deepEqual(activations, [1_000]);
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
        case "sequence.capture.disarm":
          return success(envelope, {disarmed: true});
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
    armedCaptureSlot: 17,
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
  assert.equal(await session.disarmSequenceCapture({sessionId, slot: 17}), true);
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
  assert.deepEqual(operations.find(
    ({operation}) => operation === "sequence.capture.disarm",
  ).payload, {session_id: sessionId, slot: {bank: 1, pad: 1}});
});

test("replays an ambiguous Sequence Stop before a queued boundary can fail the Host", async () => {
  const sessionId = "10000000-0000-4000-8000-000000000001";
  const patternId = "20000000-0000-4000-8000-000000000002";
  const nextPatternId = "20000000-0000-4000-8000-000000000003";
  const commandId = "30000000-0000-4000-8000-000000000004";
  const operations = [];
  let stopAttempts = 0;
  let emitBoundary;
  const activeStatus = {
    state: "active",
    session_id: sessionId,
    pattern_id: patternId,
    pending_pattern_id: null,
    expected_revision: 5,
    next_flush_seq: 0,
    pending_event_count: 1,
    effective_runtime_frame: null,
  };
  const stoppedStatus = {
    ...activeStatus,
    state: "inactive",
    session_id: null,
    pattern_id: null,
    pending_event_count: 0,
  };
  const stoppedMutation = {
    ...stoppedStatus,
    committed_revision: 6,
    replayed: true,
    project_revision: 6,
    runtime_frame: 96_000,
    pattern_publication: null,
  };
  const runtime = fixture({
    send: async (envelope) => {
      operations.push({
        operation: envelope.operation,
        payload: envelope.payload,
      });
      if (envelope.operation === "sequence.record.switch-request") {
        return success(envelope, {
          ...activeStatus,
          state: "switching",
          pending_pattern_id: nextPatternId,
          effective_runtime_frame: 96_000,
          committed_revision: null,
          replayed: false,
          project_revision: 5,
          pattern_publication: {
            generation: 2,
            activation_frame: 96_000,
          },
        });
      }
      if (envelope.operation === "sequence.record.stop") {
        stopAttempts += 1;
        if (stopAttempts === 1) {
          emitBoundary();
          return {
            protocol_version: 1,
            request_id: envelope.request_id,
            ok: false,
            error: {
              code: "INVALID_ARGUMENT",
              message: "Sequence Stop response was ambiguous at the boundary",
              details: {},
            },
          };
        }
        return success(envelope, stoppedMutation);
      }
      if (envelope.operation === "sequence.record.status") {
        return success(envelope, {
          ...stoppedStatus,
          project_revision: 6,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  emitBoundary = () => runtime.emitNotification({
    protocol_version: 1,
    event: "sequence.bar_boundary",
    payload: {
      session_id: sessionId,
      pattern_id: nextPatternId,
      runtime_frame: 96_000,
      generation: 2,
    },
  });

  await runtime.session.start();
  const boundaries = [];
  runtime.session.subscribeSequenceBarBoundary((value) => boundaries.push(value));
  await runtime.session.requestPatternSwitch({sessionId, nextPatternId});
  const stopped = await runtime.session.stopSequence({sessionId, commandId});
  assert.equal(stopped.replayed, true);
  await drainTasks();

  assert.equal((await runtime.session.querySequenceStatus()).state, "inactive");
  assert.equal(runtime.terminated(), 0);
  assert.equal(runtime.session.diagnostics().state, "audio-suspended");
  assert.deepEqual(boundaries, []);
  assert.deepEqual(
    operations.filter(({operation}) => operation.startsWith("sequence.record."))
      .map(({operation}) => operation),
    [
      "sequence.record.switch-request",
      "sequence.record.stop",
      "sequence.record.stop",
      "sequence.record.status",
    ],
  );
  assert.deepEqual(
    operations.filter(({operation}) => operation === "sequence.record.stop")
      .map(({payload}) => payload.command_id),
    [commandId, commandId],
  );
});

test("keeps a genuine invalid Stop observable and lets the queued boundary win", async () => {
  const sessionId = "10000000-0000-4000-8000-000000000001";
  const patternId = "20000000-0000-4000-8000-000000000002";
  const nextPatternId = "20000000-0000-4000-8000-000000000003";
  const commandId = "30000000-0000-4000-8000-000000000004";
  const operations = [];
  let stopAttempts = 0;
  let emitBoundary;
  const switchingStatus = {
    state: "switching",
    session_id: sessionId,
    pattern_id: patternId,
    pending_pattern_id: nextPatternId,
    expected_revision: 5,
    next_flush_seq: 0,
    pending_event_count: 1,
    effective_runtime_frame: 96_000,
  };
  const runtime = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      if (envelope.operation === "sequence.record.switch-request") {
        return success(envelope, {
          ...switchingStatus,
          committed_revision: null,
          replayed: false,
          project_revision: 5,
          pattern_publication: {
            generation: 2,
            activation_frame: 96_000,
          },
        });
      }
      if (envelope.operation === "sequence.record.stop") {
        stopAttempts += 1;
        if (stopAttempts === 1) emitBoundary();
        return {
          protocol_version: 1,
          request_id: envelope.request_id,
          ok: false,
          error: {
            code: "INVALID_ARGUMENT",
            message: "Sequence Stop was rejected before commit",
            details: {},
          },
        };
      }
      if (envelope.operation === "sequence.record.flush") {
        return success(envelope, {
          ...switchingStatus,
          state: "active",
          pattern_id: nextPatternId,
          pending_pattern_id: null,
          effective_runtime_frame: null,
          committed_revision: 6,
          replayed: false,
          project_revision: 6,
          runtime_frame: 96_000,
          pattern_publication: null,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  emitBoundary = () => runtime.emitNotification({
    protocol_version: 1,
    event: "sequence.bar_boundary",
    payload: {
      session_id: sessionId,
      pattern_id: nextPatternId,
      runtime_frame: 96_000,
      generation: 2,
    },
  });

  await runtime.session.start();
  const boundaries = [];
  runtime.session.subscribeSequenceBarBoundary((value) => boundaries.push(value));
  await runtime.session.requestPatternSwitch({sessionId, nextPatternId});
  await assert.rejects(
    runtime.session.stopSequence({sessionId, commandId}),
    (error) => error.code === "INVALID_ARGUMENT",
  );
  await drainTasks();

  assert.equal(runtime.terminated(), 0);
  assert.equal(runtime.session.diagnostics().state, "audio-suspended");
  assert.deepEqual(boundaries, [{
    sessionId,
    patternId: nextPatternId,
    runtimeFrame: 96_000,
    generation: 2,
  }]);
  assert.deepEqual(operations.filter((operation) =>
    operation.startsWith("sequence.record.")), [
    "sequence.record.switch-request",
    "sequence.record.stop",
    "sequence.record.stop",
    "sequence.record.flush",
  ]);
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

test("internal failure diagnostics retain a bounded Native reason (#2345)", async () => {
  const {emitFailure, session} = fixture();
  await session.start();
  emitFailure(Object.assign(new Error("private path"), {code: "INTERNAL_ERROR",
    details: {reason: "audio_activation_begin_refused", path: "/private"}}));
  await drainTasks();
  assert.deepEqual(session.diagnostics().error_details,
    {reason: "audio_activation_begin_refused"});
});

for (const code of ["HOST_TIMEOUT", "HOST_RESTART_REQUIRED"]) {
test(`timeout diagnostics retain bounded original request provenance (${code})`, async () => {
  const {emitFailure, session} = fixture();
  const states = [];
  session.subscribeHostState((state) => states.push(state));
  await session.start();
  const details = {operation: "project.inspect",
    request_id: "11111111-1111-4111-8111-111111111111",
    deadline_ms: 1000.5, deadline_at_ms: 1100.5, cancel_return: -1,
    terminal_state: "restart-required", mutation_outcome: "unknown"};
  emitFailure(Object.assign(new Error("private path"), {code,
    details: {...details, payload: {path: "/private"}, sidecar: [1, 2], path: "/private"}}));
  await drainTasks();
  assert.deepEqual(states.at(-1).errorDetails, details);
  assert.deepEqual(session.diagnostics().error_details, details);
  assert.equal(Object.isFrozen(session.diagnostics().error_details), true);
});
}

test("timeout diagnostics reject malformed provenance without coercion", async () => {
  const {emitFailure, session} = fixture();
  await session.start();
  emitFailure(Object.assign(new Error("private path"), {code: "HOST_TIMEOUT", details: {
    operation: "/private/project", request_id: "not-an-original-uuid",
    deadline_ms: 0x1_0000_0000, deadline_at_ms: Infinity, cancel_return: "1",
    payload: {private: true}, sidecar: [1],
  }}));
  await drainTasks();
  assert.deepEqual(session.diagnostics().error_details, {});
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
    playback: SESSION_PLAYBACK,
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

const ASSIGN_REQUEST = Object.freeze({
  commandId: "20000000-0000-4000-8000-000000000063",
  expectedRevision: 7,
  slot: 63,
  assetId: "11111111-1111-4111-8111-111111111111",
});

function assignmentResult(payload, overrides = {}) {
  return {slot: payload.slot, asset_id: payload.asset_id,
    committed_revision: 8, replayed: false, project_revision: 8,
    runtime_revision: 8, runtime_published: true, ...overrides};
}

test("retained Asset assignment sends explicit A01 and D16 with caller identity and original budget", async () => {
  const seen = [];
  const {session} = fixture({send: async (envelope, options) => {
    if (envelope.operation !== "pad.assign") {
      return success(envelope, defaultResult(envelope.operation));
    }
    seen.push({payload: structuredClone(envelope.payload), budget: options.deadlineMs});
    return success(envelope, assignmentResult(envelope.payload));
  }});
  await session.start();
  for (const slot of [0, 63]) {
    const commandId = slot === 0
      ? "20000000-0000-4000-8000-000000000001" : ASSIGN_REQUEST.commandId;
    const result = await session.assignPad({...ASSIGN_REQUEST, slot, commandId});
    assert.deepEqual(result, {slot, assetId: ASSIGN_REQUEST.assetId,
      committedRevision: 8, replayed: false, projectRevision: 8,
      runtimeRevision: 8, runtimePublished: true, snapshotError: null});
    assert.ok(Object.isFrozen(result));
  }
  assert.deepEqual(seen, [{bank: 0, pad: 0}, {bank: 3, pad: 15}].map((slot, index) => ({
    payload: {command_id: index === 0
      ? "20000000-0000-4000-8000-000000000001" : ASSIGN_REQUEST.commandId, expected_revision: 7,
      slot, asset_id: ASSIGN_REQUEST.assetId}, budget: 30_000,
  })));
  await session.close();
});

test("assignment validates non-null retained identity and explicit destination before sending", async () => {
  let assignments = 0;
  const {session} = fixture({send: async envelope => {
    if (envelope.operation === "pad.assign") assignments++;
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  for (const change of [{assetId: null}, {assetId: "foreign"}, {commandId: null},
    {commandId: "not-a-command"},
    {expectedRevision: -1}, {expectedRevision: Number.MAX_SAFE_INTEGER + 1},
    {extra: true}]) {
    await assert.rejects(session.assignPad({...ASSIGN_REQUEST, ...change}), TypeError);
  }
  for (const slot of [-1, 64, 1.5]) {
    await assert.rejects(session.assignPad({...ASSIGN_REQUEST, slot}), RangeError);
  }
  await assert.rejects(session.assignPad(null), TypeError);
  assert.equal(assignments, 0);
  await session.close();
});

test("queued assignment captures every identity field before a Project action finishes", async () => {
  const opened = Promise.withResolvers();
  const seen = [];
  const {session} = fixture({send: async envelope => {
    seen.push(envelope.operation);
    if (envelope.operation === "project.open") {
      await opened.promise;
      return success(envelope, {});
    }
    if (envelope.operation === "pad.assign") {
      assert.deepEqual(envelope.payload, {command_id: ASSIGN_REQUEST.commandId,
        expected_revision: 7, slot: {bank: 3, pad: 15}, asset_id: ASSIGN_REQUEST.assetId});
      return success(envelope, assignmentResult(envelope.payload));
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const opening = session.openProject(ASSIGN_REQUEST.assetId,
    "22222222-2222-4222-8222-222222222222");
  const request = {...ASSIGN_REQUEST};
  const assignment = session.assignPad(request);
  Object.assign(request, {commandId: "20000000-0000-4000-8000-000000000064",
    expectedRevision: 99, slot: 0, assetId: "22222222-2222-4222-8222-222222222222"});
  await drainTasks();
  assert.deepEqual(seen, ["project.open"]);
  opened.resolve();
  await opening;
  assert.equal((await assignment).slot, 63);
  assert.deepEqual(seen, ["project.open", "pad.assign"]);
  await session.close();
});

test("assignment also waits for an outstanding native query on the existing Host lane", async () => {
  const held = Promise.withResolvers();
  const seen = [];
  let inFlight = 0;
  let maximumInFlight = 0;
  const {session} = fixture({send: async (envelope, options) => {
    if (!["sample.inspect", "pad.assign"].includes(envelope.operation)) {
      return success(envelope, defaultResult(envelope.operation));
    }
    seen.push(envelope.operation);
    maximumInFlight = Math.max(maximumInFlight, ++inFlight);
    try {
      if (envelope.operation === "sample.inspect") {
        await held.promise;
        return success(envelope, {project_revision: 7, slot: {bank: 0, pad: 0},
          asset_id: ASSIGN_REQUEST.assetId, playback: WIRE_PLAYBACK,
          metadata: {sample_rate: 48_000, channels: 1, source_frames: 100},
          waveform_cache_identity: `${"a".repeat(64)}/1/max-abs-mirror/1`});
      }
      assert.equal(options.deadlineMs, 30_000);
      return success(envelope, assignmentResult(envelope.payload));
    } finally { inFlight--; }
  }});
  await session.start();
  const query = session.inspectSample(0);
  await drainTasks();
  const assignment = session.assignPad(ASSIGN_REQUEST);
  await drainTasks();
  assert.deepEqual(seen, ["sample.inspect"]);
  held.resolve();
  await Promise.all([query, assignment]);
  assert.deepEqual(seen, ["sample.inspect", "pad.assign"]);
  assert.equal(maximumInFlight, 1);
  await session.close();
});

test("assignment preserves a known commit whose Runtime publication failed", async () => {
  const error = {code: "WEB_RUNTIME_RESOURCE_LIMIT", message: "Runtime preparation refused",
    details: {resource: "resident_pcm_bytes", observed: 200, limit: 100}};
  const {session} = fixture({send: async envelope => success(envelope,
    envelope.operation === "pad.assign" ? assignmentResult(envelope.payload,
      {runtime_published: false, runtime_revision: 7, snapshot_error: error})
      : defaultResult(envelope.operation))});
  await session.start();
  assert.deepEqual(await session.assignPad(ASSIGN_REQUEST), {slot: 63,
    assetId: ASSIGN_REQUEST.assetId, committedRevision: 8, replayed: false,
    projectRevision: 8, runtimeRevision: 7, runtimePublished: false, snapshotError: error});
  await session.close();
});

test("assignment rejects publication failure without a valid typed error", async () => {
  const invalid = [
    {runtime_published: false, runtime_revision: 7},
    {runtime_published: false, runtime_revision: 7, snapshot_error: {
      code: "NOT_A_TYPED_ERROR", message: "failed", details: {},
    }},
  ];
  const {session} = fixture({send: async envelope => success(envelope,
    envelope.operation === "pad.assign"
      ? assignmentResult(envelope.payload, invalid.shift()) : defaultResult(envelope.operation))});
  await session.start();
  while (invalid.length) {
    await assert.rejects(session.assignPad(ASSIGN_REQUEST), {code: "HOST_PROTOCOL_MISMATCH"});
  }
  await session.close();
});

test("assignment rejects mismatched destination, Asset and publication authority", async () => {
  const invalid = [{slot: {bank: 0, pad: 0}}, {asset_id: null},
    {asset_id: "22222222-2222-4222-8222-222222222222"}, {replayed: 1},
    {committed_revision: 7},
    {committed_revision: 9, project_revision: 9, runtime_revision: 9},
    {project_revision: 7}, {runtime_revision: null}, {runtime_revision: 7},
    {runtime_revision: 9}, {extra: true}, {runtime_published: "true"},
    {snapshot_error: {code: "COOK_FAILED", message: "failed", details: {}}}];
  const {session} = fixture({send: async envelope => success(envelope,
    envelope.operation === "pad.assign"
      ? assignmentResult(envelope.payload, invalid.shift()) : defaultResult(envelope.operation))});
  await session.start();
  while (invalid.length) {
    await assert.rejects(session.assignPad(ASSIGN_REQUEST), {code: "HOST_PROTOCOL_MISMATCH"});
  }
  await session.close();
});

test("a lost assignment receipt sends once; only an explicit caller replay repeats the same identity", async () => {
  const sent = [];
  const {session} = fixture({send: async envelope => {
    if (envelope.operation === "pad.assign") {
      sent.push(structuredClone(envelope.payload));
      if (sent.length === 1) throw Object.assign(new Error("lost receipt"), {code: "HOST_TIMEOUT"});
      return success(envelope, assignmentResult(envelope.payload,
        {replayed: true, project_revision: 9, runtime_revision: 9}));
    }
    return success(envelope, envelope.operation === "history.inspect"
      ? HISTORY_STATUS : defaultResult(envelope.operation));
  }});
  await session.start();
  await assert.rejects(session.assignPad(ASSIGN_REQUEST), {code: "HOST_TIMEOUT"});
  await session.inspectAuthoringHistory();
  await drainTasks();
  assert.equal(sent.length, 1);
  const replay = await session.assignPad(ASSIGN_REQUEST);
  assert.equal(replay.replayed, true);
  assert.equal(replay.committedRevision, 8);
  assert.equal(replay.projectRevision, 9);
  assert.deepEqual(sent[1], sent[0]);
  await session.close();
});

test("assignment keeps the typed conflict and never replaces its command identity", async () => {
  const seen = [];
  const {session} = fixture({send: async envelope => {
    if (envelope.operation === "pad.assign") {
      seen.push(envelope.payload);
      return {protocol_version: 1, request_id: envelope.request_id, ok: false,
        error: {code: "REVISION_CONFLICT", message: "Project revision changed",
          details: {actual_revision: 9, expected_revision: 7}}};
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  await assert.rejects(session.assignPad(ASSIGN_REQUEST), error =>
    error.code === "REVISION_CONFLICT" && error.details.actual_revision === 9 &&
    error.details.expected_revision === 7);
  assert.equal(seen.length, 1);
  assert.equal(seen[0].command_id, ASSIGN_REQUEST.commandId);
  await session.close();
  await assert.rejects(session.assignPad(ASSIGN_REQUEST), {code: "HOST_STATE_INVALID"});
  assert.equal(seen.length, 1);
});

test("closing revokes an assignment still waiting on the native request lane", async () => {
  const held = Promise.withResolvers();
  let assignments = 0;
  const {session} = fixture({send: async envelope => {
    if (envelope.operation === "sample.inspect") {
      await held.promise;
      return success(envelope, {project_revision: 7, slot: {bank: 0, pad: 0},
        asset_id: null, playback: WIRE_PLAYBACK, metadata: null,
        waveform_cache_identity: null});
    }
    if (envelope.operation === "pad.assign") assignments++;
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const query = session.inspectSample(0);
  await drainTasks();
  const assignment = session.assignPad(ASSIGN_REQUEST);
  const refused = assert.rejects(assignment, {code: "HOST_STATE_INVALID"});
  const closing = session.close();
  await drainTasks();
  held.resolve();
  await Promise.all([query, refused, closing]);
  assert.equal(assignments, 0);
});

test("assignment retains the fatal owner's typed cause without sending", async () => {
  let assignments = 0;
  const runtime = fixture({send: async envelope => {
    if (envelope.operation === "pad.assign") assignments++;
    return success(envelope, defaultResult(envelope.operation));
  }});
  await runtime.session.start();
  runtime.emitFailure(Object.assign(new Error("native owner lost"), {code: "HOST_RESTART_REQUIRED"}));
  await assert.rejects(runtime.session.assignPad(ASSIGN_REQUEST), {code: "HOST_RESTART_REQUIRED"});
  assert.equal(assignments, 0);
  await runtime.session.close();
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

test("Sample playback crosses the session in both directions as the shared fixture", async () => {
  const sent = [];
  const {session} = fixture({
    send: async (envelope) => {
      if (envelope.operation === "sample.update_pad") {
        sent.push(envelope.payload.playback);
        return success(envelope, {
          committed_revision: 2,
          runtime_revision: 2,
          runtime_published: true,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  for (const wire of Object.values(PAD_PLAYBACK_FULL)) {
    await session.updatePad({
      slot: 0,
      expectedRevision: 1,
      playback: sessionPlaybackFrom(wire),
    });
  }
  // The wire carries exactly the fixture: every non-default key, no default.
  assert.deepEqual(sent, Object.values(PAD_PLAYBACK_FULL));
  await assert.rejects(
    session.updatePad({
      slot: 0,
      expectedRevision: 1,
      playback: {...sessionPlaybackFrom(PAD_PLAYBACK_FULL.forward), timeStretch: true},
    }),
    TypeError,
  );
});

// Review of #1799: an inspect result whose EQ band is null or carries an extra
// key is a protocol mismatch, not a silently trimmed band.
test("Sample inspect refuses a malformed EQ band", async () => {
  for (const eq of [
    {...PAD_PLAYBACK_FULL.tone.eq, low: null},
    {...PAD_PLAYBACK_FULL.tone.eq, mid: {...PAD_PLAYBACK_FULL.tone.eq.mid, kind: "shelf"}},
  ]) {
    const {session} = fixture({
      send: async (envelope) => {
        if (envelope.operation === "sample.inspect") {
          return success(envelope, {
            project_revision: 7,
            slot: {bank: 0, pad: 0},
            asset_id: "11111111-1111-4111-8111-111111111111",
            playback: {...PAD_PLAYBACK_FULL.tone, eq},
            metadata: {sample_rate: 48_000, channels: 1, source_frames: 8},
            waveform_cache_identity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
          });
        }
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await session.start();
    await assert.rejects(session.inspectSample(0), (error) =>
      error.code === "HOST_PROTOCOL_MISMATCH" &&
      error.message === "Sample playback result is invalid");
  }
});

// lmdj.project.v5 5.2.0: every tone field is range-checked before it reaches
// the wire, and the EQ object always names all three bands.
test("Sample playback refuses out-of-range tone parity fields", async () => {
  const {session} = fixture({
    send: async (envelope) => success(envelope, defaultResult(envelope.operation)),
  });
  await session.start();
  const tone = sessionPlaybackFrom(PAD_PLAYBACK_FULL.tone);
  for (const invalid of [
    {...tone, attackMs: 2_001},
    {...tone, releaseMs: -1},
    {...tone, tone: 101},
    {...tone, eq: {low: null, mid: null}},
    {...tone, eq: {...tone.eq, low: {...tone.eq.low, kind: "bell"}}},
    {...tone, eq: {...tone.eq, low: {...tone.eq.low, freqHz: 2_001}}},
    {...tone, eq: {...tone.eq, high: {...tone.eq.high, freqHz: 999}}},
    {...tone, eq: {...tone.eq, mid: {...tone.eq.mid, qMilli: 99}}},
    {...tone, eq: {...tone.eq, mid: {...tone.eq.mid, gainMillidb: 18_001}}},
  ]) {
    await assert.rejects(
      session.updatePad({slot: 0, expectedRevision: 1, playback: invalid}),
      TypeError,
    );
  }
});

test("Sample inspect normalizes every fixture playback to the full session shape", async () => {
  for (const wire of Object.values(PAD_PLAYBACK_FULL)) {
    const {session} = fixture({
      send: async (envelope) => {
        if (envelope.operation === "sample.inspect") {
          return success(envelope, {
            project_revision: 7,
            slot: {bank: 0, pad: 0},
            asset_id: "11111111-1111-4111-8111-111111111111",
            playback: wire,
            metadata: {sample_rate: 48_000, channels: 1, source_frames: 8},
            waveform_cache_identity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
          });
        }
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await session.start();
    const inspected = await session.inspectSample(0);
    assert.deepEqual(inspected.playback, sessionPlaybackFrom(wire));
  }
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
    sequenceSessionId: "10000000-0000-4000-8000-000000000001",
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
    "import_token", "sequence_session_id", "slot",
  ]);
  assert.equal(begin.import_token, importToken);
  assert.equal(begin.expected_revision, 3);
  assert.equal(begin.sequence_session_id, "10000000-0000-4000-8000-000000000001");
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

test("Sample import treats 1 MiB as the chunk limit instead of the total limit", async () => {
  const bytes = new Uint8Array(1_048_577);
  const file = {
    size: bytes.byteLength,
    slice(start, end) {
      return new Blob([bytes.subarray(start, end)]);
    },
  };
  const operations = [];
  const chunkSizes = [];
  const {session} = fixture({
    send: async (envelope, transportOptions) => {
      operations.push(envelope.operation);
      if (envelope.operation === "sample.import.begin") {
        return success(envelope, {
          token: envelope.payload.import_token,
          expected_bytes: bytes.byteLength,
        });
      }
      if (envelope.operation === "sample.import.chunk") {
        chunkSizes.push(transportOptions.sidecar.byteLength);
        return success(envelope, {
          received_bytes:
            envelope.payload.offset + transportOptions.sidecar.byteLength,
          final: envelope.payload.final,
        });
      }
      if (envelope.operation === "sample.import.commit") {
        return success(envelope, {
          committed_revision: 1,
          runtime_revision: 1,
          runtime_published: true,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();

  await session.importAssignSample(file, {slot: 0, expectedRevision: 0});

  assert.deepEqual(operations, [
    "sample.import.begin",
    "sample.import.chunk",
    "sample.import.chunk",
    "sample.import.commit",
  ]);
  assert.deepEqual(chunkSizes, [1_048_576, 1]);
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
  assert.equal(duringCalls[0].signal.aborted, true);
  assert.equal(duringCalls[1].signal, duringCalls[0].signal);
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

for (const quotaFailure of [
  {
    code: "BANK_QUOTA_EXHAUSTED",
    details: {
      bank: 0,
      requested_bytes: 67_108_868,
      requested_frames: 16_777_217,
      remaining_bytes: 67_108_864,
      remaining_frames: 16_777_216,
      quota_bytes: 67_108_864,
      consumed: [],
    },
  },
  {
    code: "PROJECT_QUOTA_EXHAUSTED",
    details: {
      requested_bytes: 4,
      requested_frames: 1,
      project_used_bytes: 134_217_728,
      project_remaining_bytes: 0,
      project_quota_bytes: 134_217_728,
      banks: [
        {bank: 0, prepared_bytes: 67_108_864},
        {bank: 1, prepared_bytes: 67_108_864},
      ],
    },
  },
]) {
  test(`Sample import preserves ${quotaFailure.code} details`, async () => {
    const file = new Blob([Uint8Array.of(1, 2, 3, 4)]);
    const operations = [];
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
          return success(envelope, {received_bytes: file.size, final: true});
        }
        if (envelope.operation === "sample.import.commit") {
          return {
            protocol_version: 1,
            request_id: envelope.request_id,
            ok: false,
            error: {
              code: quotaFailure.code,
              message: "Sample quota exhausted",
              details: quotaFailure.details,
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
      (error) => error.code === quotaFailure.code &&
        assert.deepEqual(error.details, quotaFailure.details) === undefined,
    );
    assert.deepEqual(operations, [
      "sample.import.begin",
      "sample.import.chunk",
      "sample.import.commit",
      "sample.import.abort",
    ]);
  });
}

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
    // This envelope-shape oracle models no elapsed time. The input budget
    // tests below cover timing, including that queue time is not charged.
    now: () => 0,
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

test("reactivation waits until both Host and AudioContext suspension commit", async () => {
  let releaseHostSuspend;
  let hostSuspendStartedResolve;
  const hostSuspendStarted = new Promise(resolve => { hostSuspendStartedResolve = resolve; });
  let releaseContextSuspend;
  const contextMaySuspend = new Promise(resolve => { releaseContextSuspend = resolve; });
  let contextSuspendStartedResolve;
  const contextSuspendStarted = new Promise(resolve => { contextSuspendStartedResolve = resolve; });
  const {context, session} = fixture({send: async envelope => {
    if (envelope.operation === "audio.suspend") {
      hostSuspendStartedResolve();
      return new Promise(resolve => {
        releaseHostSuspend = () => resolve(success(envelope, {}));
      });
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  // Gate only the explicit suspension; the first activation parks its new
  // context with the fixture's own suspend.
  context.suspend = async () => {
    contextSuspendStartedResolve();
    await contextMaySuspend;
    context.state = "suspended";
    context.dispatchEvent(new Event("statechange"));
  };
  const suspending = session.suspendAudio();
  try {
    await hostSuspendStarted;
    assert.equal(session.diagnostics().state, "running");
    assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), false);
    releaseHostSuspend();
    await contextSuspendStarted;
    assert.equal(context.state, "running");
    assert.equal(session.diagnostics().state, "running");
    assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), false);
    releaseContextSuspend();
    assert.equal(await suspending, true);
    assert.equal(context.state, "suspended");
    assert.equal(session.diagnostics().state, "audio-suspended");
    assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
    assert.equal(context.state, "running");
    assert.equal(session.diagnostics().state, "running");
  } finally {
    releaseHostSuspend?.();
    releaseContextSuspend();
    await suspending;
    await session.close();
  }
});

test("blur during explicit suspension cannot start a competing recovery", async () => {
  let contextSuspendStartedResolve;
  const contextSuspendStarted = new Promise(resolve => { contextSuspendStartedResolve = resolve; });
  let releaseContextSuspend;
  const contextMaySuspend = new Promise(resolve => { releaseContextSuspend = resolve; });
  const browserWindow = new EventTarget();
  const operations = [];
  const {context, session} = fixture({browserWindow, send: async envelope => {
    operations.push(envelope.operation);
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  operations.length = 0;
  context.suspend = async () => {
    contextSuspendStartedResolve();
    await contextMaySuspend;
    context.state = "suspended";
    context.dispatchEvent(new Event("statechange"));
  };
  const suspending = session.suspendAudio();
  try {
    await contextSuspendStarted;
    browserWindow.dispatchEvent(new Event("blur"));
    await drainTasks();
    releaseContextSuspend();
    assert.equal(await suspending, true);
    await drainTasks();
    assert.deepEqual(operations, ["sample.stop", "audio.suspend"]);
    assert.equal(session.diagnostics().state, "audio-suspended");
    assert.equal(context.state, "suspended");
    assert.equal(session.diagnostics().recovery_probe_ready, false);
  } finally {
    releaseContextSuspend();
    await suspending;
    await session.close();
  }
});

test("close during Host suspension keeps the late result from changing closed state", async () => {
  let releaseHostSuspend;
  let hostSuspendStartedResolve;
  const hostSuspendStarted = new Promise(resolve => { hostSuspendStartedResolve = resolve; });
  const {context, session} = fixture({send: async envelope => {
    if (envelope.operation === "audio.suspend") {
      hostSuspendStartedResolve();
      return new Promise(resolve => {
        releaseHostSuspend = () => resolve(success(envelope, {}));
      });
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  // Count only suspensions after activation; the first activation parks its
  // new context once before the Worklet loads.
  let contextSuspensions = 0;
  context.suspend = async () => { contextSuspensions++; };
  const suspending = session.suspendAudio();
  await hostSuspendStarted;
  const closing = session.close();
  releaseHostSuspend();
  assert.equal(await suspending, false);
  assert.equal(await closing, true);
  assert.equal(contextSuspensions, 0);
  assert.equal(session.diagnostics().state, "closed");
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

test("retains an outcome delivered after the Trigger response resolves but before its continuation", async () => {
  let emitNotification;
  const runtime = fixture({
    send: (envelope) => {
      if (envelope.operation === "trigger") {
        return resolveThen(success(envelope, {sequence: 9}), () => {
          emitNotification({
            protocol_version: 1,
            event: "runtime.trigger_outcomes",
            payload: {
              events: [{
                sequence: 9,
                outcome: "voice_started",
                runtime_frame: 42,
              }],
            },
          });
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  emitNotification = runtime.emitNotification;
  await runtime.session.start();
  await runtime.session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  const outcomes = [];
  runtime.session.subscribeRuntimeOutcome((value) => outcomes.push(value));

  assert.deepEqual(await runtime.session.trigger(3, 99, "keyboard"), {
    sequence: 9,
    slot: 3,
    velocity: 99,
    source: "keyboard",
  });
  assert.deepEqual(outcomes, [
    {sequence: 9, outcome: "voice_started", runtimeFrame: 42},
  ]);
  assert.equal(runtime.session.diagnostics().state, "running");
  assert.equal(runtime.session.diagnostics().trigger_admitted_count, 1);
  assert.equal(runtime.session.diagnostics().trigger_outcome_count, 1);
});

test("fails closed when an early outcome does not match the Trigger response", async () => {
  let emitNotification;
  const runtime = fixture({
    send: (envelope) => {
      if (envelope.operation === "trigger") {
        return resolveThen(success(envelope, {sequence: 9}), () => {
          emitNotification({
            protocol_version: 1,
            event: "runtime.trigger_outcomes",
            payload: {
              events: [{
                sequence: 8,
                outcome: "voice_started",
                runtime_frame: 42,
              }],
            },
          });
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  emitNotification = runtime.emitNotification;
  await runtime.session.start();
  await runtime.session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  const outcomes = [];
  runtime.session.subscribeRuntimeOutcome((value) => outcomes.push(value));

  assert.equal(await runtime.session.trigger(3, 99, "keyboard"), false);
  assert.deepEqual(outcomes, []);
  await drainTasks();
  assert.equal(runtime.session.diagnostics().state, "failed");
  assert.equal(
    runtime.session.diagnostics().error_code,
    "HOST_PROTOCOL_MISMATCH",
  );
  assert.equal(runtime.session.diagnostics().trigger_admitted_count, 0);
});

test("an early recovery-probe outcome completes the armed recovery epoch", async () => {
  const browserWindow = new EventTarget();
  let emitNotification;
  const runtime = fixture({
    browserWindow,
    send: (envelope) => {
      if (envelope.operation === "trigger") {
        return resolveThen(success(envelope, {sequence: 7}), () => {
          emitNotification({
            protocol_version: 1,
            event: "runtime.trigger_outcomes",
            payload: {
              events: [{
                sequence: 7,
                outcome: "voice_started",
                runtime_frame: 42,
              }],
            },
          });
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  emitNotification = runtime.emitNotification;
  await runtime.session.start();
  await runtime.session.activateAudio(
    createUserGestureToken({isTrusted: true}),
  );
  browserWindow.dispatchEvent(browserEvent("pagehide", {persisted: true}));
  for (let attempt = 0; attempt < 100; ++attempt) {
    if (runtime.session.diagnostics().recovery_probe_ready === true) break;
    await Promise.resolve();
  }

  assert.deepEqual(await runtime.session.trigger(0, 100, "keyboard"), {
    sequence: 7,
    slot: 0,
    velocity: 100,
    source: "keyboard",
  });
  assert.equal(runtime.session.diagnostics().state, "running");
  assert.equal(runtime.session.diagnostics().recovery_probe_ready, false);
  assert.equal(runtime.session.diagnostics().trigger_outcome_count, 1);
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
    // Readers accept exactly the current envelope and the single Project
    // Contract level the writer produces; see
    // docs/prd/decisions/2026-09-15-project-bundle-current-level-only.md.
    // A fixture on an older level is refused before the typed surface is
    // exercised at all, which tests the refusal rather than this journey.
    contract_version: "2.0.0",
    entries: [{
      bytes: payload.byteLength,
      offset: 0,
      path: "manifest.json",
      sha256: await hash(payload),
    }],
    project_contract: "lmdj.project.v5",
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

const SET_ID = "11111111-1111-4111-8111-111111111111";
const MANIFEST_SHA = "a1".repeat(32);
const BLOB_SHA = "b2".repeat(32);
const DEMO_SHA = "c3".repeat(32);

// A Host stand-in for the Core loop `soundset.catalog.list` really drives:
// the index names a Set by its manifest hash, the manifest names its blobs,
// and each read that cannot be served is recorded as one address.
function soundsetHost({blobBytes = 8, indexReadable = true, cached = []} = {}) {
  const staged = new Map();
  const partial = new Map();
  const pending = [];
  const supplied = [];
  const indexCalls = [];
  let indexStaged = false;
  let indexPending = false;
  const want = (kind, sha256) => {
    if (staged.has(`${kind}/${sha256}`)) return true;
    if (!pending.some((entry) => entry.object_kind === kind &&
      entry.sha256 === sha256)) {
      pending.push({object_kind: kind, sha256});
    }
    return false;
  };
  return {
    supplied,
    indexCalls,
    send(envelope) {
      const {operation, payload} = envelope;
      if (operation === "soundset.catalog.index") {
        indexCalls.push(payload.available);
        indexStaged = payload.available === true;
        if (indexStaged) indexPending = false;
        return {staged: indexStaged};
      }
      if (operation === "soundset.catalog.pending") {
        const objects = [...pending];
        pending.length = 0;
        const index = indexPending;
        indexPending = false;
        return {index, objects};
      }
      if (operation === "soundset.catalog.supply") {
        supplied.push({...payload});
        const key = `${payload.object_kind}/${payload.sha256}`;
        const held = payload.offset === 0 ? 0 : partial.get(key);
        if (held !== payload.offset) {
          throw new Error(`out of order supply at ${payload.offset}`);
        }
        const next = payload.offset + (envelope.sidecarBytes ?? 0);
        partial.set(key, next);
        if (next < payload.byte_length) return {staged: false};
        partial.delete(key);
        staged.set(key, payload.byte_length);
        return {staged: true};
      }
      if (operation !== "soundset.catalog.list") {
        return null;
      }
      if (!indexStaged || !indexReadable) {
        indexPending = true;
        // S11-D7: the Set Store is the Workspace's, not the Catalog's. What it
        // already published lists whether or not the Catalog answers.
        return {catalog_available: false, sets: [...cached], refused: [],
          project_revision: 0};
      }
      const complete = want("manifest", MANIFEST_SHA) &&
        want("blob", BLOB_SHA) && want("blob", DEMO_SHA);
      return {
        catalog_available: true,
        project_revision: 0,
        refused: [],
        sets: complete
          ? [...cached, {
              set_id: SET_ID,
              version: "1.0.0",
              manifest_sha256: MANIFEST_SHA,
              name: "Fixture Attribution Kit",
              publisher: "Bea Waveform",
              description: null,
              bpm: 128,
              key: "Fm",
              total_bytes: 34_788,
              has_demo: true,
              license: {
                spdx_id: "CC-BY-4.0",
                rights_holder: "Bea Waveform",
                copyright: "(c) 2026 Bea Waveform",
                attribution: "Fixture Attribution Kit by Bea Waveform",
              },
              occupied_slots: [{slot: 0, role: "kick", name: "Kick"}],
            }]
          : [...cached],
      };
    },
    blobBytes,
  };
}

function soundsetFixture({host, catalog}) {
  return fixture({
    soundsetCatalog: catalog,
    send(envelope, transportOptions) {
      const handled = host.send({
        ...envelope,
        sidecarBytes: transportOptions?.sidecar?.byteLength ?? 0,
      });
      return success(
        envelope,
        handled ?? defaultResult(envelope.operation),
      );
    },
  });
}

test("acquires Sound Sets by resolving exactly the addresses Core asks for", async () => {
  const host = soundsetHost({blobBytes: 1_200_000});
  const asked = [];
  const catalog = {
    readIndex: async () => new Uint8Array(16),
    readObject: async (request) => {
      assert.deepEqual(Object.keys(request).sort(), ["object_kind", "sha256"]);
      asked.push(`${request.object_kind}/${request.sha256}`);
      return new Uint8Array(
        request.object_kind === "manifest" ? 32 : host.blobBytes);
    },
  };
  const {session} = soundsetFixture({host, catalog});
  assert.equal(await session.start(), true);

  const listed = await session.listSoundSets();

  assert.deepEqual(asked, [
    `manifest/${MANIFEST_SHA}`,
    `blob/${BLOB_SHA}`,
    `blob/${DEMO_SHA}`,
  ]);
  assert.equal(listed.catalogAvailable, true);
  assert.equal(listed.sets.length, 1);
  // The CC-BY-4.0 attribution string reaches the surface verbatim.
  assert.equal(
    listed.sets.at(-1).license.attribution,
    "Fixture Attribution Kit by Bea Waveform",
  );
  assert.equal(listed.sets.at(-1).hasDemo, true);
  assert.deepEqual(host.indexCalls, [true]);

  // A blob larger than one bridge message crosses in order, in as many
  // messages as it needs, and is only readable once whole.
  const blob = host.supplied.filter((entry) => entry.sha256 === BLOB_SHA);
  assert.equal(blob.length, 3);
  assert.deepEqual(blob.map((entry) => entry.offset), [0, 524_288, 1_048_576]);
  assert.ok(blob.every((entry) => entry.byte_length === 1_200_000));
  assert.ok(host.supplied.every((entry) =>
    Object.keys(entry).sort().join() ===
      "byte_length,object_kind,offset,sha256"));
});

// One Set the Workspace Set Store already published, so "still lists" has
// something to be true of.
const CACHED_SET = Object.freeze({
  set_id: "44444444-4444-4444-8444-444444444444",
  version: "2.0.0",
  manifest_sha256: "d4".repeat(32),
  name: "Already In This Workspace",
  publisher: "LMDJ Fixtures",
  description: null,
  bpm: null,
  key: null,
  total_bytes: 2_048,
  has_demo: false,
  license: {
    spdx_id: "CC0-1.0",
    rights_holder: "LMDJ Fixtures",
    copyright: "(c) 2026 LMDJ Fixtures",
    attribution: "",
  },
  occupied_slots: [{slot: 0, role: "kick", name: "Kick"}],
});

test("an unreachable Catalog still lists what the Set Store holds", async () => {
  const host = soundsetHost({cached: [CACHED_SET]});
  const catalog = {
    readIndex: async () => {
      const error = new Error("offline");
      error.code = "IO_ERROR";
      error.details = {reason: "catalog_unavailable"};
      throw error;
    },
    readObject: async () => {
      throw new Error("no object read is expected while the Catalog is down");
    },
  };
  const {session} = soundsetFixture({host, catalog});
  assert.equal(await session.start(), true);

  const listed = await session.listSoundSets();

  assert.equal(listed.catalogAvailable, false);
  // The cached Set is still listed, with everything inspect and install need.
  assert.deepEqual(listed.sets.map((set) => set.name), [
    "Already In This Workspace",
  ]);
  assert.equal(listed.sets[0].manifestSha256, CACHED_SET.manifest_sha256);
  // The Host withdrew its index rather than leaving a stale one readable, and
  // the acquisition loop stopped instead of spinning.
  assert.deepEqual(host.indexCalls, [false]);
  assert.deepEqual(host.supplied, []);
});

test("an address that cannot be resolved leaves the loop and the other Sets", async () => {
  const host = soundsetHost({cached: [CACHED_SET]});
  let reads = 0;
  const catalog = {
    readIndex: async () => new Uint8Array(16),
    readObject: async () => {
      reads += 1;
      const error = new Error("gone");
      error.code = "IO_ERROR";
      error.details = {reason: "catalog_unavailable"};
      throw error;
    },
  };
  const {session} = soundsetFixture({host, catalog});
  assert.equal(await session.start(), true);

  const listed = await session.listSoundSets();

  assert.equal(listed.catalogAvailable, true);
  // The Set whose objects could not be resolved is absent; the one the Set
  // Store already holds is untouched by that failure.
  assert.deepEqual(listed.sets.map((set) => set.name), [
    "Already In This Workspace",
  ]);
  // One pass that resolves nothing ends the loop: no round bound is reached
  // and no address is re-asked forever.
  assert.equal(reads, 1);
});

test("refuses a Sound Set request the Locked Facade Surface cannot express", async () => {
  const host = soundsetHost();
  const {session} = soundsetFixture({
    host,
    catalog: {readIndex: async () => new Uint8Array(0), readObject: async () => {
      throw new Error("unused");
    }},
  });
  assert.equal(await session.start(), true);

  const identity = {
    setId: SET_ID,
    version: "1.0.0",
    manifestSha256: MANIFEST_SHA,
  };
  await assert.rejects(
    session.inspectSoundSet({...identity, workspacePath: "/tmp/workspace"}),
    (error) => error.code === "INVALID_ARGUMENT",
  );
  await assert.rejects(
    session.inspectSoundSet({...identity, manifestSha256: MANIFEST_SHA.toUpperCase()}),
    (error) => error.code === "INVALID_ARGUMENT",
  );
  await assert.rejects(
    session.previewSoundSetMap({...identity, bankId: 4}),
    (error) => error.code === "INVALID_ARGUMENT",
  );
  await assert.rejects(
    session.installSoundSet({
      ...identity,
      bankId: 0,
      commandId: "00000000-0000-4000-8000-000000000900",
      expectedRevision: 1,
      occupiedPadPolicy: "overwrite",
    }),
    (error) => error.code === "INVALID_ARGUMENT",
  );
});

test("forwards the occupied Pad policy only when the caller chose one", async () => {
  const host = soundsetHost();
  const installs = [];
  const {session} = fixture({
    soundsetCatalog: null,
    send(envelope) {
      if (envelope.operation === "soundset.install") {
        installs.push(envelope.payload);
        return success(envelope, {
          bank_id: envelope.payload.bank_id,
          set_id: SET_ID,
          version: "1.0.0",
          manifest_sha256: MANIFEST_SHA,
          installed: [{slot_index: 0, pad: 0}],
          collisions: [],
          kept: [],
          replayed: false,
          project_revision: 7,
        });
      }
      return success(envelope, host.send(envelope) ??
        defaultResult(envelope.operation));
    },
  });
  assert.equal(await session.start(), true);

  const identity = {
    setId: SET_ID,
    version: "1.0.0",
    manifestSha256: MANIFEST_SHA,
    bankId: 2,
    expectedRevision: 6,
  };
  const bare = await session.installSoundSet({
    ...identity,
    commandId: "00000000-0000-4000-8000-000000000901",
  });
  assert.equal(bare.committedRevision, 7);
  assert.deepEqual(bare.installed, [{slotIndex: 0, pad: 0}]);
  await session.installSoundSet({
    ...identity,
    commandId: "00000000-0000-4000-8000-000000000902",
    occupiedPadPolicy: "replace",
  });

  assert.ok(!Object.hasOwn(installs[0], "occupied_pad_policy"));
  assert.equal(installs[1].occupied_pad_policy, "replace");
  assert.deepEqual(Object.keys(installs[1]).sort(), [
    "bank_id",
    "command_id",
    "expected_revision",
    "manifest_sha256",
    "occupied_pad_policy",
    "set_id",
    "version",
  ]);
});

// #799. A slot audition names the Artifact it played; only a set-level demo
// may answer without one. Accepting `null` would hand the caller a result the
// documented type says cannot occur -- the same class
// `normalizeSoundSetSlot` already refuses for an occupied slot.
// `played` has no default on purpose: `undefined` here means the Host sent no
// outcome at all, and a default would silently repair the case under test.
function auditionFixture(artifact, slotIndex, played) {
  return fixture({
    soundsetCatalog: null,
    send(envelope) {
      if (envelope.operation !== "soundset.audition") {
        return success(envelope, defaultResult(envelope.operation));
      }
      const result = {
        set_id: SET_ID,
        version: "1.0.0",
        manifest_sha256: MANIFEST_SHA,
        slot_index: slotIndex,
        artifact,
        audio: {
          sample_rate: 44_100,
          channels: 1,
          source_frames: 2_646,
          prepared_bytes: 11_520,
          prepared_frames: 2_880,
        },
      };
      // `undefined` stands for a Host that sent no `played` at all, which is
      // the drift the normaliser refuses; every other value is passed through
      // so the type check itself can be exercised.
      if (played !== undefined) {
        result.played = played;
      }
      return success(envelope, result);
    },
  });
}

test("a slot audition that names no Artifact is refused", async () => {
  const auditionWith = (artifact, slotIndex) =>
    auditionFixture(artifact, slotIndex, true);
  const identity = {
    setId: SET_ID,
    version: "1.0.0",
    manifestSha256: MANIFEST_SHA,
  };
  const artifact = {
    sha256: BLOB_SHA,
    media_type: "audio/wav",
    byte_length: 64,
  };

  await assert.rejects(
    auditionWith(null, 0).session.auditionSoundSet({...identity, slotIndex: 0}),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
  // The demo case is the one that may answer without an Artifact, so the same
  // absence must be accepted there -- a rule that refused both would be
  // refusing the shape the contract defines.
  const demo = await auditionWith(null, null).session.auditionSoundSet(identity);
  assert.equal(demo.artifact, null);
  assert.equal(demo.slotIndex, null);
  // And the ordinary slot answer still passes, so the rule is not refusing
  // everything.
  const played = await auditionWith(artifact, 0)
    .session.auditionSoundSet({...identity, slotIndex: 0});
  assert.equal(played.artifact.sha256, BLOB_SHA);
  assert.equal(played.audio.preparedFrames, 2_880);
});

// #799, review finding. The geometry is answered from the bytes the Facade
// resolved, so it is identical whether or not this Host's engine played them.
// `played` is the only part of the reply that separates the two, which is why
// it crosses this boundary and why an absent one is drift rather than `false`.
test("an audition carries whether a voice actually started", async () => {
  const identity = {
    setId: SET_ID,
    version: "1.0.0",
    manifestSha256: MANIFEST_SHA,
  };
  const artifact = {sha256: BLOB_SHA, media_type: "audio/wav", byte_length: 64};

  const audible = await auditionFixture(artifact, 0, true)
    .session.auditionSoundSet({...identity, slotIndex: 0});
  assert.equal(audible.played, true);

  const silent = await auditionFixture(artifact, 0, false)
    .session.auditionSoundSet({...identity, slotIndex: 0});
  assert.equal(silent.played, false);
  // The two differ in exactly one field: everything a caller could otherwise
  // read is the same, which is the defect stated as an assertion.
  assert.deepEqual(
    {...audible, played: null}, {...silent, played: null});

  // A Host that sends no outcome, and one that sends a non-boolean, are both
  // drift rather than a silence to be assumed.
  await assert.rejects(
    auditionFixture(artifact, 0, undefined)
      .session.auditionSoundSet({...identity, slotIndex: 0}),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
  await assert.rejects(
    auditionFixture(artifact, 0, "true")
      .session.auditionSoundSet({...identity, slotIndex: 0}),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
});

test("a Set slot that disagrees with itself about being empty is refused", async () => {
  const slots = (override) => Array.from({length: 16}, (_, slot) =>
    slot === 0 ? override : {slot, occupied: false});
  const inspectWith = (slot0) => fixture({
    soundsetCatalog: null,
    send(envelope) {
      if (envelope.operation !== "soundset.inspect") {
        return success(envelope, defaultResult(envelope.operation));
      }
      return success(envelope, {
        set_id: SET_ID,
        version: "1.0.0",
        manifest_sha256: MANIFEST_SHA,
        name: "Inconsistent Kit",
        publisher: "LMDJ Fixtures",
        description: null,
        bpm: null,
        key: null,
        total_bytes: 1_024,
        has_demo: false,
        license: {
          spdx_id: "CC0-1.0",
          rights_holder: "LMDJ Fixtures",
          copyright: "(c) 2026 LMDJ Fixtures",
          attribution: "",
        },
        occupied_slots: [],
        slots: slots(slot0),
        demo: null,
        project_revision: 0,
      });
    },
  });
  const identity = {
    setId: SET_ID,
    version: "1.0.0",
    manifestSha256: MANIFEST_SHA,
  };
  const artifact = {
    sha256: BLOB_SHA,
    media_type: "audio/wav",
    byte_length: 64,
  };

  // S11-D12 turns on emptiness, so the two ways Core states it must agree
  // before a surface reads either. A slot that claims to be occupied and names
  // no Artifact is a protocol fault, not an empty slot the Creator may quietly
  // present as one.
  const {session: missing} = inspectWith({slot: 0, occupied: true});
  assert.equal(await missing.start(), true);
  await assert.rejects(
    missing.inspectSoundSet(identity),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );

  // And the reverse: an Artifact under a slot that calls itself empty must
  // never be silently dropped into "nothing here".
  const {session: stray} = inspectWith({slot: 0, occupied: false, artifact});
  assert.equal(await stray.start(), true);
  await assert.rejects(
    stray.inspectSoundSet(identity),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
});

test("Provider commands retain explicit grant-select-run order on the existing lane", async () => {
  const operations = [];
  let release;
  const blocked = new Promise((resolve) => {release = resolve;});
  const {session} = fixture({send: async (envelope) => {
    const {operation, payload} = envelope;
    if (operation.startsWith("provider.") || operation === "attempt.inspect") {
      operations.push({operation, payload: structuredClone(payload)});
      if (operation === "provider.permissions.configure") await blocked;
      return success(envelope, operation === "provider.list"
        ? {providers: [], granted_permissions: [], project_revision: null} : {operation});
    }
    return success(envelope, defaultResult(operation));
  }});
  await session.start();
  await session.listProviders();
  const grant = session.configureProviderPermissions(["sample.slice.execute"]);
  const selection = session.selectProvider("sample.slice.v1", "local.sample.slice");
  const request = {
    attempt_id: "owned", capability: "sample.slice.v1", inputs: [], parameters: {},
    data_classification: "public", platform: "test", region: "local", required_permissions: ["sample.slice.execute"],
  };
  const execution = session.runProvider(request);
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(operations.map((entry) => entry.operation), ["provider.list", "provider.permissions.configure"]);
  release(); await Promise.all([grant, selection, execution]);
  await session.inspectAttempt("owned");
  assert.deepEqual(operations.map((entry) => entry.operation), [
    "provider.list", "provider.permissions.configure", "provider.select", "provider.run", "attempt.inspect"]);
  assert.deepEqual(operations[3].payload, request);
  assert.deepEqual(operations[1].payload, {granted_permissions: ["sample.slice.execute"]});
  await session.close();
});

test("Provider run does not grant permissions and preserves the owner's safe failure category", async () => {
  const operations = [];
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation.startsWith("provider.")) operations.push(envelope.operation);
    if (envelope.operation === "provider.run") {
      return {protocol_version: 1, request_id: envelope.request_id, ok: false,
        error: {code: "IO_ERROR", message: "input rejected", details: {reason: "input_artifact_mismatch", attempt_id: "owned"}}};
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const request = {attempt_id: "owned", capability: "sample.slice.v1", inputs: [], parameters: {},
    data_classification: "public", platform: "test", region: "local", required_permissions: ["sample.slice.execute"]};
  await assert.rejects(session.runProvider(request), (error) => {
    assert.equal(error.code, "IO_ERROR");
    assert.deepEqual(error.details, {reason: "input_artifact_mismatch", attempt_id: "owned"});
    return true;
  });
  assert.deepEqual(operations, ["provider.run"]);
  await session.close();
});

const CANDIDATE_PROJECT_ID = "00000000-0000-4000-8000-000000000111";
const CANDIDATE_REQUEST = {project_id: CANDIDATE_PROJECT_ID, expected_revision: 3,
  job_id: "slice-job", set_id: "set", candidate_id: "recipe"};
const CANDIDATE_AUDIO = {job_id: "slice-job", set_id: "set", candidate_id: "recipe",
  artifact: {sha256: "a".repeat(64), media_type: "audio/wav", byte_length: 52},
  sample_rate: 48000, channels: 1, source_frames: 4, project_revision: 3, played: true};
const CANDIDATE_ADOPT = {project_id: CANDIDATE_PROJECT_ID, expected_revision: 3,
  command_id: CANDIDATE_PROJECT_ID, job_id: "slice-job", set_id: "set",
  selections: [{candidate_id: "recipe", bank: 0, pad: 2}]};
const CANDIDATE_ADOPTED = {set_id: "set", project_revision: 4,
  adopted: [{candidate_id: "recipe", bank: 0, pad: 2, asset_id: CANDIDATE_PROJECT_ID}]};

test("Candidate audition and stop serialize and preserve raw result fields", async () => {
  let release;
  const blocked = new Promise((resolve) => {release = resolve;});
  const seen = [];
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation.startsWith("candidate.")) seen.push(envelope.operation);
    if (envelope.operation === "candidate.audition") {await blocked; return success(envelope, CANDIDATE_AUDIO);}
    if (envelope.operation === "candidate.audition.stop") return success(envelope, {accepted: true});
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const preview = session.auditionCandidate(CANDIDATE_REQUEST);
  const stopped = session.stopCandidateAudition();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(seen, ["candidate.audition"]);
  release(); assert.deepEqual(await preview, CANDIDATE_AUDIO);
  assert.deepEqual(await stopped, {accepted: true});
  assert.deepEqual(seen, ["candidate.audition", "candidate.audition.stop"]);
  await session.close();
  await assert.rejects(session.auditionCandidate(CANDIDATE_REQUEST), {code: "HOST_STATE_INVALID"});
  await assert.rejects(session.stopCandidateAudition(), {code: "HOST_STATE_INVALID"});
  await assert.rejects(session.inspectCandidateJob("slice-job"), {code: "HOST_STATE_INVALID"});
  assert.equal(seen.length, 2);
});

test("Candidate audition refuses mismatched identity, revision and malformed playback replies", async () => {
  for (const change of [{job_id: "other"}, {set_id: "other"}, {candidate_id: "other"},
    {project_revision: 4}, {played: undefined}]) {
    const {session} = fixture({send: async (envelope) => success(envelope,
      envelope.operation === "candidate.audition" ? {...CANDIDATE_AUDIO, ...change} : defaultResult(envelope.operation))});
    await session.start();
    await assert.rejects(session.auditionCandidate(CANDIDATE_REQUEST), {code: "HOST_PROTOCOL_MISMATCH"});
    await session.close();
  }
});

test("Candidate adoption validates one revision and every explicit target without retrying unknown commits", async () => {
  for (const change of [null, {set_id: "other"}, {project_revision: 3},
    {adopted: [{...CANDIDATE_ADOPTED.adopted[0], pad: 1}]}]) {
    const seen = [];
    const {session} = fixture({send: async (envelope) => {
      if (envelope.operation === "candidate.adopt") {
        seen.push(structuredClone(envelope.payload));
        return success(envelope, {...CANDIDATE_ADOPTED, ...change});
      }
      return success(envelope, defaultResult(envelope.operation));
    }});
    await session.start();
    if (change === null) assert.deepEqual(await session.adoptCandidates(CANDIDATE_ADOPT), CANDIDATE_ADOPTED);
    else await assert.rejects(session.adoptCandidates(CANDIDATE_ADOPT), {code: "HOST_PROTOCOL_MISMATCH"});
    assert.deepEqual(seen, [CANDIDATE_ADOPT]);
    await session.close();
  }
  let calls = 0;
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation === "candidate.adopt") {calls++; throw Object.assign(new Error("lost"), {code: "HOST_TIMEOUT"});}
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  await assert.rejects(session.adoptCandidates(CANDIDATE_ADOPT), {code: "HOST_TIMEOUT"});
  assert.equal(calls, 1);
  await session.inspectProject();
  assert.equal(calls, 1);
  await session.close();
});

test("published inspection namespace shares the owned recovery request lane", async () => {
  const browserWindow = {};
  const truth = JSON.parse(readFileSync(new URL(
    "../../../tests/fixtures/contracts/project-v5-playback-parity-valid.json",
    import.meta.url,
  ), "utf8"));
  const project = {project_revision: truth.revision, project: truth};
  let releaseSample;
  const sampleGate = new Promise(resolve => { releaseSample = resolve; });
  const calls = [];
  let inFlight = 0;
  let maximumInFlight = 0;
  const {session} = fixture({browserWindow, publishRuntime: true,
    send: async (envelope, options) => {
      if (!["sample.inspect", "sequence.recovery.list", "project.inspect"].includes(envelope.operation)) {
        return success(envelope, defaultResult(envelope.operation));
      }
      calls.push({operation: envelope.operation, payload: envelope.payload,
        deadlineMs: options.deadlineMs});
      maximumInFlight = Math.max(maximumInFlight, ++inFlight);
      try {
        if (envelope.operation === "sample.inspect") {
          await sampleGate;
          return success(envelope, {
            project_revision: 7, slot: envelope.payload.slot,
            asset_id: "11111111-1111-4111-8111-111111111111",
            playback: {...WIRE_PLAYBACK, pan: -100, tone: -100},
            metadata: {sample_rate: 48_000, channels: 2, source_frames: 100},
            waveform_cache_identity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
          });
        }
        return success(envelope, envelope.operation === "project.inspect"
          ? project : {candidates: [], project_revision: null});
      } finally {
        inFlight -= 1;
      }
    },
  });
  await session.start();
  const {inspection} = browserWindow.lmdjWebRuntimeHost;

  const sampled = inspection.inspectSample(33);
  await drainTasks();
  const recovery = session.listSequenceRecovery(truth.project_id);
  const inspectedProject = inspection.inspectProject();
  await drainTasks();
  assert.deepEqual(calls, [{operation: "sample.inspect",
    payload: {slot: {bank: 2, pad: 1}}, deadlineMs: 30_000}]);
  assert.equal(maximumInFlight, 1);

  releaseSample();
  const [sample, candidates, observedProject] = await Promise.all([
    sampled, recovery, inspectedProject,
  ]);
  assert.deepEqual(sample, {projectRevision: 7, slot: 33,
    assetId: "11111111-1111-4111-8111-111111111111",
    playback: {...SESSION_PLAYBACK, pan: -100, tone: -100},
    metadata: {sampleRate: 48_000, channels: 2, sourceFrames: 100},
    waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/1`});
  assert.deepEqual(candidates, []);
  assert.deepEqual(observedProject, project);
  assert.deepEqual(calls, [
    {operation: "sample.inspect", payload: {slot: {bank: 2, pad: 1}}, deadlineMs: 30_000},
    {operation: "sequence.recovery.list", payload: {project_id: truth.project_id}, deadlineMs: 1_000},
    {operation: "project.inspect", payload: {}, deadlineMs: 30_000},
  ]);
  assert.equal(maximumInFlight, 1);
  await session.close();
});

test("closed inspection closures cannot send through a replacement owner", async () => {
  const browserWindow = {};
  const oldInspections = [];
  const oldOwner = fixture({browserWindow, publishRuntime: true,
    send: async envelope => {
      if (["sample.inspect", "project.inspect"].includes(envelope.operation)) oldInspections.push(envelope);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await oldOwner.session.start();
  const oldNamespace = browserWindow.lmdjWebRuntimeHost.inspection;
  assert.equal(await oldOwner.session.close(), true);

  const currentInspections = [];
  const currentProject = {project_revision: 8, project: {revision: 8}};
  const currentOwner = fixture({browserWindow, publishRuntime: true,
    send: async envelope => {
      if (envelope.operation === "project.inspect") currentInspections.push(envelope);
      return success(envelope, envelope.operation === "project.inspect"
        ? currentProject : defaultResult(envelope.operation));
    },
  });
  await currentOwner.session.start();
  const currentNamespace = browserWindow.lmdjWebRuntimeHost.inspection;
  assert.notEqual(currentNamespace, oldNamespace);
  await assert.rejects(oldNamespace.inspectProject(), {code: "HOST_STATE_INVALID"});
  await assert.rejects(oldNamespace.inspectSample(0), {code: "HOST_STATE_INVALID"});
  await drainTasks();
  assert.deepEqual(oldInspections, []);
  assert.deepEqual(currentInspections, []);
  assert.deepEqual(await currentNamespace.inspectProject(), currentProject);
  assert.equal(currentInspections.length, 1);
  await currentOwner.session.close();
});

test("closing inspection owner refuses reads while native close is pending", async () => {
  const browserWindow = {};
  let releaseClose;
  const closeGate = new Promise(resolve => { releaseClose = resolve; });
  const inspections = [];
  const owner = fixture({browserWindow, publishRuntime: true,
    send: async envelope => {
      if (["project.inspect", "sample.inspect"].includes(envelope.operation)) inspections.push(envelope);
      if (envelope.operation === "host.close") await closeGate;
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await owner.session.start();
  const {inspection} = browserWindow.lmdjWebRuntimeHost;
  const closing = owner.session.close();
  await drainTasks();
  await assert.rejects(inspection.inspectProject(), {code: "HOST_STATE_INVALID"});
  await assert.rejects(inspection.inspectSample(0), {code: "HOST_STATE_INVALID"});
  await drainTasks();
  assert.deepEqual(inspections, []);
  releaseClose();
  assert.equal(await closing, true);
});

for (const code of ["HOST_TIMEOUT", "HOST_PROTOCOL_MISMATCH"]) {
  test(`published inspections preserve native ${code} after fatal cleanup`, async () => {
    const browserWindow = {};
    const terminalError = Object.assign(new Error("retained native failure"), {code});
    const owner = fixture({browserWindow, publishRuntime: true,
      send: async envelope => {
        if (["project.inspect", "sample.inspect"].includes(envelope.operation)) throw terminalError;
        return success(envelope, defaultResult(envelope.operation));
      },
    });
    await owner.session.start();
    const {inspection} = browserWindow.lmdjWebRuntimeHost;
    owner.emitTransportFailure(terminalError);
    await drainTasks();
    await assert.rejects(inspection.inspectProject(), error => error === terminalError);
    await assert.rejects(inspection.inspectSample(0), error => error === terminalError);
    await owner.session.close();
  });
}

test("Candidate group extends the retained packaged Host beside providers", async () => {
  const browserWindow = {};
  const {session} = fixture({browserWindow, publishRuntime: true});
  await session.start();
  const runtime = browserWindow.lmdjWebRuntimeHost;
  assert.equal(typeof runtime.registerAudioContext, "function");
  assert.equal(runtime.providers.listProviders, session.listProviders);
  assert.ok(Object.isFrozen(runtime.candidates));
  for (const name of ["runCandidateJob", "inspectCandidateJob", "cancelCandidateJob", "discardCandidateSet",
    "auditionCandidate", "stopCandidateAudition", "adoptCandidates"]) {
    assert.equal(runtime.candidates[name], session[name]);
  }
  await session.close();
  assert.equal(browserWindow.lmdjWebRuntimeHost, runtime);
});

test("Candidate Job lifecycle returns validated Facade fields and rejects wrong Job bindings", async () => {
  const source = {project_id: CANDIDATE_PROJECT_ID,
    asset_id: CANDIDATE_PROJECT_ID, project_revision: 3, artifact: CANDIDATE_AUDIO.artifact, frame_rate: 48000, frame_count: 4};
  const intent = {attempt_id: "attempt", source, parameters_sha256: "b".repeat(64), data_classification: "public",
    platform: "test", region: "local", required_permissions: []};
  let wrongJob = false;
  let status = "interrupted";
  const calls = [];
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation.startsWith("candidate.")) {
      calls.push(structuredClone(envelope.payload));
      if (envelope.operation === "candidate.job.cancel") status = "cancelled";
      return success(envelope, {job_id: wrongJob ? "other" : "slice-job", active_set_id: null,
        sets: [], history: [{intent, set_id: "set", status}], project_revision: null});
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const request = {job_id: "slice-job", attempt_id: "attempt", project_id: CANDIDATE_PROJECT_ID,
    asset_id: CANDIDATE_PROJECT_ID, expected_revision: 3, parameters: {}, data_classification: "public",
    platform: "test", region: "local", required_permissions: []};
  const result = await session.runCandidateJob(request);
  assert.equal(result.project_revision, null);
  assert.deepEqual(result.history[0].intent.source, source);
  assert.equal((await session.inspectCandidateJob("slice-job")).history[0].status, "interrupted");
  assert.equal((await session.cancelCandidateJob("slice-job", "attempt")).history[0].status, "cancelled");
  assert.deepEqual(calls, [request, {job_id: "slice-job"}, {job_id: "slice-job", attempt_id: "attempt"}]);
  wrongJob = true;
  await assert.rejects(session.inspectCandidateJob("slice-job"), {code: "HOST_PROTOCOL_MISMATCH"});
  await assert.rejects(session.runCandidateJob({...request, project_path: "/projects/example.lmdj"}), {code: "HOST_PROTOCOL_MISMATCH"});
  assert.equal(calls.length, 4);
  await session.close();
});

test("Provider permission readback rejects absent or duplicate grants and preserves existing grants", async () => {
  for (const granted_permissions of [undefined, ["sample.slice.execute", "sample.slice.execute"], ["other.execute"]]) {
    const {session} = fixture({send: async (envelope) => success(envelope,
      envelope.operation === "provider.list" ? {providers: [], granted_permissions, project_revision: null} : defaultResult(envelope.operation))});
    await session.start();
    if (granted_permissions?.length === 1) assert.deepEqual((await session.listProviders()).granted_permissions, ["other.execute"]);
    else await assert.rejects(session.listProviders(), {code: "HOST_PROTOCOL_MISMATCH"});
    await session.close();
  }
});

const TRANSPORT_SESSION_ID = "00000000-0000-4000-8000-0000000000aa";
const TRANSPORT_PROJECT_ID = "00000000-0000-4000-8000-0000000000bb";
const TRANSPORT_PATTERN_ID = "00000000-0000-4000-8000-0000000000cc";
const TRANSPORT_COMMAND_ID = "00000000-0000-4000-8000-0000000000dd";

function transportStatus(overrides = {}) {
  return {
    engaged: true,
    playing: false,
    recording: false,
    phase: "awaiting_audio",
    runtime_generation: 1,
    transport_epoch: 1,
    origin_frame: 0,
    runtime_frame: 0,
    command_id: TRANSPORT_COMMAND_ID,
    publication_pending: false,
    error: null,
    current_pattern_id: TRANSPORT_PATTERN_ID,
    pending_switch: null,
    ...overrides,
  };
}

function countInWireTicket() {
  return {session_id: TRANSPORT_SESSION_ID, command_id: TRANSPORT_COMMAND_ID,
    runtime_generation: "18446744073709551615", frame_epoch: "18446744073709551615",
    schedule_serial: "1152921504606846975"};
}
function countInPublicTicket() {
  const ticket = countInWireTicket();
  return {sessionId: ticket.session_id, commandId: ticket.command_id,
    runtimeGeneration: ticket.runtime_generation, frameEpoch: ticket.frame_epoch,
    scheduleSerial: ticket.schedule_serial};
}
function countInWireStatus(overrides = {}) {
  const {session_id: _session, command_id: _command, ...identity} = countInWireTicket();
  return {ticket: countInWireTicket(),
    count_in: {...identity, phase: "submitted", bars: 2, bpm: null,
      bar_frames: null, count_in_frame: null, start_frame: null},
    start_receipt: null, cancel_receipt: null, opening_pending: false, opening_complete: false,
    error: null, ...overrides};
}
function countInRequest() {
  return {...countInPublicTicket(), projectId: TRANSPORT_PROJECT_ID,
    expectedEpoch: "1", bars: 2, expectedRevision: null};
}

test("frozen legacy decoder preserves the strict original Pattern transport schema", () => {
  const raw = transportStatus({playing: true, phase: "idle", origin_frame: 96_000,
    runtime_frame: 150_000});
  const decoded = decodeLegacyPatternTransportStatus(raw);
  assert.equal(decoded.originFrame, 96_000);
  assert.equal(decoded.runtimeFrame, 150_000);
  assert.equal(decoded.transportEpoch, 1);
  assert.throws(() => decodeLegacyPatternTransportStatus({...raw, count_in: null}),
    {code: "HOST_PROTOCOL_MISMATCH"});
  const {runtime_frame: _missing, ...missing} = raw;
  assert.throws(() => decodeLegacyPatternTransportStatus(missing), {code: "HOST_PROTOCOL_MISMATCH"});
});

test("count-in unknown capability on an old Host leaves ordinary Pattern transport usable", async () => {
  const sent = [];
  const {session} = fixture({patternTransport: true, send: async (envelope) => {
    sent.push(envelope.operation);
    if (envelope.operation === "pattern.transport.count-in.capabilities") return {
      protocol_version: 1, request_id: envelope.request_id, ok: false,
      error: {code: "HOST_PROTOCOL_MISMATCH", message: "host protocol request is invalid", details: {}},
    };
    if (envelope.operation === "pattern.transport.request") return success(envelope, {
      session_id: TRANSPORT_SESSION_ID, command_id: TRANSPORT_COMMAND_ID,
      submit: "accepted", status: transportStatus(),
    });
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  assert.deepEqual(await session.queryPatternCountInCapabilities(), {
    supported: false, negotiated: false, outputReady: false, runtimeGeneration: null,
    frameEpoch: null, nextSerial: null, inputCapacity: 0,
  });
  await assert.rejects(session.requestPatternCountIn(countInRequest()), {code: "UNSUPPORTED_AUDIO"});
  const ordinary = await session.requestPatternTransport({sessionId: TRANSPORT_SESSION_ID,
    projectId: TRANSPORT_PROJECT_ID, commandId: TRANSPORT_COMMAND_ID,
    expectedEpoch: 1, intent: "record", expectedRevision: null});
  assert.equal(ordinary.submit, "accepted");
  assert.deepEqual(sent.filter((name) => name.startsWith("pattern.transport.")), [
    "pattern.transport.count-in.capabilities", "pattern.transport.request",
  ]);
  await session.close();
});

test("count-in capability probing never downgrades a malformed Host envelope to unsupported", async () => {
  const {session} = fixture({patternTransport: true, send: async (envelope) =>
    envelope.operation === "pattern.transport.count-in.capabilities"
      ? {protocol_version: 1, request_id: envelope.request_id, ok: false,
          error: {code: "HOST_PROTOCOL_MISMATCH", message: "invalid", details: {}}, extra: true}
      : success(envelope, defaultResult(envelope.operation))});
  await session.start();
  await assert.rejects(session.queryPatternCountInCapabilities(), {code: "HOST_PROTOCOL_MISMATCH"});
  await session.close();
});

function metronomeCapabilityFixture(overrides = {}) {
  let handle = 10;
  return fixture({patternTransport: true,
    registerAudioNode: () => ++handle,
    startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
    ...overrides});
}

test("count-in metronome publishes boolean choices synchronously without a Host RPC", async () => {
  const choices = [], sent = [];
  const {session} = metronomeCapabilityFixture({
    setCountInMetronome(enabled) { choices.push(enabled); return true; },
    send: async envelope => {
      sent.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  const before = [...sent];
  assert.equal(session.setCountInMetronome(true), undefined);
  assert.deepEqual(choices, [true], "the atomic publication happened before returning");
  session.setCountInMetronome(false);
  assert.deepEqual(choices, [true, false]);
  assert.deepEqual(sent, before, "neither preference enters the Host dispatcher");
  for (const value of [0, 1, "true", null, undefined])
    assert.throws(() => session.setCountInMetronome(value), TypeError);
  assert.deepEqual(choices, [true, false], "invalid values never reach Native");
  await session.close();
  assert.throws(() => session.setCountInMetronome(true), {code: "HOST_STATE_INVALID"});
  assert.deepEqual(choices, [true, false]);
});

test("count-in metronome refuses inactive, legacy and unavailable Native owners explicitly", async () => {
  let calls = 0;
  const {session} = metronomeCapabilityFixture({
    setCountInMetronome() { calls++; return false; },
  });
  assert.throws(() => session.setCountInMetronome(true), {code: "HOST_STATE_INVALID"});
  await session.start();
  assert.throws(() => session.setCountInMetronome(true), {code: "HOST_STATE_INVALID"});
  assert.equal(calls, 0);
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  assert.throws(() => session.setCountInMetronome(true), {code: "HOST_STATE_INVALID"});
  assert.equal(calls, 1);
  assert.equal(session.diagnostics().state, "running", "a refusal does not seal ordinary audio");
  await session.close();

  const legacy = metronomeCapabilityFixture();
  await legacy.session.start();
  await legacy.session.activateAudio(createUserGestureToken({isTrusted: true}));
  assert.throws(() => legacy.session.setCountInMetronome(true), {code: "UNSUPPORTED_AUDIO"});
  assert.equal(legacy.session.diagnostics().state, "running");
  await legacy.session.close();
});

test("count-in metronome does not wait behind an outstanding Runtime query", async () => {
  let release, entered = false;
  const held = new Promise(resolve => { release = resolve; });
  const choices = [];
  const {session} = metronomeCapabilityFixture({
    setCountInMetronome(enabled) { choices.push(enabled); return true; },
    send: async envelope => {
      if (envelope.operation === "project.inspect") {
        entered = true;
        await held;
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const pending = session.inspectProject();
  try {
    const deadline = performance.now() + 1_000;
    while (!entered && performance.now() < deadline)
      await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(entered, true, "the original query reached the held transport");
    session.setCountInMetronome(true);
    assert.deepEqual(choices, [true], "Native has the choice while the original query is still held");
  } finally {
    release();
    await pending;
    await session.close();
  }
});

test("count-in pending admission releases SDK tails through the full twelve-second control interval", async () => {
  let clock = 0;
  let handle = 10;
  const sent = [];
  const {session} = fixture({patternTransport: true, now: () => clock,
    registerAudioNode: () => ++handle,
    startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
    send: async (envelope) => {
      sent.push(envelope);
      if (["pattern.transport.count-in.request", "pattern.transport.count-in.cancel"].includes(envelope.operation))
        return success(envelope, {submit: "accepted", ticket: countInWireTicket(), status: countInWireStatus()});
      if (envelope.operation === "pattern.transport.count-in.inspect")
        return success(envelope, countInWireStatus());
      if (envelope.operation === "pattern.transport.inspect") return success(envelope, transportStatus());
      return success(envelope, defaultResult(envelope.operation));
    }});
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  const admission = await session.requestPatternCountIn(countInRequest());
  assert.equal(admission.status.countIn.startFrame, null);
  assert.equal(admission.status.openingComplete, false);
  assert.equal(admission.ticket.runtimeGeneration, "18446744073709551615");
  for (clock = 0; clock <= 12_000; clock += 1_000) {
    const observed = await session.inspectPatternCountIn(admission.ticket);
    assert.equal(observed.countIn.startFrame, null);
    assert.equal(observed.observedAtMilliseconds, clock);
    assert.equal((await session.inspectPatternTransport(TRANSPORT_SESSION_ID)).phase, "awaiting_audio");
  }
  const cancel = await session.cancelPatternCountIn({ticket: admission.ticket,
    projectId: TRANSPORT_PROJECT_ID, commandId: "00000000-0000-4000-8000-0000000000de",
    expectedEpoch: "2", intent: "play_stop"});
  assert.equal(cancel.submit, "accepted");
  assert.equal(cancel.status.startReceipt, null);
  const request = sent.find((entry) => entry.operation === "pattern.transport.count-in.request");
  assert.equal(request.payload.runtime_generation, "18446744073709551615");
  assert.equal(request.payload.schedule_serial, "1152921504606846975");
  assert.equal(request.payload.expected_epoch, "1");
  assert.equal(sent.filter((entry) => entry.operation === "pattern.transport.count-in.inspect").length, 13);
  await session.close();
});

test("count-in Applied S remains distinct from pending Journal opening and later true cutoff F", async () => {
  let handle = 10;
  const {session_id: _session, command_id: _command, ...identity} = countInWireTicket();
  const start = {...identity, transport_epoch: "1", pattern_generation: "1",
    pattern_id: TRANSPORT_PATTERN_ID, result: "applied", effective_frame: 577_000,
    origin_frame: 577_000, playing: true};
  const view = {...identity, phase: "applied", bars: 2, bpm: 40, bar_frames: 288_000,
    count_in_frame: 1_000, start_frame: 577_000};
  let cutoff = null;
  const {session} = fixture({patternTransport: true, registerAudioNode: () => ++handle,
    startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
    send: async (envelope) => {
      if (envelope.operation === "pattern.transport.count-in.request") return success(envelope,
        {submit: "accepted", ticket: countInWireTicket(), status: countInWireStatus()});
      if (envelope.operation === "pattern.transport.count-in.inspect") return success(envelope,
        countInWireStatus({count_in: view, start_receipt: start, cancel_receipt: cutoff, opening_pending: true}));
      return success(envelope, defaultResult(envelope.operation));
    }});
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  const {ticket} = await session.requestPatternCountIn(countInRequest());
  const opened = await session.inspectPatternCountIn(ticket);
  assert.equal(opened.startReceipt.effectiveFrame, 577_000);
  assert.equal(opened.openingPending, true);
  assert.equal(opened.openingComplete, false);
  cutoff = {...start, transport_epoch: "2", effective_frame: 577_128, playing: false};
  const stopped = await session.inspectPatternCountIn(ticket);
  assert.equal(stopped.startReceipt.effectiveFrame, 577_000);
  assert.equal(stopped.cancelReceipt.effectiveFrame, 577_128);
  assert.equal(stopped.cancelReceipt.originFrame, 577_000);
  cutoff = {...cutoff, effective_frame: 577_000};
  await assert.rejects(session.inspectPatternCountIn(ticket), {code: "HOST_PROTOCOL_MISMATCH"});
  await session.close();
});

test("count-in winning cancellation refuses a fabricated future origin", async () => {
  let handle = 10;
  const {session_id: _session, command_id: _command, ...identity} = countInWireTicket();
  const {session} = fixture({patternTransport: true, registerAudioNode: () => ++handle,
    startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
    send: async (envelope) => envelope.operation === "pattern.transport.count-in.request"
      ? success(envelope, {submit: "accepted", ticket: countInWireTicket(), status: countInWireStatus({
          count_in: {...identity, phase: "cancelled", bars: 2, bpm: 40, bar_frames: 288_000,
            count_in_frame: 1_000, start_frame: 577_000},
          start_receipt: {...identity, transport_epoch: "1", pattern_generation: "1",
            pattern_id: TRANSPORT_PATTERN_ID, result: "cancelled", effective_frame: null,
            origin_frame: 577_000, playing: false},
        })}) : success(envelope, defaultResult(envelope.operation))});
  await session.start();
  assert.equal(await session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  await assert.rejects(session.requestPatternCountIn(countInRequest()), {code: "HOST_PROTOCOL_MISMATCH"});
  await session.close();
});

test("Pattern transport requires opt-in and negotiates the marker at Project open", async () => {
  const opens = [];
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "project.open") opens.push(envelope.payload);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.openProject(TRANSPORT_PROJECT_ID, TRANSPORT_PATTERN_ID);
  assert.deepEqual(opens, [{
    project_id: TRANSPORT_PROJECT_ID,
    pattern_id: TRANSPORT_PATTERN_ID,
    pattern_transport: true,
  }]);
  await session.close();

  const legacy = fixture({
    send: async (envelope) => {
      if (envelope.operation === "project.open") opens.push(envelope.payload);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await legacy.session.start();
  assert.throws(
    () => legacy.session.requestPatternTransport({
      sessionId: TRANSPORT_SESSION_ID,
      projectId: TRANSPORT_PROJECT_ID,
      commandId: TRANSPORT_COMMAND_ID,
      expectedEpoch: 1,
      intent: "record",
      expectedRevision: null,
    }),
    /requires session opt-in/,
  );
  assert.throws(
    () => legacy.session.inspectPatternTransport(TRANSPORT_SESSION_ID),
    /requires session opt-in/,
  );
  await legacy.session.openProject(TRANSPORT_PROJECT_ID, TRANSPORT_PATTERN_ID);
  assert.deepEqual(opens.at(-1), {
    project_id: TRANSPORT_PROJECT_ID,
    pattern_id: TRANSPORT_PATTERN_ID,
  });
  await legacy.session.close();
});

function createdProject(overrides = {}) {
  return {
    project_id: TRANSPORT_PROJECT_ID,
    project_revision: 0,
    initial_pattern_id: TRANSPORT_PATTERN_ID,
    runtime_ready: false,
    ...overrides,
  };
}

const CREATE_REQUEST = Object.freeze({
  projectId: TRANSPORT_PROJECT_ID,
  patternId: TRANSPORT_PATTERN_ID,
  bpm: 120,
  bars: 1,
});

test("Project creation sends the chosen identities with an empty initial Pattern", async () => {
  const creates = [];
  const {session} = fixture({
    send: async (envelope) => {
      if (envelope.operation === "project.create") {
        creates.push(envelope.payload);
        return success(envelope, createdProject());
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.createProject(CREATE_REQUEST);
  assert.deepEqual(creates, [{
    project_id: TRANSPORT_PROJECT_ID,
    bpm: 120,
    initial_pattern: {pattern_id: TRANSPORT_PATTERN_ID, bars: 1, events: []},
  }]);
  await session.close();
});

test("Project creation returns the created identities at revision 0", async () => {
  const {session} = fixture({
    send: async (envelope) => envelope.operation === "project.create"
      ? success(envelope, createdProject())
      : success(envelope, defaultResult(envelope.operation)),
  });
  await session.start();
  assert.deepEqual(await session.createProject(CREATE_REQUEST), {
    projectId: TRANSPORT_PROJECT_ID,
    patternId: TRANSPORT_PATTERN_ID,
    projectRevision: 0,
    runtimeReady: false,
  });
  await session.close();
});

test("Project creation negotiates the Pattern transport marker in an opted-in session", async () => {
  const creates = [];
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "project.create") {
        creates.push(envelope.payload);
        return success(envelope, createdProject());
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.createProject(CREATE_REQUEST);
  assert.equal(creates[0].pattern_transport, true);
  await session.close();
});

test("Project creation refuses an invalid request before any Host request", async () => {
  const operations = [];
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  const before = operations.length;
  for (const request of [
    null,
    {...CREATE_REQUEST, projectId: "not-a-uuid"},
    {...CREATE_REQUEST, patternId: "not-a-uuid"},
    {...CREATE_REQUEST, bpm: 39},
    {...CREATE_REQUEST, bpm: 241},
    {...CREATE_REQUEST, bpm: 120.5},
    {...CREATE_REQUEST, bars: 3},
    {...CREATE_REQUEST, extra: true},
  ]) {
    assert.throws(() => session.createProject(request), /Project creation request is invalid/);
  }
  assert.equal(operations.length, before);
  await session.close();
});

test("Project creation is unavailable before the session starts", async () => {
  const operations = [];
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await assert.rejects(
    session.createProject(CREATE_REQUEST),
    (error) => error.code === "HOST_STATE_INVALID",
  );
  assert.equal(operations.includes("project.create"), false);
});

test("Project creation rejects a Host result naming another Project", async () => {
  const {session} = fixture({
    send: async (envelope) => envelope.operation === "project.create"
      ? success(envelope, createdProject({project_id: "00000000-0000-4000-8000-0000000000dd"}))
      : success(envelope, defaultResult(envelope.operation)),
  });
  await session.start();
  await assert.rejects(
    session.createProject(CREATE_REQUEST),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
  await session.close();
});

const DUPLICATE_SOURCE_ID = "00000000-0000-4000-8000-0000000000d1";
const DUPLICATE_COPY_ID = "00000000-0000-4000-8000-0000000000d2";

const DUPLICATE_REQUEST = Object.freeze({
  sourceProjectId: DUPLICATE_SOURCE_ID,
  projectId: DUPLICATE_COPY_ID,
});

function duplicatedProject(overrides = {}) {
  return {
    project_id: DUPLICATE_COPY_ID,
    pattern_id: TRANSPORT_PATTERN_ID,
    revision: 0,
    bpm: 120,
    asset_count: 1,
    assigned_pad_count: 1,
    bundle_digest: "a".repeat(64),
    ...overrides,
  };
}

test("Project duplicate sends the source and the chosen identity", async () => {
  const duplicates = [];
  const {session} = fixture({
    send: async (envelope) => {
      if (envelope.operation === "project.duplicate") {
        duplicates.push(envelope.payload);
        return success(envelope, duplicatedProject());
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await session.duplicateProject(DUPLICATE_REQUEST);
  assert.deepEqual(duplicates, [{
    source_project_id: DUPLICATE_SOURCE_ID,
    project_id: DUPLICATE_COPY_ID,
  }]);
  await session.close();
});

test("Project duplicate returns the copy's library summary at revision 0", async () => {
  const {session} = fixture({
    send: async (envelope) => envelope.operation === "project.duplicate"
      ? success(envelope, duplicatedProject())
      : success(envelope, defaultResult(envelope.operation)),
  });
  await session.start();
  assert.deepEqual(await session.duplicateProject(DUPLICATE_REQUEST), {
    projectId: DUPLICATE_COPY_ID,
    patternId: TRANSPORT_PATTERN_ID,
    revision: 0,
    bpm: 120,
    assetCount: 1,
    assignedPadCount: 1,
    bundleDigest: "a".repeat(64),
  });
  await session.close();
});

test("Project duplicate refuses an invalid request before any Host request", async () => {
  const operations = [];
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  const before = operations.length;
  for (const request of [
    null,
    {...DUPLICATE_REQUEST, sourceProjectId: "not-a-uuid"},
    {...DUPLICATE_REQUEST, projectId: "not-a-uuid"},
    {...DUPLICATE_REQUEST, projectId: DUPLICATE_SOURCE_ID},
    {...DUPLICATE_REQUEST, extra: true},
    {projectId: DUPLICATE_COPY_ID},
  ]) {
    assert.throws(
      () => session.duplicateProject(request),
      /Project duplicate request is invalid/,
    );
  }
  assert.equal(operations.length, before);
  await session.close();
});

test("Project duplicate is unavailable before the session starts", async () => {
  const operations = [];
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await assert.rejects(
    session.duplicateProject(DUPLICATE_REQUEST),
    (error) => error.code === "HOST_STATE_INVALID",
  );
  assert.equal(operations.includes("project.duplicate"), false);
});

test("Project duplicate rejects a Host result naming another Project", async () => {
  const {session} = fixture({
    send: async (envelope) => envelope.operation === "project.duplicate"
      ? success(envelope, duplicatedProject({project_id: DUPLICATE_SOURCE_ID}))
      : success(envelope, defaultResult(envelope.operation)),
  });
  await session.start();
  await assert.rejects(
    session.duplicateProject(DUPLICATE_REQUEST),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
  await session.close();
});

test("Project duplicate rejects a Host result that is not at revision 0", async () => {
  const {session} = fixture({
    send: async (envelope) => envelope.operation === "project.duplicate"
      ? success(envelope, duplicatedProject({revision: 3}))
      : success(envelope, defaultResult(envelope.operation)),
  });
  await session.start();
  await assert.rejects(
    session.duplicateProject(DUPLICATE_REQUEST),
    (error) => error.code === "HOST_PROTOCOL_MISMATCH",
  );
  await session.close();
});

test("a Pattern transport status without its runtime frame is a protocol mismatch", async () => {
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "pattern.transport.inspect") {
        const {runtime_frame: _omitted, ...status} = transportStatus({phase: "idle"});
        return success(envelope, status);
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await assert.rejects(session.inspectPatternTransport(TRANSPORT_SESSION_ID),
    {code: "HOST_PROTOCOL_MISMATCH"});
  await session.close();
});

test("Pattern transport request returns the pending ticket without awaiting settlement", async () => {
  const sent = [];
  const {session} = fixture({
    patternTransport: true,
    now: () => 1234.5,
    send: async (envelope) => {
      sent.push(envelope);
      if (envelope.operation === "pattern.transport.request") {
        return success(envelope, {
          session_id: envelope.payload.session_id,
          command_id: envelope.payload.command_id,
          submit: "accepted",
          status: transportStatus(),
        });
      }
      if (envelope.operation === "pattern.transport.inspect") {
        return success(envelope, transportStatus({
          phase: "idle",
          playing: true,
          recording: true,
          origin_frame: 96_000,
          runtime_frame: 150_000,
        }));
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  const ticket = await session.requestPatternTransport({
    sessionId: TRANSPORT_SESSION_ID,
    projectId: TRANSPORT_PROJECT_ID,
    commandId: TRANSPORT_COMMAND_ID,
    expectedEpoch: 1,
    intent: "record",
    expectedRevision: null,
  });
  // The Promise tail resolves with the pending ticket; the audio receipt and
  // journal settlement are observed, never awaited inline.
  assert.equal(ticket.submit, "accepted");
  assert.equal(ticket.sessionId, TRANSPORT_SESSION_ID);
  assert.equal(ticket.commandId, TRANSPORT_COMMAND_ID);
  assert.equal(ticket.status.phase, "awaiting_audio");
  assert.equal(ticket.status.recording, false);
  const request = sent.find((entry) =>
    entry.operation === "pattern.transport.request");
  assert.deepEqual(request.payload, {
    session_id: TRANSPORT_SESSION_ID,
    project_id: TRANSPORT_PROJECT_ID,
    command_id: TRANSPORT_COMMAND_ID,
    expected_epoch: 1,
    intent: "record",
    expected_revision: null,
  });

  const observed = await session.inspectPatternTransport(TRANSPORT_SESSION_ID);
  assert.deepEqual(observed, {
    engaged: true,
    playing: true,
    recording: true,
    phase: "idle",
    runtimeGeneration: 1,
    transportEpoch: 1,
    originFrame: 96_000,
    // The Host's rendered frame, stamped with the Session's clock on receipt.
    runtimeFrame: 150_000,
    observedAtMilliseconds: 1234.5,
    commandId: TRANSPORT_COMMAND_ID,
    publicationPending: false,
    currentPatternId: TRANSPORT_PATTERN_ID,
    pendingSwitch: null,
    error: null,
  });
  const inspection = sent.find((entry) =>
    entry.operation === "pattern.transport.inspect");
  assert.deepEqual(inspection.payload, {session_id: TRANSPORT_SESSION_ID});
  await session.close();
});

test("Pattern transport rejects invalid intents and malformed statuses", async () => {
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "pattern.transport.request") {
        return success(envelope, {
          session_id: envelope.payload.session_id,
          command_id: envelope.payload.command_id,
          submit: "accepted",
          status: transportStatus({phase: "not-a-phase"}),
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  // Client-side envelope validation refuses an unknown intent before send.
  assert.throws(
    () => session.requestPatternTransport({
      sessionId: TRANSPORT_SESSION_ID,
      projectId: TRANSPORT_PROJECT_ID,
      commandId: TRANSPORT_COMMAND_ID,
      expectedEpoch: 1,
      intent: "toggle",
      expectedRevision: null,
    }),
    /Pattern transport request is invalid/,
  );
  // A malformed Host status fails closed as a protocol mismatch.
  await assert.rejects(
    session.requestPatternTransport({
      sessionId: TRANSPORT_SESSION_ID,
      projectId: TRANSPORT_PROJECT_ID,
      commandId: TRANSPORT_COMMAND_ID,
      expectedEpoch: 1,
      intent: "record",
      expectedRevision: null,
    }),
    {code: "HOST_PROTOCOL_MISMATCH"},
  );
  await session.close();
});

test("Pattern transport busy and retained-error surfaces propagate typed", async () => {
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "pattern.transport.request") {
        return {
          protocol_version: 1,
          request_id: envelope.request_id,
          ok: false,
          error: {
            code: "HOST_STATE_INVALID",
            message: "a Pattern transport operation is pending",
            details: {},
          },
        };
      }
      if (envelope.operation === "pattern.transport.inspect") {
        return success(envelope, transportStatus({
          phase: "error",
          error: {
            code: "IO_ERROR",
            message: "journal settlement failed",
            details: {reason: "storage_failure"},
          },
        }));
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  await assert.rejects(
    session.requestPatternTransport({
      sessionId: TRANSPORT_SESSION_ID,
      projectId: TRANSPORT_PROJECT_ID,
      commandId: TRANSPORT_COMMAND_ID,
      expectedEpoch: 1,
      intent: "play_stop",
      expectedRevision: null,
    }),
    {code: "HOST_STATE_INVALID"},
  );
  const observed = await session.inspectPatternTransport(TRANSPORT_SESSION_ID);
  assert.equal(observed.phase, "error");
  assert.equal(observed.error.code, "IO_ERROR");
  assert.deepEqual(observed.error.details, {reason: "storage_failure"});
  await session.close();
});

test("Pattern transport switch sends the exact payload and validates the result", async () => {
  const sent = [];
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      sent.push(envelope);
      if (envelope.operation === "pattern.transport.switch") {
        return success(envelope, {
          pattern_id: envelope.payload.pattern_id,
          activation_frame: 96_000,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  // A malformed request is refused before anything is sent.
  assert.throws(
    () => session.requestTransportPatternSwitch({patternId: TRANSPORT_PATTERN_ID}),
    /Pattern transport switch request is invalid/,
  );
  assert.throws(
    () => session.requestTransportPatternSwitch({
      patternId: TRANSPORT_PATTERN_ID,
      requestId: "not-a-uuid",
    }),
    TypeError,
  );
  const switched = await session.requestTransportPatternSwitch({
    patternId: TRANSPORT_PATTERN_ID,
    requestId: TRANSPORT_COMMAND_ID,
  });
  assert.deepEqual(switched, {
    patternId: TRANSPORT_PATTERN_ID,
    activationFrame: 96_000,
  });
  const request = sent.find((entry) =>
    entry.operation === "pattern.transport.switch");
  assert.deepEqual(request.payload, {
    pattern_id: TRANSPORT_PATTERN_ID,
    request_id: TRANSPORT_COMMAND_ID,
  });
  await session.close();
});

test("Pattern transport switch forwards each SEQ SNAP choice", async () => {
  const sent = [];
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "pattern.transport.switch") {
        sent.push(envelope.payload);
        return success(envelope, {
          pattern_id: envelope.payload.pattern_id, activation_frame: 96_000,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  for (const snap of ["beat", "bar", "pattern_end"]) {
    await session.requestTransportPatternSwitch({
      patternId: TRANSPORT_PATTERN_ID, requestId: TRANSPORT_COMMAND_ID, snap,
    });
    assert.deepEqual(sent.at(-1), {
      pattern_id: TRANSPORT_PATTERN_ID, request_id: TRANSPORT_COMMAND_ID, snap,
    });
  }
  await session.requestTransportPatternSwitch({
    patternId: TRANSPORT_PATTERN_ID, requestId: TRANSPORT_COMMAND_ID,
    snap: undefined,
  });
  assert.deepEqual(sent.at(-1), {
    pattern_id: TRANSPORT_PATTERN_ID, request_id: TRANSPORT_COMMAND_ID,
  });
  await session.close();
});

test("Pattern transport switch refuses invalid SEQ SNAP before sending", async () => {
  const sent = [];
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      sent.push(envelope.operation);
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  for (const snap of ["off", "BEAT", "", null, 1, {}, ["beat"]]) {
    assert.throws(() => session.requestTransportPatternSwitch({
      patternId: TRANSPORT_PATTERN_ID, requestId: TRANSPORT_COMMAND_ID, snap,
    }), /Pattern transport switch request is invalid/);
  }
  assert.equal(sent.includes("pattern.transport.switch"), false);
  await session.close();
});

test("Pattern transport switch result refuses a zero activation frame", async () => {
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => envelope.operation === "pattern.transport.switch"
      ? success(envelope, {pattern_id: envelope.payload.pattern_id, activation_frame: 0})
      : success(envelope, defaultResult(envelope.operation)),
  });
  await session.start();
  await assert.rejects(
    session.requestTransportPatternSwitch({
      patternId: TRANSPORT_PATTERN_ID,
      requestId: TRANSPORT_COMMAND_ID,
    }),
    /Pattern transport switch result is invalid/,
  );
  await session.close();
});

test("Pattern transport switch result is exact and null means already playing", async () => {
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "pattern.transport.switch") {
        // The pressed Pattern already plays; the queued switch withdrew.
        return success(envelope, {
          pattern_id: envelope.payload.pattern_id,
          activation_frame: null,
        });
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  const withdrawn = await session.requestTransportPatternSwitch({
    patternId: TRANSPORT_PATTERN_ID,
    requestId: TRANSPORT_COMMAND_ID,
  });
  assert.deepEqual(withdrawn, {patternId: TRANSPORT_PATTERN_ID, activationFrame: null});
  await session.close();

  const strict = fixture({
    patternTransport: true,
    send: async (envelope) => envelope.operation === "pattern.transport.switch"
      ? success(envelope, {pattern_id: envelope.payload.pattern_id})
      : success(envelope, defaultResult(envelope.operation)),
  });
  await strict.session.start();
  await assert.rejects(
    strict.session.requestTransportPatternSwitch({
      patternId: TRANSPORT_PATTERN_ID,
      requestId: TRANSPORT_COMMAND_ID,
    }),
    {code: "HOST_PROTOCOL_MISMATCH"},
  );
  await strict.session.close();
});

test("recording switch keeps the existing wire and observes Native selection separately", async () => {
  const target = "00000000-0000-4000-8000-0000000000ee";
  const sent = [];
  let applied = false;
  const {session} = fixture({patternTransport: true, send: async (envelope) => {
    if (envelope.operation === "pattern.transport.inspect") {
      return success(envelope, transportStatus({phase: "idle", playing: true, recording: true,
        current_pattern_id: applied ? target : TRANSPORT_PATTERN_ID,
        origin_frame: applied ? 24_000 : 128, runtime_frame: applied ? 24_001 : 6_000,
        pending_switch: applied ? null : {pattern_id: target, activation_frame: 24_000}}));
    }
    if (envelope.operation === "pattern.transport.switch") {
      sent.push(structuredClone(envelope.payload));
      return success(envelope, {pattern_id: target, activation_frame: 24_000});
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const queued = await session.inspectPatternTransport(TRANSPORT_SESSION_ID);
  assert.equal(queued.recording, true);
  assert.equal(queued.currentPatternId, TRANSPORT_PATTERN_ID);
  const accepted = await session.requestTransportPatternSwitch({
    patternId: target, requestId: TRANSPORT_COMMAND_ID, snap: "beat",
  });
  assert.deepEqual(sent, [{pattern_id: target, request_id: TRANSPORT_COMMAND_ID, snap: "beat"}]);
  assert.deepEqual(accepted, {patternId: target, activationFrame: 24_000});
  applied = true;
  const observed = await session.inspectPatternTransport(TRANSPORT_SESSION_ID);
  assert.equal(observed.recording, true);
  assert.equal(observed.currentPatternId, target);
  assert.equal(observed.originFrame, 24_000);
  assert.equal(observed.pendingSwitch, null);
  // This DTO has no per-switch durable receipt. Native current selection must
  // not be turned into an invented authoring or original input/caller ACK.
  assert.equal(Object.hasOwn(observed, "durableSettled"), false);
  await session.close();
});

test("recording switch busy is retained as a refusal without SDK replay or session failure", async () => {
  let requests = 0;
  const {session} = fixture({patternTransport: true, send: async (envelope) => {
    if (envelope.operation === "pattern.transport.switch") {
      requests += 1;
      return {protocol_version: 1, request_id: envelope.request_id, ok: false,
        error: {code: "HOST_STATE_INVALID", message: "Recording Pattern switch is pending",
          details: {reason: "recording_switch_overlay_pending", pending: true}}};
    }
    if (envelope.operation === "pattern.transport.inspect")
      return success(envelope, transportStatus({phase: "idle", playing: true, recording: true}));
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  await assert.rejects(session.requestTransportPatternSwitch({
    patternId: TRANSPORT_PATTERN_ID, requestId: TRANSPORT_COMMAND_ID, snap: "beat",
  }), (error) => error.code === "HOST_STATE_INVALID" &&
      error.details.reason === "recording_switch_overlay_pending" && error.details.pending === true);
  assert.equal(requests, 1);
  const status = await session.inspectPatternTransport(TRANSPORT_SESSION_ID);
  assert.equal(status.recording, true);
  assert.equal(status.currentPatternId, TRANSPORT_PATTERN_ID);
  assert.equal(requests, 1);
  await session.close();
});

test("Pattern transport status maps the current Pattern and the pending switch", async () => {
  const queued = "00000000-0000-4000-8000-0000000000ee";
  const {session} = fixture({
    patternTransport: true,
    send: async (envelope) => {
      if (envelope.operation === "pattern.transport.inspect") {
        return success(envelope, transportStatus({
          phase: "idle",
          playing: true,
          current_pattern_id: TRANSPORT_PATTERN_ID,
          pending_switch: {pattern_id: queued, activation_frame: 96_000},
        }));
      }
      return success(envelope, defaultResult(envelope.operation));
    },
  });
  await session.start();
  const observed = await session.inspectPatternTransport(TRANSPORT_SESSION_ID);
  assert.equal(observed.currentPatternId, TRANSPORT_PATTERN_ID);
  assert.deepEqual(observed.pendingSwitch, {
    patternId: queued,
    activationFrame: 96_000,
  });
  await session.close();

  const idle = fixture({
    patternTransport: true,
    send: async (envelope) => envelope.operation === "pattern.transport.inspect"
      ? success(envelope, transportStatus({
          phase: "idle",
          playing: true,
          current_pattern_id: null,
          pending_switch: null,
        }))
      : success(envelope, defaultResult(envelope.operation)),
  });
  await idle.session.start();
  const settled = await idle.session.inspectPatternTransport(TRANSPORT_SESSION_ID);
  assert.equal(settled.currentPatternId, null);
  assert.equal(settled.pendingSwitch, null);
  await idle.session.close();
});

const HISTORY_STATUS = Object.freeze({session_id: "20000000-0000-4000-8000-000000000001",
  project_revision: 4, undo_count: 1, redo_count: 0, undo_label: "Edit Pad", redo_label: "",
  disabled_reason: "", can_undo: true, can_redo: false});
const HISTORY_REQUEST = Object.freeze({sessionId: HISTORY_STATUS.session_id,
  commandId: "20000000-0000-4000-8000-000000000002", expectedRevision: 4});

test("authoring history validates status and carries exact session, revision and command identity", async () => {
  const seen = [];
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation === "history.inspect") return success(envelope, HISTORY_STATUS);
    if (["history.undo", "history.redo"].includes(envelope.operation)) {
      seen.push([envelope.operation, structuredClone(envelope.payload)]);
      return success(envelope, {committed_revision: 5, runtime_revision: 5, runtime_published: true});
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const status = await session.inspectAuthoringHistory();
  assert.equal(status.sessionId, HISTORY_REQUEST.sessionId);
  assert.equal(status.canUndo, true);
  assert.equal(status.canRedo, false);
  assert.equal(status.projectRevision, 4);
  assert.ok(Object.isFrozen(status));
  assert.equal((await session.undoAuthoring(HISTORY_REQUEST)).committedRevision, 5);
  await session.redoAuthoring(HISTORY_REQUEST);
  assert.deepEqual(seen, ["history.undo", "history.redo"].map((operation) => [operation,
    {session_id: HISTORY_REQUEST.sessionId, command_id: HISTORY_REQUEST.commandId, expected_revision: 4}]));
  await session.close();
});

test("authoring history fails closed for inconsistent status and malformed command identity", async () => {
  for (const change of [{undo_count: 101}, {can_redo: true}, {disabled_reason: "sequence_session_active"},
    {session_id: "foreign"}, {project_revision: -1}]) {
    const {session} = fixture({send: async (envelope) => success(envelope,
      envelope.operation === "history.inspect" ? {...HISTORY_STATUS, ...change} : defaultResult(envelope.operation))});
    await session.start();
    await assert.rejects(session.inspectAuthoringHistory(), {code: "HOST_PROTOCOL_MISMATCH"});
    await assert.rejects(session.undoAuthoring({...HISTORY_REQUEST, expectedRevision: -1}), TypeError);
    await assert.rejects(session.redoAuthoring({...HISTORY_REQUEST, commandId: "other"}), TypeError);
    await session.close();
  }
});

test("history never automatically repeats an unknown mutation after inspection", async () => {
  let submissions = 0;
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation === "history.undo") {submissions++; throw Object.assign(new Error("lost receipt"), {code: "HOST_TIMEOUT"});}
    return success(envelope, envelope.operation === "history.inspect" ? HISTORY_STATUS : defaultResult(envelope.operation));
  }});
  await session.start();
  await assert.rejects(session.undoAuthoring(HISTORY_REQUEST), {code: "HOST_TIMEOUT"});
  await session.inspectAuthoringHistory();
  assert.equal(submissions, 1);
  await session.close();
});


test("a Pattern event edit sends flat slots as Bank and Pad and returns its publication", async () => {
  const sent = [];
  const patternId = "30000000-0000-4000-8000-000000000001";
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation !== "pattern.events.edit") {
      return success(envelope, defaultResult(envelope.operation));
    }
    sent.push(envelope.payload);
    return success(envelope, {
      committed_revision: 5, project_revision: 5, pattern_id: patternId,
      replayed: false, publication: "live",
      pattern_publication: {generation: 7, activation_frame: 960},
    });
  }});
  await session.start();
  const edited = await session.editPatternEvents({
    patternId, expectedRevision: 4,
    remove: [{slot: 18, onsetTick: 0}],
    put: [{slot: 18, onsetTick: 480, durationTick: 240, velocity: 90}],
  });
  assert.equal(sent.length, 1);
  assert.match(sent[0].command_id, /^[0-9a-f-]{36}$/);
  assert.deepEqual({...sent[0], command_id: null}, {
    command_id: null, expected_revision: 4, pattern_id: patternId,
    remove: [{slot: {bank: 1, pad: 2}, onset_tick: 0}],
    put: [{slot: {bank: 1, pad: 2}, onset_tick: 480, duration_tick: 240, velocity: 90}],
  });
  assert.deepEqual(edited, {
    committedRevision: 5, projectRevision: 5, patternId, replayed: false,
    publication: "live", patternPublication: {generation: 7, activationFrame: 960},
    snapshotError: null,
  });
});

test("a Pattern event edit result must match its publication shape", async () => {
  const patternId = "30000000-0000-4000-8000-000000000001";
  const base = {committed_revision: 5, project_revision: 5, pattern_id: patternId, replayed: false};
  const results = [];
  const {session} = fixture({send: async (envelope) => envelope.operation === "pattern.events.edit"
    ? success(envelope, results.shift())
    : success(envelope, defaultResult(envelope.operation))});
  await session.start();
  const request = {patternId, expectedRevision: 4, remove: [], put: [
    {slot: 0, onsetTick: 0, durationTick: 240, velocity: 100}]};
  results.push({...base, publication: "none"});
  assert.equal((await session.editPatternEvents(request)).patternPublication, null);
  results.push({...base, publication: "deferred", pattern_publication: null});
  const deferred = await session.editPatternEvents(request);
  assert.equal(deferred.publication, "deferred");
  assert.equal(deferred.patternPublication, null);
  assert.equal(deferred.snapshotError, null);
  results.push({...base, publication: "failed", pattern_publication: null,
    snapshot_error: {code: "HOST_STATE_INVALID", message: "unavailable",
      details: {reason: "pattern_publication_unavailable"}}});
  const failed = await session.editPatternEvents(request);
  assert.equal(failed.patternPublication, null);
  assert.equal(failed.snapshotError.code, "HOST_STATE_INVALID");
  assert.equal(failed.snapshotError.details.reason, "pattern_publication_unavailable");
  for (const result of [
    {...base, publication: "published"},
    {...base, publication: "live", pattern_publication: null,
      snapshot_error: {code: "HOST_STATE_INVALID", message: "unavailable", details: {}}},
    {...base, publication: "deferred", pattern_publication: {generation: 1, activation_frame: 0}},
    {...base, publication: "failed", pattern_publication: null},
    {...base, publication: "none", pattern_publication: {generation: 1, activation_frame: 0}},
    {...base, publication: "later"},
    {...base, project_revision: 6, publication: "none"},
  ]) {
    results.push(result);
    await assert.rejects(session.editPatternEvents(request), {code: "HOST_PROTOCOL_MISMATCH"});
  }
});

test("an invalid Pattern event edit request is refused before it is sent", async () => {
  const operations = [];
  const {session} = fixture({send: async (envelope) => {
    operations.push(envelope.operation);
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  operations.length = 0;
  const patternId = "30000000-0000-4000-8000-000000000001";
  await assert.rejects(session.editPatternEvents({patternId, expectedRevision: 0,
    remove: [{slot: 64, onsetTick: 0}], put: []}), RangeError);
  for (const request of [
    {patternId: "not-a-uuid", expectedRevision: 0, remove: [], put: []},
    {patternId, expectedRevision: -1, remove: [], put: []},
    {patternId, expectedRevision: 0, remove: [{slot: 0}], put: []},
    {patternId, expectedRevision: 0, remove: [], put: [{slot: 0, onsetTick: 0}]},
  ]) {
    await assert.rejects(session.editPatternEvents(request), TypeError);
  }
  assert.deepEqual(operations, []);
});

test("Pattern length changes send exact payloads with a fresh command per call", async () => {
  const sent = [];
  const patternId = "30000000-0000-4000-8000-000000000001";
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation === "pattern.resize") {
      sent.push(envelope);
      return success(envelope, {
        committed_revision: 5, project_revision: 5, pattern_id: patternId, bars: 2,
        replayed: false, publication: "published",
        pattern_publication: {generation: 7, activation_frame: 960},
      });
    }
    if (envelope.operation === "pattern.double") {
      sent.push(envelope);
      return success(envelope, {
        committed_revision: 6, project_revision: 6, pattern_id: patternId, bars: 4,
        replayed: false, publication: "none",
      });
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const resized = await session.resizePattern({patternId, bars: 2, expectedRevision: 4});
  const doubled = await session.doubleUpPattern({patternId, expectedRevision: 5});
  assert.deepEqual(sent.map(({operation}) => operation), ["pattern.resize", "pattern.double"]);
  assert.deepEqual({...sent[0].payload, command_id: null}, {
    command_id: null, expected_revision: 4, pattern_id: patternId, bars: 2,
  });
  assert.deepEqual({...sent[1].payload, command_id: null}, {
    command_id: null, expected_revision: 5, pattern_id: patternId,
  });
  for (const envelope of sent) {
    assert.match(envelope.payload.command_id, /^[0-9a-f-]{36}$/);
  }
  assert.notEqual(sent[0].payload.command_id, sent[1].payload.command_id);
  assert.deepEqual(resized, {
    committedRevision: 5, projectRevision: 5, patternId, bars: 2, replayed: false,
    publication: "published", patternPublication: {generation: 7, activationFrame: 960},
    snapshotError: null,
  });
  assert.deepEqual(doubled, {
    committedRevision: 6, projectRevision: 6, patternId, bars: 4, replayed: false,
    publication: "none", patternPublication: null, snapshotError: null,
  });
});

test("a Pattern length result must match its request and publication shape", async () => {
  const patternId = "30000000-0000-4000-8000-000000000001";
  const base = {committed_revision: 5, project_revision: 5, pattern_id: patternId,
    bars: 2, replayed: false};
  const results = [];
  const {session} = fixture({send: async (envelope) =>
    ["pattern.resize", "pattern.double"].includes(envelope.operation)
      ? success(envelope, results.shift())
      : success(envelope, defaultResult(envelope.operation))});
  await session.start();
  const request = {patternId, bars: 2, expectedRevision: 4};
  results.push({...base, publication: "deferred", pattern_publication: null});
  assert.equal((await session.resizePattern(request)).publication, "deferred");
  results.push({...base, publication: "failed", pattern_publication: null,
    snapshot_error: {code: "HOST_STATE_INVALID", message: "unavailable",
      details: {reason: "pattern_publication_unavailable"}}});
  const failed = await session.resizePattern(request);
  assert.equal(failed.snapshotError.details.reason, "pattern_publication_unavailable");
  for (const result of [
    {...base, bars: 4, publication: "none"},
    {...base, publication: "live", pattern_publication: {generation: 1, activation_frame: 0}},
    {...base, publication: "published"},
    {...base, publication: "none", pattern_publication: null},
    {...base, publication: "failed", pattern_publication: null},
    {...base, project_revision: 6, publication: "none"},
  ]) {
    results.push(result);
    await assert.rejects(session.resizePattern(request), {code: "HOST_PROTOCOL_MISMATCH"});
  }
  results.push({...base, bars: 1, publication: "none"});
  await assert.rejects(session.doubleUpPattern({patternId, expectedRevision: 4}),
    {code: "HOST_PROTOCOL_MISMATCH"});
});

test("a Pattern copy returns its slot and must match its request", async () => {
  const sent = [];
  const sourcePatternId = "30000000-0000-4000-8000-000000000001";
  const patternId = "30000000-0000-4000-8000-000000000002";
  const base = {committed_revision: 5, project_revision: 5,
    source_pattern_id: sourcePatternId, pattern_id: patternId, replayed: false,
    publication: "none"};
  const results = [];
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation !== "pattern.copy") {
      return success(envelope, defaultResult(envelope.operation));
    }
    sent.push(envelope.payload);
    return success(envelope, results.shift());
  }});
  await session.start();
  const request = {sourcePatternId, patternId, expectedRevision: 4};
  results.push({...base, pattern_slot: 4});
  assert.deepEqual(await session.copyPattern(request), {
    committedRevision: 5, projectRevision: 5, sourcePatternId, patternId,
    patternSlot: 4, replayed: false,
  });
  assert.deepEqual({...sent[0], command_id: null}, {
    command_id: null, expected_revision: 4, source_pattern_id: sourcePatternId,
    pattern_id: patternId,
  });
  results.push({...base, pattern_slot: null});
  assert.equal((await session.copyPattern(request)).patternSlot, null);
  assert.notEqual(sent[0].command_id, sent[1].command_id);
  for (const result of [
    {...base, pattern_slot: 16},
    {...base, pattern_slot: 4, publication: "published"},
    {...base, pattern_slot: 4, pattern_id: sourcePatternId},
    {...base, pattern_slot: 4, project_revision: 6},
    {...base},
  ]) {
    results.push(result);
    await assert.rejects(session.copyPattern(request), {code: "HOST_PROTOCOL_MISMATCH"});
  }
});

test("an invalid Pattern length or copy request is refused before it is sent", async () => {
  const operations = [];
  const {session} = fixture({send: async (envelope) => {
    operations.push(envelope.operation);
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  operations.length = 0;
  const patternId = "30000000-0000-4000-8000-000000000001";
  for (const request of [
    {patternId, bars: 3, expectedRevision: 0},
    {patternId: "not-a-uuid", bars: 2, expectedRevision: 0},
    {patternId, bars: 2, expectedRevision: -1},
    {patternId, bars: 2},
  ]) {
    await assert.rejects(session.resizePattern(request), TypeError);
  }
  for (const request of [
    {patternId, expectedRevision: 0, bars: 2},
    {patternId: "not-a-uuid", expectedRevision: 0},
  ]) {
    await assert.rejects(session.doubleUpPattern(request), TypeError);
  }
  for (const request of [
    {sourcePatternId: patternId, patternId: "not-a-uuid", expectedRevision: 0},
    {sourcePatternId: "not-a-uuid", patternId, expectedRevision: 0},
    {patternId, expectedRevision: 0},
  ]) {
    await assert.rejects(session.copyPattern(request), TypeError);
  }
  assert.deepEqual(operations, []);
});

test("Pad delete cancels an unread Blob and queued imports only for its slot", async () => {
  const operations = [];
  let completeRead;
  let startedRead;
  const reading = new Promise((resolve) => { startedRead = resolve; });
  const file = {size: 4, slice: () => ({arrayBuffer: () => {
    startedRead();
    return new Promise((resolve) => { completeRead = resolve; });
  }})};
  const {session} = fixture({send: async (envelope) => {
    operations.push(envelope);
    if (envelope.operation === "sample.import.begin") return success(envelope, {
      token: envelope.payload.import_token, expected_bytes: 4,
    });
    if (envelope.operation === "sample.import.abort") return success(envelope, {aborted: true});
    if (envelope.operation === "sample.import.chunk") return success(envelope, {received_bytes: 4, final: true});
    if (["sample.import.commit", "pad.delete"].includes(envelope.operation)) return success(envelope, {
      committed_revision: envelope.operation === "pad.delete" ? 2 : 1,
      runtime_revision: envelope.operation === "pad.delete" ? 2 : 1,
      runtime_published: true,
    });
    return success(envelope, defaultResult(envelope.operation));
  }});
  await session.start();
  const inFlight = session.importAssignSample(file, {slot: 0, expectedRevision: 0});
  const inFlightRejected = assert.rejects(inFlight, {name: "AbortError"});
  await reading;
  const queued = session.importAssignSample(new Blob([new Uint8Array(4)]), {slot: 0, expectedRevision: 0});
  const queuedRejected = assert.rejects(queued, {name: "AbortError"});
  const other = session.importAssignSample(new Blob([new Uint8Array(4)]), {slot: 1, expectedRevision: 0});
  const deleted = session.deletePad({slot: 0, expectedRevision: 1});
  await Promise.all([inFlightRejected, queuedRejected, other]);
  assert.equal((await deleted).committedRevision, 2);
  assert.deepEqual(operations.map(({operation}) => operation), [
    "sample.import.begin", "sample.import.abort", "sample.import.begin",
    "sample.import.chunk", "sample.import.commit", "pad.delete",
  ]);
  assert.deepEqual(operations.filter(({operation}) => operation === "sample.import.begin")
    .map(({payload}) => payload.slot), [{bank: 0, pad: 0}, {bank: 0, pad: 1}]);
  assert.deepEqual(operations.at(-1).payload.slot, {bank: 0, pad: 0});
  assert.equal(operations.at(-1).payload.expected_revision, 1);
  completeRead(new ArrayBuffer(4));
  await drainTasks();
  assert.equal(operations.length, 6);
});

test("Pad delete rejects invalid slot and request shape", async () => {
  const {session} = fixture();
  await session.start();
  await assert.rejects(session.deletePad({slot: 64, expectedRevision: 0}), RangeError);
  for (const request of [{slot: 0, expectedRevision: -1},
    {slot: 0, expectedRevision: 0, extra: true}]) {
    await assert.rejects(session.deletePad(request), TypeError);
  }
});


test("slot acquisition supplies only Core addresses without holding the Project action queue", async () => {
  let releaseObject;
  const objectReady = new Promise(resolve => {releaseObject = resolve;});
  let requested;
  let supplied = false;
  const catalog = {readIndex: async () => new Uint8Array(4),
    readObject: async object => {requested = object; await objectReady; return new Uint8Array(8);}};
  const {session} = fixture({soundsetCatalog: catalog, send(envelope) {
    const operation = envelope.operation;
    if (operation === "pad.delete") return success(envelope, {committed_revision: 1, runtime_revision: 1, runtime_published: true});
    if (operation === "soundset.catalog.index") return success(envelope, {staged: true});
    if (operation === "soundset.catalog.pending") return success(envelope, {
      objects: [{object_kind: "blob", sha256: BLOB_SHA}], index: false});
    if (operation === "soundset.catalog.supply") {supplied = true; return success(envelope, {staged: true});}
    if (operation === "soundset.slot.acquire") {
      if (!supplied) {const error = new Error("object missing"); error.code = "IO_ERROR";
        // Actual Web normalization removes internal reason strings.
        error.details = {}; throw error;}
      return success(envelope, {set_id: SET_ID, version: "1.0.0", manifest_sha256: MANIFEST_SHA,
        slot_index: 3, slots: Array.from({length: 16}, (_, slot) => slot === 3 ? {
          slot, occupied: true, role: "snare", name: "Snare", artifact: {sha256: BLOB_SHA, byte_length: 8, media_type: "audio/wav"},
          audio: {sample_rate: 48000, channels: 1, source_frames: 4, prepared_bytes: 16, prepared_frames: 4},
        } : {slot, occupied: false, artifact: null})});
    }
    return success(envelope, defaultResult(operation));
  }});
  assert.equal(await session.start(), true);
  const pending = session.acquireSoundSetSlot({setId: SET_ID, version: "1.0.0", manifestSha256: MANIFEST_SHA, slotIndex: 3});
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(requested, {object_kind: "blob", sha256: BLOB_SHA});
  // A real authoring operation must finish while the asset request is blocked.
  await session.deletePad({slot: 7, expectedRevision: 0});
  releaseObject();
  const acquired = await pending;
  assert.equal(acquired.slot.slot, 3);
  assert.equal(acquired.slot.artifact.sha256, BLOB_SHA);
});

test("slot installation never forwards a replacement policy", async () => {
  const installs = [];
  const {session} = fixture({soundsetCatalog: null, send(envelope) {
    if (envelope.operation === "soundset.slot.install") {
      installs.push(envelope.payload);
      return success(envelope, {bank_id: 0, set_id: SET_ID, version: "1.0.0", manifest_sha256: MANIFEST_SHA,
        installed: [{slot_index: 3, pad: 3}], collisions: [], kept: [], project_revision: 1, replayed: false});
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  assert.equal(await session.start(), true);
  const request = {setId: SET_ID, version: "1.0.0", manifestSha256: MANIFEST_SHA,
    bankId: 0, slotIndex: 3, commandId: "00000000-0000-4000-8000-000000000941", expectedRevision: 0};
  const receipt = await session.installSoundSetSlot(request);
  assert.deepEqual(receipt.installed, [{slotIndex: 3, pad: 3}]);
  assert.equal(installs[0].slot_index, 3);
  await assert.rejects(session.installSoundSetSlot({...request, occupiedPadPolicy: "replace"}), error => error.code === "INVALID_ARGUMENT");
  assert.equal(installs.length, 1);
});

test("a Pad colour sends a flat slot as Bank and Pad, an index or null, and publishes nothing", async () => {
  const sent = [];
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation !== "pad.colour.set") {
      return success(envelope, defaultResult(envelope.operation));
    }
    sent.push(envelope.payload);
    const revision = envelope.payload.expected_revision + 1;
    return success(envelope, {
      committed_revision: revision, project_revision: revision,
      replayed: false, publication: "none",
    });
  }});
  await session.start();
  assert.deepEqual(await session.setPadColour({slot: 18, colour: 2, expectedRevision: 4}),
    {committedRevision: 5, projectRevision: 5, replayed: false});
  assert.deepEqual(await session.setPadColour({slot: 18, colour: null, expectedRevision: 5}),
    {committedRevision: 6, projectRevision: 6, replayed: false});
  assert.equal(sent.length, 2);
  for (const payload of sent) assert.match(payload.command_id, /^[0-9a-f-]{36}$/);
  assert.notEqual(sent[0].command_id, sent[1].command_id);
  assert.deepEqual(sent.map((payload) => ({...payload, command_id: null})), [
    {command_id: null, expected_revision: 4, slot: {bank: 1, pad: 2}, colour: 2},
    {command_id: null, expected_revision: 5, slot: {bank: 1, pad: 2}, colour: null},
  ]);
  await session.close();
});

test("a Pad colour refuses an invalid request before sending and a result that publishes", async () => {
  const results = [];
  let sends = 0;
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation !== "pad.colour.set") {
      return success(envelope, defaultResult(envelope.operation));
    }
    sends += 1;
    return success(envelope, results.shift());
  }});
  await session.start();
  await assert.rejects(session.setPadColour({slot: 64, colour: 1, expectedRevision: 0}), RangeError);
  for (const request of [
    {slot: 0, colour: 1},
    {slot: 0, colour: -1, expectedRevision: 0},
    {slot: 0, colour: 256, expectedRevision: 0},
    {slot: 0, colour: "drums", expectedRevision: 0},
    {slot: 0, colour: 1, expectedRevision: -1},
    {slot: 0, colour: 1, expectedRevision: 0, commandId: "00000000-0000-4000-8000-000000000001"},
  ]) {
    await assert.rejects(session.setPadColour(request), TypeError);
  }
  assert.equal(sends, 0);
  const base = {committed_revision: 1, project_revision: 1, replayed: false};
  for (const result of [
    {...base, publication: "published"},
    {...base, publication: "none", runtime_published: true},
    {...base, project_revision: 2, publication: "none"},
    {committed_revision: 1, project_revision: 1, publication: "none"},
  ]) {
    results.push(result);
    await assert.rejects(session.setPadColour({slot: 0, colour: 1, expectedRevision: 0}),
      {code: "HOST_PROTOCOL_MISMATCH"});
  }
  assert.equal(sends, 4);
  await session.close();
});

test("Project inspection hands each Pad's Core-resolved colour through unchanged", async () => {
  const pads = [
    {pad: 0, asset_id: "10000000-0000-4000-8000-000000000001", category: "drums", colour_override: null, colour: 0},
    {pad: 1, asset_id: "10000000-0000-4000-8000-000000000002", category: "bass", colour_override: 3, colour: 3},
    {pad: 2, asset_id: "10000000-0000-4000-8000-000000000003", category: null, colour_override: null, colour: null},
    {pad: 3, asset_id: null, category: null, colour_override: null, colour: null},
  ];
  const {session} = fixture({send: async (envelope) => envelope.operation === "project.inspect"
    ? success(envelope, {project_revision: 7, project: {revision: 7, banks: [{bank: 0, pads}]}})
    : success(envelope, defaultResult(envelope.operation))});
  await session.start();
  const inspected = await session.inspectProject();
  assert.deepEqual(inspected.project.banks[0].pads, pads);
  await session.close();
});

function inputWireStatus(payload, sequence, complete = true, disposition = null) {
  const ticket = {command_id: payload.command_id, runtime_generation: payload.runtime_generation,
    frame_epoch: payload.frame_epoch, ticket: payload.input_serial};
  const authority = {recording: false, schedule_serial: null, transport_epoch: null};
  return {ticket, admission: {sequence, acceptance_ordinal: sequence, authority},
    native_result: {runtime_generation: payload.runtime_generation, frame_epoch: payload.frame_epoch,
      sequence, held_press_sequence: payload.held_press_sequence, acceptance_ordinal: sequence,
      runtime_frame: 123, slot: payload.slot, authority,
      disposition: disposition ?? (payload.kind === "release" ? "release_no_voice" : "muted_no_voice")},
    durable_settled: complete, retained: false, complete, expired: false, error: null};
}
function inputProfileFixture({settled = () => true, onRequest = () => {}, sequenceFor = (p) => p.input_serial,
  now, publishRuntime = false, browserWindow = {}, runtimeTerminator, extraSend = () => null} = {}) {
  const entries = new Map();
  const sent = [];
  let handle = 10;
  const f = fixture({patternTransport: true, publishRuntime, browserWindow, now, runtimeTerminator,
    registerAudioNode: () => ++handle, startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
    send: async (envelope, options) => {
      sent.push(envelope);
      const p = envelope.payload;
      // Allow a strict transport failure before the default admission or
      // inspection fixture can fabricate a successful reply.
      const custom = extraSend(envelope, options);
      if (custom !== null && custom !== undefined) return custom;
      if (envelope.operation === "pattern.transport.input.request") {
        onRequest(p, options);
        const status = inputWireStatus(p, sequenceFor(p), settled());
        entries.set(p.input_serial, {payload: p, status});
        return success(envelope, {ticket: status.ticket, status});
      }
      if (envelope.operation === "pattern.transport.input.inspect") {
        const entry = entries.get(p.ticket);
        const status = {...entry.status, complete: settled(), durable_settled: settled()};
        return success(envelope, status);
      }
      return success(envelope, envelope.operation === "pattern.transport.inspect"
        ? transportStatus({phase: "idle"}) : defaultResult(envelope.operation));
    }});
  return {...f, entries, sent};
}
async function activateInputProfile(f) {
  assert.equal(await f.session.start(), true);
  assert.equal(await f.session.activateAudio(createUserGestureToken({isTrusted: true})), true);
}
async function untilInputRequests(f, count) {
  for (let attempt = 0; attempt < 100 && f.sent.filter((e) => e.operation === "pattern.transport.input.request").length < count; ++attempt)
    await drainTasks();
  assert.equal(f.sent.filter((e) => e.operation === "pattern.transport.input.request").length, count);
}

test("packaged runtime.session is the same frozen public Session and forwards the companion API", async () => {
  const browserWindow = {};
  const f = inputProfileFixture({publishRuntime: true, browserWindow});
  await activateInputProfile(f);
  assert.equal(browserWindow.lmdjWebRuntimeHost.session, f.session);
  assert.equal(Object.isFrozen(browserWindow.lmdjWebRuntimeHost.session), true);
  assert.equal(Object.isFrozen(browserWindow.lmdjWebRuntimeHost.patternTransport), true);
  assert.equal(browserWindow.lmdjWebRuntimeHost.patternTransport.requestPatternInput, f.session.requestPatternInput);
  assert.equal(Object.getOwnPropertyDescriptor(browserWindow.lmdjWebRuntimeHost, "session").writable, false);
  assert.equal(typeof browserWindow.lmdjWebRuntimeHost.inspection.inspectProject, "function");
  assert.equal(typeof browserWindow.lmdjWebRuntimeHost.providers.listProviders, "function");
  const result = await f.session.trigger(0, 100, "pointer");
  assert.deepEqual(result, {sequence: 1, slot: 0, velocity: 100, source: "pointer"});
  assert.equal(await f.session.release(0, "pointer"), true);
  const activation = f.sent.findIndex((e) => e.operation === "audio.activate");
  const negotiation = f.sent.findIndex((e) => e.operation === "pattern.transport.count-in.capabilities" && e.payload.negotiate);
  const refresh = f.sent.findIndex((e, i) => i > activation && e.operation === "pattern.transport.count-in.capabilities");
  const press = f.sent.findIndex((e) => e.operation === "pattern.transport.input.request");
  assert.ok(negotiation < activation && activation < refresh && refresh < press);
  await f.session.close();
});

test("two concurrent durable presses retain their own tickets while Release and Stop remain serviceable", async () => {
  let settled = false;
  const f = inputProfileFixture({settled: () => settled, extraSend: (e) => e.operation === "pattern.transport.request"
    ? success(e, {session_id: e.payload.session_id, command_id: e.payload.command_id, submit: "accepted",
        status: transportStatus({phase: "idle"})}) : null});
  await activateInputProfile(f);
  const first = f.session.trigger(0, 100, "pointer");
  const second = f.session.trigger(1, 110, "keyboard");
  await untilInputRequests(f, 2);
  let firstDone = false;
  void first.then(() => { firstDone = true; });
  const released = f.session.release(0, "pointer");
  await untilInputRequests(f, 3);
  const stop = await f.session.requestPatternTransport({sessionId: TRANSPORT_SESSION_ID,
    projectId: TRANSPORT_PROJECT_ID, commandId: TRANSPORT_COMMAND_ID, expectedEpoch: 2,
    intent: "play_stop", expectedRevision: null});
  assert.equal(stop.submit, "accepted");
  assert.equal((await f.session.inspectPatternTransport(TRANSPORT_SESSION_ID)).phase, "idle");
  assert.equal(firstDone, false);
  const requests = f.sent.filter((e) => e.operation === "pattern.transport.input.request");
  assert.deepEqual(requests.map((e) => e.payload.input_serial), ["1", "2", "3"]);
  assert.equal(requests[2].payload.held_press_sequence, "1");
  settled = true;
  assert.equal((await first).sequence, 1);
  assert.equal((await second).sequence, 2);
  assert.equal(await released, true);
  assert.equal(await f.session.release(1, "keyboard"), true, "consuming the press kept its physical release owner");
  const consumes = f.sent.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume);
  assert.deepEqual(consumes.map((e) => e.payload.ticket).sort(), ["1", "2", "3", "4"]);
  await f.session.close();
});

test("companion input round-trips exact uint64 and rejects unsafe completion frames", async () => {
  const f = inputProfileFixture({sequenceFor: () => "18446744073709551615"});
  await activateInputProfile(f);
  const request = {commandId: TRANSPORT_COMMAND_ID, runtimeGeneration: "18446744073709551615",
    frameEpoch: "9007199254740993", inputSerial: "18446744073709551615", slot: 0, velocity: 1,
    kind: "press", held: false, heldPressSequence: null};
  const admission = await f.session.requestPatternInput(request);
  assert.equal(admission.status.admission.sequence, "18446744073709551615");
  assert.equal(admission.status.nativeResult.frameEpoch, "9007199254740993");
  assert.equal((await f.session.inspectPatternInput(admission.ticket)).nativeResult.disposition, "muted_no_voice");
  f.entries.get(request.inputSerial).status.native_result.runtime_frame = Number.MAX_SAFE_INTEGER + 1;
  await assert.rejects(f.session.inspectPatternInput(admission.ticket), {code: "HOST_PROTOCOL_MISMATCH"});
  await f.session.close();
});

test("unsafe legacy trigger projection retains a real physical Release after truthful completion", async () => {
  const f = inputProfileFixture({sequenceFor: (p) => p.kind === "press" ? "9007199254740993" : "9007199254740994"});
  await activateInputProfile(f);
  await assert.rejects(f.session.trigger(0, 100, "pointer"), {code: "HOST_STATE_INVALID"});
  assert.equal(await f.session.release(0, "pointer"), true);
  const release = f.sent.filter((e) => e.operation === "pattern.transport.input.request")[1];
  assert.equal(release.payload.held_press_sequence, "9007199254740993");
  assert.equal(f.sent.filter((e) => e.operation === "pattern.transport.input.request").length, 2);
  await f.session.close();
});

test("original Pad deadline expiry keeps reconciliation and held release alive without re-enqueue", async () => {
  let clock = 0;
  let settled = false;
  const f = inputProfileFixture({now: () => clock, settled: () => settled,
    onRequest: (p) => { if (p.kind === "press") clock = 1001; }});
  await activateInputProfile(f);
  await assert.rejects(f.session.trigger(0, 100, "pointer"), {code: "HOST_TIMEOUT"});
  const release = f.session.release(0, "pointer");
  await untilInputRequests(f, 2);
  assert.equal(f.sent.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume).length, 0);
  settled = true;
  assert.equal(await release, true);
  await drainTasks();
  const consumed = f.sent.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume);
  assert.deepEqual(consumed.map((e) => e.payload.ticket).sort(), ["1", "2"]);
  assert.equal(f.sent.filter((e) => e.operation === "pattern.transport.input.request").length, 2);
  await f.session.close();
});

test("a Pad queued behind a runtime action spends its budget only from its admission turn", async () => {
  let clock = 0;
  let resolveStop;
  let stopStarted;
  const started = new Promise((resolve) => { stopStarted = resolve; });
  const gate = new Promise((resolve) => { resolveStop = resolve; });
  const f = inputProfileFixture({now: () => clock, extraSend: (e) => {
    if (e.operation !== "pattern.transport.request") return null;
    stopStarted();
    return gate.then(() => success(e, {session_id: e.payload.session_id, command_id: e.payload.command_id,
      submit: "accepted", status: transportStatus({phase: "idle"})}));
  }});
  await activateInputProfile(f);
  const stop = f.session.requestPatternTransport({sessionId: TRANSPORT_SESSION_ID,
    projectId: TRANSPORT_PROJECT_ID, commandId: TRANSPORT_COMMAND_ID, expectedEpoch: 2,
    intent: "play_stop", expectedRevision: null});
  await started;
  const press = f.session.trigger(0, 100, "pointer");
  clock = 1001;
  resolveStop();
  await stop;
  assert.equal((await press).sequence, 1);
  assert.equal(f.sent.filter((e) => e.operation === "pattern.transport.input.request").length, 1);
  assert.equal(await f.session.release(0, "pointer"), true);
  await f.session.close();
});

test("an independent host queue cannot dispatch an expired Pad or spend its input identity", async () => {
  let clock = 0;
  let releaseQuery;
  let queryStarted;
  const started = new Promise((resolve) => { queryStarted = resolve; });
  const gate = new Promise((resolve) => { releaseQuery = resolve; });
  const f = inputProfileFixture({now: () => clock, extraSend: (e) => {
    if (e.operation !== "project.inspect") return null;
    queryStarted();
    return gate.then(() => success(e, {project_revision: 7}));
  }});
  await activateInputProfile(f);
  const query = f.session.inspectProject();
  await started;
  const press = f.session.trigger(0, 100, "pointer").then(
    (value) => ({value}), (error) => ({error}));
  await drainTasks();
  assert.equal(f.sent.filter((e) => e.operation.startsWith("pattern.transport.input.")).length, 0);
  clock = 1001;
  releaseQuery();
  assert.equal((await query).project_revision, 7, "the independent Host query actually completed");
  const expired = await press;
  assert.equal(expired.error?.code, "HOST_TIMEOUT");
  assert.equal(expired.error.details.pending, false, "nothing was submitted to Native");
  assert.equal(f.sent.filter((e) => e.operation.startsWith("pattern.transport.input.")).length, 0);
  assert.equal(f.entries.size, 0);
  assert.equal(f.session.diagnostics().trigger_admitted_count, 0);
  assert.equal(await f.session.release(0, "pointer"), false, "expiry created no physical owner");
  assert.equal((await f.session.trigger(1, 100, "pointer")).sequence, 1);
  const admitted = f.sent.find((e) => e.operation === "pattern.transport.input.request");
  assert.equal(admitted.payload.input_serial, "1", "pre-dispatch expiry spent no input identity");
  assert.equal(await f.session.release(1, "pointer"), true);
  await f.session.close();
});

test("host queue residence after the admission turn spends the Pad budget; runtime queue residence does not", async () => {
  let clock = 0;
  let releaseStop;
  let stopStarted;
  let releaseQuery;
  let queryStarted;
  const stopReady = new Promise((resolve) => { stopStarted = resolve; });
  const stopGate = new Promise((resolve) => { releaseStop = resolve; });
  const queryReady = new Promise((resolve) => { queryStarted = resolve; });
  const queryGate = new Promise((resolve) => { releaseQuery = resolve; });
  const deadlines = [];
  const f = inputProfileFixture({now: () => clock, onRequest: (p, options) => {
    if (p.kind === "press") deadlines.push({submittedAt: clock, deadlineMs: options.deadlineMs});
  }, extraSend: (e) => {
    if (e.operation === "pattern.transport.request") {
      stopStarted();
      return stopGate.then(() => success(e, {session_id: e.payload.session_id,
        command_id: e.payload.command_id, submit: "accepted", status: transportStatus({phase: "idle"})}));
    }
    if (e.operation === "project.inspect") {
      queryStarted();
      return queryGate.then(() => success(e, {project_revision: 7}));
    }
    return null;
  }});
  await activateInputProfile(f);
  const stop = f.session.requestPatternTransport({sessionId: TRANSPORT_SESSION_ID,
    projectId: TRANSPORT_PROJECT_ID, commandId: TRANSPORT_COMMAND_ID, expectedEpoch: 2,
    intent: "play_stop", expectedRevision: null});
  await stopReady;
  const query = f.session.inspectProject();
  const press = f.session.trigger(0, 100, "pointer");
  await drainTasks();
  assert.equal(deadlines.length, 0, "the Pad waited behind the runtime action");
  clock = 400;
  releaseStop();
  assert.equal((await stop).submit, "accepted", "the runtime action actually completed");
  await queryReady;
  await drainTasks();
  assert.equal(deadlines.length, 0, "the Pad then waited behind the independent Host query");
  clock = 750;
  releaseQuery();
  assert.equal((await query).project_revision, 7);
  assert.equal((await press).sequence, 1);
  // The admission turn began at 400 when the runtime action released it.
  assert.deepEqual(deadlines, [{submittedAt: 750, deadlineMs: 650}]);
  assert.equal(deadlines[0].submittedAt + deadlines[0].deadlineMs, 1400,
    "the Native handoff kept one second from the admission turn");
  assert.equal(await f.session.release(0, "pointer"), true);
  assert.deepEqual(f.sent.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
    .map((e) => e.payload.ticket), ["1", "2"]);
  await f.session.close();
});

for (const lateAt of ["admission", "consume"]) {
  test(`a total input result late at ${lateAt} is consumed without a late Pad success`, async () => {
    let clock = 0;
    const f = inputProfileFixture({now: () => clock, onRequest: (p) => {
      if (lateAt === "admission" && p.kind === "press") clock = 1000;
    }, extraSend: (e) => {
      if (lateAt === "consume" && e.operation === "pattern.transport.input.inspect" &&
          e.payload.consume && e.payload.ticket === "1") clock = 1000;
      return null;
    }});
    await activateInputProfile(f);
    await assert.rejects(f.session.trigger(0, 100, "pointer"),
      (error) => error.code === "HOST_TIMEOUT" && error.details.pending === true);
    await drainTasks();
    assert.deepEqual(f.sent.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
      .map((e) => e.payload.ticket), ["1"], "the accepted total result was genuinely inspected for consumption");
    assert.equal(f.entries.get("1").status.native_result.disposition, "muted_no_voice");
    assert.equal(f.entries.get("1").status.error, null);
    assert.equal(await f.session.release(0, "pointer"), true,
      "caller expiry and press consumption preserved the independent physical release");
    const requests = f.sent.filter((e) => e.operation === "pattern.transport.input.request");
    assert.deepEqual(requests.map((e) => e.payload.input_serial), ["1", "2"]);
    assert.equal(requests[1].payload.held_press_sequence, "1");
    assert.deepEqual(f.sent.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
      .map((e) => e.payload.ticket), ["1", "2"]);
    await f.session.close();
  });
}

for (const code of ["HOST_STATE_INVALID", "HOST_PROTOCOL_MISMATCH"]) {
  test(`fatal ${code} survives rejected correlated releases with its real owner debts retained`, async () => {
    let settled = true;
    let sealed = false;
    const physicalOwners = new Map();
    const consumed = new Set();
    const terminalError = Object.assign(new Error("original retained transport failure"), {
      code, details: {resource: "pattern_input", terminal_state: "sealed", observed: 2},
    });
    const cleanupAttempts = [];
    const terminalAttempts = [];
    const f = inputProfileFixture({settled: () => settled, onRequest: (p) => {
      if (p.kind === "press") physicalOwners.set(p.input_serial, {...p});
    }, extraSend: (e) => {
      if (sealed) {
        cleanupAttempts.push(e);
        throw terminalError;
      }
      if (e.operation === "pattern.transport.input.inspect" && e.payload.consume) {
        assert.equal(f.entries.get(e.payload.ticket).status.complete, true,
          "only a total input result can be consumed");
        assert.equal(consumed.has(e.payload.ticket), false, "each input result is consumed exactly once");
        consumed.add(e.payload.ticket);
      }
      return null;
    }, runtimeTerminator: async () => {
      // This seam refuses actual outstanding fixture debts. It provides no
      // successful worker shutdown, owner ACK or invented terminal receipt.
      terminalAttempts.push({unconsumed: [...f.entries.keys()].filter((key) => !consumed.has(key)),
        physical: [...physicalOwners.keys()]});
      throw terminalError;
    }});
    await activateInputProfile(f);
    await f.session.setSamplePreview(0, PLAYBACK);
    assert.equal((await f.session.trigger(0, 100, "pointer")).sequence, 1);
    assert.deepEqual([...consumed], ["1"]);
    assert.deepEqual([...physicalOwners.keys()], ["1"], "a consumed silent press still owes physical release");
    settled = false;
    const pendingPress = f.session.trigger(1, 110, "keyboard").then(
      (value) => ({value}), (error) => ({error}));
    await untilInputRequests(f, 2);
    assert.equal(f.entries.get("2").status.durable_settled, false);
    assert.equal(consumed.has("2"), false);
    const originalInputs = [...f.entries.values()].map((entry) => structuredClone(entry));
    const failedObservations = [];
    f.session.subscribeHostState((event) => {
      if (event.state === "failed") failedObservations.push({event, operations: cleanupAttempts.map((e) => e.operation)});
    });
    sealed = true;
    f.emitTransportFailure(terminalError);
    f.emitTransportFailure({code: "IO_ERROR"});
    assert.equal(f.session.diagnostics().state, "running");
    assert.equal((await pendingPress).error, terminalError);
    await drainTasks();
    await drainTasks();
    assert.equal(f.session.diagnostics().state, "failed", "release refusal cannot strand running/closing state");
    assert.equal(f.session.diagnostics().error_code, code);
    assert.deepEqual(f.session.diagnostics().error_details, terminalError.details);
    assert.equal(failedObservations.length, 1);
    assert.equal(failedObservations[0].event.errorCode, code);
    assert.deepEqual(failedObservations[0].event.errorDetails, terminalError.details);
    const releases = cleanupAttempts.filter((e) => e.operation === "pattern.transport.input.request");
    assert.deepEqual(releases.map((e) => e.payload.held_press_sequence), ["1", "2"],
      "each retained physical owner received its own real correlated release attempt");
    assert.deepEqual(releases.map((e) => e.payload.input_serial), ["3", "3"],
      "known admission rejection did not spend a new ticket identity");
    assert.deepEqual(failedObservations[0].operations.filter((operation) => operation !== "pattern.transport.input.inspect"),
      ["pattern.transport.input.request", "pattern.transport.input.request", "sample.preview.clear", "sample.stop"],
      "preview clear and best-effort Stop were attempted before the failed state was observable");
    assert.deepEqual(terminalAttempts, [{unconsumed: ["2"], physical: ["1", "2"]}]);
    assert.equal(f.terminated(), 1, "terminal cleanup was attempted, never acknowledged as successful");
    assert.equal(await f.session.close(), false);
    assert.equal(await f.session.trigger(2, 100, "pointer"), false);
    await assert.rejects(f.session.release(0, "pointer"), (error) => error === terminalError);
    assert.equal(cleanupAttempts.at(-1).payload.held_press_sequence, "1",
      "the first physical owner remains correlated after terminal cleanup refusal");
    await assert.rejects(f.session.release(1, "keyboard"), (error) => error === terminalError);
    assert.equal(cleanupAttempts.at(-1).payload.held_press_sequence, "2");
    assert.deepEqual([...f.entries.values()], originalInputs, "neither input evidence nor error was rewritten");
    assert.deepEqual([...consumed], ["1"], "the failed incomplete ticket was never forged as consumed");
    assert.deepEqual([...physicalOwners.keys()], ["1", "2"], "no rejected release or terminal ACK cleared physical debts");
    assert.equal(f.session.diagnostics().error_code, code);
  });
}

test("a queued fatal cleanup release spends its own original deadline without replacing the fatal error", async () => {
  let clock = 0;
  let blockInspection = false;
  let failed = false;
  let releaseInspection;
  let inspectionStarted;
  const gate = new Promise((resolve) => { releaseInspection = resolve; });
  const started = new Promise((resolve) => { inspectionStarted = resolve; });
  const originalError = Object.assign(new Error("original fatal observation"), {
    code: "HOST_PROTOCOL_MISMATCH", details: {resource: "pattern_input", terminal_state: "failed"},
  });
  const cleanupError = Object.assign(new Error("cleanup is not physically ready"), {code: "HOST_STATE_INVALID"});
  let terminalRefusals = 0;
  const f = inputProfileFixture({now: () => clock, extraSend: (e) => {
    if (blockInspection && e.operation === "provider.list") {
      inspectionStarted();
      return gate.then(() => success(e, {providers: [], granted_permissions: [], project_revision: null}));
    }
    if (failed && ["pattern.transport.input.request", "sample.preview.clear", "sample.stop"].includes(e.operation))
      throw cleanupError;
    return null;
  }, runtimeTerminator: async () => {
    terminalRefusals += 1;
    throw cleanupError;
  }});
  await activateInputProfile(f);
  await f.session.setSamplePreview(0, PLAYBACK);
  assert.equal((await f.session.trigger(0, 100, "pointer")).sequence, 1);
  blockInspection = true;
  const inspection = f.session.listProviders();
  await started;
  const beforeFailure = f.sent.length;
  failed = true;
  f.emitTransportFailure(originalError);
  await drainTasks();
  assert.equal(f.sent.length, beforeFailure, "the correlated cleanup release waited on the real Host tail");
  clock = 1001;
  releaseInspection();
  assert.deepEqual((await inspection).providers, [], "the independent Host inventory actually finished");
  await drainTasks();
  await drainTasks();
  assert.equal(f.session.diagnostics().state, "failed");
  assert.equal(f.session.diagnostics().error_code, originalError.code);
  assert.deepEqual(f.session.diagnostics().error_details, originalError.details);
  assert.deepEqual(f.sent.slice(beforeFailure).map((e) => e.operation), ["sample.preview.clear", "sample.stop"],
    "expired cleanup release was never dispatched, but the remaining safety attempts still ran");
  assert.equal(f.entries.size, 1, "expiry forged no unknown input ticket");
  assert.equal(terminalRefusals, 1, "terminal cleanup refused outstanding physical ownership");
  assert.equal(await f.session.close(), false);
  await assert.rejects(f.session.release(0, "pointer"), (error) => error === cleanupError);
  const retainedRelease = f.sent.at(-1);
  assert.equal(retainedRelease.operation, "pattern.transport.input.request");
  assert.equal(retainedRelease.payload.input_serial, "2", "pre-dispatch expiry preserved the real release identity");
  assert.equal(retainedRelease.payload.held_press_sequence, "1", "the original physical owner remained serviceable");
  assert.equal(f.sent.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume).length, 1,
    "only the already total press was consumed, never a fabricated release");
  assert.equal(f.session.diagnostics().error_code, originalError.code);
});

test("valid unknown companion capability keeps legacy Pads usable on a two-output SDK", async () => {
  const f = inputProfileFixture({extraSend: (e) => {
    if (e.operation === "pattern.transport.count-in.capabilities") return {
      protocol_version: 1, request_id: e.request_id, ok: false,
      error: {code: "HOST_PROTOCOL_MISMATCH", message: "host protocol request is invalid", details: {}},
    };
    if (e.operation === "trigger") return success(e, e.payload.kind === "release"
      ? {accepted: true} : {sequence: 1, status: "enqueued"});
    return null;
  }});
  await activateInputProfile(f);
  assert.deepEqual(await f.session.trigger(0, 100, "pointer"), {sequence: 1, slot: 0, velocity: 100, source: "pointer"});
  assert.equal(await f.session.release(0, "pointer"), true);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), {code: "UNSUPPORTED_AUDIO"});
  await assert.rejects(f.session.requestPatternInput({commandId: TRANSPORT_COMMAND_ID,
    runtimeGeneration: "1", frameEpoch: "1", inputSerial: "1", slot: 0, velocity: 1,
    kind: "press", held: false, heldPressSequence: null}), {code: "UNSUPPORTED_AUDIO"});
  assert.equal(f.sent.filter((e) => ["pattern.transport.count-in.request", "pattern.transport.input.request"].includes(e.operation)).length, 0);
  assert.equal(f.sent.filter((e) => e.operation === "trigger").length, 2);
  await f.session.close();
});

test("SDK serial exhaustion preserves an existing physical Release without spending refused identities", async () => {
  const f = inputProfileFixture();
  await activateInputProfile(f);
  assert.equal((await f.session.trigger(0, 100, "pointer")).sequence, 1);
  const manual = await f.session.requestPatternInput({commandId: TRANSPORT_COMMAND_ID,
    runtimeGeneration: "1", frameEpoch: "1", inputSerial: "18446744073709551613", slot: 2, velocity: 1,
    kind: "press", held: false, heldPressSequence: null});
  await f.session.inspectPatternInput(manual.ticket, true);
  const before = f.sent.filter((e) => e.operation === "pattern.transport.input.request").length;
  await assert.rejects(f.session.trigger(1, 100, "pointer"), {code: "HOST_STATE_INVALID"});
  await assert.rejects(f.session.trigger(1, 100, "pointer"), {code: "HOST_STATE_INVALID"});
  assert.equal(f.sent.filter((e) => e.operation === "pattern.transport.input.request").length, before);
  assert.equal(await f.session.release(0, "pointer"), true);
  const release = f.sent.filter((e) => e.operation === "pattern.transport.input.request").at(-1);
  assert.equal(release.payload.input_serial, "18446744073709551614");
  assert.equal(release.payload.held_press_sequence, "1");
  await f.session.close();
});

test("total Native dispositions cannot relabel a press as release or a release as a voice", async () => {
  const f = inputProfileFixture();
  await activateInputProfile(f);
  const admitted = await f.session.requestPatternInput({commandId: TRANSPORT_COMMAND_ID,
    runtimeGeneration: "1", frameEpoch: "1", inputSerial: "1", slot: 0, velocity: 1,
    kind: "press", held: false, heldPressSequence: null});
  const native = f.entries.get("1").status.native_result;
  native.disposition = "release_no_voice";
  await assert.rejects(f.session.inspectPatternInput(admitted.ticket), {code: "HOST_PROTOCOL_MISMATCH"});
  native.disposition = "voice_started";
  native.held_press_sequence = "1";
  await assert.rejects(f.session.inspectPatternInput(admitted.ticket), {code: "HOST_PROTOCOL_MISMATCH"});
  await f.session.close();
});

// Witnesses for the independent sealed transport/owner lane. The
// Host seam admits once, keeps exact identities, and refuses consumer ACKs
// until its own input, physical-owner and original count evidence gates pass.
function retainedConsumerFixture({countMode = "accepted", retainedAvailable = true, loseInputAdmission = false,
  terminate, beforeAdmission, admissionReply, beforeInputInspect, beforeInputAdmission, inputReply,
  inputDisposition = () => null, browserWindow = {}, browserDocument = {}, retainLifecycleUntilInputConsumed = false} = {}) {
  let clock = 0;
  let timerId = 0;
  let failureListener = null;
  let sealed = false;
  let terminalOwnerReleased = false;
  let terminalOwnerEnded = false;
  let resolveTerminalOwnerRelease;
  const terminalOwnerRelease = new Promise((resolve) => { resolveTerminalOwnerRelease = resolve; });
  const pendingTimers = new Map();
  let timerSchedulingCancelled = false;
  const normal = [];
  const retained = [];
  const inputEntries = new Map();
  const physicalOwners = new Map();
  const inputConsumed = new Set();
  const nodes = [];
  const originalError = Object.assign(new Error("original count/input response loss"), {
    code: "HOST_TIMEOUT", details: {pending: true, resource: "pattern_input", terminal_state: "sealed"},
  });
  const state = {retainedAvailable, inputComplete: false, nativeOwnerAcknowledged: false,
    countAccepted: false, countConsumed: false, countStatus: countInWireStatus(), countConsumes: 0,
    countInspects: 0, terminalStarts: 0, corruptConsume: false, zeroTimersServiced: 0, backendCloses: 0,
    lifecyclePending: [], lifecycleCompleted: []};
  state.completeInput = () => state.inputComplete;
  const reject = (e, code = "HOST_STATE_INVALID", details = {pending: true}) => ({
    protocol_version: 1, request_id: e.request_id, ok: false,
    error: {code, message: "real retained owner remains pending", details},
  });
  const sameCountTicket = (payload) => Object.entries(countInWireTicket())
    .every(([key, value]) => payload[key] === value);
  const admission = (e, result) => {
    const response = success(e, result);
    return admissionReply?.(e, response) ?? response;
  };
  const assertNoTerminalDebt = () => {
    assert.equal(physicalOwners.size, 0);
    assert.equal([...inputEntries.keys()].some((key) => !inputConsumed.has(key)), false);
    assert.equal(state.countAccepted && !state.countConsumed, false, "NativeStop cannot consume the count caller ticket");
  };
  const resolveLifecycleContinuations = () => {
    if (physicalOwners.size === 0 && [...inputEntries.keys()].every((key) => inputConsumed.has(key)) &&
        !(state.countAccepted && !state.countConsumed)) {
      for (const continuation of state.lifecyclePending.splice(0)) continuation.resolve();
    }
  };
  const releaseTerminalOwner = () => {
    assert.equal(state.nativeOwnerAcknowledged, true, "the real backend independently acknowledged retirement");
    assertNoTerminalDebt();
    terminalOwnerReleased = true;
    resolveTerminalOwnerRelease();
  };
  const host = async (e, options, retainedLane) => {
    assert.equal(options.deadlineMs > 0 && options.deadlineMs <= 1000, true,
      "each retained/ordinary short RPC keeps the original short deadline");
    const p = e.payload;
    if (retainedLane) assert.equal([
      "pattern.transport.input.inspect", "pattern.transport.count-in.inspect",
      "pattern.transport.count-in.cancel", "pattern.transport.inspect",
    ].includes(e.operation) || (e.operation === "pattern.transport.input.request" && p.kind === "release"), true);
    if (e.operation === "pattern.transport.count-in.request") {
      beforeAdmission?.(e);
      assert.equal(retainedLane, false, "a retained lane can never admit or replay count-in");
      assert.equal(normal.filter((entry) => entry.operation === e.operation).length, 1,
        "there is exactly one original Native count-in submission");
      if (countMode === "pre-refusal") return reject(e, "HOST_TIMEOUT", {pending: false});
      state.countAccepted = countMode !== "unknown-unaccepted";
      if (countMode !== "accepted") {
        sealed = true;
        failureListener?.(originalError);
        throw originalError;
      }
      return admission(e, {submit: "accepted", ticket: countInWireTicket(), status: state.countStatus});
    }
    if (e.operation === "pattern.transport.count-in.inspect") {
      assert.equal(sameCountTicket(p), true, "inspect/consume owns the exact original scheduled ticket");
      state.countInspects += 1;
      if (!state.countAccepted || state.countConsumed) return reject(e);
      if (p.consume) {
        state.countConsumes += 1;
        if (!state.countStatus.start_receipt || !state.countStatus.cancel_receipt ||
            state.countStatus.opening_pending || !state.nativeOwnerAcknowledged || physicalOwners.size ||
            [...inputEntries.keys()].some((key) => !inputConsumed.has(key))) return reject(e);
        state.countConsumed = true;
        resolveLifecycleContinuations();
      }
      return success(e, state.corruptConsume && p.consume
        ? {...state.countStatus, start_receipt: {...state.countStatus.start_receipt, frame_epoch: "2"}}
        : state.countStatus);
    }
    if (e.operation === "pattern.transport.count-in.cancel") {
      assert.equal(p.start_command_id, countInWireTicket().command_id);
      assert.equal(sameCountTicket({...p, command_id: p.start_command_id}), true);
      assert.equal(p.project_id, TRANSPORT_PROJECT_ID);
      if (!state.countAccepted || state.countConsumed) return reject(e, "HOST_STATE_INVALID", {pending: false});
      return success(e, {submit: "accepted", ticket: countInWireTicket(), status: state.countStatus});
    }
    if (e.operation === "pattern.transport.input.request") {
      beforeAdmission?.(e);
      const refusal = beforeInputAdmission?.(e);
      if (refusal !== undefined) return refusal;
      if (p.kind === "release") {
        const owner = physicalOwners.get(p.held_press_sequence);
        assert.ok(owner, "release targets a still-retained original physical press");
        assert.equal(p.slot, owner.slot);
        assert.equal(p.runtime_generation, owner.runtime_generation);
        assert.equal(p.frame_epoch, owner.frame_epoch);
      } else assert.equal(retainedLane, false, "no new press enters the sealed lane");
      assert.equal(inputEntries.has(p.input_serial), false, "no original input is re-enqueued");
      const status = inputWireStatus(p, p.input_serial, state.completeInput(p), inputDisposition(p));
      inputEntries.set(p.input_serial, {payload: {...p}, status});
      if (p.kind === "press" && p.held) physicalOwners.set(status.admission.sequence, {...p});
      if (loseInputAdmission && p.kind === "press") {
        sealed = true;
        failureListener?.(originalError);
        throw originalError;
      }
      return admission(e, {ticket: status.ticket, status});
    }
    if (e.operation === "pattern.transport.input.inspect") {
      await beforeInputInspect?.(e, retainedLane);
      const entry = inputEntries.get(p.ticket);
      assert.ok(entry, "there must be an actual original input admission");
      assert.equal(p.command_id, entry.status.ticket.command_id);
      assert.equal(p.runtime_generation, entry.status.ticket.runtime_generation);
      assert.equal(p.frame_epoch, entry.status.ticket.frame_epoch);
      const status = {...entry.status, complete: state.completeInput(entry.payload),
        durable_settled: state.completeInput(entry.payload)};
      if (p.consume) {
        assert.equal(status.complete, true, "only total Native plus durable input evidence is consumed");
        assert.equal(inputConsumed.has(p.ticket), false, "an original input is consumed exactly once");
        inputConsumed.add(p.ticket);
        if (entry.payload.kind === "release" &&
            ["release_applied", "release_no_voice"].includes(status.native_result.disposition))
          physicalOwners.delete(entry.payload.held_press_sequence);
        resolveLifecycleContinuations();
      }
      const response = success(e, status);
      return inputReply?.(e, response) ?? response;
    }
    if (e.operation === "pattern.transport.inspect") return success(e, transportStatus({phase: "idle"}));
    assert.equal(retainedLane, false, "ordinary operations never borrow a retained capability");
    return success(e, defaultResult(e.operation));
  };
  const transport = {
    async send(e, options) {
      normal.push(e);
      if (sealed) throw originalError;
      if (e.operation === "pattern.transport.count-in.capabilities") return success(e, {
        supported: true, negotiated: true, output_ready: true,
        runtime_generation: countInWireTicket().runtime_generation,
        frame_epoch: countInWireTicket().frame_epoch, next_serial: countInWireTicket().schedule_serial,
        input_capacity: 16,
      });
      if (retainLifecycleUntilInputConsumed && ["host.close", "audio.suspend"].includes(e.operation)) {
        // Model the production Bridge continuation: the lifecycle RPC keeps
        // its original response pending while the Host still owns an input
        // caller ticket. It never substitutes Stop for the actual consume.
        const startedAt = clock;
        const tickets = [...inputEntries.keys()].filter((key) => !inputConsumed.has(key));
        const countPending = state.countAccepted && !state.countConsumed;
        if (tickets.length !== 0 || countPending) await new Promise((resolve) => {
          state.lifecyclePending.push({operation: e.operation, tickets, countPending, resolve});
        });
        assert.equal(clock - startedAt < options.deadlineMs, true,
          "the lifecycle response still fits its unchanged original deadline");
        assertNoTerminalDebt();
        state.lifecycleCompleted.push({operation: e.operation, consumed: [...inputConsumed]});
        return success(e, defaultResult(e.operation));
      }
      // Non-short bootstrap/project operations use the existing fixture.
      if (!["pattern.transport.count-in.request", "pattern.transport.count-in.inspect",
        "pattern.transport.count-in.cancel",
        "pattern.transport.input.request", "pattern.transport.input.inspect", "pattern.transport.inspect"].includes(e.operation))
        return success(e, defaultResult(e.operation));
      return host(e, options, false);
    },
    get sendRetained() {
      if (!state.retainedAvailable) return undefined;
      return async (e, options) => {
        assert.equal(sealed, true, "only the sealed real lane uses sendRetained");
        retained.push(e);
        return host(e, options, true);
      };
    },
    get terminated() { return sealed; },
    get terminalOwnerReleased() { return terminalOwnerReleased; },
    get terminalOwnerEnded() { return terminalOwnerEnded; },
    subscribe() { return () => {}; },
    subscribeFailure(listener) { failureListener = listener; return () => { failureListener = null; }; },
  };
  let handle = 10;
  const f = fixture({patternTransport: true, browserWindow, browserDocument, sessionTransport: transport, now: () => clock,
    timers: {
      setTimeout(callback, ms) {
        const id = ++timerId;
        if (timerSchedulingCancelled) return id;
        const timer = {callback, at: clock + ms, realHandle: null};
        pendingTimers.set(id, timer);
        // Device resume polling must observe the real Promise outcome before
        // activation can return. Service zero turns without moving this clock.
        if (ms === 0) timer.realHandle = globalThis.setTimeout(() => {
          if (!pendingTimers.delete(id)) return;
          state.zeroTimersServiced += 1;
          callback();
        }, 0);
        return id;
      },
      clearTimeout(id) {
        const timer = pendingTimers.get(id);
        if (timer?.realHandle !== null && timer?.realHandle !== undefined) globalThis.clearTimeout(timer.realHandle);
        pendingTimers.delete(id);
      },
    },
    registerAudioNode: (node) => { nodes.push(node); return ++handle; },
    startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
    runtimeTerminator: async (...arguments_) => {
      state.terminalStarts += 1;
      if (terminate !== undefined) { await terminate(...arguments_); return; }
      if (!sealed && f.session.diagnostics().error_code === null) {
        // The scripted normal backend retires only an empty owner. This is a
        // separate full receipt, never a Stop, count result or mock resolution.
        assertNoTerminalDebt();
        sealed = true;
        failureListener?.(deliberateTerminationSeal());
        if (!terminalOwnerReleased) {
          state.nativeOwnerAcknowledged = true;
          releaseTerminalOwner();
        }
      } else sealed = true;
      await terminalOwnerRelease;
      const {audioContext} = arguments_[0];
      await audioContext.close();
      assert.equal(audioContext.state, "closed", "a full owner receipt cannot manufacture backend closure");
    },
  });
  f.context.close = async () => {
    assert.equal(terminalOwnerReleased, true, "backend close waits for the independent full owner receipt");
    state.backendCloses += 1;
    f.context.state = "closed";
  };
  return {...f, state, normal, retained, transport, originalError, inputEntries, inputConsumed, physicalOwners, nodes,
    clockMilliseconds: () => clock,
    advanceClock(ms) { clock += ms; }, // Do not dispatch timers: models a delayed timer task.
    seal(error = originalError) { sealed = true; failureListener?.(error); },
    releaseTerminal: releaseTerminalOwner,
    // Models the Host ending an owner by force: no release receipt exists.
    endTerminalOwnerByForce() { terminalOwnerEnded = true; },
    cancelTimers() {
      // Test-resource disposal only. Do not resolve a retained RPC, invoke
      // its callback, consume a caller ticket or retire a physical owner.
      timerSchedulingCancelled = true;
      for (const timer of pendingTimers.values()) {
        if (timer.realHandle !== null) globalThis.clearTimeout(timer.realHandle);
      }
      pendingTimers.clear();
    },
    async tick(ms = 5) {
      clock += ms;
      for (const [id, timer] of [...pendingTimers]) if (timer.at <= clock) {
        pendingTimers.delete(id);
        if (timer.realHandle !== null) globalThis.clearTimeout(timer.realHandle);
        timer.callback();
      }
      await drainTasks();
      await drainTasks();
    },
  };
}

function failedOriginalCountInEvidence() {
  const {session_id: _session, command_id: _command, ...identity} = countInWireTicket();
  const start = {...identity, transport_epoch: "1", pattern_generation: "7",
    pattern_id: TRANSPORT_PATTERN_ID, result: "refused", effective_frame: null, origin_frame: null, playing: false};
  return countInWireStatus({count_in: {...countInWireStatus().count_in, phase: "refused"},
    start_receipt: start, cancel_receipt: {...start, transport_epoch: "2"},
    error: {code: "IO_ERROR", message: "original owner failure", details: {resource: "journal"}}});
}

function expiredOpeningCountInEvidence(pending = true) {
  const {session_id: _session, command_id: _command, ...identity} = countInWireTicket();
  const start = {...identity, transport_epoch: "1", pattern_generation: "7",
    pattern_id: TRANSPORT_PATTERN_ID, result: "applied", effective_frame: 192_000,
    origin_frame: 192_000, playing: true};
  return countInWireStatus({count_in: {...identity, phase: "applied", bars: 2, bpm: 120,
    bar_frames: 96_000, count_in_frame: 0, start_frame: start.effective_frame},
    start_receipt: start, cancel_receipt: {...start, transport_epoch: "2",
      effective_frame: 192_001, playing: false}, opening_pending: pending,
    // These safe messages and exact reasons require the count-in Host's
    // narrow error projection; a generic redacted details={} is insufficient.
    error: pending
      ? {code: "IO_ERROR", message: "project storage operation failed",
          details: {reason: "pattern_transport_opening_expired"}}
      : {code: "INVALID_ARGUMENT", message: "request is invalid",
          details: {reason: "admission_opening_deadline_elapsed", journal_retained: true}}});
}

async function tickRetainedUntil(f, predicate) {
  for (let step = 0; step < 40 && !predicate(); ++step) await f.tick();
  assert.equal(predicate(), true);
}

async function settleRetainedCall(f, promise) {
  let outcome = null;
  void promise.then(
    (value) => { outcome = {ok: true, value}; },
    (error) => { outcome = {ok: false, error}; });
  // Observe a bounded number of existing fixture turns. A queue cycle must
  // fail this test naturally; it must not wedge the module awaiting an RPC
  // whose response is deliberately retained. This neither changes the RPC's
  // deadline nor resolves it on behalf of its original owner.
  await tickRetainedUntil(f, () => outcome !== null);
  if (!outcome.ok) throw outcome.error;
  return outcome.value;
}

for (const operation of ["host.close", "audio.suspend"]) {
  for (const expireObserver of [false, true]) {
    test(`retained ${operation} consumes the original Release ${expireObserver ? "after observer expiry" : "within its observer budget"}`, async (t) => {
      const f = retainedConsumerFixture({retainLifecycleUntilInputConsumed: true});
      t.after(() => f.cancelTimers());
      await activateInputProfile(f);
      // The press is genuinely admitted and consumed first. Its physical
      // owner remains held; only its exact correlated Release may
      // remove it. Leave that Release's durable completion unresolved.
      f.state.completeInput = (payload) => payload.kind === "press" || f.state.inputComplete;
      assert.deepEqual(await f.session.trigger(0, 100, "pointer"),
        {sequence: 1, slot: 0, velocity: 100, source: "pointer"});
      assert.deepEqual([...f.inputConsumed], ["1"]);
      assert.equal(f.physicalOwners.size, 1);
      let originalRelease = null;
      if (expireObserver) {
        originalRelease = f.session.release(0, "pointer").then(
          (value) => ({value}), (error) => ({error}));
        await tickRetainedUntil(f, () => f.inputEntries.has("2"));
        // Spend the original input observer's time before lifecycle dispatch,
        // so its expiry remains inside audio.suspend's own original budget.
        await f.tick(750);
      }
      let lifecycleResult = null;
      const lifecycle = (operation === "host.close" ? f.session.close() : f.session.suspendAudio())
        .then((value) => { lifecycleResult = value; return value; });
      await tickRetainedUntil(f, () => f.state.lifecyclePending.length === 1);
      assert.deepEqual(f.state.lifecyclePending[0].tickets, ["2"]);
      assert.equal(f.state.lifecyclePending[0].operation, operation);
      const release = f.inputEntries.get("2");
      assert.equal(release.payload.kind, "release");
      assert.equal(release.payload.held_press_sequence, "1");
      assert.equal(release.payload.slot, 0);
      assert.equal(lifecycleResult, null, "admission and Stop do not finish the retained lifecycle RPC");
      assert.equal(f.state.backendCloses, 0);

      let ordinaryQuery = null;
      if (operation === "audio.suspend") {
        ordinaryQuery = f.session.inspectProject();
        await drainTasks();
        assert.equal(f.normal.some((e) => e.operation === "project.inspect"), false,
          "an ordinary query still waits behind the lifecycle RPC");
      }
      if (expireObserver) {
        await f.tick(250);
        const originalOutcome = await originalRelease;
        assert.equal(originalOutcome.error?.code, "HOST_TIMEOUT");
        assert.equal(originalOutcome.error.details.pending, true);
      }
      assert.equal(f.physicalOwners.size, 1, "observer time cannot release the held physical owner");
      assert.deepEqual([...f.inputConsumed], ["1"], "pending durability cannot pay caller debt");
      assert.equal(lifecycleResult, null);

      f.state.inputComplete = true;
      await tickRetainedUntil(f, () => f.inputConsumed.has("2"));
      assert.equal(await settleRetainedCall(f, lifecycle), true);
      if (ordinaryQuery !== null) assert.deepEqual(await settleRetainedCall(f, ordinaryQuery), {});
      assert.equal(f.state.lifecyclePending.length, 0);
      assert.deepEqual(f.state.lifecycleCompleted[0], {operation, consumed: ["1", "2"]});
      assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.request")
        .map((e) => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
        [["press", "1", null], ["release", "2", "1"]]);
      assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
        .map((e) => e.payload.ticket), ["1", "2"]);
      assert.equal(f.physicalOwners.size, 0);
      assert.equal(f.retained.length, 0, "a healthy continuation keeps ordinary transport.send");
      if (operation === "audio.suspend") {
        assert.equal(f.session.diagnostics().state, "audio-suspended");
        assert.equal(f.context.state, "suspended");
        assert.equal(f.state.backendCloses, 0);
        assert.equal(await settleRetainedCall(f, f.session.close()), true);
      }
      assert.equal(f.state.backendCloses, 1);
    });
  }
}

for (const operation of ["host.close", "audio.suspend"]) {
  test(`retained ${operation} releases every same-slot/source physical hold by its exact sequence`, async (t) => {
    const f = retainedConsumerFixture({retainLifecycleUntilInputConsumed: true});
    t.after(() => f.cancelTimers());
    await activateInputProfile(f);
    f.state.completeInput = (payload) => payload.kind === "press" || f.state.inputComplete;
    for (const sequence of [1, 2]) {
      assert.deepEqual(await f.session.trigger(0, 100, "keyboard"),
        {sequence, slot: 0, velocity: 100, source: "keyboard"});
    }
    assert.deepEqual([...f.inputConsumed], ["1", "2"]);
    assert.deepEqual([...f.physicalOwners.keys()], ["1", "2"],
      "consuming both press results leaves both real physical owners held");
    let lifecycleResult = null;
    const lifecycle = (operation === "host.close" ? f.session.close() : f.session.suspendAudio())
      .then((value) => { lifecycleResult = value; return value; });
    await tickRetainedUntil(f, () => f.state.lifecyclePending.length === 1);
    assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.request")
      .map((e) => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
      [["press", "1", null], ["press", "2", null], ["release", "3", "1"], ["release", "4", "2"]]);
    assert.deepEqual(f.state.lifecyclePending[0].tickets, ["3", "4"]);
    assert.equal(lifecycleResult, null, "real release admission does not consume either caller ticket");
    assert.deepEqual([...f.inputConsumed], ["1", "2"]);
    assert.deepEqual([...f.physicalOwners.keys()], ["1", "2"]);
    assert.equal(f.state.backendCloses, 0);
    f.state.inputComplete = true;
    await tickRetainedUntil(f, () => f.inputConsumed.has("3") && f.inputConsumed.has("4"));
    assert.equal(await settleRetainedCall(f, lifecycle), true);
    assert.equal(f.physicalOwners.size, 0);
    assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
      .map((e) => e.payload.ticket), ["1", "2", "3", "4"]);
    assert.equal(f.retained.length, 0);
    if (operation === "audio.suspend") {
      assert.equal(f.session.diagnostics().state, "audio-suspended");
      assert.equal(f.context.state, "suspended");
      assert.equal(await settleRetainedCall(f, f.session.close()), true);
    }
    assert.equal(f.state.backendCloses, 1);
  });
}

for (const operation of ["host.close", "audio.suspend"]) {
  test(`known count-in consumption stays independent of retained ${operation}`, async (t) => {
    const f = retainedConsumerFixture({retainLifecycleUntilInputConsumed: true});
    t.after(() => f.cancelTimers());
    await activateInputProfile(f);
    const admission = await f.session.requestPatternCountIn(countInRequest());
    let lifecycleResult = null;
    const lifecycle = (operation === "host.close" ? f.session.close() : f.session.suspendAudio())
      .then((value) => { lifecycleResult = value; return value; });
    await tickRetainedUntil(f, () => f.state.lifecyclePending.length === 1);
    assert.equal(f.state.lifecyclePending[0].countPending, true);
    assert.deepEqual(f.state.lifecyclePending[0].tickets, []);
    assert.equal(lifecycleResult, null);
    assert.equal(f.state.countConsumed, false, "the lifecycle Stop cannot consume its original count caller");

    let ordinaryStop = null;
    if (operation === "audio.suspend") {
      const priorStops = f.normal.filter((e) => e.operation === "sample.stop").length;
      ordinaryStop = f.session.stopAll();
      await drainTasks();
      assert.equal(f.normal.filter((e) => e.operation === "sample.stop").length, priorStops,
        "an ordinary Runtime action still waits for the retained lifecycle RPC");
    }
    const pending = await settleRetainedCall(f, f.session.inspectPatternCountIn(admission.ticket));
    assert.equal(pending.startReceipt, null);
    assert.equal(f.state.countConsumes, 0);
    assert.equal(lifecycleResult, null);

    // The Host seam separately publishes its original applied S and Stop F,
    // with the opened recording fully settled. The SDK neither creates that
    // evidence nor turns it into the independent physical-owner ACK.
    const final = expiredOpeningCountInEvidence(false);
    final.error = null;
    final.opening_complete = true;
    f.state.countStatus = final;
    const terminal = await settleRetainedCall(f, f.session.inspectPatternCountIn(admission.ticket));
    assert.equal(terminal.startReceipt.result, "applied");
    assert.equal(terminal.cancelReceipt.result, "applied");
    assert.equal(terminal.cancelReceipt.playing, false);
    assert.equal(terminal.openingComplete, true);
    await settleRetainedCall(f,
      assert.rejects(f.session.inspectPatternCountIn(admission.ticket, true), {code: "HOST_STATE_INVALID"}));
    assert.equal(f.state.countConsumed, false, "terminal-looking evidence alone never pays caller debt");
    assert.equal(lifecycleResult, null);
    assert.equal(f.state.backendCloses, 0);

    f.state.nativeOwnerAcknowledged = true;
    const consumed = await settleRetainedCall(f, f.session.inspectPatternCountIn(admission.ticket, true));
    assert.deepEqual(consumed.startReceipt, terminal.startReceipt);
    assert.deepEqual(consumed.cancelReceipt, terminal.cancelReceipt);
    assert.equal(f.state.countConsumed, true);
    assert.equal(await settleRetainedCall(f, lifecycle), true);
    if (ordinaryStop !== null) assert.equal(await settleRetainedCall(f, ordinaryStop), true);
    assert.equal(f.state.lifecyclePending.length, 0);
    assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.count-in.request").length, 1);
    assert.equal(f.normal.some((e) => e.operation === "pattern.transport.count-in.cancel"), false);
    assert.equal(f.retained.length, 0, "healthy original callers use ordinary transport.send");
    if (operation === "audio.suspend") {
      assert.equal(f.session.diagnostics().state, "audio-suspended");
      assert.equal(f.context.state, "suspended");
      assert.equal(await settleRetainedCall(f, f.session.close()), true);
    }
    assert.equal(f.state.backendCloses, 1);
  });
}

test("a forced terminal end stops retained consumer polling without claiming release", async (t) => {
  const f = retainedConsumerFixture({countMode: "accepted-response-loss"});
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  await tickRetainedUntil(f, () => f.state.countInspects > 0 && f.state.terminalStarts === 1);
  f.endTerminalOwnerByForce();
  await f.tick();
  await f.tick();
  const settled = f.retained.length;
  for (let step = 0; step < 20; ++step) await f.tick();
  assert.equal(f.retained.length, settled, "an ended owner cannot be polled again");
  assert.equal(f.transport.terminalOwnerReleased, false, "a forced end is not a release receipt");
  assert.equal(f.state.countConsumed, false, "a forced end consumes no caller ticket");
});

test("accepted count-in response loss keeps original failure and exact final caller consumption", async () => {
  const f = retainedConsumerFixture({countMode: "accepted-response-loss"});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  await tickRetainedUntil(f, () => f.state.countInspects > 0 && f.state.terminalStarts === 1);
  assert.equal(f.state.countConsumes, 0, "pending evidence cannot pay caller debt");
  assert.equal(f.state.countAccepted, true);
  assert.equal(f.session.diagnostics().state, "restart-required");
  const final = failedOriginalCountInEvidence();
  f.state.countStatus = final;
  await f.tick();
  assert.equal(f.state.countConsumed, false, "valid final evidence cannot replace the independent physical ACK");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0), "mock terminator resolution did not detach output");
  f.state.nativeOwnerAcknowledged = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  const consumed = f.retained.filter((e) => e.operation === "pattern.transport.count-in.inspect" && e.payload.consume);
  assert.ok(consumed.length >= 1);
  assert.ok(consumed.every((e) => e.payload.command_id === countInWireTicket().command_id));
  const before = f.retained.length;
  const retainedFinal = await f.session.inspectPatternCountIn(countInPublicTicket());
  assert.equal(f.retained.length, before, "the frozen final evidence survives exact private consumption locally");
  assert.equal(Object.isFrozen(retainedFinal), true);
  assert.equal(retainedFinal.startReceipt.result, "refused");
  assert.equal(retainedFinal.startReceipt.effectiveFrame, null);
  assert.equal(retainedFinal.cancelReceipt.effectiveFrame, null);
  assert.deepEqual(retainedFinal.error, final.error);
  await assert.rejects(f.session.inspectPatternCountIn(countInPublicTicket(), true), {code: "HOST_STATE_INVALID"});
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.count-in.request").length, 1);
  assert.equal(f.retained.some((e) => e.operation === "pattern.transport.count-in.request"), false);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  f.releaseTerminal();
  await f.tick();
  assert.ok(f.nodes.some((node) => node.disconnected.length > 0), "only the positive full receipt released SDK output");
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
});

test("held input original consumers and physical release remain independent of count caller debt after fatality", async () => {
  const f = retainedConsumerFixture();
  await activateInputProfile(f);
  await f.session.requestPatternCountIn(countInRequest());
  const press = f.session.trigger(0, 100, "pointer").then((value) => ({value}), (error) => ({error}));
  await tickRetainedUntil(f, () => f.inputEntries.size === 1);
  const originalInput = structuredClone(f.inputEntries.get("1"));
  f.state.countStatus = failedOriginalCountInEvidence();
  f.seal();
  assert.equal((await press).error, f.originalError, "the original caller rejects before independent completion");
  await tickRetainedUntil(f, () => f.inputEntries.size === 2 && f.state.terminalStarts === 1);
  assert.equal(f.inputEntries.get("2").payload.held_press_sequence, "1");
  assert.deepEqual(f.inputEntries.get("1"), originalInput, "fatal observation rewrote no original input evidence");
  assert.equal(f.inputConsumed.size, 0);
  assert.equal(f.physicalOwners.size, 1);
  assert.equal(f.state.countConsumed, false);
  assert.equal(await f.session.trigger(1, 100, "pointer"), false, "fatal state admits no new press");
  f.state.inputComplete = true;
  await tickRetainedUntil(f, () => f.inputConsumed.size === 2 && f.physicalOwners.size === 0);
  assert.deepEqual([...f.inputConsumed].sort(), ["1", "2"]);
  assert.equal(f.state.countConsumed, false, "input complete+consume and real release do not stand in for Native owner ACK");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  f.state.nativeOwnerAcknowledged = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  assert.deepEqual(f.retained.filter((e) => e.operation === "pattern.transport.input.request")
    .map((e) => [e.payload.input_serial, e.payload.kind, e.payload.held_press_sequence]), [["2", "release", "1"]]);
  assert.deepEqual(f.retained.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
    .map((e) => e.payload.ticket).sort(), ["1", "2"]);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  f.releaseTerminal();
  await f.tick();
});

test("no optional retained capability preserves genuine unknown owner debt without synthetic consumes", async () => {
  const f = retainedConsumerFixture({countMode: "accepted-response-loss", retainedAvailable: false});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  await f.tick();
  await f.tick();
  assert.equal(f.state.countAccepted, true);
  assert.equal(f.state.countConsumed, false);
  assert.equal(f.state.countInspects, 0);
  assert.equal(f.retained.length, 0);
  assert.equal(f.state.terminalStarts, 1, "a mock terminator's resolved value is no full owner receipt");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  assert.equal(await f.session.close(), false);
  f.state.countStatus = failedOriginalCountInEvidence();
  f.state.nativeOwnerAcknowledged = true;
  f.state.retainedAvailable = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  f.releaseTerminal();
  await f.tick();
});

test("unknown unaccepted count-in requires a positive full terminal receipt without manufacturing acceptance", async () => {
  const f = retainedConsumerFixture({countMode: "unknown-unaccepted"});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  await tickRetainedUntil(f, () => f.state.countInspects >= 2);
  assert.equal(f.state.countAccepted, false);
  assert.equal(f.state.countConsumes, 0, "generic HOST_STATE_INVALID inspection is no accepted status or consumer ACK");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await f.tick();
  const inspections = f.state.countInspects;
  await f.tick();
  assert.equal(f.state.countInspects, inspections, "positive full release ended uncertainty for the original unaccepted identity");
  assert.equal(f.state.countAccepted, false);
  assert.equal(f.state.countConsumed, false);
  assert.equal(f.state.countConsumes, 0);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
});

test("known pending:false count-in refusal retains no synthetic original caller ticket", async () => {
  const f = retainedConsumerFixture({countMode: "pre-refusal"});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()),
    (error) => error.code === "HOST_TIMEOUT" && error.details.pending === false);
  await f.tick();
  assert.equal(f.state.countAccepted, false);
  assert.equal(f.state.countInspects, 0);
  assert.equal(f.state.countConsumes, 0);
  assert.equal(f.retained.length, 0);
  assert.equal(f.session.diagnostics().state, "running");
  await f.session.close();
});

test("healthy known count-in keeps ordinary public inspect and exact explicit consume", async () => {
  const f = retainedConsumerFixture();
  await activateInputProfile(f);
  const admission = await f.session.requestPatternCountIn(countInRequest());
  await f.tick(12_000);
  assert.equal(f.state.countInspects, 0, "known successful admission owns no private healthy consumer");
  assert.equal(f.retained.length, 0);
  assert.equal((await f.session.inspectPatternCountIn(admission.ticket)).startReceipt, null);
  f.state.countStatus = failedOriginalCountInEvidence();
  f.state.nativeOwnerAcknowledged = true;
  const consumed = await f.session.inspectPatternCountIn(admission.ticket, true);
  assert.equal(consumed.error.code, "IO_ERROR");
  assert.equal(f.state.countConsumed, true);
  assert.equal(f.state.countConsumes, 1);
  assert.equal(f.retained.length, 0, "ordinary public consumers retain the normal send lane");
  await f.session.close();
});

for (const stopAlreadyObserved of [true, false]) {
  test(`count-in opening deadline settles the original error with ${stopAlreadyObserved ? "retained" : "new"} Stop F`, async () => {
    const f = retainedConsumerFixture();
    await activateInputProfile(f);
    const admitted = await f.session.requestPatternCountIn(countInRequest());
    f.state.countStatus = expiredOpeningCountInEvidence();
    if (!stopAlreadyObserved) f.state.countStatus.cancel_receipt = null;
    const pending = await f.session.inspectPatternCountIn(admitted.ticket);
    assert.equal(pending.openingPending, true);
    assert.equal(pending.error.details.reason, "pattern_transport_opening_expired");
    await f.tick(12_000);
    assert.equal(f.state.countConsumes, 0, "elapsed observer time does not spend caller debt");
    const final = expiredOpeningCountInEvidence(false);
    f.state.countStatus = final;
    const settled = await f.session.inspectPatternCountIn(admitted.ticket);
    assert.deepEqual(settled.startReceipt, pending.startReceipt);
    if (stopAlreadyObserved) assert.deepEqual(settled.cancelReceipt, pending.cancelReceipt);
    assert.equal(settled.cancelReceipt.result, "applied");
    assert.equal(settled.cancelReceipt.playing, false);
    assert.equal(settled.openingPending, false);
    assert.equal(settled.openingComplete, false);
    assert.deepEqual(settled.error, final.error);
    f.state.nativeOwnerAcknowledged = true;
    const consumed = await f.session.inspectPatternCountIn(admitted.ticket, true);
    assert.deepEqual(consumed.error, final.error);
    assert.deepEqual(consumed.startReceipt, settled.startReceipt);
    assert.deepEqual(consumed.cancelReceipt, settled.cancelReceipt);
    assert.equal(f.state.countConsumes, 1);
    assert.equal(f.state.countConsumed, true);
    assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.count-in.request").length, 1);
    assert.equal(f.normal.some((e) => e.operation === "pattern.transport.count-in.cancel"), false);
    assert.equal(f.retained.length, 0);
    await assert.rejects(f.session.inspectPatternCountIn(admitted.ticket, true), {code: "HOST_STATE_INVALID"});
    await f.session.close();
  });
}

test("count-in opening deadline retains the original observer failure through private final consumption", async () => {
  const f = retainedConsumerFixture({countMode: "accepted-response-loss"});
  await activateInputProfile(f);
  f.state.countStatus = expiredOpeningCountInEvidence();
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  await tickRetainedUntil(f, () => f.state.countInspects > 0 && f.state.terminalStarts === 1);
  const pending = await f.session.inspectPatternCountIn(countInPublicTicket());
  assert.equal(pending.openingPending, true);
  assert.equal(f.state.countConsumes, 0);
  const final = expiredOpeningCountInEvidence(false);
  f.state.countStatus = final;
  await f.tick();
  assert.equal(f.state.countConsumed, false, "final refusal cannot manufacture the independent physical ACK");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  f.state.nativeOwnerAcknowledged = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  const consumed = await f.session.inspectPatternCountIn(countInPublicTicket());
  assert.deepEqual(consumed.startReceipt, pending.startReceipt);
  assert.deepEqual(consumed.cancelReceipt, pending.cancelReceipt);
  assert.deepEqual(consumed.error, final.error);
  assert.equal(consumed.openingComplete, false);
  await assert.rejects(f.session.inspectPatternCountIn(countInPublicTicket(), true), {code: "HOST_STATE_INVALID"});
  assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.count-in.request").length, 1);
  assert.equal(f.retained.some((e) => e.operation === "pattern.transport.count-in.request"), false);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  f.releaseTerminal();
  await f.tick();
  assert.ok(f.nodes.some((node) => node.disconnected.length > 0));
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
});

for (const [name, corrupt] of [
  ["changed e1", (_before, after) => {
    after.start_receipt.effective_frame += 1;
    after.start_receipt.origin_frame += 1;
    after.count_in.count_in_frame += 1;
    after.count_in.start_frame += 1;
    after.cancel_receipt.origin_frame += 1;
    after.cancel_receipt.effective_frame += 1;
  }],
  ["changed F", (_before, after) => { after.cancel_receipt.effective_frame += 1; }],
  ["unobserved original e1", (before) => { before.start_receipt = null; before.cancel_receipt = null; }],
  ["missing Stop F", (before, after) => { before.cancel_receipt = null; after.cancel_receipt = null; }],
  ["refused Stop F", (before, after) => {
    before.cancel_receipt = null;
    Object.assign(after.cancel_receipt, {result: "refused", effective_frame: null, origin_frame: null});
  }],
  ["playing Stop F", (before, after) => { before.cancel_receipt = null; after.cancel_receipt.playing = true; }],
  ["wrong provisional reason", (before) => { before.error.details.reason = "another_pending_error"; }],
  ["wrong provisional code", (before) => { before.error.code = "INVALID_ARGUMENT"; }],
  ["already final provisional error", (before) => { before.opening_pending = false; }],
  ["wrong final reason", (_before, after) => { after.error.details.reason = "another_final_error"; }],
  ["wrong final code", (_before, after) => { after.error.code = "IO_ERROR"; }],
  ["redacted reasons", (before, after) => { before.error.details = {}; after.error.details = {}; }],
  ["retryable final error", (_before, after) => { after.error.details.retryable = true; }],
  ["unresolved final journal", (_before, after) => { after.error.details.closure_unresolved = true; }],
  ["missing final journal retention", (_before, after) => { delete after.error.details.journal_retained; }],
  ["still pending opening", (_before, after) => { after.opening_pending = true; }],
  ["false opening success", (_before, after) => { after.opening_complete = true; }],
  ["cleared pending error", (_before, after) => { after.error = null; }],
]) {
  test(`count-in opening deadline rejects ${name}`, async () => {
    const f = retainedConsumerFixture();
    await activateInputProfile(f);
    const before = expiredOpeningCountInEvidence();
    const after = expiredOpeningCountInEvidence(false);
    corrupt(before, after);
    f.state.countStatus = before;
    const admitted = await f.session.requestPatternCountIn(countInRequest());
    f.state.countStatus = after;
    await assert.rejects(f.session.inspectPatternCountIn(admitted.ticket), {code: "HOST_PROTOCOL_MISMATCH"});
    assert.equal(f.state.countConsumed, false);
    assert.equal(f.state.countConsumes, 0, "rejected inspection cannot spend caller debt");
    // Restore the actual original evidence; an unchanged error may settle as
    // a failure after the real Stop, but may not be replaced by this reply.
    f.state.countStatus = {...before, opening_pending: false,
      start_receipt: before.start_receipt ?? expiredOpeningCountInEvidence().start_receipt,
      cancel_receipt: before.cancel_receipt ?? expiredOpeningCountInEvidence().cancel_receipt};
    f.state.nativeOwnerAcknowledged = true;
    const consumed = await f.session.inspectPatternCountIn(admitted.ticket, true);
    assert.deepEqual(consumed.error, before.error);
    assert.equal(f.state.countConsumes, 1);
    await f.session.close();
  });
}

for (const [name, mutate] of [
  ["cleared final error", (status) => { status.error = null; }],
  ["replaced final error", (status) => { status.error.details.reason = "another_final_error"; }],
  ["reversed provisional error", (status) => {
    status.opening_pending = true;
    status.error = expiredOpeningCountInEvidence().error;
  }],
]) {
  test(`count-in opening deadline rejects ${name} after settlement`, async () => {
    const f = retainedConsumerFixture();
    await activateInputProfile(f);
    f.state.countStatus = expiredOpeningCountInEvidence();
    const admitted = await f.session.requestPatternCountIn(countInRequest());
    const final = expiredOpeningCountInEvidence(false);
    f.state.countStatus = final;
    await f.session.inspectPatternCountIn(admitted.ticket);
    f.state.countStatus = structuredClone(final);
    mutate(f.state.countStatus);
    await assert.rejects(f.session.inspectPatternCountIn(admitted.ticket), {code: "HOST_PROTOCOL_MISMATCH"});
    assert.equal(f.state.countConsumes, 0);
    f.state.countStatus = final;
    f.state.nativeOwnerAcknowledged = true;
    assert.deepEqual((await f.session.inspectPatternCountIn(admitted.ticket, true)).error, final.error);
    assert.equal(f.state.countConsumes, 1);
    await f.session.close();
  });
}

test("retained count consume cannot replace original e1 identity or erase its original failure", async () => {
  const f = retainedConsumerFixture({countMode: "accepted-response-loss"});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  f.state.countStatus = failedOriginalCountInEvidence();
  f.state.nativeOwnerAcknowledged = true;
  f.state.corruptConsume = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  await f.tick();
  const final = await f.session.inspectPatternCountIn(countInPublicTicket()).then(
    (value) => ({value}), (error) => ({error}));
  assert.equal(final.error?.code, "HOST_STATE_INVALID", "corrupt consumer result is never exposed as a local successful final ACK");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0), "a remote consume boolean alone supplies no SDK/physical ACK");
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  f.releaseTerminal();
  await f.tick();
});

test("accepted input response loss preserves its original identity and correlated release on the retained lane", async () => {
  const f = retainedConsumerFixture({loseInputAdmission: true});
  await activateInputProfile(f);
  const press = f.session.trigger(0, 100, "pointer").then((value) => ({value}), (error) => ({error}));
  assert.equal((await press).error, f.originalError);
  await tickRetainedUntil(f, () => f.inputEntries.size === 2);
  const original = f.inputEntries.get("1");
  const release = f.inputEntries.get("2");
  assert.equal(release.payload.held_press_sequence, original.status.admission.sequence);
  assert.equal(release.payload.runtime_generation, original.payload.runtime_generation);
  assert.equal(release.payload.frame_epoch, original.payload.frame_epoch);
  assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.input.request").length, 1);
  assert.equal(f.retained.filter((e) => e.operation === "pattern.transport.input.request").length, 1);
  assert.equal(f.inputConsumed.size, 0);
  f.state.inputComplete = true;
  await tickRetainedUntil(f, () => f.inputConsumed.size === 2);
  assert.deepEqual([...f.inputConsumed].sort(), ["1", "2"]);
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await f.tick();
});

test("real correlated release consumption cannot retire an independently unconsumed press ticket", async () => {
  const f = retainedConsumerFixture();
  await activateInputProfile(f);
  const press = f.session.trigger(0, 100, "pointer").then((value) => ({value}), (error) => ({error}));
  await tickRetainedUntil(f, () => f.inputEntries.size === 1);
  f.seal();
  assert.equal((await press).error, f.originalError);
  await tickRetainedUntil(f, () => f.inputEntries.size === 2);
  f.state.completeInput = (payload) => payload.kind === "release";
  await tickRetainedUntil(f, () => f.inputConsumed.has("2"));
  assert.equal(f.inputConsumed.has("1"), false, "the separate press consumer remains owed after physical release");
  assert.equal(f.physicalOwners.size, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  f.state.completeInput = () => true;
  await tickRetainedUntil(f, () => f.inputConsumed.has("1"));
  assert.deepEqual(f.retained.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
    .map((e) => e.payload.ticket), ["2", "1"], "both original tickets actually reached their own consumer in release-first order");
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await f.tick();
});

test("sealed SDK permits only existing count continuation and blocks foreign inspection and new admission", async () => {
  const f = retainedConsumerFixture();
  await activateInputProfile(f);
  const admission = await f.session.requestPatternCountIn(countInRequest());
  f.seal();
  const foreign = {...admission.ticket, commandId: "00000000-0000-4000-8000-0000000000de"};
  assert.notEqual(foreign.commandId, admission.ticket.commandId);
  await assert.rejects(f.session.inspectPatternCountIn(foreign), (error) => error === f.originalError);
  await assert.rejects(f.session.requestPatternCountIn({...countInRequest(), commandId: foreign.commandId}),
    (error) => error.code === "HOST_STATE_INVALID" && error.details.pending === false);
  await assert.rejects(f.session.requestPatternInput({commandId: foreign.commandId,
    runtimeGeneration: admission.ticket.runtimeGeneration, frameEpoch: admission.ticket.frameEpoch,
    inputSerial: "1", slot: 0, velocity: 100, kind: "press", held: true, heldPressSequence: null}),
    (error) => error.code === "HOST_STATE_INVALID" && error.details.pending === false);
  const cancelled = await f.session.cancelPatternCountIn({ticket: admission.ticket,
    projectId: TRANSPORT_PROJECT_ID, commandId: foreign.commandId, expectedEpoch: "2", intent: "play_stop"});
  assert.equal(cancelled.submit, "accepted");
  assert.equal(cancelled.status.startReceipt, null, "admitted cancellation is no invented terminal evidence");
  assert.equal((await f.session.inspectPatternTransport(TRANSPORT_SESSION_ID)).phase, "idle");
  assert.equal(f.retained.some((e) => e.operation === "pattern.transport.count-in.request" ||
    (e.operation === "pattern.transport.input.request" && e.payload.kind !== "release")), false);
  assert.equal(f.retained.some((e) => e.operation === "pattern.transport.count-in.inspect" &&
    e.payload.command_id === foreign.commandId), false);
  assert.equal(f.inputEntries.size, 0);
  f.state.countStatus = failedOriginalCountInEvidence();
  f.state.nativeOwnerAcknowledged = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  f.releaseTerminal();
  await f.tick();
});

function deliberateTerminationSeal() {
  return Object.assign(new Error("formal Web Host transport is terminated"), {
    code: "HOST_STATE_INVALID", details: Object.freeze({}),
  });
}

test("repeated fatal close without Pattern debt waits the original Native and backend cleanup", async (t) => {
  const f = retainedConsumerFixture();
  t.after(() => f.cancelTimers());
  let releaseBackend;
  const backendPending = new Promise((resolve) => { releaseBackend = resolve; });
  const actualClose = f.context.close.bind(f.context);
  let backendStarted = 0;
  f.context.close = async () => {
    backendStarted += 1;
    await backendPending;
    return actualClose();
  };
  await activateInputProfile(f);
  assert.equal(f.context.state, "running");
  assert.equal(f.inputEntries.size, 0);
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(f.state.countAccepted, false);
  f.seal();
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  assert.equal(f.transport.terminated, true);
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.session.diagnostics().state, "restart-required");
  let first = null;
  const replacementBoundaries = [];
  const firstClose = f.session.close().then((value) => {
    first = {value};
    // Model the unchanged Creator then(factory) boundary using actual
    // fixture owner/backend evidence, not the close boolean as an ACK.
    replacementBoundaries.push({owner: f.transport.terminalOwnerReleased,
      backend: f.context.state});
  }, (error) => { first = {error}; });
  await f.tick();
  assert.equal(first, null, "sealed Native still owes its real full owner receipt");
  assert.equal(replacementBoundaries.length, 0);
  assert.equal(backendStarted, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));

  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await tickRetainedUntil(f, () => backendStarted === 1);
  assert.equal(f.transport.terminalOwnerReleased, true);
  assert.equal(f.context.state, "running", "full Native retirement is not backend closure");
  assert.equal(first, null);
  assert.equal(replacementBoundaries.length, 0);
  let second = null;
  const secondClose = f.session.close().then(
    (value) => { second = {value}; }, (error) => { second = {error}; });
  await f.tick();
  assert.equal(second, null, "a late repeated caller waits the same outstanding backend close");
  assert.equal(f.state.terminalStarts, 1);
  assert.equal(backendStarted, 1);
  assert.equal(f.state.backendCloses, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));

  releaseBackend();
  await tickRetainedUntil(f, () => first !== null && second !== null);
  await Promise.all([firstClose, secondClose]);
  assert.deepEqual(first, {value: false}, "fatal closure must not be relabeled clean close");
  assert.deepEqual(second, {value: false});
  assert.deepEqual(replacementBoundaries, [{owner: true, backend: "closed"}]);
  assert.equal(f.state.backendCloses, 1);
  assert.equal(f.state.terminalStarts, 1);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 1));
  assert.equal(f.session.diagnostics().state, "restart-required");
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  assert.equal(await f.session.close(), false);
  assert.equal(f.state.terminalStarts, 1, "a completed repeated call does not restart cleanup");
});

test("repeated fatal close waits actual termination rejection and retains original failure and resources", async (t) => {
  let releaseTermination;
  const terminationPending = new Promise((resolve) => { releaseTermination = resolve; });
  const backendFailure = Object.assign(new Error("actual terminal backend rejected"), {
    code: "IO_ERROR", details: {resource: "audio_backend", pending: true},
  });
  const f = retainedConsumerFixture({terminate: async () => {
    await terminationPending;
    throw backendFailure;
  }});
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.seal();
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  assert.equal(f.inputEntries.size, 0);
  assert.equal(f.physicalOwners.size, 0);
  let outcome = null;
  const closing = f.session.close().then(
    (value) => { outcome = {value}; }, (error) => { outcome = {error}; });
  await f.tick();
  assert.equal(outcome, null, "the actual terminator has not settled its original Promise");
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.context.state, "running");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  releaseTermination();
  await tickRetainedUntil(f, () => outcome !== null);
  await closing;
  assert.deepEqual(outcome, {value: false});
  assert.equal(f.session.diagnostics().state, "restart-required");
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT", "later cleanup rejection cannot replace the first fatal error");
  assert.deepEqual(f.session.diagnostics().error_details, {
    resource: "pattern_input", terminal_state: "sealed",
  });
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.context.state, "running");
  assert.equal(f.state.backendCloses, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  assert.equal(await f.session.close(), false);
  assert.equal(f.state.terminalStarts, 1);
});

test("repeated fatal close cannot turn resolved termination into Native retirement or backend closure", async (t) => {
  const f = retainedConsumerFixture({terminate: async () => {}});
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.seal();
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  assert.equal(f.inputEntries.size, 0);
  assert.equal(f.physicalOwners.size, 0);
  let outcome = null;
  const closing = f.session.close().then(
    (value) => { outcome = {value}; }, (error) => { outcome = {error}; });
  await f.tick();
  assert.equal(outcome, null, "a resolved custom terminator is not the Native full owner receipt");
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.context.state, "running");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await tickRetainedUntil(f, () => outcome !== null);
  await closing;
  assert.deepEqual(outcome, {value: false}, "a still-open backend is not successful fatal cleanup");
  assert.equal(f.transport.terminalOwnerReleased, true);
  assert.equal(f.context.state, "running");
  assert.equal(f.state.backendCloses, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  assert.equal(f.session.diagnostics().state, "restart-required");
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  assert.equal(await f.session.close(), false);
  assert.equal(f.state.terminalStarts, 1);
});

test("normal close reports actual termination rejection without closing or detaching SDK ownership", async () => {
  const backendFailure = Object.assign(new Error("formal backend termination failed"), {
    code: "IO_ERROR", details: {resource: "audio_backend", pending: true},
  });
  const f = retainedConsumerFixture({terminate: () => { throw backendFailure; }});
  await activateInputProfile(f);
  assert.equal(await f.session.close(), false);
  await drainTasks();
  assert.equal(f.session.diagnostics().state, "failed");
  assert.equal(f.session.diagnostics().error_code, "IO_ERROR");
  assert.deepEqual(f.session.diagnostics().error_details, {resource: "audio_backend"});
  assert.equal(f.context.state, "running");
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.state.terminalStarts, 1);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  assert.equal(await f.session.close(), false);
});

test("normal close preserves real AudioContext close failure after its deliberate production seal", async () => {
  const backendFailure = Object.assign(new Error("AudioContext.close rejected"), {
    code: "IO_ERROR", details: {resource: "audio_context", pending: true},
  });
  const f = retainedConsumerFixture({terminate: async ({audioContext}) => {
    f.seal(deliberateTerminationSeal());
    f.state.nativeOwnerAcknowledged = true;
    f.releaseTerminal();
    await audioContext.close();
  }});
  f.context.close = async () => { throw backendFailure; };
  await activateInputProfile(f);
  assert.equal(await f.session.close(), false);
  await drainTasks();
  assert.equal(f.session.diagnostics().state, "failed");
  assert.equal(f.session.diagnostics().error_code, "IO_ERROR", "the deliberate seal cannot replace the actual backend error");
  assert.deepEqual(f.session.diagnostics().error_details, {resource: "audio_context"});
  assert.equal(f.transport.terminalOwnerReleased, true, "full Native owner release is separate from backend closure");
  assert.equal(f.context.state, "running");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
});

test("normal close cannot infer backend closure from an arbitrary resolved terminator", async () => {
  const f = retainedConsumerFixture({terminate: async ({audioContext}) => {
    f.seal(deliberateTerminationSeal());
    f.state.nativeOwnerAcknowledged = true;
    f.releaseTerminal();
    await audioContext.close();
  }});
  let closeCalls = 0;
  f.context.close = async () => { closeCalls += 1; };
  await activateInputProfile(f);
  assert.equal(await f.session.close(), false);
  await drainTasks();
  assert.equal(closeCalls, 1);
  assert.equal(f.session.diagnostics().state, "failed");
  assert.equal(f.session.diagnostics().error_code, "HOST_STATE_INVALID");
  assert.deepEqual(f.session.diagnostics().error_details, {});
  assert.equal(f.context.state, "running");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
});

test("normal close cannot infer owner release from a resolved terminator with an advertised false receipt", async () => {
  const f = retainedConsumerFixture({terminate: async ({audioContext}) => { audioContext.state = "closed"; }});
  f.context.close = async () => { f.context.state = "closed"; };
  await activateInputProfile(f);
  assert.equal(await f.session.close(), false);
  await drainTasks();
  assert.equal(f.transport.terminated, false, "a false advertised receipt matters even without a seal notification");
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.session.diagnostics().state, "failed");
  assert.equal(f.session.diagnostics().error_code, "HOST_STATE_INVALID");
  assert.deepEqual(f.session.diagnostics().error_details, {});
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
});

test("normal close accepts its own production seal only after real owner and backend closure", async () => {
  let releaseBackend;
  const backendPending = new Promise((resolve) => { releaseBackend = resolve; });
  const f = retainedConsumerFixture({terminate: async ({audioContext}) => {
    f.seal(deliberateTerminationSeal());
    await backendPending;
    f.state.nativeOwnerAcknowledged = true;
    f.releaseTerminal();
    await audioContext.close();
  }});
  let closeCalls = 0;
  f.context.close = async () => { closeCalls += 1; f.context.state = "closed"; };
  await activateInputProfile(f);
  const closing = f.session.close();
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  assert.equal(f.session.diagnostics().state, "running", "closed is not published before termination settles");
  assert.equal(f.session.diagnostics().error_code, null, "this exact deliberate local seal is expected");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  releaseBackend();
  await drainTasks();
  await f.tick();
  assert.equal(await closing, true);
  assert.equal(closeCalls, 1);
  assert.equal(f.context.state, "closed");
  assert.equal(f.transport.terminalOwnerReleased, true);
  assert.equal(f.session.diagnostics().state, "closed");
  assert.equal(f.session.diagnostics().error_code, null);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 1));
});

test("normal close does not suppress an unrelated transport failure during terminator invocation", async () => {
  const actualFailure = Object.assign(new Error("actual owner transport failed during close"), {
    code: "HOST_STATE_INVALID", details: {resource: "owner", pending: true},
  });
  const f = retainedConsumerFixture({terminate: ({audioContext}) => {
    f.seal(actualFailure);
    f.state.nativeOwnerAcknowledged = true;
    f.releaseTerminal();
    audioContext.state = "closed";
  }});
  await activateInputProfile(f);
  assert.equal(await f.session.close(), false);
  await drainTasks();
  assert.equal(f.session.diagnostics().state, "failed");
  assert.deepEqual(f.session.diagnostics().error_details, {resource: "owner"});
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
});

test("normal close does not suppress a matching seal message outside its synchronous invocation", async () => {
  const actualFailure = deliberateTerminationSeal();
  const f = retainedConsumerFixture({terminate: async ({audioContext}) => {
    await Promise.resolve();
    f.seal(actualFailure);
    f.state.nativeOwnerAcknowledged = true;
    f.releaseTerminal();
    audioContext.state = "closed";
  }});
  await activateInputProfile(f);
  assert.equal(await f.session.close(), false);
  await drainTasks();
  assert.equal(f.session.diagnostics().state, "failed");
  assert.equal(f.session.diagnostics().error_code, "HOST_STATE_INVALID");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
});

test("later termination rejection preserves the original fatal response loss and retained backend references", async () => {
  const laterFailure = Object.assign(new Error("later backend termination failed"), {code: "IO_ERROR", details: {pending: true}});
  const f = retainedConsumerFixture({terminate: () => { throw laterFailure; }});
  await activateInputProfile(f);
  f.seal();
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await f.tick();
  assert.equal(f.session.diagnostics().state, "restart-required");
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  assert.deepEqual(f.session.diagnostics().error_details, {resource: "pattern_input", terminal_state: "sealed"});
  assert.equal(f.context.state, "running");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  assert.equal(await f.session.close(), false);
});

function directInputRequest(overrides = {}) {
  const identity = countInPublicTicket();
  return {commandId: TRANSPORT_COMMAND_ID, runtimeGeneration: identity.runtimeGeneration,
    frameEpoch: identity.frameEpoch, inputSerial: "1", slot: 0, velocity: 100, kind: "press",
    held: true, heldPressSequence: null, ...overrides};
}

for (const expireObserver of [false, true]) {
  test(`transient input I/O error recovers the same physical owner ${expireObserver ? "after original observer expiry" : "within the original deadline"}`, async () => {
    const f = retainedConsumerFixture();
    await activateInputProfile(f);
    let observed = null;
    const press = f.session.trigger(0, 100, "pointer").then(
      (value) => { observed = {value}; },
      (error) => { observed = {error}; });
    await tickRetainedUntil(f, () => f.inputEntries.has("1"));
    const original = f.inputEntries.get("1");
    const identity = structuredClone(original.status);
    const ticket = {commandId: original.payload.command_id,
      runtimeGeneration: original.payload.runtime_generation,
      frameEpoch: original.payload.frame_epoch, ticket: "1"};
    const unknownError = {code: "IO_ERROR", message: "Original candidate flush outcome is unknown",
      details: {reason: "sequence_append_unknown"}};
    original.status.error = unknownError;
    const pending = await f.session.inspectPatternInput(ticket);
    assert.equal(pending.complete, false);
    assert.equal(pending.durableSettled, false);
    assert.deepEqual(pending.error, unknownError);
    assert.equal(observed, null, "a pending worker error is not a final public input result");
    let originalObserverError = null;
    if (expireObserver) {
      await f.tick(1000); // Fire the actual original SDK observer timer.
      await press;
      originalObserverError = observed.error;
      assert.equal(originalObserverError.code, "HOST_TIMEOUT");
      assert.equal(originalObserverError.details.pending, true);
      assert.equal(f.inputConsumed.size, 0, "observer expiry is not durable consumption");
    }
    // The same retained work reconciles; no new request or Native effect is sent.
    original.status.error = null;
    f.state.inputComplete = true;
    await tickRetainedUntil(f, () => f.inputConsumed.has("1"));
    await press;
    if (expireObserver) assert.equal(observed.error, originalObserverError,
      "late reconciliation preserves the exact original observer failure");
    else assert.deepEqual(observed, {value: {sequence: 1, slot: 0, velocity: 100, source: "pointer"}});
    assert.deepEqual(original.status.admission, identity.admission);
    assert.deepEqual(original.status.native_result, identity.native_result);
    assert.equal(f.physicalOwners.size, 1, "press consumption retains its future physical release");
    const release = f.session.release(0, "pointer");
    await tickRetainedUntil(f, () => f.inputConsumed.has("2"));
    assert.equal(await release, true);
    assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.request")
      .map((e) => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
      [["press", "1", null], ["release", "2", "1"]]);
    assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
      .map((e) => e.payload.ticket), ["1", "2"]);
    assert.equal(f.physicalOwners.size, 0);
    assert.equal(await f.session.release(0, "pointer"), false, "the actual release retired its one SDK hold");
    assert.equal(f.retained.length, 0, "healthy worker reconciliation does not seal or borrow the terminal lane");
    assert.equal(await f.session.close(), true, "the exact input consumers and physical owners left no terminal debt");
    assert.equal(f.state.backendCloses, 1);
  });
}

for (const changed of ["admission", "native result", "final error", "final success"]) {
  test(`input reconciliation still refuses a changed ${changed}`, async () => {
    const finalError = {code: "IO_ERROR", message: "Original final candidate refusal", details: {reason: "append_refused"}};
    const f = retainedConsumerFixture({admissionReply: (_envelope, response) => {
      if (changed === "final error") response.result.status.error = finalError;
      return response;
    }});
    await activateInputProfile(f);
    f.state.inputComplete = true;
    const admission = await f.session.requestPatternInput(directInputRequest({held: false}));
    const input = f.inputEntries.get("1");
    const original = structuredClone(input.status);
    if (changed === "admission") {
      input.status.admission = {...input.status.admission, acceptance_ordinal: "2"};
      input.status.native_result = {...input.status.native_result, acceptance_ordinal: "2"};
    } else if (changed === "native result") {
      input.status.native_result = {...input.status.native_result, runtime_frame: 124};
    } else input.status.error = changed === "final error" ? null : finalError;
    await assert.rejects(f.session.inspectPatternInput(admission.ticket), {code: "HOST_PROTOCOL_MISMATCH"});
    assert.equal(f.inputConsumed.size, 0, "corrupt evidence cannot consume the retained original ticket");
    input.status = original;
    const consumed = await f.session.inspectPatternInput(admission.ticket, true);
    assert.equal(consumed.complete, true);
    assert.deepEqual(consumed.error, changed === "final error" ? finalError : null);
    assert.deepEqual([...f.inputConsumed], ["1"]);
    assert.equal(await f.session.close(), true);
  });
}

test("direct public input response loss consumes the exact original complete ticket while retaining its held owner", async () => {
  const f = retainedConsumerFixture({loseInputAdmission: true});
  await activateInputProfile(f);
  const request = directInputRequest();
  await assert.rejects(f.session.requestPatternInput(request), (error) => error === f.originalError);
  await tickRetainedUntil(f, () => f.retained.some((e) => e.operation === "pattern.transport.input.inspect"));
  assert.equal(f.inputEntries.size, 1);
  assert.equal(f.inputConsumed.size, 0);
  assert.equal(f.physicalOwners.size, 1);
  assert.equal(f.retained.some((e) => e.operation === "pattern.transport.input.request"), false,
    "the direct consumer neither re-enqueues its press nor manufactures a physical release");
  f.state.inputComplete = true;
  await tickRetainedUntil(f, () => f.inputConsumed.has("1"));
  const consumed = f.retained.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume);
  assert.equal(consumed.length, 1);
  assert.deepEqual(consumed[0].payload, {command_id: request.commandId, runtime_generation: request.runtimeGeneration,
    frame_epoch: request.frameEpoch, ticket: "1", consume: true});
  assert.equal(f.physicalOwners.size, 1, "the caller-ticket consumer is no physical owner release");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  const release = await f.session.requestPatternInput(directInputRequest({
    commandId: "00000000-0000-4000-8000-0000000000ee", inputSerial: "2", velocity: 0,
    kind: "release", heldPressSequence: f.inputEntries.get("1").status.admission.sequence,
  }));
  await f.tick();
  assert.equal(f.inputConsumed.has("2"), false, "a known direct release keeps its explicit public consumer");
  assert.equal((await f.session.inspectPatternInput(release.ticket, true)).nativeResult.disposition, "release_no_voice");
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.input.request").length, 1);
  assert.equal(f.retained.filter((e) => e.operation === "pattern.transport.input.request").length, 1);
  assert.deepEqual([...f.inputConsumed].sort(), ["1", "2"]);
  assert.equal(f.session.diagnostics().state, "restart-required");
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await f.tick();
});

test("direct response-loss input without a retained capability stays pending without synthetic consumption", async () => {
  const f = retainedConsumerFixture({loseInputAdmission: true, retainedAvailable: false});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternInput(directInputRequest({held: false})), (error) => error === f.originalError);
  f.state.inputComplete = true;
  await f.tick(12_000);
  assert.equal(f.inputEntries.size, 1);
  assert.equal(f.inputConsumed.size, 0);
  assert.equal(f.retained.length, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  assert.equal(await f.session.close(), false);
  f.state.retainedAvailable = true;
  await tickRetainedUntil(f, () => f.inputConsumed.has("1"));
  assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.input.request").length, 1);
  assert.equal(f.retained.filter((e) => e.operation === "pattern.transport.input.request").length, 0);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await f.tick();
});

test("healthy known direct public input keeps its original explicit inspect and consume semantics", async () => {
  const f = retainedConsumerFixture();
  await activateInputProfile(f);
  const admission = await f.session.requestPatternInput(directInputRequest({held: false}));
  f.state.inputComplete = true;
  await f.tick(12_000);
  assert.equal(f.inputConsumed.size, 0);
  assert.equal(f.normal.some((e) => e.operation === "pattern.transport.input.inspect"), false);
  assert.equal(f.retained.length, 0);
  assert.equal((await f.session.inspectPatternInput(admission.ticket)).complete, true);
  assert.equal(f.inputConsumed.size, 0);
  assert.equal((await f.session.inspectPatternInput(admission.ticket, true)).complete, true);
  assert.deepEqual([...f.inputConsumed], ["1"]);
  assert.equal(f.retained.length, 0);
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  assert.equal(await f.session.close(), true);
});

test("retained fixture zero turns observe actual resume settlement without moving production deadlines", async () => {
  const f = retainedConsumerFixture();
  let releaseResume;
  const resumePending = new Promise((resolve) => { releaseResume = resolve; });
  let resumeStarted;
  const started = new Promise((resolve) => { resumeStarted = resolve; });
  f.context.resume = async () => {
    resumeStarted();
    await resumePending;
    f.context.state = "running";
  };
  assert.equal(await f.session.start(), true);
  let settled = false;
  const activating = f.session.activateAudio(createUserGestureToken({isTrusted: true})).then((result) => {
    settled = true;
    return result;
  });
  try {
    await started;
    await drainTasks();
    await drainTasks();
    assert.ok(f.state.zeroTimersServiced > 0);
    assert.equal(settled, false, "servicing a zero timer cannot replace the actual resume outcome");
    assert.equal(f.context.state, "suspended");
    assert.equal(f.clockMilliseconds(), 0);
    releaseResume();
    assert.equal(await activating, true);
    assert.equal(f.context.state, "running");
    assert.equal(f.clockMilliseconds(), 0, "activation spent no fabricated monotonic budget");
    f.state.nativeOwnerAcknowledged = true;
    f.releaseTerminal();
    assert.equal(await f.session.close(), true);
    assert.equal(f.state.backendCloses, 1);
  } finally {
    releaseResume();
    await activating;
  }
});

test("default retained terminator requires full owner release and actual backend closure independently", async () => {
  const f = retainedConsumerFixture({countMode: "accepted-response-loss"});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  f.state.countStatus = failedOriginalCountInEvidence();
  f.state.nativeOwnerAcknowledged = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  await f.tick(5_000);
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.state.backendCloses, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0), "count consume, physical ACK and elapsed time are no full receipt");
  let releaseBackend;
  const backendPending = new Promise((resolve) => { releaseBackend = resolve; });
  const closeBackend = f.context.close;
  let backendStarted = false;
  f.context.close = async () => {
    backendStarted = true;
    await backendPending;
    await closeBackend();
  };
  try {
    f.releaseTerminal();
    await f.tick();
    assert.equal(backendStarted, true);
    assert.equal(f.context.state, "running");
    assert.ok(f.nodes.every((node) => node.disconnected.length === 0), "full owner release cannot stand in for actual backend close");
    releaseBackend();
    await drainTasks();
    await f.tick();
    assert.equal(f.state.backendCloses, 1);
    assert.equal(f.context.state, "closed");
    assert.ok(f.nodes.every((node) => node.disconnected.length === 1));
    assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  } finally {
    releaseBackend();
  }
});

test("raw unsealed protocol admission rejection preserves direct input identity and explicit healthy consumption", async () => {
  const rawFailure = Object.freeze(Object.assign(new Error("known raw admission rejection"), {
    code: "HOST_PROTOCOL_MISMATCH", details: Object.freeze({resource: "pattern_input"}),
  }));
  let rejectAdmission = true;
  const f = retainedConsumerFixture({beforeAdmission: (e) => {
    if (rejectAdmission && e.operation === "pattern.transport.input.request") throw rawFailure;
  }});
  await activateInputProfile(f);
  const request = directInputRequest({held: false});
  await assert.rejects(f.session.requestPatternInput(request), (error) => error === rawFailure);
  await f.tick(12_000);
  assert.equal(f.transport.terminated, false);
  assert.equal(f.inputEntries.size, 0, "the strict Host never enqueued the rejected request");
  assert.equal(f.inputConsumed.size, 0);
  assert.equal(f.normal.some((e) => e.operation === "pattern.transport.input.inspect"), false);
  assert.equal(f.state.terminalStarts, 0);
  assert.deepEqual(Object.keys(rawFailure).sort(), ["code", "details"]);
  rejectAdmission = false;
  const known = await f.session.requestPatternInput(request);
  assert.equal(known.ticket.ticket, "1", "a known raw rejection did not spend or retain the fresh identity");
  f.state.inputComplete = true;
  await f.tick();
  assert.equal(f.inputConsumed.size, 0, "a later healthy known ticket remains explicitly consumed");
  assert.equal((await f.session.inspectPatternInput(known.ticket, true)).complete, true);
  assert.equal(f.inputEntries.size, 1);
  assert.deepEqual([...f.inputConsumed], ["1"]);
  assert.equal(await f.session.close(), true);
});

test("raw unsealed count protocol rejection creates no unknown caller debt or synthetic consume", async () => {
  const rawFailure = Object.freeze(Object.assign(new Error("known raw count admission rejection"), {
    code: "HOST_PROTOCOL_MISMATCH", details: Object.freeze({resource: "count_in"}),
  }));
  const f = retainedConsumerFixture({beforeAdmission: (e) => {
    if (e.operation === "pattern.transport.count-in.request") throw rawFailure;
  }});
  await activateInputProfile(f);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === rawFailure);
  await f.tick(12_000);
  assert.equal(f.transport.terminated, false);
  assert.equal(f.state.countAccepted, false);
  assert.equal(f.state.countInspects, 0);
  assert.equal(f.state.countConsumes, 0);
  assert.equal(f.state.terminalStarts, 0);
  assert.equal(f.retained.length, 0);
  assert.deepEqual(Object.keys(rawFailure).sort(), ["code", "details"]);
  assert.equal(await f.session.close(), true);
});

for (const fault of ["envelope", "request-id", "positive-dto", "sealed-raw"]) {
  test(`accepted direct input ${fault} corruption retains its exact original private consumer`, async () => {
    let originalStatus;
    const rawFailure = Object.freeze(Object.assign(new Error("sealed accepted input reply failed"), {
      code: "HOST_PROTOCOL_MISMATCH", details: Object.freeze({resource: "pattern_input"}),
    }));
    const f = retainedConsumerFixture({admissionReply: (e, response) => {
      assert.equal(e.operation, "pattern.transport.input.request");
      assert.equal(f.transport.terminated, false, "the local validation evidence precedes producer sealing");
      originalStatus = structuredClone(response.result.status);
      if (fault === "sealed-raw") { f.seal(rawFailure); throw rawFailure; }
      const bad = structuredClone(response);
      if (fault === "envelope") bad.unexpected = true;
      else if (fault === "request-id") bad.request_id = "00000000-0000-4000-8000-0000000000ff";
      else bad.result.status.native_result.runtime_frame = -1;
      return bad;
    }});
    await activateInputProfile(f);
    const request = directInputRequest({held: false});
    let primaryFailure;
    await assert.rejects(f.session.requestPatternInput(request), (error) => {
      primaryFailure = error;
      return error.code === "HOST_PROTOCOL_MISMATCH";
    });
    if (fault === "sealed-raw") assert.equal(primaryFailure, rawFailure);
    assert.deepEqual(Object.keys(primaryFailure).sort(), fault === "sealed-raw" ? ["code", "details"] : ["code", "details", "name"],
      "private validation evidence adds no error fields");
    await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
    assert.equal(f.inputEntries.size, 1);
    assert.deepEqual(f.inputEntries.get("1").status, originalStatus, "a corrupt reply did not rewrite the actual original owner");
    assert.equal(f.inputConsumed.size, 0);
    await assert.rejects(f.session.requestPatternInput(request), {code: "HOST_STATE_INVALID"});
    f.state.inputComplete = true;
    await tickRetainedUntil(f, () => f.inputConsumed.has("1"));
    assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.input.request").length, 1);
    assert.equal(f.retained.filter((e) => e.operation === "pattern.transport.input.request").length, 0);
    assert.equal(f.retained.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume).length, 1);
    assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
    assert.equal(f.session.diagnostics().error_code, primaryFailure.code);
    f.state.nativeOwnerAcknowledged = true;
    f.releaseTerminal();
    await f.tick();
    assert.equal(f.context.state, "closed");
    assert.equal(f.session.diagnostics().error_code, primaryFailure.code);
  });
}

for (const fault of ["request-id", "positive-dto", "explicit-pending"]) {
  test(`accepted count ${fault} failure retains original admission and final exact caller consume`, async () => {
    const rawFailure = Object.freeze(Object.assign(new Error("accepted count reply is unknown"), {
      code: "HOST_PROTOCOL_MISMATCH", details: Object.freeze({pending: true, resource: "count_in"}),
    }));
    const f = retainedConsumerFixture({admissionReply: (e, response) => {
      assert.equal(e.operation, "pattern.transport.count-in.request");
      assert.equal(f.state.countAccepted, true);
      assert.equal(f.transport.terminated, false);
      if (fault === "explicit-pending") throw rawFailure;
      const bad = structuredClone(response);
      if (fault === "request-id") bad.request_id = "00000000-0000-4000-8000-0000000000ff";
      else bad.result.ticket.command_id = "00000000-0000-4000-8000-0000000000ff";
      return bad;
    }});
    await activateInputProfile(f);
    let primaryFailure;
    await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => {
      primaryFailure = error;
      return error.code === "HOST_PROTOCOL_MISMATCH";
    });
    if (fault === "explicit-pending") {
      assert.equal(primaryFailure, rawFailure);
      assert.deepEqual(Object.keys(rawFailure).sort(), ["code", "details"]);
    }
    await tickRetainedUntil(f, () => f.state.countInspects > 0 && f.state.terminalStarts === 1);
    await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === primaryFailure);
    assert.equal(f.state.countConsumes, 0);
    assert.equal(f.normal.filter((e) => e.operation === "pattern.transport.count-in.request").length, 1);
    f.state.countStatus = failedOriginalCountInEvidence();
    f.state.nativeOwnerAcknowledged = true;
    await tickRetainedUntil(f, () => f.state.countConsumed);
    const final = await f.session.inspectPatternCountIn(countInPublicTicket());
    assert.equal(final.startReceipt.result, "refused");
    assert.equal(final.cancelReceipt.result, "refused");
    assert.equal(final.error.code, "IO_ERROR");
    assert.equal(f.state.countConsumes, 1);
    assert.equal(f.retained.some((e) => e.operation === "pattern.transport.count-in.request"), false);
    assert.equal(f.session.diagnostics().error_code, primaryFailure.code);
    f.releaseTerminal();
    await f.tick();
    assert.equal(f.context.state, "closed");
    assert.equal(f.session.diagnostics().error_code, primaryFailure.code);
  });
}

test("accepted profile positive DTO corruption keeps its existing consumer and original release without duplicate admission", async () => {
  const f = retainedConsumerFixture({admissionReply: (e, response) => {
    if (e.payload.kind !== "press") return response;
    const bad = structuredClone(response);
    bad.result.status.native_result.slot = 7;
    return bad;
  }});
  await activateInputProfile(f);
  await assert.rejects(f.session.trigger(0, 100, "pointer"), {code: "HOST_PROTOCOL_MISMATCH"});
  assert.equal(f.inputEntries.size, 1);
  assert.equal(f.inputConsumed.size, 0);
  f.state.inputComplete = true;
  await tickRetainedUntil(f, () => f.inputConsumed.has("1"));
  assert.equal(f.physicalOwners.size, 1, "the original profile consumer cannot erase physical escrow");
  assert.equal(await f.session.release(0, "pointer"), true);
  assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.request")
    .map((e) => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
    [["press", "1", null], ["release", "2", "1"]]);
  assert.deepEqual(f.normal.filter((e) => e.operation === "pattern.transport.input.inspect" && e.payload.consume)
    .map((e) => e.payload.ticket), ["1", "2"]);
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(f.retained.length, 0);
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  assert.equal(await f.session.close(), true);
});

for (const countOwner of [false, true]) {
  test(`ordinary ${countOwner ? "count owner" : "unnegotiated legacy"} transport inspection retains its original project deadline`, async () => {
    const inspections = [];
    const admissions = [];
    let handle = 10;
    const f = fixture({patternTransport: true,
      registerAudioNode: () => ++handle,
      startAudioWorkletWithCountIn: async () => ({ok: true, outputs: 2}),
      send: async (envelope, options) => {
        if (envelope.operation === "pattern.transport.count-in.request") {
          admissions.push(envelope);
          return success(envelope, {submit: "accepted", ticket: countInWireTicket(), status: countInWireStatus()});
        }
        if (envelope.operation === "pattern.transport.inspect") {
          inspections.push({payload: envelope.payload, deadlineMs: options.deadlineMs});
          return success(envelope, transportStatus({phase: "idle"}));
        }
        if (envelope.operation === "pattern.transport.count-in.inspect")
          return success(envelope, failedOriginalCountInEvidence());
        return success(envelope, defaultResult(envelope.operation));
      }});
    if (countOwner) await activateInputProfile(f);
    else assert.equal(await f.session.start(), true);
    const admission = countOwner ? await f.session.requestPatternCountIn(countInRequest()) : null;
    assert.equal((await f.session.inspectPatternTransport(TRANSPORT_SESSION_ID)).phase, "idle");
    assert.deepEqual(inspections, [{payload: {session_id: TRANSPORT_SESSION_ID}, deadlineMs: 30_000}],
      "a healthy owner or unnegotiated legacy query never inherits the sealed continuation budget");
    assert.equal(admissions.length, countOwner ? 1 : 0);
    if (admission) await f.session.inspectPatternCountIn(admission.ticket, true);
    assert.equal(await f.session.close(), true);
  });
}


// Exact local gesture ownership; Native requests and caller consumption remain real.
test("local gesture key releases two same-slot/source holds in original key order", async (t) => {
  const f = retainedConsumerFixture();
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.state.inputComplete = true;
  const first = Object.freeze({});
  const second = Object.freeze({});
  assert.equal((await f.session.trigger(0, 100, "pointer", first)).sequence, 1);
  assert.equal((await f.session.trigger(0, 100, "pointer", second)).sequence, 2);
  assert.deepEqual([...f.physicalOwners.keys()], ["1", "2"]);
  assert.equal(await f.session.release(0, "pointer", first), true);
  assert.deepEqual([...f.physicalOwners.keys()], ["2"], "keyup pays its own original physical owner");
  assert.equal(await f.session.release(0, "pointer", second), true);
  assert.deepEqual(f.normal.filter(e => e.operation === "pattern.transport.input.request")
    .map(e => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
    [["press", "1", null], ["press", "2", null], ["release", "3", "1"], ["release", "4", "2"]]);
  assert.deepEqual([...f.inputConsumed], ["1", "2", "3", "4"]);
  assert.equal(await f.session.close(), true);
});

test("local gesture key rejects active reuse and never falls back on key/slot/source mismatch", async (t) => {
  const f = retainedConsumerFixture();
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.state.inputComplete = true;
  const key = {};
  assert.equal((await f.session.trigger(0, 100, "keyboard", key)).sequence, 1);
  assert.equal(await f.session.trigger(1, 100, "keyboard", key), false);
  assert.equal(await f.session.release(1, "keyboard", key), false);
  assert.equal(await f.session.release(0, "pointer", key), false);
  assert.equal(await f.session.release(0, "keyboard", {}), false);
  assert.equal(f.inputEntries.size, 1, "none of the refused calls dispatches Native input");
  assert.equal(await f.session.release(0, "keyboard", key), true);
  assert.equal((await f.session.trigger(1, 100, "keyboard", key)).sequence, 3,
    "the same reference is reusable only after real physical and caller settlement");
  assert.equal(await f.session.release(1, "keyboard", key), true);
  assert.equal(await f.session.close(), true);
});

test("local gesture key refuses null and primitive identity before Native effects", async (t) => {
  const f = retainedConsumerFixture();
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.state.inputComplete = true;
  for (const invalid of [null, 1, "key", true, Symbol("key")]) {
    await assert.rejects(Promise.resolve().then(() => f.session.trigger(0, 100, "pointer", invalid)), TypeError);
    await assert.rejects(f.session.release(0, "pointer", invalid), TypeError);
  }
  assert.equal(f.inputEntries.size, 0);
  assert.equal(await f.session.close(), true);
});

test("local gesture early release joins one original intent while durable input remains held", async (t) => {
  const f = retainedConsumerFixture();
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  const key = {};
  const press = f.session.trigger(0, 100, "pointer", key);
  const release = f.session.release(0, "pointer", key);
  const repeated = f.session.release(0, "pointer", key);
  const legacy = f.session.release(0, "pointer");
  await tickRetainedUntil(f, () => f.inputEntries.size === 2);
  assert.deepEqual(f.normal.filter(e => e.operation === "pattern.transport.input.request")
    .map(e => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
    [["press", "1", null], ["release", "2", "1"]]);
  assert.equal(f.inputConsumed.size, 0);
  assert.equal(f.physicalOwners.size, 1);
  f.state.inputComplete = true;
  assert.equal((await settleRetainedCall(f, press)).sequence, 1);
  for (const observation of [release, repeated, legacy])
    assert.equal(await settleRetainedCall(f, observation), true, "all observers join the actual same release");
  assert.deepEqual([...f.inputConsumed], ["1", "2"]);
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(await f.session.close(), true);
});

test("local gesture unknown admission reserves one release before keyup/cancel/safety race", async (t) => {
  let resolveInspection;
  const inspection = new Promise(resolve => { resolveInspection = resolve; });
  const f = retainedConsumerFixture({loseInputAdmission: true,
    beforeInputInspect: (e) => e.payload.ticket === "1" ? inspection : undefined});
  t.after(() => { resolveInspection(); f.cancelTimers(); });
  await activateInputProfile(f);
  const key = {};
  await assert.rejects(f.session.trigger(0, 100, "pointer", key), error => error === f.originalError);
  const release = f.session.release(0, "pointer", key).then(value => ({value}), error => ({error}));
  const repeated = f.session.release(0, "pointer", key).then(value => ({value}), error => ({error}));
  const legacy = f.session.release(0, "pointer").then(value => ({value}), error => ({error}));
  await drainTasks();
  assert.equal(f.inputEntries.size, 1);
  assert.equal(f.physicalOwners.size, 1);
  resolveInspection();
  await tickRetainedUntil(f, () => f.inputEntries.size >= 2);
  await f.tick();
  const actual = [...f.normal, ...f.retained].filter(e => e.operation === "pattern.transport.input.request");
  assert.deepEqual(actual.map(e => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
    [["press", "1", null], ["release", "2", "1"]]);
  assert.equal(f.inputConsumed.size, 0);
  f.state.inputComplete = true;
  for (const observation of [release, repeated, legacy])
    assert.deepEqual(await settleRetainedCall(f, observation), {value: true});
  await tickRetainedUntil(f, () => f.inputConsumed.has("1") && f.inputConsumed.has("2"));
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT", "the original press observer stays failed");
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await f.tick();
});

test("local gesture repeated release keeps its first deadline and retained consume debt", async (t) => {
  const f = retainedConsumerFixture();
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.state.completeInput = p => p.kind === "press" || f.state.inputComplete;
  const key = {};
  assert.equal((await f.session.trigger(0, 100, "keyboard", key)).sequence, 1);
  const first = f.session.release(0, "keyboard", key).then(value => ({value}), error => ({error}));
  await tickRetainedUntil(f, () => f.inputEntries.size === 2);
  await f.tick(700);
  const second = f.session.release(0, "keyboard", key).then(value => ({value}), error => ({error}));
  await drainTasks();
  await f.tick(300);
  for (const observation of [first, second]) {
    const outcome = await settleRetainedCall(f, observation);
    assert.equal(outcome.error?.code, "HOST_TIMEOUT");
    assert.equal(outcome.error.details.pending, true);
  }
  assert.equal(f.inputEntries.size, 2, "observer expiry does not enqueue another release");
  assert.deepEqual([...f.inputConsumed], ["1"]);
  assert.equal(f.physicalOwners.size, 1);
  f.state.inputComplete = true;
  await tickRetainedUntil(f, () => f.inputConsumed.has("2"));
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(await f.session.close(), true);
});


for (const operation of ["host.close", "audio.suspend"]) {
  test(`local gesture unsealed unknown release joins explicit ${operation} safety and exact consumes`, async (t) => {
    let resolveInspection;
    const inspection = new Promise(resolve => { resolveInspection = resolve; });
    const loss = Object.assign(new Error("actual admitted press response lost on healthy lane"), {
      code: "HOST_TIMEOUT", details: {pending: true},
    });
    const f = retainedConsumerFixture({retainLifecycleUntilInputConsumed: true,
      admissionReply: (e, response) => {
        if (e.operation === "pattern.transport.input.request" && e.payload.kind === "press") throw loss;
        return response;
      }, beforeInputInspect: e => e.payload.ticket === "1" ? inspection : undefined});
    t.after(() => { resolveInspection(); f.cancelTimers(); });
    await activateInputProfile(f);
    const key = {};
    await assert.rejects(f.session.trigger(0, 100, "pointer", key), error => error === loss);
    assert.equal(f.transport.terminated, false);
    assert.equal(f.session.diagnostics().state, "running", "unknown original caller is independent of lifecycle");
    const release = f.session.release(0, "pointer", key);
    const repeated = f.session.release(0, "pointer", key);
    let lifecycleResult = null;
    const lifecycle = (operation === "host.close" ? f.session.close() : f.session.suspendAudio())
      .then(value => { lifecycleResult = value; return value; });
    await tickRetainedUntil(f, () => f.state.lifecyclePending.length === 1);
    assert.deepEqual(f.state.lifecyclePending[0].tickets, ["1"]);
    assert.equal(lifecycleResult, null);
    assert.equal(f.inputConsumed.size, 0);
    resolveInspection();
    await tickRetainedUntil(f, () => f.inputEntries.size === 2);
    assert.deepEqual(f.normal.filter(e => e.operation === "pattern.transport.input.request")
      .map(e => [e.payload.kind, e.payload.input_serial, e.payload.held_press_sequence]),
      [["press", "1", null], ["release", "2", "1"]]);
    assert.equal(f.physicalOwners.size, 1);
    f.state.inputComplete = true;
    assert.equal(await settleRetainedCall(f, release), true);
    assert.equal(await settleRetainedCall(f, repeated), true);
    assert.equal(await settleRetainedCall(f, lifecycle), true);
    assert.deepEqual([...f.inputConsumed].sort(), ["1", "2"], "both original caller debts settle independently");
    assert.equal(f.physicalOwners.size, 0);
    assert.equal(f.state.lifecyclePending.length, 0);
    if (operation === "audio.suspend") {
      assert.equal(f.session.diagnostics().state, "audio-suspended");
      assert.equal(await settleRetainedCall(f, f.session.close()), true);
    }
    assert.equal(f.state.backendCloses, 1);
  });
}


// Recovery is owned by an exact SDK epoch, not by the fixture's reported state.
function profileRecoveryFixture(t, options = {}) {
  const browserWindow = new EventTarget();
  const browserDocument = new EventTarget();
  browserDocument.visibilityState = "visible";
  const f = retainedConsumerFixture({browserWindow, browserDocument,
    inputDisposition: p => p.kind === "press" ? "voice_started" : "release_no_voice", ...options});
  t.after(() => f.cancelTimers());
  return {...f, browserWindow, setVisibility(hidden) {
    browserDocument.visibilityState = hidden ? "hidden" : "visible";
    browserDocument.dispatchEvent(new Event("visibilitychange"));
  }};
}
async function armProfileRecovery(f) {
  f.browserWindow.dispatchEvent(browserEvent("pagehide", {persisted: true}));
  f.browserWindow.dispatchEvent(browserEvent("pageshow", {persisted: true}));
  await tickRetainedUntil(f, () => f.session.diagnostics().recovery_probe_ready === true);
  assert.equal(f.session.diagnostics().state, "recovering");
}
const observeProfileCall = promise => promise.then(value => ({value}), error => ({error}));
async function finishFailedProfileOwner(f) {
  await tickRetainedUntil(f, () => f.physicalOwners.size === 0 &&
    [...f.inputEntries.keys()].every(key => f.inputConsumed.has(key)));
  // The fixture's independent backend receipt checks every real modeled debt.
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await tickRetainedUntil(f, () => f.state.backendCloses === 1);
}

for (const delayedTimer of [false, true]) {
  test(`profile recovery original deadline prevents late success with ${delayedTimer ? "delayed" : "dispatched"} timer`, async t => {
    let releaseReply;
    let heldReply = null;
    const held = new Promise(resolve => { releaseReply = resolve; });
    const f = profileRecoveryFixture(t, {inputReply: (e, response) => {
      if (e.payload.consume && e.payload.ticket === "1") {
        heldReply = response;
        return held.then(() => response); // Genuine consumed bytes, never synthetic status.
      }
      return response;
    }});
    t.after(() => releaseReply());
    await activateInputProfile(f);
    await armProfileRecovery(f);
    f.state.inputComplete = true;
    const outcomes = [];
    f.session.subscribeRuntimeOutcome(value => outcomes.push(value));
    const key = {};
    const press = observeProfileCall(f.session.trigger(0, 100, "pointer", key));
    await tickRetainedUntil(f, () => heldReply !== null);
    assert.equal(f.inputConsumed.has("1"), true, "Native consumed; SDK still has not observed its reply");
    assert.equal(f.physicalOwners.size, 1, "press consumption cannot repay physical release");
    if (delayedTimer) f.advanceClock(1000);
    else {
      await f.tick(1000);
      await tickRetainedUntil(f, () => f.session.diagnostics().state === "restart-required");
      assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT",
        "SDK fails before the original consuming response is delivered");
    }
    releaseReply();
    const result = await settleRetainedCall(f, press);
    assert.equal(result.error?.code, "HOST_TIMEOUT");
    await tickRetainedUntil(f, () => f.session.diagnostics().state === "restart-required");
    assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
    assert.deepEqual(outcomes, [], "expired probe cannot publish old recovery success");
    assert.equal(f.normal.filter(e => e.operation === "pattern.transport.input.request" && e.payload.kind === "press").length, 1);
    await finishFailedProfileOwner(f);
    assert.deepEqual([...f.inputConsumed].sort(), ["1", "2"]);
    const release = f.normal.find(e => e.operation === "pattern.transport.input.request" && e.payload.kind === "release");
    assert.equal(release.payload.held_press_sequence, "1");
    assert.equal(f.session.diagnostics().state, "restart-required");
  });
}

for (const unknown of [false, true]) {
  test(`profile recovery ${unknown ? "unknown admitted" : "known pre-enqueue"} error fails only its original probe`, async t => {
    const error = Object.assign(new Error("original probe admission failure"), {
      code: unknown ? "HOST_TIMEOUT" : "HOST_STATE_INVALID", details: {pending: unknown},
    });
    const f = profileRecoveryFixture(t, {
      beforeInputAdmission: e => !unknown && e.payload.kind === "press" ? {
        protocol_version: 1, request_id: e.request_id, ok: false,
        error: {code: error.code, message: error.message, details: error.details},
      } : undefined,
      admissionReply: (e, response) => {
        if (unknown && e.operation === "pattern.transport.input.request" && e.payload.kind === "press") throw error;
        return response;
      },
    });
    await activateInputProfile(f);
    await armProfileRecovery(f);
    f.state.inputComplete = true;
    const press = observeProfileCall(f.session.trigger(0, 100, "pointer", {}));
    const result = await settleRetainedCall(f, press);
    assert.equal(result.error?.code, error.code);
    await tickRetainedUntil(f, () => f.session.diagnostics().state === (unknown ? "restart-required" : "failed"));
    assert.equal(f.session.diagnostics().error_code, error.code);
    await finishFailedProfileOwner(f);
    assert.equal(f.inputEntries.size, unknown ? 2 : 0);
    assert.equal(f.normal.filter(e => e.operation === "pattern.transport.input.request" && e.payload.kind === "press").length, 1);
    const releases = [...f.normal, ...f.retained].filter(e =>
      e.operation === "pattern.transport.input.request" && e.payload.kind === "release");
    assert.deepEqual(releases.map(e => [e.payload.input_serial, e.payload.held_press_sequence]),
      unknown ? [["2", "1"]] : [], "ordinary and retained lanes together submit exactly one original Release");
  });
}

test("profile recovery late accepted admission after foreground invalidation owes an exact release", async t => {
  let deliverAdmission;
  let originalReply = null;
  const gate = new Promise(resolve => { deliverAdmission = resolve; });
  const f = profileRecoveryFixture(t, {admissionReply: (e, response) => {
    if (e.operation === "pattern.transport.input.request" && e.payload.kind === "press") {
      originalReply = response;
      return gate.then(() => response);
    }
    return response;
  }});
  t.after(() => deliverAdmission());
  await activateInputProfile(f);
  await armProfileRecovery(f);
  f.state.inputComplete = true;
  const outcomes = [];
  f.session.subscribeRuntimeOutcome(value => outcomes.push(value));
  const first = observeProfileCall(f.session.trigger(0, 100, "pointer", {}));
  await tickRetainedUntil(f, () => originalReply !== null);
  // A real visibility edge invalidates ownership before admission returns.
  f.setVisibility(true);
  deliverAdmission();
  await settleRetainedCall(f, first);
  await tickRetainedUntil(f, () => f.inputConsumed.size === 2 && f.physicalOwners.size === 0);
  assert.deepEqual(outcomes, [], "late old epoch cannot publish success");
  assert.equal(f.session.diagnostics().error_code, null);
  assert.notEqual(f.session.diagnostics().state, "running");
  assert.deepEqual(f.normal.filter(e => e.operation === "pattern.transport.input.request")
    .map(e => [e.payload.kind, e.payload.held_press_sequence]), [["press", null], ["release", "1"]]);
  f.setVisibility(false);
  await tickRetainedUntil(f, () => f.session.diagnostics().recovery_probe_ready);
  // The original Release consumed during recovery must not become a probe.
  assert.equal(f.session.diagnostics().state, "recovering");
  assert.equal(await settleRetainedCall(f, f.session.close()), true);
});

test("profile recovery reserves one pending Press and only healthy exact success completes it", async t => {
  let deliverAdmission;
  let originalReply = null;
  const gate = new Promise(resolve => { deliverAdmission = resolve; });
  const f = profileRecoveryFixture(t, {admissionReply: (e, response) => {
    if (e.operation === "pattern.transport.input.request" && e.payload.kind === "press") {
      originalReply = response;
      return gate.then(() => response);
    }
    return response;
  }});
  t.after(() => deliverAdmission());
  await activateInputProfile(f);
  await armProfileRecovery(f);
  f.state.inputComplete = true;
  const outcomes = [];
  f.session.subscribeRuntimeOutcome(value => outcomes.push(value));
  const key = {};
  const first = observeProfileCall(f.session.trigger(0, 100, "pointer", key));
  await tickRetainedUntil(f, () => originalReply !== null);
  const duplicate = observeProfileCall(f.session.trigger(1, 100, "pointer", {}));
  assert.equal(f.inputEntries.size, 1, "one genuine admission owns the pending recovery window");
  assert.equal(f.session.diagnostics().recovery_probe_ready, false);
  deliverAdmission();
  assert.equal((await settleRetainedCall(f, first)).value.sequence, 1);
  // Once the first succeeds the queued second is an ordinary real Pad; it
  // must not be classified as a second recovery probe while admission waits.
  const second = await settleRetainedCall(f, duplicate);
  assert.equal(f.session.diagnostics().state, "running");
  assert.equal(f.session.diagnostics().error_code, null);
  assert.equal(outcomes[0].sequence, 1);
  assert.equal(await settleRetainedCall(f, f.session.release(0, "pointer", key)), true);
  if (second.value !== false) assert.equal(await settleRetainedCall(f, f.session.release(1, "pointer")), true);
  assert.equal(await settleRetainedCall(f, f.session.close()), true);
});

test("ordinary profile Pad deadline remains nonfatal with genuine later consume and release", async t => {
  const f = profileRecoveryFixture(t);
  await activateInputProfile(f);
  const key = {};
  const press = observeProfileCall(f.session.trigger(0, 100, "pointer", key));
  await tickRetainedUntil(f, () => f.inputEntries.size === 1);
  await f.tick(1000);
  assert.equal((await settleRetainedCall(f, press)).error?.code, "HOST_TIMEOUT");
  assert.equal(f.session.diagnostics().state, "running");
  assert.equal(f.session.diagnostics().error_code, null);
  assert.equal(f.inputConsumed.size, 0);
  assert.equal(f.physicalOwners.size, 1);
  const release = observeProfileCall(f.session.release(0, "pointer", key));
  await tickRetainedUntil(f, () => f.inputEntries.size === 2);
  f.state.inputComplete = true;
  assert.equal((await settleRetainedCall(f, release)).value, true);
  await tickRetainedUntil(f, () => f.inputConsumed.size === 2);
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(f.session.diagnostics().state, "running");
  assert.equal(await settleRetainedCall(f, f.session.close()), true);
});


test("profile recovery real close invalidates a held consuming reply without successful resurrection", async t => {
  let deliverConsume;
  let actualConsumedReply = null;
  const gate = new Promise(resolve => { deliverConsume = resolve; });
  const f = profileRecoveryFixture(t, {inputReply: (e, response) => {
    if (e.payload.consume && e.payload.ticket === "1") {
      actualConsumedReply = response;
      return gate.then(() => response);
    }
    return response;
  }});
  t.after(() => deliverConsume());
  await activateInputProfile(f);
  await armProfileRecovery(f);
  f.state.inputComplete = true;
  const outcomes = [];
  f.session.subscribeRuntimeOutcome(value => outcomes.push(value));
  const press = observeProfileCall(f.session.trigger(0, 100, "pointer", {}));
  await tickRetainedUntil(f, () => actualConsumedReply !== null);
  assert.equal(f.inputConsumed.has("1"), true);
  const close = observeProfileCall(f.session.close());
  await tickRetainedUntil(f, () => f.physicalOwners.size === 0 && f.inputConsumed.has("2"));
  deliverConsume();
  await settleRetainedCall(f, press);
  assert.equal((await settleRetainedCall(f, close)).value, true);
  assert.deepEqual(outcomes, []);
  assert.equal(f.session.diagnostics().state, "closed");
  assert.equal(f.session.diagnostics().error_code, null);
  assert.equal(f.state.backendCloses, 1);
});


test("profile recovery actual voice capacity fails with its original code and consumed evidence", async t => {
  const f = profileRecoveryFixture(t, {inputDisposition: p => p.kind === "press" ? "voice_capacity" : "release_no_voice"});
  await activateInputProfile(f);
  await armProfileRecovery(f);
  f.state.inputComplete = true;
  const outcomes = [];
  f.session.subscribeRuntimeOutcome(value => outcomes.push(value));
  const result = await settleRetainedCall(f, observeProfileCall(f.session.trigger(0, 100, "pointer", {})));
  assert.equal(result.error?.code, "HOST_STATE_INVALID");
  await tickRetainedUntil(f, () => f.session.diagnostics().state === "failed");
  assert.equal(f.session.diagnostics().error_code, "HOST_STATE_INVALID");
  assert.deepEqual(outcomes.map(value => value.outcome), ["voice_capacity"], "actual failure outcome is not recovery success");
  await finishFailedProfileOwner(f);
  assert.equal(f.inputConsumed.size, 2);
});

// Replacement eligibility is a local observation of the original cleanup,
// independent of the public fatal close(false) result and of Native tickets.
test("terminal cleanup waiter before initiation is false and starts no work", async () => {
  const sent = [];
  const f = fixture({send: async (envelope) => {
    sent.push(envelope); return success(envelope, defaultResult(envelope.operation));
  }});
  assert.equal(await f.session.waitForTerminalCleanup(), false);
  assert.equal(f.terminated(), 0);
  assert.equal(sent.length, 0);
  assert.equal(await f.session.start(), true);
  assert.equal(await f.session.waitForTerminalCleanup(), false);
  assert.equal(f.terminated(), 0);
  assert.equal(sent.length, 0);
  assert.equal(await f.session.close(), true);
  assert.equal(await f.session.waitForTerminalCleanup(), true,
    "the separately supported older normal-close contract remains compatible");
});

for (const phase of ["manifest", "capability", "preflight"]) {
  test(`closing while ${phase} is pending cannot load or publish a late owner`, async () => {
    let releasePhase;
    const phasePending = new Promise((resolve) => { releasePhase = resolve; });
    let entered = false;
    let loads = 0;
    const browserWindow = {};
    const hold = async () => { entered = true; await phasePending; };
    const f = fixture({browserWindow, publishRuntime: true,
      ...(phase === "manifest" ? {beforeManifest: hold} :
        phase === "capability" ? {capabilities: {secureContext: hold}} : {preflight: hold}),
      beforeRuntimeLoad: () => { loads += 1; }});
    const starting = f.session.start();
    for (let turn = 0; turn < 40 && !entered; ++turn) await drainTasks();
    assert.equal(entered, true);
    assert.equal(await f.session.close(), true);
    assert.equal(await f.session.waitForTerminalCleanup(), true);
    assert.equal(loads, 0);
    assert.equal(browserWindow.lmdjWebRuntimeHost, undefined);
    releasePhase();
    assert.equal(await starting, false, "the original closed bootstrap cannot resume into a new owner");
    assert.equal(loads, 0, "far-side original loader was never invoked");
    assert.equal(browserWindow.lmdjWebRuntimeHost, undefined);
    assert.equal(f.session.diagnostics().state, "closed");
    assert.equal(f.terminated(), 1);
  });
}

test("cleanup waits an already invoked loader and retires its actual late published owner", async () => {
  let releaseLoad;
  const loadPending = new Promise((resolve) => { releaseLoad = resolve; });
  let entered = false;
  let releaseOwner;
  const ownerPending = new Promise((resolve) => { releaseOwner = resolve; });
  let sealed = false;
  let fullReceipt = false;
  const ownerTransport = {
    get terminated() { return sealed; },
    get terminalOwnerReleased() { return fullReceipt; },
    async send(envelope) { return success(envelope, defaultResult(envelope.operation)); },
  };
  const browserWindow = {};
  let terminatedRuntime = null;
  const f = fixture({browserWindow, publishRuntime: true, sessionTransport: ownerTransport,
    runtimeTransport: ownerTransport,
    beforeRuntimeLoad: async () => { entered = true; await loadPending; },
    runtimeTerminator: async ({runtime}) => {
      terminatedRuntime = runtime;
      sealed = true;
      await ownerPending;
      fullReceipt = true;
    }});
  const starting = f.session.start();
  for (let turn = 0; turn < 40 && !entered; ++turn) await drainTasks();
  assert.equal(entered, true);
  let closed = null;
  const closing = f.session.close().then((value) => { closed = value; });
  await drainTasks();
  await drainTasks();
  let eligible = null;
  const waiting = f.session.waitForTerminalCleanup().then((value) => { eligible = value; });
  await drainTasks();
  assert.equal(closed, null);
  assert.equal(eligible, null, "an invoked loader's null result is not never-loaded evidence");
  assert.equal(f.terminated(), 0, "the actual late owner has not been handed back yet");
  releaseLoad();
  assert.equal(await starting, false);
  for (let turn = 0; turn < 40 && terminatedRuntime === null; ++turn) await drainTasks();
  assert.equal(terminatedRuntime, browserWindow.lmdjWebRuntimeHost);
  assert.ok(terminatedRuntime);
  assert.equal(terminatedRuntime.session, undefined, "the retired bootstrap must not publish a live SDK namespace");
  assert.equal(fullReceipt, false);
  assert.equal(eligible, null);
  releaseOwner();
  for (let turn = 0; turn < 40 && (closed === null || eligible === null); ++turn) await drainTasks();
  assert.notEqual(closed, null);
  assert.notEqual(eligible, null);
  await Promise.all([closing, waiting]);
  assert.equal(closed, true);
  assert.equal(eligible, true);
  assert.equal(f.terminated(), 1);
});

test("attempted loader rejection cannot obtain replacement permission from absent runtime", async () => {
  const loaderError = Object.assign(new Error("actual loader failed"), {code: "IO_ERROR"});
  const f = fixture({beforeRuntimeLoad: () => { throw loaderError; }});
  assert.equal(await f.session.start(), false);
  for (let turn = 0; turn < 40 && f.terminated() === 0; ++turn) await drainTasks();
  assert.equal(f.terminated(), 1, "original safety and actual cleanup have begun before observing its result");
  assert.equal(await f.session.waitForTerminalCleanup(), false);
  assert.equal(f.session.diagnostics().error_code, "IO_ERROR");
});

test("fatal waiter retains physical input and count debt through genuine consume then Native and backend closure", async (t) => {
  const f = retainedConsumerFixture({countMode: "accepted-response-loss"});
  t.after(() => f.cancelTimers());
  let releaseBackend;
  const backendPending = new Promise((resolve) => { releaseBackend = resolve; });
  let backendStarted = 0;
  const actualClose = f.context.close.bind(f.context);
  f.context.close = async () => { backendStarted += 1; await backendPending; return actualClose(); };
  await activateInputProfile(f);
  f.state.completeInput = (payload) => payload.kind === "press" || f.state.inputComplete;
  assert.equal((await f.session.trigger(0, 100, "pointer")).sequence, 1);
  assert.deepEqual([...f.inputConsumed], ["1"]);
  assert.equal(f.physicalOwners.size, 1);
  await assert.rejects(f.session.requestPatternCountIn(countInRequest()), (error) => error === f.originalError);
  await tickRetainedUntil(f, () => f.inputEntries.size === 2 && f.state.terminalStarts === 1);
  assert.equal(await f.session.close(), false, "retained caller debt still returns prompt fatal false");
  const originalWait = f.session.waitForTerminalCleanup();
  assert.equal(f.session.waitForTerminalCleanup(), originalWait, "duplicate callers observe one actual cleanup");
  let outcome = null;
  void originalWait.then((value) => { outcome = value; });
  await f.tick();
  assert.equal(outcome, null);
  assert.equal(f.physicalOwners.size, 1);
  assert.equal(f.state.countConsumed, false);
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(backendStarted, 0);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  f.state.countStatus = failedOriginalCountInEvidence();
  f.state.inputComplete = true;
  await tickRetainedUntil(f, () => f.inputConsumed.size === 2);
  assert.equal(f.physicalOwners.size, 0);
  assert.equal(f.state.countConsumed, false, "physical Release does not consume the separate count caller");
  assert.equal(outcome, null);
  f.state.nativeOwnerAcknowledged = true;
  await tickRetainedUntil(f, () => f.state.countConsumed);
  assert.equal(f.transport.terminalOwnerReleased, false, "all genuine consumers are not the separate full owner receipt");
  assert.equal(outcome, null);
  f.releaseTerminal();
  await tickRetainedUntil(f, () => backendStarted === 1);
  assert.equal(f.context.state, "running");
  assert.equal(outcome, null, "full Native receipt is not an AudioContext close receipt");
  releaseBackend();
  await tickRetainedUntil(f, () => outcome !== null);
  assert.equal(await originalWait, true);
  assert.equal(f.context.state, "closed");
  assert.equal(f.state.backendCloses, 1);
  assert.equal(f.state.terminalStarts, 1);
  assert.ok(f.nodes.every((node) => node.disconnected.length === 1));
  assert.deepEqual([...f.inputConsumed], ["1", "2"]);
  const original = f.inputEntries.get("1");
  const release = f.inputEntries.get("2");
  assert.deepEqual([release.payload.slot, release.payload.runtime_generation, release.payload.frame_epoch,
    release.payload.held_press_sequence], [original.payload.slot, original.payload.runtime_generation,
      original.payload.frame_epoch, original.status.admission.sequence]);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  assert.equal(await f.session.close(), false);
});

for (const failure of ["termination", "backend"]) {
  test(`fatal waiter is false after actual ${failure} rejection and keeps the first error`, async (t) => {
    const cleanupError = Object.assign(new Error("actual cleanup rejected"), {code: "IO_ERROR"});
    const f = retainedConsumerFixture(failure === "termination"
      ? {terminate: () => { throw cleanupError; }} : {});
    t.after(() => f.cancelTimers());
    await activateInputProfile(f);
    if (failure === "backend") f.context.close = async () => { throw cleanupError; };
    f.seal();
    await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
    const waiting = f.session.waitForTerminalCleanup();
    if (failure === "backend") { f.state.nativeOwnerAcknowledged = true; f.releaseTerminal(); }
    assert.equal(await settleRetainedCall(f, waiting), false);
    assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
    assert.equal(f.context.state, "running");
    assert.equal(f.state.backendCloses, 0);
    assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
    assert.equal(f.state.terminalStarts, 1);
  });
}

test("resolved terminator waiter stays pending without Native ACK and false with a still open backend", async (t) => {
  const f = retainedConsumerFixture({terminate: async () => {}});
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.seal();
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  let outcome = null;
  const waiting = f.session.waitForTerminalCleanup().then((value) => { outcome = value; });
  await f.tick();
  assert.equal(outcome, null);
  assert.equal(f.transport.terminalOwnerReleased, false);
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  await tickRetainedUntil(f, () => outcome !== null);
  await waiting;
  assert.equal(outcome, false);
  assert.equal(f.context.state, "running");
  assert.ok(f.nodes.every((node) => node.disconnected.length === 0));
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
});

test("synchronous terminator reentry sees the same bound pending cleanup waiter", async (t) => {
  let reentrantWait;
  let outcome = null;
  let releaseTermination;
  const terminationPending = new Promise((resolve) => { releaseTermination = resolve; });
  const f = retainedConsumerFixture({terminate: async ({audioContext}) => {
    reentrantWait = f.session.waitForTerminalCleanup();
    void reentrantWait.then((value) => { outcome = value; });
    await terminationPending;
    await audioContext.close();
  }});
  t.after(() => f.cancelTimers());
  await activateInputProfile(f);
  f.seal();
  await tickRetainedUntil(f, () => f.state.terminalStarts === 1);
  assert.ok(reentrantWait, "the real terminator synchronously entered the local observer");
  assert.equal(f.session.waitForTerminalCleanup(), reentrantWait);
  await f.tick();
  assert.equal(outcome, null, "reentrant null/unbound Promise cannot mean completed cleanup");
  assert.equal(f.transport.terminalOwnerReleased, false);
  assert.equal(f.context.state, "running");
  f.state.nativeOwnerAcknowledged = true;
  f.releaseTerminal();
  assert.equal(outcome, null);
  releaseTermination();
  await tickRetainedUntil(f, () => outcome !== null);
  assert.equal(await reentrantWait, true);
  assert.equal(f.context.state, "closed");
  assert.equal(f.state.backendCloses, 1);
  assert.equal(f.state.terminalStarts, 1);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
});


test("late rejected load retires its actually published partial owner without granting success", async () => {
  const browserWindow = {};
  const loaderError = Object.assign(new Error("partial actual loader failed"), {code: "IO_ERROR"});
  let releaseOwner;
  const ownerPending = new Promise((resolve) => { releaseOwner = resolve; });
  let fullReceipt = false;
  let sealed = false;
  const ownerTransport = {
    get terminated() { return sealed; },
    get terminalOwnerReleased() { return fullReceipt; },
    async send(envelope) { return success(envelope, defaultResult(envelope.operation)); },
  };
  const partialOwner = {transport: ownerTransport, workers: []};
  let terminatedRuntime;
  const f = fixture({browserWindow, sessionTransport: ownerTransport,
    beforeRuntimeLoad: (invocation) => {
      invocation.onRuntimeOwnerCreated(partialOwner);
      browserWindow.lmdjWebRuntimeHost = partialOwner;
      throw loaderError;
    },
    runtimeTerminator: async ({runtime}) => {
      terminatedRuntime = runtime;
      sealed = true;
      await ownerPending;
      fullReceipt = true;
    }});
  assert.equal(await f.session.start(), false);
  for (let turn = 0; turn < 40 && f.terminated() === 0; ++turn) await drainTasks();
  assert.equal(f.terminated(), 1, "the original fatal safety has reached actual terminal cleanup");
  let outcome = null;
  const waiting = f.session.waitForTerminalCleanup().then((value) => { outcome = value; });
  await drainTasks();
  assert.equal(terminatedRuntime, partialOwner, "the real partial published owner was not discarded on rejection");
  assert.equal(fullReceipt, false);
  assert.equal(outcome, null, "published resources still require their original termination");
  releaseOwner();
  for (let turn = 0; turn < 40 && outcome === null; ++turn) await drainTasks();
  assert.notEqual(outcome, null);
  await waiting;
  assert.equal(fullReceipt, true);
  assert.equal(outcome, false, "actual loader failure is not a successful closure eligibility result");
  assert.equal(f.session.diagnostics().error_code, "IO_ERROR");
  assert.equal(f.terminated(), 1);
});

test("healthy older normal closure observes actual backend closure without inventing a Native getter", async () => {
  let backendCloses = 0;
  const f = fixture({runtimeTerminator: async ({audioContext}) => { await audioContext.close(); }});
  f.context.close = async () => { backendCloses += 1; f.context.state = "closed"; };
  await activateInputProfile(f);
  assert.equal(f.context.state, "running");
  assert.equal(await f.session.waitForTerminalCleanup(), false);
  assert.equal(await f.session.close(), true);
  assert.equal(await f.session.waitForTerminalCleanup(), true);
  assert.equal(f.context.state, "closed");
  assert.equal(backendCloses, 1);
  assert.equal(f.terminated(), 1);
  assert.equal(f.session.diagnostics().error_code, null);
});

for (const publication of ["prior", "other-session"]) {
  test(`failed custom loader never terminates or borrows ${publication} global Host`, async () => {
    let foreignTerminations = 0;
    const foreign = {transport: {
      get terminalOwnerReleased() { return true; },
      terminate() { foreignTerminations += 1; },
    }, workers: [{terminate() { foreignTerminations += 1; }}]};
    const browserWindow = publication === "prior" ? {lmdjWebRuntimeHost: foreign} : {};
    const loaderError = Object.assign(new Error("this invocation actually rejected"), {code: "IO_ERROR"});
    let actualTerminatorRuntime;
    const f = fixture({browserWindow,
      beforeRuntimeLoad: () => {
        if (publication === "other-session") browserWindow.lmdjWebRuntimeHost = foreign;
        throw loaderError; // No producer registration means no identity claim.
      },
      runtimeTerminator: ({runtime}) => {
        actualTerminatorRuntime = runtime;
        runtime?.transport?.terminate?.();
        for (const worker of runtime?.workers ?? []) worker.terminate();
      }});
    assert.equal(await f.session.start(), false);
    for (let turn = 0; turn < 40 && f.terminated() === 0; ++turn) await drainTasks();
    assert.equal(f.terminated(), 1);
    assert.equal(await f.session.waitForTerminalCleanup(), false);
    assert.equal(actualTerminatorRuntime, null, "global identity is not this invocation's owned partial runtime");
    assert.equal(foreignTerminations, 0, "no direct or formal termination of an unrelated Host");
    assert.equal(browserWindow.lmdjWebRuntimeHost, foreign);
    assert.equal(f.session.diagnostics().error_code, "IO_ERROR");
  });
}

test("pressed-state reentry observes the bound original cleanup before actual terminator entry", async () => {
  let latestWait;
  let outcome = null;
  let releaseBackend;
  const backendPending = new Promise((resolve) => { releaseBackend = resolve; });
  const f = fixture({
    onPressedChange: () => { latestWait = f.session.waitForTerminalCleanup(); },
    runtimeTerminator: async ({audioContext}) => { await backendPending; await audioContext.close(); },
  });
  f.context.close = async () => { f.context.state = "closed"; };
  await activateInputProfile(f);
  const closing = f.session.close();
  for (let turn = 0; turn < 40 && f.terminated() === 0; ++turn) await drainTasks();
  assert.equal(f.terminated(), 1);
  assert.equal(latestWait, f.session.waitForTerminalCleanup(),
    "clearPressed external callback cannot observe an initiated cleanup as unbound false");
  void latestWait.then((value) => { outcome = value; });
  await drainTasks();
  assert.equal(outcome, null);
  assert.equal(f.context.state, "running");
  releaseBackend();
  assert.equal(await closing, true);
  assert.equal(await latestWait, true);
  assert.equal(f.context.state, "closed");
});

async function packagedLoaderFixture() {
  const wasmBytes = new Uint8Array([0]);
  const wasmDigest = [...new Uint8Array(await webcrypto.subtle.digest("SHA-256", wasmBytes))]
    .map((value) => value.toString(16).padStart(2, "0")).join("");
  const manifest = {
    host_id: "web-runtime-host", host_version: "1.2.15", platform_version: "0.3.6",
    product_build: TEST_PRODUCT_BUILD, protocol_version: 1,
    canonical_bytes: new Uint8Array([1]), manifest_sha256: "0".repeat(64),
    assets: [
      {role: "runtime_script", path: "runtime.js", bytes: 1, sha256: "0".repeat(64)},
      {role: "runtime_wasm", path: "runtime.wasm", bytes: wasmBytes.length, sha256: wasmDigest},
    ],
  };
  const scripts = [];
  const browserWindow = {
    fetch: async () => new Response(wasmBytes), btoa: globalThis.btoa,
    performance: globalThis.performance, setTimeout, clearTimeout,
  };
  const browserDocument = {
    baseURI: "https://example.test/index.html",
    createElement: () => new EventTarget(),
    head: {append(script) { scripts.push({script, configuration: browserWindow.Module}); }},
  };
  const newOwner = () => ({
    runtimeInitialized: true, registerAudioContext: () => 1,
    audioCallbackHeartbeat: () => 1, startAudioWorklet: async () => ({ok: true}),
    workers: [], transport: {send: async (envelope) => success(envelope, defaultResult(envelope.operation))},
  });
  return {browserWindow, browserDocument, scripts, newOwner,
    makeSession(runtimeTerminator) {
      return fixture({browserWindow, browserDocument, useDefaultRuntimeLoader: true,
        verifiedManifest: manifest, runtimeTerminator});
    },
    publish(index, owner = newOwner()) {
      const {script, configuration} = scripts[index];
      configuration.lmdjRuntimeOwnerCreated(owner, configuration);
      browserWindow.lmdjWebRuntimeHost = owner;
      script.dispatchEvent(new Event("load"));
      return owner;
    }};
}

test("two default packaged loaders cannot overwrite one in-flight producer Module and release the real load reservation", async () => {
  const p = await packagedLoaderFixture();
  let retiredFirst;
  const first = p.makeSession(({runtime}) => { retiredFirst = runtime; });
  const firstStart = first.session.start();
  for (let turn = 0; turn < 40 && p.scripts.length === 0; ++turn) await drainTasks();
  assert.equal(p.scripts.length, 1);
  const firstConfiguration = p.scripts[0].configuration;
  let retiredOther;
  const other = p.makeSession(({runtime}) => { retiredOther = runtime; });
  let otherOutcome = null;
  const otherStart = other.session.start().then((value) => { otherOutcome = {value}; },
    (error) => { otherOutcome = {error}; });
  for (let turn = 0; turn < 40 && otherOutcome === null && p.scripts.length === 1; ++turn) await drainTasks();
  assert.equal(p.scripts.length, 1, "the second loader is refused before another script can own shared Module");
  assert.deepEqual(otherOutcome, {value: false});
  await otherStart;
  for (let turn = 0; turn < 40 && other.terminated() === 0; ++turn) await drainTasks();
  assert.equal(other.terminated(), 1);
  assert.equal(await other.session.waitForTerminalCleanup(), false);
  assert.equal(retiredOther, null);
  assert.equal(p.browserWindow.Module, firstConfiguration,
    "a second loader cannot redirect the original script into a foreign configuration");
  assert.equal(p.scripts.length, 1);
  assert.equal(retiredFirst, undefined);
  const firstOwner = p.publish(0);
  assert.equal(await firstStart, true);
  assert.equal(p.browserWindow.lmdjWebRuntimeHost, firstOwner);
  assert.equal(firstOwner.session, first.session);
  assert.equal(await first.session.close(), true);
  assert.equal(retiredFirst, firstOwner);
  const later = p.makeSession();
  const laterStart = later.session.start();
  for (let turn = 0; turn < 40 && p.scripts.length < 2; ++turn) await drainTasks();
  assert.equal(p.scripts.length, 2, "completed original invocation releases its actual single-flight reservation");
  const laterOwner = p.publish(1);
  assert.notEqual(laterOwner, firstOwner);
  assert.equal(await laterStart, true);
  assert.equal(await later.session.close(), true);
});

test("default packaged load rejects a foreign Module callback and never adopts a global foreign owner", async () => {
  const p = await packagedLoaderFixture();
  let actualTerminatorRuntime;
  const f = p.makeSession(({runtime}) => { actualTerminatorRuntime = runtime; });
  const starting = f.session.start();
  for (let turn = 0; turn < 40 && p.scripts.length === 0; ++turn) await drainTasks();
  assert.equal(p.scripts.length, 1);
  const foreign = p.newOwner();
  p.browserWindow.lmdjWebRuntimeHost = foreign;
  assert.throws(() => p.scripts[0].configuration.lmdjRuntimeOwnerCreated(foreign, {}),
    (error) => error.code === "HOST_STATE_INVALID");
  p.scripts[0].script.dispatchEvent(new Event("error"));
  assert.equal(await starting, false);
  for (let turn = 0; turn < 40 && f.terminated() === 0; ++turn) await drainTasks();
  assert.equal(f.terminated(), 1);
  assert.equal(await f.session.waitForTerminalCleanup(), false);
  assert.equal(actualTerminatorRuntime, null);
  assert.equal(p.browserWindow.lmdjWebRuntimeHost, foreign);
  assert.equal(foreign.session, undefined);
});

// ---------------------------------------------------------------------------
// D0/W1 typed live-control producer oracles.
// ---------------------------------------------------------------------------

const LIVE_EPOCH = "40000000-0000-4000-8000-000000000001";
const LIVE_STATE_WIRE = {
  hold: false,
  filter: {mode: "legacy", engaged: false, frozen: false, value: 0},
  other_fx: Object.fromEntries(
    ["delay", "reverb", "stutter", "gate", "reverse", "crush", "cutter"]
      .map((name) => [name, {engaged: false, frozen: false, value: 0}])),
  muted_slots: [],
  solo_slots: [],
};

test("typed live control serializes exactly and tracks the CAS window", async () => {
  const operations = [];
  let liveSequence = 0;
  const {session} = fixture({
    send: async (envelope) => {
      operations.push(envelope);
      switch (envelope.operation) {
        case "performance.live.status":
          return success(envelope, {
            available: true,
            control_epoch: LIVE_EPOCH,
            accepted: LIVE_STATE_WIRE,
            applied: LIVE_STATE_WIRE,
            runtime_generations: Object.fromEntries(
              ["crush", "cutter", "delay", "filter", "gate", "reverse",
                "reverb", "stutter"].map((name) => [name, null])),
            accepted_control_sequence: String(liveSequence),
            applied_control_sequence: String(liveSequence),
            reset_pending: false,
            begin_pending: false,
            project_revision: null,
          });
        case "performance.live.control": {
          // A replayed receipt does not advance the SDK's window.
          const replayed = envelope.payload.intent.kind === "hold_off";
          liveSequence += replayed ? 0 : 1;
          return success(envelope, {
            command_id: envelope.payload.command_id,
            control_epoch: envelope.payload.control_epoch,
            control_sequence: String(liveSequence),
            gesture_generation: null,
            accepted: true,
            applied: false,
            replayed,
            project_revision: null,
          });
        }
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    },
  });
  await session.start();
  const status = await session.queryPerformanceLiveStatus();
  assert.equal(status.available, true);
  assert.equal(status.controlEpoch, LIVE_EPOCH);
  assert.equal(status.accepted.hold, false);
  assert.equal(status.appliedControlSequence, "0");

  const first = await session.applyPerformanceLiveControl({
    controlEpoch: LIVE_EPOCH,
    intent: {kind: "pad_mute", slot: 7, enabled: true},
  });
  assert.equal(first.accepted, true);
  assert.equal(first.replayed, false);
  const wired = operations.find(
    ({operation}) => operation === "performance.live.control").payload;
  assert.deepEqual(wired, {
    control_epoch: LIVE_EPOCH,
    command_id: wired.command_id,
    expected_control_sequence: "0",
    intent: {kind: "pad_mute", slot: 7, enabled: true},
  });

  // The same-identity replay does not advance the window.
  const replayed = await session.applyPerformanceLiveControl({
    controlEpoch: LIVE_EPOCH,
    intent: {kind: "hold_off"},
  });
  assert.equal(replayed.replayed, true);
  const third = await session.applyPerformanceLiveControl({
    controlEpoch: LIVE_EPOCH,
    intent: {kind: "hold_on"},
  });
  assert.equal(third.replayed, false);
  const envelopes = operations.filter(
    ({operation}) => operation === "performance.live.control");
  assert.equal(envelopes[1].payload.expected_control_sequence, "1");
  assert.equal(envelopes[2].payload.expected_control_sequence, "1");

  // A closed session rejects new inputs without sending anything.
  await session.close();
  const before = operations.length;
  await assert.rejects(
    session.applyPerformanceLiveControl({
      controlEpoch: LIVE_EPOCH,
      intent: {kind: "hold_on"},
    }),
    (error) => error.code === "HOST_STATE_INVALID",
  );
  assert.equal(operations.length, before);
});

test("bounded live-input window rejects overflow, never drops releases, and cleanup rejects the waiting input", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000010";
  const performanceId = "40000000-0000-4000-8000-000000000011";
  const order = [];
  let gateResolve = null;
  let gate = null;
  const {session} = fixture({
    send: async (envelope) => {
      switch (envelope.operation) {
        case "performance.record.begin":
          return success(envelope, {
            performance_id: performanceId,
            committed_revision: 1,
            replayed: false,
            project_revision: 1,
          });
        case "performance.record.event":
          order.push(envelope.payload.event.kind);
          if (gate !== null) await gate;
          return success(envelope, {
            event_id: envelope.payload.event_id,
            accepted_tick: 0,
            input_sequence: 1,
            coalesced: false,
            replayed: false,
            project_revision: null,
          });
        case "performance.record.stop":
          order.push("stop");
          return success(envelope, {
            request_id: envelope.payload.request_id,
            session_id: sessionId,
            performance_id: performanceId,
            state: "stopped",
            pending_event_count: 0,
            replayed: false,
            project_revision: null,
          });
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    },
  });
  await session.start();
  await session.beginPerformanceRecording({
    sessionId, performanceId, expectedRevision: 0,
  });

  // The first event inflight holds the gate; one ordinary waits; the next
  // ordinary input is explicitly refused.
  gate = new Promise((resolve) => { gateResolve = resolve; });
  const press = session.recordPerformanceEvent({
    sessionId,
    eventId: "40000000-0000-4000-8000-000000000020",
    event: {kind: "pad_press", gestureId: "40000000-0000-4000-8000-000000000021", slot: 1, velocity: 100},
  });
  const waiting = session.recordPerformanceEvent({
    sessionId,
    eventId: "40000000-0000-4000-8000-000000000022",
    event: {kind: "hold_on"},
  });
  await assert.rejects(
    session.recordPerformanceEvent({
      sessionId,
      eventId: "40000000-0000-4000-8000-000000000023",
      event: {kind: "hold_off"},
    }),
    /window is full/,
  );
  // The matching release always fits its reserved slot.
  const release = session.recordPerformanceEvent({
    sessionId,
    eventId: "40000000-0000-4000-8000-000000000024",
    event: {kind: "pad_release", gestureId: "40000000-0000-4000-8000-000000000021", slot: 1},
  });
  gateResolve();
  gate = null;
  await press;
  await waiting;
  await release;
  assert.deepEqual(order, ["pad_press", "hold_on", "pad_release"]);
  // Let the lane's completion bookkeeping settle before the next window.
  await drainTasks();

  // The cleanup token rejects a never-admitted waiting input explicitly and
  // still completes after the admitted work.
  gate = new Promise((resolve) => { gateResolve = resolve; });
  const admitted = session.recordPerformanceEvent({
    sessionId,
    eventId: "40000000-0000-4000-8000-000000000025",
    event: {kind: "hold_on"},
  });
  const cancelled = session.recordPerformanceEvent({
    sessionId,
    eventId: "40000000-0000-4000-8000-000000000026",
    event: {kind: "hold_off"},
  });
  const stopping = session.stopPerformanceRecording({
    sessionId,
    requestId: "40000000-0000-4000-8000-000000000027",
  });
  await assert.rejects(cancelled, /cancelled before Core admission/);
  gateResolve();
  gate = null;
  await admitted;
  await stopping;
  assert.deepEqual(order.slice(-2), ["hold_on", "stop"]);
  await session.close();
});

function performanceEventQueueFixture() {
  const sessionId = "40000000-0000-4000-8000-000000000090";
  const performanceId = "40000000-0000-4000-8000-000000000091";
  const state = {clock: 0, events: [], queryStarted: null, releaseQuery: null};
  const started = new Promise((resolve) => { state.queryStarted = resolve; });
  const gate = new Promise((resolve) => { state.releaseQuery = resolve; });
  const {session} = fixture({
    now: () => state.clock,
    send: async (envelope, options) => {
      switch (envelope.operation) {
        case "project.inspect":
          state.queryStarted();
          await gate;
          return success(envelope, {project_revision: 7});
        case "performance.record.begin":
          return success(envelope, {performance_id: performanceId,
            committed_revision: 1, replayed: false, project_revision: 1});
        case "performance.record.event":
          state.events.push({submittedAt: state.clock, deadlineMs: options.deadlineMs});
          return success(envelope, {event_id: envelope.payload.event_id,
            accepted_tick: 0, input_sequence: 1, coalesced: false,
            replayed: false, project_revision: null});
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    },
  });
  const press = () => session.recordPerformanceEvent({sessionId,
    eventId: "40000000-0000-4000-8000-000000000092",
    event: {kind: "pad_press", gestureId: "40000000-0000-4000-8000-000000000093",
      slot: 1, velocity: 100}});
  return {session, state, sessionId, performanceId, press, started};
}

test("a Performance event submitted late in its Pad budget keeps the full Host liveness deadline", async () => {
  const f = performanceEventQueueFixture();
  await f.session.start();
  await f.session.beginPerformanceRecording({sessionId: f.sessionId,
    performanceId: f.performanceId, expectedRevision: 0});
  const query = f.session.inspectProject();
  await f.started;
  const press = f.press();
  await drainTasks();
  assert.equal(f.state.events.length, 0, "the Pad waited behind the independent Host query");
  f.state.clock = 980;
  f.state.releaseQuery();
  assert.equal((await query).project_revision, 7);
  await press;
  // An expired event deadline seals the Runtime, so 20 ms left of the Pad
  // budget must not become the Native watchdog for this event.
  assert.deepEqual(f.state.events, [{submittedAt: 980, deadlineMs: 1_000}]);
  await f.session.close();
});

test("a Performance event whose Pad budget expired in the Host queue is refused before submission", async () => {
  const f = performanceEventQueueFixture();
  await f.session.start();
  await f.session.beginPerformanceRecording({sessionId: f.sessionId,
    performanceId: f.performanceId, expectedRevision: 0});
  const query = f.session.inspectProject();
  await f.started;
  const press = f.press().then((value) => ({value}), (error) => ({error}));
  await drainTasks();
  f.state.clock = 1_001;
  f.state.releaseQuery();
  assert.equal((await query).project_revision, 7);
  const expired = await press;
  assert.equal(expired.error?.code, "HOST_TIMEOUT");
  assert.equal(expired.error.details.pending, false, "nothing was submitted to Native");
  assert.equal(f.state.events.length, 0);
  await f.session.close();
});

test("the 65th open Pad gesture is refused without an admission report", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000030";
  const performanceId = "40000000-0000-4000-8000-000000000031";
  const {session} = fixture({
    send: async (envelope) => {
      switch (envelope.operation) {
        case "performance.record.begin":
          return success(envelope, {
            performance_id: performanceId,
            committed_revision: 1,
            replayed: false,
            project_revision: 1,
          });
        case "performance.record.event":
          return success(envelope, {
            event_id: envelope.payload.event_id,
            accepted_tick: 0,
            input_sequence: 1,
            coalesced: false,
            replayed: false,
            project_revision: null,
          });
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    },
  });
  await session.start();
  await session.beginPerformanceRecording({
    sessionId, performanceId, expectedRevision: 0,
  });
  for (let pad = 0; pad < 64; pad += 1) {
    await session.recordPerformanceEvent({
      sessionId,
      eventId: `40000000-0000-4000-8000-${String(pad + 256).padStart(12, "0")}`,
      event: {
        kind: "pad_press",
        gestureId: `40000000-0000-4000-9000-${String(pad + 1).padStart(12, "0")}`,
        slot: pad,
        velocity: 100,
      },
    });
  }
  await assert.rejects(
    session.recordPerformanceEvent({
      sessionId,
      eventId: "40000000-0000-4000-8000-000000000321",
      event: {
        kind: "pad_press",
        gestureId: "40000000-0000-4000-9000-000000000065",
        slot: 0,
        velocity: 100,
      },
    }),
    /Too many open Pad gestures/,
  );
  await session.close();
});

test("the dual-ready gate parks recorded inputs until Core-ready and the started ACK both land", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000040";
  const performanceId = "40000000-0000-4000-8000-000000000041";
  let coreReady = false;
  let tapStarted = null;
  let tapBinding = null;
  let platformCapture = null;
  let captureStops = 0;
  let beginCommandId = null;
  const sentOperations = [];
  const tapController = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    start(sink, binding) {
      tapBinding = binding;
      return new Promise((resolve) => {
        platformCapture = {
          generation: 1,
          binding,
          stop: async () => { captureStops += 1; sink.onStopped(); },
        };
        tapStarted = () => resolve(platformCapture);
      });
    },
    failProcessor() {},
    async close() {},
  };
  const {session} = fixture({
    browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {
      resourceLimits: {
        perform_recording_frames: 86_400_000,
        perform_recording_queue_batches: 32,
      },
      performanceMasterTapUrl: "./assets/perform-master-tap.js",
    },
    createPerformanceMasterTap: async () => tapController,
    send: async (envelope) => {
      sentOperations.push(envelope.operation);
      switch (envelope.operation) {
        case "performance.record.begin":
          beginCommandId = envelope.payload.command_id;
          return success(envelope, {
            performance_id: performanceId,
            committed_revision: 1,
            replayed: false,
            profile: "header_input_sequence",
            control_epoch: LIVE_EPOCH,
            core_control_ready: false,
            next_recording_sequence: "0",
            fx_bindings: [],
            project_revision: 1,
          });
        case "performance.record.status":
          return success(envelope, {
            state: "active",
            session_id: sessionId,
            performance_id: performanceId,
            journal_revision: 1,
            next_flush_seq: 1,
            pending_event_count: 0,
            open_pad_gestures: 0,
            open_fx_gestures: 0,
            hold: false,
            pending_launch: null,
            last_launch_ack: null,
            profile: "header_input_sequence",
            control_epoch: LIVE_EPOCH,
            core_control_ready: coreReady,
            next_recording_sequence: "0",
            pending_admission: null,
            project_revision: null,
          });
        case "performance.record.event":
          return success(envelope, {
            event_id: envelope.payload.event_id,
            accepted_tick: 4,
            input_sequence: "1",
            next_recording_sequence: "1",
            result: "no_audio",
            coalesced: false,
            gesture_generation: null,
            recording_gesture_id: null,
            replayed: false,
            project_revision: null,
          });
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    },
  });
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));

  let beginSettled = false;
  const begin = session.beginPerformanceRecording({
    sessionId,
    performanceId,
    expectedRevision: 0,
    controlEpoch: LIVE_EPOCH,
    captureSink: {onBatch() {}, onStopped() {}, onFailure() {}},
  }).then((value) => {
    beginSettled = true;
    return value;
  });
  await drainTasks();
  assert.equal(beginSettled, false);

  // A recorded Pad parks in the window: zero delivery to the Host bridge.
  const parked = session.recordPerformanceEvent({
    sessionId,
    eventId: "40000000-0000-4000-8000-000000000042",
    event: {kind: "pad_press", gestureId: "40000000-0000-4000-8000-000000000043", slot: 2, velocity: 100},
  });
  await drainTasks();
  assert.equal(sentOperations.includes("performance.record.event"), false);

  // Core fence ready first: the capture ACK still holds the gate.
  coreReady = true;
  for (let attempt = 0; attempt < 20 && tapBinding === null; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  assert.notEqual(tapBinding, null);
  assert.equal(tapBinding.control_epoch, LIVE_EPOCH);
  assert.equal(tapBinding.session_id, sessionId);
  assert.equal(tapBinding.begin_command_id, beginCommandId);
  await drainTasks();
  assert.equal(beginSettled, false);
  assert.equal(sentOperations.includes("performance.record.event"), false);

  // The matching started ACK releases both.
  tapStarted();
  const begun = await begin;
  assert.equal(begun.coreControlReady, true);
  assert.equal(Object.isFrozen(begun), true);
  assert.equal(Object.isFrozen(begun.capture), true);
  assert.deepEqual(Object.keys(begun.capture), ["stop"]);
  assert.notEqual(begun.capture, platformCapture);
  await parked;
  assert.equal(sentOperations.includes("performance.record.event"), true);
  const eventEnvelope = sentOperations
    .map((operation, index) => ({operation, index}))
    .filter(({operation}) => operation === "performance.record.event");
  assert.equal(eventEnvelope.length, 1);
  const captureStop = begun.capture.stop();
  assert.equal(begun.capture.stop(), captureStop);
  await captureStop;
  assert.equal(captureStops, 1);
  await session.close();
  assert.equal(captureStops, 1);
});

test("legacy and no-sink headered begins retain exact result shapes and initial FX identities", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000050";
  const performanceId = "40000000-0000-4000-8000-000000000051";
  const gestureGeneration = "40000000-0000-4000-8000-000000000052";
  const recordingGestureId = "40000000-0000-4000-8000-000000000053";
  const runtime = masterCaptureFixture({send: async (envelope) => {
    if (envelope.operation !== "performance.record.begin") {
      return success(envelope, defaultResult(envelope.operation));
    }
    const lifecycle = {
      performance_id: performanceId, committed_revision: 1,
      replayed: false, project_revision: 1,
    };
    return success(envelope, Object.hasOwn(envelope.payload, "control_epoch") ? {
      ...lifecycle, profile: "header_input_sequence", control_epoch: LIVE_EPOCH,
      core_control_ready: true, next_recording_sequence: "0",
      fx_bindings: [{fx: "delay", gesture_generation: gestureGeneration,
        recording_gesture_id: recordingGestureId}],
    } : lifecycle);
  }});
  const {session} = runtime;
  await session.start();
  await session.activateAudio(createUserGestureToken({isTrusted: true}));
  const legacy = await session.beginPerformanceRecording({
    sessionId, performanceId, expectedRevision: 0,
  });
  assert.deepEqual(legacy, {
    performanceId, committedRevision: 1, replayed: false, projectRevision: 1,
  });
  assert.equal(Object.isFrozen(legacy), true);
  const headered = await session.beginPerformanceRecording({
    sessionId, performanceId, expectedRevision: 0, controlEpoch: LIVE_EPOCH,
  });
  assert.deepEqual(headered, {
    performanceId, committedRevision: 1, replayed: false, projectRevision: 1,
    profile: "header_input_sequence", controlEpoch: LIVE_EPOCH,
    coreControlReady: true, nextRecordingSequence: "0",
    fxBindings: [{fx: "delay", gestureGeneration, recordingGestureId}],
  });
  assert.equal(Object.isFrozen(headered), true);
  assert.equal(Object.isFrozen(headered.fxBindings), true);
  assert.equal(Object.isFrozen(headered.fxBindings[0]), true);
  assert.equal(runtime.lowerStarts, 0);
  await session.close();
});


// Integration regression: Native capacity only applies once admission runs;
// queued calls need their own reservation before either SDK promise tail.
// This injected short-admission gate proves SDK bounds and exact wire/caller
// retirement, not physical device hearing or native callback performance.
test("profile queued Press capacity is bounded before admission and real Release retires each original owner", async () => {
  let releaseShort;
  let shortStarted;
  const shortReady = new Promise(resolve => { shortStarted = resolve; });
  const f = inputProfileFixture({extraSend: e => {
    if (e.operation !== "pattern.transport.request") return null;
    shortStarted();
    return new Promise(resolve => { releaseShort = () => resolve(success(e, {
      session_id: e.payload.session_id, command_id: e.payload.command_id, submit: "accepted",
      status: transportStatus({phase: "idle"}),
    })); });
  }});
  await activateInputProfile(f);
  const stop = f.session.requestPatternTransport({sessionId: TRANSPORT_SESSION_ID,
    projectId: TRANSPORT_PROJECT_ID, commandId: TRANSPORT_COMMAND_ID, expectedEpoch: 2,
    intent: "play_stop", expectedRevision: null});
  await shortReady;
  const keys = Array.from({length: 64}, () => ({}));
  const presses = keys.map((key, slot) => f.session.trigger(slot, 100, "pointer", key));
  assert.equal(await f.session.trigger(0, 100, "pointer", {}), false);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 0,
    "the 65th queued Press never acquired a Native ticket");
  releaseShort();
  assert.equal((await stop).submit, "accepted");
  const accepted = await Promise.all(presses);
  assert.deepEqual(accepted.map(x => x.sequence), Array.from({length: 64}, (_, i) => i + 1));
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 64);
  for (let slot = 0; slot < 64; slot += 1) {
    assert.equal(await f.session.release(slot, "pointer", keys[slot]), true);
  }
  const requests = f.sent.filter(e => e.operation === "pattern.transport.input.request");
  assert.equal(requests.length, 128);
  assert.deepEqual(requests.slice(64).map(e => e.payload.held_press_sequence),
    Array.from({length: 64}, (_, i) => String(i + 1)));
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.inspect" && e.payload.consume).length, 128);
  // Capacity returns only after these real matching release consumes.
  assert.equal((await f.session.trigger(0, 100, "pointer", keys[0])).sequence, 129);
  assert.equal(await f.session.release(0, "pointer", keys[0]), true);
  await f.session.close();
});

test("Performance queued Pad admission counts toward 64 before the first receipt", async () => {
  let releaseFirst;
  let firstStarted;
  const ready = new Promise(resolve => { firstStarted = resolve; });
  const events = [];
  const {session} = fixture({send: async e => {
    if (e.operation === "performance.record.event") {
      events.push(e.payload.event);
      if (events.length === 1) {
        firstStarted();
        await new Promise(resolve => { releaseFirst = resolve; });
      }
      return success(e, {event_id: e.payload.event_id, accepted_tick: 0, input_sequence: 1,
        coalesced: false, replayed: false, project_revision: null});
    }
    return success(e, defaultResult(e.operation));
  }});
  await session.start();
  const sessionId = "40000000-0000-4000-8000-000000000050";
  const id = (prefix, i) => `40000000-0000-4000-${prefix}-${String(i + 1).padStart(12, "0")}`;
  const presses = Array.from({length: 64}, (_, slot) => session.recordPerformanceEvent({
    sessionId, eventId: id("8100", slot),
    event: {kind: "pad_press", gestureId: id("8200", slot), slot, velocity: 100},
  }));
  await ready;
  await assert.rejects(session.recordPerformanceEvent({sessionId, eventId: id("8100", 64),
    event: {kind: "pad_press", gestureId: id("8200", 64), slot: 0, velocity: 100},
  }), /Too many open Pad gestures/);
  assert.equal(events.length, 1, "the pending 64 reservations bound the unsent queue");
  releaseFirst();
  await Promise.all(presses);
  assert.equal(events.length, 64);
  for (let slot = 0; slot < 64; slot += 1) {
    await session.recordPerformanceEvent({sessionId, eventId: id("8300", slot),
      event: {kind: "pad_release", gestureId: id("8200", slot), slot},
    });
  }
  assert.deepEqual(events.slice(64).map(e => e.gesture_id),
    Array.from({length: 64}, (_, slot) => id("8200", slot)));
  await session.recordPerformanceEvent({sessionId, eventId: id("8400", 0),
    event: {kind: "pad_press", gestureId: id("8500", 0), slot: 0, velocity: 100},
  });
  await session.recordPerformanceEvent({sessionId, eventId: id("8600", 0),
    event: {kind: "pad_release", gestureId: id("8500", 0), slot: 0},
  });
  assert.equal(events.length, 130, "matching accepted release returned admission capacity");
  await session.close();
});


test("direct companion requests reserve actual known capacity before the Host tail", async () => {
  let releaseQuery;
  let queryStarted;
  const ready = new Promise(resolve => { queryStarted = resolve; });
  const f = inputProfileFixture({extraSend: e => {
    if (e.operation === "pattern.transport.count-in.capabilities")
      return success(e, {...defaultResult(e.operation), input_capacity: 2});
    if (e.operation === "project.inspect") {
      queryStarted();
      return new Promise(resolve => { releaseQuery = () => resolve(success(e, defaultResult(e.operation))); });
    }
    return null;
  }});
  await activateInputProfile(f);
  const query = f.session.inspectProject();
  await ready;
  const request = i => ({commandId: `40000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
    runtimeGeneration: "1", frameEpoch: "1", inputSerial: String(i), slot: i - 1, velocity: 100,
    kind: "press", held: false, heldPressSequence: null});
  const first = f.session.requestPatternInput(request(1));
  const second = f.session.requestPatternInput(request(2));
  await assert.rejects(f.session.requestPatternInput(request(3)),
    error => error.code === "HOST_STATE_INVALID" && error.details.pending === false);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 0);
  releaseQuery();
  await query;
  for (const admitted of await Promise.all([first, second])) {
    const consumed = await f.session.inspectPatternInput(admitted.ticket, true);
    assert.equal(consumed.complete, true);
    assert.equal(consumed.nativeResult.disposition, "muted_no_voice");
  }
  const third = await f.session.requestPatternInput(request(3));
  assert.equal((await f.session.inspectPatternInput(third.ticket, true)).complete, true);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 3);
  await f.session.close();
});

test("queued profile keyup observers share one original matching Release", async () => {
  let releaseStop;
  let stopStarted;
  const ready = new Promise(resolve => { stopStarted = resolve; });
  const f = inputProfileFixture({extraSend: e => {
    if (e.operation !== "pattern.transport.request") return null;
    stopStarted();
    return new Promise(resolve => { releaseStop = () => resolve(success(e, {
      session_id: e.payload.session_id, command_id: e.payload.command_id, submit: "accepted",
      status: transportStatus({phase: "idle"}),
    })); });
  }});
  await activateInputProfile(f);
  const stop = f.session.requestPatternTransport({sessionId: TRANSPORT_SESSION_ID,
    projectId: TRANSPORT_PROJECT_ID, commandId: TRANSPORT_COMMAND_ID, expectedEpoch: 2,
    intent: "play_stop", expectedRevision: null});
  await ready;
  const key = {};
  const press = f.session.trigger(0, 100, "pointer", key);
  const released = f.session.release(0, "pointer", key);
  const joined = f.session.release(0, "pointer", key);
  releaseStop();
  await stop;
  assert.equal((await press).sequence, 1);
  assert.equal(await released, true);
  assert.equal(await joined, true);
  const requests = f.sent.filter(e => e.operation === "pattern.transport.input.request");
  assert.deepEqual(requests.map(e => [e.payload.kind, e.payload.held_press_sequence]),
    [["press", null], ["release", "1"]]);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.inspect" && e.payload.consume).length, 2);
  await f.session.close();
});

test("a capture started ACK arriving during close cannot arm before the physical cleanup fence", async () => {
  let acknowledge;
  let releaseBackend;
  let backendStarted;
  const backendReady = new Promise(resolve => { backendStarted = resolve; });
  let tapClosed = 0;
  let captureStops = 0;
  let backendClosed = false;
  const tap = {
    destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    start(sink) {
      return new Promise(resolve => { acknowledge = () => resolve({stop: async () => {
        captureStops += 1;
        sink.onStopped();
      }}); });
    },
    failProcessor() {},
    async close() {
      assert.equal(backendClosed, true, "SDK tap detach follows the actual backend closure");
      tapClosed += 1;
    },
  };
  const f = fixture({browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {resourceLimits: {perform_recording_frames: 86_400_000,
      perform_recording_queue_batches: 32}, performanceMasterTapUrl: "./assets/perform-master-tap.js"},
    createPerformanceMasterTap: async () => tap,
    runtimeTerminator: async () => {
      backendStarted();
      await new Promise(resolve => { releaseBackend = resolve; });
      f.context.state = "closed";
      backendClosed = true;
    },
  });
  await f.session.start();
  assert.equal(await f.session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  const starting = f.session.startPerformanceMasterCapture({onBatch() {}, onStopped() {}, onFailure() {}});
  const rejected = assert.rejects(starting, {code: "HOST_STATE_INVALID"});
  const closing = f.session.close();
  await backendReady;
  assert.equal(tapClosed, 0);
  acknowledge();
  await rejected;
  assert.equal(captureStops, 1);
  assert.equal(tapClosed, 0, "a cancelled ACK cannot detach the original tap early");
  releaseBackend();
  assert.equal(await closing, true);
  assert.equal(await f.session.waitForTerminalCleanup(), true);
  assert.equal(tapClosed, 1);
  await assert.rejects(f.session.startPerformanceMasterCapture({onBatch() {}, onStopped() {}, onFailure() {}}),
    {code: "HOST_STATE_INVALID"});
});


// Injected legacy owner fixture: a real invocation-bound owner receipt and
// backend close are separate producers. Neither terminator entry/completion
// nor public close is a full-owner or backend receipt.
function legacyOwnerClosureFixture({send, beforeSeal = async () => {}}) {
  let sealed = false;
  let fullReceipt = false;
  let actualRuntime = null;
  let actualAudioContext = null;
  let nativeStops = 0;
  let backendCloses = 0;
  let ownerConfirmation;
  const ownerPending = new Promise(resolve => {ownerConfirmation = resolve;});
  let beginTermination;
  const terminationStarted = new Promise(resolve => {beginTermination = resolve;});
  let beginBackend;
  const backendStarted = new Promise(resolve => {beginBackend = resolve;});
  let closeBackend;
  const backendPending = new Promise(resolve => {closeBackend = resolve;});
  const ownerTransport = {
    get terminated() { return sealed; },
    get terminalOwnerReleased() { return fullReceipt; },
    async send(envelope) {
      assert.equal(sealed, false, "a sealed owner accepts no new ordinary request");
      return send(envelope);
    },
    subscribe() { return () => {}; },
    subscribeFailure() { return () => {}; },
  };
  const f = fixture({browserWindow: {}, publishRuntime: true,
    sessionTransport: ownerTransport, runtimeTransport: ownerTransport,
    runtimeTerminator: async ({runtime, audioContext}) => {
      assert.equal(runtime.transport, ownerTransport, "terminate this invocation's actual loaded owner");
      assert.equal(audioContext, f.context, "backend belongs to the same original Session");
      actualRuntime = runtime;
      actualAudioContext = audioContext;
      nativeStops += 1;
      beginTermination();
      // A genuine queued legacy Release is allowed to finish before sealing;
      // this is an explicit input-owner gate, not a fabricated Release ACK.
      await beforeSeal();
      sealed = true;
      await ownerPending;
      await audioContext.close();
    }});
  f.context.close = async () => {
    assert.equal(actualAudioContext, f.context);
    backendCloses += 1;
    beginBackend();
    await backendPending;
    f.context.state = "closed";
  };
  return Object.assign(f, {
    ownerTransport, terminationStarted, backendStarted,
    deliverOwnerReceipt() {
      assert.equal(actualRuntime?.transport, ownerTransport);
      assert.equal(nativeStops, 1, "only the original owner produces its closure receipt");
      assert.equal(sealed, true, "the original owner was actually sealed before its receipt");
      assert.equal(fullReceipt, false);
      fullReceipt = true;
      ownerConfirmation();
    },
    releaseBackend() { closeBackend(); },
    nativeStops: () => nativeStops,
    backendCloses: () => backendCloses,
  });
}

// F1/F2/F3 repair witnesses use public APIs and original wire/receipt IDs.
// Source delivery only: these component models do not prove physical hearing.
test("legacy known-unsubmitted refusals never acquire a matching Release capacity slot", async () => {
  const wire = [];
  let sequence = 0;
  const f = fixture({send: async e => {
    if (e.operation === "trigger") {
      wire.push(e.payload);
      return success(e, e.payload.kind === "release" ? {accepted: true} : {sequence: ++sequence});
    }
    return success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  for (let i = 0; i < 64; i += 1)
    assert.equal(await f.session.trigger(0, 100, "pointer", {}), false);
  assert.equal(wire.length, 0, "non-running refusals have no Native handoff");
  assert.equal(await f.session.activateAudio(createUserGestureToken({isTrusted: true})), true);
  for (let i = 0; i < 64; i += 1)
    assert.equal(await f.session.trigger(0, 0, "pointer", {}), false);
  assert.equal(wire.length, 0, "invalid velocity also has no Native handoff");
  const key = {};
  assert.equal((await f.session.trigger(0, 100, "pointer", key)).sequence, 1);
  assert.equal(await f.session.release(0, "pointer", key), true);
  assert.deepEqual(wire, [{slot: 0, velocity: 100}, {slot: 0, kind: "release"}]);
  const next = {};
  assert.equal((await f.session.trigger(1, 100, "pointer", next)).sequence, 2);
  assert.equal(await f.session.release(1, "pointer", next), true);
  assert.equal(await f.session.close(), true);
});

test("a swallowed submitted-unknown legacy false retains its original capacity until real matching Release", async () => {
  let sequence = 0;
  const wire = [];
  let releaseUnknown;
  let unknownStarted;
  const ready = new Promise(resolve => {unknownStarted = resolve;});
  let releaseObserved;
  const genuineRelease = new Promise(resolve => {releaseObserved = resolve;});
  const f = legacyOwnerClosureFixture({beforeSeal: () => genuineRelease, send: async e => {
    if (e.operation === "trigger") {
      wire.push(e.payload);
      if (e.payload.kind === "release") {
        releaseObserved();
        return success(e, {accepted: true});
      }
      sequence += 1;
      if (sequence === 64) {
        unknownStarted();
        await new Promise(resolve => {releaseUnknown = resolve;});
        throw Object.assign(new Error("original admission response lost"),
          {code: "HOST_TIMEOUT", details: {pending: true}});
      }
      return success(e, {sequence});
    }
    return success(e, defaultResult(e.operation));
  }});
  assert.equal(await f.session.waitForTerminalCleanup(), false, "no cleanup initiated");
  await f.session.start();
  await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
  assert.equal(await f.session.waitForTerminalCleanup(), false, "activation is not cleanup initiation");
  const keys = Array.from({length: 64}, () => ({}));
  for (let slot = 0; slot < 63; slot += 1)
    assert.equal((await f.session.trigger(slot, 100, "pointer", keys[slot])).sequence, slot + 1);
  const unknown = f.session.trigger(63, 100, "pointer", keys[63]);
  await ready;
  const matchingRelease = f.session.release(63, "pointer", keys[63]);
  await assert.rejects(f.session.trigger(0, 100, "pointer", {}), /Too many open Pad gestures/);
  releaseUnknown();
  assert.equal(await unknown, false);
  assert.equal(wire.filter(x => x.kind !== "release").length, 64,
    "unknown false is not evidence that the original handoff never happened");
  assert.equal(await matchingRelease, true);
  // Fatal failure seals new admission. Do not turn that seal into a false
  // capacity-reuse claim: retirement must follow real cleanup in this model.
  await assert.rejects(f.session.trigger(0, 100, "pointer", {}), /Runtime session is closed/);
  assert.deepEqual(wire.at(-1), {slot: 63, kind: "release"});
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  await f.terminationStarted;
  const originalWait = f.session.waitForTerminalCleanup();
  assert.equal(f.session.waitForTerminalCleanup(), originalWait);
  let eligible = null;
  void originalWait.then(value => {eligible = value;});
  await drainTasks();
  assert.equal(f.ownerTransport.terminalOwnerReleased, false);
  assert.equal(eligible, null, "fatal cleanup cannot borrow legacy normal-close eligibility");
  assert.equal(f.backendCloses(), 0);
  f.deliverOwnerReceipt();
  await f.backendStarted;
  assert.equal(f.ownerTransport.terminalOwnerReleased, true);
  assert.equal(f.context.state, "running");
  assert.equal(eligible, null, "full owner receipt is not backend closure");
  f.releaseBackend();
  assert.equal(await originalWait, true);
  assert.equal(f.context.state, "closed");
  assert.equal(f.backendCloses(), 1);
  assert.equal(f.nativeStops(), 1);
  assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
  assert.deepEqual(wire.at(-1), {slot: 63, kind: "release"});
});

test("legacy Release stays after its parked Press across the original dual-ready capture gate", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000090";
  const performanceId = "40000000-0000-4000-8000-000000000091";
  let acknowledge;
  let tapStarting;
  const tapReady = new Promise(resolve => {tapStarting = resolve;});
  const wire = [];
  let sequence = 0;
  const tap = {destinationNode: Object.assign(new EventTarget(), {disconnect() {}}),
    start(sink, binding) {
      tapStarting();
      return new Promise(resolve => {acknowledge = () => resolve({binding, generation: 1,
        stop: async () => {sink.onStopped();}});});
    }, failProcessor() {}, async close() {}};
  const f = fixture({browserDocument: {baseURI: "https://example.test/creator/"},
    manifestSource: {resourceLimits: RESOURCE_LIMITS, performanceMasterTapUrl: "./assets/perform-master-tap.js"},
    createPerformanceMasterTap: async () => tap,
    send: async e => {
      if (e.operation === "performance.record.begin") return success(e, {
        performance_id: performanceId, committed_revision: 1, replayed: false,
        profile: "header_input_sequence", control_epoch: LIVE_EPOCH, core_control_ready: true,
        next_recording_sequence: "0", fx_bindings: [], project_revision: 1});
      if (e.operation === "trigger") {
        wire.push(e.payload);
        return success(e, e.payload.kind === "release" ? {accepted: true} : {sequence: ++sequence});
      }
      return success(e, defaultResult(e.operation));
    }});
  await f.session.start();
  await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
  const begin = f.session.beginPerformanceRecording({sessionId, performanceId, expectedRevision: 0,
    controlEpoch: LIVE_EPOCH, captureSink: {onBatch() {}, onStopped() {}, onFailure() {}}});
  await tapReady;
  const key = {};
  const press = f.session.trigger(2, 100, "pointer", key);
  const release = f.session.release(2, "pointer", key);
  await drainTasks();
  assert.deepEqual(wire, [], "neither the parked Press nor its Release overtakes readiness");
  acknowledge();
  assert.equal((await begin).coreControlReady, true);
  assert.equal((await press).sequence, 1);
  assert.equal(await release, true);
  assert.deepEqual(wire, [{slot: 2, velocity: 100}, {slot: 2, kind: "release"}]);
  const fresh = {};
  assert.equal((await f.session.trigger(3, 100, "pointer", fresh)).sequence, 2);
  assert.equal(await f.session.release(3, "pointer", fresh), true);
  assert.equal(await f.session.close(), true);
});

test("legacy Release waits for its original first admission including a submitted-unknown response", async () => {
  for (const unknown of [false, true]) {
    let releaseAdmission;
    let admissionStarted;
    const ready = new Promise(resolve => {admissionStarted = resolve;});
    const wire = [];
    const f = fixture({send: async e => {
      if (e.operation !== "trigger") return success(e, defaultResult(e.operation));
      wire.push(e.payload);
      if (e.payload.kind === "release") return success(e, {accepted: true});
      admissionStarted();
      await new Promise(resolve => {releaseAdmission = resolve;});
      if (unknown) throw Object.assign(new Error("original response lost"),
        {code: "HOST_TIMEOUT", details: {pending: true}});
      return success(e, {sequence: 1});
    }});
    await f.session.start();
    await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
    const key = {};
    const press = f.session.trigger(4, 100, "keyboard", key);
    await ready;
    const release = f.session.release(4, "keyboard", key);
    await drainTasks();
    assert.deepEqual(wire, [{slot: 4, velocity: 100}]);
    releaseAdmission();
    const admitted = await press;
    assert.equal(unknown ? admitted : admitted.sequence, unknown ? false : 1);
    assert.equal(await release, true);
    assert.deepEqual(wire, [{slot: 4, velocity: 100}, {slot: 4, kind: "release"}]);
    if (unknown) {
      assert.equal(f.session.diagnostics().error_code, "HOST_TIMEOUT");
      await f.session.waitForTerminalCleanup();
    } else assert.equal(await f.session.close(), true);
  }
});

test("Performance matching Release reservations are bounded while foreign and duplicate events cannot borrow them", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000092";
  const id = (prefix, i) => `40000000-0000-4000-${prefix}-${String(i + 1).padStart(12, "0")}`;
  let releaseFirst;
  let firstStarted;
  const ready = new Promise(resolve => {firstStarted = resolve;});
  const wire = [];
  const f = fixture({send: async e => {
    if (e.operation === "performance.record.event") {
      wire.push(e.payload);
      if (wire.length === 1) {firstStarted(); await new Promise(resolve => {releaseFirst = resolve;});}
      return success(e, {event_id: e.payload.event_id, accepted_tick: 0, input_sequence: wire.length,
        coalesced: false, replayed: false, project_revision: null});
    }
    return success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  const presses = Array.from({length: 64}, (_, slot) => f.session.recordPerformanceEvent({sessionId,
    eventId: id("9100", slot), event: {kind: "pad_press", gestureId: id("9200", slot), slot, velocity: 100}}));
  await ready;
  const releases = Array.from({length: 64}, (_, slot) => f.session.recordPerformanceEvent({sessionId,
    eventId: id("9300", slot), event: {kind: "pad_release", gestureId: id("9200", slot), slot}}));
  await assert.rejects(f.session.recordPerformanceEvent({sessionId, eventId: id("9400", 64),
    event: {kind: "pad_press", gestureId: id("9200", 0), slot: 0, velocity: 100}}), /already owns a Press position/);
  for (let i = 0; i < 64; i += 1) {
    await assert.rejects(f.session.recordPerformanceEvent({sessionId, eventId: id("9400", i),
      event: {kind: "pad_release", gestureId: id("9200", 0), slot: 0}}), /Release is already reserved/);
  }
  // Preserve the original foreign/replay API within the ordinary 1+1 window.
  const foreign = f.session.recordPerformanceEvent({sessionId, eventId: id("9500", 0),
    event: {kind: "pad_release", gestureId: id("9600", 0), slot: 0}});
  await assert.rejects(f.session.recordPerformanceEvent({sessionId, eventId: id("9500", 65),
    event: {kind: "pad_release", gestureId: id("9200", 0), slot: 1}}), /Live input window is full/,
    "a wrong-slot UUID Release has no original owner reservation to borrow");
  for (let i = 1; i <= 64; i += 1) {
    await assert.rejects(f.session.recordPerformanceEvent({sessionId, eventId: id("9500", i),
      event: {kind: "pad_release", gestureId: id("9600", i), slot: 0}}), /Live input window is full/);
  }
  assert.equal(wire.length, 1, "no matching or foreign Release bypasses the original receipt");
  releaseFirst();
  await Promise.all(presses);
  await Promise.all(releases);
  await foreign;
  assert.deepEqual(wire.slice(64, 128).map(x => [x.event.gesture_id, x.event.slot]),
    Array.from({length: 64}, (_, slot) => [id("9200", slot), slot]));
  const fresh = {sessionId, eventId: id("9700", 0),
    event: {kind: "pad_press", gestureId: id("9800", 0), slot: 0, velocity: 100}};
  await f.session.recordPerformanceEvent(fresh);
  await f.session.recordPerformanceEvent({sessionId, eventId: id("9900", 0),
    event: {kind: "pad_release", gestureId: fresh.event.gestureId, slot: 0}});
  assert.equal(wire.length, 131, "all 64 original Releases complete and return their owner capacity");
  assert.equal(await f.session.close(), true);
});

test("Performance cleanup owns one token while a received gesture still completes before stop", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000093";
  const performanceId = "40000000-0000-4000-8000-000000000094";
  const id = i => `40000000-0000-4000-8000-${String(i + 100).padStart(12, "0")}`;
  let releaseFirst;
  let firstStarted;
  const ready = new Promise(resolve => {firstStarted = resolve;});
  const wire = [];
  const f = fixture({send: async e => {
    if (e.operation === "performance.record.event") {
      wire.push([e.operation, e.payload.event.kind]);
      if (wire.length === 1) {firstStarted(); await new Promise(resolve => {releaseFirst = resolve;});}
      return success(e, {event_id: e.payload.event_id, accepted_tick: 0, input_sequence: wire.length,
        coalesced: false, replayed: false, project_revision: null});
    }
    if (e.operation === "performance.record.stop") {
      wire.push([e.operation, e.payload.request_id]);
      return success(e, {request_id: e.payload.request_id, session_id: sessionId, performance_id: performanceId,
        state: "stopped", pending_event_count: 0, replayed: false, project_revision: null});
    }
    return success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  const press = f.session.recordPerformanceEvent({sessionId, eventId: id(1),
    event: {kind: "pad_press", gestureId: id(2), slot: 0, velocity: 100}});
  await ready;
  const release = f.session.recordPerformanceEvent({sessionId, eventId: id(3),
    event: {kind: "pad_release", gestureId: id(2), slot: 0}});
  const ordinary = f.session.recordPerformanceEvent({sessionId, eventId: id(4), event: {kind: "hold_on"}});
  const cancelled = assert.rejects(ordinary, /cancelled before Core admission/);
  const stop = f.session.stopPerformanceRecording({sessionId, requestId: id(5)});
  for (let i = 6; i < 70; i += 1)
    await assert.rejects(f.session.stopPerformanceRecording({sessionId, requestId: id(i)}), /cleanup token is already reserved/);
  assert.deepEqual(wire, [["performance.record.event", "pad_press"]]);
  await cancelled;
  releaseFirst();
  await press;
  await release;
  assert.equal((await stop).requestId, id(5));
  assert.deepEqual(wire, [["performance.record.event", "pad_press"],
    ["performance.record.event", "pad_release"], ["performance.record.stop", id(5)]]);
  const next = await f.session.stopPerformanceRecording({sessionId, requestId: id(70)});
  assert.equal(next.requestId, id(70), "the token is reusable after its original successful receipt");
  assert.equal(await f.session.close(), true);
});


test("close truthfully cancels a never-admitted legacy Press and its queued real Release", async () => {
  let releaseAdmission;
  let admissionStarted;
  const ready = new Promise(resolve => {admissionStarted = resolve;});
  const wire = [];
  const f = legacyOwnerClosureFixture({send: async e => {
    if (e.operation !== "trigger") return success(e, defaultResult(e.operation));
    wire.push(e.payload);
    admissionStarted();
    await new Promise(resolve => {releaseAdmission = resolve;});
    return success(e, {sequence: 1});
  }});
  assert.equal(await f.session.waitForTerminalCleanup(), false, "no cleanup initiated");
  await f.session.start();
  await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
  assert.equal(await f.session.waitForTerminalCleanup(), false, "activation is not cleanup initiation");
  const admitted = f.session.trigger(0, 100, "pointer", {});
  await ready;
  const key = {};
  const queued = f.session.trigger(1, 100, "pointer", key);
  const release = f.session.release(1, "pointer", key);
  const pressRejected = assert.rejects(queued, /cancelled before Core admission/);
  const releaseRejected = assert.rejects(release, /cancelled before Core admission/);
  const closing = f.session.close();
  await pressRejected;
  await releaseRejected;
  assert.deepEqual(wire, [{slot: 0, velocity: 100}], "no fabricated Release or cancelled Press reached Native");
  releaseAdmission();
  assert.equal(await admitted, false);
  await f.terminationStarted;
  const originalWait = f.session.waitForTerminalCleanup();
  assert.equal(f.session.waitForTerminalCleanup(), originalWait);
  let eligible = null;
  let closed = null;
  void originalWait.then(value => {eligible = value;});
  void closing.then(value => {closed = value;});
  await drainTasks();
  assert.equal(f.ownerTransport.terminalOwnerReleased, false);
  assert.equal(eligible, null);
  assert.equal(closed, null, "public close waits the original owner resources");
  assert.equal(f.backendCloses(), 0);
  f.deliverOwnerReceipt();
  await f.backendStarted;
  assert.equal(f.ownerTransport.terminalOwnerReleased, true);
  assert.equal(f.context.state, "running");
  assert.equal(eligible, null, "normal close still needs independent backend closure");
  assert.equal(closed, null);
  f.releaseBackend();
  assert.equal(await closing, true);
  assert.equal(await originalWait, true);
  assert.equal(f.context.state, "closed");
  assert.equal(f.backendCloses(), 1);
  assert.equal(f.nativeStops(), 1);
  assert.equal(f.session.diagnostics().error_code, null);
  assert.deepEqual(wire, [{slot: 0, velocity: 100}]);
});

test("unknown Performance Release retains the original reserved position until actual cleanup", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000095";
  const performanceId = "40000000-0000-4000-8000-000000000096";
  const id = i => `40000000-0000-4000-8000-${String(i + 200).padStart(12, "0")}`;
  let loseRelease = true;
  const wire = [];
  const f = fixture({send: async e => {
    if (e.operation === "performance.record.event") {
      wire.push(e.payload);
      if (e.payload.event.kind === "pad_release" && loseRelease)
        throw Object.assign(new Error("matching Release receipt lost"), {code: "HOST_TIMEOUT", details: {pending: true}});
      return success(e, {event_id: e.payload.event_id, accepted_tick: 0, input_sequence: wire.length,
        coalesced: false, replayed: false, project_revision: null});
    }
    if (e.operation === "performance.record.stop") return success(e, {
      request_id: e.payload.request_id, session_id: sessionId, performance_id: performanceId,
      state: "stopped", pending_event_count: 0, replayed: false, project_revision: null});
    return success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  await f.session.recordPerformanceEvent({sessionId, eventId: id(1),
    event: {kind: "pad_press", gestureId: id(2), slot: 0, velocity: 100}});
  await assert.rejects(f.session.recordPerformanceEvent({sessionId, eventId: id(3),
    event: {kind: "pad_release", gestureId: id(2), slot: 0}}), {code: "HOST_TIMEOUT"});
  await assert.rejects(f.session.recordPerformanceEvent({sessionId, eventId: id(4),
    event: {kind: "pad_release", gestureId: id(2), slot: 0}}), /Release is already reserved/);
  assert.equal(wire.length, 2, "caller rejection did not retire or redispatch the unknown Release");
  assert.equal((await f.session.stopPerformanceRecording({sessionId, requestId: id(5)})).state, "stopped");
  loseRelease = false;
  await f.session.recordPerformanceEvent({sessionId, eventId: id(6),
    event: {kind: "pad_press", gestureId: id(2), slot: 0, velocity: 100}});
  await f.session.recordPerformanceEvent({sessionId, eventId: id(7),
    event: {kind: "pad_release", gestureId: id(2), slot: 0}});
  assert.deepEqual(wire.slice(2).map(x => x.event.kind), ["pad_press", "pad_release"]);
  assert.equal(await f.session.close(), true);
});

test("unknown Performance cleanup keeps the singleton token after its caller rejects", async () => {
  const sessionId = "40000000-0000-4000-8000-000000000097";
  const requestId = "40000000-0000-4000-8000-000000000098";
  const stops = [];
  const f = fixture({send: async e => {
    if (e.operation === "performance.record.stop") {
      stops.push(e.payload);
      throw Object.assign(new Error("original cleanup receipt lost"), {code: "HOST_TIMEOUT", details: {pending: true}});
    }
    return success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  await assert.rejects(f.session.stopPerformanceRecording({sessionId, requestId}), {code: "HOST_TIMEOUT"});
  await assert.rejects(f.session.stopPerformanceRecording({sessionId,
    requestId: "40000000-0000-4000-8000-000000000099"}), /cleanup token is already reserved/);
  assert.deepEqual(stops, [{session_id: sessionId, request_id: requestId}]);
  assert.equal(await f.session.close(), true);
  assert.equal(await f.session.waitForTerminalCleanup(), true);
});


// Shared physical capacity witnesses use original public APIs and actual
// producer/consumer IDs. Injected transports prove SDK ownership, not hearing.
const SHARED_SESSION = "51000000-0000-4000-8000-000000000001";
function sharedId(group, index) {
  return `51000000-0000-4000-${group}-${String(index + 1).padStart(12, "0")}`;
}
function sharedPerformanceReply(e) {
  if (e.operation === "performance.record.event") return success(e, {
    event_id: e.payload.event_id, accepted_tick: 0, input_sequence: 1,
    coalesced: false, replayed: false, project_revision: null});
  if (e.operation === "performance.record.stop") return success(e, {
    request_id: e.payload.request_id, session_id: e.payload.session_id,
    performance_id: sharedId("8800", 0), state: "stopped", pending_event_count: 0,
    replayed: false, project_revision: null});
  return null;
}
function sharedPad(index, kind = "pad_press", slot = 0) {
  return {sessionId: SHARED_SESSION, eventId: sharedId(kind === "pad_press" ? "8100" : "8300", index),
    event: {kind, gestureId: sharedId("8200", index), slot,
      ...(kind === "pad_press" ? {velocity: 100} : {})}};
}

test("64 physical presses share Pattern and Performance positions and both actual domains must retire", async () => {
  const f = inputProfileFixture({extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  const keys = Array.from({length: 64}, () => ({}));
  const leases = keys.map(key => f.session.reserveInputGesture(key, 0, "pointer"));
  assert.ok(leases.every(lease => lease !== null));
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  // Distinct physical keys on the SAME Pad remain distinct retained presses.
  const bothDomains = keys.flatMap((key, index) => index % 2 === 0
    // Creator's real observer enters Performance BEFORE deferred Pattern work.
    ? [f.session.recordPerformanceEvent(sharedPad(index), key), f.session.trigger(0, 100, "pointer", key)]
    : [f.session.trigger(0, 100, "pointer", key), f.session.recordPerformanceEvent(sharedPad(index), key)]);
  await Promise.all(bothDomains);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 64);
  assert.equal(f.sent.filter(e => e.operation === "performance.record.event").length, 64);
  await assert.rejects(f.session.recordPerformanceEvent(sharedPad(64), {}), {code: "HOST_STATE_INVALID"});
  assert.equal(await f.session.trigger(0, 100, "pointer", {}), false);
  assert.equal(f.sent.filter(e => e.operation === "performance.record.event").length, 64);
  // Neither a duplicate domain nor a foreign local key can borrow a position.
  await assert.rejects(f.session.recordPerformanceEvent({...sharedPad(0), eventId: sharedId("8400", 0)}, keys[0]),
    /already owns a Press/);
  for (let index = 0; index < 64; index += 1) {
    leases[index].releasePhysical();
    await f.session.recordPerformanceEvent(sharedPad(index, "pad_release"), keys[index]);
  }
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null,
    "Performance Release alone is not Pattern caller/physical retirement");
  assert.equal(await f.session.release(0, "pointer", keys[0]), true);
  const freshKey = {};
  const freshLease = f.session.reserveInputGesture(freshKey, 0, "pointer");
  assert.notEqual(freshLease, null);
  freshLease.cancelUnsubmittedPattern();
  for (let index = 1; index < 64; index += 1)
    assert.equal(await f.session.release(0, "pointer", keys[index]), true);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.inspect" && e.payload.consume).length, 128);
  const finalKey = {};
  const finalLease = f.session.reserveInputGesture(finalKey, 0, "pointer");
  assert.notEqual(finalLease, null);
  await f.session.trigger(0, 100, "pointer", finalKey);
  finalLease.releasePhysical();
  assert.equal(await f.session.release(0, "pointer", finalKey), true);
  await f.session.close();
});

test("uncorrelated direct callers share the combined 64 cap without guessing UUID or Pad equivalence", async () => {
  const f = inputProfileFixture({extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  for (let index = 0; index < 32; index += 1)
    assert.notEqual(await f.session.trigger(0, 100, "pointer"), false);
  for (let index = 0; index < 32; index += 1)
    await f.session.recordPerformanceEvent(sharedPad(index));
  assert.equal(await f.session.trigger(0, 100, "pointer"), false);
  await assert.rejects(f.session.recordPerformanceEvent(sharedPad(32)),
    error => error.code === "HOST_STATE_INVALID" && error.details.pending === false);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 32);
  assert.equal(f.sent.filter(e => e.operation === "performance.record.event").length, 32);
  await f.session.recordPerformanceEvent(sharedPad(0, "pad_release"));
  await f.session.recordPerformanceEvent(sharedPad(32));
  for (let index = 0; index < 32; index += 1)
    assert.equal(await f.session.release(0, "pointer"), true);
  await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 0)});
  assert.notEqual(await f.session.trigger(0, 100, "pointer"), false);
  assert.equal(await f.session.release(0, "pointer"), true);
  await f.session.close();
});

test("definite unsubmitted preparation frees capacity and its stale leased key cannot resurrect", async () => {
  const f = inputProfileFixture({extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  lease.cancelUnsubmittedPattern();
  const next = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(next, null);
  next.cancelUnsubmittedPattern();
  assert.equal(f.session.reserveInputGesture(key, 0, "pointer"), null);
  assert.equal(await f.session.trigger(0, 100, "pointer", key), false);
  await assert.rejects(f.session.recordPerformanceEvent(sharedPad(0), key), {code: "HOST_STATE_INVALID"});
  lease.releasePhysical();
  assert.equal(f.sent.filter(e => /input.request|record.event/.test(e.operation)).length, 0);
  for (const other of others) other.cancelUnsubmittedPattern();
  // A known local trigger refusal transfers no physical/caller debt.
  for (let index = 0; index < 64; index += 1) {
    const refusedKey = {};
    const refused = f.session.reserveInputGesture(refusedKey, 0, "pointer");
    assert.notEqual(refused, null);
    assert.equal(await f.session.trigger(0, 0, "pointer", refusedKey), false);
    refused.cancelUnsubmittedPattern();
  }
  const fresh = {};
  const accepted = f.session.reserveInputGesture(fresh, 0, "pointer");
  assert.notEqual(accepted, null);
  assert.notEqual(await f.session.trigger(0, 100, "pointer", fresh), false);
  accepted.releasePhysical();
  assert.equal(await f.session.release(0, "pointer", fresh), true);
  await f.session.close();
});

test("unknown Performance Press retains its shared place after physical and Pattern release until real Stop", async () => {
  let losePress = true;
  const f = inputProfileFixture({extraSend: e => {
    if (e.operation === "performance.record.event" && losePress) {
      losePress = false;
      throw Object.assign(new Error("original journal Press receipt lost"),
        {code: "HOST_TIMEOUT", details: {pending: true}});
    }
    return sharedPerformanceReply(e);
  }});
  await activateInputProfile(f);
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  await f.session.trigger(0, 100, "pointer", key);
  await assert.rejects(f.session.recordPerformanceEvent(sharedPad(0), key), {code: "HOST_TIMEOUT"});
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(x => x !== null));
  lease.releasePhysical();
  assert.equal(await f.session.release(0, "pointer", key), true);
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null,
    "observer rejection and one-sided real release do not retire unknown journal ownership");
  assert.equal((await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION,
    requestId: sharedId("8700", 1)})).state, "stopped");
  const fresh = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(fresh, null);
  fresh.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});

test("a cancelled Pattern preparation cannot be reattached while the same physical journal owner lives", async () => {
  const f = inputProfileFixture({extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  await f.session.recordPerformanceEvent(sharedPad(0), key);
  lease.cancelUnsubmittedPattern();
  assert.equal(await f.session.trigger(0, 100, "pointer", key), false);
  lease.releasePhysical();
  await f.session.recordPerformanceEvent(sharedPad(0, "pad_release"), key);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 0);
  const next = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(next, null);
  next.cancelUnsubmittedPattern();
  await f.session.close();
});


test("synthetic journal Release and Stop reuse the exact UUID owner without ending its physical lease", async () => {
  const f = inputProfileFixture({extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  await f.session.recordPerformanceEvent(sharedPad(0), key);
  lease.cancelUnsubmittedPattern(); // Only the journal received this physical press.
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(x => x !== null));
  // The Host closes journal gestures with the genuine original UUID. That
  // does not attest that the pointer is physically up.
  await f.session.recordPerformanceEvent(sharedPad(0, "pad_release"));
  await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 2)});
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  lease.releasePhysical();
  const next = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(next, null);
  next.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});

test("Creator preparation time before the SDK trigger does not spend the Pattern input budget", async () => {
  let now = 0;
  const f = inputProfileFixture({now: () => now});
  await activateInputProfile(f);
  const key = {};
  assert.notEqual(f.session.reserveInputGesture(key, 0, "pointer"), null);
  now = 1001;
  assert.equal((await f.session.trigger(0, 100, "pointer", key)).sequence, 1);
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 1);
  assert.equal(await f.session.release(0, "pointer", key), true);
  await f.session.close();
});

test("a sixteen-Pad burst queued in the SDK charges each Press and Release only from its own admission turn", async () => {
  let now = 0;
  // Each Native admission costs 125 ms, so the ninth queued Press would be
  // dispatched after one second if queue time were charged.
  const f = inputProfileFixture({now: () => now, onRequest: () => { now += 125; }});
  await activateInputProfile(f);
  const keys = Array.from({length: 16}, () => ({}));
  const admissions = await Promise.all(keys.map((key, slot) => f.session.trigger(slot, 100, "pointer", key)));
  assert.deepEqual(admissions.map(a => a.sequence), Array.from({length: 16}, (_, i) => i + 1));
  assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.request").length, 16);
  // Sixteen queued Releases follow the same rule.
  assert.deepEqual(await Promise.all(keys.map((key, slot) => f.session.release(slot, "pointer", key))),
    Array(16).fill(true));
  await f.session.close();
});

test("a sixteen-Pad legacy burst charges each trigger and Release only from its own turn", async () => {
  let now = 0;
  let sequence = 0;
  // Each legacy trigger round trip costs 125 ms, so the ninth queued input
  // would expire before dispatch if queue time were charged.
  const f = fixture({now: () => now, send: async (e) => {
    if (e.operation !== "trigger") return success(e, defaultResult(e.operation));
    now += 125;
    return success(e, e.payload.kind === "release" ? {accepted: true} : {sequence: ++sequence});
  }});
  await f.session.start();
  await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
  const keys = Array.from({length: 16}, () => ({}));
  const presses = keys.map((key, slot) => f.session.trigger(slot, 100, "keyboard", key));
  const releases = keys.map((key, slot) => f.session.release(slot, "keyboard", key));
  assert.deepEqual((await Promise.all(presses)).map(value => value.sequence),
    Array.from({length: 16}, (_, i) => i + 1));
  assert.deepEqual(await Promise.all(releases), Array(16).fill(true));
  await f.session.close();
});

test("keyless legacy retriggers of one Pad hold one position, as on main", async () => {
  let sequence = 0;
  const f = fixture({send: async (e) => e.operation === "trigger"
    ? success(e, e.payload.kind === "release" ? {accepted: true} : {sequence: ++sequence})
    : success(e, defaultResult(e.operation))});
  await f.session.start();
  await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
  // A one-shot caller that never releases must not exhaust the 64 positions.
  for (let index = 0; index < 200; index += 1)
    assert.equal((await f.session.trigger(0, 100, "pointer")).sequence, index + 1);
  const keys = Array.from({length: 63}, () => ({}));
  for (const [index, key] of keys.entries())
    assert.notEqual(await f.session.trigger(index + 1, 100, "pointer", key), false);
  // Slot 0's keyless position plus 63 keyed gestures fill the window.
  await assert.rejects(f.session.trigger(1, 100, "pointer", {}),
    error => error.code === "HOST_STATE_INVALID");
  // The keyless Release frees slot 0's position for a new keyed gesture.
  assert.equal(await f.session.release(0, "pointer"), true);
  assert.notEqual(await f.session.trigger(0, 100, "pointer", {}), false);
  await f.session.close();
});


for (const elapsed of [650, 1001]) {
  test(`legacy queued Release spends its original one-second budget at the real Host handoff (${elapsed}ms)`, async () => {
    let now = 0;
    let resolveQuery;
    let startedQuery;
    const queryStarted = new Promise(resolve => {startedQuery = resolve;});
    const releaseOptions = [];
    let sequence = 0;
    const f = fixture({now: () => now, send: async (e, options) => {
      if (e.operation === "project.inspect") {
        startedQuery();
        return new Promise(resolve => {resolveQuery = () => resolve(success(e, defaultResult(e.operation)));});
      }
      if (e.operation === "trigger") {
        if (e.payload.kind === "release") {
          releaseOptions.push(options.deadlineMs);
          return success(e, {accepted: true});
        }
        return success(e, {sequence: ++sequence});
      }
      return success(e, defaultResult(e.operation));
    }});
    await f.session.start();
    await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
    const key = {};
    assert.equal((await f.session.trigger(0, 100, "pointer", key)).sequence, 1);
    const query = f.session.inspectProject();
    await queryStarted;
    const release = f.session.release(0, "pointer", key);
    // Observe the original rejection immediately while its actual dispatch
    // remains parked; no timeout is widened or reset by query completion.
    const result = release.then(value => ({value}), error => ({error}));
    await drainTasks();
    assert.deepEqual(releaseOptions, []);
    now = elapsed;
    resolveQuery();
    await query;
    const observed = await result;
    if (elapsed < 1000) {
      assert.equal(observed.value, true);
      assert.deepEqual(releaseOptions, [1000 - elapsed]);
    } else {
      assert.equal(observed.error.code, "HOST_TIMEOUT");
      assert.equal(observed.error.details.pending, false);
      assert.deepEqual(releaseOptions, [], "expired original Release never reaches Native");
      // Only a fresh explicit retry after definite non-submission may use a
      // new budget, matching the still-retained original Press owner.
      assert.equal(await f.session.release(0, "pointer", key), true);
      assert.deepEqual(releaseOptions, [1000]);
    }
    assert.equal((await f.session.trigger(0, 100, "pointer", {})).sequence, 2);
    assert.equal(await f.session.release(0, "pointer"), true);
    await f.session.close();
  });
}


test("foreign Pattern Release cannot end a journal-only or differently-addressed original physical lease", async () => {
  const f = inputProfileFixture({extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  const journalKey = {};
  const journalLease = f.session.reserveInputGesture(journalKey, 0, "pointer");
  await f.session.recordPerformanceEvent(sharedPad(0), journalKey);
  journalLease.cancelUnsubmittedPattern();
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(x => x !== null));
  assert.equal(await f.session.release(1, "pointer", journalKey), false);
  assert.equal(await f.session.release(0, "keyboard", journalKey), false);
  assert.equal(await f.session.release(0, "pointer", journalKey), false,
    "journal-only owner has no Pattern Press whose Release can attest keyup");
  await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 3)});
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null,
    "foreign false and genuine journal Stop cannot retire a still-held physical lease");
  journalLease.releasePhysical();
  const patternKey = {};
  const patternLease = f.session.reserveInputGesture(patternKey, 0, "pointer");
  assert.notEqual(patternLease, null);
  assert.notEqual(await f.session.trigger(0, 100, "pointer", patternKey), false);
  assert.equal(await f.session.release(1, "pointer", patternKey), false);
  assert.equal(await f.session.release(0, "keyboard", patternKey), false);
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  assert.equal(await f.session.release(0, "pointer", patternKey), true,
    "only the exact original Pattern owner is actual matching Release authority");
  const finalLease = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(finalLease, null);
  finalLease.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});


test("foreign legacy Release success is not the journal-only physical owner's matching keyup", async () => {
  const f = fixture({send: async e => {
    const performance = sharedPerformanceReply(e);
    if (performance !== null) return performance;
    if (e.operation === "trigger") return success(e, {accepted: true});
    return success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  await f.session.recordPerformanceEvent(sharedPad(0), key);
  lease.cancelUnsubmittedPattern();
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(x => x !== null));
  // Preserve the old foreign wire API: a Native no-owner Release may return
  // true. Only a matching original local Press could attest physical end.
  assert.equal(await f.session.release(1, "pointer", key), true);
  assert.equal(await f.session.release(0, "keyboard", key), true);
  await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 4)});
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  lease.releasePhysical();
  const next = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(next, null);
  next.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});


for (const receipt of ["foreign-session", "foreign-request", "original-owner"]) {
  test(`shared journal capacity requires the original Stop session and request receipt (${receipt})`, async () => {
    let losePress = true;
    const stopRequestId = sharedId("8700", 5);
    const stops = [];
    const f = inputProfileFixture({extraSend: e => {
      if (e.operation === "performance.record.event" && losePress) {
        losePress = false;
        throw Object.assign(new Error("original Press receipt lost"),
          {code: "HOST_TIMEOUT", details: {pending: true}});
      }
      if (e.operation === "performance.record.stop") {
        stops.push(e.payload);
        return success(e, {
          request_id: receipt === "foreign-request" ? sharedId("8700", 6) : e.payload.request_id,
          session_id: receipt === "foreign-session" ? sharedId("8900", 0) : e.payload.session_id,
          performance_id: sharedId("8800", 0), state: "stopped", pending_event_count: 0,
          replayed: false, project_revision: null});
      }
      return sharedPerformanceReply(e);
    }});
    await activateInputProfile(f);
    const key = {};
    const lease = f.session.reserveInputGesture(key, 0, "pointer");
    await assert.rejects(f.session.recordPerformanceEvent(sharedPad(0), key), {code: "HOST_TIMEOUT"});
    lease.cancelUnsubmittedPattern();
    lease.releasePhysical();
    const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
    assert.ok(others.every(x => x !== null));
    assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
    const stop = f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: stopRequestId});
    if (receipt === "original-owner") {
      const result = await stop;
      assert.equal(result.requestId, stopRequestId);
      assert.equal(result.sessionId, SHARED_SESSION);
      const next = f.session.reserveInputGesture({}, 0, "pointer");
      assert.notEqual(next, null, "only this original genuine Stop can retire its unknown journal owner");
      next.cancelUnsubmittedPattern();
    } else {
      await assert.rejects(stop, {code: "HOST_PROTOCOL_MISMATCH"});
      assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null,
        "a valid outer envelope with a foreign nested receipt is no refund authority");
      await assert.rejects(f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: stopRequestId}),
        /cleanup token is already reserved/);
    }
    assert.deepEqual(stops, [{session_id: SHARED_SESSION, request_id: stopRequestId}]);
    for (const other of others) other.cancelUnsubmittedPattern();
    await f.session.close();
    if (receipt !== "original-owner") assert.equal(await f.session.waitForTerminalCleanup(), false,
      "a Pattern/backend close cannot substitute for the unknown journal Stop receipt");
  });
}


for (const profile of [true, false]) {
  test(`${profile ? "profile" : "legacy"} keyless Native Release preserves a still-held leased physical place after journal cleanup`, async () => {
    const legacyInputs = [];
    let sequence = 0;
    const f = profile ? inputProfileFixture({extraSend: sharedPerformanceReply})
      : fixture({send: async e => {
        const performance = sharedPerformanceReply(e);
        if (performance !== null) return performance;
        if (e.operation === "trigger") {
          legacyInputs.push(e.payload);
          return success(e, e.payload.kind === "release" ? {accepted: true} : {sequence: ++sequence});
        }
        return success(e, defaultResult(e.operation));
      }});
    if (profile) await activateInputProfile(f);
    else {
      await f.session.start();
      await f.session.activateAudio(createUserGestureToken({isTrusted: true}));
    }
    const key = {};
    const lease = f.session.reserveInputGesture(key, 0, "keyboard");
    await f.session.recordPerformanceEvent(sharedPad(0), key);
    assert.notEqual(await f.session.trigger(0, 100, "keyboard", key), false);
    lease.cancelUnsubmittedPattern(); // Already transferred; this is not a refund.
    const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
    assert.ok(others.every(x => x !== null));
    // Preserve actual old slot/source selection and native consume while the
    // physical keyboard is still down. This caller supplied NO physical key.
    assert.equal(await f.session.release(0, "keyboard"), true);
    if (profile) {
      const releases = f.sent.filter(e => e.operation === "pattern.transport.input.request" && e.payload.kind === "release");
      assert.equal(releases.length, 1);
      assert.equal(releases[0].payload.held_press_sequence, "1");
      assert.equal(f.sent.filter(e => e.operation === "pattern.transport.input.inspect" && e.payload.consume).length, 2);
    } else {
      assert.deepEqual(legacyInputs, [{slot: 0, velocity: 100}, {slot: 0, kind: "release"}]);
    }
    // Synthetic journal Release reuses the original UUID owner without a
    // physical key. Neither it nor a real matching journal Stop is keyup.
    await f.session.recordPerformanceEvent(sharedPad(0, "pad_release"));
    assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
    await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 7)});
    assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null,
      "both actual domains settled but their real physical lease is still held");
    lease.releasePhysical();
    const nextKey = {};
    const nextLease = f.session.reserveInputGesture(nextKey, 0, "keyboard");
    assert.notEqual(nextLease, null, "only actual physical end returned the shared place");
    assert.notEqual(await f.session.trigger(0, 100, "keyboard", nextKey), false);
    assert.equal(await f.session.release(0, "keyboard", nextKey), true,
      "explicit original key still ends the fresh physical gesture and consumes its Native owner");
    const finalLease = f.session.reserveInputGesture({}, 0, "pointer");
    assert.notEqual(finalLease, null);
    finalLease.cancelUnsubmittedPattern();
    for (const other of others) other.cancelUnsubmittedPattern();
    await f.session.close();
  });
}


test("prepared Performance Pad keeps its shared place after Pattern retirement and submits its snapshot once", async () => {
  const f = inputProfileFixture({now: () => 0, extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  const request = sharedPad(0);
  const prepared = f.session.preparePerformancePadEvent(request, key);
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(Boolean));
  await f.session.trigger(0, 100, "pointer", key);
  lease.releasePhysical();
  await f.session.release(0, "pointer", key);
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null,
    "actual Pattern consumption and keyup cannot retire a prepared Performance claim");
  request.event.slot = 1;
  const first = prepared.submit();
  assert.equal(prepared.submit(), first);
  await first;
  assert.equal(prepared.cancelBeforeSubmit(), false);
  assert.deepEqual(f.sent.filter(e => e.operation === "performance.record.event").map(e => e.payload.event),
    [{kind: "pad_press", gesture_id: sharedId("8200", 0), slot: 0, velocity: 100}]);
  const release = f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), key);
  await release.submit();
  const fresh = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(fresh, null);
  fresh.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});

test("prepared matching Release cannot run ahead of its Press or borrow a foreign physical owner", async () => {
  const f = fixture({now: () => 0, send: e => sharedPerformanceReply(e) ?? success(e, defaultResult(e.operation))});
  await f.session.start();
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  const press = f.session.preparePerformancePadEvent(sharedPad(0), key);
  assert.throws(() => f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), {}),
    /different physical owner/);
  assert.throws(() => f.session.preparePerformancePadEvent(sharedPad(1, "pad_release"), key),
    /different physical owner/);
  const premature = f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), key);
  await assert.rejects(premature.submit(), /Submit the original Pad Press/);
  assert.equal(premature.cancelBeforeSubmit(), false);
  await press.submit();
  const release = f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), key);
  assert.throws(() => f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), key), /already reserved/);
  await release.submit();
  lease.cancelUnsubmittedPattern();
  assert.notEqual(f.session.reserveInputGesture({}, 0, "pointer"), null);
  await f.session.close();
});

test("cancelling a prepared Press settles its unsubmitted Release pair without cancelling Pattern ownership", async () => {
  const f = inputProfileFixture({now: () => 0, extraSend: sharedPerformanceReply});
  await activateInputProfile(f);
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  await f.session.trigger(0, 100, "pointer", key);
  const press = f.session.preparePerformancePadEvent(sharedPad(0), key);
  const release = f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), key);
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(Boolean));
  assert.equal(press.cancelBeforeSubmit(), true);
  assert.equal(press.cancelBeforeSubmit(), false);
  await assert.rejects(press.submit(), /cancelled before submission/);
  await assert.rejects(release.submit(), /cancelled before submission/);
  assert.equal(f.sent.filter(e => e.operation === "performance.record.event").length, 0);
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null,
    "cancelled Performance preparation is not a Pattern retirement receipt");
  lease.releasePhysical();
  await f.session.release(0, "pointer", key);
  const fresh = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(fresh, null);
  fresh.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});

for (const boundary of ["stop", "close"]) {
  test(`prepared Pad descriptors are invalidated by actual ${boundary} without reaching the wire`, async () => {
    const wire = [];
    const f = fixture({now: () => 0, send: e => {
      if (e.operation === "performance.record.event") wire.push(e.payload);
      return sharedPerformanceReply(e) ?? success(e, defaultResult(e.operation));
    }});
    await f.session.start();
    const key = {};
    const lease = f.session.reserveInputGesture(key, 0, "pointer");
    const press = f.session.preparePerformancePadEvent(sharedPad(0), key);
    const release = f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), key);
    lease.cancelUnsubmittedPattern();
    lease.releasePhysical();
    if (boundary === "stop") await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 9)});
    else assert.equal(await f.session.close(), true);
    await assert.rejects(press.submit(), /cancelled before Core admission/);
    await assert.rejects(release.submit(), /cancelled before Core admission/);
    assert.deepEqual(wire, []);
    if (boundary === "stop") {
      const fresh = f.session.reserveInputGesture({}, 0, "pointer");
      assert.notEqual(fresh, null);
      fresh.cancelUnsubmittedPattern();
      await f.session.close();
    }
  });
}

for (const kind of ["pad_press", "pad_release"]) {
  test(`prepared ${kind} spends its budget only from its own turn, not across the Host wait`, async () => {
    let clock = 0;
    const wire = [];
    const f = fixture({now: () => clock, send: e => {
      if (e.operation === "performance.record.event") wire.push(e.payload.event.kind);
      return sharedPerformanceReply(e) ?? success(e, defaultResult(e.operation));
    }});
    await f.session.start();
    const key = {};
    const lease = f.session.reserveInputGesture(key, 0, "pointer");
    const press = f.session.preparePerformancePadEvent(sharedPad(0), key);
    let operation = press;
    if (kind === "pad_release") {
      await press.submit();
      clock = 100;
      lease.releasePhysical();
      operation = f.session.preparePerformancePadEvent(sharedPad(0, kind), key);
      clock = 1101;
    } else clock = 1001;
    await operation.submit();
    assert.deepEqual(wire, kind === "pad_release" ? ["pad_press", "pad_release"] : ["pad_press"]);
    lease.cancelUnsubmittedPattern();
    lease.releasePhysical();
    await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 10)});
    await f.session.close();
  });
}

test("prepared submitted-unknown Performance ownership cannot be cancelled by its observer", async () => {
  let lose = true;
  const f = inputProfileFixture({now: () => 0, extraSend: e => {
    if (e.operation === "performance.record.event" && lose) {
      lose = false;
      throw Object.assign(new Error("original prepared Press receipt lost"), {code: "HOST_TIMEOUT", details: {pending: true}});
    }
    return sharedPerformanceReply(e);
  }});
  await activateInputProfile(f);
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  const press = f.session.preparePerformancePadEvent(sharedPad(0), key);
  await assert.rejects(press.submit(), /original prepared Press receipt lost/);
  assert.equal(press.cancelBeforeSubmit(), false);
  lease.cancelUnsubmittedPattern();
  lease.releasePhysical();
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(Boolean));
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  await f.session.stopPerformanceRecording({sessionId: SHARED_SESSION, requestId: sharedId("8700", 11)});
  const fresh = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(fresh, null);
  fresh.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});


test("a prepared Press that expires in the Host queue cancels its queued Release without an orphan wire event", async () => {
  let clock = 0;
  const wire = [];
  let queryStarted;
  let releaseQuery;
  const started = new Promise(resolve => { queryStarted = resolve; });
  const gate = new Promise(resolve => { releaseQuery = resolve; });
  const f = fixture({now: () => clock, send: e => {
    if (e.operation === "project.inspect") {
      queryStarted();
      return gate.then(() => success(e, {project_revision: 7}));
    }
    if (e.operation === "performance.record.event") wire.push(e.payload.event.kind);
    return sharedPerformanceReply(e) ?? success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  const press = f.session.preparePerformancePadEvent(sharedPad(0), key);
  const release = f.session.preparePerformancePadEvent(sharedPad(0, "pad_release"), key);
  const query = f.session.inspectProject();
  await started;
  // The Press takes its turn, then waits behind the independent Host query
  // until its own one-second budget is spent.
  const results = Promise.allSettled([press.submit(), release.submit()]);
  await drainTasks();
  clock = 1001;
  releaseQuery();
  assert.equal((await query).project_revision, 7);
  assert.deepEqual(wire, [], "a definitely never-submitted Press owns no wire Release");
  assert.ok((await results).every(result => result.status === "rejected" &&
    result.reason.code === "HOST_TIMEOUT" && result.reason.details.pending === false));
  lease.cancelUnsubmittedPattern();
  lease.releasePhysical();
  assert.notEqual(f.session.reserveInputGesture({}, 0, "pointer"), null);
  await f.session.close();
});


test("a held headered Pad reply remains bound to its original recording after close", async () => {
  let enter, finish;
  const entered = new Promise(resolve => { enter = resolve; });
  const gate = new Promise(resolve => { finish = resolve; });
  const f = fixture({now: () => 0, send: async e => {
    if (e.operation === "performance.record.begin") return success(e, {
      performance_id: sharedId("8800", 0), committed_revision: 1, replayed: false,
      profile: "header_input_sequence", control_epoch: LIVE_EPOCH, core_control_ready: true,
      next_recording_sequence: "0", fx_bindings: [], project_revision: 1});
    if (e.operation === "performance.record.event") {
      assert.equal(e.payload.control_epoch, LIVE_EPOCH);
      assert.equal(e.payload.expected_recording_sequence, "0");
      enter();
      await gate;
      return success(e, {event_id: e.payload.event_id, accepted_tick: 0,
        input_sequence: "1", next_recording_sequence: "1", result: "no_audio",
        coalesced: false, gesture_generation: null, recording_gesture_id: null,
        replayed: false, project_revision: null});
    }
    return success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  await f.session.beginPerformanceRecording({sessionId: SHARED_SESSION,
    performanceId: sharedId("8800", 0), expectedRevision: 0, controlEpoch: LIVE_EPOCH});
  const key = {};
  const lease = f.session.reserveInputGesture(key, 0, "pointer");
  const prepared = f.session.preparePerformancePadEvent(sharedPad(0), key);
  const press = prepared.submit();
  // Attach before close so the real rejected receipt is observed in RED.
  const result = press.then(value => ({ok: true, value}), error => ({ok: false, error}));
  await entered;
  lease.cancelUnsubmittedPattern();
  lease.releasePhysical();
  const closing = f.session.close();
  finish();
  const actual = await result;
  assert.equal(actual.ok, true, `original headered response lost: ${actual.error?.message}`);
  assert.equal(actual.value.eventId, sharedPad(0).eventId);
  assert.equal(actual.value.nextRecordingSequence, "1");
  assert.equal(prepared.cancelBeforeSubmit(), false);
  await closing;
  assert.equal(await f.session.waitForTerminalCleanup(), false,
    "Host closure does not prove this original Performance journal Press retired");
});


test("direct exact replay cannot submit a still-prepared Press outside its token", async () => {
  const wire = [];
  const f = fixture({now: () => 0, send: e => {
    if (e.operation === "performance.record.event") wire.push(e.payload.event.kind);
    return sharedPerformanceReply(e) ?? success(e, defaultResult(e.operation));
  }});
  await f.session.start();
  const request = sharedPad(0);
  const prepared = f.session.preparePerformancePadEvent(request);
  const direct = await f.session.recordPerformanceEvent(request).then(() => null, error => error);
  assert.deepEqual(wire, [], "the exact replay cannot bypass a never-submitted token's ownership");
  assert.equal(direct.code, "HOST_STATE_INVALID");
  assert.equal(prepared.cancelBeforeSubmit(), true);
  await assert.rejects(prepared.submit(), /cancelled before submission/);
  const nextRequest = sharedPad(1);
  const next = f.session.preparePerformancePadEvent(nextRequest);
  const others = Array.from({length: 63}, () => f.session.reserveInputGesture({}, 0, "pointer"));
  assert.ok(others.every(Boolean));
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  await next.submit();
  assert.equal(next.cancelBeforeSubmit(), false);
  // Once the original token handed off, exact replay keeps the old bounded
  // ordinary API and cannot allocate a second shared position.
  await f.session.recordPerformanceEvent(nextRequest);
  assert.equal(f.session.reserveInputGesture({}, 0, "pointer"), null);
  await f.session.recordPerformanceEvent(sharedPad(1, "pad_release"));
  assert.deepEqual(wire, ["pad_press", "pad_press", "pad_release"]);
  const fresh = f.session.reserveInputGesture({}, 0, "pointer");
  assert.notEqual(fresh, null);
  fresh.cancelUnsubmittedPattern();
  for (const other of others) other.cancelUnsubmittedPattern();
  await f.session.close();
});
function headeredFxShapeFixture() {
  const sessionId = "40000000-0000-4000-8000-000000000201";
  const performanceId = "40000000-0000-4000-8000-000000000202";
  const coreBinding = {
    gesture_generation: "40000000-0000-4000-8000-000000000203",
    recording_gesture_id: "40000000-0000-4000-8000-000000000204",
  };
  // A Core cursor beyond Number's exact range must remain an opaque string.
  const initialSequence = "9007199254740993";
  let nextSequence = BigInt(initialSequence);
  const sent = [];
  const receipts = [];
  const {session} = fixture({send: async (envelope) => {
    switch (envelope.operation) {
      case "performance.record.begin":
        return success(envelope, {performance_id: performanceId, committed_revision: 1,
          replayed: false, profile: "header_input_sequence", control_epoch: LIVE_EPOCH,
          core_control_ready: true, next_recording_sequence: initialSequence,
          fx_bindings: [], project_revision: 1});
      case "performance.record.event": {
        sent.push(envelope.payload);
        const receipt = {
          event_id: envelope.payload.event_id, accepted_tick: 17,
          input_sequence: String(nextSequence), next_recording_sequence: String(++nextSequence),
          result: "published", coalesced: false,
          ...(envelope.payload.event.kind === "fx_engage" ? coreBinding : {
            gesture_generation: null, recording_gesture_id: null,
          }),
          replayed: false, project_revision: null,
        };
        receipts.push(receipt);
        return success(envelope, receipt);
      }
      default: return success(envelope, defaultResult(envelope.operation));
    }
  }});
  return {session, sessionId, performanceId, initialSequence, sent, receipts};
}

for (const fx of ["delay", "reverb", "stutter", "gate", "reverse", "crush", "cutter"]) {
  test(`headered ${fx} FX wires engage, move and release with returned Core identities`, async (t) => {
    const {session, sessionId, performanceId, initialSequence, sent, receipts} = headeredFxShapeFixture();
    t.after(() => session.close());
    await session.start();
    const begun = await session.beginPerformanceRecording({sessionId, performanceId,
      expectedRevision: 0, controlEpoch: LIVE_EPOCH});
    assert.equal(begun.nextRecordingSequence, initialSequence);
    const engageId = webcrypto.randomUUID();
    const engaged = await session.recordPerformanceEvent({sessionId, eventId: engageId,
      event: {kind: "fx_engage", fx, value: 500}});
    assert.deepEqual(sent[0], {
      session_id: sessionId, event_id: engageId,
      control_epoch: LIVE_EPOCH, expected_recording_sequence: initialSequence,
      event: {kind: "fx_engage", fx, value: 500},
    });
    assert.deepEqual(engaged, {
      eventId: engageId, acceptedTick: 17,
      inputSequence: receipts[0].input_sequence,
      nextRecordingSequence: receipts[0].next_recording_sequence,
      result: "published", coalesced: false,
      gestureGeneration: receipts[0].gesture_generation,
      recordingGestureId: receipts[0].recording_gesture_id,
      replayed: false, projectRevision: null,
    });
    // The caller echoes the public receipt; it does not invent a legacy ID.
    const binding = {gestureId: engaged.recordingGestureId,
      gestureGeneration: engaged.gestureGeneration};
    assert.equal(typeof binding.gestureId, "string");
    assert.equal(typeof binding.gestureGeneration, "string");
    for (const [kind, values] of [["fx_move", {value: 600}], ["fx_release", {}]]) {
      const eventId = webcrypto.randomUUID();
      const expectedSequence = receipts.at(-1).next_recording_sequence;
      const result = await session.recordPerformanceEvent({sessionId, eventId,
        event: {kind, fx, ...values, ...binding}});
      assert.deepEqual(sent.at(-1), {
        session_id: sessionId, event_id: eventId,
        control_epoch: LIVE_EPOCH, expected_recording_sequence: expectedSequence,
        event: {kind, fx, ...values, gesture_id: binding.gestureId,
          gesture_generation: binding.gestureGeneration},
      });
      assert.deepEqual(result, {
        eventId, acceptedTick: 17, inputSequence: receipts.at(-1).input_sequence,
        nextRecordingSequence: receipts.at(-1).next_recording_sequence,
        result: "published", coalesced: false,
        gestureGeneration: null, recordingGestureId: null,
        replayed: false, projectRevision: null,
      });
    }
    assert.equal(sent.length, 3);
  });
}

const HEADERED_FX_SHAPE_BINDING = {
  gestureId: "40000000-0000-4000-8000-000000000205",
  gestureGeneration: "40000000-0000-4000-8000-000000000206",
};
for (const [name, event] of [
  ["engage with legacy ID", {kind: "fx_engage", fx: "delay", value: 500,
    gestureId: HEADERED_FX_SHAPE_BINDING.gestureId}],
  ["engage with generation", {kind: "fx_engage", fx: "delay", value: 500,
    gestureGeneration: HEADERED_FX_SHAPE_BINDING.gestureGeneration}],
  ["engage with both identities", {kind: "fx_engage", fx: "delay", value: 500,
    ...HEADERED_FX_SHAPE_BINDING}],
  ["engage without value", {kind: "fx_engage", fx: "delay"}],
  ["move without value", {kind: "fx_move", fx: "delay", ...HEADERED_FX_SHAPE_BINDING}],
  ["move without generation", {kind: "fx_move", fx: "delay", value: 600,
    gestureId: HEADERED_FX_SHAPE_BINDING.gestureId}],
  ["move without ID", {kind: "fx_move", fx: "delay", value: 600,
    gestureGeneration: HEADERED_FX_SHAPE_BINDING.gestureGeneration}],
  ["release without generation", {kind: "fx_release", fx: "delay",
    gestureId: HEADERED_FX_SHAPE_BINDING.gestureId}],
  ["release without ID", {kind: "fx_release", fx: "delay",
    gestureGeneration: HEADERED_FX_SHAPE_BINDING.gestureGeneration}],
  ["release with value", {kind: "fx_release", fx: "delay", value: 600,
    ...HEADERED_FX_SHAPE_BINDING}],
]) {
  test(`headered FX rejects ${name} before transport and retains the cursor`, async (t) => {
    const {session, sessionId, performanceId, initialSequence, sent} = headeredFxShapeFixture();
    t.after(() => session.close());
    await session.start();
    await session.beginPerformanceRecording({sessionId, performanceId,
      expectedRevision: 0, controlEpoch: LIVE_EPOCH});
    await assert.rejects(session.recordPerformanceEvent({sessionId,
      eventId: webcrypto.randomUUID(), event}), TypeError);
    assert.deepEqual(sent, []);
    const eventId = webcrypto.randomUUID();
    await session.recordPerformanceEvent({sessionId, eventId,
      event: {kind: "fx_engage", fx: "delay", value: 500}});
    assert.deepEqual(sent, [{
      session_id: sessionId, event_id: eventId, control_epoch: LIVE_EPOCH,
      expected_recording_sequence: initialSequence,
      event: {kind: "fx_engage", fx: "delay", value: 500},
    }]);
  });
}

test("legacy FX keeps its ID-bound engage, move and no-value release wire", async (t) => {
  const sessionId = "40000000-0000-4000-8000-000000000207";
  const performanceId = "40000000-0000-4000-8000-000000000208";
  const {gestureId, gestureGeneration} = HEADERED_FX_SHAPE_BINDING;
  const sent = [];
  const {session} = fixture({send: async (envelope) => {
    if (envelope.operation === "performance.record.begin") {
      return success(envelope, {performance_id: performanceId,
        committed_revision: 1, replayed: false, project_revision: 1});
    }
    if (envelope.operation === "performance.record.event") {
      sent.push(envelope.payload);
      return success(envelope, {event_id: envelope.payload.event_id,
        accepted_tick: 17, input_sequence: sent.length, coalesced: false,
        replayed: false, project_revision: null});
    }
    return success(envelope, defaultResult(envelope.operation));
  }});
  t.after(() => session.close());
  await session.start();
  await session.beginPerformanceRecording({sessionId, performanceId, expectedRevision: 0});
  for (const [kind, values] of [
    ["fx_engage", {value: 500}], ["fx_move", {value: 600}], ["fx_release", {}],
  ]) {
    const before = sent.length;
    await assert.rejects(session.recordPerformanceEvent({sessionId,
      eventId: webcrypto.randomUUID(), event: {kind, fx: "delay", ...values}}), TypeError);
    await assert.rejects(session.recordPerformanceEvent({sessionId,
      eventId: webcrypto.randomUUID(), event: {kind, fx: "delay", ...values,
        gestureId, gestureGeneration}}), TypeError);
    assert.equal(sent.length, before);
    const eventId = webcrypto.randomUUID();
    const result = await session.recordPerformanceEvent({sessionId, eventId,
      event: {kind, fx: "delay", ...values, gestureId}});
    assert.deepEqual(sent.at(-1), {session_id: sessionId, event_id: eventId,
      event: {kind, fx: "delay", ...values, gesture_id: gestureId}});
    assert.deepEqual(result, {eventId, acceptedTick: 17, inputSequence: sent.length,
      coalesced: false, replayed: false, projectRevision: null});
  }
  assert.equal(sent.length, 3);
});

for (const variant of ["ack", "delayed-status", "other-session", "other-epoch"]) {
  test(`headered recording cursor follows matching observed status: ${variant}`, async () => {
    const sessionId = "40000000-0000-4000-8000-000000000060";
    const performanceId = "40000000-0000-4000-8000-000000000061";
    let observedSequence = "2";
    let events = 0;
    const sent = [];
    const {session} = fixture({send: async (envelope) => {
      switch (envelope.operation) {
        case "performance.record.begin":
          return success(envelope, {performance_id: performanceId, committed_revision: 1,
            replayed: false, profile: "header_input_sequence", control_epoch: LIVE_EPOCH,
            core_control_ready: true, next_recording_sequence: "1", fx_bindings: [],
            project_revision: 1});
        case "performance.record.status": {
          const result = {state: "active", session_id: variant === "other-session"
              ? "40000000-0000-4000-8000-000000000099" : sessionId,
            performance_id: performanceId, journal_revision: 1, next_flush_seq: 1,
            pending_event_count: 0, open_pad_gestures: 0, open_fx_gestures: 0,
            hold: false, pending_launch: null, last_launch_ack: null,
            profile: "header_input_sequence", control_epoch: variant === "other-epoch"
              ? "40000000-0000-4000-8000-000000000098" : LIVE_EPOCH,
            core_control_ready: true, next_recording_sequence: observedSequence,
            pending_admission: null, project_revision: null};
          return success(envelope, result);
        }
        case "performance.record.event":
          sent.push(envelope.payload.expected_recording_sequence);
          events += 1;
          return success(envelope, {event_id: envelope.payload.event_id, accepted_tick: events,
            input_sequence: String(events), next_recording_sequence: String(events + 1),
            result: "no_audio", coalesced: false, gesture_generation: null,
            recording_gesture_id: null, replayed: false, project_revision: null});
        default: return success(envelope, defaultResult(envelope.operation));
      }
    }});
    await session.start();
    await session.beginPerformanceRecording({sessionId, performanceId,
      expectedRevision: 0, controlEpoch: LIVE_EPOCH});
    const input = () => session.recordPerformanceEvent({sessionId,
      eventId: webcrypto.randomUUID(), event: {kind: "hold_on"}});
    if (variant === "delayed-status") {
      await input();
      // A stale status payload must not roll back a later admitted receipt.
      observedSequence = "1";
    }
    await session.queryPerformanceRecordingStatus();
    await input();
    const expected = variant === "other-session" || variant === "other-epoch" ? "1"
      : "2";
    assert.equal(sent.at(-1), expected,
      "the next real input must echo the matching Core cursor without regression");
    await session.close();
  });
}

for (const coreStopFails of [false, true]) {
  test(`headered owned capture drains final PCM and the queue after Core stop ${coreStopFails ? "failure" : "receipt"}`, async () => {
    const sessionId = "40000000-0000-4000-8000-000000000060";
    const performanceId = "40000000-0000-4000-8000-000000000061";
    const gestureId = "40000000-0000-4000-8000-000000000062";
    const gestureGeneration = "40000000-0000-4000-8000-000000000063";
    const recordingGestureId = "40000000-0000-4000-8000-000000000064";
    const coreFailure = {code: "IO_ERROR", message: "Core stop journal failed", details: {}};
    let finishCoreStop;
    let finishWrites;
    let finishSeal;
    const coreStopped = new Promise((resolve) => { finishCoreStop = resolve; });
    const writesReady = new Promise((resolve) => { finishWrites = resolve; });
    const sealReady = new Promise((resolve) => { finishSeal = resolve; });
    let sequence = 0;
    const runtime = masterCaptureFixture({send: async (envelope) => {
      switch (envelope.operation) {
        case "performance.record.begin":
          return success(envelope, {
            performance_id: performanceId, committed_revision: 1,
            replayed: false, project_revision: 1,
            profile: "header_input_sequence", control_epoch: LIVE_EPOCH,
            core_control_ready: true, next_recording_sequence: "0",
            fx_bindings: [{fx: "delay", gesture_generation: gestureGeneration,
              recording_gesture_id: recordingGestureId}],
          });
        case "performance.record.event":
          runtime.order.push(envelope.payload.event.kind);
          sequence += 1;
          return success(envelope, {
            event_id: envelope.payload.event_id, accepted_tick: 4,
            input_sequence: String(sequence), next_recording_sequence: String(sequence),
            result: "no_audio", coalesced: false, gesture_generation: null,
            recording_gesture_id: null, replayed: false, project_revision: null,
          });
        case "performance.record.stop":
          runtime.order.push("core:stop-request");
          await coreStopped;
          runtime.order.push(coreStopFails ? "core:stop-failed" : "core:stop-receipt");
          return coreStopFails ? {
            protocol_version: 1, request_id: envelope.request_id,
            ok: false, error: coreFailure,
          } : success(envelope, {
            request_id: envelope.payload.request_id, session_id: sessionId,
            performance_id: performanceId, state: "stopped", pending_event_count: 0,
            replayed: false, project_revision: null,
          });
        default:
          return success(envelope, defaultResult(envelope.operation));
      }
    }});
    // The actual queue owns append/seal ordering. This controlled writer
    // models durable receipts; it does not exercise OPFS or the Creator UI.
    const appended = [];
    let durableFrames = 0;
    const queue = new MasterTapBatchQueue({
      queueBatchLimit: 32,
      async appendChannels(channels) {
        await writesReady;
        appended.push(channels);
        durableFrames += channels[0].length;
        runtime.order.push(`writer:append:${channels[0].length}`);
        return {state: "active", durableFrames, byteLength: 44 + durableFrames * 4, reason: null};
      },
      async seal(reason) {
        runtime.order.push("writer:seal");
        await sealReady;
        return {state: "sealed", durableFrames, byteLength: 44 + durableFrames * 4, reason};
      },
    }, {
      onFailure() { assert.fail("capture and writer must remain healthy"); },
      requestCaptureStop() { assert.fail("normal owner cleanup stops the capture"); },
    });
    const {session} = runtime;
    await session.start();
    await session.activateAudio(createUserGestureToken({isTrusted: true}));
    const begun = await session.beginPerformanceRecording({
      sessionId, performanceId, expectedRevision: 0, controlEpoch: LIVE_EPOCH,
      captureSink: queue,
    });
    assert.equal(Object.isFrozen(begun.capture), true);
    assert.deepEqual(begun.fxBindings, [{fx: "delay", gestureGeneration, recordingGestureId}]);
    assert.equal(Object.isFrozen(begun.fxBindings[0]), true);
    const full = [new Float32Array(4_800).fill(0.25), new Float32Array(4_800).fill(-0.5)];
    const partial = [Float32Array.from({length: 127}, (_, i) => i / 128), new Float32Array(127).fill(-0.25)];
    for (const input of [full, partial]) {
      const output = input.map((channel) => new Float32Array(channel.length));
      assert.equal(runtime.processor.process([input], [output]), true);
      assert.deepEqual(output, input);
    }
    assert.equal(queue.pendingBatches, 1, "partial PCM stays in the worklet until stop");
    const press = await session.recordPerformanceEvent({
      sessionId, eventId: "40000000-0000-4000-8000-000000000065",
      event: {kind: "pad_press", slot: 2, gestureId, velocity: 100},
    });
    assert.equal(press.inputSequence, "1");
    const release = await session.recordPerformanceEvent({
      sessionId, eventId: "40000000-0000-4000-8000-000000000066",
      event: {kind: "pad_release", slot: 2, gestureId},
    });
    assert.equal(release.inputSequence, "2");

    let observedCoreFailure = null;
    let ownerSettled = false;
    const stopping = (async () => {
      try {
        const stopped = await session.stopPerformanceRecording({
          sessionId, requestId: "40000000-0000-4000-8000-000000000067",
        });
        assert.equal(stopped.state, "stopped");
      } catch (error) {
        observedCoreFailure = error;
      }
      const captureStop = begun.capture.stop();
      assert.equal(begun.capture.stop(), captureStop);
      await captureStop;
      runtime.order.push("owner:capture-stopped");
      const sealed = await queue.settled;
      runtime.order.push("owner:queue-settled");
      if (observedCoreFailure !== null) throw observedCoreFailure;
      return sealed;
    })();
    const outcome = stopping.then(
      (value) => { ownerSettled = true; return {value}; },
      (error) => { ownerSettled = true; return {error}; },
    );
    await drainTasks();
    assert.deepEqual(runtime.order.slice(-3), ["pad_press", "pad_release", "core:stop-request"]);
    assert.equal(runtime.commands.some(({type}) => type === "stop"), false);
    finishCoreStop();
    await drainTasks();
    assert.deepEqual(runtime.commands.filter(({type}) => type === "stop"), [
      {type: "stop", generation: 1},
    ]);
    assert.deepEqual(runtime.messages.map(({type}) => type), ["started", "batch", "batch", "stopped"]);
    assert.deepEqual({...runtime.messages.at(-1)}, {type: "stopped", generation: 1, finalSequence: 2});
    assert.equal(queue.pendingBatches, 2);
    assert.equal(queue.sealed, false);
    assert.deepEqual(appended, []);
    assert.equal(ownerSettled, false, "capture ACK cannot stand in for durable PCM");
    finishWrites();
    await drainTasks();
    assert.deepEqual(appended.map((channels) => [...channels]), [full, partial]);
    assert.equal(queue.pendingBatches, 0);
    assert.equal(queue.sealed, true);
    assert.equal(ownerSettled, false, "queue settlement still awaits the seal receipt");
    finishSeal();
    const completed = await outcome;
    const sealed = await queue.settled;
    assert.deepEqual(sealed, {
      state: "sealed", durableFrames: 4_927, byteLength: 19_752,
      reason: "stopped", droppedFrames: 0,
    });
    if (coreStopFails) {
      assert.equal(completed.error, observedCoreFailure);
      assert.equal(completed.error.code, coreFailure.code);
      assert.equal(completed.error.message, "Host request was rejected");
    } else {
      assert.equal(observedCoreFailure, null);
      assert.equal(completed.value, sealed);
    }
    assert.deepEqual(runtime.order.slice(-9), [
      coreStopFails ? "core:stop-failed" : "core:stop-receipt",
      "host:stop:1", "tap:batch:1", "tap:stopped:1", "owner:capture-stopped",
      "writer:append:4800", "writer:append:127", "writer:seal", "owner:queue-settled",
    ]);
    await session.close();
    assert.equal(runtime.commands.filter(({type}) => type === "stop").length, 1);
  });
}
