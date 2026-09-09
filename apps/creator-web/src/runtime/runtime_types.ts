export interface LocalProjectSummary {
  projectId: string;
  patternId: string;
  revision: number;
  bpm: number;
  assetCount: number;
  assignedPadCount: number;
  bundleDigest: string;
}

export interface ProjectPadView {
  slot: number;
  assetId: string | null;
}

export interface ProjectView extends LocalProjectSummary {
  key: "—";
  pads: readonly ProjectPadView[];
  patterns: readonly Readonly<{patternId: string; bars: 1 | 2 | 4 | 8}>[];
  readonly patternSlots: readonly (string | null)[];
  sequenceSettings: Readonly<{
    quantizeEnabled: boolean;
    swingPercent: number;
  }>;
}

export interface TransferProgress {
  completedBytes: number;
  totalBytes: number;
}

export interface ProjectInspectResult {
  project_revision: number;
  project: unknown;
}

export type RuntimeTriggerSource = "pointer" | "keyboard" | "midi";

export interface TriggerAdmission {
  sequence: number;
  slot: number;
  velocity: number;
  source: RuntimeTriggerSource;
}

export interface RuntimeOutcome {
  sequence: number;
  outcome: "voice_started" | "voice_capacity";
  runtimeFrame: number;
}

export type SampleTriggerMode =
  | "one_shot"
  | "gate"
  | "loop_gate"
  | "loop_toggle";

export interface PadPlayback {
  trimStartFrame: number;
  trimEndFrame: number | null;
  triggerMode: SampleTriggerMode;
  gainMillidb: number;
  muted: boolean;
}

export interface SampleMetadata {
  sampleRate: 44_100 | 48_000;
  channels: 1 | 2;
  sourceFrames: number;
}

export interface SampleInspect {
  projectRevision: number;
  slot: number;
  assetId: string | null;
  playback: Readonly<PadPlayback>;
  metadata: Readonly<SampleMetadata> | null;
  waveformCacheIdentity: string | null;
}

export interface SampleQuotaConsumption {
  slot: number;
  preparedBytes: number;
  preparedFrames: number;
}

export interface SampleQuota {
  projectRevision: number;
  slot: number;
  bankQuotaBytes: number;
  bankUsedBytes: number;
  bankRemainingBytes: number;
  projectQuotaBytes: number;
  projectUsedBytes: number;
  projectRemainingBytes: number;
  effectiveRemainingBytes: number;
  effectiveRemainingFrames: number;
  consumed: readonly Readonly<SampleQuotaConsumption>[];
}

export interface SampleIngestLimits {
  sourceBytes: number;
  decodedFrames: number;
  channels: number;
  artifactBytes: number;
}

export interface WaveformWindow {
  startFrame: number;
  endFrame: number;
  bucketCount: number;
}

export interface WaveformQuery {
  slot: number;
  window: Readonly<WaveformWindow>;
}

export interface WaveformBucket {
  startFrame: number;
  endFrame: number;
  peakMagnitude: number;
}

export interface WaveformEnvelope {
  metadata: Readonly<SampleMetadata>;
  algorithmVersion: 1;
  buckets: readonly Readonly<WaveformBucket>[];
  projectRevision: number;
}

export interface SampleSnapshotError {
  code: string;
  message: string;
  details: Readonly<Record<string, unknown>>;
}

export interface SampleCommit {
  committedRevision: number;
  runtimeRevision: number | null;
  runtimePublished: boolean;
  snapshotError: Readonly<SampleSnapshotError> | null;
}

export interface SampleImportOptions {
  slot: number;
  expectedRevision: number;
  sequenceSessionId?: string;
  signal?: AbortSignal;
  onProgress?: (progress: TransferProgress) => void;
}

export interface SampleUpdateRequest {
  slot: number;
  expectedRevision: number;
  playback: Readonly<PadPlayback>;
}

export interface SampleResetRequest {
  slot: number;
  expectedRevision: number;
}

export interface SnapshotPublication {
  projectId: string;
  projectRevision: number;
  patternId: string;
  runtimeReady: boolean;
  generation: number | null;
  snapshotError: Readonly<SampleSnapshotError> | null;
  runtimeRevision: number | null;
}

