import type {
  PadPlayback,
  RuntimeVoiceState,
  SampleCommit,
  SampleInspect,
  SampleMetadata,
  SampleSnapshotError,
  SampleTriggerMode,
  SnapshotPublication,
  WaveformEnvelope,
  WaveformWindow,
} from "../runtime/runtime_types";

export interface SampleViewport {
  sourceFrames: number;
  startFrame: number;
  endFrame: number;
}

export interface SampleWaveformRequestIdentity {
  readonly slot: number;
  readonly window: Readonly<WaveformWindow>;
  readonly waveformCacheIdentity: string;
}

export interface SampleDraft {
  readonly baseRevision: number;
  readonly saved: Readonly<PadPlayback>;
  readonly proposed: Readonly<PadPlayback>;
  readonly dirty: boolean;
}

export type SamplePendingKind =
  | "import"
  | "replace"
  | "reset"
  | "update"
  | "retry-prepare";

export interface SamplePendingAction {
  readonly kind: SamplePendingKind;
  readonly slot: number;
  readonly expectedRevision: number;
}

export interface SampleLastError {
  readonly code: string;
  readonly message: string;
  readonly retryPrepare: boolean;
  readonly details?: Readonly<Record<string, unknown>>;
}

export interface SampleVoiceRender {
  readonly sequence: number;
  readonly slot: number;
  readonly state: "started";
  readonly runtimeFrame: number;
  readonly sourceFrame: number;
  readonly sampleRate: number | null;
  readonly trimStartFrame: number | null;
  readonly trimEndFrame: number | null;
}

export interface SamplePlayheadRender {
  readonly sequence: number;
  readonly slot: number;
  readonly runtimeFrame: number;
  readonly sourceFrame: number;
  readonly sampleRate: number | null;
  readonly trimStartFrame: number | null;
  readonly trimEndFrame: number | null;
}

export interface SampleState {
  readonly selectedSlot: number | null;
  readonly inspect: Readonly<SampleInspect> | null;
  readonly waveform: Readonly<WaveformEnvelope> | null;
  readonly viewport: Readonly<SampleViewport> | null;
  readonly draft: Readonly<SampleDraft> | null;
  readonly auditionPlayback: Readonly<PadPlayback> | null;
  readonly pendingAction: Readonly<SamplePendingAction> | null;
  readonly voices: readonly Readonly<SampleVoiceRender>[];
  readonly playhead: Readonly<SamplePlayheadRender> | null;
  readonly lastError: Readonly<SampleLastError> | null;
  readonly savedRevision: number | null;
  readonly runtimeRevision: number | null;
}

export type SampleStateAction =
  | Readonly<{type: "slot-selected"; slot: number}>
  | Readonly<{type: "inspect-stored"; inspect: unknown}>
  | Readonly<{
      type: "waveform-stored";
      envelope: unknown;
      request: SampleWaveformRequestIdentity;
    }>
  | Readonly<{type: "draft-began"}>
  | Readonly<{type: "draft-updated"; changes: Partial<PadPlayback>}>
  | Readonly<{type: "draft-cancelled"}>
  | Readonly<{type: "preview-applied"; playback: unknown}>
  | Readonly<{type: "preview-cleared"}>
  | Readonly<{type: "pending-began"; pending: unknown}>
  | Readonly<{
      type: "mutation-committed";
      pending: unknown;
      inspect: unknown;
      commit: unknown;
    }>
  | Readonly<{type: "mutation-conflicted"; pending: unknown; inspect: unknown}>
  | Readonly<{type: "retry-published"; pending: unknown; publication: unknown}>
  | Readonly<{type: "voice-changed"; event: unknown}>
  | Readonly<{type: "preview-failed"}>
  | Readonly<{type: "operation-failed"; pending: unknown; error: unknown}>
  | Readonly<{type: "operation-cancelled"; pending: unknown}>
  | Readonly<{type: "error-cleared"}>;

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const CACHE_IDENTITY_PATTERN =
  /^([0-9a-f]{64})\/1\/max-abs-mirror\/([1-9][0-9]*)$/;
