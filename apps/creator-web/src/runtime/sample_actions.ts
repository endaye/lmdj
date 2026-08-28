import type {
  CreatorSampleRuntimeSession,
  PadPlayback,
  SampleCommit,
  SampleImportOptions,
  SampleInspect,
  SampleMetadata,
  SampleResetRequest,
  SampleSnapshotError,
  SampleUpdateRequest,
  SnapshotPublication,
  WaveformEnvelope,
  WaveformQuery,
  WaveformWindow,
} from "./runtime_types";
import {
  initialSampleState,
  normalizeSampleSnapshotError,
  projectSamplePlayback,
  selectSampleSlot,
  storeSampleInspect,
  type SampleDraft,
} from "../state/sample_state";
import {COMMIT_MAX_FRAMES, type CaptureBuffer} from "../capture/capture_buffer";
import {encodePcm16Wav} from "../capture/wav_encoder";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
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
  "sourceFileName",
  "source_file_name",
  "bytes",
  "sampleBytes",
  "sample_bytes",
  "rawBytes",
  "raw_bytes",
  "storageHandle",
  "storage_handle",
  "opfsHandle",
  "opfs_handle",
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
const MAX_SAFE_JSON_DEPTH = 8;
const MAX_SAFE_JSON_NODES = 4_096;
const MAX_SAFE_JSON_COLLECTION = 512;
const MAX_SAFE_JSON_STRING = 4_096;

export const SAMPLE_CONFLICT_MESSAGE =
  "Project changed; review and try again";
export const SAMPLE_PREVIEW_FAILURE_MESSAGE = "Runtime preview failed";

export type SampleMutationResolution =
  | Readonly<{
      kind: "committed";
      commit: Readonly<SampleCommit>;
      inspect: Readonly<SampleInspect> | null;
    }>
  | Readonly<{
      kind: "conflict";
      inspect: Readonly<SampleInspect>;
      message: typeof SAMPLE_CONFLICT_MESSAGE;
    }>;

export type SampleDraftCommitResolution =
  | SampleMutationResolution
  | Readonly<{kind: "cancelled"}>;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
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

function protocolMismatch(message: string): Error & {code: string} {
  return Object.assign(new Error(message), {code: "HOST_PROTOCOL_MISMATCH"});
}

function errorCode(error: unknown): string | undefined {
  return record(error) && typeof error.code === "string" ? error.code : undefined;
}

function assertPrivacySafeValue(
  value: unknown,
  depth: number,
  budget: {nodes: number},
): void {
  budget.nodes += 1;
  if (budget.nodes > MAX_SAFE_JSON_NODES || depth > MAX_SAFE_JSON_DEPTH) {
    throw protocolMismatch("Sample response exceeds safe JSON bounds");
  }
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (value.length > MAX_SAFE_JSON_STRING) {
      throw protocolMismatch("Sample response exceeds safe JSON bounds");
    }
    return;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw protocolMismatch("Sample response contains unsafe JSON data");
    }
    return;
  }
  if (typeof value !== "object" || ArrayBuffer.isView(value) ||
    value instanceof ArrayBuffer ||
    (typeof SharedArrayBuffer !== "undefined" &&
      value instanceof SharedArrayBuffer)) {
    throw protocolMismatch("Sample response contains private data");
  }
  if (Array.isArray(value)) {
    if (value.length > MAX_SAFE_JSON_COLLECTION) {
      throw protocolMismatch("Sample response exceeds safe JSON bounds");
    }
    for (const item of value) {
      assertPrivacySafeValue(item, depth + 1, budget);
    }
    return;
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw protocolMismatch("Sample response contains private data");
  }
  const response = value as Record<string, unknown>;
  if ((response.contract === "lmdj.project.v1" ||
      response.contract === "lmdj.project.v2") &&
      Object.hasOwn(value, "banks") && Object.hasOwn(value, "assets")) {
    throw protocolMismatch("Sample response contains private data");
  }
  const entries = Object.entries(value);
  if (entries.length > MAX_SAFE_JSON_COLLECTION) {
    throw protocolMismatch("Sample response exceeds safe JSON bounds");
  }
  for (const [key, item] of entries) {
    const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, "");
    const privateKey = FORBIDDEN_PRIVATE_KEYS.has(key) ||
      (!SAFE_PROJECT_KEYS.has(normalizedKey) &&
        PRIVATE_KEY_TERMS.some((term) => normalizedKey.includes(term)));
    if (key.length > 128 || privateKey) {
      throw protocolMismatch("Sample response contains private data");
    }
    assertPrivacySafeValue(item, depth + 1, budget);
  }
}

