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
