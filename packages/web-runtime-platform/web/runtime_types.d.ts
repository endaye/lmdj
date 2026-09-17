export type SequenceRecordState =
  | "inactive"
  | "active"
  | "switching"
  | "recoverable";

export interface SequenceStatus {
  readonly state: SequenceRecordState;
  readonly sessionId: string | null;
  readonly patternId: string | null;
  readonly pendingPatternId: string | null;
  readonly expectedRevision: number;
  readonly nextFlushSequence: number;
  readonly pendingEventCount: number;
  readonly effectiveRuntimeFrame: number | null;
}

export interface SequenceMutation extends SequenceStatus {
  readonly committedRevision: number | null;
  readonly replayed: boolean;
  readonly projectRevision: number | null;
}

export interface SequenceTransportAnchor {
  readonly runtimeFrame: number;
  readonly tickNumerator: number;
  readonly bpm: number;
}

export interface SequenceBeginResult extends SequenceMutation {
  readonly transportAnchor: SequenceTransportAnchor;
}

export interface SequenceEventResult extends SequenceMutation {
  readonly runtimeFrame: number;
  readonly inputSequence: number;
}

export interface SequencePatternPublication {
  readonly generation: number;
  readonly activationFrame: number;
}

export interface SequenceFlushResult extends SequenceMutation {
  readonly runtimeFrame: number;
  readonly patternPublication: SequencePatternPublication | null;
}

export interface SequenceSwitchResult extends SequenceMutation {
  readonly patternPublication: SequencePatternPublication;
}

export interface SequenceRecoveryCandidate {
  readonly sessionId: string;
  readonly patternId: string;
  readonly bars: 1 | 2 | 4 | 8;
  readonly reason: string;
  readonly eventCount: number;
}

export type PatternTransportPhase =
  | "idle"
  | "preparing"
  | "awaiting_audio"
  | "flushing"
  | "reconciling"
  | "error";

export type PatternTransportIntent = "play_stop" | "record";

export interface PatternTransportStatus {
  readonly engaged: boolean;
  readonly playing: boolean;
  readonly recording: boolean;
  readonly phase: PatternTransportPhase;
  readonly runtimeGeneration: number;
  readonly transportEpoch: number;
  readonly originFrame: number;
  readonly commandId: string | null;
  readonly publicationPending: boolean;
  readonly error: Readonly<{
    code: string;
    message: string;
    details: Readonly<Record<string, unknown>>;
  }> | null;
}

export interface PatternTransportRequest {
  readonly sessionId: string;
  readonly projectId: string;
  readonly commandId: string;
  readonly expectedEpoch: number;
  readonly intent: PatternTransportIntent;
  readonly expectedRevision: number | null;
}

export interface PatternTransportTicket {
  readonly sessionId: string;
  readonly commandId: string;
  readonly submit: "accepted" | "replayed";
  readonly status: PatternTransportStatus;
}

export interface PatternTransportRuntimeSession {
  requestPatternTransport(
    request: PatternTransportRequest,
  ): Promise<PatternTransportTicket>;
  inspectPatternTransport(sessionId: string): Promise<PatternTransportStatus>;
}

export interface SequenceRuntimeSession {
  createPattern(request: {
    readonly patternId: string;
    readonly bars: 1 | 2 | 4 | 8;
    readonly expectedRevision: number;
  }): Promise<Readonly<{
    committedRevision: number;
    patternId: string;
    bars: 1 | 2 | 4 | 8;
    replayed: boolean;
    projectRevision: number;
  }>>;
  updateSequenceSettings(request: {
    readonly expectedRevision: number;
    readonly sessionId: string | null;
    readonly bpm: number | null;
    readonly quantizeEnabled: boolean | null;
    readonly swingPercent: number | null;
  }): Promise<Readonly<{
    committedRevision: number;
    bpm: number;
    quantizeEnabled: boolean;
    swingPercent: number;
    replayed: boolean;
    patternPublication: SequencePatternPublication | null;
    projectRevision: number;
  }>>;
  subscribeSequenceBarBoundary(
    listener: (event: Readonly<{
      sessionId: string;
      patternId: string;
      runtimeFrame: number;
      generation: number;
    }>) => void,
  ): () => boolean;
  beginSequence(request: {
    readonly sessionId: string;
    readonly patternId: string;
    readonly expectedRevision: number;
    readonly armedCaptureSlot?: number | null;
  }): Promise<SequenceBeginResult>;
  disarmSequenceCapture(request: {
    readonly sessionId: string;
    readonly slot: number;
  }): Promise<boolean>;
  recordSequenceEvent(request: {
    readonly sessionId: string;
    readonly slot: number;
    readonly velocity: number;
    readonly pressed: boolean;
  }): Promise<SequenceEventResult>;
  flushSequence(request: {
    readonly sessionId: string;
    readonly commandId: string;
  }): Promise<SequenceFlushResult>;
  stopSequence(request: {
    readonly sessionId: string;
    readonly commandId: string;
  }): Promise<SequenceFlushResult>;
  requestPatternSwitch(request: {
    readonly sessionId: string;
    readonly nextPatternId: string;
  }): Promise<SequenceSwitchResult>;
  querySequenceStatus(projectId?: string | null): Promise<SequenceStatus>;
  listSequenceRecovery(
    projectId?: string | null,
  ): Promise<readonly SequenceRecoveryCandidate[]>;
  applySequenceRecovery(request: {
    readonly sessionId: string;
    readonly destinationPatternId: string | null;
  }): Promise<SequenceMutation>;
  discardSequenceRecovery(sessionId: string): Promise<boolean>;
}