function assertPrivacySafe(value: unknown): void {
  assertPrivacySafeValue(value, 0, {nodes: 0});
}

function normalizeBoolean(value: unknown, name: string): boolean {
  if (typeof value !== "boolean") {
    throw protocolMismatch(`${name} result is invalid`);
  }
  return value;
}

function normalizeMetadata(value: unknown): Readonly<SampleMetadata> {
  if (!exactKeys(value, ["sampleRate", "channels", "sourceFrames"]) ||
    (value.sampleRate !== 44_100 && value.sampleRate !== 48_000) ||
    (value.channels !== 1 && value.channels !== 2) ||
    !positiveInteger(value.sourceFrames)) {
    throw protocolMismatch("Sample metadata result is invalid");
  }
  return Object.freeze({
    sampleRate: value.sampleRate,
    channels: value.channels,
    sourceFrames: value.sourceFrames,
  });
}

function normalizeInspect(value: unknown, expectedSlot: number): Readonly<SampleInspect> {
  try {
    const selected = selectSampleSlot(initialSampleState, expectedSlot);
    const inspected = storeSampleInspect(selected, value).inspect;
    if (inspected === null) {
      throw new TypeError("missing inspect");
    }
    return inspected;
  } catch {
    throw protocolMismatch("Sample inspect result is invalid");
  }
}

function normalizeWindow(value: unknown): Readonly<WaveformWindow> {
  if (!exactKeys(value, ["startFrame", "endFrame", "bucketCount"]) ||
    !unsignedInteger(value.startFrame) || !unsignedInteger(value.endFrame) ||
    value.startFrame >= value.endFrame || !positiveInteger(value.bucketCount) ||
    value.bucketCount > 512) {
    throw new TypeError("Sample waveform query is invalid");
  }
  return Object.freeze({
    startFrame: value.startFrame,
    endFrame: value.endFrame,
    bucketCount: value.bucketCount,
  });
}

function normalizeWaveform(
  value: unknown,
  request: Readonly<WaveformWindow>,
): Readonly<WaveformEnvelope> {
  assertPrivacySafe(value);
  if (!exactKeys(value, [
    "metadata",
    "algorithmVersion",
    "buckets",
    "projectRevision",
  ]) || value.algorithmVersion !== 1 || !unsignedInteger(value.projectRevision) ||
    !Array.isArray(value.buckets) || value.buckets.length === 0 ||
    value.buckets.length > request.bucketCount) {
    throw protocolMismatch("Sample waveform result is invalid");
  }
  const metadata = normalizeMetadata(value.metadata);
  if (request.endFrame > metadata.sourceFrames) {
    throw protocolMismatch("Sample waveform metadata is invalid");
  }
  const frameCount = request.endFrame - request.startFrame;
  const framesPerBucket = Math.ceil(frameCount / request.bucketCount);
  const expectedBucketCount = Math.ceil(frameCount / framesPerBucket);
  if (value.buckets.length !== expectedBucketCount) {
    throw protocolMismatch("Sample waveform bucket count is invalid");
  }
  const buckets = value.buckets.map((bucket, index) => {
    const startFrame = request.startFrame + index * framesPerBucket;
    const endFrame = Math.min(request.endFrame, startFrame + framesPerBucket);
    if (!exactKeys(bucket, ["startFrame", "endFrame", "peakMagnitude"]) ||
      bucket.startFrame !== startFrame || bucket.endFrame !== endFrame ||
      !unsignedInteger(bucket.peakMagnitude, 32_768)) {
      throw protocolMismatch("Sample waveform bucket is invalid");
    }
    return Object.freeze({
      startFrame: bucket.startFrame,
      endFrame: bucket.endFrame,
      peakMagnitude: bucket.peakMagnitude,
    });
  });
  return Object.freeze({
    metadata,
    algorithmVersion: 1,
    buckets: Object.freeze(buckets),
    projectRevision: value.projectRevision,
  });
}