const TRIGGER_MODES = new Set<SampleTriggerMode>([
  "one_shot",
  "gate",
  "loop_gate",
  "loop_toggle",
]);
const PENDING_KINDS = new Set<SamplePendingKind>([
  "import",
  "replace",
  "reset",
  "update",
  "retry-prepare",
]);
const MUTATION_PENDING_KINDS = new Set<SamplePendingKind>([
  "import",
  "replace",
  "reset",
  "update",
]);
const RETRY_PENDING_KINDS = new Set<SamplePendingKind>(["retry-prepare"]);
const ALLOWED_ERROR_CODES = new Set([
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
const VOICE_STATES = new Set(["started", "stopped", "completed"]);
const MAX_SAFE_JSON_DEPTH = 8;
const MAX_SAFE_JSON_NODES = 4_096;
const MAX_SAFE_JSON_COLLECTION = 512;
const MAX_SAFE_JSON_STRING = 4_096;
const FORBIDDEN_PRIVATE_KEYS = new Set([
  "project",
  "projectPath",
  "project_path",
  "bundle",
  "checkpoint",
  "path",
  "fileName",
  "filename",
  "file_name",
  "bytes",
  "sampleBytes",
  "sample_bytes",
  "rawBytes",
  "raw_bytes",
  "storageHandle",
  "storage_handle",
  "opfsHandle",
  "opfs_handle",
  "waveformCache",
]);
const SAFE_PROJECT_KEYS = new Set([
  "projectid",
  "projectrevision",
  "expectedprojectrevision",
  "actualprojectrevision",
  "currentprojectrevision",
]);
const PRIVATE_KEY_TERMS = [
  "path",
  "filename",
  "bytes",
  "project",
  "bundle",
  "checkpoint",
  "storage",
  "opfs",
] as const;
const SNAPSHOT_RESOURCE_TOKENS = new Set([
  "artifact_bytes",
  "decoded_frames_per_pad",
  "prepared_bank_bytes",
  "live_bank_bytes",
]);
const SNAPSHOT_STORAGE_CONDITIONS = new Set([
  "project_busy",
  "already_exists",
  "atomic_publish_unsupported",
]);
const SNAPSHOT_TRANSFER_CONDITIONS = new Set(["resource_limit"]);
const SAMPLE_PUBLIC_ERROR_MESSAGES: Readonly<Record<string, string>> =
  Object.freeze({
    INVALID_ARGUMENT: "Sample request is invalid",
    NOT_FOUND: "Sample resource was not found",
    REVISION_CONFLICT: "Project changed; review and try again",
    DUPLICATE_ID: "Sample identity already exists",
    UNSUPPORTED_AUDIO: "Sample audio is unsupported",
    MISSING_ASSET: "Sample Artifact is unavailable",
    INVALID_PROJECT: "Project could not be validated",
    COOK_FAILED: "Sample runtime preparation failed",
    PROVIDER_NOT_FOUND: "Sample operation failed",
    PROVIDER_FAILED: "Sample operation failed",
    PERMISSION_DENIED: "Sample operation is not permitted",
    IO_ERROR: "Sample storage operation failed",
    INTERNAL_ERROR: "Sample operation failed",
    UNSUPPORTED_WEB_RUNTIME: "Sample operation is unavailable in this Web Runtime",
    PROJECT_BUSY: "Project is already open for writing",
    WEB_RUNTIME_RESOURCE_LIMIT: "Sample exceeds the Web Runtime resource limit",
    HOST_STATE_INVALID: "Sample operation is unavailable",
    HOST_TIMEOUT: "Sample operation timed out",
    HOST_RESTART_REQUIRED: "Restart the Sample runtime and try again",
    HOST_PROTOCOL_MISMATCH: "Sample Host response was invalid",
  });
const PRIVATE_HOST_MESSAGE_PATTERN = new RegExp([
  String.raw`\bopfs\b`,
  "file://",
  String.raw`(?:^|[\s"'(])/(?:[^\s]*)`,
  String.raw`\b[a-z]:\\`,
  String.raw`[a-z0-9._-]+\.(?:wav|wave|aiff?|flac|mp3|ogg|lmdj)\b`,
].join("|"), "i");

export const SAMPLE_VOICE_RENDER_LIMIT = 64;

const DEFAULT_PLAYBACK: Readonly<PadPlayback> = Object.freeze({
  trimStartFrame: 0,
  trimEndFrame: null,
  triggerMode: "one_shot",
  gainMillidb: 0,
  muted: false,
});

export const initialSampleState: SampleState = Object.freeze({
  selectedSlot: null,
  inspect: null,
  waveform: null,
  viewport: null,
  draft: null,
  auditionPlayback: null,
  pendingAction: null,
  voices: Object.freeze([]),
  playhead: null,
  lastError: null,
  savedRevision: null,
  runtimeRevision: null,
});

export function preparedSampleState(projectRevision: number): SampleState {
  if (!unsignedInteger(projectRevision)) {
    throw new TypeError("Prepared Project revision is invalid");
  }
  return Object.freeze({
    ...initialSampleState,
    savedRevision: projectRevision,
    runtimeRevision: projectRevision,
  });
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function plainRecord(value: unknown): value is Record<string, unknown> {
  if (!record(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function exactKeys(
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> {
  return record(value) && Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key));
}

function unsignedInteger(value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0 &&
    (value as number) <= maximum;
}

function positiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0;
}

function slotNumber(value: unknown): value is number {
  return unsignedInteger(value, 63);
}

function assertPrivacySafeValue(
  value: unknown,
  depth: number,
  budget: {nodes: number},
): void {
  budget.nodes += 1;
  if (budget.nodes > MAX_SAFE_JSON_NODES || depth > MAX_SAFE_JSON_DEPTH) {
    throw new TypeError("Sample state input exceeds safe JSON bounds");
  }
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (value.length > MAX_SAFE_JSON_STRING) {
      throw new TypeError("Sample state input exceeds safe JSON bounds");
    }
    return;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new TypeError("Sample state input contains unsafe JSON data");
    }
    return;
  }
  if (typeof value !== "object" || ArrayBuffer.isView(value) ||
    value instanceof ArrayBuffer ||
    (typeof SharedArrayBuffer !== "undefined" &&
      value instanceof SharedArrayBuffer)) {
    throw new TypeError("Sample state input contains private data");
  }
  if (Array.isArray(value)) {
    if (value.length > MAX_SAFE_JSON_COLLECTION) {
      throw new TypeError("Sample state input exceeds safe JSON bounds");
    }
    for (const item of value) {
      assertPrivacySafeValue(item, depth + 1, budget);
    }
    return;
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new TypeError("Sample state input contains private data");
  }
  const stateInput = value as Record<string, unknown>;
  if ((stateInput.contract === "lmdj.project.v1" ||
      stateInput.contract === "lmdj.project.v2") &&
      Object.hasOwn(value, "banks") && Object.hasOwn(value, "assets")) {
    throw new TypeError("Sample state input contains private data");
  }
  const entries = Object.entries(value);
  if (entries.length > MAX_SAFE_JSON_COLLECTION) {
    throw new TypeError("Sample state input exceeds safe JSON bounds");
  }
  for (const [key, item] of entries) {
    const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, "");
    const privateKey = FORBIDDEN_PRIVATE_KEYS.has(key) ||
      (!SAFE_PROJECT_KEYS.has(normalizedKey) &&
        PRIVATE_KEY_TERMS.some((term) => normalizedKey.includes(term)));
    if (key.length > 128 || privateKey) {
      throw new TypeError("Sample state input contains private data");
    }
    assertPrivacySafeValue(item, depth + 1, budget);
  }
}

function assertPrivacySafe(value: unknown): void {
  assertPrivacySafeValue(value, 0, {nodes: 0});
}

function freezePlayback(playback: PadPlayback): Readonly<PadPlayback> {
  return Object.freeze({...playback});
}

function playbackEquals(left: PadPlayback, right: PadPlayback): boolean {
  return left.trimStartFrame === right.trimStartFrame &&
    left.trimEndFrame === right.trimEndFrame &&
    left.triggerMode === right.triggerMode &&
    left.gainMillidb === right.gainMillidb &&
    left.muted === right.muted;
}

function validatePlayback(value: unknown): Readonly<PadPlayback> {
  assertPrivacySafe(value);
  if (!exactKeys(value, [
    "trimStartFrame",
    "trimEndFrame",
    "triggerMode",
    "gainMillidb",
    "muted",
  ]) ||
    !unsignedInteger(value.trimStartFrame) ||
    !(value.trimEndFrame === null ||
      (unsignedInteger(value.trimEndFrame) &&
        value.trimEndFrame > value.trimStartFrame)) ||
    typeof value.triggerMode !== "string" ||
    !TRIGGER_MODES.has(value.triggerMode as SampleTriggerMode) ||
    !Number.isSafeInteger(value.gainMillidb) ||
    (value.gainMillidb as number) < -60_000 ||
    (value.gainMillidb as number) > 6_000 ||
    typeof value.muted !== "boolean") {
    throw new TypeError("Sample playback is invalid");
  }
  return freezePlayback({
    trimStartFrame: value.trimStartFrame,
    trimEndFrame: value.trimEndFrame as number | null,
    triggerMode: value.triggerMode as SampleTriggerMode,
    gainMillidb: value.gainMillidb as number,
    muted: value.muted,
  });
}

function validateMetadata(value: unknown): Readonly<SampleMetadata> {
  if (!exactKeys(value, ["sampleRate", "channels", "sourceFrames"]) ||
    (value.sampleRate !== 44_100 && value.sampleRate !== 48_000) ||
    (value.channels !== 1 && value.channels !== 2) ||
    !positiveInteger(value.sourceFrames)) {
    throw new TypeError("Sample metadata is invalid");
  }
  return Object.freeze({
    sampleRate: value.sampleRate,
    channels: value.channels,
    sourceFrames: value.sourceFrames,
  });
}

function validateCacheIdentity(value: unknown, sourceFrames: number): string {
  if (typeof value !== "string" || value.length > 512) {
    throw new TypeError("Sample waveform cache identity is invalid");
  }
  const match = CACHE_IDENTITY_PATTERN.exec(value);
  const framesPerBucket = match === null ? NaN : Number(match[2]);
  const expected = Math.ceil(sourceFrames / Math.min(sourceFrames, 512));
  if (match === null || !positiveInteger(framesPerBucket) || framesPerBucket !== expected) {
    throw new TypeError("Sample waveform cache identity is invalid");
  }
  return value;
}

function validateInspect(value: unknown): Readonly<SampleInspect> {
  assertPrivacySafe(value);
  if (!exactKeys(value, [
    "projectRevision",
    "slot",
    "assetId",
    "playback",
    "metadata",
    "waveformCacheIdentity",
  ]) ||
    !unsignedInteger(value.projectRevision) ||
    !slotNumber(value.slot) ||
    !(value.assetId === null ||
      (typeof value.assetId === "string" && UUID_PATTERN.test(value.assetId)))) {
    throw new TypeError("Sample inspect result is invalid");
  }
  const playback = validatePlayback(value.playback);
  const metadata = value.metadata === null ? null : validateMetadata(value.metadata);
  if ((value.assetId === null &&
      (metadata !== null || value.waveformCacheIdentity !== null)) ||
    (value.assetId !== null &&
      (metadata === null || value.waveformCacheIdentity === null))) {
    throw new TypeError("Sample inspect Asset truth is invalid");
  }
  if (metadata !== null) {
    const resolvedEnd = playback.trimEndFrame ?? metadata.sourceFrames;
    if (playback.trimStartFrame >= resolvedEnd || resolvedEnd > metadata.sourceFrames) {
      throw new TypeError("Sample inspect playback bounds are invalid");
    }
  }
  return Object.freeze({
    projectRevision: value.projectRevision,
    slot: value.slot,
    assetId: value.assetId,
    playback,
    metadata,
    waveformCacheIdentity: metadata === null
      ? null
      : validateCacheIdentity(value.waveformCacheIdentity, metadata.sourceFrames),
  });
}

function validateViewport(value: unknown): Readonly<SampleViewport> {
  if (!exactKeys(value, ["sourceFrames", "startFrame", "endFrame"]) ||
    !positiveInteger(value.sourceFrames) ||
    !unsignedInteger(value.startFrame) ||
    !unsignedInteger(value.endFrame) ||
    value.startFrame >= value.endFrame ||
    value.endFrame > value.sourceFrames) {
    throw new TypeError("Sample viewport is invalid");
  }
  return Object.freeze({
    sourceFrames: value.sourceFrames,
    startFrame: value.startFrame,
    endFrame: value.endFrame,
  });
}

function validateWindow(value: unknown): Readonly<WaveformWindow> {
  if (!exactKeys(value, ["startFrame", "endFrame", "bucketCount"]) ||
    !unsignedInteger(value.startFrame) ||
    !unsignedInteger(value.endFrame) ||
    value.startFrame >= value.endFrame ||
    !positiveInteger(value.bucketCount) ||
    value.bucketCount > 512) {
    throw new TypeError("Sample waveform window is invalid");
  }
  return Object.freeze({
    startFrame: value.startFrame,
    endFrame: value.endFrame,
    bucketCount: value.bucketCount,
  });
}

function normalizeSnapshotDetails(value: unknown): Readonly<Record<string, unknown>> {
  if (!plainRecord(value)) {
    throw new TypeError("Sample snapshot error details are invalid");
  }
  const hasKeys = (keys: readonly string[]): boolean =>
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key));
  if (hasKeys([])) return Object.freeze({});
  if (hasKeys(["actual_revision", "expected_revision"]) &&
    unsignedInteger(value.actual_revision) &&
    unsignedInteger(value.expected_revision)) {
    return Object.freeze({
      actual_revision: value.actual_revision,
      expected_revision: value.expected_revision,
    });
  }
  if (hasKeys(["resource", "observed", "limit"]) &&
    typeof value.resource === "string" &&
    SNAPSHOT_RESOURCE_TOKENS.has(value.resource) &&
    unsignedInteger(value.observed) && unsignedInteger(value.limit)) {
    return Object.freeze({
      resource: value.resource,
      observed: value.observed,
      limit: value.limit,
    });
  }
  if (hasKeys(["storage_condition"]) &&
    typeof value.storage_condition === "string" &&
    SNAPSHOT_STORAGE_CONDITIONS.has(value.storage_condition)) {
    return Object.freeze({storage_condition: value.storage_condition});
  }
  if (hasKeys(["transfer_condition"]) &&
    typeof value.transfer_condition === "string" &&
    SNAPSHOT_TRANSFER_CONDITIONS.has(value.transfer_condition)) {
    return Object.freeze({transfer_condition: value.transfer_condition});
  }
  throw new TypeError("Sample snapshot error details are invalid");
}

