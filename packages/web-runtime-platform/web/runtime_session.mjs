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
  MAX_ASSET_BYTES,
  createRequestEnvelope,
  deadlineForOperation,
  validateNotificationEnvelope,
  validateResponseEnvelope,
} from "./protocol.mjs";
import {canonicalJson, exactKeys, sha256Hex} from "./integrity.mjs";
import { createHostStateMachine } from "./state_machine.mjs";

const HOST_MANIFEST_MAXIMUM_BYTES = 65_536;
const CONTROL_WORKER_CAPABILITY_PROBE_TIMEOUT_MS = 15_000;
const TRIGGER_LEDGER_LIMIT = 4_096;
const RECOVERY_OUTCOME_DEADLINE_MS = 1_000;
const SAMPLE_PREVIEW_SLOT_LIMIT = 64;
const VOICE_LISTENER_LIMIT = 64;
const VOICE_NOTIFICATION_EVENT_LIMIT = 4_096;
const SAFETY_QUERY_RETRY_LIMIT = 4;
const SAFETY_INTERRUPTIBLE_HOST_OPERATIONS = new Set([
  "project.inspect",
  "project.list",
  "sample.inspect",
  "sample.quota",
  "sample.waveform",
]);
const TRIGGER_SOURCES = new Set(["pointer", "keyboard", "midi"]);
const SAFE_ERROR_DETAIL_NAMES = new Set([
  "mutation_outcome",
  "resource",
  "storage_condition",
  "terminal_state",
]);
const VOICE_STATES = new Set(["started", "stopped", "completed"]);
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ALLOWED_TYPED_ERROR_CODES = new Set([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "REVISION_CONFLICT",
  "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO",
  "MISSING_ASSET",
  "INVALID_PROJECT",
  "COOK_FAILED",
  "BANK_QUOTA_EXHAUSTED",
  "PROJECT_QUOTA_EXHAUSTED",
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

function typedError(code, message = code, details = {}) {
  return new HostProtocolError(code, message, details);
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
  return Number.isSafeInteger(value) && value > 0;
}

function generationsMatch(status) {
  return (
    isPositiveInteger(status?.control_generation) &&
    isPositiveInteger(status?.acknowledged_generation) &&
    status.control_generation === status.acknowledged_generation
  );
}

async function probeControlWorkerCapabilities(scope, timeoutMs) {
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
    return await new Promise((resolvePromise, rejectPromise) => {
      const timeout = scope.setTimeout(() => {
        rejectPromise(typedError(
          "HOST_TIMEOUT",
          "Control Worker capability probe timed out",
        ));
      }, timeoutMs);
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

async function defaultCapabilities(scope, timeoutMs) {
  const controlWorker = await probeControlWorkerCapabilities(scope, timeoutMs);
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

function protocolMismatch(message) {
  return typedError("HOST_PROTOCOL_MISMATCH", message);
}

function isUnsignedInteger(value, maximum = Number.MAX_SAFE_INTEGER) {
  return Number.isSafeInteger(value) && value >= 0 && value <= maximum;
}

function flatSlotAddress(flatSlot) {
  if (!Number.isInteger(flatSlot) || flatSlot < 0 || flatSlot >= 64) {
    throw new RangeError("Sample slot must be an integer in 0..63");
  }
  return Object.freeze({
    bank: Math.floor(flatSlot / 16),
    pad: flatSlot % 16,
  });
}

function flatSlotFromAddress(value) {
  if (
    !exactKeys(value, ["bank", "pad"]) ||
    !isUnsignedInteger(value.bank, 3) ||
    !isUnsignedInteger(value.pad, 15)
  ) {
    throw protocolMismatch("Sample slot result is invalid");
  }
  return value.bank * 16 + value.pad;
}

function wirePlayback(value) {
  if (
    !exactKeys(value, [
      "trimStartFrame",
      "trimEndFrame",
      "triggerMode",
      "gainMillidb",
      "muted",
    ]) ||
    !isUnsignedInteger(value.trimStartFrame) ||
    !(
      value.trimEndFrame === null ||
      (isUnsignedInteger(value.trimEndFrame) &&
        value.trimEndFrame > value.trimStartFrame)
    ) ||
    !["one_shot", "gate", "loop_gate", "loop_toggle"].includes(
      value.triggerMode,
    ) ||
    !Number.isSafeInteger(value.gainMillidb) ||
    value.gainMillidb < -60_000 ||
    value.gainMillidb > 6_000 ||
    typeof value.muted !== "boolean"
  ) {
    throw new TypeError("Sample playback is invalid");
  }
  return Object.freeze({
    trim_start_frame: value.trimStartFrame,
    trim_end_frame: value.trimEndFrame,
    trigger_mode: value.triggerMode,
    gain_millidb: value.gainMillidb,
    muted: value.muted,
  });
}

function normalizePlayback(value) {
  if (!exactKeys(value, [
    "trim_start_frame",
    "trim_end_frame",
    "trigger_mode",
    "gain_millidb",
    "muted",
  ])) {
    throw protocolMismatch("Sample playback result is invalid");
  }
  let validated;
  try {
    validated = wirePlayback({
      trimStartFrame: value.trim_start_frame,
      trimEndFrame: value.trim_end_frame,
      triggerMode: value.trigger_mode,
      gainMillidb: value.gain_millidb,
      muted: value.muted,
    });
  } catch {
    throw protocolMismatch("Sample playback result is invalid");
  }
  return Object.freeze({
    trimStartFrame: validated.trim_start_frame,
    trimEndFrame: validated.trim_end_frame,
    triggerMode: validated.trigger_mode,
    gainMillidb: validated.gain_millidb,
    muted: validated.muted,
  });
}

function normalizeMetadata(value) {
  if (
    !exactKeys(value, ["sample_rate", "channels", "source_frames"]) ||
    ![44_100, 48_000].includes(value.sample_rate) ||
    ![1, 2].includes(value.channels) ||
    !isUnsignedInteger(value.source_frames) ||
    value.source_frames === 0
  ) {
    throw protocolMismatch("Sample metadata result is invalid");
  }
  return Object.freeze({
    sampleRate: value.sample_rate,
    channels: value.channels,
    sourceFrames: value.source_frames,
  });
}

function canonicalWaveformFramesPerBucket(sourceFrames) {
  return Math.ceil(sourceFrames / Math.min(sourceFrames, 512));
}

function normalizeWaveformCacheIdentity(value, metadata) {
  if (typeof value !== "string" || value.length === 0 || value.length > 512) {
    throw protocolMismatch("Sample waveform cache identity is invalid");
  }
  const match = /^([0-9a-f]{64})\/1\/max-abs-mirror\/([1-9][0-9]*)$/.exec(
    value,
  );
  const framesPerBucket = match === null ? NaN : Number(match[2]);
  if (
    match === null ||
    !isUnsignedInteger(framesPerBucket) ||
    framesPerBucket !== canonicalWaveformFramesPerBucket(metadata.sourceFrames)
  ) {
    throw protocolMismatch("Sample waveform cache identity is invalid");
  }
  return value;
}

function normalizeSnapshotError(value) {
  if (
    !exactKeys(value, ["code", "message", "details"]) ||
    !ALLOWED_TYPED_ERROR_CODES.has(value.code) ||
    typeof value.message !== "string" ||
    value.message.length === 0 ||
    value.message.length > 512 ||
    value.details === null ||
    typeof value.details !== "object" ||
    Array.isArray(value.details)
  ) {
    throw protocolMismatch("Snapshot error result is invalid");
  }
  return Object.freeze({
    code: value.code,
    message: value.message,
    details: Object.freeze({...value.details}),
  });
}

function normalizeSampleInspect(value, expectedSlot) {
  if (
    !exactKeys(value, [
      "project_revision",
      "slot",
      "asset_id",
      "playback",
      "metadata",
      "waveform_cache_identity",
    ]) ||
    !isUnsignedInteger(value.project_revision) ||
    !(value.asset_id === null ||
      (typeof value.asset_id === "string" && UUID_PATTERN.test(value.asset_id)))
  ) {
    throw protocolMismatch("Sample inspect result is invalid");
  }
  const slot = flatSlotFromAddress(value.slot);
  if (slot !== expectedSlot) {
    throw protocolMismatch("Sample inspect slot does not match the request");
  }
  const metadata = value.metadata === null
    ? null
    : normalizeMetadata(value.metadata);
  if (
    (value.asset_id === null &&
      (metadata !== null || value.waveform_cache_identity !== null)) ||
    (value.asset_id !== null &&
      (metadata === null || value.waveform_cache_identity === null))
  ) {
    throw protocolMismatch("Sample inspect Asset truth is invalid");
  }
  return Object.freeze({
    projectRevision: value.project_revision,
    slot,
    assetId: value.asset_id,
    playback: normalizePlayback(value.playback),
    metadata,
    waveformCacheIdentity: metadata === null
      ? null
      : normalizeWaveformCacheIdentity(value.waveform_cache_identity, metadata),
  });
}

function normalizeWaveform(value, request) {
  if (
    !exactKeys(value, [
      "metadata",
      "algorithm_version",
      "buckets",
      "project_revision",
    ]) ||
    !isUnsignedInteger(value.project_revision) ||
    value.algorithm_version !== 1 ||
    !Array.isArray(value.buckets) ||
    value.buckets.length === 0 ||
    value.buckets.length > request.window.bucketCount
  ) {
    throw protocolMismatch("Sample waveform result is invalid");
  }
  const metadata = normalizeMetadata(value.metadata);
  const windowFrames = request.window.endFrame - request.window.startFrame;
  const framesPerBucket = Math.ceil(
    windowFrames / request.window.bucketCount,
  );
  const expectedBucketCount = Math.ceil(windowFrames / framesPerBucket);
  if (
    metadata.sourceFrames < request.window.endFrame ||
    value.buckets.length !== expectedBucketCount
  ) {
    throw protocolMismatch("Sample waveform result is invalid");
  }
  const buckets = [];
  for (const [index, bucket] of value.buckets.entries()) {
    const expectedStart =
      request.window.startFrame + index * framesPerBucket;
    const expectedEnd = Math.min(
      request.window.endFrame,
      expectedStart + framesPerBucket,
    );
    if (
      !exactKeys(bucket, ["start_frame", "end_frame", "peak_magnitude"]) ||
      bucket.start_frame !== expectedStart ||
      bucket.end_frame !== expectedEnd ||
      !isUnsignedInteger(bucket.peak_magnitude, 32_768)
    ) {
      throw protocolMismatch("Sample waveform bucket is invalid");
    }
    buckets.push(Object.freeze({
      startFrame: bucket.start_frame,
      endFrame: bucket.end_frame,
      peakMagnitude: bucket.peak_magnitude,
    }));
  }
  return Object.freeze({
    metadata,
    algorithmVersion: value.algorithm_version,
    buckets: Object.freeze(buckets),
    projectRevision: value.project_revision,
  });
}

function normalizeSampleCommit(value) {
  const keys = [
    "committed_revision",
    "runtime_revision",
    "runtime_published",
  ];
  const published = value?.runtime_published;
  const hasSnapshotError = Object.hasOwn(value ?? {}, "snapshot_error");
  if (
    !exactKeys(value, hasSnapshotError ? [...keys, "snapshot_error"] : keys) ||
    !isUnsignedInteger(value.committed_revision) ||
    !(value.runtime_revision === null ||
      isUnsignedInteger(value.runtime_revision)) ||
    typeof published !== "boolean" ||
    (published && hasSnapshotError) ||
    (published &&
      (value.runtime_revision === null ||
        value.runtime_revision < value.committed_revision))
  ) {
    throw protocolMismatch("Sample mutation result is invalid");
  }
  const snapshotError = hasSnapshotError
    ? normalizeSnapshotError(value.snapshot_error)
    : null;
  return Object.freeze({
    committedRevision: value.committed_revision,
    runtimeRevision: value.runtime_revision,
    runtimePublished: published,
    snapshotError,
  });
}

function normalizeSampleQuota(value, expectedSlot) {
  const keys = [
    "project_revision",
    "slot",
    "bank_quota_bytes",
    "bank_used_bytes",
    "bank_remaining_bytes",
    "project_quota_bytes",
    "project_used_bytes",
    "project_remaining_bytes",
    "effective_remaining_bytes",
    "effective_remaining_frames",
    "consumed",
  ];
  if (!exactKeys(value, keys) || !Array.isArray(value.consumed) ||
      !keys.slice(0, -2).filter((key) => key !== "slot")
        .every((key) => isUnsignedInteger(value[key]))) {
    throw protocolMismatch("Sample quota result is invalid");
  }
  const slot = flatSlotFromAddress(value.slot);
  if (slot !== expectedSlot ||
      value.bank_used_bytes > value.bank_quota_bytes ||
      value.project_used_bytes > value.project_quota_bytes ||
      value.bank_remaining_bytes !== value.bank_quota_bytes - value.bank_used_bytes ||
      value.project_remaining_bytes !==
        value.project_quota_bytes - value.project_used_bytes ||
      value.effective_remaining_bytes !== Math.min(
        value.bank_remaining_bytes,
        value.project_remaining_bytes,
      ) || value.effective_remaining_frames * 4 !== value.effective_remaining_bytes) {
    throw protocolMismatch("Sample quota result is invalid");
  }
  const bank = Math.floor(slot / 16);
  const consumed = value.consumed.map((entry) => {
    if (!exactKeys(entry, ["slot", "prepared_bytes", "prepared_frames"]) ||
        !isUnsignedInteger(entry.prepared_bytes) ||
        !isUnsignedInteger(entry.prepared_frames) ||
        entry.prepared_frames * 4 !== entry.prepared_bytes) {
      throw protocolMismatch("Sample quota consumption is invalid");
    }
    const consumedSlot = flatSlotFromAddress(entry.slot);
    if (Math.floor(consumedSlot / 16) !== bank) {
      throw protocolMismatch("Sample quota consumption is invalid");
    }
    return Object.freeze({
      slot: consumedSlot,
      preparedBytes: entry.prepared_bytes,
      preparedFrames: entry.prepared_frames,
    });
  });
  return Object.freeze({
    projectRevision: value.project_revision,
    slot,
    bankQuotaBytes: value.bank_quota_bytes,
    bankUsedBytes: value.bank_used_bytes,
    bankRemainingBytes: value.bank_remaining_bytes,
    projectQuotaBytes: value.project_quota_bytes,
    projectUsedBytes: value.project_used_bytes,
    projectRemainingBytes: value.project_remaining_bytes,
    effectiveRemainingBytes: value.effective_remaining_bytes,
    effectiveRemainingFrames: value.effective_remaining_frames,
    consumed: Object.freeze(consumed),
  });
}

function normalizeAccepted(value, keys = ["accepted"]) {
  if (!exactKeys(value, keys) || typeof value.accepted !== "boolean") {
    throw protocolMismatch("Runtime control result is invalid");
  }
  return value.accepted;
}

function normalizeSequenceStatus(value, extraKeys = []) {
  const statusKeys = [
    "state",
    "session_id",
    "pattern_id",
    "pending_pattern_id",
    "expected_revision",
    "next_flush_seq",
    "pending_event_count",
    "effective_runtime_frame",
  ];
  if (
    !exactKeys(value, [...statusKeys, ...extraKeys]) ||
    !["inactive", "active", "switching", "recoverable"].includes(
      value.state,
    ) ||
    !(value.session_id === null || UUID_PATTERN.test(value.session_id)) ||
    !(value.pattern_id === null || UUID_PATTERN.test(value.pattern_id)) ||
    !(value.pending_pattern_id === null ||
      UUID_PATTERN.test(value.pending_pattern_id)) ||
    !isUnsignedInteger(value.expected_revision) ||
    !isUnsignedInteger(value.next_flush_seq) ||
    !isUnsignedInteger(value.pending_event_count) ||
    !(value.effective_runtime_frame === null ||
      isUnsignedInteger(value.effective_runtime_frame))
  ) {
    throw protocolMismatch("Sequence status result is invalid");
  }
  return Object.freeze({
    state: value.state,
    sessionId: value.session_id,
    patternId: value.pattern_id,
    pendingPatternId: value.pending_pattern_id,
    expectedRevision: value.expected_revision,
    nextFlushSequence: value.next_flush_seq,
    pendingEventCount: value.pending_event_count,
    effectiveRuntimeFrame: value.effective_runtime_frame,
  });
}

function normalizeSequenceMutation(value, extraKeys = []) {
  const mutationKeys = [
    "committed_revision",
    "replayed",
    "project_revision",
    ...extraKeys,
  ];
  const status = normalizeSequenceStatus(value, mutationKeys);
  if (
    !(value.committed_revision === null ||
      isUnsignedInteger(value.committed_revision)) ||
    typeof value.replayed !== "boolean" ||
    !(value.project_revision === null ||
      isUnsignedInteger(value.project_revision))
  ) {
    throw protocolMismatch("Sequence mutation result is invalid");
  }
  return Object.freeze({
    ...status,
    committedRevision: value.committed_revision,
    replayed: value.replayed,
    projectRevision: value.project_revision,
  });
}

function requireSequenceIdentity(value, name) {
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) {
    throw new TypeError(`${name} must be a lowercase UUID`);
  }
  return value;
}

function normalizePatternPublication(value) {
  if (value === null) {
    return null;
  }
  if (
    !exactKeys(value, ["generation", "activation_frame"]) ||
    !isPositiveInteger(value.generation) ||
    !isUnsignedInteger(value.activation_frame)
  ) {
    throw protocolMismatch("Sequence Pattern publication is invalid");
  }
  return Object.freeze({
    generation: value.generation,
    activationFrame: value.activation_frame,
  });
}

function normalizeSnapshotPublication(value, expectedPatternId) {
  if (
    !exactKeys(value, [
      "project_id",
      "project_revision",
      "pattern_id",
      "runtime_ready",
      "generation",
      "snapshot_error",
      "runtime_revision",
    ]) ||
    typeof value.project_id !== "string" ||
    !UUID_PATTERN.test(value.project_id) ||
    !isUnsignedInteger(value.project_revision) ||
    value.pattern_id !== expectedPatternId ||
    typeof value.runtime_ready !== "boolean" ||
    !(value.runtime_revision === null ||
      isUnsignedInteger(value.runtime_revision)) ||
    (value.runtime_ready &&
      (!isPositiveInteger(value.generation) ||
        value.runtime_revision === null ||
        value.runtime_revision !== value.project_revision ||
        value.snapshot_error !== null)) ||
    (!value.runtime_ready &&
      (value.generation !== null ||
        value.snapshot_error === null ||
        (value.runtime_revision !== null &&
          value.runtime_revision > value.project_revision)))
  ) {
    throw protocolMismatch("Snapshot publication result is invalid");
  }
  return Object.freeze({
    projectId: value.project_id,
    projectRevision: value.project_revision,
    patternId: value.pattern_id,
    runtimeReady: value.runtime_ready,
    generation: value.generation,
    snapshotError: value.snapshot_error === null
      ? null
      : normalizeSnapshotError(value.snapshot_error),
    runtimeRevision: value.runtime_revision,
  });
}

function normalizeSnapshotNotification(event, payload) {
  if (event === "snapshot.published") {
    const legacy = exactKeys(payload, ["generation"]);
    const task6 = exactKeys(payload, ["generation", "project_revision"]);
    if (
      (!legacy && !task6) ||
      !isPositiveInteger(payload?.generation) ||
      (task6 && !isUnsignedInteger(payload.project_revision))
    ) {
      throw protocolMismatch("Snapshot published notification is invalid");
    }
    return Object.freeze({
      generation: payload.generation,
      projectRevision: task6 ? payload.project_revision : null,
      snapshotError: null,
      runtimeRevision: null,
    });
  }

  const legacy = exactKeys(payload, ["error"]);
  const task6 = exactKeys(payload, [
    "project_revision",
    "runtime_revision",
    "error",
  ]);
  if (
    (!legacy && !task6) ||
    (task6 &&
      (!isUnsignedInteger(payload.project_revision) ||
        !(payload.runtime_revision === null ||
          isUnsignedInteger(payload.runtime_revision)) ||
        (payload.runtime_revision !== null &&
          payload.runtime_revision > payload.project_revision)))
  ) {
    throw protocolMismatch("Snapshot rejected notification is invalid");
  }
  return Object.freeze({
    generation: null,
    projectRevision: task6 ? payload.project_revision : null,
    snapshotError: normalizeSnapshotError(payload.error),
    runtimeRevision: task6 ? payload.runtime_revision : null,
  });
}

function abortError(message) {
  if (typeof DOMException === "function") {
    return new DOMException(message, "AbortError");
  }
  const error = new Error(message);
  error.name = "AbortError";
  return error;
}

function throwIfAborted(signal) {
  if (signal?.aborted !== true) {
    return;
  }
  throw abortError("Sample import was cancelled");
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
    typeof runtime?.audioCallbackHeartbeat !== "function" ||
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
  const capabilityProbeTimeoutMs =
    options.capabilityProbeTimeoutMs === undefined
      ? CONTROL_WORKER_CAPABILITY_PROBE_TIMEOUT_MS
      : options.capabilityProbeTimeoutMs;
  if (!isPositiveInteger(capabilityProbeTimeoutMs)) {
    throw new TypeError(
      "Capability probe timeout must be a positive safe integer",
    );
  }
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
  let verifiedSampleImportLimit = null;
  let verifiedSampleIngestLimits = null;
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
  let hostRequestTail = null;
  let hostQueryGeneration = 0;
  let activeHostQueryAbort = null;
  let runtimeActionTail = Promise.resolve();
  let projectActionTail = Promise.resolve();
  let pendingSequenceSwitch = null;
  let sequenceBoundaryFlush = null;
  let interruptionReservation = null;
  let safetyReservation = null;
  let fatalReservation = null;
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
  const sequenceBoundaryListeners = new Set();
  const diagnosticsListeners = new Set();
  const voiceStateListeners = new Set();
  const activePreviewSlots = new Set();

  const padBindings = [...(options.padBindings ?? [])];

  function renderPressed(pointerSlots = null) {
    options.onPressedChange?.(pointerSlots);
    renderDiagnostics();
  }

  let pointerAdapter;
  let keyboardAdapter;
  let midiAdapter;
  let suppressInputRelease = false;

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
        safetyReservation === null &&
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
    suppressInputRelease = true;
    try {
      pointerAdapter?.clearPressed();
      keyboardAdapter?.clearPressed();
      midiAdapter?.clearPressed();
    } finally {
      suppressInputRelease = false;
    }
    options.onPressedChange?.([]);
    renderDiagnostics();
  }

  async function clearOwnedPreviews(onlySlot = null, bestEffort = false) {
    const selected = onlySlot === null
      ? [...activePreviewSlots]
      : activePreviewSlots.has(onlySlot) ? [onlySlot] : [];
    for (const flatSlot of selected) {
      activePreviewSlots.delete(flatSlot);
      const slot = flatSlotAddress(flatSlot);
      try {
        normalizeAccepted(await boundedRequest(
          "sample.preview.clear",
          {slot},
        ));
      } catch (error) {
        if (!bestEffort) {
          throw error;
        }
        // Safety and cancellation clear local preview ownership fail closed.
      }
    }
  }

  function clearPreviewsForCancellation(onlySlot = null) {
    void serializeRuntimeAction(() =>
      clearOwnedPreviews(onlySlot, true)).catch(() => {});
  }

  async function stopAllInRuntimeLane(bestEffort = false) {
    try {
      const result = await boundedRequest("sample.stop", {});
      if (result?.scope !== "all") {
        throw protocolMismatch("Sample stop scope is invalid");
      }
      return normalizeAccepted(result, ["accepted", "scope"]);
    } catch (error) {
      if (!bestEffort) {
        throw error;
      }
      return false;
    }
  }

  function beginSafetyCleanup(reason) {
    if (safetyReservation !== null) {
      return safetyReservation;
    }
    hostQueryGeneration += 1;
    activeHostQueryAbort?.abort();
    const reservation = {reason, promise: null};
    safetyReservation = reservation;
    reservation.promise = serializeRuntimeAction(async () => {
      await clearOwnedPreviews(null, true);
      return stopAllInRuntimeLane(true);
    });
    Object.freeze(reservation);
    clearPressed();
    return reservation;
  }

  function releaseSafetyReservation(reservation) {
    if (safetyReservation === reservation && !closing) {
      safetyReservation = null;
      renderDiagnostics();
    }
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
    activePreviewSlots.clear();
    pendingSequenceSwitch = null;
    sequenceBoundaryFlush = null;
    sequenceBoundaryListeners.clear();
    voiceStateListeners.clear();
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

  function fail(codeOrError, targetOverride) {
    if (
      fatalReservation !== null ||
      ["restart-required", "failed", "closed"].includes(machine.state)
    ) {
      return false;
    }
    const code =
      typeof codeOrError === "string"
        ? validatedErrorCode(codeOrError)
        : errorCode(codeOrError);
    lastErrorCode = code;
    lastErrorDetails =
      typeof codeOrError === "string"
        ? Object.freeze({})
        : safeErrorDetails(codeOrError);
    closing = true;
    const target =
      targetOverride ??
      (["HOST_RESTART_REQUIRED", "HOST_TIMEOUT"].includes(code)
        ? "restart-required"
        : "failed");
    const safety = beginSafetyCleanup(`fatal:${code}`);
    const reservation = Object.freeze({code, safety, target});
    fatalReservation = reservation;
    void safety.promise.then(() => {
      if (
        fatalReservation !== reservation ||
        ["restart-required", "failed", "closed"].includes(machine.state)
      ) {
        return;
      }
      invalidateProbe();
      machine.transition(target, {reason: code});
      renderDiagnostics();
    }).catch(() => {
      // The best-effort safety lane absorbs Host cleanup failures.
    });
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

  async function dispatchBoundedRequest(operation, payload, requestOptions = {}) {
    const request = createRequestEnvelope({ operation, payload, crypto });
    const transportOptions = {
      deadlineMs: requestOptions.deadlineMs ?? deadlineForOperation(operation),
    };
    if (requestOptions.sidecar !== undefined) {
      transportOptions.sidecar = requestOptions.sidecar;
    }
    if (requestOptions.signal !== undefined) {
      transportOptions.signal = requestOptions.signal;
    }
    if (requestOptions.cancelQuery === true) {
      transportOptions.cancelQuery = true;
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
      throw typedError(
        validatedErrorCode(response.error.code, "HOST_PROTOCOL_MISMATCH"),
        "Host request was rejected",
        Object.freeze({...response.error.details}),
      );
    }
    return response.result;
  }

  function boundedRequest(operation, payload, requestOptions = {}) {
    const interruptible = SAFETY_INTERRUPTIBLE_HOST_OPERATIONS.has(operation);
    const queryGeneration = hostQueryGeneration;
    const action = async () => {
      if (interruptible && queryGeneration !== hostQueryGeneration) {
        throw abortError("Host query was cancelled for Runtime safety");
      }
      if (!interruptible) {
        return dispatchBoundedRequest(operation, payload, requestOptions);
      }
      const controller = new AbortController();
      activeHostQueryAbort = controller;
      try {
        return await dispatchBoundedRequest(operation, payload, {
          ...requestOptions,
          signal: controller.signal,
          cancelQuery: true,
        });
      } finally {
        if (activeHostQueryAbort === controller) activeHostQueryAbort = null;
      }
    };
    const pending = hostRequestTail === null
      ? action()
      : hostRequestTail.then(action);
    const completion = pending.then(
      () => undefined,
      () => undefined,
    );
    hostRequestTail = completion;
    void completion.then(() => {
      if (hostRequestTail === completion) hostRequestTail = null;
    });
    return pending;
  }

  async function recoverableQuery(operation, payload) {
    for (let attempt = 0; attempt < SAFETY_QUERY_RETRY_LIMIT; ++attempt) {
      const queryGeneration = hostQueryGeneration;
      try {
        return await boundedRequest(operation, payload);
      } catch (error) {
        const safety = safetyReservation;
        if (
          error?.name !== "AbortError" ||
          queryGeneration === hostQueryGeneration ||
          safety === null ||
          closing ||
          ["restart-required", "failed", "closed"].includes(machine.state)
        ) {
          throw error;
        }
        try {
          await safety.promise;
        } catch {
          throw error;
        }
        if (
          closing ||
          ["restart-required", "failed", "closed"].includes(machine.state)
        ) {
          throw error;
        }
      }
    }
    throw typedError(
      "HOST_TIMEOUT",
      "Host query could not recover after Runtime safety",
    );
  }

  /**
   * @template T
   * @param {() => T} action
   * @returns {Promise<Awaited<T>>}
   */
  function serializeRuntimeAction(action) {
    const pending = runtimeActionTail.then(action);
    runtimeActionTail = pending.then(
      () => undefined,
      () => undefined,
    );
    return pending;
  }

  /**
   * @template T
   * @param {() => T} action
   * @returns {Promise<Awaited<T>>}
   */
  function serializeProjectAction(action) {
    const pending = projectActionTail.then(action);
    projectActionTail = pending.then(
      () => undefined,
      () => undefined,
    );
    return pending;
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

  /**
   * @param {number} flatSlot
   * @param {number} velocity
   * @param {"pointer" | "keyboard" | "midi"} source
   * @returns {Promise<false | Readonly<{
   *   sequence: number,
   *   slot: number,
   *   velocity: number,
   *   source: "pointer" | "keyboard" | "midi",
   * }>>}
   */
  async function dispatchTrigger(flatSlot, velocity, source) {
    if (
      !Number.isInteger(flatSlot) ||
      flatSlot < 0 ||
      flatSlot > 63 ||
      !Number.isInteger(velocity) ||
      velocity < 1 ||
      velocity > 127 ||
      !TRIGGER_SOURCES.has(source) ||
      closing ||
      interruptionReservation !== null ||
      safetyReservation !== null
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
        : !closing &&
          interruptionReservation === null &&
          machine.state === "running";
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
    return serializeRuntimeAction(() =>
      dispatchTrigger(flatSlot, velocity, source));
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

  async function activateRuntimeForRecovery(
    epoch,
    activationDeadline =
      monotonicNow() + deadlineForOperation("audio.activate"),
    callbackReady = false,
  ) {
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
      if (!callbackReady) {
        const callbackBaseline = readAudioCallbackHeartbeat();
        await awaitAudioCallbackAfterResume(
          callbackBaseline, activationDeadline);
      }
      await boundedRequest("audio.activate", {}, {
        deadlineMs: remainingActivationBudget(activationDeadline),
      });
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
    if (
      closing ||
      interruptionReservation !== null ||
      machine.state === "failed" ||
      machine.state === "closed"
    ) {
      return false;
    }

    const isNewRunningEdge = machine.state === "running";
    const isNewRecoveryEdge =
      machine.state === "recovering" && recoveryEpoch?.contextUsable === true;
    if (!isNewRunningEdge && !isNewRecoveryEdge) {
      return false;
    }
    const reservation = Object.freeze({reason});
    interruptionReservation = reservation;
    const safety = beginSafetyCleanup(`interruption:${reason}`);
    void safety.promise.then(async () => {
      if (closing || interruptionReservation !== reservation) {
        return;
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
      await boundedRequest("audio.suspend", {});
      if (recoveryEpoch !== epoch || closing) {
        return;
      }
      epoch.suspendComplete = true;
      if (machine.state === "interrupted") {
        machine.transition("recovering", { reason: "recovery_started" });
      }
      if (audioContext?.state === "running") {
        await activateRuntimeForRecovery(epoch);
      } else if (machine.state === "recovering") {
        machine.transition("audio-suspended", {
          reason: "recovery_gesture_required",
        });
      }
    }).catch((error) => fail(error)).finally(() => {
      if (interruptionReservation === reservation) {
        interruptionReservation = null;
      }
      releaseSafetyReservation(safety);
    });
    return true;
  }

  function markAdverseCondition(condition) {
    const hadActiveCondition =
      condition === "audio_statechange"
        ? activeAdverseConditions.has(condition)
        : activeAdverseConditions.has("visibilitychange") ||
          activeAdverseConditions.has("pagehide") ||
          activeAdverseConditions.has("blur");
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

  function observeBlur() {
    if (markAdverseCondition("blur")) {
      beginInterruption("blur");
    } else {
      clearPressed();
    }
  }

  function observeFocus() {
    activeAdverseConditions.delete("blur");
    renderDiagnostics();
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

  function observeVoiceStates(payload) {
    if (
      !exactKeys(payload, ["events"]) ||
      !Array.isArray(payload.events) ||
      payload.events.length === 0 ||
      payload.events.length > VOICE_NOTIFICATION_EVENT_LIMIT
    ) {
      fail("HOST_PROTOCOL_MISMATCH");
      return;
    }
    const events = [];
    for (const event of payload.events) {
      if (
        !exactKeys(event, [
          "sequence",
          "slot",
          "state",
          "runtime_frame",
          "source_frame",
        ]) ||
        !isPositiveInteger(event.sequence) ||
        !isUnsignedInteger(event.slot, 63) ||
        !VOICE_STATES.has(event.state) ||
        !isUnsignedInteger(event.runtime_frame) ||
        !isUnsignedInteger(event.source_frame)
      ) {
        fail("HOST_PROTOCOL_MISMATCH");
        return;
      }
      events.push(Object.freeze({
        sequence: event.sequence,
        slot: event.slot,
        state: event.state,
        runtimeFrame: event.runtime_frame,
        sourceFrame: event.source_frame,
      }));
    }
    for (const event of events) {
      for (const listener of voiceStateListeners) {
        try {
          listener(event);
        } catch {
          // A render listener cannot corrupt the authoritative Voice stream.
        }
      }
    }
  }

  function acknowledgeSequenceBoundary(boundary) {
    const pending = pendingSequenceSwitch;
    if (
      pending === null ||
      sequenceBoundaryFlush !== null ||
      boundary.sessionId !== pending.sessionId ||
      boundary.patternId !== pending.patternId ||
      boundary.runtimeFrame !== pending.runtimeFrame ||
      boundary.generation !== pending.generation
    ) {
      return;
    }
    const reservation = Object.freeze({pending, boundary});
    sequenceBoundaryFlush = reservation;
    const commandId = crypto.randomUUID();
    void serializeRuntimeAction(async () => {
      if (
        sequenceBoundaryFlush !== reservation ||
        pendingSequenceSwitch !== pending
      ) {
        return null;
      }
      return commitSequenceBoundaryInLane(
        "sequence.record.flush", pending.sessionId, commandId,
      );
    }).then((result) => {
      if (result === null || sequenceBoundaryFlush !== reservation) {
        return;
      }
      if (
        result.state !== "active" ||
        result.sessionId !== pending.sessionId ||
        result.patternId !== pending.patternId ||
        result.pendingPatternId !== null ||
        result.effectiveRuntimeFrame !== null
      ) {
        throw protocolMismatch("Sequence boundary flush authority is invalid");
      }
      pendingSequenceSwitch = null;
      sequenceBoundaryFlush = null;
      for (const listener of sequenceBoundaryListeners) {
        try {
          listener(boundary);
        } catch {
          // UI observers cannot alter the authoritative boundary stream.
        }
      }
    }).catch((error) => {
      if (sequenceBoundaryFlush === reservation) {
        sequenceBoundaryFlush = null;
        fail(error);
      }
    });
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
    if (notification.event === "runtime.voice_state") {
      observeVoiceStates(notification.payload);
      return;
    }
    if (notification.event === "sequence.bar_boundary") {
      const value = notification.payload;
      if (
        !exactKeys(value, [
          "session_id",
          "pattern_id",
          "runtime_frame",
          "generation",
        ]) ||
        !UUID_PATTERN.test(value.session_id) ||
        !UUID_PATTERN.test(value.pattern_id) ||
        !isUnsignedInteger(value.runtime_frame) ||
        !isPositiveInteger(value.generation)
      ) {
        fail("HOST_PROTOCOL_MISMATCH");
        return;
      }
      const boundary = Object.freeze({
        sessionId: value.session_id,
        patternId: value.pattern_id,
        runtimeFrame: value.runtime_frame,
        generation: value.generation,
      });
      acknowledgeSequenceBoundary(boundary);
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
    if (
      notification.event === "snapshot.published" ||
      notification.event === "snapshot.rejected"
    ) {
      let snapshot;
      try {
        snapshot = normalizeSnapshotNotification(
          notification.event,
          notification.payload,
        );
      } catch (error) {
        fail(error);
        return;
      }
      if (notification.event === "snapshot.published") {
        controlGeneration = snapshot.generation;
      }
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

  function readAudioCallbackHeartbeat() {
    const heartbeat = runtime?.audioCallbackHeartbeat?.();
    if (
      !Number.isInteger(heartbeat) ||
      heartbeat < 0 ||
      heartbeat > 0xffff_ffff
    ) {
      throw typedError(
        "HOST_PROTOCOL_MISMATCH",
        "AudioWorklet callback heartbeat is invalid",
      );
    }
    return heartbeat;
  }

  async function awaitAudioCallbackAfterResume(baseline, deadline) {
    let heartbeat = readAudioCallbackHeartbeat();
    while (heartbeat === baseline && monotonicNow() < deadline) {
      await new Promise((resolvePromise) =>
        timers.setTimeout(resolvePromise, 0));
      heartbeat = readAudioCallbackHeartbeat();
    }
    if (heartbeat === baseline) {
      throw typedError(
        "HOST_TIMEOUT",
        "AudioWorklet callback did not resume",
      );
    }
  }

  function remainingActivationBudget(deadline) {
    const remaining = Math.ceil(deadline - monotonicNow());
    if (remaining <= 0) {
      throw typedError(
        "HOST_TIMEOUT",
        "AudioWorklet activation deadline expired",
      );
    }
    return Math.min(deadlineForOperation("audio.activate"), remaining);
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
      const activationDeadline =
        monotonicNow() + deadlineForOperation("audio.activate");
      const callbackBaseline = readAudioCallbackHeartbeat();
      await audioContext.resume();
      if (!activationIsCurrent(reservation, "audio-suspended")) {
        return false;
      }
      await awaitAudioCallbackAfterResume(
        callbackBaseline, activationDeadline);
      if (recoveryEpoch !== null) {
        machine.transition("recovering", {
          reason: "recovery_activation",
          recoveryEpoch: true,
        });
        recoveryEpoch.contextUsable = true;
        recoveryEpoch.suspendComplete = true;
        await activateRuntimeForRecovery(
          recoveryEpoch, activationDeadline, true);
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
      await boundedRequest("audio.activate", {}, {
        deadlineMs: remainingActivationBudget(activationDeadline),
      });
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
    if (
      closing ||
      safetyReservation !== null ||
      machine.state !== "running"
    ) {
      return false;
    }
    const safety = beginSafetyCleanup("audio.suspend");
    try {
      await safety.promise;
      if (closing || machine.state !== "running") {
        return false;
      }
      machine.handleOperation("audio.suspend");
      expectedContextSuspend = true;
      // The Host closes its admission gate by requesting one final
      // AudioWorklet quantum. Suspending the browser context concurrently can
      // remove that quantum and strand Host quiescence until its deadline.
      // Commit Host quiescence first, then park the browser context.
      await boundedRequest("audio.suspend", {});
      await (audioContext?.suspend?.() ?? Promise.resolve());
      return true;
    } catch (error) {
      fail(error);
      return false;
    } finally {
      releaseSafetyReservation(safety);
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

  function subscribeSequenceBarBoundary(listener) {
    requireFunction(listener, "Sequence Bar-boundary listener");
    sequenceBoundaryListeners.add(listener);
    return () => sequenceBoundaryListeners.delete(listener);
  }

  function subscribeVoiceState(listener) {
    requireFunction(listener, "Voice state listener");
    if (voiceStateListeners.size >= VOICE_LISTENER_LIMIT) {
      throw typedError(
        "WEB_RUNTIME_RESOURCE_LIMIT",
        "Voice state listener limit reached",
        {limit: VOICE_LISTENER_LIMIT},
      );
    }
    voiceStateListeners.add(listener);
    let subscribed = true;
    return () => {
      if (!subscribed) {
        return false;
      }
      subscribed = false;
      return voiceStateListeners.delete(listener);
    };
  }

  function openProject(projectId, patternId, requestOptions = {}) {
    return serializeProjectAction(() => boundedRequest("project.open", {
      project_id: projectId,
      pattern_id: patternId,
    }, requestOptions));
  }

  async function inspectProject() {
    return recoverableQuery("project.inspect", {});
  }

  function beginSequence(request) {
    if (
      request === null ||
      typeof request !== "object" ||
      (!exactKeys(request, ["sessionId", "patternId", "expectedRevision"]) &&
        !exactKeys(request, [
          "sessionId", "patternId", "expectedRevision", "armedCaptureSlot",
        ])) ||
      !isUnsignedInteger(request.expectedRevision)
    ) {
      throw new TypeError("Sequence begin request is invalid");
    }
    const sessionId = requireSequenceIdentity(request.sessionId, "sessionId");
    const patternId = requireSequenceIdentity(request.patternId, "patternId");
    let armedCaptureSlot;
    try {
      armedCaptureSlot = request.armedCaptureSlot === undefined ||
          request.armedCaptureSlot === null
        ? null
        : flatSlotAddress(request.armedCaptureSlot);
    } catch (error) {
      throw new TypeError("Sequence armed capture slot is invalid", {cause: error});
    }
    return serializeRuntimeAction(async () => {
      const value = await boundedRequest("sequence.record.begin", {
        session_id: sessionId,
        pattern_id: patternId,
        expected_revision: request.expectedRevision,
        ...(request.armedCaptureSlot === undefined
          ? {}
          : {armed_capture_slot: armedCaptureSlot}),
      });
      const mutation = normalizeSequenceMutation(value, ["transport_anchor"]);
      const anchor = value.transport_anchor;
      if (
        !exactKeys(anchor, ["runtime_frame", "tick_numerator", "bpm"]) ||
        !isUnsignedInteger(anchor.runtime_frame) ||
        !isUnsignedInteger(anchor.tick_numerator) ||
        !isUnsignedInteger(anchor.bpm, 240) ||
        anchor.bpm < 40
      ) {
        throw protocolMismatch("Sequence transport anchor is invalid");
      }
      const result = Object.freeze({
        ...mutation,
        transportAnchor: Object.freeze({
          runtimeFrame: anchor.runtime_frame,
          tickNumerator: anchor.tick_numerator,
          bpm: anchor.bpm,
        }),
      });
      pendingSequenceSwitch = null;
      sequenceBoundaryFlush = null;
      return result;
    });
  }

  function disarmSequenceCapture(request) {
    if (
      request === null ||
      typeof request !== "object" ||
      !exactKeys(request, ["sessionId", "slot"])
    ) {
      return Promise.reject(new TypeError("Sequence capture disarm request is invalid"));
    }
    let sessionId;
    let slot;
    try {
      sessionId = requireSequenceIdentity(request.sessionId, "sessionId");
      slot = flatSlotAddress(request.slot);
    } catch (error) {
      return Promise.reject(error);
    }
    return serializeRuntimeAction(async () => {
      const result = await boundedRequest("sequence.capture.disarm", {
        session_id: sessionId,
        slot,
      });
      if (!exactKeys(result, ["disarmed"]) || result.disarmed !== true) {
        throw protocolMismatch("Sequence capture disarm result is invalid");
      }
      return true;
    });
  }

  function recordSequenceEvent(request) {
    if (
      request === null ||
      typeof request !== "object" ||
      !exactKeys(request, ["sessionId", "slot", "velocity", "pressed"]) ||
      !isUnsignedInteger(request.slot, 63) ||
      !isUnsignedInteger(request.velocity, 127) ||
      typeof request.pressed !== "boolean" ||
      (request.pressed ? request.velocity === 0 : request.velocity !== 0)
    ) {
      throw new TypeError("Sequence Pad event is invalid");
    }
    const sessionId = requireSequenceIdentity(request.sessionId, "sessionId");
    return serializeRuntimeAction(async () => {
      const value = await boundedRequest("sequence.record.event", {
        session_id: sessionId,
        event: {
          slot: flatSlotAddress(request.slot),
          velocity: request.velocity,
          pressed: request.pressed,
        },
      });
      const mutation = normalizeSequenceMutation(
        value,
        ["runtime_frame", "input_sequence"],
      );
      if (
        !isUnsignedInteger(value.runtime_frame) ||
        !isPositiveInteger(value.input_sequence)
      ) {
        throw protocolMismatch("Sequence event clock is invalid");
      }
      return Object.freeze({
        ...mutation,
        runtimeFrame: value.runtime_frame,
        inputSequence: value.input_sequence,
      });
    });
  }

  async function commitSequenceBoundaryInLane(operation, sessionId, commandId) {
    const value = await boundedRequest(operation, {
      session_id: sessionId,
      command_id: commandId,
    });
    const mutation = normalizeSequenceMutation(
      value,
      ["runtime_frame", "pattern_publication"],
    );
    if (!isUnsignedInteger(value.runtime_frame)) {
      throw protocolMismatch("Sequence flush clock is invalid");
    }
    return Object.freeze({
      ...mutation,
      runtimeFrame: value.runtime_frame,
      patternPublication: normalizePatternPublication(
        value.pattern_publication,
      ),
    });
  }

  function commitSequenceBoundary(operation, request) {
    if (
      request === null ||
      typeof request !== "object" ||
      !exactKeys(request, ["sessionId", "commandId"])
    ) {
      throw new TypeError("Sequence flush request is invalid");
    }
    const sessionId = requireSequenceIdentity(request.sessionId, "sessionId");
    const commandId = requireSequenceIdentity(request.commandId, "commandId");
    return serializeRuntimeAction(async () => {
      const result = await commitSequenceBoundaryInLane(
        operation, sessionId, commandId,
      );
      if (
        pendingSequenceSwitch?.sessionId === sessionId &&
        (operation === "sequence.record.stop" ||
          (operation === "sequence.record.flush" &&
            sequenceBoundaryFlush === null && result.state !== "switching"))
      ) {
        pendingSequenceSwitch = null;
        sequenceBoundaryFlush = null;
      }
      return result;
    });
  }

  function flushSequence(request) {
    return commitSequenceBoundary("sequence.record.flush", request);
  }

  function stopSequence(request) {
    return commitSequenceBoundary("sequence.record.stop", request);
  }

  function requestPatternSwitch(request) {
    if (
      request === null ||
      typeof request !== "object" ||
      !exactKeys(request, ["sessionId", "nextPatternId"])
    ) {
      throw new TypeError("Sequence switch request is invalid");
    }
    const sessionId = requireSequenceIdentity(request.sessionId, "sessionId");
    const nextPatternId = requireSequenceIdentity(
      request.nextPatternId,
      "nextPatternId",
    );
    return serializeRuntimeAction(async () => {
      const value = await boundedRequest("sequence.record.switch-request", {
        session_id: sessionId,
        next_pattern_id: nextPatternId,
      });
      const result = Object.freeze({
        ...normalizeSequenceMutation(value, ["pattern_publication"]),
        patternPublication: normalizePatternPublication(
          value.pattern_publication,
        ),
      });
      if (
        result.state !== "switching" ||
        result.sessionId !== sessionId ||
        result.pendingPatternId !== nextPatternId ||
        result.effectiveRuntimeFrame === null ||
        result.patternPublication === null ||
        result.patternPublication.activationFrame !==
          result.effectiveRuntimeFrame
      ) {
        throw protocolMismatch("Sequence switch authority is invalid");
      }
      pendingSequenceSwitch = Object.freeze({
        sessionId,
        patternId: nextPatternId,
        runtimeFrame: result.effectiveRuntimeFrame,
        generation: result.patternPublication.generation,
      });
      sequenceBoundaryFlush = null;
      return result;
    });
  }

  function createPattern(request) {
    if (
      request === null ||
      typeof request !== "object" ||
      !exactKeys(request, ["patternId", "bars", "expectedRevision"]) ||
      !UUID_PATTERN.test(request.patternId) ||
      ![1, 2, 4, 8].includes(request.bars) ||
      !isUnsignedInteger(request.expectedRevision)
    ) {
      return Promise.reject(new TypeError("Pattern create request is invalid"));
    }
    return serializeProjectAction(async () => {
      const value = await boundedRequest("pattern.create", {
        command_id: crypto.randomUUID(),
        expected_revision: request.expectedRevision,
        pattern_id: request.patternId,
        bars: request.bars,
      });
      if (
        !exactKeys(value, [
          "committed_revision",
          "pattern_id",
          "bars",
          "replayed",
          "project_revision",
        ]) ||
        !isUnsignedInteger(value.committed_revision) ||
        value.pattern_id !== request.patternId ||
        value.bars !== request.bars ||
        typeof value.replayed !== "boolean" ||
        value.project_revision !== value.committed_revision
      ) {
        throw protocolMismatch("Pattern create result is invalid");
      }
      return Object.freeze({
        committedRevision: value.committed_revision,
        patternId: value.pattern_id,
        bars: value.bars,
        replayed: value.replayed,
        projectRevision: value.project_revision,
      });
    });
  }

  function updateSequenceSettings(request) {
    if (
      request === null ||
      typeof request !== "object" ||
      !exactKeys(request, [
        "expectedRevision",
        "sessionId",
        "bpm",
        "quantizeEnabled",
        "swingPercent",
      ]) ||
      !isUnsignedInteger(request.expectedRevision) ||
      !(request.sessionId === null || UUID_PATTERN.test(request.sessionId)) ||
      !(request.bpm === null ||
        (isUnsignedInteger(request.bpm, 240) && request.bpm >= 40)) ||
      !(request.quantizeEnabled === null ||
        typeof request.quantizeEnabled === "boolean") ||
      !(request.swingPercent === null ||
        (isUnsignedInteger(request.swingPercent, 75) &&
          request.swingPercent >= 50)) ||
      (request.bpm === null && request.quantizeEnabled === null &&
        request.swingPercent === null)
    ) {
      return Promise.reject(new TypeError("Sequence settings request is invalid"));
    }
    return serializeRuntimeAction(async () => {
      const value = await boundedRequest("sequence.settings.update", {
        command_id: crypto.randomUUID(),
        expected_revision: request.expectedRevision,
        session_id: request.sessionId,
        bpm: request.bpm,
        quantize_enabled: request.quantizeEnabled,
        swing_percent: request.swingPercent,
      });
      if (
        !exactKeys(value, [
          "committed_revision",
          "bpm",
          "quantize_enabled",
          "swing_percent",
          "replayed",
          "pattern_publication",
          "project_revision",
        ]) ||
        !isUnsignedInteger(value.committed_revision) ||
        !isUnsignedInteger(value.bpm, 240) || value.bpm < 40 ||
        typeof value.quantize_enabled !== "boolean" ||
        !isUnsignedInteger(value.swing_percent, 75) ||
        value.swing_percent < 50 ||
        typeof value.replayed !== "boolean" ||
        value.project_revision !== value.committed_revision
      ) {
        throw protocolMismatch("Sequence settings result is invalid");
      }
      return Object.freeze({
        committedRevision: value.committed_revision,
        bpm: value.bpm,
        quantizeEnabled: value.quantize_enabled,
        swingPercent: value.swing_percent,
        replayed: value.replayed,
        patternPublication: normalizePatternPublication(value.pattern_publication),
        projectRevision: value.project_revision,
      });
    });
  }

  async function querySequenceStatus(projectId = null) {
    const payload = projectId === null
      ? {}
      : {project_id: requireSequenceIdentity(projectId, "projectId")};
    const value = await recoverableQuery("sequence.record.status", payload);
    return normalizeSequenceStatus(value, ["project_revision"]);
  }

  async function listSequenceRecovery(projectId = null) {
    const payload = projectId === null
      ? {}
      : {project_id: requireSequenceIdentity(projectId, "projectId")};
    const value = await recoverableQuery("sequence.recovery.list", payload);
    if (
      !exactKeys(value, ["candidates", "project_revision"]) ||
      !Array.isArray(value.candidates) ||
      value.project_revision !== null
    ) {
      throw protocolMismatch("Sequence recovery inventory is invalid");
    }
    return Object.freeze(value.candidates.map((candidate) => {
      if (
        !exactKeys(candidate, [
          "session_id",
          "pattern_id",
          "bars",
          "reason",
          "event_count",
        ]) ||
        !UUID_PATTERN.test(candidate.session_id) ||
        !UUID_PATTERN.test(candidate.pattern_id) ||
        ![1, 2, 4, 8].includes(candidate.bars) ||
        typeof candidate.reason !== "string" ||
        !isUnsignedInteger(candidate.event_count)
      ) {
        throw protocolMismatch("Sequence recovery candidate is invalid");
      }
      return Object.freeze({
        sessionId: candidate.session_id,
        patternId: candidate.pattern_id,
        bars: candidate.bars,
        reason: candidate.reason,
        eventCount: candidate.event_count,
      });
    }));
  }

  function applySequenceRecovery(request) {
    if (
      request === null ||
      typeof request !== "object" ||
      !exactKeys(request, ["sessionId", "destinationPatternId"]) ||
      !(request.destinationPatternId === null ||
        typeof request.destinationPatternId === "string")
    ) {
      throw new TypeError("Sequence recovery request is invalid");
    }
    const sessionId = requireSequenceIdentity(request.sessionId, "sessionId");
    const destinationPatternId = request.destinationPatternId === null
      ? null
      : requireSequenceIdentity(
        request.destinationPatternId,
        "destinationPatternId",
      );
    return serializeProjectAction(async () => normalizeSequenceMutation(
      await boundedRequest("sequence.recovery.apply", {
        session_id: sessionId,
        destination_pattern_id: destinationPatternId,
      }),
    ));
  }

  function discardSequenceRecovery(sessionId) {
    requireSequenceIdentity(sessionId, "sessionId");
    return serializeProjectAction(async () => {
      const value = await boundedRequest("sequence.recovery.discard", {
        session_id: sessionId,
      });
      if (
        !exactKeys(value, ["session_id", "discarded", "project_revision"]) ||
        value.session_id !== sessionId ||
        value.discarded !== true ||
        value.project_revision !== null
      ) {
        throw protocolMismatch("Sequence recovery discard result is invalid");
      }
      return true;
    });
  }

  async function reloadSnapshot(patternId) {
    return boundedRequest("snapshot.reload", {pattern_id: patternId});
  }

  async function inspectSample(flatSlot) {
    const slot = flatSlotAddress(flatSlot);
    const result = await recoverableQuery("sample.inspect", {slot});
    return normalizeSampleInspect(result, flatSlot);
  }

  async function querySampleQuota(flatSlot) {
    const slot = flatSlotAddress(flatSlot);
    const result = await recoverableQuery("sample.quota", {slot});
    return normalizeSampleQuota(result, flatSlot);
  }

  function sampleIngestLimits() {
    if (verifiedSampleIngestLimits === null) {
      throw typedError(
        "HOST_STATE_INVALID",
        "Verified Sample ingest limits are unavailable",
      );
    }
    return verifiedSampleIngestLimits;
  }

  async function queryWaveform(request) {
    if (
      !exactKeys(request, ["slot", "window"]) ||
      !exactKeys(request.window, [
        "startFrame",
        "endFrame",
        "bucketCount",
      ]) ||
      !isUnsignedInteger(request.window.startFrame) ||
      !isUnsignedInteger(request.window.endFrame) ||
      request.window.startFrame >= request.window.endFrame ||
      !isUnsignedInteger(request.window.bucketCount, 512) ||
      request.window.bucketCount === 0
    ) {
      throw new TypeError("Sample waveform query is invalid");
    }
    const result = await recoverableQuery("sample.waveform", {
      slot: flatSlotAddress(request.slot),
      window: {
        start_frame: request.window.startFrame,
        end_frame: request.window.endFrame,
        bucket_count: request.window.bucketCount,
      },
    });
    return normalizeWaveform(result, request);
  }

  function updatePad(request) {
    if (
      !exactKeys(request, ["slot", "expectedRevision", "playback"]) ||
      !isUnsignedInteger(request.expectedRevision)
    ) {
      return Promise.reject(new TypeError("Sample update request is invalid"));
    }
    let slot;
    let playback;
    try {
      slot = flatSlotAddress(request.slot);
      playback = wirePlayback(request.playback);
    } catch (error) {
      return Promise.reject(error);
    }
    return serializeProjectAction(async () => normalizeSampleCommit(
      await boundedRequest("sample.update_pad", {
        command_id: crypto.randomUUID(),
        expected_revision: request.expectedRevision,
        slot,
        playback,
      }),
    ));
  }

  function resetPad(request) {
    if (
      !exactKeys(request, ["slot", "expectedRevision"]) ||
      !isUnsignedInteger(request.expectedRevision)
    ) {
      return Promise.reject(new TypeError("Sample reset request is invalid"));
    }
    let slot;
    try {
      slot = flatSlotAddress(request.slot);
    } catch (error) {
      return Promise.reject(error);
    }
    return serializeProjectAction(async () => normalizeSampleCommit(
      await boundedRequest("sample.reset_pad", {
        command_id: crypto.randomUUID(),
        expected_revision: request.expectedRevision,
        slot,
      }),
    ));
  }

  function importAssignSample(file, importOptions = {}) {
    return serializeProjectAction(async () => {
      const allowedKeys = [
        "slot", "expectedRevision", "sequenceSessionId", "signal", "onProgress",
      ];
      if (
        importOptions === null ||
        typeof importOptions !== "object" ||
        Array.isArray(importOptions) ||
        Object.keys(importOptions).some((key) => !allowedKeys.includes(key)) ||
        !Object.hasOwn(importOptions, "slot") ||
        !Object.hasOwn(importOptions, "expectedRevision") ||
        !isUnsignedInteger(importOptions.expectedRevision) ||
        (importOptions.sequenceSessionId !== undefined &&
          !UUID_PATTERN.test(importOptions.sequenceSessionId))
      ) {
        throw new TypeError("Sample import options are invalid");
      }
      const slot = flatSlotAddress(importOptions.slot);
      const signal = importOptions.signal;
      const onProgress = importOptions.onProgress ?? (() => {});
      if (typeof onProgress !== "function") {
        throw new TypeError("Sample import progress observer must be a function");
      }
      throwIfAborted(signal);
      if (
        typeof file?.slice !== "function" ||
        !isUnsignedInteger(file.size) ||
        file.size === 0
      ) {
        throw typedError("UNSUPPORTED_AUDIO", "Sample source is invalid");
      }
      if (verifiedSampleImportLimit === null) {
        throw typedError(
          "HOST_STATE_INVALID",
          "Verified Sample import limits are unavailable",
        );
      }
      if (file.size > verifiedSampleImportLimit) {
        throw typedError(
          "WEB_RUNTIME_RESOURCE_LIMIT",
          "Sample source exceeds the Web Runtime limit",
          {limit: verifiedSampleImportLimit, observed: file.size},
        );
      }
      const totalBytes = file.size;
      const importToken = crypto.randomUUID();
      const commandId = crypto.randomUUID();
      const assetId = crypto.randomUUID();
      let beginAttempted = false;
      let committed = false;
      let abortAttempted = false;
      const report = (completedBytes) => {
        try {
          onProgress(Object.freeze({completedBytes, totalBytes}));
        } catch {
          // Progress observers cannot change the authoritative import outcome.
        }
      };
      const abortOnce = async () => {
        if (!beginAttempted || committed || abortAttempted) {
          return;
        }
        abortAttempted = true;
        const aborted = await boundedRequest("sample.import.abort", {
          import_token: importToken,
        });
        if (!exactKeys(aborted, ["aborted"]) || aborted.aborted !== true) {
          throw protocolMismatch("Sample import abort result is invalid");
        }
      };

      report(0);
      try {
        throwIfAborted(signal);
        beginAttempted = true;
        const begun = await boundedRequest("sample.import.begin", {
          import_token: importToken,
          command_id: commandId,
          expected_revision: importOptions.expectedRevision,
          ...(importOptions.sequenceSessionId === undefined
            ? {}
            : {sequence_session_id: importOptions.sequenceSessionId}),
          slot,
          asset_id: assetId,
          byte_length: totalBytes,
        }, {signal});
        if (
          !exactKeys(begun, ["token", "expected_bytes"]) ||
          begun.token !== importToken ||
          begun.expected_bytes !== totalBytes
        ) {
          throw protocolMismatch("Sample import session result is invalid");
        }

        let offset = 0;
        while (offset < totalBytes) {
          throwIfAborted(signal);
          const end = Math.min(offset + MAX_ASSET_BYTES, totalBytes);
          const part = file.slice(offset, end);
          if (typeof part?.arrayBuffer !== "function") {
            throw typedError("UNSUPPORTED_AUDIO", "Sample source cannot be read");
          }
          const bytes = new Uint8Array(await part.arrayBuffer());
          if (bytes.byteLength !== end - offset) {
            throw typedError("UNSUPPORTED_AUDIO", "Sample source ended unexpectedly");
          }
          throwIfAborted(signal);
          const final = end === totalBytes;
          const appended = await boundedRequest("sample.import.chunk", {
            import_token: importToken,
            offset,
            final,
            sidecar: {
              sidecar_bytes: bytes.byteLength,
              sidecar_sha256: await sha256Hex(bytes, crypto),
            },
          }, {sidecar: bytes, signal});
          if (
            !exactKeys(appended, ["received_bytes", "final"]) ||
            appended.received_bytes !== end ||
            appended.final !== final
          ) {
            throw protocolMismatch("Sample import chunk result is invalid");
          }
          offset = end;
          report(offset);
        }
        throwIfAborted(signal);
        const result = normalizeSampleCommit(await boundedRequest(
          "sample.import.commit",
          {import_token: importToken},
          {signal},
        ));
        committed = true;
        return result;
      } catch (error) {
        try {
          await abortOnce();
        } catch (abortError) {
          if (errorCode(abortError) === "HOST_PROTOCOL_MISMATCH") {
            fail(abortError);
          }
          // The primary failure or cancellation remains authoritative.
        }
        throw error;
      }
    });
  }

  async function setSamplePreview(flatSlot, playback) {
    const slot = flatSlotAddress(flatSlot);
    const encoded = wirePlayback(playback);
    if (closing || safetyReservation !== null) {
      return false;
    }
    return serializeRuntimeAction(async () => {
      const accepted = normalizeAccepted(await boundedRequest(
        "sample.preview.set",
        {slot, playback: encoded},
      ));
      if (accepted) {
        if (
          !activePreviewSlots.has(flatSlot) &&
          activePreviewSlots.size >= SAMPLE_PREVIEW_SLOT_LIMIT
        ) {
          throw typedError(
            "WEB_RUNTIME_RESOURCE_LIMIT",
            "Sample preview slot limit reached",
            {limit: SAMPLE_PREVIEW_SLOT_LIMIT},
          );
        }
        activePreviewSlots.add(flatSlot);
      }
      return accepted;
    });
  }

  async function clearSamplePreview(flatSlot) {
    const slot = flatSlotAddress(flatSlot);
    return serializeRuntimeAction(async () => {
      if (!activePreviewSlots.has(flatSlot)) {
        return false;
      }
      const accepted = normalizeAccepted(await boundedRequest(
        "sample.preview.clear",
        {slot},
      ));
      if (accepted) {
        activePreviewSlots.delete(flatSlot);
      }
      return accepted;
    });
  }

  async function release(flatSlot, source) {
    flatSlotAddress(flatSlot);
    if (!TRIGGER_SOURCES.has(source)) {
      throw new TypeError("Runtime release source is invalid");
    }
    return serializeRuntimeAction(async () => normalizeAccepted(
      await boundedRequest("trigger", {slot: flatSlot, kind: "release"}),
    ));
  }

  async function stopPad(flatSlot) {
    const slot = flatSlotAddress(flatSlot);
    return serializeRuntimeAction(async () => {
      const result = await boundedRequest("sample.stop", {slot});
      if (result?.scope !== "slot") {
        throw protocolMismatch("Sample stop scope is invalid");
      }
      return normalizeAccepted(result, ["accepted", "scope"]);
    });
  }

  async function stopAll() {
    return serializeRuntimeAction(() => stopAllInRuntimeLane());
  }

  function retryPrepare(patternId) {
    return serializeProjectAction(async () => {
      const value = await boundedRequest(
        "snapshot.retry",
        {pattern_id: patternId},
      );
      try {
        return normalizeSnapshotPublication(value, patternId);
      } catch (error) {
        if (errorCode(error) === "HOST_PROTOCOL_MISMATCH") {
          fail(error);
        }
        throw error;
      }
    });
  }

  async function listLocalProjects() {
    if (closing || !started) {
      throw typedError("HOST_STATE_INVALID", "Project discovery is unavailable");
    }
    const result = await recoverableQuery("project.list", {});
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
    return serializeProjectAction(async () => {
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
  }

  async function close() {
    if (terminalCleanupStarted) {
      await terminalCleanupPromise;
      return false;
    }
    if (closing || machine.state === "closed" || machine.state === "failed") {
      return false;
    }
    closing = true;
    invalidateProbe();
    const safety = beginSafetyCleanup("host.close");
    try {
      await safety.promise;
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
    const hasPointerIdentity = (event) => Number.isInteger(event?.pointerId);
    const inputAvailable = () =>
      !closing &&
      interruptionReservation === null &&
      safetyReservation === null &&
      (
        machine.state === "running" ||
        (
          machine.state === "recovering" &&
          recoveryEpoch?.probeWindow === true &&
          probeReservation === null
        )
      );
    const releaseInput = (flatSlot, source) => {
      if (suppressInputRelease) {
        return;
      }
      void release(flatSlot, source).catch(() => {});
    };
    const cancelInput = (flatSlot, source) => {
      void release(flatSlot, source).catch(() => {});
      clearPreviewsForCancellation(flatSlot);
    };
    pointerAdapter = createPointerAdapter({
      trigger,
      velocity: options.pointerVelocity ?? 100,
      now: monotonicNow,
      isAvailable: inputAvailable,
      onPressedChange: renderPressed,
      onRelease: releaseInput,
      onCancel: cancelInput,
    });
    keyboardAdapter = createKeyboardAdapter({
      trigger,
      mapping: options.keyboardMapping ?? DEFAULT_KEYBOARD_MAPPING,
      velocity: options.keyboardVelocity ?? 100,
      isAvailable: inputAvailable,
      onPressedChange: renderDiagnostics,
      onRelease: releaseInput,
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
      isAvailable: inputAvailable,
      onPressedChange: renderDiagnostics,
      onRelease: releaseInput,
    });

    for (const binding of padBindings) {
      const pad = binding.element;
      const flatSlot = flattenPadSlot(binding.slot);
      listen(pad, "pointerdown", (event) =>
        pointerAdapter.pointerDown(event, flatSlot));
      listen(pad, "mousedown", (event) =>
        pointerAdapter.mouseDown(event, flatSlot));
      listen(pad, "pointerup", (event) => {
        if (
          !pointerAdapter.releasePointer(event) &&
          !hasPointerIdentity(event)
        ) {
          pointerAdapter.pointerUp(event, flatSlot);
        }
      });
      listen(pad, "mouseup", (event) => {
        if (!pointerAdapter.releaseMouse(event)) {
          pointerAdapter.pointerUp(event, flatSlot);
        }
      });
      listen(pad, "pointercancel", (event) => {
        if (
          !pointerAdapter.pointerCancel(event) &&
          !hasPointerIdentity(event)
        ) {
          pointerAdapter.pointerUp(event, flatSlot);
        }
      });
    }
    listen(window, "pointerup", (event) => pointerAdapter.releasePointer(event));
    listen(window, "pointercancel", (event) => pointerAdapter.pointerCancel(event));
    listen(window, "mouseup", (event) => pointerAdapter.releaseMouse(event));
    listen(window, "keydown", (event) => {
      if (event?.code === "Escape") {
        clearPreviewsForCancellation();
        return;
      }
      keyboardAdapter.keyDown(event);
    });
    listen(window, "keyup", (event) => keyboardAdapter.keyUp(event));
  }

  function wireLifecycle() {
    listen(window, "blur", observeBlur);
    listen(window, "focus", observeFocus);
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
      const resourceLimits = manifestSource?.resourceLimits;
      const importedWavBytes = resourceLimits?.imported_wav_bytes;
      const ingestSourceBytes = resourceLimits?.ingest_source_bytes;
      const ingestDecodedFrames = resourceLimits?.ingest_decoded_frames;
      const ingestChannels = resourceLimits?.ingest_channels;
      if (!isPositiveInteger(importedWavBytes) ||
          !isPositiveInteger(ingestSourceBytes) ||
          !isPositiveInteger(ingestDecodedFrames) ||
          !isPositiveInteger(ingestChannels) || ingestChannels > 2) {
        throw typedError(
          "HOST_PROTOCOL_MISMATCH",
          "Manifest Sample ingest limits are invalid",
        );
      }
      verifiedSampleImportLimit = importedWavBytes;
      verifiedSampleIngestLimits = Object.freeze({
        sourceBytes: ingestSourceBytes,
        decodedFrames: ingestDecodedFrames,
        channels: ingestChannels,
        artifactBytes: importedWavBytes,
      });
      const capabilities =
        options.capabilities ??
        (preflight === runPreflight
          ? await defaultCapabilities(window, capabilityProbeTimeoutMs)
          : {});
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
      fail(error, "failed");
      return false;
    }
  }

  const session = Object.freeze({
    start,
    trigger,
    listLocalProjects,
    importProject,
    importAssignSample,
    openProject,
    inspectProject,
    beginSequence,
    disarmSequenceCapture,
    recordSequenceEvent,
    flushSequence,
    stopSequence,
    requestPatternSwitch,
    createPattern,
    updateSequenceSettings,
    querySequenceStatus,
    listSequenceRecovery,
    applySequenceRecovery,
    discardSequenceRecovery,
    inspectSample,
    querySampleQuota,
    sampleIngestLimits,
    queryWaveform,
    updatePad,
    resetPad,
    setSamplePreview,
    clearSamplePreview,
    reloadSnapshot,
    retryPrepare,
    activateAudio,
    suspendAudio,
    release,
    stopPad,
    stopAll,
    requestMidi: enableMidi,
    close,
    subscribeDiagnostics,
    subscribeHostState,
    subscribeRuntimeOutcome,
    subscribeSequenceBarBoundary,
    subscribeVoiceState,
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
