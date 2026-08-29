export const PROTOCOL_VERSION = 1;
export const MAX_ENVELOPE_BYTES = 65_536;
export const MAX_ASSET_BYTES = 1_048_576;
export const MAX_SAMPLE_IMPORT_BYTES = 68_157_440;
export const DEADLINES_MS = Object.freeze({
  short: 1_000,
  project: 30_000,
  close: 10_000,
});

export const HOST_OPERATIONS = Object.freeze([
  "host.status",
  "project.create",
  "project.open",
  "project.inspect",
  "project.list",
  "project.import.begin",
  "project.import.index",
  "project.import.entry",
  "project.import.commit",
  "project.import.abort",
  "asset.import",
  "pad.assign",
  "pattern.create",
  "snapshot.reload",
  "snapshot.retry",
  "sample.inspect",
  "sample.quota",
  "sample.waveform",
  "sample.import.begin",
  "sample.import.chunk",
  "sample.import.commit",
  "sample.import.abort",
  "sample.update_pad",
  "sample.reset_pad",
  "sample.preview.set",
  "sample.preview.clear",
  "sample.stop",
  "audio.activate",
  "audio.suspend",
  "trigger",
  "sequence.record.begin",
  "sequence.capture.disarm",
  "sequence.record.event",
  "sequence.record.flush",
  "sequence.record.stop",
  "sequence.record.switch-request",
  "sequence.record.status",
  "sequence.settings.update",
  "sequence.recovery.list",
  "sequence.recovery.apply",
  "sequence.recovery.discard",
  "host.close",
]);

export const HOST_NOTIFICATIONS = Object.freeze([
  "host.state_changed",
  "snapshot.published",
  "snapshot.rejected",
  "audio.interrupted",
  "audio.recovered",
  "midi.connected",
  "midi.disconnected",
  "runtime.warning",
  "runtime.trigger_outcomes",
  "runtime.voice_state",
  "sequence.bar_boundary",
  "capture.sealed",
]);

const OPERATION_SET = new Set(HOST_OPERATIONS);
const NOTIFICATION_SET = new Set(HOST_NOTIFICATIONS);
const SHORT_OPERATIONS = new Set([
  "host.status",
  "audio.activate",
  "audio.suspend",
  "trigger",
  "sample.preview.set",
  "sample.preview.clear",
  "sample.stop",
  "sequence.record.event",
  "sequence.record.status",
  "sequence.recovery.list",
]);
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

export class HostProtocolError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "HostProtocolError";
    this.code = code;
    this.details = details;
  }
}

function protocolError(message, details = {}) {
  return new HostProtocolError("HOST_PROTOCOL_MISMATCH", message, details);
}

function resourceLimitError(message, details = {}) {
  return new HostProtocolError("WEB_RUNTIME_RESOURCE_LIMIT", message, details);
}

function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function hasExactKeys(value, expected) {
  if (!isPlainObject(value)) {
    return false;
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return (
    actual.length === wanted.length &&
    actual.every((key, index) => key === wanted[index])
  );
}

function requireProtocolVersion(value) {
  if (value !== PROTOCOL_VERSION) {
    throw protocolError("Protocol version does not match the same-build Host");
  }
}

function requireRequestId(value) {
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) {
    throw protocolError("request_id must be a lowercase UUID");
  }
}

function requireOperation(value) {
  if (typeof value !== "string" || !OPERATION_SET.has(value)) {
    throw protocolError("Unsupported Host operation", { operation: value });
  }
}

function isUnsignedInteger(value, maximum = Number.MAX_SAFE_INTEGER) {
  return Number.isSafeInteger(value) && value >= 0 && value <= maximum;
}

function validSlot(value) {
  return (
    hasExactKeys(value, ["bank", "pad"]) &&
    isUnsignedInteger(value.bank, 3) &&
    isUnsignedInteger(value.pad, 15)
  );
}