export function normalizeSampleSnapshotError(
  value: unknown,
): Readonly<SampleSnapshotError> | null {
  if (value === null) return null;
  if (!exactKeys(value, ["code", "message", "details"]) ||
    typeof value.code !== "string" || !ALLOWED_ERROR_CODES.has(value.code) ||
    typeof value.message !== "string" || value.message.length === 0 ||
    value.message.length > 512 || PRIVATE_HOST_MESSAGE_PATTERN.test(value.message)) {
    throw new TypeError("Sample snapshot error is invalid");
  }
  return Object.freeze({
    code: value.code,
    message: SAMPLE_PUBLIC_ERROR_MESSAGES[value.code] ?? "Sample operation failed",
    details: normalizeSnapshotDetails(value.details),
  });
}

export function projectSamplePlayback(
  playback: unknown | undefined,
): Readonly<PadPlayback> {
  return playback === undefined ? DEFAULT_PLAYBACK : validatePlayback(playback);
}

export function beginSampleDraft(
  saved: PadPlayback,
  baseRevision: number,
): SampleDraft {
  if (!unsignedInteger(baseRevision)) {
    throw new TypeError("Sample draft revision is invalid");
  }
  const stableSaved = validatePlayback(saved);
  return Object.freeze({
    baseRevision,
    saved: stableSaved,
    proposed: stableSaved,
    dirty: false,
  });
}