function normalizeSnapshotError(value: unknown): Readonly<SampleSnapshotError> | null {
  try {
    return normalizeSampleSnapshotError(value);
  } catch {
    throw protocolMismatch("Sample snapshot error result is invalid");
  }
}

function normalizeCommit(value: unknown): Readonly<SampleCommit> {
  if (!exactKeys(value, [
    "committedRevision",
    "runtimeRevision",
    "runtimePublished",
    "snapshotError",
  ]) || !unsignedInteger(value.committedRevision) ||
    !(value.runtimeRevision === null || unsignedInteger(value.runtimeRevision)) ||
    typeof value.runtimePublished !== "boolean") {
    throw protocolMismatch("Sample mutation result is invalid");
  }
  const snapshotError = normalizeSnapshotError(value.snapshotError);
  if (value.runtimePublished &&
    (value.runtimeRevision === null ||
      value.runtimeRevision < value.committedRevision ||
      snapshotError !== null)) {
    throw protocolMismatch("Sample mutation publication is invalid");
  }
  return Object.freeze({
    committedRevision: value.committedRevision,
    runtimeRevision: value.runtimeRevision,
    runtimePublished: value.runtimePublished,
    snapshotError,
  });
}

function normalizePublication(
  value: unknown,
  expectedPatternId: string,
): Readonly<SnapshotPublication> {
  if (!exactKeys(value, [
    "projectId",
    "projectRevision",
    "patternId",
    "runtimeReady",
    "generation",
    "snapshotError",
    "runtimeRevision",
  ]) || typeof value.projectId !== "string" || !UUID_PATTERN.test(value.projectId) ||
    !unsignedInteger(value.projectRevision) || value.patternId !== expectedPatternId ||
    typeof value.runtimeReady !== "boolean" ||
    !(value.runtimeRevision === null || unsignedInteger(value.runtimeRevision))) {
    throw protocolMismatch("Snapshot publication result is invalid");
  }
  const snapshotError = normalizeSnapshotError(value.snapshotError);
  if ((value.runtimeReady &&
      (!positiveInteger(value.generation) || value.runtimeRevision === null ||
        value.runtimeRevision !== value.projectRevision || snapshotError !== null)) ||
    (!value.runtimeReady &&
      (value.generation !== null || snapshotError === null ||
        (value.runtimeRevision !== null &&
          value.runtimeRevision > value.projectRevision)))) {
    throw protocolMismatch("Snapshot publication truth is invalid");
  }
  return Object.freeze({
    projectId: value.projectId,
    projectRevision: value.projectRevision,
    patternId: value.patternId,
    runtimeReady: value.runtimeReady,
    generation: value.generation as number | null,
    snapshotError,
    runtimeRevision: value.runtimeRevision,
  });
}

function normalizePlayback(value: unknown): PadPlayback {
  if (value === undefined) {
    throw new TypeError("Sample playback is invalid");
  }
  try {
    return {...projectSamplePlayback(value)};
  } catch {
    throw new TypeError("Sample playback is invalid");
  }
}

async function clearPreview(
  session: CreatorSampleRuntimeSession,
  slot: number,
): Promise<boolean> {
  return normalizeBoolean(
    await session.clearSamplePreview(slot),
    "Sample preview clear",
  );
}

