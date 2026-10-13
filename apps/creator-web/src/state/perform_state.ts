import {userMessage} from "./error_messages";
import type {
  PerformanceFilterTypeName,
  PerformanceFx,
  PerformanceHeaderedEvent,
  PerformanceLiveControlIntent,
  PerformanceLiveStatus,
  PerformanceMasterCapture,
  PerformanceMasterCaptureStatus,
  PerformanceRawEvent,
  PerformanceRecordStatus,
  PerformanceReplayStatus,
} from "@lmdj/web-runtime-platform/runtime_types";

import {
  MasterTapBatchQueue,
  type MasterTapFailure,
  type MasterTapListener,
} from "../record/master_tap_source";
import {
  OpfsPerformanceRecordingStorage,
  PerformanceRecordingStore,
} from "../record/performance_recording_store";
import {
  openWavStreamWriter,
  type WavStreamWriter,
  type WavWriterSnapshot,
} from "../record/wav_stream_writer";
import type {CreatorPerformanceRuntimeSession} from "../runtime/runtime_types";
import {selectCanTrigger, type Bank, type CreatorState} from "./creator_state";
import {slotAddress} from "./view_model";

export const PERFORMANCE_FX_ORDER = Object.freeze([
  "filter", "delay", "reverb", "stutter",
  "gate", "reverse", "crush", "cutter",
] as const satisfies readonly PerformanceFx[]);

export interface PerformanceSummary {
  readonly performanceId: string;
  readonly name: string;
  readonly createdBpm: number;
  readonly recordingArtifact: Readonly<{
    sha256: string;
    mediaType: "audio/wav";
    byteLength: number;
  }> | null;
  readonly eventCount: number;
}

export interface PerformanceRecoverySummary {
  readonly sessionId: string;
  readonly performanceId: string;
  readonly reason: string;
  readonly durableEventCount: number;
  readonly pendingEventCount: number;
  readonly fingerprint: string;
}

export type PerformanceRecordingPhase =
  | "idle"
  | "starting"
  | "recording"
  | "flushing"
  | "stopping"
  | "stopped"
  | "saving"
  | "discarding";

// D04 independent Filter: the only units the surface may show are the Core
// ones. The cutoff slider is a 0..1000 log position over 20 Hz–20 kHz; the
// endpoints are exact and the Host never derives Hz from a legacy percentage.
export const FILTER_CUTOFF_MIN_HZ = 20;
export const FILTER_CUTOFF_MAX_HZ = 20000;
export const FILTER_TYPES = Object.freeze([
  "lp", "hp", "bp",
] as const satisfies readonly PerformanceFilterTypeName[]);

export function cutoffPositionToHz(position: number): number {
  const clamped = Math.min(1000, Math.max(0, Math.round(position)));
  if (clamped === 0) return FILTER_CUTOFF_MIN_HZ;
  if (clamped === 1000) return FILTER_CUTOFF_MAX_HZ;
  return Math.round(FILTER_CUTOFF_MIN_HZ * Math.pow(1000, clamped / 1000));
}

export function cutoffHzToPosition(hz: number): number {
  const clamped = Math.min(FILTER_CUTOFF_MAX_HZ,
    Math.max(FILTER_CUTOFF_MIN_HZ, hz));
  return Math.round(1000 * Math.log10(clamped / FILTER_CUTOFF_MIN_HZ) / 3);
}

export interface FilterControlState {
  readonly type: PerformanceFilterTypeName;
  readonly cutoffHz: number;
  readonly resonanceMilli: number;
  readonly engaged: boolean;
  readonly frozen: boolean;
  // "core" is an applied Core readback, "pending" an intent in flight, and
  // "unavailable" the honest state when no typed producer answered.
  readonly provenance: "core" | "pending" | "unavailable";
}

const FILTER_DEFAULT = Object.freeze({
  type: "lp" as const,
  cutoffHz: FILTER_CUTOFF_MAX_HZ,
  resonanceMilli: 0,
  engaged: false,
  frozen: false,
});

export const FILTER_UNAVAILABLE: FilterControlState = Object.freeze({
  ...FILTER_DEFAULT, provenance: "unavailable",
});

type FilterParameter = "type" | "cutoff_hz" | "resonance_milli";

// The typed wire discriminates on parameter; build each member literally so
// neither the Host nor the SDK ever widens a value across parameters.
function filterParameterIntent(
  phase: "engage" | "move",
  parameter: FilterParameter,
  value: number | PerformanceFilterTypeName,
  gestureGeneration?: string,
): PerformanceLiveControlIntent {
  const bound = gestureGeneration === undefined ? {} : {gestureGeneration};
  switch (parameter) {
    case "type":
      return {kind: "filter_parameter", phase, parameter,
        value: value as PerformanceFilterTypeName, ...bound};
    case "cutoff_hz":
      return {kind: "filter_parameter", phase, parameter,
        value: value as number, ...bound};
    case "resonance_milli":
      return {kind: "filter_parameter", phase, parameter,
        value: value as number, ...bound};
  }
}

function filterParameterEvent(
  phase: "engage" | "move",
  parameter: FilterParameter,
  value: number | PerformanceFilterTypeName,
  binding?: Readonly<{gestureId: string; gestureGeneration: string}>,
): PerformanceHeaderedEvent {
  const bound = binding === undefined ? {} : binding;
  switch (parameter) {
    case "type":
      return {kind: "filter_parameter", phase, parameter,
        value: value as PerformanceFilterTypeName, ...bound};
    case "cutoff_hz":
      return {kind: "filter_parameter", phase, parameter,
        value: value as number, ...bound};
    case "resonance_milli":
      return {kind: "filter_parameter", phase, parameter,
        value: value as number, ...bound};
  }
}

// The headered profile journals fx_engage with exactly {kind, fx, value}: the
// Core begin mapping (or the engage receipt) issues both gesture ids, so the
// Host sends none. runtime_types.d.ts is one member short of the wire shape
// the SDK validates; the cast is confined to this helper.
function headeredFxEngage(
  fx: PerformanceFx,
  value: number,
): PerformanceHeaderedEvent {
  return {kind: "fx_engage", fx, value} as PerformanceHeaderedEvent;
}

export interface PerformState {
  readonly bank: Bank;
  readonly captureStatus: PerformanceMasterCaptureStatus;
  readonly recording: Readonly<{
    phase: PerformanceRecordingPhase;
    sessionId: string | null;
    performanceId: string | null;
    expectedRevision: number | null;
    wav: WavWriterSnapshot | null;
  }>;
  readonly pendingLaunch: PerformanceRecordStatus["pendingLaunch"];
  readonly lastLaunchAck: PerformanceRecordStatus["lastLaunchAck"];
  readonly authority: PerformanceRecordStatus | null;
  readonly hold: boolean;
  readonly fx: Readonly<Record<PerformanceFx, number>>;
  readonly filter: FilterControlState;
  readonly liveControl: Readonly<{available: boolean; epoch: string | null}>;
  // A legacy scalar Filter gesture opened before the first live-status answer
  // keeps the legacy fader and encoder until it closes; the typed surface
  // never flips an open gesture mid-route.
  readonly legacyFilterGesture: boolean;
  readonly performances: readonly PerformanceSummary[];
  readonly recovery: readonly PerformanceRecoverySummary[];
  readonly recoveryLoaded: boolean;
  readonly replay: PerformanceReplayStatus | null;
  readonly replayNeutral: boolean;
  readonly recordingNote: string | null;
  readonly wavStatus: string;
  readonly bindingStatus: "unbound" | "binding" | "retry" | "bound";
  readonly recoveryStatus: string;
  readonly resampleStatus: string;
  readonly error: string | null;
}

export type PerformAction =
  | {readonly type: "bank"; readonly bank: Bank}
  | {readonly type: "capture"; readonly status: PerformanceMasterCaptureStatus}
  | {readonly type: "recording"; readonly recording: PerformState["recording"]}
  | {readonly type: "pending-launch";
      readonly pending: PerformState["pendingLaunch"]}
  | {readonly type: "authority"; readonly status: PerformanceRecordStatus}
  | {readonly type: "fx"; readonly fx: PerformanceFx; readonly value: number}
  | {readonly type: "filter"; readonly filter: FilterControlState}
  | {readonly type: "filter-legacy-gesture"; readonly open: boolean}
  | {readonly type: "live-status"; readonly status: PerformanceLiveStatus}
  | {readonly type: "hold"; readonly value: boolean}
  | {readonly type: "performances"; readonly values: readonly PerformanceSummary[]}
  | {readonly type: "recovery"; readonly values: readonly PerformanceRecoverySummary[]}
  | {readonly type: "recovery-checking"}
  | {readonly type: "replay"; readonly replay: PerformanceReplayStatus | null}
  | {readonly type: "neutral"}
  | {readonly type: "session-neutral"}
  | {readonly type: "recording-note"; readonly message: string | null}
  | {readonly type: "wav-status"; readonly message: string}
  | {readonly type: "binding-status"; readonly status: PerformState["bindingStatus"]}
  | {readonly type: "recovery-status"; readonly message: string}
  | {readonly type: "resample-status"; readonly message: string}
  | {readonly type: "error"; readonly message: string | null};