export function updateSampleDraft(
  draft: SampleDraft,
  changes: Partial<PadPlayback>,
): SampleDraft {
  if (!record(changes) || Object.keys(changes).some((key) => ![
    "trimStartFrame",
    "trimEndFrame",
    "triggerMode",
    "gainMillidb",
    "muted",
  ].includes(key))) {
    throw new TypeError("Sample draft changes are invalid");
  }
  const proposed = validatePlayback({...draft.proposed, ...changes});
  return Object.freeze({
    ...draft,
    proposed,
    dirty: !playbackEquals(draft.saved, proposed),
  });
}

export function cancelSampleDraft(state: SampleState): SampleState {
  return Object.freeze({...state, draft: null, auditionPlayback: null});
}

export function selectSampleSlot(state: SampleState, slot: number): SampleState {
  if (!slotNumber(slot)) throw new RangeError("Sample slot must be in 0..63");
  if (state.selectedSlot === slot) return state;
  return Object.freeze({
    ...state,
    selectedSlot: slot,
    inspect: null,
    waveform: null,
    viewport: null,
    draft: null,
    auditionPlayback: null,
    playhead: null,
  });
}

export function storeSampleInspect(state: SampleState, value: unknown): SampleState {
  const inspected = validateInspect(value);
  if (state.selectedSlot !== null && state.selectedSlot !== inspected.slot) {
    throw new TypeError("Sample inspect slot does not match selection");
  }
  return Object.freeze({
    ...state,
    selectedSlot: inspected.slot,
    inspect: inspected,
    waveform: null,
    viewport: inspected.metadata === null
      ? null
      : fitSampleViewport(inspected.metadata.sourceFrames),
    draft: null,
    auditionPlayback: null,
    savedRevision: inspected.projectRevision,
  });
}

