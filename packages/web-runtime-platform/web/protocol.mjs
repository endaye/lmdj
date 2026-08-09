export const PROTOCOL_VERSION = 1;
export const MAX_ENVELOPE_BYTES = 65_536;
export const MAX_ASSET_BYTES = 1_048_576;
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
  "snapshot.reload",
  "audio.activate",
  "audio.suspend",
  "trigger",
  "take.begin",
  "take.stop",
  "take.commit",
  "take.recoverable.list",
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
  "capture.sealed",
]);

const OPERATION_SET = new Set(HOST_OPERATIONS);
const NOTIFICATION_SET = new Set(HOST_NOTIFICATIONS);
const SHORT_OPERATIONS = new Set([
  "host.status",
  "audio.activate",
  "audio.suspend",
  "trigger",
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