export interface PerformanceMasterCaptureConfig {
  readonly performRecordingFrames: number;
  readonly performRecordingQueueBatches: number;
}

export interface PerformanceMasterCaptureError {
  readonly code:
    | "capture-unsupported"
    | "tap-initialization-failed"
    | "tap-processor-failed";
  readonly message: string;
}

export type PerformanceMasterCaptureStatus =
  | {readonly state: "unconfigured"; readonly config: null; readonly error: null}
  | {readonly state: "configured"; readonly config: PerformanceMasterCaptureConfig; readonly error: null}
  | {readonly state: "ready"; readonly config: PerformanceMasterCaptureConfig; readonly error: null}
  | {readonly state: "unavailable"; readonly config: PerformanceMasterCaptureConfig; readonly error: PerformanceMasterCaptureError};

export interface PerformanceMasterCaptureSink {
  onBatch(channels: readonly [Float32Array, Float32Array]): void;
  onStopped(): void;
  onFailure(reason: "tap-failure", droppedFrames: number): void;
}

export interface PerformanceMasterCapture {
  stop(): Promise<void>;
}

export interface WebPerformanceCaptureSession {
  performanceMasterCaptureStatus(): PerformanceMasterCaptureStatus;
  subscribePerformanceMasterCaptureStatus(
    listener: (status: PerformanceMasterCaptureStatus) => void,
  ): () => void;
  startPerformanceMasterCapture(
    sink: PerformanceMasterCaptureSink,
  ): Promise<PerformanceMasterCapture>;
}

export type PerformanceFx =
  | "filter"
  | "delay"
  | "reverb"
  | "stutter"
  | "gate"
  | "reverse"
  | "crush"
  | "cutter";

export type PerformanceRawEvent =
  | Readonly<{
      kind: "pad_press";
      gestureId: string;
      slot: number;
      velocity: number;
    }>
  | Readonly<{kind: "pad_release"; gestureId: string; slot: number}>
  | Readonly<{
      kind: "fx_engage" | "fx_move";
      gestureId: string;
      fx: PerformanceFx;
      value: number;
    }>
  | Readonly<{
      kind: "fx_release";
      gestureId: string;
      fx: PerformanceFx;
    }>
  | Readonly<{kind: "hold_on" | "hold_off"}>;

export interface PerformanceArtifact {
  readonly sha256: string;
  readonly mediaType: "audio/wav";
  readonly byteLength: number;
}

export interface PerformanceLifecycleResult {
  readonly performanceId: string;
  readonly committedRevision: number;
  readonly replayed: boolean;
  readonly projectRevision: number;
}

export interface PerformanceRecordStatus {
  readonly state: "idle" | "active" | "stopped" | "recovery_required";
  readonly sessionId: string | null;
  readonly performanceId: string | null;
  readonly journalRevision: number;
  readonly nextFlushSequence: number;
  readonly pendingEventCount: number;
  readonly openPadGestures: number;
  readonly openFxGestures: number;
  readonly hold: boolean;
  readonly pendingLaunch: Readonly<{
    requestId: string;
    patternSlot: number;
    targetTick: number;
    claimed: boolean;
  }> | null;
  readonly lastLaunchAck: Readonly<{
    requestId: string;
    patternSlot: number;
    effectiveTick: number;
  }> | null;
  readonly projectRevision: null;
}