export function fitSampleViewport(sourceFrames: number): Readonly<SampleViewport> {
  if (!positiveInteger(sourceFrames)) {
    throw new TypeError("Sample source frame count is invalid");
  }
  return Object.freeze({sourceFrames, startFrame: 0, endFrame: sourceFrames});
}

export function zoomSampleViewport(
  viewport: SampleViewport,
  factor: number,
  anchorFrame: number,
): Readonly<SampleViewport> {
  const current = validateViewport(viewport);
  if (!Number.isFinite(factor) || factor <= 0 ||
    !unsignedInteger(anchorFrame, current.sourceFrames)) {
    throw new TypeError("Sample viewport zoom is invalid");
  }
  const currentSpan = current.endFrame - current.startFrame;
  const nextSpan = Math.min(
    current.sourceFrames,
    Math.max(1, Math.round(currentSpan / factor)),
  );
  if (nextSpan === current.sourceFrames) return fitSampleViewport(current.sourceFrames);
  const ratio = (anchorFrame - current.startFrame) / currentSpan;
  const unclampedStart = Math.round(anchorFrame - nextSpan * ratio);
  const startFrame = Math.min(
    current.sourceFrames - nextSpan,
    Math.max(0, unclampedStart),
  );
  return Object.freeze({
    sourceFrames: current.sourceFrames,
    startFrame,
    endFrame: startFrame + nextSpan,
  });
}

export function panSampleViewport(
  viewport: SampleViewport,
  deltaFrames: number,
): Readonly<SampleViewport> {
  const current = validateViewport(viewport);
  if (!Number.isSafeInteger(deltaFrames)) {
    throw new TypeError("Sample viewport pan is invalid");
  }
  const span = current.endFrame - current.startFrame;
  const startFrame = Math.min(
    current.sourceFrames - span,
    Math.max(0, current.startFrame + deltaFrames),
  );
  return Object.freeze({
    sourceFrames: current.sourceFrames,
    startFrame,
    endFrame: startFrame + span,
  });
}

export function waveformWindowForViewport(
  viewport: SampleViewport,
  bucketCount: number,
): Readonly<WaveformWindow> {
  const current = validateViewport(viewport);
  return validateWindow({
    startFrame: current.startFrame,
    endFrame: current.endFrame,
    bucketCount,
  });
}

export function storeSampleWaveform(
  state: SampleState,
  value: unknown,
  request: SampleWaveformRequestIdentity,
): SampleState {
  assertPrivacySafe(value);
  if (!exactKeys(request, ["slot", "window", "waveformCacheIdentity"]) ||
    !slotNumber(request.slot) ||
    typeof request.waveformCacheIdentity !== "string") {
    throw new TypeError("Sample waveform request identity is invalid");
  }
  const window = validateWindow(request.window);
  if (!exactKeys(value, [
    "metadata",
    "algorithmVersion",
    "buckets",
    "projectRevision",
  ]) || value.algorithmVersion !== 1 ||
    !unsignedInteger(value.projectRevision) ||
    !Array.isArray(value.buckets) || value.buckets.length === 0 ||
    value.buckets.length > window.bucketCount) {
    throw new TypeError("Sample waveform result is invalid");
  }
  const waveformMetadata = validateMetadata(value.metadata);
  const selectedInspect = state.inspect;
  if (selectedInspect === null || selectedInspect.metadata === null) {
    throw new TypeError("Sample waveform truth does not match selection");
  }
  const selectedMetadata = selectedInspect.metadata;
  if (request.slot !== selectedInspect.slot ||
    request.waveformCacheIdentity !== selectedInspect.waveformCacheIdentity ||
    value.projectRevision !== selectedInspect.projectRevision ||
    waveformMetadata.sampleRate !== selectedMetadata.sampleRate ||
    waveformMetadata.channels !== selectedMetadata.channels ||
    waveformMetadata.sourceFrames !== selectedMetadata.sourceFrames ||
    window.endFrame > waveformMetadata.sourceFrames ||
    state.viewport?.startFrame !== window.startFrame ||
    state.viewport.endFrame !== window.endFrame) {
    throw new TypeError("Sample waveform truth does not match selection");
  }
  const frameCount = window.endFrame - window.startFrame;
  const framesPerBucket = Math.ceil(frameCount / window.bucketCount);
  const expectedBucketCount = Math.ceil(frameCount / framesPerBucket);
  if (value.buckets.length !== expectedBucketCount) {
    throw new TypeError("Sample waveform bucket count is invalid");
  }
  const buckets = value.buckets.map((bucket, index) => {
    const expectedStart = window.startFrame + index * framesPerBucket;
    const expectedEnd = Math.min(window.endFrame, expectedStart + framesPerBucket);
    if (!exactKeys(bucket, ["startFrame", "endFrame", "peakMagnitude"]) ||
      bucket.startFrame !== expectedStart || bucket.endFrame !== expectedEnd ||
      !unsignedInteger(bucket.peakMagnitude, 32_768)) {
      throw new TypeError("Sample waveform bucket is invalid");
    }
    return Object.freeze({
      startFrame: bucket.startFrame,
      endFrame: bucket.endFrame,
      peakMagnitude: bucket.peakMagnitude,
    });
  });
  const envelope: Readonly<WaveformEnvelope> = Object.freeze({
    metadata: waveformMetadata,
    algorithmVersion: 1,
    buckets: Object.freeze(buckets),
    projectRevision: value.projectRevision,
  });
  return Object.freeze({...state, waveform: envelope});
}

