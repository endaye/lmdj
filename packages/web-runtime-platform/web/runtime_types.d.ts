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
  /** The Engine's rendered frame when the Host read this status. */
  readonly runtimeFrame: number;
  /** When the Session received it, on the `performance.now()` clock. */
  readonly observedAtMilliseconds: number;
  readonly commandId: string | null;
  readonly publicationPending: boolean;
  /** The Pattern the Engine is playing, or null before one is published. */
  readonly currentPatternId: string | null;
  /**
   * The latest queued switch while playing, including recording. This is a
   * Native selection observation, not a durable segment acknowledgment.
   */
  readonly pendingSwitch: Readonly<{
    patternId: string;
    activationFrame: number;
  }> | null;
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

export interface TransportPatternSwitchRequest {
  readonly patternId: string;
  readonly requestId: string;
  /** Device preference; omission retains the legacy next-Bar boundary. */
  readonly snap?: "beat" | "bar" | "pattern_end";
}

/**
 * Switches the playing transport's Pattern at the selected engine boundary. A
 * request for the Pattern already playing withdraws any queued switch and
 * answers `activationFrame: null`. Recording continues across accepted switches;
 * old-segment persistence and retained input completion progress separately.
 * Material/I/O/capacity refusal has no Native publication effect. The request
 * ID is advisory and is not a durable replay/receipt identity.
 */
export interface TransportPatternSwitchResult {
  readonly patternId: string;
  readonly activationFrame: number | null;
}

export interface PatternTransportTicket {
  readonly sessionId: string;
  readonly commandId: string;
  readonly submit: "accepted" | "replayed";
  readonly status: PatternTransportStatus;
}

/** Canonical nonzero decimal; exact uint64, or uint60 for a schedule serial. */
export type PatternTransportDecimalIdentity = string;

export interface PatternCountInCapabilities {
  readonly supported: boolean;
  readonly negotiated: boolean;
  readonly outputReady: boolean;
  readonly runtimeGeneration: PatternTransportDecimalIdentity | null;
  readonly frameEpoch: PatternTransportDecimalIdentity | null;
  readonly nextSerial: PatternTransportDecimalIdentity | null;
  readonly inputCapacity: number;
}

export interface PatternCountInTicket {
  readonly sessionId: string;
  readonly commandId: string;
  readonly runtimeGeneration: PatternTransportDecimalIdentity;
  readonly frameEpoch: PatternTransportDecimalIdentity;
  readonly scheduleSerial: PatternTransportDecimalIdentity;
}

export interface PatternCountInRequest extends PatternCountInTicket {
  readonly projectId: string;
  readonly expectedEpoch: PatternTransportDecimalIdentity;
  readonly bars: 1 | 2;
  readonly expectedRevision: number | null;
}

export interface PatternCountInReceipt {
  readonly runtimeGeneration: PatternTransportDecimalIdentity;
  readonly frameEpoch: PatternTransportDecimalIdentity;
  readonly scheduleSerial: PatternTransportDecimalIdentity;
  readonly transportEpoch: PatternTransportDecimalIdentity;
  readonly patternGeneration: PatternTransportDecimalIdentity;
  readonly patternId: string;
  readonly result: "applied" | "cancelled" | "refused";
  /** Absent for an unapplied cancellation or refused intent. */
  readonly effectiveFrame: number | null;
  readonly originFrame: number | null;
  readonly playing: boolean;
}

export interface PatternCountInStatus {
  readonly ticket: PatternCountInTicket | null;
  readonly countIn: Readonly<{
    runtimeGeneration: PatternTransportDecimalIdentity;
    frameEpoch: PatternTransportDecimalIdentity;
    scheduleSerial: PatternTransportDecimalIdentity;
    phase: "empty" | "submitted" | "preparing" | "cancel_preparing" | "armed" |
      "starting" | "applied" | "cancelled" | "failing" | "refused";
    bars: 1 | 2;
    bpm: number | null;
    barFrames: number | null;
    countInFrame: number | null;
    /** Planned native boundary; only an Applied receipt proves actual start. */
    startFrame: number | null;
  }> | null;
  readonly startReceipt: PatternCountInReceipt | null;
  readonly cancelReceipt: PatternCountInReceipt | null;
  readonly openingPending: boolean;
  readonly openingComplete: boolean;
  readonly observedAtMilliseconds: number;
  readonly error: PatternTransportStatus["error"];
}