async function resolveMutation(
  session: CreatorSampleRuntimeSession,
  slot: number,
  operation: () => Promise<SampleCommit>,
  clearOnFailure: boolean,
): Promise<SampleMutationResolution> {
  let commit: Readonly<SampleCommit>;
  try {
    commit = normalizeCommit(await operation());
  } catch (error) {
    if (errorCode(error) !== "REVISION_CONFLICT") {
      if (clearOnFailure) {
        try {
          await clearPreview(session, slot);
        } catch {
          // The primary typed failure remains authoritative.
        }
      }
      throw error;
    }
    await clearPreview(session, slot);
    const inspected = await inspectSampleJourney(session, slot);
    return Object.freeze({
      kind: "conflict",
      inspect: inspected,
      message: SAMPLE_CONFLICT_MESSAGE,
    });
  }

  try {
    await clearPreview(session, slot);
  } catch {
    return Object.freeze({kind: "committed", commit, inspect: null});
  }
  let inspected: Readonly<SampleInspect>;
  try {
    inspected = await inspectSampleJourney(session, slot);
  } catch {
    return Object.freeze({kind: "committed", commit, inspect: null});
  }
  const minimumRevision = Math.max(
    commit.committedRevision,
    commit.runtimeRevision ?? 0,
  );
  if (inspected.projectRevision < minimumRevision) {
    throw protocolMismatch("Sample mutation refresh is stale");
  }
  return Object.freeze({kind: "committed", commit, inspect: inspected});
}

export async function inspectSampleJourney(
  session: CreatorSampleRuntimeSession,
  slot: number,
): Promise<Readonly<SampleInspect>> {
  if (!slotNumber(slot)) throw new RangeError("Sample slot must be in 0..63");
  return normalizeInspect(await session.inspectSample(slot), slot);
}

export async function queryWaveformJourney(
  session: CreatorSampleRuntimeSession,
  request: WaveformQuery,
): Promise<Readonly<WaveformEnvelope>> {
  if (!exactKeys(request, ["slot", "window"]) || !slotNumber(request.slot)) {
    throw new TypeError("Sample waveform query is invalid");
  }
  const window = normalizeWindow(request.window);
  const query = Object.freeze({slot: request.slot, window});
  return normalizeWaveform(await session.queryWaveform(query), window);
}

export async function previewSampleDraftJourney(
  session: CreatorSampleRuntimeSession,
  slot: number,
  draft: SampleDraft,
): Promise<boolean> {
  if (!slotNumber(slot)) throw new RangeError("Sample slot must be in 0..63");
  const accepted = normalizeBoolean(
    await session.setSamplePreview(slot, normalizePlayback(draft.proposed)),
    "Sample preview",
  );
  if (accepted) return true;
  try {
    await clearPreview(session, slot);
  } catch {
    // Preview rejection is the stable primary failure.
  }
  throw Object.assign(new Error(SAMPLE_PREVIEW_FAILURE_MESSAGE), {
    code: "HOST_STATE_INVALID",
  });
}

export function cancelSamplePreviewJourney(
  session: CreatorSampleRuntimeSession,
  slot: number,
): Promise<boolean> {
  if (!slotNumber(slot)) {
    return Promise.reject(new RangeError("Sample slot must be in 0..63"));
  }
  return clearPreview(session, slot);
}

export function updateSampleJourney(
  session: CreatorSampleRuntimeSession,
  request: SampleUpdateRequest,
): Promise<SampleMutationResolution> {
  if (!exactKeys(request, ["slot", "expectedRevision", "playback"]) ||
    !slotNumber(request.slot) || !unsignedInteger(request.expectedRevision)) {
    return Promise.reject(new TypeError("Sample update request is invalid"));
  }
  const normalized = Object.freeze({
    slot: request.slot,
    expectedRevision: request.expectedRevision,
    playback: normalizePlayback(request.playback),
  });
  return resolveMutation(
    session,
    request.slot,
    () => session.updatePad(normalized),
    true,
  );
}

export function resetSampleJourney(
  session: CreatorSampleRuntimeSession,
  request: SampleResetRequest,
): Promise<SampleMutationResolution> {
  if (!exactKeys(request, ["slot", "expectedRevision"]) ||
    !slotNumber(request.slot) || !unsignedInteger(request.expectedRevision)) {
    return Promise.reject(new TypeError("Sample reset request is invalid"));
  }
  const normalized = Object.freeze({
    slot: request.slot,
    expectedRevision: request.expectedRevision,
  });
  return resolveMutation(
    session,
    request.slot,
    () => session.resetPad(normalized),
    true,
  );
}