export interface RuntimeVoiceState {
  sequence: number;
  slot: number;
  state: "started" | "stopped" | "completed";
  runtimeFrame: number;
  sourceFrame: number;
}

export interface RuntimeHostState {
  state: string;
  errorCode: string | null;
  errorDetails: Readonly<Record<string, unknown>>;
}

export interface RuntimeIssue {
  code: string;
  details: Readonly<Record<string, unknown>>;
}

export interface RuntimeDiagnostics {
  state: string;
  error_code: string | null;
  error_details: Readonly<Record<string, unknown>>;
  product_build: string;
  host_id: string;
  host_version: string;
  platform_version: string;
  protocol_version: number;
  capabilities: {
    secureContext: boolean;
    crossOriginIsolated: boolean;
    sharedArrayBuffer: boolean;
    webAssembly: boolean;
    audioWorklet: boolean;
    opfs: boolean;
    opfsSyncAccessHandle: boolean;
    opfsWritableReplace: boolean;
    webMidi: boolean;
  };
  trigger_admitted_count: number;
  trigger_outcome_count: number;
  trigger_rejected_count: number;
  recovery_probe_ready?: boolean;
  [key: string]: unknown;
}

export interface CreatorRuntimeSession {
  start(): Promise<boolean>;
  close(): Promise<boolean>;
  listLocalProjects(): Promise<readonly LocalProjectSummary[]>;
  importProject(
    file: File,
    options: {
      signal: AbortSignal;
      onProgress: (progress: TransferProgress) => void;
    },
  ): Promise<LocalProjectSummary>;
  openProject(
    projectId: string,
    patternId: string,
  ): Promise<unknown>;
  inspectProject(): Promise<ProjectInspectResult | unknown>;
  reloadSnapshot(patternId: string): Promise<unknown>;
  activateAudio(token: unknown): Promise<boolean>;
  suspendAudio(): Promise<boolean>;
  trigger(
    slot: number,
    velocity: number,
    source: RuntimeTriggerSource,
  ): Promise<TriggerAdmission | false>;
  requestMidi(): Promise<boolean>;
  subscribeDiagnostics(listener: (value: RuntimeDiagnostics) => void): () => void;
  subscribeHostState(listener: (state: RuntimeHostState) => void): () => void;
  subscribeRuntimeOutcome(listener: (outcome: RuntimeOutcome) => void): () => void;
  diagnostics(): RuntimeDiagnostics;
}

export interface CreatorSampleRuntimeSession extends CreatorRuntimeSession {
  inspectSample(slot: number): Promise<SampleInspect>;
  querySampleQuota(slot: number): Promise<SampleQuota>;
  sampleIngestLimits(): Readonly<SampleIngestLimits>;
  queryWaveform(request: WaveformQuery): Promise<WaveformEnvelope>;
  importAssignSample(
    file: File,
    options: SampleImportOptions,
  ): Promise<SampleCommit>;
  updatePad(request: SampleUpdateRequest): Promise<SampleCommit>;
  resetPad(request: SampleResetRequest): Promise<SampleCommit>;
  setSamplePreview(slot: number, playback: PadPlayback): Promise<boolean>;
  clearSamplePreview(slot: number): Promise<boolean>;
  release(slot: number, source: RuntimeTriggerSource): Promise<boolean>;
  stopPad(slot: number): Promise<boolean>;
  stopAll(): Promise<boolean>;
  retryPrepare(patternId: string): Promise<SnapshotPublication>;
  subscribeVoiceState(listener: (event: RuntimeVoiceState) => void): () => void;
}

export interface CreatorPerformanceRuntimeSession
  extends CreatorSampleRuntimeSession,
    PerformanceRuntimeSession,
    WebPerformanceCaptureSession {}

export type SequenceRecordState = "inactive" | "active" | "switching" | "recoverable";

export interface SequenceStatus {
  state: SequenceRecordState;
  sessionId: string | null;
  patternId: string | null;
  pendingPatternId: string | null;
  expectedRevision: number;
  nextFlushSequence: number;
  pendingEventCount: number;
  effectiveRuntimeFrame: number | null;
}

