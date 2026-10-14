// Frozen legacy SDK response decoder from 96802c0f8764d04cbf3d3c913e82292a01284ac9.
// Source blob 0a3bbee4a184cce12cabccffa4b33e47a6dac657; module SHA256 b30148fbae472a13f4d0b03f5f63761e6ce372f4a267380f9d8090cb878fd7c5.
// Keep independent of the current protocol/SDK decoder for compatibility proof.
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const monotonicNow = () => 0;
function protocolMismatch(message) { return Object.assign(new Error(message), {code: "HOST_PROTOCOL_MISMATCH"}); }
function exactKeys(value, keys) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isUnsignedInteger(value, maximum = Number.MAX_SAFE_INTEGER) {
  return Number.isSafeInteger(value) && value >= 0 && value <= maximum;
}

  const PATTERN_TRANSPORT_PHASES = new Set([
    "idle",
    "preparing",
    "awaiting_audio",
    "flushing",
    "reconciling",
    "error",
  ]);

  function normalizePatternTransportStatus(value) {
    if (
      value === null ||
      typeof value !== "object" ||
      !exactKeys(value, [
        "engaged",
        "playing",
        "recording",
        "phase",
        "runtime_generation",
        "transport_epoch",
        "origin_frame",
        "runtime_frame",
        "command_id",
        "publication_pending",
        "error",
        "current_pattern_id",
        "pending_switch",
      ]) ||
      typeof value.engaged !== "boolean" ||
      typeof value.playing !== "boolean" ||
      typeof value.recording !== "boolean" ||
      !PATTERN_TRANSPORT_PHASES.has(value.phase) ||
      !isUnsignedInteger(value.runtime_generation) ||
      !isUnsignedInteger(value.transport_epoch) ||
      !isUnsignedInteger(value.origin_frame) ||
      !isUnsignedInteger(value.runtime_frame) ||
      (value.command_id !== null && !UUID_PATTERN.test(value.command_id)) ||
      typeof value.publication_pending !== "boolean" ||
      (value.current_pattern_id !== null &&
        !UUID_PATTERN.test(value.current_pattern_id)) ||
      (value.pending_switch !== null &&
        (typeof value.pending_switch !== "object" ||
          !exactKeys(value.pending_switch, ["pattern_id", "activation_frame"]) ||
          !UUID_PATTERN.test(value.pending_switch.pattern_id) ||
          !isUnsignedInteger(value.pending_switch.activation_frame))) ||
      (value.error !== null &&
        (typeof value.error !== "object" ||
          !exactKeys(value.error, ["code", "message", "details"]) ||
          typeof value.error.code !== "string" ||
          typeof value.error.message !== "string" ||
          value.error.details === null ||
          typeof value.error.details !== "object" ||
          Array.isArray(value.error.details)))
    ) {
      throw protocolMismatch("Pattern transport status is invalid");
    }
    return Object.freeze({
      engaged: value.engaged,
      playing: value.playing,
      recording: value.recording,
      phase: value.phase,
      runtimeGeneration: value.runtime_generation,
      transportEpoch: value.transport_epoch,
      originFrame: value.origin_frame,
      // The Engine's rendered frame when the Host read the status, and when
      // this Session received it, on the same monotonic clock a Host's
      // animation frames use.
      runtimeFrame: value.runtime_frame,
      observedAtMilliseconds: monotonicNow(),
      commandId: value.command_id,
      publicationPending: value.publication_pending,
      currentPatternId: value.current_pattern_id,
      pendingSwitch: value.pending_switch === null
        ? null
        : Object.freeze({
            patternId: value.pending_switch.pattern_id,
            activationFrame: value.pending_switch.activation_frame,
          }),
      error: value.error === null
        ? null
        : Object.freeze({
            code: value.error.code,
            message: value.error.message,
            details: Object.freeze({...value.error.details}),
          }),
    });
  }

export function decodeLegacyPatternTransportStatus(value) {
  return normalizePatternTransportStatus(value);
}
