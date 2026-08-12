import {
  DEFAULT_KEYBOARD_MAPPING,
  createUserGestureToken,
  createKeyboardAdapter,
  createMidiAdapter,
  createPointerAdapter,
  flattenPadSlot,
} from "./input_adapters.mjs";
import {registerDiagnosticTransport} from "./diagnostic_client.mjs";
import {
  importProjectBundle,
  normalizeLocalProjectSummary,
} from "./project_bundle_reader.mjs";
import {
  createPackagedRuntimeLocator,
  defaultRuntimeTerminator,
} from "./runtime_loader.mjs";
import { PREFLIGHT_CAPABILITIES, runPreflight } from "./preflight.mjs";
import {
  HostProtocolError,
  createRequestEnvelope,
  deadlineForOperation,
  validateNotificationEnvelope,
  validateResponseEnvelope,
} from "./protocol.mjs";
import {canonicalJson, exactKeys, sha256Hex} from "./integrity.mjs";
import { createHostStateMachine } from "./state_machine.mjs";

const HOST_MANIFEST_MAXIMUM_BYTES = 65_536;
const TRIGGER_LEDGER_LIMIT = 4_096;
const RECOVERY_OUTCOME_DEADLINE_MS = 1_000;
const TRIGGER_SOURCES = new Set(["pointer", "keyboard", "midi"]);
const SAFE_ERROR_DETAIL_NAMES = new Set([
  "mutation_outcome",
  "resource",
  "storage_condition",
  "terminal_state",
]);
const ALLOWED_TYPED_ERROR_CODES = new Set([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "REVISION_CONFLICT",
  "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO",
  "MISSING_ASSET",
  "INVALID_PROJECT",
  "COOK_FAILED",
  "PROVIDER_NOT_FOUND",
  "PROVIDER_FAILED",
  "PERMISSION_DENIED",
  "IO_ERROR",
  "INTERNAL_ERROR",
  "UNSUPPORTED_WEB_RUNTIME",
  "PROJECT_BUSY",
  "WEB_RUNTIME_RESOURCE_LIMIT",
  "HOST_STATE_INVALID",
  "HOST_TIMEOUT",
  "HOST_RESTART_REQUIRED",
  "HOST_PROTOCOL_MISMATCH",
]);

function typedError(code, message = code) {
  return new HostProtocolError(code, message, {});
}

function validatedErrorCode(value, fallback = "HOST_STATE_INVALID") {
  if (ALLOWED_TYPED_ERROR_CODES.has(value)) {
    return value;
  }
  return typeof value === "string" ? "HOST_PROTOCOL_MISMATCH" : fallback;
}

function errorCode(error, fallback = "HOST_STATE_INVALID") {
  return validatedErrorCode(error?.code, fallback);
}

function safeErrorDetails(error) {
  const source = error?.details;
  if (source === null || typeof source !== "object" || Array.isArray(source)) {
    return Object.freeze({});
  }
  const details = {};
  for (const name of ["observed", "limit"]) {
    const value = source[name];
    if (Number.isSafeInteger(value) && value >= 0) {
      details[name] = value;
    }
  }
  for (const name of SAFE_ERROR_DETAIL_NAMES) {
    const value = source[name];
    if (typeof value === "string" && /^[a-z0-9._-]{1,64}$/.test(value)) {
      details[name] = value;
    }
  }
  return Object.freeze(details);
}

function requireFunction(value, name) {
  if (typeof value !== "function") {
    throw new TypeError(`${name} must be injected`);
  }
  return value;
}

function isPositiveInteger(value) {
  return Number.isInteger(value) && value > 0;
}

function generationsMatch(status) {
  return (
    isPositiveInteger(status?.control_generation) &&
    isPositiveInteger(status?.acknowledged_generation) &&
    status.control_generation === status.acknowledged_generation
  );
}

async function probeControlWorkerCapabilities(scope) {
  if (typeof scope.Worker !== "function" || typeof scope.Blob !== "function") {
    return {
      opfs: false,
      opfsSyncAccessHandle: false,
      opfsWritableReplace: false,
    };
  }
  const source = `
    self.onmessage = async (event) => {
      const probeName = event.data;
      let root = null;
      let sync = null;
      let writable = null;
      const result = {
        opfs: false,
        opfsSyncAccessHandle: false,
        opfsWritableReplace: false,
      };
      try {
        root = await navigator.storage.getDirectory();
        result.opfs = true;
        const file = await root.getFileHandle(probeName, {create: true});
        sync = await file.createSyncAccessHandle();
        result.opfsSyncAccessHandle = true;
        sync.close();
        sync = null;
        writable = await file.createWritable({keepExistingData: false});
        await writable.close();
        writable = null;
        result.opfsWritableReplace = true;
      } catch {}
      try { sync?.close(); } catch {}
      try { await writable?.abort(); } catch {}
      try { await root?.removeEntry(probeName); } catch {}
      self.postMessage(result);
    };
  `;
  const url = scope.URL.createObjectURL(new scope.Blob([source], {
    type: "text/javascript",
  }));
  const worker = new scope.Worker(url);
  const probeName = `.lmdj-capability-probe-${scope.crypto.randomUUID()}`;
  try {
    return await new Promise((resolvePromise) => {
      const timeout = scope.setTimeout(() => {
        resolvePromise({
          opfs: false,
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
        });
      }, 2_000);
      worker.addEventListener("message", (event) => {
        scope.clearTimeout(timeout);
        resolvePromise(event.data);
      }, { once: true });
      worker.addEventListener("error", () => {
        scope.clearTimeout(timeout);
        resolvePromise({
          opfs: false,
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
        });
      }, { once: true });
      worker.postMessage(probeName);
    });
  } finally {
    worker.terminate();
    scope.URL.revokeObjectURL(url);
  }
}

async function defaultCapabilities(scope) {
  const controlWorker = await probeControlWorkerCapabilities(scope);
  return {
    secureContext: scope.isSecureContext === true,
    crossOriginIsolated: scope.crossOriginIsolated === true,
    sharedArrayBuffer: typeof scope.SharedArrayBuffer === "function",
    webAssembly: typeof scope.WebAssembly === "object",
    audioWorklet:
      typeof scope.AudioContext === "function" &&
      "audioWorklet" in scope.AudioContext.prototype,
    ...controlWorker,
  };
}