export interface SequenceMutation extends SequenceStatus {
  committedRevision: number | null;
  replayed: boolean;
  projectRevision: number | null;
}

export interface SequenceRecoveryCandidate {
  sessionId: string;
  patternId: string;
  bars: 1 | 2 | 4 | 8;
  reason: string;
  eventCount: number;
}

export interface SequenceSettingsMutation {
  committedRevision: number;
  projectRevision: number;
  bpm: number;
  quantizeEnabled: boolean;
  swingPercent: number;
  replayed: boolean;
  patternPublication: Readonly<{
    generation: number;
    activationFrame: number;
  }> | null;
}

export interface PatternCreateMutation {
  committedRevision: number;
  projectRevision: number;
  patternId: string;
  bars: 1 | 2 | 4 | 8;
  replayed: boolean;
}

export interface CreatorSequenceRuntimeSession extends CreatorSampleRuntimeSession {
  createPattern(request: {
    patternId: string;
    bars: 1 | 2 | 4 | 8;
    expectedRevision: number;
  }): Promise<PatternCreateMutation>;
  updateSequenceSettings(request: {
    expectedRevision: number;
    sessionId: string | null;
    bpm: number | null;
    quantizeEnabled: boolean | null;
    swingPercent: number | null;
  }): Promise<SequenceSettingsMutation>;
  beginSequence(request: {
    sessionId: string;
    patternId: string;
    expectedRevision: number;
    armedCaptureSlot?: number | null;
  }): Promise<SequenceMutation & {transportAnchor: {
    runtimeFrame: number;
    tickNumerator: number;
    bpm: number;
  }}>;
  disarmSequenceCapture(request: {
    sessionId: string;
    slot: number;
  }): Promise<boolean>;
  flushSequence(request: {sessionId: string; commandId: string}): Promise<SequenceMutation>;
  stopSequence(request: {sessionId: string; commandId: string}): Promise<SequenceMutation>;
  requestPatternSwitch(request: {
    sessionId: string;
    nextPatternId: string;
  }): Promise<SequenceMutation>;
  querySequenceStatus(projectId?: string | null): Promise<SequenceStatus>;
  listSequenceRecovery(projectId?: string | null): Promise<readonly SequenceRecoveryCandidate[]>;
  applySequenceRecovery(request: {
    sessionId: string;
    destinationPatternId: string | null;
  }): Promise<SequenceMutation>;
  discardSequenceRecovery(sessionId: string): Promise<boolean>;
  subscribeSequenceBarBoundary(listener: (event: Readonly<{
    sessionId: string;
    patternId: string;
    runtimeFrame: number;
    generation: number;
  }>) => void): () => boolean;
}

export type RuntimeSessionFactory = () => CreatorRuntimeSession;

export interface TypedRuntimeError extends Error {
  code?: string;
  details?: Readonly<Record<string, unknown>>;
}
import type {
  PerformanceRuntimeSession,
  WebPerformanceCaptureSession,
} from "@lmdj/web-runtime-platform/runtime_types";

export interface SoundSetLicense {
  spdxId: string;
  rightsHolder: string;
  copyright: string;
  // S11-D2 keeps this a required key that is empty for a Set that needs no
  // attribution, so the surface shows the string the manifest declared and
  // never composes one of its own.
  attribution: string;
}

export interface SoundSetArtifact {
  sha256: string;
  mediaType: string;
  byteLength: number;
}

// #799. What an audition returns is the geometry of the bytes the Host played,
// never the bytes: `sourceFrames` is what the Artifact holds and
// `preparedFrames` is what the engine received after resampling, so a Set
// authored at 44.1 kHz reports both and a caller can tell them apart.
export interface SoundSetAuditionGeometry {
  sampleRate: number;
  channels: number;
  sourceFrames: number;
  preparedBytes: number;
  preparedFrames: number;
}

