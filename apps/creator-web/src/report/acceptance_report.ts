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
    physical: Object.freeze({
      macos_safari_pointer: "deferred / unverified" as const,
      macos_chrome_pointer: "deferred / unverified" as const,
      macos_chrome_physical_midi: "deferred / unverified" as const,
      ipados_safari_touch: "deferred / unverified" as const,
      ipados_safari_lifecycle: "deferred / unverified" as const,
    }),
  });
}