export interface PatternCountInAdmission {
  readonly submit: "accepted" | "replayed";
  readonly ticket: PatternCountInTicket;
  readonly status: PatternCountInStatus;
}

export interface PatternCountInCancel {
  readonly ticket: PatternCountInTicket;
  readonly projectId: string;
  readonly commandId: string;
  readonly expectedEpoch: PatternTransportDecimalIdentity;
  readonly intent: PatternTransportIntent;
}

export interface PatternTransportRuntimeSession {
  requestPatternInput(request: PatternInputRequest): Promise<PatternInputAdmission>;
  inspectPatternInput(ticket: PatternInputTicket, consume?: boolean): Promise<PatternInputStatus>;
  queryPatternCountInCapabilities(): Promise<PatternCountInCapabilities>;
  /** Direct monitoring preference for Native's optional downbeat at scheduled S. */
  setCountInMetronome(enabled: boolean): void;
  /** Returns admission promptly; inspect observes native and durable progress. */
  requestPatternCountIn(request: PatternCountInRequest): Promise<PatternCountInAdmission>;
  inspectPatternCountIn(ticket: PatternCountInTicket, consume?: boolean): Promise<PatternCountInStatus>;
  cancelPatternCountIn(request: PatternCountInCancel): Promise<PatternCountInAdmission>;
  requestPatternTransport(
    request: PatternTransportRequest,
  ): Promise<PatternTransportTicket>;
  inspectPatternTransport(sessionId: string): Promise<PatternTransportStatus>;
  requestTransportPatternSwitch(
    request: TransportPatternSwitchRequest,
  ): Promise<TransportPatternSwitchResult>;
}

export interface PatternInputTicket {
  readonly commandId: string;
  readonly runtimeGeneration: PatternTransportDecimalIdentity;
  readonly frameEpoch: PatternTransportDecimalIdentity;
  readonly ticket: PatternTransportDecimalIdentity;
}
export interface PatternInputRequest {
  readonly commandId: string;
  readonly runtimeGeneration: PatternTransportDecimalIdentity;
  readonly frameEpoch: PatternTransportDecimalIdentity;
  readonly inputSerial: PatternTransportDecimalIdentity;
  readonly slot: number;
  readonly velocity: number;
  readonly kind: "press" | "release";
  readonly held: boolean;
  readonly heldPressSequence: PatternTransportDecimalIdentity | null;
}
export interface PatternInputAuthority {
  readonly recording: boolean;
  readonly scheduleSerial: PatternTransportDecimalIdentity | null;
  readonly transportEpoch: PatternTransportDecimalIdentity | null;
}
export interface PatternInputStatus {
  readonly ticket: PatternInputTicket;
  readonly admission: Readonly<{sequence: PatternTransportDecimalIdentity;
    acceptanceOrdinal: PatternTransportDecimalIdentity; authority: PatternInputAuthority}>;
  readonly nativeResult: Readonly<{runtimeGeneration: PatternTransportDecimalIdentity;
    frameEpoch: PatternTransportDecimalIdentity; sequence: PatternTransportDecimalIdentity;
    heldPressSequence: PatternTransportDecimalIdentity | null; acceptanceOrdinal: PatternTransportDecimalIdentity;
    runtimeFrame: number; slot: number; authority: PatternInputAuthority;
    disposition: "voice_started" | "voice_capacity" | "toggle_stopped" | "muted_no_voice" |
      "release_applied" | "release_no_voice" | "invalidated_before_consume"}> | null;
  readonly durableSettled: boolean;
  readonly retained: boolean;
  readonly complete: boolean;
  readonly expired: boolean;
  readonly error: Readonly<{code: string; message: string; details: Readonly<Record<string, unknown>>}> | null;
}
export interface PatternInputAdmission {
  readonly ticket: PatternInputTicket;
  readonly status: PatternInputStatus;
}
/** Local Session lifecycle; these waits introduce no Native RPC or wire DTO. */
export interface RuntimeLifecycleSession {
  start(): Promise<boolean>;
  /** True only for a clean normal close; a fatal close still returns false. */
  close(): Promise<boolean>;
  /**
   * Observes this Session's already initiated cleanup. True requires actual
   * owner/backend retirement and SDK teardown. Failure is false; unknown
   * retained debt remains pending. Before cleanup begins returns false and
   * starts no owner action. Older healthy normal closure and a known empty,
   * never-loaded Session retain their separate closure contracts.
   */
  waitForTerminalCleanup(): Promise<boolean>;
}