export interface PerformanceReplayStatus {
  readonly replayId: string;
  readonly state: "playing" | "stopped" | "complete";
  readonly resolvedRevision: number;
  readonly eventCursor: number;
  readonly eventCount: number;
  readonly projectRevision: null;
}

export interface PerformanceRuntimeSession {
  assignPatternSlot(request: Readonly<{
    expectedRevision: number;
    patternSlot: number;
    patternId: string;
  }>): Promise<Readonly<{
    patternSlot: number;
    patternId: string;
    committedRevision: number;
    replayed: boolean;
    projectRevision: number;
  }>>;
  clearPatternSlot(request: Readonly<{
    expectedRevision: number;
    patternSlot: number;
  }>): Promise<Readonly<{
    patternSlot: number;
    patternId: null;
    committedRevision: number;
    replayed: boolean;
    projectRevision: number;
  }>>;
  movePatternSlot(request: Readonly<{
    expectedRevision: number;
    fromSlot: number;
    toSlot: number;
  }>): Promise<Readonly<{
    fromSlot: number;
    toSlot: number;
    patternId: string;
    committedRevision: number;
    replayed: boolean;
    projectRevision: number;
  }>>;
  listPerformances(): Promise<readonly Readonly<{
    performanceId: string;
    name: string;
    createdBpm: number;
    recordingArtifact: PerformanceArtifact | null;
    eventCount: number;
  }>[]>;
  inspectPerformance(performanceId: string): Promise<Readonly<{
    id: string;
    name: string;
    createdBpm: number;
    recordingArtifact: PerformanceArtifact | null;
    events: readonly Readonly<Record<string, unknown>>[];
    projectRevision: number;
  }>>;
  beginPerformanceRecording(request: Readonly<{
    sessionId: string;
    performanceId: string;
    expectedRevision: number;
  }>): Promise<PerformanceLifecycleResult>;
  recordPerformanceEvent(request: Readonly<{
    sessionId: string;
    eventId: string;
    event: PerformanceRawEvent;
  }>): Promise<Readonly<{
    eventId: string;
    acceptedTick: number;
    inputSequence: number;
    coalesced: boolean;
    replayed: boolean;
    projectRevision: null;
  }>>;
  requestPerformancePatternLaunch(request: Readonly<{
    sessionId: string;
    requestId: string;
    patternSlot: number;
  }>): Promise<Readonly<{
    requestId: string;
    state: "pending";
    targetTick: number;
    projectRevision: null;
  }>>;
  flushPerformanceRecording(request: Readonly<{
    sessionId: string;
    commandId: string;
  }>): Promise<PerformanceLifecycleResult>;
  stopPerformanceRecording(request: Readonly<{
    sessionId: string;
    requestId: string;
  }>): Promise<Readonly<{
    requestId: string;
    sessionId: string;
    performanceId: string;
    state: "stopped";
    pendingEventCount: number;
    replayed: boolean;
    projectRevision: null;
  }>>;
  queryPerformanceRecordingStatus(): Promise<PerformanceRecordStatus>;
  savePerformance(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
    name: string;
    recordingArtifact: PerformanceArtifact | null;
  }>): Promise<PerformanceLifecycleResult>;
  discardPerformance(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
  }>): Promise<PerformanceLifecycleResult>;
  listPerformanceRecovery(): Promise<readonly Readonly<{
    sessionId: string;
    performanceId: string;
    reason: string;
    durableEventCount: number;
    pendingEventCount: number;
    fingerprint: string;
  }>[]>;
  applyPerformanceRecovery(request: Readonly<{
    expectedRevision: number;
    sessionId: string;
  }>): Promise<PerformanceLifecycleResult>;
  discardPerformanceRecovery(request: Readonly<{
    sessionId: string;
    requestId: string;
  }>): Promise<Readonly<{
    requestId: string;
    sessionId: string;
    performanceId: string;
    state: "stopped";
    pendingEventCount: number;
    replayed: boolean;
    projectRevision: null;
  }>>;
  renamePerformance(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
    name: string;
  }>): Promise<PerformanceLifecycleResult>;
  deletePerformance(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
  }>): Promise<PerformanceLifecycleResult>;
  bindPerformanceRecording(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
    recordingArtifact: PerformanceArtifact;
  }>): Promise<PerformanceLifecycleResult>;
  beginPerformanceReplay(request: Readonly<{
    replayId: string;
    performanceId: string;
  }>): Promise<PerformanceReplayStatus>;
  stopPerformanceReplay(request: Readonly<{
    replayId: string;
    requestId: string;
  }>): Promise<PerformanceReplayStatus & Readonly<{
    requestId: string;
    replayed: boolean;
  }>>;
  queryPerformanceReplayStatus(replayId: string): Promise<PerformanceReplayStatus>;
  commitPerformanceResample(request: Readonly<{
    expectedRevision: number;
    performanceId: string;
    sourceStartFrame: number;
    sourceEndFrame: number;
    targetSlot: number;
  }>): Promise<Readonly<{
    performanceId: string;
    committedRevision: number;
    runtimePrepareRequired: true;
    projectRevision: number;
  }>>;
}