function validatePendingAction(value: unknown): Readonly<SamplePendingAction> {
  if (!exactKeys(value, ["kind", "slot", "expectedRevision"]) ||
    typeof value.kind !== "string" ||
    !PENDING_KINDS.has(value.kind as SamplePendingKind) ||
    !slotNumber(value.slot) || !unsignedInteger(value.expectedRevision) ||
    value.expectedRevision === Number.MAX_SAFE_INTEGER) {
    throw new TypeError("Sample pending action is invalid");
  }
  return Object.freeze({
    kind: value.kind as SamplePendingKind,
    slot: value.slot,
    expectedRevision: value.expectedRevision,
  });
}

function requireMatchingPending(
  state: SampleState,
  value: unknown,
  kinds?: ReadonlySet<SamplePendingKind>,
): Readonly<SamplePendingAction> {
  const pending = validatePendingAction(value);
  const current = state.pendingAction;
  if (current === null || current.kind !== pending.kind ||
    current.slot !== pending.slot ||
    current.expectedRevision !== pending.expectedRevision ||
    (kinds !== undefined && !kinds.has(pending.kind))) {
    throw new TypeError("Sample pending action does not match");
  }
  return current;
}

export function beginSamplePending(
  state: SampleState,
  value: unknown,
): SampleState {
  if (state.pendingAction !== null) {
    throw new TypeError("Sample action is already pending");
  }
  const pending = validatePendingAction(value);
  if (state.selectedSlot !== null && pending.slot !== state.selectedSlot) {
    throw new TypeError("Sample pending action is invalid");
  }
  return Object.freeze({...state, pendingAction: pending});
}

export function applySampleCommit(
  state: SampleState,
  pendingValue: unknown,
  currentInspect: unknown,
  value: unknown,
): SampleState {
  const pending = requireMatchingPending(
    state,
    pendingValue,
    MUTATION_PENDING_KINDS,
  );
  if (!exactKeys(value, [
    "committedRevision",
    "runtimeRevision",
    "runtimePublished",
    "snapshotError",
  ]) || !unsignedInteger(value.committedRevision) ||
    !(value.runtimeRevision === null || unsignedInteger(value.runtimeRevision)) ||
    typeof value.runtimePublished !== "boolean") {
    throw new TypeError("Sample mutation result is invalid");
  }
  const commit = value as unknown as SampleCommit;
  const snapshotError = normalizeSampleSnapshotError(commit.snapshotError);
  if (commit.runtimePublished &&
    (commit.runtimeRevision === null ||
      commit.runtimeRevision < commit.committedRevision ||
      snapshotError !== null)) {
    throw new TypeError("Sample mutation publication is invalid");
  }
  const inspected = validateInspect(currentInspect);
  const minimumRevision = Math.max(
    commit.committedRevision,
    commit.runtimeRevision ?? 0,
  );
  if (state.selectedSlot === null) {
    throw new TypeError("Sample mutation has no matching selection");
  }
  if (inspected.slot !== pending.slot ||
    commit.committedRevision !== pending.expectedRevision + 1 ||
    inspected.projectRevision < minimumRevision) {
    throw new TypeError("Sample mutation refresh is stale");
  }
  const runtimeIsCurrent = commit.runtimeRevision === inspected.projectRevision;
  const selectedMutationSlot = state.selectedSlot === pending.slot;
  return Object.freeze({
    ...state,
    inspect: selectedMutationSlot ? inspected : null,
    waveform: null,
    viewport: selectedMutationSlot
      ? inspected.metadata === null
        ? null
        : fitSampleViewport(inspected.metadata.sourceFrames)
      : null,
    draft: selectedMutationSlot ? null : state.draft,
    auditionPlayback: null,
    pendingAction: null,
    savedRevision: inspected.projectRevision,
    runtimeRevision: commit.runtimeRevision,
    lastError: snapshotError === null || runtimeIsCurrent ? null : Object.freeze({
      code: snapshotError.code,
      message: snapshotError.message,
      retryPrepare: snapshotError.code === "COOK_FAILED",
    }),
  });
}