export interface SoundSetAudition {
  setId: string;
  version: string;
  manifestSha256: string;
  // `null` when the set-level demo was auditioned rather than a slot.
  slotIndex: number | null;
  artifact: Readonly<SoundSetArtifact> | null;
  // Whether a voice actually started. The geometry above describes bytes the
  // Facade resolved and decoded, which it does whether or not this Host's
  // engine was in a state to play them: with audio never activated, or with
  // both audition Bank slots still held, an audition answers `ok` and makes no
  // sound. `false` is a normal outcome, not a refusal -- a refusal arrives as a
  // thrown typed error, and this field adds no reason vocabulary of its own.
  played: boolean;
  audio: Readonly<SoundSetAuditionGeometry>;
}

export interface SoundSetOccupiedSlotSummary {
  slot: number;
  role: string;
  name: string;
}

export interface SoundSetSummary {
  setId: string;
  version: string;
  manifestSha256: string;
  name: string;
  publisher: string;
  description: string | null;
  bpm: number | null;
  key: string | null;
  totalBytes: number;
  hasDemo: boolean;
  license: Readonly<SoundSetLicense>;
  occupiedSlots: readonly Readonly<SoundSetOccupiedSlotSummary>[];
}

export interface SoundSetSlotAudio {
  sampleRate: number;
  channels: number;
  sourceFrames: number;
  preparedBytes: number;
  preparedFrames: number;
}

// S11-D12: a Set slot is empty exactly when it carries no `artifact`. There is
// no emptiness flag, because an empty slot is never an instruction to clear
// the Pad it maps to.
export interface SoundSetSlot {
  slot: number;
  role?: string;
  name?: string;
  bpm?: number | null;
  key?: string | null;
  artifact: Readonly<SoundSetArtifact> | null;
  audio?: Readonly<SoundSetSlotAudio>;
}

export interface SoundSetInspect extends SoundSetSummary {
  slots: readonly Readonly<SoundSetSlot>[];
  demo: Readonly<SoundSetArtifact> | null;
}

export interface SoundSetRefusal {
  setId: string;
  version: string;
  manifestSha256: string;
  code: string;
  reason: string | null;
}

export interface SoundSetCatalog {
  catalogAvailable: boolean;
  sets: readonly Readonly<SoundSetSummary>[];
  refused: readonly Readonly<SoundSetRefusal>[];
}

export interface SoundSetProposedPad {
  slotIndex: number;
  pad: number;
  artifact: Readonly<SoundSetArtifact> | null;
}

export interface SoundSetMapPreview {
  bankId: number;
  setId: string;
  version: string;
  manifestSha256: string;
  projectRevision: number;
  proposed: readonly Readonly<SoundSetProposedPad>[];
  collisions: readonly number[];
  kept: readonly number[];
}

export type OccupiedPadPolicy = "keep" | "replace";

export interface SoundSetInstallReceipt {
  bankId: number;
  setId: string;
  version: string;
  manifestSha256: string;
  committedRevision: number;
  replayed: boolean;
  installed: readonly Readonly<{slotIndex: number; pad: number}>[];
  collisions: readonly number[];
  kept: readonly number[];
}

export interface SoundSetIdentity {
  setId: string;
  version: string;
  manifestSha256: string;
}

export interface CreatorSoundSetRuntimeSession extends CreatorRuntimeSession {
  listSoundSets(): Promise<Readonly<SoundSetCatalog>>;
  inspectSoundSet(
    request: Readonly<SoundSetIdentity>,
  ): Promise<Readonly<SoundSetInspect>>;
  // Omitting `slotIndex` auditions the set-level demo; supplying one auditions
  // that slot's Artifact. Both are queries with respect to Project Truth.
  auditionSoundSet(
    request: Readonly<SoundSetIdentity & {slotIndex?: number}>,
  ): Promise<Readonly<SoundSetAudition>>;
  // Idempotent: stopping when nothing is auditioning succeeds.
  stopSoundSetAudition(): Promise<Readonly<{accepted: true}>>;
  previewSoundSetMap(
    request: Readonly<SoundSetIdentity & {bankId: number}>,
  ): Promise<Readonly<SoundSetMapPreview>>;
  installSoundSet(
    request: Readonly<SoundSetIdentity & {
      bankId: number;
      commandId: string;
      expectedRevision: number;
      occupiedPadPolicy?: OccupiedPadPolicy;
    }>,
  ): Promise<Readonly<SoundSetInstallReceipt>>;
}