/** Programmatic Provider request; owner paths are supplied by the retained Host. */
export interface ProviderRunRequest {
  attempt_id: string;
  capability: string;
  inputs: readonly {
    port: string;
    artifact: {sha256: string; media_type: string; byte_length: number};
  }[];
  input_owners?: readonly {
    port: string;
    occurrence: number;
    project_id: string;
    asset_id: string;
  }[];
  parameters: Record<string, unknown>;
  data_classification: string;
  platform: string;
  region: string;
  required_permissions: readonly string[];
}


export interface CandidateRunRequest {
  job_id: string; attempt_id: string; project_id: string; asset_id: string;
  expected_revision: number; parameters: Record<string, unknown>;
  data_classification: string; platform: string; region: string;
  required_permissions: readonly string[];
}
export interface CandidateAuditionRequest {
  project_id: string; expected_revision: number; job_id: string; set_id: string; candidate_id: string;
}
export interface CandidateSelection { candidate_id: string; bank: number; pad: number; }
export interface CandidateAdoptRequest {
  project_id: string; expected_revision: number; command_id: string;
  job_id: string; set_id: string; selections: readonly CandidateSelection[];
}
export interface CandidateArtifact { sha256: string; media_type: string; byte_length: number; }
export interface CandidateSource {
  project_id: string; asset_id: string; project_revision: number;
  artifact: CandidateArtifact; frame_rate: number; frame_count: number;
}
export interface CandidateIntent {
  attempt_id: string; source: CandidateSource; parameters_sha256: string;
  data_classification: string; platform: string; region: string; required_permissions: readonly string[];
}
export interface CandidateRecipe {
  candidate_id: string; kind: "slice_interval_v1"; start_frame: number; end_frame: number; frame_rate: number;
}
export interface CandidateSet {
  set_id: string; status: "active" | "superseded" | "discarded";
  attempt_id: string; sdk_candidate_id: string; source: CandidateSource;
  output_artifact: CandidateArtifact;
  capability: {id: string; contract: string; version: string};
  provider: {id: string; version: string; artifact_sha256: string};
  model_identity: {id: string; version: string; artifact_sha256: string} | null;
  parameters_sha256: string; recipes: readonly CandidateRecipe[];
}
export interface CandidateJobResult {
  job_id: string; active_set_id: string | null; project_revision: null;
  history: readonly {intent: CandidateIntent; set_id: string;
    status: "pending" | "succeeded" | "failed" | "interrupted" | "cancelled"}[];
  sets: readonly CandidateSet[];
}
export interface CandidateAuditionResult {
  job_id: string; set_id: string; candidate_id: string; artifact: CandidateArtifact;
  sample_rate: number; channels: number; source_frames: number; project_revision: number; played: boolean;
}
export interface CandidateAdoptResult {
  set_id: string; adopted: readonly (CandidateSelection & {asset_id: string})[]; project_revision: number;
}
export interface CandidateRuntimeSession {
  runCandidateJob(request: CandidateRunRequest): Promise<CandidateJobResult>;
  inspectCandidateJob(jobId: string): Promise<CandidateJobResult>;
  cancelCandidateJob(jobId: string, attemptId: string): Promise<CandidateJobResult>;
  discardCandidateSet(jobId: string, setId: string): Promise<CandidateJobResult>;
  auditionCandidate(request: CandidateAuditionRequest): Promise<CandidateAuditionResult>;
  stopCandidateAudition(): Promise<{accepted: true}>;
  adoptCandidates(request: CandidateAdoptRequest): Promise<CandidateAdoptResult>;
}