const EMPTY_FX = Object.freeze(Object.fromEntries(
  PERFORMANCE_FX_ORDER.map((fx) => [fx, 500]),
) as Record<PerformanceFx, number>);

function freezeRecording(
  recording: PerformState["recording"],
): PerformState["recording"] {
  return Object.freeze({...recording});
}

export function initialPerformState(
  captureStatus: PerformanceMasterCaptureStatus,
  bank: Bank = 0,
): PerformState {
  return Object.freeze({
    bank,
    captureStatus,
    recording: freezeRecording({phase: "idle", sessionId: null,
      performanceId: null, expectedRevision: null, wav: null}),
    pendingLaunch: null,
    lastLaunchAck: null,
    authority: null,
    hold: false,
    fx: EMPTY_FX,
    filter: FILTER_UNAVAILABLE,
    liveControl: Object.freeze({available: false, epoch: null}),
    legacyFilterGesture: false,
    performances: Object.freeze([]),
    recovery: Object.freeze([]),
    recoveryLoaded: false,
    replay: null,
    replayNeutral: false,
    recordingNote: null,
    wavStatus: "idle",
    bindingStatus: "unbound",
    recoveryStatus: "checking",
    resampleStatus: "idle",
    error: null,
  });
}

export function reducePerform(state: PerformState, action: PerformAction): PerformState {
  switch (action.type) {
    case "bank": return Object.freeze({...state, bank: action.bank});
    case "capture": return Object.freeze({...state, captureStatus: action.status});
    case "recording": return Object.freeze({...state,
      recording: freezeRecording(action.recording)});
    case "pending-launch": return Object.freeze({...state,
      pendingLaunch: action.pending});
    case "authority": {
      const acknowledged = action.status.lastLaunchAck?.requestId ===
        state.pendingLaunch?.requestId;
      return Object.freeze({...state,
        authority: action.status,
        pendingLaunch: action.status.pendingLaunch ??
          (acknowledged ? null : state.pendingLaunch),
        lastLaunchAck: action.status.lastLaunchAck ?? state.lastLaunchAck,
        hold: action.status.hold,
      });
    }
    case "fx": return Object.freeze({...state,
      fx: Object.freeze({...state.fx, [action.fx]: action.value})});
    case "filter": return Object.freeze({...state,
      filter: Object.freeze(action.filter)});
    case "filter-legacy-gesture": return Object.freeze({...state,
      legacyFilterGesture: action.open});
    case "live-status": {
      if (!action.status.available || action.status.applied === null) {
        // Unavailable never fakes a neutral state (W1); the legacy surface
        // keeps its own scalar mirror and the typed panel says unavailable.
        return Object.freeze({...state,
          liveControl: Object.freeze({available: false, epoch: null}),
          filter: FILTER_UNAVAILABLE,
        });
      }
      const applied = action.status.applied;
      const fx: Record<PerformanceFx, number> = {...state.fx};
      for (const [name, gate] of Object.entries(applied.otherFx)) {
        fx[name as Exclude<PerformanceFx, "filter">] = gate.value;
      }
      return Object.freeze({...state,
        liveControl: Object.freeze({
          available: true, epoch: action.status.controlEpoch,
        }),
        filter: Object.freeze(applied.filter.mode === "independent" ? {
          type: applied.filter.type,
          cutoffHz: applied.filter.cutoffHz,
          resonanceMilli: applied.filter.resonanceMilli,
          engaged: applied.filter.engaged,
          frozen: applied.filter.frozen,
          provenance: action.status.appliedControlSequence ===
            action.status.acceptedControlSequence ? "core" as const : "pending" as const,
        } : FILTER_UNAVAILABLE),
        hold: applied.hold,
        fx: Object.freeze(fx),
      });
    }
    case "hold": return Object.freeze({...state, hold: action.value});
    case "performances": return Object.freeze({...state,
      performances: Object.freeze([...action.values])});
    case "recovery": return Object.freeze({...state,
      recovery: Object.freeze([...action.values]), recoveryLoaded: true});
    case "recovery-checking": return Object.freeze({...state, recoveryLoaded: false});
    case "replay": return Object.freeze({...state,
      replay: action.replay, replayNeutral: false});
    case "neutral": return Object.freeze({...state,
      pendingLaunch: null,
      lastLaunchAck: null,
      authority: null,
      hold: false,
      fx: EMPTY_FX,
      filter: Object.freeze({...FILTER_DEFAULT,
        provenance: state.liveControl.available ? "pending" as const
          : "unavailable" as const}),
      replayNeutral: true,
    });
    // Recording start/stop is an independent toggle from FX (#1674): the live
    // FX and HOLD the user is holding stay exactly where they are.
    case "session-neutral": return Object.freeze({...state,
      pendingLaunch: null,
      lastLaunchAck: null,
      authority: null,
      replayNeutral: true,
    });
    case "recording-note": return Object.freeze({...state,
      recordingNote: action.message});
    case "wav-status": return Object.freeze({...state, wavStatus: action.message});
    case "binding-status": return Object.freeze({...state,
      bindingStatus: action.status});
    case "recovery-status": return Object.freeze({...state,
      recoveryStatus: action.message});
    case "resample-status": return Object.freeze({...state,
      resampleStatus: action.message});
    case "error": return Object.freeze({...state, error: action.message});
  }
}

type RecordingQueue = Pick<MasterTapBatchQueue,
  "onBatch" | "onStopped" | "onFailure" | "settled">;

export interface PreparedPerformanceRecording {
  readonly writer: WavStreamWriter;
  readonly store: Pick<PerformanceRecordingStore, "bind" | "save" | "discard">;
  readonly cleanupTemporary: () => Promise<void>;
  readonly readTemporary?: () => Promise<Blob>;
}

export interface PerformControllerDependencies {
  readonly createId?: () => string;
  readonly prepareRecording?: (request: Readonly<{
    projectId: string;
    performanceId: string;
    captureStatus: Extract<PerformanceMasterCaptureStatus, {state: "ready"}>;
  }>) => Promise<PreparedPerformanceRecording>;
  readonly createQueue?: (
    writer: WavStreamWriter,
    listener: MasterTapListener,
  ) => RecordingQueue;
  readonly waitForStatusQuery?: () => Promise<void>;
  readonly maximumStatusQueries?: number;
}

export interface PerformControllerOptions {
  readonly session: CreatorPerformanceRuntimeSession;
  readonly getCreatorState: () => CreatorState;
  readonly refreshProject: () => Promise<unknown>;
  readonly opfsAvailable: () => boolean;
  readonly dependencies?: PerformControllerDependencies;
  // Records a failure in Developer diagnostics (#1680).
  readonly reportFailure?: (operation: string, error: unknown) => unknown;
}

async function defaultPrepareRecording(
  session: CreatorPerformanceRuntimeSession,
  request: Parameters<NonNullable<PerformControllerDependencies["prepareRecording"]>>[0],
): Promise<PreparedPerformanceRecording> {
  if (navigator.storage?.getDirectory === undefined) {
    throw new Error("Origin-private storage is unavailable");
  }
  const root = await navigator.storage.getDirectory();
  const temporaryDirectory = await root.getDirectoryHandle(
    "lmdj-perform-temporary", {create: true},
  );
  const projectsDirectory = await root.getDirectoryHandle("projects");
  const projectDirectory = await projectsDirectory.getDirectoryHandle(
    `${request.projectId}.lmdj`,
  );
  const managedDirectory = await projectDirectory.getDirectoryHandle("assets");
  const temporaryHandle = await temporaryDirectory.getFileHandle(
    `${request.performanceId}.wav`, {create: true},
  );
  const storage = new OpfsPerformanceRecordingStorage(
    temporaryDirectory,
    managedDirectory,
  );
  const cleanupTemporary = () => storage.deleteTemporary(temporaryHandle);
  try {
    const config = request.captureStatus.config;
    const realWriter = await openWavStreamWriter(temporaryHandle, {
      perform_recording_frames: config.performRecordingFrames,
      perform_recording_queue_batches: config.performRecordingQueueBatches,
    });
    const realStore = new PerformanceRecordingStore(temporaryHandle, storage, session);
    const seams = (window as Window & {__LMDJ_WEB_HOST_SEAMS__?: {
      createWavStreamWriter?: (real: WavStreamWriter) =>
        WavStreamWriter | Promise<WavStreamWriter>;
      createPerformanceRecordingStore?: (real: PerformanceRecordingStore) =>
        Pick<PerformanceRecordingStore, "bind" | "save" | "discard"> |
        Promise<Pick<PerformanceRecordingStore, "bind" | "save" | "discard">>;
    }}).__LMDJ_WEB_HOST_SEAMS__;
    const writer = seams?.createWavStreamWriter === undefined
      ? realWriter : await seams.createWavStreamWriter(realWriter);
    const store = seams?.createPerformanceRecordingStore === undefined
      ? realStore : await seams.createPerformanceRecordingStore(realStore);
    const readTemporary = () => temporaryHandle.getFile();
    return Object.freeze({writer, store, cleanupTemporary, readTemporary});
  } catch (error) {
    await cleanupTemporary().catch(() => {});
    throw error;
  }
}