/** Local physical ownership only; neither method manufactures a Native ACK. */
export interface InputGestureLease {
  cancelUnsubmittedPattern(): void;
  releasePhysical(): void;
}

/** Same already-running frozen Session; never a second input/controller owner. */
export interface RuntimeSessionNamespace {
  readonly session: RuntimeLifecycleSession & PatternTransportRuntimeSession & MonitorOutputSession &
    WebAudioClockSession & WebPerformanceCaptureSession & Readonly<{
    /** Synchronous combined admission before caller queues retain this press. */
    reserveInputGesture(key: object, slot: number, source?: "pointer" | "keyboard" | "midi"):
      InputGestureLease | null;
    /** Opaque local reference; exact hold correlation requires the negotiated input profile. */
    trigger(slot: number, velocity: number, source?: "pointer" | "keyboard" | "midi", gestureKey?: object):
      Promise<false | Readonly<{sequence: number; slot: number; velocity: number; source: "pointer" | "keyboard" | "midi"}>>;
    release(slot: number, source: "pointer" | "keyboard" | "midi", gestureKey?: object): Promise<boolean>;
  }>;
  readonly patternTransport: PatternTransportRuntimeSession;
}

export interface PatternEventKeyRequest {
  /** Flat Pad slot, 0..63. */
  readonly slot: number;
  readonly onsetTick: number;
}

export interface PatternEventRequest extends PatternEventKeyRequest {
  readonly durationTick: number;
  readonly velocity: number;
}

export type PatternLengthResult = Readonly<{
  committedRevision: number;
  projectRevision: number;
  patternId: string;
  bars: 1 | 2 | 4 | 8;
  replayed: boolean;
  publication: "none" | "published" | "deferred" | "failed";
  patternPublication: Readonly<{generation: number; activationFrame: number}> | null;
  snapshotError: Readonly<{code: string; message: string; details: Readonly<Record<string, unknown>>}> | null;
}>;