export function applySampleConflict(
  state: SampleState,
  pendingValue: unknown,
  currentInspect: unknown,
): SampleState {
  const pending = requireMatchingPending(
    state,
    pendingValue,
    MUTATION_PENDING_KINDS,
  );
  const inspected = validateInspect(currentInspect);
  if (state.selectedSlot === null) {
    throw new TypeError("Sample conflict has no matching selection");
  }
  if (inspected.slot !== pending.slot ||
    inspected.projectRevision <= pending.expectedRevision) {
    throw new TypeError("Sample conflict refresh is stale");
  }
  const refreshed = state.selectedSlot === pending.slot
    ? storeSampleInspect(state, inspected)
    : Object.freeze({
        ...state,
        inspect: null,
        waveform: null,
        viewport: null,
        savedRevision: inspected.projectRevision,
      });
  return Object.freeze({
    ...refreshed,
    draft: null,
    auditionPlayback: null,
    pendingAction: null,
    lastError: Object.freeze({
      code: "REVISION_CONFLICT",
      message: "Project changed; review and try again",
      retryPrepare: false,
    }),
  });
}

export function applySampleRetryPublication(
  state: SampleState,
  pendingValue: unknown,
  value: unknown,
): SampleState {
  const pending = requireMatchingPending(
    state,
    pendingValue,
    RETRY_PENDING_KINDS,
  );
  if (!exactKeys(value, [
    "projectId",
    "projectRevision",
    "patternId",
    "runtimeReady",
    "generation",
    "snapshotError",
    "runtimeRevision",
  ]) || typeof value.projectId !== "string" || !UUID_PATTERN.test(value.projectId) ||
    typeof value.patternId !== "string" || !UUID_PATTERN.test(value.patternId) ||
    !unsignedInteger(value.projectRevision) ||
    typeof value.runtimeReady !== "boolean" ||
    !(value.runtimeRevision === null || unsignedInteger(value.runtimeRevision))) {
    throw new TypeError("Sample retry publication is invalid");
  }
  const publication = value as unknown as SnapshotPublication;
  const snapshotError = normalizeSampleSnapshotError(publication.snapshotError);
  if (pending.expectedRevision !== publication.projectRevision ||
    state.savedRevision !== publication.projectRevision ||
    (publication.runtimeReady &&
      (!positiveInteger(publication.generation) ||
        publication.runtimeRevision !== publication.projectRevision ||
        snapshotError !== null)) ||
    (!publication.runtimeReady &&
      (publication.generation !== null || snapshotError === null ||
        (publication.runtimeRevision !== null &&
          publication.runtimeRevision > publication.projectRevision)))) {
    throw new TypeError("Sample retry publication truth is invalid");
  }
  return Object.freeze({
    ...state,
    pendingAction: null,
    runtimeRevision: publication.runtimeRevision,
    lastError: snapshotError === null ? null : Object.freeze({
      code: snapshotError.code,
      message: snapshotError.message,
      retryPrepare: snapshotError.code === "COOK_FAILED",
    }),
  });
}

function validateVoiceState(value: unknown): RuntimeVoiceState {
  assertPrivacySafe(value);
  if (!exactKeys(value, [
    "sequence",
    "slot",
    "state",
    "runtimeFrame",
    "sourceFrame",
  ]) || !positiveInteger(value.sequence) || !slotNumber(value.slot) ||
    typeof value.state !== "string" || !VOICE_STATES.has(value.state) ||
    !unsignedInteger(value.runtimeFrame) || !unsignedInteger(value.sourceFrame)) {
    throw new TypeError("Runtime Voice state is invalid");
  }
  return {
    sequence: value.sequence,
    slot: value.slot,
    state: value.state as RuntimeVoiceState["state"],
    runtimeFrame: value.runtimeFrame,
    sourceFrame: value.sourceFrame,
  };
}

export function applyRuntimeVoiceState(
  state: SampleState,
  value: unknown,
): SampleState {
  const event = validateVoiceState(value);
  let voices = state.voices.filter(({sequence}) => sequence !== event.sequence);
  let playhead = state.playhead;
  if (event.state === "started") {
    const selected = state.selectedSlot === event.slot;
    const playback = selected
      ? state.auditionPlayback ?? state.inspect?.playback
      : undefined;
    const metadata = selected ? state.inspect?.metadata : undefined;
    const sampleRate = metadata?.sampleRate ?? null;
    const trimStartFrame = playback?.trimStartFrame ?? null;
    const trimEndFrame = playback === undefined
      ? null
      : playback.trimEndFrame ?? metadata?.sourceFrames ?? null;
    const renderBounds = {sampleRate, trimStartFrame, trimEndFrame};
    const voice: Readonly<SampleVoiceRender> = Object.freeze({
      ...event,
      state: "started",
      ...renderBounds,
    });
    voices = [...voices, voice].slice(-SAMPLE_VOICE_RENDER_LIMIT);
    if (selected) {
      const lower = trimStartFrame ?? 0;
      const sourceFrame = trimEndFrame === null
        ? Math.max(lower, event.sourceFrame)
        : Math.min(Math.max(lower, event.sourceFrame), trimEndFrame - 1);
      playhead = Object.freeze({
        sequence: event.sequence,
        slot: event.slot,
        runtimeFrame: event.runtimeFrame,
        sourceFrame,
        ...renderBounds,
      });
    }
  } else if (playhead?.sequence === event.sequence) {
    playhead = null;
  }
  return Object.freeze({
    ...state,
    voices: Object.freeze(voices),
    playhead,
  });
}