function validPlayback(value) {
  return (
    hasExactKeys(value, [
      "trim_start_frame",
      "trim_end_frame",
      "trigger_mode",
      "gain_millidb",
      "muted",
    ]) &&
    isUnsignedInteger(value.trim_start_frame) &&
    (value.trim_end_frame === null ||
      (isUnsignedInteger(value.trim_end_frame) &&
        value.trim_end_frame > value.trim_start_frame)) &&
    ["one_shot", "gate", "loop_gate", "loop_toggle"].includes(
      value.trigger_mode,
    ) &&
    Number.isSafeInteger(value.gain_millidb) &&
    value.gain_millidb >= -60_000 &&
    value.gain_millidb <= 6_000 &&
    typeof value.muted === "boolean"
  );
}

function validSidecarDeclaration(value) {
  return (
    hasExactKeys(value, ["sidecar_bytes", "sidecar_sha256"]) &&
    isUnsignedInteger(value.sidecar_bytes, MAX_ASSET_BYTES) &&
    typeof value.sidecar_sha256 === "string" &&
    SHA256_PATTERN.test(value.sidecar_sha256)
  );
}

function requireSampleOperationPayload(operation, payload) {
  let valid = true;
  switch (operation) {
    case "sample.inspect":
    case "sample.quota":
      valid = hasExactKeys(payload, ["slot"]) && validSlot(payload.slot);
      break;
    case "sample.waveform":
      valid =
        hasExactKeys(payload, ["slot", "window"]) &&
        validSlot(payload.slot) &&
        hasExactKeys(payload.window, [
          "start_frame",
          "end_frame",
          "bucket_count",
        ]) &&
        isUnsignedInteger(payload.window.start_frame) &&
        isUnsignedInteger(payload.window.end_frame) &&
        payload.window.start_frame < payload.window.end_frame &&
        isUnsignedInteger(payload.window.bucket_count, 512) &&
        payload.window.bucket_count > 0;
      break;
    case "sample.import.begin":
      valid =
        (hasExactKeys(payload, [
          "import_token",
          "command_id",
          "expected_revision",
          "slot",
          "asset_id",
          "byte_length",
        ]) || hasExactKeys(payload, [
          "import_token",
          "command_id",
          "expected_revision",
          "sequence_session_id",
          "slot",
          "asset_id",
          "byte_length",
        ])) &&
        UUID_PATTERN.test(payload.import_token) &&
        UUID_PATTERN.test(payload.command_id) &&
        isUnsignedInteger(payload.expected_revision) &&
        validSlot(payload.slot) &&
        UUID_PATTERN.test(payload.asset_id) &&
        (!Object.hasOwn(payload, "sequence_session_id") ||
          UUID_PATTERN.test(payload.sequence_session_id)) &&
        isUnsignedInteger(payload.byte_length, MAX_SAMPLE_IMPORT_BYTES) &&
        payload.byte_length > 0;
      break;
    case "sample.import.chunk":
      valid =
        hasExactKeys(payload, [
          "import_token",
          "offset",
          "final",
          "sidecar",
        ]) &&
        UUID_PATTERN.test(payload.import_token) &&
        isUnsignedInteger(payload.offset) &&
        typeof payload.final === "boolean" &&
        validSidecarDeclaration(payload.sidecar);
      break;
    case "sample.import.commit":
    case "sample.import.abort":
      valid =
        hasExactKeys(payload, ["import_token"]) &&
        UUID_PATTERN.test(payload.import_token);
      break;
    case "sample.update_pad":
      valid =
        hasExactKeys(payload, [
          "command_id",
          "expected_revision",
          "slot",
          "playback",
        ]) &&
        UUID_PATTERN.test(payload.command_id) &&
        isUnsignedInteger(payload.expected_revision) &&
        validSlot(payload.slot) &&
        validPlayback(payload.playback);
      break;
    case "sample.reset_pad":
      valid =
        hasExactKeys(payload, [
          "command_id",
          "expected_revision",
          "slot",
        ]) &&
        UUID_PATTERN.test(payload.command_id) &&
        isUnsignedInteger(payload.expected_revision) &&
        validSlot(payload.slot);
      break;
    case "pattern.create":
      valid =
        hasExactKeys(payload, [
          "command_id",
          "expected_revision",
          "pattern_id",
          "bars",
        ]) &&
        UUID_PATTERN.test(payload.command_id) &&
        isUnsignedInteger(payload.expected_revision) &&
        UUID_PATTERN.test(payload.pattern_id) &&
        [1, 2, 4, 8].includes(payload.bars);
      break;
    case "sample.preview.set":
      valid =
        hasExactKeys(payload, ["slot", "playback"]) &&
        validSlot(payload.slot) &&
        validPlayback(payload.playback);
      break;
    case "sample.preview.clear":
      valid = hasExactKeys(payload, ["slot"]) && validSlot(payload.slot);
      break;
    case "sample.stop":
      valid =
        hasExactKeys(payload, []) ||
        (hasExactKeys(payload, ["slot"]) && validSlot(payload.slot));
      break;
    case "snapshot.retry":
      valid =
        hasExactKeys(payload, ["pattern_id"]) &&
        UUID_PATTERN.test(payload.pattern_id);
      break;
    case "trigger":
      valid =
        (hasExactKeys(payload, ["slot", "velocity"]) &&
          isUnsignedInteger(payload.slot, 63) &&
          isUnsignedInteger(payload.velocity, 127) &&
          payload.velocity > 0) ||
        (hasExactKeys(payload, ["slot", "kind"]) &&
          isUnsignedInteger(payload.slot, 63) &&
          payload.kind === "release");
      break;
    case "sequence.record.begin":
      valid =
        (hasExactKeys(payload, [
          "session_id",
          "pattern_id",
          "expected_revision",
        ]) || hasExactKeys(payload, [
          "session_id",
          "pattern_id",
          "expected_revision",
          "armed_capture_slot",
        ])) &&
        UUID_PATTERN.test(payload.session_id) &&
        UUID_PATTERN.test(payload.pattern_id) &&
        isUnsignedInteger(payload.expected_revision) &&
        (!Object.hasOwn(payload, "armed_capture_slot") ||
          payload.armed_capture_slot === null || validSlot(payload.armed_capture_slot));
      break;
    case "sequence.capture.disarm":
      valid =
        hasExactKeys(payload, ["session_id", "slot"]) &&
        UUID_PATTERN.test(payload.session_id) &&
        validSlot(payload.slot);
      break;
    case "sequence.record.event":
      valid =
        hasExactKeys(payload, ["session_id", "event"]) &&
        UUID_PATTERN.test(payload.session_id) &&
        hasExactKeys(payload.event, ["slot", "velocity", "pressed"]) &&
        validSlot(payload.event.slot) &&
        isUnsignedInteger(payload.event.velocity, 127) &&
        typeof payload.event.pressed === "boolean" &&
        (payload.event.pressed
          ? payload.event.velocity > 0
          : payload.event.velocity === 0);
      break;
    case "sequence.record.flush":
    case "sequence.record.stop":
      valid =
        hasExactKeys(payload, ["session_id", "command_id"]) &&
        UUID_PATTERN.test(payload.session_id) &&
        UUID_PATTERN.test(payload.command_id);
      break;
    case "sequence.record.switch-request":
      valid =
        hasExactKeys(payload, ["session_id", "next_pattern_id"]) &&
        UUID_PATTERN.test(payload.session_id) &&
        UUID_PATTERN.test(payload.next_pattern_id);
      break;
    case "sequence.settings.update":
      valid =
        hasExactKeys(payload, [
          "command_id",
          "expected_revision",
          "session_id",
          "bpm",
          "quantize_enabled",
          "swing_percent",
        ]) &&
        UUID_PATTERN.test(payload.command_id) &&
        isUnsignedInteger(payload.expected_revision) &&
        (payload.session_id === null || UUID_PATTERN.test(payload.session_id)) &&
        (payload.bpm === null ||
          (isUnsignedInteger(payload.bpm, 240) && payload.bpm >= 40)) &&
        (payload.quantize_enabled === null ||
          typeof payload.quantize_enabled === "boolean") &&
        (payload.swing_percent === null ||
          (isUnsignedInteger(payload.swing_percent, 75) &&
            payload.swing_percent >= 50)) &&
        (payload.bpm !== null || payload.quantize_enabled !== null ||
          payload.swing_percent !== null);
      break;
    case "sequence.record.status":
    case "sequence.recovery.list":
      valid =
        hasExactKeys(payload, []) ||
        (hasExactKeys(payload, ["project_id"]) &&
          UUID_PATTERN.test(payload.project_id));
      break;
    case "sequence.recovery.apply":
      valid =
        hasExactKeys(payload, ["session_id", "destination_pattern_id"]) &&
        UUID_PATTERN.test(payload.session_id) &&
        (payload.destination_pattern_id === null ||
          UUID_PATTERN.test(payload.destination_pattern_id));
      break;
    case "sequence.recovery.discard":
      valid =
        hasExactKeys(payload, ["session_id"]) &&
        UUID_PATTERN.test(payload.session_id);
      break;
    default:
      return;
  }
  if (!valid) {
    throw protocolError("Host operation payload is invalid", {operation});
  }
}

