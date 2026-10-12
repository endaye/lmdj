import {userMessage} from "./error_messages";
import type {
  PerformanceFx,
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

interface PreparationFailureOutcome {
  readonly error: unknown;
  readonly knownNoOwner: boolean;
  readonly retained: unknown;
}

async function defaultPrepareRecording(
  session: CreatorPerformanceRuntimeSession,
  request: Parameters<NonNullable<PerformControllerDependencies["prepareRecording"]>>[0],
  observeFailure: (outcome: PreparationFailureOutcome) => void,
): Promise<PreparedPerformanceRecording> {
  let temporaryHandle: FileSystemFileHandle | null = null;
  let cleanupTemporary: (() => Promise<void>) | null = null;
  let temporaryCreationAttempted = false;
  let writerAttempted = false;
  let realWriter: WavStreamWriter | null = null;
  try {
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
    temporaryCreationAttempted = true;
    temporaryHandle = await temporaryDirectory.getFileHandle(
      `${request.performanceId}.wav`, {create: true},
    );
    const storage = new OpfsPerformanceRecordingStorage(temporaryDirectory, managedDirectory);
    const handle = temporaryHandle;
    cleanupTemporary = () => storage.deleteTemporary(handle);
    const config = request.captureStatus.config;
    const limits = {
      perform_recording_frames: config.performRecordingFrames,
      perform_recording_queue_batches: config.performRecordingQueueBatches,
    };
    writerAttempted = true;
    realWriter = await openWavStreamWriter(handle, limits);
    const realStore = new PerformanceRecordingStore(handle, storage, session);
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
    const readTemporary = () => handle.getFile();
    return Object.freeze({writer, store, cleanupTemporary, readTemporary});
  } catch (error) {
    // openWavStreamWriter may have lost an abort result. Never delete an
    // unknown writer's bytes or mistake a null returned reference for absence.
    let knownNoOwner = !temporaryCreationAttempted;
    let cleanupFailure: unknown;
    if (!writerAttempted && cleanupTemporary !== null) {
      try {
        await cleanupTemporary();
        knownNoOwner = true;
      } catch (failure) {
        cleanupFailure = failure;
        knownNoOwner = false;
      }
    }
    observeFailure({error, knownNoOwner,
      retained: {temporaryHandle, cleanupTemporary, realWriter, writerAttempted, cleanupFailure}});
    throw error;
  }
}

interface RecordingShutdownOwner {
  readonly sessionId: string;
  readonly performanceId: string;
  resources: PreparedPerformanceRecording | null;
  queue: RecordingQueue | null;
  capture: PerformanceMasterCapture | null;
  preparationFailure: PreparationFailureOutcome | null;
  queueAttempted: boolean;
  captureAttempted: boolean;
  captureStopObserved: boolean;
  captureStopped: boolean;
  wavSettled: boolean;
  coreBeginAttempted: boolean;
  coreBeginAcknowledged: boolean;
  coreStopped: boolean;
  readonly failures: Map<string, RecordingShutdownDebt>;
}

interface RecordingShutdownDebt {
  readonly owner: RecordingShutdownOwner;
  readonly operation: string;
  readonly error: unknown;
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
  const prepareRecording = options.dependencies?.prepareRecording;
  const createQueue = options.dependencies?.createQueue ??
    ((writer, listener) => new MasterTapBatchQueue(writer, listener));
  const waitForStatusQuery = options.dependencies?.waitForStatusQuery ??
    (() => new Promise<void>((resolve) => window.setTimeout(resolve, 50)));
  const maximumStatusQueries = options.dependencies?.maximumStatusQueries ?? 200;
  let state = initialPerformState(session.performanceMasterCaptureStatus(),
    options.getCreatorState().activeBank);
  let authoringRevision = options.getCreatorState().project.current?.revision ?? 0;
  let resources: PreparedPerformanceRecording | null = null;
  let recordingOwner: RecordingShutdownOwner | null = null;
  const shutdownDebts: RecordingShutdownDebt[] = [];
  const rememberShutdownFailure = (owner: RecordingShutdownOwner | null,
    operation: string, error: unknown) => {
    if (owner === null || owner.failures.has(operation)) return;
    const debt = {owner, operation, error};
    owner.failures.set(operation, debt);
    shutdownDebts.push(debt);
  };
  const settleShutdownFailure = (owner: RecordingShutdownOwner | null,
    ...operations: string[]) => {
    for (const operation of operations) owner?.failures.delete(operation);
  };
  const firstShutdownFailure = () => shutdownDebts.find(
    (debt) => debt.owner.failures.get(debt.operation) === debt,
  );
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
  const openFxGestures = new Map<PerformanceFx, string>();
  const encoderFxGestures = new Map<PerformanceFx, string>();
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
  const appendRawEvent = (
    sessionId: string,
    event: PerformanceRawEvent,
  ): Promise<void> => {
    const owner = recordingOwner;
    const operation = rawEventTail.then(async () => {
      try {
        await session.recordPerformanceEvent({sessionId, eventId: createId(), event});
      } catch (error) {
        rememberShutdownFailure(owner, "raw-event", error);
        throw error;
      }
      await controller.refreshAuthority();
    });
    rawEventTail = operation.catch(fail);
    return operation;
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

  const recordingOwnersStopped = (owner: RecordingShutdownOwner | null) =>
    owner === null || (owner.coreBeginAcknowledged && owner.coreStopped &&
      owner.captureStopped && owner.wavSettled && !owner.failures.has("wav"));
  const refuseUnsettledFinalization = () => {
    if (recordingOwnersStopped(recordingOwner)) return false;
    const failure = firstShutdownFailure();
    if (failure !== undefined) fail(failure.error);
    return true;
  };

  const bindSavedRecording = async () => {
    if (resources === null || state.recording.performanceId === null ||
        state.recording.expectedRevision === null) return;
    if (refuseUnsettledFinalization()) return;
    const bindingResources = resources;
    const owner = recordingOwner;
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
          settleShutdownFailure(owner, "bind", "save-projection");
          return receipt;
        });
      } catch (error) {
        rememberShutdownFailure(owner, "bind", error);
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
      recordingOwner = null;
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
      const authority = await session.queryPerformanceRecordingStatus();
      if (generation !== launchPollGeneration) return;
      dispatch({type: "authority", status: authority});
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
        controller.releaseEncoderFx();
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
      closePromise = Promise.resolve().then(async () => {
        try {
          await controller.leave();
        } catch (error) {
          const failure = firstShutdownFailure();
          throw failure === undefined ? error : failure.error;
        }
        const failure = firstShutdownFailure();
        if (failure !== undefined) throw failure.error;
      });
      // Observe without replacing the exact cached, possibly rejected Promise.
      void closePromise.catch(() => {});
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
        saveCommitted = false;
        saveOutcomeUnknown = false;
        savedName = null;
        bindingCommitted = false;
        discardCommitted = false;
        setRecording("starting", {sessionId, performanceId});
        const owner: RecordingShutdownOwner = {sessionId, performanceId,
          resources: null, queue: null, capture: null, preparationFailure: null,
          queueAttempted: false, captureAttempted: false, captureStopObserved: false,
          captureStopped: false, wavSettled: false, coreBeginAttempted: false,
          coreBeginAcknowledged: false, coreStopped: false, failures: new Map()};
        recordingOwner = owner;
        let beganRevision: number | null = null;
        try {
          const preparationRequest = {projectId, performanceId,
            captureStatus: state.captureStatus as Extract<
              PerformanceMasterCaptureStatus, {state: "ready"}>};
          resources = await (prepareRecording === undefined
            ? defaultPrepareRecording(session, preparationRequest,
                (outcome) => { owner.preparationFailure = outcome; })
            : prepareRecording(preparationRequest));
          owner.resources = resources;
          const listener: MasterTapListener = {
            requestCaptureStop: () => { void controller.stop().catch(fail); },
            onFailure: (failure: MasterTapFailure) => {
              if (failure.reason !== "frame-limit") {
                rememberShutdownFailure(owner, "wav", failure);
                report(failure);
              }
              dispatch({type: "error", message: failure.message});
              void controller.stop();
            },
          };
          owner.queueAttempted = true;
          const sourceQueue = createQueue(resources.writer, listener);
          queue = {
            onBatch: (channels) => sourceQueue.onBatch(channels),
            onStopped: () => {
              owner.captureStopObserved = true;
              sourceQueue.onStopped();
            },
            onFailure: (reason, droppedFrames) => sourceQueue.onFailure(reason, droppedFrames),
            get settled() { return sourceQueue.settled; },
          };
          owner.queue = queue;
          owner.captureAttempted = true;
          capture = await session.startPerformanceMasterCapture(queue);
          owner.capture = capture;
          if (closed) throw new Error("Performance controller closed during setup");
          if (state.captureStatus.state !== "ready") {
            throw new Error("Performance capture became unavailable during setup");
          }
          const receipt = await mutate(async () => {
            owner.coreBeginAttempted = true;
            const began = await session.beginPerformanceRecording({
              sessionId, performanceId,
              expectedRevision: expectedProjectRevision(),
            });
            beganRevision = began.committedRevision;
            owner.coreBeginAcknowledged = true;
            return began;
          });
          setRecording("recording", {expectedRevision: receipt.committedRevision});
          // FX engaged before Record are already audible (#1674); journal
          // matching engage/hold events so the recording replays what the
          // master bus is actually producing.
          if (state.hold) {
            void controller.recordRawEvent({kind: "hold_on"}).catch(fail);
          }
          for (const [fx, gestureId] of openFxGestures) {
            void controller.recordRawEvent({
              kind: "fx_engage", gestureId, fx, value: state.fx[fx],
            }).catch(fail);
          }
        } catch (error) {
          if (resources === null && owner.preparationFailure?.knownNoOwner !== true) {
            rememberShutdownFailure(owner, "prepare", error);
          }
          if (owner.queueAttempted && queue === null) {
            rememberShutdownFailure(owner, "queue-setup", error);
          }
          if (owner.coreBeginAttempted && !owner.coreBeginAcknowledged) {
            rememberShutdownFailure(owner, "core-begin", error);
          }
          if (owner.captureAttempted && capture === null && !owner.captureStopObserved) {
            rememberShutdownFailure(owner, "capture-start", error);
          }
          if (beganRevision !== null) {
            try {
              await session.stopPerformanceRecording({sessionId, requestId: createId()});
              owner.coreStopped = true;
            } catch (cleanupError) {
              rememberShutdownFailure(owner, "setup", error);
              rememberShutdownFailure(owner, "core-stop", cleanupError);
            }
          }
          if (capture !== null) {
            try {
              await capture.stop();
              owner.captureStopped = true;
            } catch (cleanupError) {
              rememberShutdownFailure(owner, "setup", error);
              rememberShutdownFailure(owner, "capture-stop", cleanupError);
            }
          } else if (owner.captureStopObserved) {
            owner.captureStopped = true;
          }
          let wav: WavWriterSnapshot | null = null;
          if (owner.captureStopped && queue !== null) {
            try {
              wav = await queue.settled;
              owner.wavSettled = true;
              capture = null;
              owner.capture = null;
            } catch (cleanupError) {
              rememberShutdownFailure(owner, "setup", error);
              rememberShutdownFailure(owner, "wav", cleanupError);
            }
          }
          // Unknown begin/capture admission is still original ownership. The
          // original bytes and resource references survive; no extra Stop or
          // discard is invented to make the failed setup look absent.
          const knownOwnersStopped =
            (!owner.captureAttempted || (owner.captureStopped && owner.wavSettled)) &&
            (!owner.coreBeginAttempted || (owner.coreBeginAcknowledged && owner.coreStopped));
          let compensationError: unknown;
          if (knownOwnersStopped && owner.failures.size === 0 && resources !== null) {
            try {
              if (beganRevision !== null) {
                const discardRevision = beganRevision;
                await runProjectMutation(() => resources!.store.discard({
                  expectedRevision: discardRevision, performanceId,
                }));
              } else {
                await resources.cleanupTemporary();
              }
            } catch (cleanupError) {
              compensationError = cleanupError;
              rememberShutdownFailure(owner, "setup", error);
              rememberShutdownFailure(owner, "setup-compensation", cleanupError);
            }
          }
          if (owner.failures.size > 0) {
            setRecording("stopped", {expectedRevision: beganRevision, wav});
            dispatch({type: "wav-status", message: wav === null
              ? "temporary retained · cleanup unconfirmed" : "sealed · temporary retained"});
            dispatch({type: "recovery-checking"});
            dispatch({type: "recovery-status", message: "recovery required"});
            report(error);
            if (compensationError !== undefined) report(compensationError);
            dispatch({type: "error", message:
              `${errorMessage(error)} The interrupted recording is kept for recovery.`});
            await loadRecovery("recovery required").catch(fail);
            return;
          }
          queue = null;
          resources = null;
          capture = null;
          recordingOwner = null;
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
      const owner = recordingOwner;
      setRecording("flushing");
      const operation = (async () => {
        try {
          const receipt = await mutate(async () => {
            try {
              return await session.flushPerformanceRecording({
                sessionId, commandId: createId(),
              });
            } catch (error) {
              rememberShutdownFailure(owner, "flush", error);
              throw error;
            }
          });
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
        const owner = recordingOwner;
        launchPollGeneration += 1;
        setRecording("stopping");
        for (const [gestureId, slot] of openPadGestures) {
          void appendRawEvent(sessionId, {kind: "pad_release", gestureId, slot});
        }
        openPadGestures.clear();
        await rawEventTail;
        let coreError: unknown = null;
        try {
          await session.stopPerformanceRecording({sessionId, requestId: createId()});
          if (owner !== null) owner.coreStopped = true;
          settleShutdownFailure(owner, "core-stop");
        } catch (error) {
          coreError = error;
          rememberShutdownFailure(owner, "core-stop", error);
        }
        try {
          try {
            await capture?.stop();
            if (owner !== null) owner.captureStopped = true;
            settleShutdownFailure(owner, "capture-stop");
          } catch (error) {
            rememberShutdownFailure(owner, "capture-stop", error);
            throw error;
          }
          let wav: WavWriterSnapshot;
          try {
            wav = await queue.settled;
            if (owner !== null) owner.wavSettled = true;
          } catch (error) {
            rememberShutdownFailure(owner, "wav", error);
            throw error;
          }
          capture = null;
          if (owner !== null) owner.capture = null;
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
      if (refuseUnsettledFinalization()) return Promise.resolve();
      return runFinalization(async () => {
        const {performanceId} = currentRecording();
        const owner = recordingOwner;
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
            settleShutdownFailure(owner, "save");
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
              rememberShutdownFailure(owner, "save", error);
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
            settleShutdownFailure(owner, "save");
            setRecording("saving", {expectedRevision: receipt.committedRevision});
          }
          try {
            await refreshProjectTruth();
          } catch (error) {
            rememberShutdownFailure(owner, "save-projection", error);
            setRecording("stopped");
            report(error);
            dispatch({type: "error", message:
              "The Performance was saved, but Creator could not show the latest Project. " +
              "Choose Save Performance again."});
            return;
          }
          await bindSavedRecording();
        } catch (error) {
          rememberShutdownFailure(owner, "save", error);
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
      if (refuseUnsettledFinalization()) return Promise.resolve();
      return runFinalization(async () => {
        const {performanceId} = currentRecording();
        const owner = recordingOwner;
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
              settleShutdownFailure(owner, "discard", "bind", "save", "save-projection");
              if (recordingOwnersStopped(owner)) {
                settleShutdownFailure(owner, "setup", "setup-compensation");
              }
              return receipt;
            });
          }
          await refreshProjectTruth();
          resources = null; queue = null; recordingOwner = null;
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
            rememberShutdownFailure(owner, "discard", error);
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
      dispatch({type: "fx", fx, value});
      openFxGestures.set(fx, gestureId);
      // One live application per gesture: a running recording applies it live
      // through the journaled event; outside recording the session-free op
      // applies it directly (#1674).
      if (["recording", "flushing"].includes(state.recording.phase)) {
        void controller.recordRawEvent({kind: "fx_engage", gestureId, fx, value}).catch(fail);
      } else {
        void session.applyFxGesture({kind: "fx_engage", fx, value}).catch(fail);
      }
      return gestureId;
    },
    moveFx(gestureId, fx, value) {
      if (openFxGestures.get(fx) !== gestureId) return;
      dispatch({type: "fx", fx, value});
      if (["recording", "flushing"].includes(state.recording.phase)) {
        void controller.recordRawEvent({kind: "fx_move", gestureId, fx, value}).catch(fail);
      } else {
        void session.applyFxGesture({kind: "fx_move", fx, value}).catch(fail);
      }
    },
    releaseFx(gestureId, fx) {
      if (openFxGestures.get(fx) !== gestureId) return;
      if (encoderFxGestures.get(fx) === gestureId) return;
      openFxGestures.delete(fx);
      if (["recording", "flushing"].includes(state.recording.phase)) {
        void controller.recordRawEvent({kind: "fx_release", gestureId, fx}).catch(fail);
      } else {
        void session.applyFxGesture({kind: "fx_release", fx}).catch(fail);
      }
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
      encoderFxGestures.set(fx, gestureId);
    },
    releaseEncoderFx() {
      for (const [fx, gestureId] of encoderFxGestures) {
        encoderFxGestures.delete(fx);
        controller.releaseFx(gestureId, fx);
        if (!state.hold) dispatch({type: "fx", fx, value: 500});
      }
    },
    toggleHold() {
      const value = !state.hold;
      dispatch({type: "hold", value});
      if (["recording", "flushing"].includes(state.recording.phase)) {
        void controller.recordRawEvent({kind: value ? "hold_on" : "hold_off"}).catch(fail);
      } else {
        void session.applyFxGesture({kind: value ? "hold_on" : "hold_off"}).catch(fail);
      }
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
      dispatch({type: "authority",
        status: await session.queryPerformanceRecordingStatus()});
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
        if (replay.state !== "playing") dispatch({type: "neutral"});
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