// #1680: Host and internal messages stay in Developer diagnostics; the
// Perform surface reads the shared catalogue for the error's code.
function errorMessage(error: unknown): string {
  const code = errorCode(error);
  const {message, nextStep} = userMessage(code ?? "INTERNAL_ERROR");
  return `${message} ${nextStep}`;
}

function errorCode(error: unknown): string | null {
  if (error === null || typeof error !== "object" || !("code" in error)) return null;
  return typeof error.code === "string" ? error.code : null;
}

export interface PerformController {
  getState(): PerformState;
  subscribe(listener: () => void): () => void;
  connect(): () => void;
  leave(): Promise<void>;
  close(): Promise<void>;
  setBank(bank: Bank): void;
  canRecord(): boolean;
  recordingSink(): RecordingQueue | null;
  record(): Promise<void>;
  flush(): Promise<void>;
  stop(): Promise<void>;
  save(name?: string): Promise<void>;
  retryWavBind(): Promise<void>;
  exportWav(): Promise<void>;
  discard(): Promise<void>;
  recordRawEvent(event: PerformanceRawEvent): Promise<void>;
  engageFx(fx: PerformanceFx, value: number): string;
  moveFx(gestureId: string, fx: PerformanceFx, value: number): void;
  releaseFx(gestureId: string, fx: PerformanceFx): void;
  turnFx(fx: PerformanceFx, detents: number, fine?: boolean): void;
  releaseEncoderFx(): void;
  toggleHold(): void;
  refreshLiveStatus(): Promise<void>;
  setFilterType(type: PerformanceFilterTypeName): void;
  turnFilterType(detents: number): void;
  turnFilterCutoff(detents: number, fine?: boolean): void;
  turnFilterResonance(detents: number, fine?: boolean): void;
  touchFilterEngage(parameter: "cutoff" | "resonance"): string;
  touchFilterMove(token: string, parameter: "cutoff" | "resonance",
    value: number): void;
  touchFilterRelease(token: string, parameter: "cutoff" | "resonance"): void;
  launchPattern(patternSlot: number): Promise<void>;
  refreshAuthority(): Promise<void>;
  refreshPerformances(): Promise<void>;
  refreshRecovery(): Promise<void>;
  applyRecovery(sessionId: string): Promise<void>;
  discardRecovery(sessionId: string): Promise<void>;
  beginReplay(performanceId: string): Promise<void>;
  stopReplay(): Promise<void>;
  refreshReplay(): Promise<void>;
  resample(performanceId: string, sourceStartFrame: number,
    sourceEndFrame: number, targetSlot: number): Promise<void>;
  assignPattern(patternSlot: number, patternId: string): Promise<void>;
  clearPattern(patternSlot: number): Promise<void>;
  movePattern(fromSlot: number, toSlot: number): Promise<void>;
}