function asBytes(value) {
  if (value instanceof ArrayBuffer) {
    return new Uint8Array(value);
  }
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  }
  throw protocolError("Protocol input must be a byte buffer");
}

function enforceEnvelopeByteLimit(envelope) {
  let json;
  try {
    json = JSON.stringify(envelope);
  } catch {
    throw protocolError("Protocol envelope is not JSON serializable");
  }
  if (typeof json !== "string") {
    throw protocolError("Protocol envelope is not a JSON value");
  }
  const byteLength = new TextEncoder().encode(json).byteLength;
  if (byteLength > MAX_ENVELOPE_BYTES) {
    throw resourceLimitError("JSON envelope exceeds the Web Host limit", {
      limit: MAX_ENVELOPE_BYTES,
      actual: byteLength,
    });
  }
}

function validateRequestObject(
  envelope,
  { seenRequestIds, allowOperation } = {},
) {
  if (
    !hasExactKeys(envelope, [
      "protocol_version",
      "request_id",
      "operation",
      "payload",
    ])
  ) {
    throw protocolError("Request envelope has unknown or missing fields");
  }
  requireProtocolVersion(envelope.protocol_version);
  requireRequestId(envelope.request_id);
  requireOperation(envelope.operation);
  if (!isPlainObject(envelope.payload)) {
    throw protocolError("Request payload must be an object");
  }
  requireSampleOperationPayload(envelope.operation, envelope.payload);
  if (seenRequestIds?.has(envelope.request_id)) {
    throw protocolError("Duplicate request_id", {
      request_id: envelope.request_id,
    });
  }
  if (
    allowOperation !== undefined &&
    (typeof allowOperation !== "function" ||
      allowOperation(envelope.operation, envelope.payload) !== true)
  ) {
    throw new HostProtocolError(
      "HOST_STATE_INVALID",
      "Operation is not allowed in the current Host state",
      { operation: envelope.operation },
    );
  }
  seenRequestIds?.add(envelope.request_id);
  return envelope;
}