function metaContent(document, name) {
  return document
    ?.querySelector?.(`meta[name='${name}']`)
    ?.getAttribute?.("content");
}

async function readBoundedResponse(response, maximumBytes) {
  if (response?.ok !== true) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest or asset is unavailable");
  }
  const declared = Number.parseInt(response.headers?.get?.("content-length") ?? "", 10);
  if (Number.isFinite(declared) && declared > maximumBytes) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest or asset is oversized");
  }
  if (typeof response.body?.getReader !== "function") {
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > maximumBytes) {
      throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest or asset is oversized");
    }
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      total += value.byteLength;
      if (total > maximumBytes) {
        throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest or asset is oversized");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock?.();
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

function validatePackagedManifest(
  manifest,
  expected,
  assemblyIdentity,
  manifestSource,
) {
  const expectedAssets = manifestSource?.expectedAssets;
  const expectedResourceLimits = manifestSource?.resourceLimits;
  const expectedEmscripten = manifestSource?.emscripten;
  const expectedCompatibleHosts = manifestSource?.compatibleHosts;
  const manifestKeys = [
    "assets",
    ...(expectedCompatibleHosts === undefined ? [] : ["compatible_hosts"]),
    "distribution_contract",
    "emscripten",
    "heap_bytes",
    "host_id",
    "host_version",
    "manifest_version",
    "platform_version",
    "product_build",
    "protocol_version",
    "resource_limits",
  ];
  if (
    !exactKeys(manifest, manifestKeys) ||
    manifest.distribution_contract !== assemblyIdentity.distributionContract ||
    manifest.manifest_version !== 1 ||
    manifest.product_build !== expected.product_build ||
    manifest.product_build !== assemblyIdentity.productBuild ||
    manifest.host_id !== expected.host_id ||
    manifest.host_id !== assemblyIdentity.hostId ||
    manifest.host_version !== expected.host_version ||
    manifest.host_version !== assemblyIdentity.hostVersion ||
    manifest.platform_version !== expected.platform_version ||
    manifest.platform_version !== assemblyIdentity.platformVersion ||
    manifest.protocol_version !== expected.protocol_version ||
    manifest.protocol_version !== assemblyIdentity.protocolVersion ||
    manifest.heap_bytes !== manifestSource?.heapBytes ||
    !exactKeys(manifest.resource_limits, Object.keys(expectedResourceLimits ?? {})) ||
    Object.entries(expectedResourceLimits ?? {}).some(
      ([name, value]) => manifest.resource_limits[name] !== value,
    ) ||
    !exactKeys(manifest.emscripten, [
      "emcc_version",
      "emscripten_releases_revision",
      "emsdk_revision",
      "emsdk_tag",
    ]) ||
    Object.entries(expectedEmscripten ?? {}).some(
      ([name, value]) => manifest.emscripten[name] !== value,
    ) ||
    (expectedCompatibleHosts !== undefined && (
      !Array.isArray(manifest.compatible_hosts) ||
      manifest.compatible_hosts.length !== expectedCompatibleHosts.length ||
      manifest.compatible_hosts.some((host, index) =>
        !exactKeys(host, ["host_id", "host_version"]) ||
        host.host_id !== expectedCompatibleHosts[index]?.host_id ||
        host.host_version !== expectedCompatibleHosts[index]?.host_version
      )
    )) ||
    !Array.isArray(manifest.assets) ||
    !Array.isArray(expectedAssets) ||
    manifest.assets.length !== expectedAssets.length
  ) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest identity is invalid");
  }
  for (let index = 0; index < manifest.assets.length; index += 1) {
    const asset = manifest.assets[index];
    const expectedAsset = expectedAssets[index];
    if (
      !exactKeys(asset, ["bytes", "path", "role", "sha256"]) ||
      !Number.isSafeInteger(asset.bytes) ||
      asset.bytes < 1 ||
      typeof asset.path !== "string" ||
      !/^assets\/[a-z0-9-]+\.[0-9a-f]{64}\.(?:css|js|mjs|wasm)$/.test(asset.path) ||
      typeof asset.role !== "string" ||
      !/^[0-9a-f]{64}$/.test(asset.sha256) ||
      asset.path !== `${expectedAsset.prefix}${asset.sha256}${expectedAsset.suffix}` ||
      asset.role !== expectedAsset.role
    ) {
      throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest asset is invalid");
    }
  }
}

async function verifyPackagedManifest({
  document,
  window,
  crypto,
  assemblyIdentity,
  manifestSource,
}) {
  const manifestPath = metaContent(document, "lmdj-host-manifest-path");
  const expectedDigest = metaContent(document, "lmdj-host-manifest-sha256");
  const expected = {
    product_build: metaContent(document, "lmdj-product-build"),
    host_id: metaContent(document, "lmdj-host-id"),
    host_version: metaContent(document, "lmdj-host-version"),
    platform_version: metaContent(
      document,
      "lmdj-web-runtime-platform-version",
    ),
    protocol_version: Number.parseInt(
      metaContent(document, "lmdj-host-protocol-version") ?? "",
      10,
    ),
  };
  if (
    typeof manifestPath !== "string" ||
    manifestPath !== "./host-manifest.json" ||
    !/^[0-9a-f]{64}$/.test(expectedDigest ?? "") ||
    typeof expected.product_build !== "string" ||
    expected.product_build !== assemblyIdentity.productBuild ||
    expected.host_id !== assemblyIdentity.hostId ||
    expected.host_version !== assemblyIdentity.hostVersion ||
    expected.platform_version !== assemblyIdentity.platformVersion ||
    expected.protocol_version !== assemblyIdentity.protocolVersion
  ) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest metadata is absent");
  }
  try {
    const response = await window.fetch(
      new URL(manifestPath, document.baseURI).href,
      { cache: "no-store", credentials: "same-origin" },
    );
    const bytes = await readBoundedResponse(response, HOST_MANIFEST_MAXIMUM_BYTES);
    const actualDigest = await sha256Hex(bytes, crypto);
    if (actualDigest !== expectedDigest) {
      throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest digest does not match");
    }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const manifest = JSON.parse(text);
    if (canonicalJson(manifest) !== text) {
      throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest is not canonical");
    }
    validatePackagedManifest(
      manifest,
      expected,
      assemblyIdentity,
      manifestSource,
    );
    return Object.freeze({
      ...manifest,
      canonical_bytes: bytes,
      manifest_sha256: actualDigest,
    });
  } catch (error) {
    if (error?.code === "HOST_PROTOCOL_MISMATCH") {
      throw error;
    }
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest verification failed");
  }
}