export function createPerformController(options: PerformControllerOptions): PerformController {
  const {session} = options;
  const createId = options.dependencies?.createId ?? (() => crypto.randomUUID());
  const prepareRecording = options.dependencies?.prepareRecording ??
    ((request) => defaultPrepareRecording(session, request));
  const createQueue = options.dependencies?.createQueue ??
    ((writer, listener) => new MasterTapBatchQueue(writer, listener));
  const waitForStatusQuery = options.dependencies?.waitForStatusQuery ??
    (() => new Promise<void>((resolve) => window.setTimeout(resolve, 50)));
  const maximumStatusQueries = options.dependencies?.maximumStatusQueries ?? 200;
  let state = initialPerformState(session.performanceMasterCaptureStatus(),
    options.getCreatorState().activeBank);
  let authoringRevision = options.getCreatorState().project.current?.revision ?? 0;
  let resources: PreparedPerformanceRecording | null = null;
  let queue: RecordingQueue | null = null;
  let capture: PerformanceMasterCapture | null = null;
  let disconnectCapture: (() => void) | null = null;
  let launchPollGeneration = 0;
  let replayPollGeneration = 0;
  let closePromise: Promise<void> | null = null;
  let leavePromise: Promise<void> | null = null;
  let recordSetupPromise: Promise<void> | null = null;
  let rawEventTail: Promise<void> = Promise.resolve();
  let flushPromise: Promise<void> | null = null;
  let stopPromise: Promise<void> | null = null;
  let finalizationPromise: Promise<void> | null = null;
  let projectMutationTail: Promise<void> = Promise.resolve();
  let saveCommitted = false;
  let saveOutcomeUnknown = false;
  let savedName: string | null = null;
  let bindingCommitted = false;
  let discardCommitted = false;
  const openPadGestures = new Map<string, number>();
  // A submitted release keeps its slot until Core finishes it. Otherwise a
  // stalled producer could hide unbounded press/release pairs behind the tail.
  const pendingPadGestures = new Set<string>();
  const openFxGestures = new Map<PerformanceFx, string>();
  const encoderFxGestures = new Map<PerformanceFx, string>();
  // D0/W1 typed live control: runtime gesture generations come from Core
  // receipts only; a stale or forged generation is rejected far-side.
  const liveFxGenerations = new Map<PerformanceFx, string>();
  let controlTail: Promise<void> = Promise.resolve();
  let ordinaryControls = 0;
  const controlEntries = new Set<{
    reserved: boolean; started: boolean; cancelled: boolean;
  }>();
  let liveFilterGeneration: string | null = null;
  let controlRevision = 0;
  let liveStatusRevision = 0;
  let filterEncoderOwned = false;
  const filterTouchTokens = new Map<string, "cutoff" | "resonance">();
  // The headered recording profile journals moves/releases against the Core
  // begin mapping; legacy recordings keep the Host-id seeding branch.
  let recordingProfile: "legacy" | "headered" = "legacy";
  const recordingFxBindings = new Map<PerformanceFx,
    Readonly<{gestureGeneration: string; recordingGestureId: string}>>();
  let recordingFilterBinding: Readonly<{
    gestureGeneration: string;
    recordingGestureId: string;
  }> | null = null;
  // Gestures opened before the first live-status answer (or against an
  // unavailable producer) keep the legacy route for their whole lifetime;
  // the typed route never adopts an open legacy gesture mid-flight (D0 R3:
  // a Host-local gesture id is not a Core identity).
  const legacyPinnedFx = new Set<PerformanceFx>();
  let closed = false;
  const listeners = new Set<() => void>();

  const dispatch = (action: PerformAction) => {
    state = reducePerform(state, action);
    for (const listener of listeners) listener();
  };
  const report = (error: unknown) => options.reportFailure?.("Perform", error);
  const fail = (error: unknown) => {
    report(error);
    dispatch({type: "error", message: errorMessage(error)});
  };
  const observeProjectRevision = (value: unknown) => {
    if (value === null || typeof value !== "object") return;
    for (const key of ["committedRevision", "projectRevision", "revision"] as const) {
      const revision = (value as Record<string, unknown>)[key];
      if (Number.isSafeInteger(revision) && (revision as number) >= authoringRevision) {
        authoringRevision = revision as number;
      }
    }
  };
  const expectedProjectRevision = () => {
    observeProjectRevision(options.getCreatorState().project.current);
    return authoringRevision;
  };
  const runProjectMutation = <T,>(operation: () => Promise<T>): Promise<T> => {
    const result = projectMutationTail.then(operation);
    projectMutationTail = result.then(() => {}, () => {});
    return result;
  };
  const mutate = <T,>(operation: () => Promise<T>): Promise<T> => {
    return runProjectMutation(async () => {
      const result = await operation();
      observeProjectRevision(result);
      observeProjectRevision(await options.refreshProject());
      return result;
    });
  };
  const refreshProjectTruth = async () => {
    await runProjectMutation(async () => {
      observeProjectRevision(await options.refreshProject());
    });
    await controller.refreshPerformances();
  };
  const currentRecording = () => {
    if (state.recording.sessionId === null || state.recording.performanceId === null) {
      throw new Error("No Performance recording is active");
    }
    return {sessionId: state.recording.sessionId,
      performanceId: state.recording.performanceId};
  };
  // Resolve generations and recording mappings at dequeue time, with the
  // same ordinary 1+1 bound as W1. Matching releases use their already-open
  // gesture's reserved slot and cannot be rejected by an ordinary overflow.
  const inputWindowError = () => Object.assign(new Error(
    "Live input window is full; wait for the current input to settle"),
  {code: "HOST_STATE_INVALID"});
  const controlWindowFull = () => ordinaryControls +
    (controlEntries.values().next().value?.reserved ? 1 : 0) >= 2;
  const admitOrdinaryControl = () => {
    if (!controlWindowFull()) return true;
    fail(inputWindowError());
    return false;
  };
  const cancelWaitingControls = () => {
    for (const entry of controlEntries) {
      if (!entry.started && !entry.reserved) entry.cancelled = true;
    }
  };
  const enqueueControl = (action: () => Promise<void>, reserved = false,
    waitForTransition = true) => {
    if (!reserved && controlWindowFull()) return Promise.reject(inputWindowError());
    if (!reserved) ordinaryControls += 1;
    const entry = {reserved, started: false, cancelled: false};
    controlEntries.add(entry);
    const revision = ++controlRevision;
    const waitForBegin = waitForTransition && state.recording.phase === "starting";
    const waitForStop = waitForTransition && state.recording.phase === "stopping";
    const result = controlTail.then(async () => {
      if (waitForBegin) await recordSetupPromise;
      if (waitForStop) await stopPromise;
      if (entry.cancelled) throw Object.assign(new Error(
        "Live input was cancelled before Core admission"), {code: "HOST_STATE_INVALID"});
      entry.started = true;
      await action();
    }).finally(() => {
      controlEntries.delete(entry);
      if (!reserved) ordinaryControls -= 1;
      // Every typed control can change the shared live snapshot. A Filter
      // query begun before HOLD/FX must never overwrite the newer control.
      if (revision === controlRevision) void readLiveStatus(revision).catch(fail);
    });
    controlTail = result.then(() => {}, () => {});
    return result;
  };
  const activeRecordingId = () =>
    ["recording", "flushing", "stopping"].includes(state.recording.phase)
      ? state.recording.sessionId : null;
  const appendRawEvent = (
    sessionId: string,
    event: PerformanceRawEvent,
  ): Promise<void> => {
    const headered = recordingProfile === "headered";
    const action = async () => {
      if (headered && event.kind === "pad_release" &&
          !pendingPadGestures.has(event.gestureId)) return;
      try {
        await session.recordPerformanceEvent({sessionId, eventId: createId(), event});
      } catch (error) {
        if (headered && event.kind === "pad_press") {
          pendingPadGestures.delete(event.gestureId);
          openPadGestures.delete(event.gestureId);
        }
        throw error;
      }
      await controller.refreshAuthority();
    };
    const submitted = headered
      ? enqueueControl(action, event.kind === "pad_press" || event.kind === "pad_release", false)
      : rawEventTail.then(action);
    const operation = submitted.finally(() => {
      if (headered && event.kind === "pad_release") pendingPadGestures.delete(event.gestureId);
    });
    rawEventTail = operation.catch(fail);
    return operation;
  };
  // Headered journal entries are built at dequeue time: a move/release whose
  // engage was never admitted has no far-side gesture and is dropped here,
  // never forged with a Host-invented binding.
  const applyHeaderedEvent = async (
    sessionId: string,
    build: () => PerformanceHeaderedEvent | null,
    adopt?: (binding: Readonly<{
      gestureGeneration: string;
      recordingGestureId: string;
    }>) => void,
  ): Promise<void> => {
    const event = build();
    if (event === null) return;
    const receipt = await session.recordPerformanceEvent({
      sessionId, eventId: createId(), event,
    });
    if (adopt !== undefined && "gestureGeneration" in receipt &&
        "recordingGestureId" in receipt &&
        receipt.gestureGeneration !== null &&
        receipt.recordingGestureId !== null) {
      adopt({gestureGeneration: receipt.gestureGeneration,
        recordingGestureId: receipt.recordingGestureId});
    }
    await controller.refreshAuthority();
  };
  const liveControlEpoch = () =>
    state.liveControl.available ? state.liveControl.epoch : null;
  const filterTypedReady = () =>
    !state.legacyFilterGesture && (liveControlEpoch() !== null ||
    (["recording", "flushing"].includes(state.recording.phase) &&
      recordingProfile === "headered"));
  // An ACK proves admission, not the applied tuple. Only the latest control
  // may reconcile the optimistic display; older reads cannot overwrite a
  // later turn or an epoch reset. Poll within the existing status budget.
  const readLiveStatus = async (revision = controlRevision,
    expected?: Readonly<{epoch: string; sequence: string}>) => {
    const request = ++liveStatusRevision;
    for (let attempt = 0; attempt < maximumStatusQueries; attempt += 1) {
      const status = await session.queryPerformanceLiveStatus();
      if (closed || request !== liveStatusRevision ||
          revision !== controlRevision) return;
      const previousEpoch = liveControlEpoch();
      if (status.controlEpoch !== previousEpoch && previousEpoch !== null) {
        liveFilterGeneration = null;
        liveFxGenerations.clear();
      }
      if (!status.available || (expected !== undefined &&
          status.controlEpoch !== expected.epoch)) {
        dispatch({type: "live-status", status});
        return;
      }
      const applied = status.appliedControlSequence === status.acceptedControlSequence &&
        (expected === undefined ||
          BigInt(status.appliedControlSequence) >= BigInt(expected.sequence));
      if (applied) {
        dispatch({type: "live-status", status});
        return;
      }
      await waitForStatusQuery();
    }
    throw new Error("Performance live state acknowledgement timed out");
  };
  const submitFxControl = (kind: "engage" | "move" | "release",
    fx: PerformanceFx, gestureId: string, value?: number,
    pinned = legacyPinnedFx.has(fx)) => {
    const epoch = liveControlEpoch();
    const action = async () => {
      const sessionId = activeRecordingId();
      if (sessionId !== null && recordingProfile === "headered") {
        await applyHeaderedEvent(sessionId, () => {
          const binding = recordingFxBindings.get(fx);
          if (kind === "release") return binding === undefined ? null : {
            kind: "fx_release", fx, gestureId: binding.recordingGestureId,
            gestureGeneration: binding.gestureGeneration,
          };
          return binding === undefined ? headeredFxEngage(fx, value!) : {
            kind: "fx_move", fx, value: value!,
            gestureId: binding.recordingGestureId,
            gestureGeneration: binding.gestureGeneration,
          };
        }, (binding) => {
          recordingFxBindings.set(fx, binding);
          liveFxGenerations.set(fx, binding.gestureGeneration);
        });
        if (kind === "release") {
          recordingFxBindings.delete(fx);
          liveFxGenerations.delete(fx);
        }
      } else if (sessionId !== null) {
        const event: PerformanceRawEvent = kind === "release"
          ? {kind: "fx_release", gestureId, fx}
          : {kind: kind === "engage" ? "fx_engage" : "fx_move", gestureId, fx, value: value!};
        await session.recordPerformanceEvent({sessionId, eventId: createId(), event});
        await controller.refreshAuthority();
      } else if (epoch !== null && !pinned) {
        if (epoch !== liveControlEpoch()) return;
        const generation = liveFxGenerations.get(fx);
        if (kind === "release" && generation === undefined) return;
        const receipt = await session.applyPerformanceLiveControl({controlEpoch: epoch,
          intent: kind === "release"
            ? {kind: "fx_release", fx, gestureGeneration: generation!}
            : generation === undefined
              ? {kind: "fx_parameter", phase: "engage", fx, value: value!}
              : {kind: "fx_parameter", phase: "move", fx, value: value!,
                  gestureGeneration: generation},
        });
        if (epoch !== liveControlEpoch()) return;
        if (kind === "release") liveFxGenerations.delete(fx);
        else if (receipt.gestureGeneration !== null) {
          liveFxGenerations.set(fx, receipt.gestureGeneration);
        }
      } else {
        await session.applyFxGesture(kind === "release"
          ? {kind: "fx_release", fx}
          : {kind: kind === "engage" ? "fx_engage" : "fx_move", fx, value: value!});
      }
    };
    const typed = epoch !== null || recordingProfile === "headered" ||
      state.recording.phase === "starting";
    const result = typed ? enqueueControl(action, kind === "release")
      : activeRecordingId() === null ? action() : rawEventTail.then(action);
    rawEventTail = result.catch(fail);
  };
  const sendFilterControl = (
    parameter: FilterParameter,
    value: number | PerformanceFilterTypeName,
  ) => {
    const epoch = liveControlEpoch();
    const result = enqueueControl(async () => {
      const sessionId = activeRecordingId();
      if (sessionId !== null) {
        if (recordingProfile !== "headered") return;
        await applyHeaderedEvent(sessionId, () => {
          const binding = recordingFilterBinding;
          return binding === null
            ? filterParameterEvent("engage", parameter, value)
            : filterParameterEvent("move", parameter, value, {
                gestureId: binding.recordingGestureId,
                gestureGeneration: binding.gestureGeneration,
              });
        }, (binding) => {
          recordingFilterBinding = binding;
          liveFilterGeneration = binding.gestureGeneration;
        });
      } else {
        if (epoch === null || epoch !== liveControlEpoch()) return;
        const receipt = await session.applyPerformanceLiveControl({
          controlEpoch: epoch,
          intent: liveFilterGeneration === null
            ? filterParameterIntent("engage", parameter, value)
            : filterParameterIntent("move", parameter, value, liveFilterGeneration),
        });
        if (epoch !== liveControlEpoch()) return;
        if (receipt.gestureGeneration !== null) liveFilterGeneration = receipt.gestureGeneration;
      }
    });
    void result.catch((error) => {
      fail(error);
      // Rejected input has no Core value. Reconcile after admitted controls
      // drain so its optimistic tuple cannot remain labelled as pending.
      void controlTail.then(() => readLiveStatus()).catch(fail);
    });
  };
  const releaseFilterGesture = () => {
    if (liveFilterGeneration === null && recordingFilterBinding === null &&
        !state.filter.engaged) return;
    const epoch = liveControlEpoch();
    const released = enqueueControl(async () => {
      const sessionId = activeRecordingId();
      if (sessionId !== null && recordingProfile === "headered") {
        await applyHeaderedEvent(sessionId, () => {
          const binding = recordingFilterBinding;
          return binding === null ? null : {kind: "filter_release",
            gestureId: binding.recordingGestureId,
            gestureGeneration: binding.gestureGeneration};
        });
        recordingFilterBinding = null;
        liveFilterGeneration = null;
      } else if (epoch !== null && epoch === liveControlEpoch()) {
        const generation = liveFilterGeneration;
        if (generation === null) return;
        await session.applyPerformanceLiveControl({controlEpoch: epoch,
          intent: {kind: "filter_release", gestureGeneration: generation}});
        if (epoch === liveControlEpoch()) liveFilterGeneration = null;
      }
    }, true);
    void released.catch(fail);
    filterEncoderOwned = false;
    dispatch({type: "filter", filter: {...state.filter, engaged: false,
      provenance: liveControlEpoch() === null ? "unavailable" : "pending"}});
  };
  const clearRecordingBindings = () => {
    recordingProfile = "legacy";
    recordingFxBindings.clear();
    recordingFilterBinding = null;
  };
  const clearLiveGenerations = () => {
    ++controlRevision;
    ++liveStatusRevision;
    liveFxGenerations.clear();
    liveFilterGeneration = null;
    filterEncoderOwned = false;
    legacyPinnedFx.clear();
    if (state.legacyFilterGesture) {
      dispatch({type: "filter-legacy-gesture", open: false});
    }
  };
  const setRecording = (phase: PerformanceRecordingPhase,
    changes: Partial<PerformState["recording"]> = {}) => dispatch({
      type: "recording",
      recording: {...state.recording, ...changes, phase},
    });
  const formatReason = (reason: string) => reason.replaceAll("_", " ");
  const loadRecovery = async (message?: string) => {
    const values = await session.listPerformanceRecovery() as
      readonly PerformanceRecoverySummary[];
    dispatch({type: "recovery", values});
    dispatch({type: "recovery-status", message: message ??
      (values[0] === undefined ? "idle" : formatReason(values[0].reason))});
  };

  const runFinalization = (operation: () => Promise<void>): Promise<void> => {
    if (finalizationPromise !== null) return finalizationPromise;
    const promise = operation().finally(() => {
      if (finalizationPromise === promise) finalizationPromise = null;
    });
    finalizationPromise = promise;
    return promise;
  };

  const bindSavedRecording = async () => {
    if (resources === null || state.recording.performanceId === null ||
        state.recording.expectedRevision === null) return;
    const bindingResources = resources;
    const performanceId = state.recording.performanceId;
    dispatch({type: "binding-status", status: "binding"});
    if (!bindingCommitted) {
      try {
        await runProjectMutation(async () => {
          const receipt = await bindingResources.store.bind({
            expectedRevision: expectedProjectRevision(), performanceId,
          });
          observeProjectRevision(receipt);
          bindingCommitted = true;
          return receipt;
        });
      } catch (error) {
        dispatch({type: "binding-status", status: "retry"});
        setRecording("stopped");
        report(error);
        dispatch({type: "error", message:
          "The recording could not be saved into the Project. Choose Retry WAV bind."});
        return;
      }
    }
    try {
      await refreshProjectTruth();
    } catch (error) {
      dispatch({type: "binding-status", status: "retry"});
      setRecording("stopped");
      report(error);
      dispatch({type: "error", message:
        "The recording was saved, but Creator could not show the latest Project. " +
        "Choose Retry WAV bind."});
      return;
    }
    if (resources === bindingResources) {
      resources = null;
      queue = null;
    }
    dispatch({type: "binding-status", status: "bound"});
    setRecording("idle", {sessionId: null, performanceId: null,
      expectedRevision: null, wav: null});
    saveCommitted = false;
    saveOutcomeUnknown = false;
    savedName = null;
    bindingCommitted = false;
    discardCommitted = false;
  };

  const observeLaunch = async (requestId: string, generation: number) => {
    for (let attempt = 0; attempt < maximumStatusQueries; attempt += 1) {
      if (generation !== launchPollGeneration) return;
      const revision = controlRevision;
      const authority = await session.queryPerformanceRecordingStatus();
      if (generation !== launchPollGeneration) return;
      if (revision === controlRevision) dispatch({type: "authority", status: authority});
      if (authority.lastLaunchAck?.requestId === requestId) return;
      if (authority.state !== "active" ||
          (authority.pendingLaunch !== null &&
            authority.pendingLaunch.requestId !== requestId)) {
        dispatch({type: "pending-launch", pending: null});
        throw new Error("Pattern launch ended without its acknowledgement");
      }
      await waitForStatusQuery();
    }
    if (generation === launchPollGeneration) {
      dispatch({type: "pending-launch", pending: null});
      throw new Error("Pattern launch acknowledgement timed out");
    }
  };

  const controller: PerformController = {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    connect() {
      if (disconnectCapture === null) {
        disconnectCapture = session.subscribePerformanceMasterCaptureStatus(
          (captureStatus) => {
            dispatch({type: "capture", status: captureStatus});
            if (captureStatus.state !== "ready" &&
                ["starting", "recording", "flushing"].includes(
                  state.recording.phase,
                )) {
              void controller.stop();
            }
          },
        );
        void controller.refreshPerformances().catch(fail);
        void controller.refreshRecovery().catch(fail);
        void controller.refreshLiveStatus().catch(fail);
      }
      return () => {
        disconnectCapture?.();
        disconnectCapture = null;
      };
    },
    leave() {
      if (leavePromise !== null) return leavePromise;
      const operation = (async () => {
        await recordSetupPromise?.catch(() => {});
        cancelWaitingControls();
        controller.releaseEncoderFx();
        await controlTail;
        await controller.stop().catch(fail);
        await finalizationPromise?.catch(fail);
        await projectMutationTail;
        if (state.replay !== null && state.replay.state === "playing") {
          await controller.stopReplay();
        }
      })();
      const tracked = operation.finally(() => {
        if (leavePromise === tracked) leavePromise = null;
      });
      leavePromise = tracked;
      return tracked;
    },
    close() {
      if (closePromise !== null) return closePromise;
      closed = true;
      launchPollGeneration += 1;
      disconnectCapture?.();
      disconnectCapture = null;
      closePromise = controller.leave();
      return closePromise;
    },
    setBank(bank) { dispatch({type: "bank", bank}); },
    canRecord() {
      return !closed && state.captureStatus.state === "ready" &&
        options.opfsAvailable() && options.getCreatorState().audio.phase === "running" &&
        selectCanTrigger(options.getCreatorState()) && state.recoveryLoaded &&
        state.recovery.length === 0 &&
        state.recording.phase === "idle";
    },
    recordingSink: () => queue,
    record() {
      if (!controller.canRecord() || state.captureStatus.state !== "ready") {
        return Promise.resolve();
      }
      const priorControls = controlTail;
      const setup = async () => {
        dispatch({type: "error", message: null});
        dispatch({type: "session-neutral"});
        dispatch({type: "recording-note", message: null});
        dispatch({type: "wav-status", message: "recording"});
        dispatch({type: "binding-status", status: "unbound"});
        const sessionId = createId();
        const performanceId = createId();
        const projectId = options.getCreatorState().project.current?.projectId;
        if (projectId === undefined) {
          throw new Error("A playable Project is required for Performance recording");
        }
        openPadGestures.clear();
        pendingPadGestures.clear();
        saveCommitted = false;
        saveOutcomeUnknown = false;
        savedName = null;
        bindingCommitted = false;
        discardCommitted = false;
        setRecording("starting", {sessionId, performanceId});
        let beganRevision: number | null = null;
        try {
          resources = await prepareRecording({projectId, performanceId,
            captureStatus: state.captureStatus as Extract<
              PerformanceMasterCaptureStatus, {state: "ready"}>});
          const listener: MasterTapListener = {
            requestCaptureStop: () => { void controller.stop().catch(fail); },
            onFailure: (failure: MasterTapFailure) => {
              dispatch({type: "error", message: failure.message});
              void controller.stop();
            },
          };
          queue = createQueue(resources.writer, listener);
          await priorControls;
          const liveStatus = await session.queryPerformanceLiveStatus()
            .catch(() => null);
          const headered = liveStatus !== null && liveStatus.available &&
            liveStatus.controlEpoch !== null;
          recordingProfile = headered ? "headered" : "legacy";
          if (liveStatus !== null) {
            dispatch({type: "live-status", status: liveStatus});
          }
          if (headered && liveStatus.available) {
            // D0 dual-ready, Host-composed: the headered begin promise proves
            // the Core fence and returns the gesture mapping; the capture
            // start then resolves only on the real started ACK. Keep the
            // begin receipt before starting capture: compensation needs its
            // committed revision even if capture start fails. The Host owns
            // the returned capture handle and keeps the first recorded Pad
            // behind both gates in this fence → capture sequence.
            const receipt = await mutate(async () => {
              const began = await session.beginPerformanceRecording({
                sessionId, performanceId,
                expectedRevision: expectedProjectRevision(),
                controlEpoch: liveStatus.controlEpoch,
              });
              beganRevision = began.committedRevision;
              return began;
            });
            for (const binding of receipt.fxBindings) {
              const pair = {
                gestureGeneration: binding.gestureGeneration,
                recordingGestureId: binding.recordingGestureId,
              };
              if (binding.fx === "filter" &&
                  liveStatus.accepted.filter.mode === "independent") {
                recordingFilterBinding = pair;
                liveFilterGeneration = binding.gestureGeneration;
              } else {
                recordingFxBindings.set(binding.fx, pair);
                liveFxGenerations.set(binding.fx, binding.gestureGeneration);
                // An FX the Core mapping reports as already engaged is
                // adopted, never re-engaged: a later touch move/release pairs
                // against the mapping instead of seeding a fake engage.
                if (!openFxGestures.has(binding.fx)) {
                  openFxGestures.set(binding.fx, createId());
                }
              }
            }
            capture = await session.startPerformanceMasterCapture(queue);
            if (closed) throw new Error("Performance controller closed during setup");
            if (state.captureStatus.state !== "ready") {
              throw new Error("Performance capture became unavailable during setup");
            }
            setRecording("recording", {expectedRevision: receipt.committedRevision});
          } else {
            capture = await session.startPerformanceMasterCapture(queue);
            if (closed) throw new Error("Performance controller closed during setup");
            if (state.captureStatus.state !== "ready") {
              throw new Error("Performance capture became unavailable during setup");
            }
            const receipt = await mutate(async () => {
              const began = await session.beginPerformanceRecording({
                sessionId, performanceId,
                expectedRevision: expectedProjectRevision(),
              });
              beganRevision = began.committedRevision;
              return began;
            });
            setRecording("recording", {expectedRevision: receipt.committedRevision});
            // FX engaged before Record are already audible (#1674); journal
            // matching engage/hold events so the recording replays what the
            // master bus is actually producing. The headered profile consumes
            // the Core begin mapping instead and seeds nothing.
            if (state.hold) {
              void controller.recordRawEvent({kind: "hold_on"}).catch(fail);
            }
            for (const [fx, gestureId] of openFxGestures) {
              void controller.recordRawEvent({
                kind: "fx_engage", gestureId, fx, value: state.fx[fx],
              }).catch(fail);
            }
          }
        } catch (error) {
          clearRecordingBindings();
          if (beganRevision !== null) {
            await session.stopPerformanceRecording({sessionId, requestId: createId()})
              .catch(() => {});
          }
          await capture?.stop().catch(() => {});
          let wav: WavWriterSnapshot | null = null;
          if (capture !== null && queue !== null) {
            wav = await queue.settled.catch(() => null);
          }
          if (beganRevision !== null && resources !== null) {
            const discardRevision = beganRevision;
            try {
              await runProjectMutation(() => resources!.store.discard({
                expectedRevision: discardRevision,
                performanceId,
              }));
            } catch (compensationError) {
              capture = null;
              setRecording("stopped", {expectedRevision: beganRevision, wav});
              dispatch({type: "wav-status", message: "sealed · temporary retained"});
              dispatch({type: "recovery-checking"});
              dispatch({type: "recovery-status", message: "recovery required"});
              report(error);
              report(compensationError);
              dispatch({type: "error", message:
                `${errorMessage(error)} The interrupted recording is kept for recovery.`});
              await loadRecovery("recovery required").catch(fail);
              return;
            }
          } else {
            await resources?.cleanupTemporary().catch(() => {});
          }
          queue = null;
          resources = null;
          capture = null;
          setRecording("idle", {sessionId: null, performanceId: null,
            expectedRevision: null, wav: null});
          dispatch({type: "wav-status", message: "temporary removed"});
          fail(error);
        }
      };
      recordSetupPromise = setup().finally(() => { recordSetupPromise = null; });
      return recordSetupPromise;
    },
    flush() {
      if (flushPromise !== null) return flushPromise;
      if (state.recording.phase !== "recording") return Promise.resolve();
      const {sessionId} = currentRecording();
      setRecording("flushing");
      const operation = (async () => {
        try {
          const receipt = await mutate(() => session.flushPerformanceRecording({
            sessionId, commandId: createId(),
          }));
          if (state.recording.phase === "flushing") {
            setRecording("recording", {expectedRevision: receipt.committedRevision});
            dispatch({type: "recording-note", message: "flushed"});
            await controller.refreshAuthority();
          }
        } catch (error) {
          if (state.recording.phase === "flushing") setRecording("recording");
          fail(error);
        }
      })();
      const tracked = operation.finally(() => {
        if (flushPromise === tracked) flushPromise = null;
      });
      flushPromise = tracked;
      return tracked;
    },
    stop() {
      if (stopPromise !== null) return stopPromise;
      const operation = (async () => {
        if (state.recording.phase === "starting") {
          await recordSetupPromise?.catch(() => {});
        }
        if (state.recording.phase === "flushing") {
          await flushPromise?.catch(() => {});
        }
        if (state.recording.phase !== "recording" || queue === null) return;
        const {sessionId} = currentRecording();
        launchPollGeneration += 1;
        setRecording("stopping");
        cancelWaitingControls();
        for (const [gestureId, slot] of openPadGestures) {
          void appendRawEvent(sessionId, {kind: "pad_release", gestureId, slot});
        }
        openPadGestures.clear();
        const stoppedControls = controlTail;
        await rawEventTail;
        await stoppedControls;
        let coreError: unknown = null;
        try {
          await session.stopPerformanceRecording({sessionId, requestId: createId()});
        } catch (error) {
          coreError = error;
        }
        clearRecordingBindings();
        try {
          await capture?.stop();
          const wav = await queue.settled;
          capture = null;
          setRecording("stopped", {wav});
          dispatch({type: "wav-status", message: `sealed · ${wav.reason ?? "stopped"}`});
          dispatch({type: "session-neutral"});
          if (coreError !== null) throw coreError;
        } catch (error) { setRecording("stopped"); fail(error); }
      })();
      const tracked = operation.finally(() => {
        if (stopPromise === tracked) stopPromise = null;
      });
      stopPromise = tracked;
      return tracked;
    },
    save(name = "Performance") {
      if (state.recording.phase !== "stopped" || resources === null) {
        return Promise.resolve();
      }
      return runFinalization(async () => {
        const {performanceId} = currentRecording();
        dispatch({type: "error", message: null});
        setRecording("saving");
        try {
          if (saveOutcomeUnknown) {
            const inspected = await session.inspectPerformance(performanceId);
            if (inspected.id !== performanceId || inspected.name !== savedName) {
              throw new Error("Saved Performance identity did not match the pending recording");
            }
            observeProjectRevision(inspected);
            saveCommitted = true;
            saveOutcomeUnknown = false;
            setRecording("saving", {expectedRevision: inspected.projectRevision});
          } else if (!saveCommitted) {
            savedName = name;
            let receipt: Readonly<{committedRevision: number}>;
            try {
              receipt = await runProjectMutation(async () => {
                const saved = await session.savePerformance({
                  expectedRevision: expectedProjectRevision(),
                  performanceId, name, recordingArtifact: null,
                });
                observeProjectRevision(saved);
                return saved;
              });
            } catch (error) {
              if (errorCode(error) === "PROJECT_BUSY") throw error;
              saveOutcomeUnknown = true;
              const inspected = await session.inspectPerformance(performanceId);
              if (inspected.id !== performanceId || inspected.name !== savedName) {
                throw error;
              }
              observeProjectRevision(inspected);
              saveCommitted = true;
              saveOutcomeUnknown = false;
              receipt = {committedRevision: inspected.projectRevision};
            }
            saveCommitted = true;
            setRecording("saving", {expectedRevision: receipt.committedRevision});
          }
          try {
            await refreshProjectTruth();
          } catch (error) {
            setRecording("stopped");
            report(error);
            dispatch({type: "error", message:
              "The Performance was saved, but Creator could not show the latest Project. " +
              "Choose Save Performance again."});
            return;
          }
          await bindSavedRecording();
        } catch (error) {
          setRecording("stopped");
          if (saveOutcomeUnknown) {
            report(error);
            dispatch({type: "error", message:
              "Creator could not confirm the save. Choose Save Performance again " +
              "before saving anything else."});
          } else if (errorCode(error) === "PROJECT_BUSY") {
            savedName = null;
            dispatch({type: "error", message:
              "Project is busy; retry Save Performance."});
          } else {
            fail(error);
          }
        }
      });
    },
    retryWavBind() {
      dispatch({type: "error", message: null});
      return runFinalization(bindSavedRecording);
    },
    async exportWav() {
      if (resources?.readTemporary === undefined || state.recording.wav === null) return;
      try {
        const blob = await resources.readTemporary();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${state.recording.performanceId ?? "performance"}.wav`;
        anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      } catch (error) { fail(error); }
    },
    discard() {
      if (state.recording.phase !== "stopped" || resources === null) {
        return Promise.resolve();
      }
      return runFinalization(async () => {
        const {performanceId} = currentRecording();
        setRecording("discarding");
        try {
          if (!discardCommitted) {
            await runProjectMutation(async () => {
              const receipt = await resources!.store.discard({
                expectedRevision: expectedProjectRevision(),
                performanceId,
              });
              observeProjectRevision(receipt);
              discardCommitted = true;
              return receipt;
            });
          }
          await refreshProjectTruth();
          resources = null; queue = null;
          setRecording("idle", {sessionId: null, performanceId: null,
            expectedRevision: null, wav: null});
          dispatch({type: "wav-status", message: "temporary removed"});
          saveCommitted = false;
          saveOutcomeUnknown = false;
          savedName = null;
          bindingCommitted = false;
          discardCommitted = false;
        } catch (error) {
          setRecording("stopped");
          if (discardCommitted) {
            report(error);
            dispatch({type: "error", message:
              "The Performance was discarded, but Creator could not show the latest Project. " +
              "Choose Discard Performance again."});
          } else {
            fail(error);
          }
        }
      });
    },
    recordRawEvent(event) {
      if (!["recording", "flushing"].includes(state.recording.phase) ||
          state.recording.sessionId === null) {
        return Promise.resolve();
      }
      if (event.kind === "pad_press") {
        if (recordingProfile === "headered") {
          if (pendingPadGestures.size >= 64) return Promise.reject(Object.assign(
            new Error("Too many open Pad gestures; the 65th press is not admitted"),
            {code: "HOST_STATE_INVALID"}));
          pendingPadGestures.add(event.gestureId);
        }
        openPadGestures.set(event.gestureId, event.slot);
      } else if (event.kind === "pad_release") {
        if (!openPadGestures.has(event.gestureId)) return Promise.resolve();
        openPadGestures.delete(event.gestureId);
      }
      const sessionId = state.recording.sessionId;
      return appendRawEvent(sessionId, event);
    },
    engageFx(fx, value) {
      const existing = openFxGestures.get(fx);
      if (existing !== undefined) {
        controller.moveFx(existing, fx, value);
        return existing;
      }
      const gestureId = createId();
      if ((liveControlEpoch() !== null || recordingProfile === "headered" ||
          state.recording.phase === "starting") && !admitOrdinaryControl()) return gestureId;
      dispatch({type: "fx", fx, value});
      openFxGestures.set(fx, gestureId);
      if (liveControlEpoch() === null && state.recording.phase !== "starting" &&
          recordingProfile !== "headered") {
        legacyPinnedFx.add(fx);
        if (fx === "filter") dispatch({type: "filter-legacy-gesture", open: true});
      }
      submitFxControl("engage", fx, gestureId, value);
      return gestureId;
    },
    moveFx(gestureId, fx, value) {
      if (openFxGestures.get(fx) !== gestureId) return;
      if ((liveControlEpoch() !== null || recordingProfile === "headered" ||
          state.recording.phase === "starting") && !admitOrdinaryControl()) return;
      dispatch({type: "fx", fx, value});
      submitFxControl("move", fx, gestureId, value);
    },
    releaseFx(gestureId, fx) {
      if (openFxGestures.get(fx) !== gestureId ||
          encoderFxGestures.get(fx) === gestureId) return;
      openFxGestures.delete(fx);
      const pinned = legacyPinnedFx.delete(fx);
      if (fx === "filter" && state.legacyFilterGesture) {
        dispatch({type: "filter-legacy-gesture", open: false});
      }
      submitFxControl("release", fx, gestureId, undefined, pinned);
    },
    turnFx(fx, detents, fine = false) {
      if (!Number.isFinite(detents) || detents === 0) return;
      const value = Math.min(1000, Math.max(0,
        state.fx[fx] + Math.trunc(detents) * (fine ? 1 : 10)));
      if (value === state.fx[fx]) return;
      // A turn continues the current FX gesture instead of stranding a
      // journalled touch engagement. Subsequent touch-up cannot release the
      // value the rotary now owns; page exit releases it under Core HOLD.
      let gestureId = openFxGestures.get(fx);
      if (gestureId === undefined) gestureId = controller.engageFx(fx, value);
      else controller.moveFx(gestureId, fx, value);
      if (openFxGestures.get(fx) === gestureId) encoderFxGestures.set(fx, gestureId);
    },
    releaseEncoderFx() {
      for (const [fx, gestureId] of encoderFxGestures) {
        encoderFxGestures.delete(fx);
        controller.releaseFx(gestureId, fx);
        if (!state.hold) dispatch({type: "fx", fx, value: 500});
      }
      // The FILTER rotary gesture survives rest and group switches (D04);
      // page exit is the one rotary release, frozen far-side under HOLD.
      if ((filterEncoderOwned || state.filter.engaged) && filterTouchTokens.size === 0) {
        releaseFilterGesture();
      }
    },
    toggleHold() {
      const epoch = liveControlEpoch();
      if ((epoch !== null || recordingProfile === "headered") &&
          !admitOrdinaryControl()) return;
      const value = !state.hold;
      dispatch({type: "hold", value});
      if (epoch !== null || recordingProfile === "headered") {
        void enqueueControl(async () => {
          const sessionId = activeRecordingId();
          if (sessionId !== null) {
            await session.recordPerformanceEvent({sessionId, eventId: createId(),
              event: {kind: value ? "hold_on" : "hold_off"}});
            await controller.refreshAuthority();
          } else if (epoch !== null && epoch === liveControlEpoch()) {
            await session.applyPerformanceLiveControl({controlEpoch: epoch,
              intent: {kind: value ? "hold_on" : "hold_off"}});
          }
        }).catch(fail);
      } else if (["recording", "flushing"].includes(state.recording.phase)) {
        void controller.recordRawEvent({kind: value ? "hold_on" : "hold_off"}).catch(fail);
      } else {
        void session.applyFxGesture({kind: value ? "hold_on" : "hold_off"}).catch(fail);
      }
    },
    async refreshLiveStatus() {
      await readLiveStatus();
    },
    setFilterType(type) {
      if (!filterTypedReady() || state.filter.type === type || !admitOrdinaryControl()) return;
      dispatch({type: "filter", filter: {...state.filter, type,
        engaged: true, provenance: "pending"}});
      sendFilterControl("type", type);
    },
    turnFilterType(detents) {
      if (!Number.isFinite(detents) || detents === 0) return;
      const index = FILTER_TYPES.indexOf(state.filter.type);
      const next = FILTER_TYPES[
        (index + (detents > 0 ? 1 : FILTER_TYPES.length - 1)) %
        FILTER_TYPES.length]!;
      controller.setFilterType(next);
    },
    turnFilterCutoff(detents, fine = false) {
      if (!filterTypedReady() || !Number.isFinite(detents) || detents === 0) {
        return;
      }
      const position = cutoffHzToPosition(state.filter.cutoffHz);
      const next = Math.min(1000, Math.max(0,
        position + Math.trunc(detents) * (fine ? 1 : 10)));
      if (next === position || !admitOrdinaryControl()) return;
      const cutoffHz = cutoffPositionToHz(next);
      dispatch({type: "filter", filter: {...state.filter, cutoffHz,
        engaged: true, provenance: "pending"}});
      // Rotary rest never releases (D04); the turn adopts the shared Filter
      // gesture so a later touch-up cannot strand it.
      filterEncoderOwned = true;
      sendFilterControl("cutoff_hz", cutoffHz);
    },
    turnFilterResonance(detents, fine = false) {
      if (!filterTypedReady() || !Number.isFinite(detents) || detents === 0) {
        return;
      }
      const resonanceMilli = Math.min(1000, Math.max(0,
        state.filter.resonanceMilli + Math.trunc(detents) * (fine ? 1 : 10)));
      if (resonanceMilli === state.filter.resonanceMilli || !admitOrdinaryControl()) return;
      dispatch({type: "filter", filter: {...state.filter, resonanceMilli,
        engaged: true, provenance: "pending"}});
      filterEncoderOwned = true;
      sendFilterControl("resonance_milli", resonanceMilli);
    },
    touchFilterEngage(parameter) {
      const token = createId();
      if (!filterTypedReady() || !admitOrdinaryControl()) return token;
      filterTouchTokens.set(token, parameter);
      // Touch-down carries the current value, like the existing fader
      // engage: entering the FILTER group changes no sound (D04).
      dispatch({type: "filter", filter: {...state.filter, engaged: true,
        provenance: "pending"}});
      if (parameter === "cutoff") {
        sendFilterControl("cutoff_hz", state.filter.cutoffHz);
      } else {
        sendFilterControl("resonance_milli", state.filter.resonanceMilli);
      }
      return token;
    },
    touchFilterMove(token, parameter, value) {
      if (filterTouchTokens.get(token) !== parameter || !filterTypedReady()) {
        return;
      }
      if (!admitOrdinaryControl()) return;
      if (parameter === "cutoff") {
        const cutoffHz = cutoffPositionToHz(value);
        if (cutoffHz === state.filter.cutoffHz) return;
        dispatch({type: "filter", filter: {...state.filter, cutoffHz,
          engaged: true, provenance: "pending"}});
        sendFilterControl("cutoff_hz", cutoffHz);
      } else {
        const resonanceMilli = Math.min(1000, Math.max(0, Math.round(value)));
        if (resonanceMilli === state.filter.resonanceMilli) return;
        dispatch({type: "filter", filter: {...state.filter, resonanceMilli,
          engaged: true, provenance: "pending"}});
        sendFilterControl("resonance_milli", resonanceMilli);
      }
    },
    touchFilterRelease(token, parameter) {
      if (filterTouchTokens.get(token) !== parameter) return;
      filterTouchTokens.delete(token);
      // Pointer-up/cancel/blur keep the legacy release semantics; a gesture
      // the rotary adopted stays open until page exit (D04).
      if (filterTouchTokens.size > 0 || filterEncoderOwned) return;
      releaseFilterGesture();
    },
    async launchPattern(patternSlot) {
      if (!["recording", "flushing"].includes(state.recording.phase) ||
          state.recording.sessionId === null) return;
      try {
        const request = await session.requestPerformancePatternLaunch({
          sessionId: state.recording.sessionId,
          requestId: createId(),
          patternSlot,
        });
        dispatch({type: "pending-launch", pending: {
          requestId: request.requestId, patternSlot,
          targetTick: request.targetTick, claimed: false,
        }});
        const generation = ++launchPollGeneration;
        await observeLaunch(request.requestId, generation);
      } catch (error) { fail(error); }
    },
    async refreshAuthority() {
      const revision = controlRevision;
      const status = await session.queryPerformanceRecordingStatus();
      if (revision === controlRevision) dispatch({type: "authority", status});
    },
    async refreshPerformances() {
      dispatch({type: "performances",
        values: await session.listPerformances() as readonly PerformanceSummary[]});
    },
    async refreshRecovery() {
      await loadRecovery();
    },
    async applyRecovery(sessionId) {
      try {
        await mutate(() => session.applyPerformanceRecovery({
          expectedRevision: expectedProjectRevision(),
          sessionId,
        }));
        await loadRecovery("applied · closed Pad gestures");
        await controller.refreshPerformances();
      } catch (error) { fail(error); }
    },
    async discardRecovery(sessionId) {
      try {
        await session.discardPerformanceRecovery({sessionId, requestId: createId()});
        await loadRecovery("discarded");
      } catch (error) { fail(error); }
    },
    async beginReplay(performanceId) {
      try {
        replayPollGeneration += 1;
        dispatch({type: "replay", replay: await session.beginPerformanceReplay({
          replayId: createId(), performanceId,
        })});
      } catch (error) { fail(error); }
    },
    async stopReplay() {
      if (state.replay === null) return;
      replayPollGeneration += 1;
      const replayId = state.replay.replayId;
      dispatch({type: "error", message: null});
      for (let attempt = 0; attempt < maximumStatusQueries; attempt += 1) {
        try {
          const replay = await session.stopPerformanceReplay({
            replayId, requestId: createId(),
          });
          dispatch({type: "replay", replay});
          if (replay.state !== "playing") {
            dispatch({type: "error", message: null});
            dispatch({type: "neutral"});
            // The neutral reset retires every runtime generation; the epoch
            // and filter/frozen facts come back only from a Core readback.
            clearLiveGenerations();
            void controller.refreshLiveStatus().catch(fail);
            return;
          }
        } catch (error) { fail(error); }
        await waitForStatusQuery();
      }
      const error = new Error("Performance replay neutral reset timed out");
      fail(error);
      throw error;
    },
    async refreshReplay() {
      const current = state.replay;
      if (current === null) return;
      const generation = replayPollGeneration;
      try {
        const replay = await session.queryPerformanceReplayStatus(current.replayId);
        // A reply that outlived a stop (or a newer replay) describes a state
        // the surface has already left; only a current reply may dispatch.
        if (generation !== replayPollGeneration) return;
        if (state.replay?.replayId !== current.replayId) return;
        dispatch({type: "replay", replay});
        if (replay.state !== "playing") {
          dispatch({type: "neutral"});
          clearLiveGenerations();
          void controller.refreshLiveStatus().catch(fail);
        }
      } catch (error) { fail(error); }
    },
    async resample(performanceId, sourceStartFrame, sourceEndFrame, targetSlot) {
      try {
        await mutate(() => session.commitPerformanceResample({
          expectedRevision: expectedProjectRevision(),
          performanceId, sourceStartFrame, sourceEndFrame, targetSlot,
        }));
        dispatch({type: "resample-status", message:
          `committed · Pad ${slotAddress(targetSlot)}`});
      } catch (error) { fail(error); }
    },
    async assignPattern(patternSlot, patternId) {
      try {
        await mutate(() => session.assignPatternSlot({
          expectedRevision: expectedProjectRevision(),
          patternSlot, patternId,
        }));
      } catch (error) { fail(error); }
    },
    async clearPattern(patternSlot) {
      try {
        await mutate(() => session.clearPatternSlot({
          expectedRevision: expectedProjectRevision(),
          patternSlot,
        }));
      } catch (error) { fail(error); }
    },
    async movePattern(fromSlot, toSlot) {
      try {
        await mutate(() => session.movePatternSlot({
          expectedRevision: expectedProjectRevision(),
          fromSlot, toSlot,
        }));
      } catch (error) { fail(error); }
    },
  };
  return controller;
}