export function decodeRequestEnvelope(bytes, options = {}) {
  const input = asBytes(bytes);
  if (input.byteLength > MAX_ENVELOPE_BYTES) {
    throw resourceLimitError("JSON envelope exceeds the Web Host limit", {
      limit: MAX_ENVELOPE_BYTES,
      actual: input.byteLength,
    });
  }

  let json;
  try {
    json = new TextDecoder("utf-8", { fatal: true }).decode(input);
  } catch {
    throw protocolError("Request envelope is not strict UTF-8");
  }

  let envelope;
  try {
    envelope = JSON.parse(json);
  } catch {
    throw protocolError("Request envelope is not valid JSON");
  }
  return validateRequestObject(envelope, options);
}

export function createRequestEnvelope({ operation, payload, crypto }) {
  if (typeof crypto?.randomUUID !== "function") {
    throw protocolError("A request UUID source must be injected");
  }
  const envelope = {
    protocol_version: PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    operation,
    payload,
  };
  return validateRequestObject(envelope);
}

export function validateResponseEnvelope(envelope) {
  enforceEnvelopeByteLimit(envelope);
  if (!isPlainObject(envelope) || typeof envelope.ok !== "boolean") {
    throw protocolError("Response envelope is invalid");
  }
  const expectedKeys = envelope.ok
    ? ["protocol_version", "request_id", "ok", "result"]
    : ["protocol_version", "request_id", "ok", "error"];
  if (!hasExactKeys(envelope, expectedKeys)) {
    throw protocolError("Response envelope has unknown or missing fields");
  }
  requireProtocolVersion(envelope.protocol_version);
  requireRequestId(envelope.request_id);
  if (!envelope.ok) {
    if (!hasExactKeys(envelope.error, ["code", "message", "details"])) {
      throw protocolError("Response error has unknown or missing fields");
    }
    if (
      typeof envelope.error.code !== "string" ||
      typeof envelope.error.message !== "string" ||
      !isPlainObject(envelope.error.details)
    ) {
      throw protocolError("Response error fields are invalid");
    }
  }
  return envelope;
}

