const HOST_STATES = new Set([
  "cold",
  "preflight",
  "storage-ready",
  "core-ready",
  "audio-suspended",
  "running",
  "interrupted",
  "recovering",
  "restart-required",
  "failed",
  "closed",
]);

const ERROR_CODES = new Set([
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
const SAMPLE_OPERATIONS = new Set([
  "import",
  "replace",
  "update",
  "reset",
  "prepare",
]);
const SAMPLE_OPERATION_OUTCOMES = new Set([
  "committed",
  "conflicted",
  "failed",
  "cancelled",
]);
const SAMPLE_TRIGGER_MODES = [
  "one_shot",
  "gate",
  "loop_gate",
  "loop_toggle",
] as const;

export interface CreatorAcceptanceIdentity {
  productBuild: string;
  hostId: string;
  hostVersion: string;
  platformVersion: string;
  protocolVersion: number;
}

export interface CreatorAcceptanceCapabilities {
  secureContext: boolean;
  crossOriginIsolated: boolean;
  sharedArrayBuffer: boolean;
  webAssembly: boolean;
  audioWorklet: boolean;
  opfs: boolean;
  opfsSyncAccessHandle: boolean;
  opfsWritableReplace: boolean;
  webMidi: boolean;
}

export function serializeAcceptanceReport(report: unknown): string {
  return `${JSON.stringify(report, null, 2)}\n`;
}

export interface AcceptanceDiagnostics {
  state: string;
  error_code: string | null;
  trigger_admitted_count: number;
  trigger_outcome_count: number;
  trigger_rejected_count: number;
  [key: string]: unknown;
}

interface AcceptanceReportInput {
  identity: CreatorAcceptanceIdentity;
  capabilities: CreatorAcceptanceCapabilities;
  diagnostics: AcceptanceDiagnostics;
  bankCount: number;
  padCount: number;
  sampleEvidence?: CreatorAcceptanceSampleEvidence;
  sequenceEvidence?: CreatorAcceptanceSequenceEvidence;
}

interface CreatorAcceptanceSequenceEvidence {
  semanticState: string;
  sessionId: string | null;
  lastCommandId: string | null;
  projectRevision: number | null;
  expectedRevision: number | null;
  nextFlushSequence: number;
  pendingEventCount: number;
  effectiveRuntimeFrame: number | null;
  recoveryCandidateCount: number;
}

interface CreatorAcceptanceSampleEvidence {
  projectRevision: number | null;
  runtimeRevision: number | null;
  operationOutcomes: readonly Readonly<{
    operation: string;
    outcome: string;
    errorCode: string | null;
  }>[];
  triggerModeCoverage: readonly string[];
  [key: string]: unknown;
}

function requireIdentity(value: string, label: string): string {
  if (!/^[a-z0-9][a-z0-9.-]*$/.test(value)) {
    throw new TypeError(`${label} is invalid`);
  }
  return value;
}

function requireCount(value: number, label: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${label} is invalid`);
  }
  return value;
}

function requireRevision(value: number | null, label: string): number | null {
  if (value === null) return null;
  return requireCount(value, label);
}

function requireBoolean(value: boolean, label: string): boolean {
  if (typeof value !== "boolean") throw new TypeError(`${label} is invalid`);
  return value;
}

export function createAcceptanceReport({
  identity,
  capabilities,
  diagnostics,
  bankCount,
  padCount,
  sampleEvidence,
  sequenceEvidence,
}: AcceptanceReportInput) {
  if (!HOST_STATES.has(diagnostics.state)) {
    throw new TypeError("Host state is invalid");
  }
  if (diagnostics.error_code !== null && !ERROR_CODES.has(diagnostics.error_code)) {
    throw new TypeError("Host error code is invalid");
  }
  if (identity.protocolVersion !== 1) {
    throw new TypeError("Protocol version is invalid");
  }
  const sample = sampleEvidence === undefined
    ? undefined
    : normalizeSampleEvidence(sampleEvidence);
  const sequence = sequenceEvidence === undefined
    ? undefined
    : Object.freeze({
        semantic_state: requireSequenceState(sequenceEvidence.semanticState),
        session_id: sequenceEvidence.sessionId,
        last_command_id: sequenceEvidence.lastCommandId,
        project_revision: requireRevision(sequenceEvidence.projectRevision, "Project revision"),
        expected_revision: requireRevision(sequenceEvidence.expectedRevision, "Expected revision"),
        next_flush_sequence: requireCount(sequenceEvidence.nextFlushSequence, "Flush sequence"),
        pending_event_count: requireCount(sequenceEvidence.pendingEventCount, "Pending event count"),
        effective_runtime_frame: requireRevision(
          sequenceEvidence.effectiveRuntimeFrame,
          "Effective Runtime frame",
        ),
        recovery_candidate_count: requireCount(
          sequenceEvidence.recoveryCandidateCount,
          "Recovery candidate count",
        ),
      });
  return Object.freeze({
    contract: "lmdj.creator-web.acceptance.v1" as const,
    product_build: requireIdentity(identity.productBuild, "Product Build"),
    host_id: requireIdentity(identity.hostId, "Host ID"),
    host_version: requireIdentity(identity.hostVersion, "Host version"),
    platform_version: requireIdentity(identity.platformVersion, "Platform version"),
    protocol_version: identity.protocolVersion,
    capabilities: Object.freeze({
      secure_context: requireBoolean(capabilities.secureContext, "secureContext"),
      cross_origin_isolated: requireBoolean(
        capabilities.crossOriginIsolated,
        "crossOriginIsolated",
      ),
      shared_array_buffer: requireBoolean(
        capabilities.sharedArrayBuffer,
        "sharedArrayBuffer",
      ),
      web_assembly: requireBoolean(capabilities.webAssembly, "webAssembly"),
      audio_worklet: requireBoolean(capabilities.audioWorklet, "audioWorklet"),
      opfs: requireBoolean(capabilities.opfs, "opfs"),
      opfs_sync_access_handle: requireBoolean(
        capabilities.opfsSyncAccessHandle,
        "opfsSyncAccessHandle",
      ),
      opfs_writable_replace: requireBoolean(
        capabilities.opfsWritableReplace,
        "opfsWritableReplace",
      ),
      web_midi: requireBoolean(capabilities.webMidi, "webMidi"),
    }),
    state: diagnostics.state,
    bank_count: requireCount(bankCount, "Bank count"),
    pad_count: requireCount(padCount, "Pad count"),
    trigger_admitted_count: requireCount(
      diagnostics.trigger_admitted_count,
      "Trigger admission count",
    ),
    trigger_outcome_count: requireCount(
      diagnostics.trigger_outcome_count,
      "Trigger outcome count",
    ),
    trigger_rejected_count: requireCount(
      diagnostics.trigger_rejected_count,
      "Trigger rejection count",
    ),
    error_code: diagnostics.error_code,
    ...(sample === undefined ? {} : {sample}),
    ...(sequence === undefined ? {} : {sequence}),
    physical: Object.freeze({
      macos_safari_pointer: "deferred / unverified" as const,
      macos_chrome_pointer: "deferred / unverified" as const,
      macos_chrome_physical_midi: "deferred / unverified" as const,
      ipados_safari_touch: "deferred / unverified" as const,
      ipados_safari_lifecycle: "deferred / unverified" as const,
    }),
  });
}

function requireSequenceState(value: string): string {
  if (!["stopped", "recording", "switch-pending", "flushing", "recovery", "trim-overlay"]
    .includes(value)) throw new TypeError("Sequence state is invalid");
  return value;
}

function normalizeSampleEvidence(value: CreatorAcceptanceSampleEvidence) {
  const projectRevision = requireRevision(value.projectRevision, "Project revision");
  const runtimeRevision = requireRevision(value.runtimeRevision, "Runtime revision");
  if (projectRevision !== null && runtimeRevision !== null &&
    runtimeRevision > projectRevision) {
    throw new TypeError("Runtime revision is invalid");
  }
  if (!Array.isArray(value.operationOutcomes) || value.operationOutcomes.length > 32) {
    throw new TypeError("Sample operation outcomes are invalid");
  }
  const operationOutcomes = value.operationOutcomes.map((entry) => {
    if (entry === null || typeof entry !== "object" ||
      Object.keys(entry).length !== 3 ||
      !Object.hasOwn(entry, "operation") || !SAMPLE_OPERATIONS.has(entry.operation) ||
      !Object.hasOwn(entry, "outcome") || !SAMPLE_OPERATION_OUTCOMES.has(entry.outcome) ||
      !Object.hasOwn(entry, "errorCode") ||
      !(entry.errorCode === null || ERROR_CODES.has(entry.errorCode)) ||
      (entry.outcome === "failed") !== (entry.errorCode !== null)) {
      throw new TypeError("Sample operation outcome is invalid");
    }
    return Object.freeze({
      operation: entry.operation,
      outcome: entry.outcome,
      error_code: entry.errorCode,
    });
  });
  if (!Array.isArray(value.triggerModeCoverage) ||
    value.triggerModeCoverage.length > SAMPLE_TRIGGER_MODES.length ||
    value.triggerModeCoverage.some((mode) =>
      !SAMPLE_TRIGGER_MODES.includes(mode as typeof SAMPLE_TRIGGER_MODES[number]))) {
    throw new TypeError("Sample trigger-mode coverage is invalid");
  }
  const modes = new Set(value.triggerModeCoverage);
  if (modes.size !== value.triggerModeCoverage.length) {
    throw new TypeError("Sample trigger-mode coverage is invalid");
  }
  return Object.freeze({
    project_revision: projectRevision,
    runtime_revision: runtimeRevision,
    operation_outcomes: Object.freeze(operationOutcomes),
    trigger_mode_coverage: Object.freeze(
      SAMPLE_TRIGGER_MODES.filter((mode) => modes.has(mode)),
    ),
  });
}