export interface SequenceRuntimeSession {
  /**
   * Atomically removes the keyed events, then puts each event by key.
   * `publication` is "none" when the edited Pattern is not the Runtime's
   * current one, "published" when it was swapped in while stopped, "live"
   * when it was swapped in place while playing, "deferred" when every
   * Pattern slot was held by a sounding retiring view (it swaps in place by
   * itself once one frees), and "failed" when the committed edit's view
   * could not swap (`snapshotError`).
   */
  editPatternEvents(request: {
    readonly patternId: string;
    readonly expectedRevision: number;
    readonly remove: readonly PatternEventKeyRequest[];
    readonly put: readonly PatternEventRequest[];
  }): Promise<Readonly<{
    committedRevision: number;
    projectRevision: number;
    patternId: string;
    replayed: boolean;
    publication: "none" | "published" | "live" | "deferred" | "failed";
    patternPublication: Readonly<{generation: number; activationFrame: number}> | null;
    snapshotError: Readonly<{code: string; message: string; details: Readonly<Record<string, unknown>>}> | null;
  }>>;
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
  /**
   * Changes a Pattern's length (#1823). Lengthening leaves the added bars
   * empty; shortening removes notes from the new end on and cuts a note
   * crossing it. The current length is refused and records nothing. Refused
   * with HOST_STATE_INVALID while the Pattern transport plays
   * (`pattern_transport_playing`), records (`sequence_session_active`) or
   * settles a command (`pattern_transport_busy`). `publication` is "none"
   * when the Pattern is not the Runtime's current one, "published" when its
   * view was republished at once, "deferred" when it swaps once a Pattern
   * slot frees or a replay ends, and "failed" (`snapshotError`) when the
   * committed change's view could not swap.
   */
  resizePattern(request: {
    readonly patternId: string;
    readonly bars: 1 | 2 | 4 | 8;
    readonly expectedRevision: number;
  }): Promise<PatternLengthResult>;
  /** Doubles a Pattern and repeats its notes; refused at 8 bars. */
  doubleUpPattern(request: {
    readonly patternId: string;
    readonly expectedRevision: number;
  }): Promise<PatternLengthResult>;
  /**
   * Copies a Pattern's length and notes to `patternId`. A source in Pattern
   * slot s puts the copy in the lowest empty slot after s (`patternSlot`);
   * otherwise the copy holds no slot. Publishes nothing.
   */
  copyPattern(request: {
    readonly sourcePatternId: string;
    readonly patternId: string;
    readonly expectedRevision: number;
  }): Promise<Readonly<{
    committedRevision: number;
    projectRevision: number;
    sourcePatternId: string;
    patternId: string;
    patternSlot: number | null;
    replayed: boolean;
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
    binding?: Readonly<{
      controlEpoch: string;
      sessionId: string;
      beginCommandId: string;
    }> | null,
  ): Promise<PerformanceMasterCapture>;
}

/** Host monitoring only: after the capture tap, never authoring or recorded PCM. */
export interface MonitorOutputSession {
  /** Linear amplitude percentage, 0..100; default 100. */
  monitorVolume(): number;
  /** Available after graph creation, null before activation or after close. */
  monitorDestination(): AudioNode | null;
  /** Synchronous, no activation or transport; invalid/terminal updates throw. */
  setMonitorVolume(value: number): void;
}

/**
 * One synchronous sample of the session audio clock.
 *
 * The engine frame counter resets to zero inside `audio.activate` and then
 * advances exactly 128 frames per audio callback while the gate is open.
 * `engineEpochHeartbeat` is the heartbeat immediately preceding Native's first
 * open-gate render for the acknowledged activation. Current runtimes publish it
 * before that callback's positive ACK, so activation/profile RPC latency cannot
 * move the epoch. Within that epoch (using uint32 modular heartbeat subtraction):
 *
 *   engineFrame = (callbackHeartbeat − engineEpochHeartbeat) × 128
 *
 * The AudioContext/current-heartbeat pair is sampled on Browser Main, so its
 * conversion can differ by a render quantum at the sample edge. A manual
 * suspend/activate or interruption recovery establishes a new Native epoch.
 * Legacy runtimes without the additive Native getter retain their approximate
 * heartbeat sample after the activation reply, with no Native phase guarantee.
 */
export interface AudioClockSample {
  readonly contextTimeSeconds: number;
  readonly callbackHeartbeat: number;
  readonly engineEpochHeartbeat: number;
}