export function applySampleOperationFailure(
  state: SampleState,
  pendingValue: unknown,
  value: unknown,
): SampleState {
  requireMatchingPending(state, pendingValue);
  const hasDetails = record(value) && Object.hasOwn(value, "details");
  if (!(exactKeys(value, ["code", "message"]) ||
    exactKeys(value, ["code", "message", "details"])) ||
    typeof value.code !== "string" || !ALLOWED_ERROR_CODES.has(value.code) ||
    typeof value.message !== "string" || value.message.length === 0 ||
    value.message.length > 512) {
    throw new TypeError("Sample operation failure is invalid");
  }
  const details = hasDetails
    ? normalizeSnapshotDetails(value.details)
    : Object.freeze({});
  return Object.freeze({
    ...state,
    pendingAction: null,
    lastError: Object.freeze({
      code: value.code,
      message: SAMPLE_PUBLIC_ERROR_MESSAGES[value.code] ?? "Sample operation failed",
      retryPrepare: value.code === "COOK_FAILED",
      details,
    }),
  });
}

export function cancelSampleOperation(
  state: SampleState,
  pendingValue: unknown,
): SampleState {
  requireMatchingPending(state, pendingValue);
  return Object.freeze({...state, pendingAction: null});
}

function requireSampleActionKeys(
  action: SampleStateAction,
  keys: readonly string[],
): void {
  if (!exactKeys(action, keys)) {
    throw new TypeError("Sample state action is invalid");
  }
}

export function reduceSampleState(
  state: SampleState,
  action: SampleStateAction,
): SampleState {
  switch (action.type) {
    case "slot-selected":
      requireSampleActionKeys(action, ["type", "slot"]);
      return selectSampleSlot(state, action.slot);
    case "inspect-stored":
      requireSampleActionKeys(action, ["type", "inspect"]);
      return storeSampleInspect(state, action.inspect);
    case "waveform-stored":
      requireSampleActionKeys(action, ["type", "envelope", "request"]);
      return storeSampleWaveform(state, action.envelope, action.request);
    case "draft-began":
      requireSampleActionKeys(action, ["type"]);
      if (state.inspect === null) {
        throw new TypeError("Sample draft has no selected truth");
      }
      return Object.freeze({
        ...state,
        draft: beginSampleDraft(
          state.inspect.playback,
          state.inspect.projectRevision,
        ),
      });
    case "draft-updated":
      requireSampleActionKeys(action, ["type", "changes"]);
      if (state.draft === null) {
        throw new TypeError("Sample draft is not active");
      }
      return Object.freeze({
        ...state,
        draft: updateSampleDraft(state.draft, action.changes),
      });
    case "draft-cancelled":
      requireSampleActionKeys(action, ["type"]);
      return cancelSampleDraft(state);
    case "preview-applied": {
      requireSampleActionKeys(action, ["type", "playback"]);
      if (state.draft === null) {
        throw new TypeError("Sample preview has no active draft");
      }
      const playback = validatePlayback(action.playback);
      if (!playbackEquals(playback, state.draft.proposed)) {
        throw new TypeError("Sample preview does not match active draft");
      }
      return Object.freeze({...state, auditionPlayback: playback});
    }
    case "preview-cleared":
      requireSampleActionKeys(action, ["type"]);
      return Object.freeze({...state, auditionPlayback: null});
    case "pending-began":
      requireSampleActionKeys(action, ["type", "pending"]);
      return beginSamplePending(state, action.pending);
    case "mutation-committed":
      requireSampleActionKeys(action, ["type", "pending", "inspect", "commit"]);
      return applySampleCommit(
        state,
        action.pending,
        action.inspect,
        action.commit,
      );
    case "mutation-conflicted":
      requireSampleActionKeys(action, ["type", "pending", "inspect"]);
      return applySampleConflict(state, action.pending, action.inspect);
    case "retry-published":
      requireSampleActionKeys(action, ["type", "pending", "publication"]);
      return applySampleRetryPublication(
        state,
        action.pending,
        action.publication,
      );
    case "voice-changed":
      requireSampleActionKeys(action, ["type", "event"]);
      return applyRuntimeVoiceState(state, action.event);
    case "preview-failed":
      requireSampleActionKeys(action, ["type"]);
      return Object.freeze({
        ...state,
        draft: null,
        auditionPlayback: null,
        lastError: Object.freeze({
          code: "HOST_STATE_INVALID",
          message: "Runtime preview failed",
          retryPrepare: false,
        }),
      });
    case "operation-failed":
      requireSampleActionKeys(action, ["type", "pending", "error"]);
      return applySampleOperationFailure(state, action.pending, action.error);
    case "operation-cancelled":
      requireSampleActionKeys(action, ["type", "pending"]);
      return cancelSampleOperation(state, action.pending);
    case "error-cleared":
      requireSampleActionKeys(action, ["type"]);
      return Object.freeze({...state, lastError: null});
    default:
      throw new TypeError("Sample state action is invalid");
  }
}