async function verifySourceShellManifest({
  document,
  crypto,
  assemblyIdentity,
}) {
  const manifest = Object.freeze({
    product_build: assemblyIdentity.productBuild,
    host_version: assemblyIdentity.hostVersion,
    protocol_version: assemblyIdentity.protocolVersion,
    runtime_script: "source-shell",
  });
  const manifestText = JSON.stringify(manifest);
  const expected = document
    ?.querySelector?.("meta[name='lmdj-host-manifest-sha256']")
    ?.getAttribute?.("content");
  if (typeof expected !== "string" || expected.length !== 64) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest digest is absent");
  }
  const actual = await sha256Hex(new TextEncoder().encode(manifestText), crypto);
  if (actual !== expected) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest digest does not match");
  }
  return manifest;
}

async function verifyDocumentManifest({
  document,
  window,
  crypto,
  assemblyIdentity,
  manifestSource,
}) {
  return metaContent(document, "lmdj-host-manifest-path") ===
    "./host-manifest.json"
    ? verifyPackagedManifest({
      document,
      window,
      crypto,
      assemblyIdentity,
      manifestSource,
    })
    : verifySourceShellManifest({document, crypto, assemblyIdentity});
}

async function loadSourceRuntime({ window }) {
  const runtime = window?.lmdjWebRuntimeHost;
  if (
    typeof runtime?.registerAudioContext !== "function" ||
    typeof runtime?.startAudioWorklet !== "function"
  ) {
    throw typedError("HOST_STATE_INVALID", "Source runtime is not loaded");
  }
  return runtime;
}

function assetForRole(manifest, role) {
  const matches = manifest.assets.filter((asset) => asset.role === role);
  if (matches.length !== 1) {
    throw typedError("HOST_PROTOCOL_MISMATCH", `Manifest ${role} asset is invalid`);
  }
  return matches[0];
}

function sha256Integrity(hexDigest, window) {
  const bytes = new Uint8Array(
    hexDigest.match(/../g).map((value) => Number.parseInt(value, 16)),
  );
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return `sha256-${window.btoa(binary)}`;
}

async function loadPackagedRuntime({ document, window, crypto, manifest }) {
  const runtimeScript = assetForRole(manifest, "runtime_script");
  const runtimeWasm = assetForRole(manifest, "runtime_wasm");
  const runtimeScriptURL = new URL(
    `./${runtimeScript.path}`,
    document.baseURI,
  ).href;
  const wasmURL = new URL(`./${runtimeWasm.path}`, document.baseURI).href;
  const wasmResponse = await window.fetch(wasmURL, {
    cache: "force-cache",
    credentials: "same-origin",
  });
  const wasmBytes = await readBoundedResponse(wasmResponse, runtimeWasm.bytes);
  if (
    wasmBytes.byteLength !== runtimeWasm.bytes ||
    (await sha256Hex(wasmBytes, crypto)) !== runtimeWasm.sha256
  ) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Runtime Wasm asset mismatch");
  }
  window.Module = {
    ...(window.Module ?? {}),
    lmdjHostManifestBytes: manifest.canonical_bytes,
    lmdjHostManifestSha256: manifest.manifest_sha256,
    wasmBinary: wasmBytes,
    locateFile: createPackagedRuntimeLocator({
      baseURI: document.baseURI,
      runtimeScriptURL,
      runtimeWasmURL: wasmURL,
    }),
  };
  await new Promise((resolvePromise, rejectPromise) => {
    const script = document.createElement("script");
    script.src = runtimeScriptURL;
    script.integrity = sha256Integrity(runtimeScript.sha256, window);
    script.crossOrigin = "anonymous";
    script.addEventListener("load", resolvePromise, { once: true });
    script.addEventListener(
      "error",
      () => rejectPromise(
        typedError("HOST_PROTOCOL_MISMATCH", "Runtime script asset mismatch"),
      ),
      { once: true },
    );
    document.head.append(script);
  });
  const runtime = await loadSourceRuntime({ window });
  const initializationDeadline =
    (window.performance ?? globalThis.performance).now() + 30_000;
  while (
    runtime.runtimeInitialized !== true &&
    (window.performance ?? globalThis.performance).now() < initializationDeadline
  ) {
    await new Promise((resolvePromise) => window.setTimeout(resolvePromise, 2));
  }
  if (runtime.runtimeInitialized !== true) {
    throw typedError("HOST_STATE_INVALID", "Runtime initialization timed out");
  }
  if (typeof runtime.transport?.send !== "function") {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Runtime transport is absent");
  }
  return runtime;
}