export function importAssignSampleJourney(
  session: CreatorSampleRuntimeSession,
  file: File,
  options: SampleImportOptions,
): Promise<SampleMutationResolution> {
  const keys = Object.keys(options ?? {});
  if (!record(options) ||
    keys.some((key) => ![
      "slot",
      "expectedRevision",
      "sequenceSessionId",
      "signal",
      "onProgress",
    ].includes(key)) ||
    !Object.hasOwn(options, "slot") ||
    !Object.hasOwn(options, "expectedRevision") ||
    !slotNumber(options.slot) || !unsignedInteger(options.expectedRevision) ||
    (options.sequenceSessionId !== undefined &&
      !UUID_PATTERN.test(options.sequenceSessionId)) ||
    (options.onProgress !== undefined && typeof options.onProgress !== "function") ||
    (options.signal !== undefined && !(options.signal instanceof AbortSignal))) {
    return Promise.reject(new TypeError("Sample import options are invalid"));
  }
  const normalizedOptions: SampleImportOptions = Object.freeze({
    slot: options.slot,
    expectedRevision: options.expectedRevision,
    ...(options.sequenceSessionId === undefined
      ? {}
      : {sequenceSessionId: options.sequenceSessionId}),
    ...(options.signal === undefined ? {} : {signal: options.signal}),
    ...(options.onProgress === undefined ? {} : {onProgress: options.onProgress}),
  });
  return resolveMutation(
    session,
    options.slot,
    () => session.importAssignSample(file, normalizedOptions),
    false,
  );
}

export const CAPTURE_FILE_NAME = "capture.wav";

// A committed capture is just another byte source for the Stage 8 import
// session: encode the trimmed selection here, then hand the File to the very
// same journey the file picker uses. Nothing downstream — staging, writer
// lease, command_id/expected_revision, conflict classification, Cooker
// preparation — learns that these bytes came from a microphone (S8B design
// §6.2). A conflict therefore surfaces exactly like an import conflict, and a
// retry re-encodes the identical selection into identical bytes.
export function captureCommitJourney(
  session: CreatorSampleRuntimeSession,
  buffer: CaptureBuffer,
  selection: {startFrame: number; frameCount: number},
  options: SampleImportOptions,
): Promise<SampleMutationResolution> {
  if (!exactKeys(selection, ["startFrame", "frameCount"]) ||
      !unsignedInteger(selection.startFrame) ||
      !unsignedInteger(selection.frameCount) ||
      selection.frameCount < 1 ||
      selection.frameCount > COMMIT_MAX_FRAMES) {
    return Promise.reject(new TypeError("Capture commit selection is invalid"));
  }
  let file: File;
  try {
    const wav = encodePcm16Wav(
      buffer.slice(selection.startFrame, selection.frameCount),
    );
    file = new File([wav], CAPTURE_FILE_NAME, {type: "audio/wav"});
  } catch (error) {
    return Promise.reject(error);
  }
  return importAssignSampleJourney(session, file, options);
}

export async function retryPrepareJourney(
  session: CreatorSampleRuntimeSession,
  patternId: string,
): Promise<Readonly<SnapshotPublication>> {
  if (!UUID_PATTERN.test(patternId)) {
    throw new TypeError("Sample retry Pattern identity is invalid");
  }
  return normalizePublication(await session.retryPrepare(patternId), patternId);
}

export async function commitSampleDraft(
  session: CreatorSampleRuntimeSession,
  slot: number,
  draft: SampleDraft,
): Promise<SampleDraftCommitResolution> {
  if (!draft.dirty) {
    await clearPreview(session, slot);
    return Object.freeze({kind: "cancelled"});
  }
  return updateSampleJourney(session, {
    slot,
    expectedRevision: draft.baseRevision,
    playback: draft.proposed,
  });
}