export interface WebAudioClockSession {
  /**
   * Synchronously samples the audio clock. Throws HOST_STATE_INVALID before
   * the first activation and whenever audio is not running.
   */
  sampleAudioClock(): AudioClockSample;
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

// Session-free live FX gesture (#1674): the FX subset of PerformanceRawEvent
// without the journal's gesture identity. Applied to the master bus only.
export type PerformanceFxGesture =
  | Readonly<{
      kind: "fx_engage" | "fx_move";
      fx: PerformanceFx;
      value: number;
    }>
  | Readonly<{kind: "fx_release"; fx: PerformanceFx}>
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

// ---------------------------------------------------------------------------
// D0/W1 headered live-control types (lmdj.project.v5 5.4.1). Opaque Core
// sequences are canonical decimal strings; Pad slots are 0..63 safe integers.
// ---------------------------------------------------------------------------

export type PerformanceFilterTypeName = "lp" | "hp" | "bp";

export type PerformanceLiveControlIntent =
  | Readonly<{
      kind: "filter_parameter";
      phase: "engage" | "move";
      parameter: "type";
      value: PerformanceFilterTypeName;
      gestureGeneration?: string;
    }>
  | Readonly<{
      kind: "filter_parameter";
      phase: "engage" | "move";
      parameter: "cutoff_hz";
      value: number;
      gestureGeneration?: string;
    }>
  | Readonly<{
      kind: "filter_parameter";
      phase: "engage" | "move";
      parameter: "resonance_milli";
      value: number;
      gestureGeneration?: string;
    }>
  | Readonly<{kind: "filter_release"; gestureGeneration: string}>
  | Readonly<{
      kind: "fx_parameter";
      phase: "engage" | "move";
      fx: PerformanceFx;
      value: number;
      gestureGeneration?: string;
    }>
  | Readonly<{
      kind: "fx_release";
      fx: PerformanceFx;
      gestureGeneration: string;
    }>
  | Readonly<{kind: "pad_mute" | "pad_solo"; slot: number; enabled: boolean}>
  | Readonly<{kind: "clear_pad_gates"}>
  | Readonly<{kind: "hold_on" | "hold_off"}>;

export type PerformanceLiveFilterState =
  | Readonly<{mode: "legacy"; engaged: boolean; frozen: boolean; value: number}>
  | Readonly<{
      mode: "independent";
      engaged: boolean;
      frozen: boolean;
      type: PerformanceFilterTypeName;
      cutoffHz: number;
      resonanceMilli: number;
    }>;

export interface PerformanceLiveFxGateState {
  readonly engaged: boolean;
  readonly frozen: boolean;
  readonly value: number;
}

export interface PerformanceLiveState {
  readonly hold: boolean;
  readonly filter: PerformanceLiveFilterState;
  readonly otherFx: Readonly<
    Record<Exclude<PerformanceFx, "filter">, PerformanceLiveFxGateState>
  >;
  readonly mutedSlots: readonly number[];
  readonly soloSlots: readonly number[];
}

export type PerformanceLiveStatus =
  | Readonly<{
      available: true;
      controlEpoch: string;
      accepted: PerformanceLiveState;
      applied: PerformanceLiveState;
      runtimeGenerations: Readonly<Record<PerformanceFx, string | null>>;
      acceptedControlSequence: string;
      appliedControlSequence: string;
      resetPending: boolean;
      beginPending: boolean;
      projectRevision: null;
    }>
  | Readonly<{
      available: false;
      controlEpoch: null;
      accepted: null;
      applied: null;
      acceptedControlSequence: null;
      appliedControlSequence: null;
      resetPending: false;
      beginPending: false;
      projectRevision: null;
    }>;

export interface PerformanceLiveControlResult {
  readonly commandId: string;
  readonly controlEpoch: string;
  readonly controlSequence: string;
  readonly gestureGeneration: string | null;
  readonly accepted: true;
  readonly applied: boolean;
  readonly replayed: boolean;
  readonly projectRevision: null;
}

export interface PerformanceFxBinding {
  readonly fx: PerformanceFx;
  readonly gestureGeneration: string;
  readonly recordingGestureId: string;
}

export interface PerformanceHeaderedBeginResult extends PerformanceLifecycleResult {
  readonly profile: "header_input_sequence";
  readonly controlEpoch: string;
  readonly coreControlReady: boolean;
  readonly nextRecordingSequence: string;
  readonly fxBindings: readonly PerformanceFxBinding[];
  // Present only when this begin supplied a sink; the exact owned SDK handle.
  readonly capture?: PerformanceMasterCapture;
}

export type PerformanceHeaderedEvent =
  | Exclude<PerformanceRawEvent, {kind: "fx_engage" | "fx_move" | "fx_release"}>
  | Readonly<{
      kind: "fx_engage";
      fx: PerformanceFx;
      value: number;
      // Core issues these identities; callers cannot supply legacy bindings.
      gestureId?: never;
      gestureGeneration?: never;
    }>
  | Readonly<{
      kind: "fx_move";
      fx: PerformanceFx;
      gestureId: string;
      gestureGeneration: string;
      value: number;
    }>
  | Readonly<{
      kind: "fx_release";
      fx: PerformanceFx;
      gestureId: string;
      gestureGeneration: string;
      value?: never;
    }>
  | Readonly<{
      kind: "filter_parameter";
      phase: "engage" | "move";
      parameter: "type" | "cutoff_hz" | "resonance_milli";
      value: number | PerformanceFilterTypeName;
      gestureId?: string;
      gestureGeneration?: string;
    }>
  | Readonly<{
      kind: "filter_release";
      gestureId: string;
      gestureGeneration: string;
    }>
  | Readonly<{kind: "pad_mute" | "pad_solo"; slot: number; enabled: boolean}>
  | Readonly<{kind: "clear_pad_gates"}>;

export type PerformanceEventResult =
  | Readonly<{
      eventId: string;
      acceptedTick: number;
      inputSequence: number;
      coalesced: boolean;
      replayed: boolean;
      projectRevision: null;
    }>
  | Readonly<{
      eventId: string;
      acceptedTick: number;
      inputSequence: string;
      nextRecordingSequence: string;
      result: "published" | "no_audio";
      coalesced: false;
      gestureGeneration: string | null;
      recordingGestureId: string | null;
      replayed: false;
      projectRevision: null;
    }>
  | Readonly<{
      admission: Readonly<Record<string, unknown>>;
      replayed: true;
      projectRevision: null;
    }>;

export interface PerformanceRuntimeSession {
  // Synchronous local ownership only: no wire admission/ACK. The current SDK
  // supplies this optional companion for Hosts with an ordered event tail.
  // A fresh Press/matching Release is single-use; submit is idempotent and
  // cancelBeforeSubmit succeeds only before that handoff. Original deadlines
  // and physical keys survive the Host wait. Foreign/replay events use the
  // ordinary recordPerformanceEvent API instead, after the original token's
  // handoff; an exact replay cannot bypass a still-prepared Press.
  preparePerformancePadEvent?(request: Readonly<{
    sessionId: string;
    eventId: string;
    event: Extract<PerformanceRawEvent, {kind: "pad_press" | "pad_release"}>;
  }>, physicalKey?: object): Readonly<{
    submit(): Promise<PerformanceEventResult>;
    cancelBeforeSubmit(): boolean;
  }>;
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
  // D0/W1 headered profile: the begin promise resolves only after the Core
  // fence proves the applied header and (when a captureSink is supplied) the
  // real worklet start ACK matches this begin's binding.
  beginPerformanceRecording(request: Readonly<{
    sessionId: string;
    performanceId: string;
    expectedRevision: number;
    controlEpoch: string;
    captureSink?: PerformanceMasterCaptureSink;
  }>): Promise<PerformanceHeaderedBeginResult>;
  recordPerformanceEvent(request: Readonly<{
    sessionId: string;
    eventId: string;
    event: PerformanceRawEvent | PerformanceHeaderedEvent;
  }>, physicalKey?: object): Promise<PerformanceEventResult>;
  applyFxGesture(event: PerformanceFxGesture): Promise<Readonly<{
    applied: true;
  }>>;
  // D0/W1 typed live control: the sessionless producer echoes the Core epoch
  // from queryPerformanceLiveStatus and the CAS window advances per admitted
  // control.
  applyPerformanceLiveControl(request: Readonly<{
    controlEpoch: string;
    intent: PerformanceLiveControlIntent;
  }>): Promise<PerformanceLiveControlResult>;
  queryPerformanceLiveStatus(): Promise<PerformanceLiveStatus>;
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

export interface AuthoringHistoryStatus {
  readonly sessionId: string;
  readonly projectRevision: number;
  readonly undoCount: number;
  readonly redoCount: number;
  readonly undoLabel: string;
  readonly redoLabel: string;
  readonly disabledReason: string;
  readonly canUndo: boolean;
  readonly canRedo: boolean;
}
export interface AuthoringHistoryRequest {
  readonly sessionId: string;
  readonly commandId: string;
  readonly expectedRevision: number;
}
export interface AuthoringHistoryMutation {
  readonly committedRevision: number;
  readonly runtimeRevision: number | null;
  readonly runtimePublished: boolean;
  readonly snapshotError: Readonly<{code: string; message: string; details: Readonly<Record<string, unknown>>}> | null;
}
export interface AuthoringHistoryRuntimeSession {
  inspectAuthoringHistory(): Promise<Readonly<AuthoringHistoryStatus>>;
  undoAuthoring(request: AuthoringHistoryRequest): Promise<Readonly<AuthoringHistoryMutation>>;
  redoAuthoring(request: AuthoringHistoryRequest): Promise<Readonly<AuthoringHistoryMutation>>;
}

/** lmdj.project.v5 5.3.0 Asset category, in palette index order. */
export type PadCategory = "drums" | "bass" | "melodic" | "vocal" | "texture";

/**
 * The Pad colour fields every `project.inspect` Pad carries (#1207). Core
 * resolves `colour`: the override, else the category's palette index, else
 * null (neutral). Hosts draw `colour` and never recompute it.
 */
export interface InspectedPadColour {
  /** The Pad's Asset category, or null when unclassified or empty. */
  readonly category: PadCategory | null;
  /** The user's palette index override, or null. */
  readonly colour_override: number | null;
  /** The effective palette index 0..4, or null for the neutral Pad. */
  readonly colour: number | null;
}

export interface PadAssignmentRequest {
  /** Caller-retained durable identity; an explicit retry keeps every field. */
  readonly commandId: string;
  readonly expectedRevision: number;
  /** Explicit flat destination, 0..63 (A01..D16). */
  readonly slot: number;
  /** Non-null Asset already retained by the current Project. */
  readonly assetId: string;
}

export interface PadAssignmentResult {
  readonly slot: number;
  readonly assetId: string;
  readonly committedRevision: number;
  readonly replayed: boolean;
  readonly projectRevision: number;
  readonly runtimeRevision: number | null;
  readonly runtimePublished: boolean;
  readonly snapshotError: Readonly<{
    code: string;
    message: string;
    details: Readonly<Record<string, unknown>>;
  }> | null;
}

export interface PadAssignmentRuntimeSession {
  /** Known commit and Runtime publication are distinct; no automatic retry. */
  assignPad(request: PadAssignmentRequest): Promise<PadAssignmentResult>;
}

export interface PadColourRuntimeSession {
  /**
   * Sets the Pad's palette index override, or with null restores its
   * category default. Admitted while playing and refused while recording.
   * It changes no audio and publishes nothing.
   */
  setPadColour(request: {
    /** Flat Pad slot, 0..63. */
    readonly slot: number;
    readonly colour: number | null;
    readonly expectedRevision: number;
  }): Promise<Readonly<{
    committedRevision: number;
    projectRevision: number;
    replayed: boolean;
  }>>;
}