function createRuntimeSessionController(options = {}) {
  const document = options.document;
  const window = options.window;
  const navigator = options.navigator ?? window?.navigator;
  const crypto = options.crypto ?? window?.crypto;
  const assemblyIdentity = options.assemblyIdentity;
  const manifestSource = options.manifestSource;
  const inputOwnership = options.inputOwnership ?? "session";
  if (inputOwnership !== "session" && inputOwnership !== "host") {
    throw new TypeError("Runtime Session input ownership is invalid");
  }
  const verifyManifest =
    options.verifyManifest ??
    (() => verifyDocumentManifest({
      document,
      window,
      crypto,
      assemblyIdentity,
      manifestSource,
    }));
  const preflight = options.preflight ?? runPreflight;
  const loadRuntime =
    options.loadRuntime ??
    ((manifest) =>
      Array.isArray(manifest?.assets)
        ? loadPackagedRuntime({ document, window, crypto, manifest })
        : loadSourceRuntime({ window }));
  const createAudioContext =
    options.createAudioContext ??
    ((audioOptions) => new window.AudioContext(audioOptions));
  const transport =
    options.transport ??
    Object.freeze({
      send(...arguments_) {
        if (typeof runtime?.transport?.send !== "function") {
          return Promise.reject(
            typedError("HOST_STATE_INVALID", "Runtime transport is unavailable"),
          );
        }
        return runtime.transport.send(...arguments_);
      },
      subscribe(listener) {
        if (typeof runtime?.transport?.subscribe !== "function") {
          throw typedError("HOST_STATE_INVALID", "Runtime transport is unavailable");
        }
        return runtime.transport.subscribe(listener);
      },
      subscribeFailure(listener) {
        if (typeof runtime?.transport?.subscribeFailure !== "function") {
          return () => {};
        }
        return runtime.transport.subscribeFailure(listener);
      },
    });
  const runtimeTerminator =
    options.runtimeTerminator ??
    ((resources) => defaultRuntimeTerminator({ ...resources, window }));
  const timers = options.timers ?? {
    setTimeout: (callback, milliseconds) =>
      (typeof window?.setTimeout === "function" ? window : globalThis)
        .setTimeout(callback, milliseconds),
    clearTimeout: (handle) =>
      (typeof window?.clearTimeout === "function" ? window : globalThis)
        .clearTimeout(handle),
  };
  const monotonicNow =
    options.now ?? (() => (window?.performance ?? globalThis.performance).now());

  requireFunction(verifyManifest, "Manifest verifier");
  requireFunction(preflight, "Runtime preflight");
  requireFunction(loadRuntime, "Runtime loader");
  requireFunction(createAudioContext, "AudioContext factory");
  requireFunction(runtimeTerminator, "Runtime terminator");
  requireFunction(transport?.send, "Transport send");
  requireFunction(crypto?.randomUUID, "Request UUID source");
  if (
    assemblyIdentity === null ||
    typeof assemblyIdentity !== "object" ||
    typeof assemblyIdentity.distributionContract !== "string" ||
    typeof assemblyIdentity.hostId !== "string" ||
    typeof assemblyIdentity.hostVersion !== "string" ||
    typeof assemblyIdentity.platformVersion !== "string" ||
    typeof assemblyIdentity.productBuild !== "string" ||
    assemblyIdentity.protocolVersion !== 1
  ) {
    throw new TypeError("Runtime Session assembly identity is invalid");
  }

  let manifest = Object.freeze({
    product_build: assemblyIdentity.productBuild,
    host_version: assemblyIdentity.hostVersion,
    protocol_version: assemblyIdentity.protocolVersion,
  });
  let runtime = null;
  let audioContext = null;
  let contextHandle = null;
  let started = false;
  let closing = false;
  let terminalCleanupStarted = false;
  let terminalCleanupPromise = null;
  let unsubscribeTransport = null;
  let unsubscribeTransportFailure = null;
  let expectedContextSuspend = false;
  let visibilityHidden = false;
  let pageHidden = false;
  const activeAdverseConditions = new Set();
  let lastContextState = null;
  let recoveryEpoch = null;
  let nextRecoveryEpoch = 1;
  let activationReservation = null;
  let probeReservation = null;
  let lastErrorCode = null;
  let lastErrorDetails = Object.freeze({});
  let controlGeneration = null;
  let acknowledgedGeneration = null;
  let triggerAdmittedCount = 0;
  let triggerOutcomeCount = 0;
  let triggerRejectedCount = 0;
  let triggerTail = Promise.resolve();
  let importTail = Promise.resolve();
  let capabilitySnapshot = Object.freeze({
    secureContext: false,
    crossOriginIsolated: false,
    sharedArrayBuffer: false,
    webAssembly: false,
    audioWorklet: false,
    opfs: false,
    opfsSyncAccessHandle: false,
    opfsWritableReplace: false,
    webMidi: typeof navigator?.requestMIDIAccess === "function",
  });
  const admittedSequences = new Map();
  const listenerDisposers = [];
  const hostStateListeners = new Set();
  const runtimeOutcomeListeners = new Set();
  const diagnosticsListeners = new Set();

  const padBindings = [...(options.padBindings ?? [])];

  function renderPressed(pointerSlots = null) {
    options.onPressedChange?.(pointerSlots);
    renderDiagnostics();
  }

  let pointerAdapter;
  let keyboardAdapter;
  let midiAdapter;

  function pressedCount() {
    return (
      (pointerAdapter?.diagnostics().pressed_count ?? 0) +
      (keyboardAdapter?.diagnostics().pressed_count ?? 0) +
      (midiAdapter?.diagnostics().pressed_note_count ?? 0)
    );
  }

  function diagnostics() {
    const midi = midiAdapter?.diagnostics() ?? {
      permission: "prompt",
      connected_input_count: 0,
    };
    return Object.freeze({
      state: machine.state,
      error_code: lastErrorCode,
      error_details: lastErrorDetails,
      product_build: manifest.product_build,
      host_id: assemblyIdentity.hostId,
      host_version: manifest.host_version,
      platform_version: assemblyIdentity.platformVersion,
      protocol_version: manifest.protocol_version,
      capabilities: capabilitySnapshot,
      control_generation: controlGeneration,
      acknowledged_generation: acknowledgedGeneration,
      recovery_probe_ready:
        machine.state === "recovering" &&
        recoveryEpoch?.probeWindow === true &&
        probeReservation === null,
      trigger_admitted_count: triggerAdmittedCount,
      trigger_outcome_count: triggerOutcomeCount,
      trigger_rejected_count: triggerRejectedCount,
      midi_permission: midi.permission,
      connected_input_count: midi.connected_input_count,
      pressed_count: pressedCount(),
    });
  }

  function renderDiagnostics() {
    const value = diagnostics();
    options.onDiagnostics?.(value);
    for (const listener of [...diagnosticsListeners]) {
      listener(value);
    }
  }

  function clearPressed() {
    pointerAdapter?.clearPressed();
    keyboardAdapter?.clearPressed();
    midiAdapter?.clearPressed();
    options.onPressedChange?.([]);
    renderDiagnostics();
  }

  function cleanupForTransition(targetState) {
    clearPressed();
    if (
      targetState === "restart-required" ||
      targetState === "failed" ||
      targetState === "closed"
    ) {
      terminalCleanup();
    }
  }

  const machine = createHostStateMachine({
    notify(event, payload) {
      renderDiagnostics();
      if (event === "host.state_changed") {
        const value = Object.freeze({
          state: payload.state,
          errorCode: lastErrorCode,
          errorDetails: lastErrorDetails,
        });
        for (const listener of hostStateListeners) {
          listener(value);
        }
      }
    },
    cleanup: cleanupForTransition,
  });

  function terminalCleanup() {
    if (terminalCleanupStarted) {
      return terminalCleanupPromise;
    }
    terminalCleanupStarted = true;
    if (probeReservation?.timeout != null) {
      timers.clearTimeout(probeReservation.timeout);
    }
    probeReservation = null;
    clearPressed();
    unsubscribeTransport?.();
    unsubscribeTransport = null;
    unsubscribeTransportFailure?.();
    unsubscribeTransportFailure = null;
    for (const dispose of listenerDisposers.splice(0)) {
      dispose();
    }
    midiAdapter?.dispose();
    terminalCleanupPromise = Promise.resolve()
      .then(() => {
        diagnosticsListeners.clear();
        return runtimeTerminator({ runtime, audioContext });
      })
      .catch(() => {});
    return terminalCleanupPromise;
  }

  function fail(codeOrError) {
    if (["restart-required", "failed", "closed"].includes(machine.state)) {
      return false;
    }
    lastErrorCode =
      typeof codeOrError === "string"
        ? validatedErrorCode(codeOrError)
        : errorCode(codeOrError);
    lastErrorDetails =
      typeof codeOrError === "string"
        ? Object.freeze({})
        : safeErrorDetails(codeOrError);
    closing = true;
    machine.transition(
      ["HOST_RESTART_REQUIRED", "HOST_TIMEOUT"].includes(lastErrorCode)
        ? "restart-required"
        : "failed",
      {reason: lastErrorCode},
    );
    renderDiagnostics();
    return true;
  }

  function listen(target, type, listener) {
    if (typeof target?.addEventListener !== "function") {
      return;
    }
    target.addEventListener(type, listener);
    listenerDisposers.push(() => target.removeEventListener(type, listener));
  }

  async function boundedRequest(operation, payload, requestOptions = {}) {
    const request = createRequestEnvelope({ operation, payload, crypto });
    const transportOptions = {
      deadlineMs: requestOptions.deadlineMs ?? deadlineForOperation(operation),
    };
    if (requestOptions.sidecar !== undefined) {
      transportOptions.sidecar = requestOptions.sidecar;
    }
    const response = validateResponseEnvelope(
      await transport.send(request, transportOptions),
    );
    if (response.request_id !== request.request_id) {
      throw typedError(
        "HOST_PROTOCOL_MISMATCH", "Response request_id mismatch",
      );
    }
    if (!response.ok) {
      throw typedError(response.error.code, "Host request was rejected");
    }
    return response.result;
  }

  function retainAdmission(sequence, epochId, isProbe) {
    if (!isPositiveInteger(sequence) || admittedSequences.has(sequence)) {
      throw typedError("HOST_PROTOCOL_MISMATCH", "Trigger sequence is invalid");
    }
    if (admittedSequences.size >= TRIGGER_LEDGER_LIMIT) {
      const completed = [...admittedSequences].find(([, entry]) => entry.outcome !== null);
      if (!completed) {
        throw typedError("HOST_STATE_INVALID", "Trigger ledger is full");
      }
      admittedSequences.delete(completed[0]);
    }
    admittedSequences.set(sequence, {
      epochId,
      isProbe,
      outcome: null,
    });
    triggerAdmittedCount += 1;
  }

  function rejectTrigger() {
    triggerRejectedCount += 1;
    renderDiagnostics();
    return false;
  }

  async function dispatchTrigger(flatSlot, velocity, source) {
    if (
      !Number.isInteger(flatSlot) ||
      flatSlot < 0 ||
      flatSlot > 63 ||
      !Number.isInteger(velocity) ||
      velocity < 1 ||
      velocity > 127 ||
      !TRIGGER_SOURCES.has(source) ||
      closing
    ) {
      return rejectTrigger();
    }

    const ordinary = machine.state === "running";
    const recoveryProbe =
      machine.state === "recovering" &&
      recoveryEpoch !== null &&
      recoveryEpoch.probeWindow === true &&
      probeReservation === null;
    if (!ordinary && !recoveryProbe) {
      return rejectTrigger();
    }

    const admissionEpoch = recoveryProbe ? recoveryEpoch.id : 0;
    if (recoveryProbe) {
      recoveryEpoch.probeWindow = false;
      probeReservation = {
        epochId: admissionEpoch,
        sequence: null,
        timeout: null,
      };
    }

    try {
      const result = await boundedRequest("trigger", {
        slot: flatSlot,
        velocity,
      });
      const responseIsCurrent = recoveryProbe
        ? (
            !closing &&
            machine.state === "recovering" &&
            recoveryEpoch?.id === admissionEpoch &&
            probeReservation?.epochId === admissionEpoch
          )
        : !closing && machine.state === "running";
      if (!responseIsCurrent) {
        return false;
      }
      retainAdmission(result?.sequence, admissionEpoch, recoveryProbe);
      if (recoveryProbe && probeReservation?.epochId === admissionEpoch) {
        probeReservation.sequence = result.sequence;
        probeReservation.timeout = timers.setTimeout(() => {
          if (
            probeReservation?.epochId === admissionEpoch &&
            probeReservation.sequence === result.sequence
          ) {
            fail("HOST_TIMEOUT");
          }
        }, RECOVERY_OUTCOME_DEADLINE_MS);
      }
      renderDiagnostics();
      return Object.freeze({
        sequence: result.sequence,
        slot: flatSlot,
        velocity,
        source,
      });
    } catch (error) {
      fail(error);
      return false;
    }
  }

  function trigger(flatSlot, velocity, source = "pointer") {
    const pending = triggerTail.then(() =>
      dispatchTrigger(flatSlot, velocity, source));
    triggerTail = pending.then(
      () => undefined,
      () => undefined,
    );
    return pending;
  }

  function completeRecovery(status) {
    controlGeneration = status?.control_generation ?? null;
    acknowledgedGeneration = status?.acknowledged_generation ?? null;
    if (
      machine.state === "recovering" &&
      recoveryEpoch !== null &&
      audioContext?.state === "running" &&
      generationsMatch(status) &&
      probeReservation === null
    ) {
      recoveryEpoch.contextUsable = true;
      recoveryEpoch.probeWindow = true;
    }
    renderDiagnostics();
  }

  function observeRuntimeStatus(status) {
    if (status === null || typeof status !== "object") {
      fail("HOST_PROTOCOL_MISMATCH");
      return false;
    }
    completeRecovery(status);
    return generationsMatch(status);
  }

  async function activateRuntimeForRecovery(epoch) {
    if (
      recoveryEpoch !== epoch ||
      epoch.activationStarted ||
      machine.state !== "recovering" ||
      audioContext?.state !== "running"
    ) {
      return;
    }
    epoch.activationStarted = true;
    epoch.contextUsable = true;
    try {
      await boundedRequest("audio.activate", {});
      if (recoveryEpoch !== epoch || machine.state !== "recovering") {
        return;
      }
      const status = await boundedRequest("host.status", {});
      if (recoveryEpoch === epoch) {
        completeRecovery(status);
      }
    } catch (error) {
      fail(error);
    }
  }

  function invalidateProbe() {
    if (probeReservation?.timeout != null) {
      timers.clearTimeout(probeReservation.timeout);
    }
    probeReservation = null;
  }

  function beginInterruption(reason) {
    if (closing || machine.state === "failed" || machine.state === "closed") {
      return false;
    }
    clearPressed();

    const isNewRunningEdge = machine.state === "running";
    const isNewRecoveryEdge =
      machine.state === "recovering" && recoveryEpoch?.contextUsable === true;
    if (!isNewRunningEdge && !isNewRecoveryEdge) {
      return false;
    }

    invalidateProbe();
    machine.transition("interrupted", { reason });
    const epoch = {
      id: nextRecoveryEpoch,
      contextUsable: audioContext?.state === "running",
      suspendComplete: false,
      activationStarted: false,
      probeWindow: false,
    };
    nextRecoveryEpoch += 1;
    recoveryEpoch = epoch;

    boundedRequest("audio.suspend", {}).then(
      () => {
        if (recoveryEpoch !== epoch || closing) {
          return;
        }
        epoch.suspendComplete = true;
        if (machine.state === "interrupted") {
          machine.transition("recovering", { reason: "recovery_started" });
        }
        if (audioContext?.state === "running") {
          activateRuntimeForRecovery(epoch);
        } else if (machine.state === "recovering") {
          machine.transition("audio-suspended", {
            reason: "recovery_gesture_required",
          });
        }
      },
      (error) => fail(error),
    );
    return true;
  }

  function markAdverseCondition(condition) {
    const hadActiveCondition =
      condition === "audio_statechange"
        ? activeAdverseConditions.has(condition)
        : activeAdverseConditions.has("visibilitychange") ||
          activeAdverseConditions.has("pagehide");
    activeAdverseConditions.add(condition);
    return !hadActiveCondition;
  }

  function observeContextState() {
    if (!audioContext || closing) {
      return;
    }
    const previousState = lastContextState;
    lastContextState = audioContext.state;
    if (audioContext.state === "running") {
      activeAdverseConditions.delete("audio_statechange");
      if (recoveryEpoch !== null) {
        recoveryEpoch.contextUsable = true;
        if (recoveryEpoch.suspendComplete && machine.state === "recovering") {
          activateRuntimeForRecovery(recoveryEpoch);
        }
      }
      return;
    }
    if (expectedContextSuspend) {
      expectedContextSuspend = false;
      activeAdverseConditions.delete("audio_statechange");
      return;
    }
    if (previousState === audioContext.state) {
      clearPressed();
      return;
    }
    if (markAdverseCondition("audio_statechange")) {
      beginInterruption("audio_statechange");
    } else {
      clearPressed();
    }
  }

  function observeVisibility(hidden) {
    if (hidden === true) {
      if (visibilityHidden) {
        clearPressed();
        return false;
      }
      visibilityHidden = true;
      if (markAdverseCondition("visibilitychange")) {
        beginInterruption("visibilitychange");
      } else {
        clearPressed();
      }
    } else {
      visibilityHidden = false;
      activeAdverseConditions.delete("visibilitychange");
      renderDiagnostics();
    }
  }

  function observePageShow() {
    pageHidden = false;
    activeAdverseConditions.delete("pagehide");
    if (recoveryEpoch?.suspendComplete && machine.state === "recovering") {
      if (audioContext?.state === "running") {
        activateRuntimeForRecovery(recoveryEpoch);
      }
    }
  }

  function observePageHide(event) {
    if (event?.persisted === true) {
      if (pageHidden) {
        clearPressed();
        return Promise.resolve(false);
      }
      pageHidden = true;
      if (markAdverseCondition("pagehide")) {
        beginInterruption("pagehide");
      } else {
        clearPressed();
      }
      return Promise.resolve(false);
    }
    return close();
  }

  function validateOutcome(event) {
    return (
      isPositiveInteger(event?.sequence) &&
      (event.outcome === "voice_started" || event.outcome === "voice_capacity") &&
      Number.isInteger(event.runtime_frame) &&
      event.runtime_frame >= 0
    );
  }

  function observeOutcomes(events) {
    if (!Array.isArray(events) || events.length === 0) {
      fail("HOST_PROTOCOL_MISMATCH");
      return;
    }
    for (const event of events) {
      if (!validateOutcome(event)) {
        fail("HOST_PROTOCOL_MISMATCH");
        return;
      }
      const admission = admittedSequences.get(event.sequence);
      if (!admission || admission.outcome !== null) {
        fail("HOST_PROTOCOL_MISMATCH");
        return;
      }
      admission.outcome = event.outcome;
      triggerOutcomeCount += 1;
      const publicOutcome = Object.freeze({
        sequence: event.sequence,
        outcome: event.outcome,
        runtimeFrame: event.runtime_frame,
      });
      for (const listener of runtimeOutcomeListeners) {
        listener(publicOutcome);
      }

      const isCurrentProbe =
        admission.isProbe &&
        recoveryEpoch !== null &&
        admission.epochId === recoveryEpoch.id &&
        probeReservation?.epochId === recoveryEpoch.id &&
        probeReservation.sequence === event.sequence;
      if (!isCurrentProbe) {
        continue;
      }
      timers.clearTimeout(probeReservation.timeout);
      probeReservation = null;
      if (event.outcome !== "voice_started") {
        fail("HOST_STATE_INVALID");
        return;
      }
      recoveryEpoch = null;
      machine.transition("running", { reason: "recovery_probe_completed" });
    }
    renderDiagnostics();
  }

  function observeNotification(rawNotification) {
    let notification;
    try {
      notification = validateNotificationEnvelope(rawNotification);
    } catch (error) {
      fail(error);
      return;
    }
    if (notification.event === "runtime.trigger_outcomes") {
      observeOutcomes(notification.payload.events);
      return;
    }
    if (notification.event === "runtime.warning") {
      if (
        notification.payload?.fatal === true &&
        ALLOWED_TYPED_ERROR_CODES.has(notification.payload.code)
      ) {
        fail(notification.payload.code);
      } else {
        renderDiagnostics();
      }
      return;
    }
    if (notification.event === "snapshot.published") {
      controlGeneration = notification.payload?.generation ?? controlGeneration;
    }
    renderDiagnostics();
  }

  function observeRuntime(observation) {
    if (
      observation?.fatal === true &&
      typeof observation.code === "string" &&
      observation.code.length > 0
    ) {
      fail(observation.code);
      return true;
    }
    return false;
  }

  function activationIsCurrent(reservation, expectedState) {
    return (
      activationReservation === reservation &&
      !closing &&
      !visibilityHidden &&
      !pageHidden &&
      recoveryEpoch === reservation.recoveryEpoch &&
      machine.state === expectedState
    );
  }

  async function activateAudio(token) {
    if (
      createUserGestureToken.consume(token) !== true ||
      closing ||
      machine.state !== "audio-suspended" ||
      activationReservation !== null ||
      visibilityHidden ||
      pageHidden
    ) {
      return false;
    }
    const reservation = Object.freeze({ recoveryEpoch });
    activationReservation = reservation;
    try {
      if (audioContext === null) {
        audioContext = createAudioContext({ sampleRate: 48_000 });
        lastContextState = audioContext.state;
        listen(audioContext, "statechange", observeContextState);
        contextHandle = runtime.registerAudioContext(audioContext);
        const workletResult = await runtime.startAudioWorklet(contextHandle);
        if (workletResult?.ok === false) {
          throw typedError("HOST_STATE_INVALID", "AudioWorklet start failed");
        }
        if (!activationIsCurrent(reservation, "audio-suspended")) {
          return false;
        }
      }
      await audioContext.resume();
      if (!activationIsCurrent(reservation, "audio-suspended")) {
        return false;
      }
      if (recoveryEpoch !== null) {
        machine.transition("recovering", {
          reason: "recovery_activation",
          recoveryEpoch: true,
        });
        recoveryEpoch.contextUsable = true;
        recoveryEpoch.suspendComplete = true;
        await activateRuntimeForRecovery(recoveryEpoch);
        if (
          closing ||
          visibilityHidden ||
          pageHidden ||
          recoveryEpoch !== reservation.recoveryEpoch
        ) {
          return false;
        }
        return machine.state === "recovering";
      }
      await boundedRequest("audio.activate", {});
      if (!activationIsCurrent(reservation, "audio-suspended")) {
        return false;
      }
      const status = await boundedRequest("host.status", {});
      if (!activationIsCurrent(reservation, "audio-suspended")) {
        return false;
      }
      controlGeneration = status?.control_generation ?? null;
      acknowledgedGeneration = status?.acknowledged_generation ?? null;
      if (!generationsMatch(status)) {
        throw typedError(
          "HOST_PROTOCOL_MISMATCH",
          "Initial Runtime generation is not acknowledged",
        );
      }
      machine.transition("running", { reason: "audio_activation" });
      return true;
    } catch (error) {
      if (machine.state !== "failed" && machine.state !== "closed") {
        fail(error);
      }
      return false;
    } finally {
      if (activationReservation === reservation) {
        activationReservation = null;
      }
    }
  }

  async function suspendAudio() {
    if (closing || machine.state !== "running") {
      return false;
    }
    machine.handleOperation("audio.suspend");
    clearPressed();
    expectedContextSuspend = true;
    try {
      await Promise.all([
        boundedRequest("audio.suspend", {}),
        audioContext?.suspend?.() ?? Promise.resolve(),
      ]);
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  }

  async function enableMidi() {
    if (inputOwnership !== "session" || midiAdapter === undefined) {
      return false;
    }
    try {
      await midiAdapter.requestPermission();
      renderDiagnostics();
      return true;
    } catch {
      renderDiagnostics();
      return false;
    }
  }

  function subscribeHostState(listener) {
    requireFunction(listener, "Host state listener");
    hostStateListeners.add(listener);
    return () => hostStateListeners.delete(listener);
  }

  function subscribeDiagnostics(listener) {
    requireFunction(listener, "Runtime diagnostics listener");
    diagnosticsListeners.add(listener);
    return () => diagnosticsListeners.delete(listener);
  }

  function subscribeRuntimeOutcome(listener) {
    requireFunction(listener, "Runtime outcome listener");
    runtimeOutcomeListeners.add(listener);
    return () => runtimeOutcomeListeners.delete(listener);
  }

  async function openProject(projectId, patternId, requestOptions = {}) {
    return boundedRequest("project.open", {
      project_id: projectId,
      pattern_id: patternId,
    }, requestOptions);
  }

  async function inspectProject() {
    return boundedRequest("project.inspect", {});
  }

  async function reloadSnapshot(patternId) {
    return boundedRequest("snapshot.reload", {pattern_id: patternId});
  }

  async function listLocalProjects() {
    if (closing || !started) {
      throw typedError("HOST_STATE_INVALID", "Project discovery is unavailable");
    }
    const result = await boundedRequest("project.list", {});
    if (!exactKeys(result, ["projects"]) || !Array.isArray(result.projects)) {
      throw typedError(
        "HOST_PROTOCOL_MISMATCH",
        "Local Project inventory is invalid",
      );
    }
    return Object.freeze(result.projects.map((item) =>
      normalizeLocalProjectSummary(item)));
  }

  function importProject(file, importOptions = {}) {
    const pending = importTail.then(async () => {
      if (closing || !started) {
        throw typedError("HOST_STATE_INVALID", "Project import is unavailable");
      }
      return importProjectBundle(file, {
        crypto,
        signal: importOptions.signal,
        onProgress: importOptions.onProgress,
        send: async (operation, payload, sidecar) => {
          try {
            return await boundedRequest(
              operation,
              payload,
              sidecar === undefined ? {} : {sidecar},
            );
          } catch (error) {
            const code = errorCode(error);
            if ([
              "HOST_RESTART_REQUIRED",
              "HOST_TIMEOUT",
              "HOST_PROTOCOL_MISMATCH",
            ].includes(code)) {
              fail(code);
            }
            throw error;
          }
        },
      });
    });
    importTail = pending.then(
      () => undefined,
      () => undefined,
    );
    return pending;
  }

  async function close() {
    if (closing || machine.state === "closed" || machine.state === "failed") {
      return false;
    }
    closing = true;
    clearPressed();
    invalidateProbe();
    try {
      await boundedRequest("host.close", {});
      machine.transition("closed", { reason: "pagehide" });
      await terminalCleanup();
      return true;
    } catch (error) {
      closing = false;
      fail(error);
      return false;
    }
  }

  function wireInputs() {
    if (inputOwnership !== "session") {
      return;
    }
    pointerAdapter = createPointerAdapter({
      trigger,
      velocity: options.pointerVelocity ?? 100,
      now: monotonicNow,
      onPressedChange: renderPressed,
    });
    keyboardAdapter = createKeyboardAdapter({
      trigger,
      mapping: options.keyboardMapping ?? DEFAULT_KEYBOARD_MAPPING,
      velocity: options.keyboardVelocity ?? 100,
      onPressedChange: renderDiagnostics,
    });
    midiAdapter = createMidiAdapter({
      trigger,
      requestMIDIAccess: (...args) => navigator.requestMIDIAccess(...args),
      notify: (event, payload) => {
        if (event === "runtime.warning" && payload?.fatal === true) {
          fail(payload.code);
        }
        renderDiagnostics();
      },
      noteStart: options.midiNoteStart ?? 36,
      slotStart: options.midiSlotStart ?? 0,
      slotCount: options.midiSlotCount ?? 64,
      onPressedChange: renderDiagnostics,
    });

    for (const binding of padBindings) {
      const pad = binding.element;
      const flatSlot = flattenPadSlot(binding.slot);
      listen(pad, "pointerdown", (event) =>
        pointerAdapter.pointerDown(event, flatSlot));
      listen(pad, "mousedown", (event) =>
        pointerAdapter.mouseDown(event, flatSlot));
      listen(pad, "pointerup", (event) => {
        if (!pointerAdapter.releasePointer(event)) {
          pointerAdapter.pointerUp(event, flatSlot);
        }
      });
      listen(pad, "mouseup", (event) => {
        if (!pointerAdapter.releaseMouse(event)) {
          pointerAdapter.pointerUp(event, flatSlot);
        }
      });
      listen(pad, "pointercancel", (event) => {
        pointerAdapter.pointerCancel(event);
        pointerAdapter.pointerUp(event, flatSlot);
      });
    }
    listen(window, "pointerup", (event) => pointerAdapter.releasePointer(event));
    listen(window, "pointercancel", (event) => pointerAdapter.pointerCancel(event));
    listen(window, "mouseup", (event) => pointerAdapter.releaseMouse(event));
    listen(window, "blur", () => pointerAdapter.clearPressed());
    listen(window, "keydown", (event) => keyboardAdapter.keyDown(event));
    listen(window, "keyup", (event) => keyboardAdapter.keyUp(event));
  }

  function wireLifecycle() {
    listen(document, "visibilitychange", () =>
      observeVisibility(document.visibilityState === "hidden"));
    listen(window, "pagehide", (event) => observePageHide(event));
    listen(window, "pageshow", observePageShow);
    for (const worker of runtime?.workers ?? []) {
      listen(worker, "error", () => fail("HOST_STATE_INVALID"));
      listen(worker, "messageerror", () => fail("HOST_PROTOCOL_MISMATCH"));
    }
    if (runtime?.worklet) {
      listen(runtime.worklet, "processorerror", () =>
        fail("HOST_STATE_INVALID"));
    }
    if (typeof transport.subscribe === "function") {
      unsubscribeTransport = transport.subscribe(observeNotification);
    }
    if (typeof transport.subscribeFailure === "function") {
      unsubscribeTransportFailure = transport.subscribeFailure(fail);
    }
  }

  async function start() {
    if (started) {
      return false;
    }
    started = true;
    try {
      machine.transition("preflight", { reason: "bootstrap" });
      manifest = Object.freeze(await verifyManifest());
      if (
        manifest.product_build !== assemblyIdentity.productBuild ||
        manifest.host_version !== assemblyIdentity.hostVersion ||
        manifest.protocol_version !== assemblyIdentity.protocolVersion ||
        (manifest.host_id !== undefined &&
          manifest.host_id !== assemblyIdentity.hostId) ||
        (manifest.platform_version !== undefined &&
          manifest.platform_version !== assemblyIdentity.platformVersion)
      ) {
        throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest identity is invalid");
      }
      const capabilities =
        options.capabilities ??
        (preflight === runPreflight ? await defaultCapabilities(window) : {});
      const resolvedCapabilities = {};
      for (const name of PREFLIGHT_CAPABILITIES) {
        try {
          const value = capabilities[name];
          resolvedCapabilities[name] =
            (typeof value === "function" ? await value() : await value) === true;
        } catch {
          resolvedCapabilities[name] = false;
        }
      }
      capabilitySnapshot = Object.freeze({
        ...resolvedCapabilities,
        webMidi: typeof navigator?.requestMIDIAccess === "function",
      });
      await preflight(resolvedCapabilities);
      runtime = await loadRuntime(manifest);
      machine.transition("storage-ready", { reason: "runtime_loaded" });
      machine.transition("core-ready", { reason: "runtime_ready" });
      machine.transition("audio-suspended", { reason: "activation_required" });
      wireInputs();
      wireLifecycle();
      renderDiagnostics();
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  }

  const session = Object.freeze({
    start,
    trigger,
    listLocalProjects,
    importProject,
    openProject,
    inspectProject,
    reloadSnapshot,
    activateAudio,
    suspendAudio,
    requestMidi: enableMidi,
    close,
    subscribeDiagnostics,
    subscribeHostState,
    subscribeRuntimeOutcome,
    diagnostics,
  });
  registerDiagnosticTransport(session, async (...arguments_) => {
    try {
      return await boundedRequest(...arguments_);
    } catch (error) {
      const code = errorCode(error);
      if (
        code === "HOST_RESTART_REQUIRED" ||
        code === "HOST_TIMEOUT" ||
        code === "HOST_PROTOCOL_MISMATCH"
      ) {
        fail(code);
      }
      throw error;
    }
  });
  return session;
}

export function createRuntimeSession({
  document,
  window,
  navigator,
  crypto,
  manifestSource,
  assemblyIdentity,
  inputConfiguration = {},
  inputOwnership = "session",
  seams = {},
}) {
  return createRuntimeSessionController({
    document,
    window,
    navigator,
    crypto,
    manifestSource,
    assemblyIdentity,
    inputOwnership,
    ...inputConfiguration,
    ...seams,
  });
}