export function validateNotificationEnvelope(envelope) {
  enforceEnvelopeByteLimit(envelope);
  if (
    !hasExactKeys(envelope, ["protocol_version", "event", "payload"]) ||
    typeof envelope.event !== "string" ||
    !NOTIFICATION_SET.has(envelope.event) ||
    !isPlainObject(envelope.payload)
  ) {
    throw protocolError("Notification envelope is invalid or unsupported");
  }
  requireProtocolVersion(envelope.protocol_version);
  return envelope;
}

export function deadlineForOperation(operation) {
  requireOperation(operation);
  if (operation === "host.close") {
    return DEADLINES_MS.close;
  }
  if (SHORT_OPERATIONS.has(operation)) {
    return DEADLINES_MS.short;
  }
  return DEADLINES_MS.project;
}

export async function verifyAssetSidecar(declaration, sidecar, { crypto } = {}) {
  if (
    !hasExactKeys(declaration, ["sidecar_bytes", "sidecar_sha256"]) ||
    !Number.isSafeInteger(declaration.sidecar_bytes) ||
    declaration.sidecar_bytes < 0 ||
    typeof declaration.sidecar_sha256 !== "string" ||
    !SHA256_PATTERN.test(declaration.sidecar_sha256)
  ) {
    throw protocolError("Asset sidecar declaration is invalid");
  }
  const bytes = asBytes(sidecar);
  if (
    bytes.byteLength > MAX_ASSET_BYTES ||
    declaration.sidecar_bytes > MAX_ASSET_BYTES
  ) {
    throw resourceLimitError("Asset sidecar exceeds the Web Host import limit", {
      limit: MAX_ASSET_BYTES,
      actual: bytes.byteLength,
    });
  }
  if (declaration.sidecar_bytes !== bytes.byteLength) {
    throw protocolError("Asset sidecar length does not match its declaration");
  }
  if (typeof crypto?.subtle?.digest !== "function") {
    throw protocolError("A SHA-256 implementation must be injected");
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const actualSha256 = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  if (actualSha256 !== declaration.sidecar_sha256) {
    throw protocolError("Asset sidecar SHA-256 does not match its declaration");
  }
  return true;
}

export function createProtocolTransport({
  send,
  terminate,
  now,
  setTimer,
  clearTimer,
}) {
  if (
    typeof send !== "function" ||
    typeof terminate !== "function" ||
    typeof now !== "function" ||
    typeof setTimer !== "function" ||
    typeof clearTimer !== "function"
  ) {
    throw new TypeError("Transport dependencies must be injected functions");
  }

  const pending = new Map();
  const activeRequestIds = new Set();
  let isTerminated = false;

  function failClosed(failure) {
    if (isTerminated) {
      return;
    }
    isTerminated = true;
    const entries = [...pending.values()];
    pending.clear();
    activeRequestIds.clear();
    for (const entry of entries) {
      if (entry.timer !== null) {
        clearTimer(entry.timer);
      }
      entry.reject(failure);
    }
    try {
      terminate();
    } catch {
      // Internal state is already failed closed; transport cleanup cannot reopen it.
    }
  }

  function armTimer(requestId, delay) {
    return setTimer(() => {
      const entry = pending.get(requestId);
      if (!entry || isTerminated) {
        return;
      }
      const remaining = entry.deadlineAt - now();
      if (remaining > 0) {
        entry.timer = armTimer(requestId, remaining);
        return;
      }
      failClosed(
        new HostProtocolError(
          "HOST_TIMEOUT",
          "Host request deadline expired",
          { request_id: requestId },
        ),
      );
    }, delay);
  }

  function request(envelope, sidecar) {
    if (isTerminated) {
      return Promise.reject(
        new HostProtocolError("HOST_TIMEOUT", "Host transport is terminated"),
      );
    }
    const bytes = new TextEncoder().encode(JSON.stringify(envelope));
    const validated = decodeRequestEnvelope(bytes, {
      seenRequestIds: activeRequestIds,
    });
    const deadlineAt = now() + deadlineForOperation(validated.operation);
    let resolveRequest;
    let rejectRequest;
    const promise = new Promise((resolve, reject) => {
      resolveRequest = resolve;
      rejectRequest = reject;
    });
    const entry = {
      resolve: resolveRequest,
      reject: rejectRequest,
      deadlineAt,
      timer: null,
    };
    pending.set(validated.request_id, entry);
    try {
      entry.timer = armTimer(
        validated.request_id,
        deadlineForOperation(validated.operation),
      );
      send(validated, sidecar);
    } catch {
      failClosed(protocolError("Host transport dispatch failed"));
    }
    return promise;
  }

  function receive(envelope) {
    if (isTerminated) {
      return false;
    }
    let validated;
    try {
      validated = validateResponseEnvelope(envelope);
    } catch (error) {
      failClosed(
        error instanceof HostProtocolError
          ? error
          : protocolError("Host response validation failed"),
      );
      return false;
    }
    const entry = pending.get(validated.request_id);
    if (!entry) {
      failClosed(
        protocolError("Response request_id does not match a pending request", {
          request_id: validated.request_id,
        }),
      );
      return false;
    }
    if (now() >= entry.deadlineAt) {
      failClosed(
        new HostProtocolError(
          "HOST_TIMEOUT",
          "Host request deadline expired",
          { request_id: validated.request_id },
        ),
      );
      return false;
    }
    clearTimer(entry.timer);
    pending.delete(validated.request_id);
    activeRequestIds.delete(validated.request_id);
    if (validated.ok) {
      entry.resolve(validated.result);
    } else {
      entry.reject(
        new HostProtocolError(
          validated.error.code,
          validated.error.message,
          validated.error.details,
        ),
      );
    }
    return true;
  }

  return Object.freeze({
    request,
    receive,
    get terminated() {
      return isTerminated;
    },
    get pendingCount() {
      return pending.size;
    },
    get activeRequestIdCount() {
      return activeRequestIds.size;
    },
  });
}
