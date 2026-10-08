import {SystemSurface, ProviderSettings} from "./components/system_surface";
import {CREATOR_DEFAULT_SOUND_SET} from "../../../products/lmdj/creator-defaults.mjs";
import {claimDefaultSeed, readDefaultSeed, type DefaultSeed} from "./state/default_seed";
import {createDefaultSeedController} from "./runtime/default_seed_controller";
import type {CreatorSlotSoundSetRuntimeSession} from "./runtime/runtime_types";
import {useAuthoringHistory} from "./components/authoring_history";
import {slotAddress} from "./state/view_model";
import {CandidateSurface, isCandidateSession} from "./components/candidate_surface";
import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";

import {
  appendDiagnostic, diagnosticRecord, DiagnosticsLog, type DiagnosticRecord,
} from "./components/diagnostics_log";
import {ErrorPanel} from "./components/error_panel";
import {DiagnosticsProvider} from "./runtime/diagnostics_context";
import {PUBLIC_ERROR_CODES, sampleMessage} from "./state/error_messages";
import {RecoveryPrompt, type RecoveryCounts} from "./components/recovery_prompt";
import {
  TakenOverPanel,
  TakeoverPending,
  takeoverNote,
} from "./components/takeover_panel";
import {
  HardwareConsole,
  retireCreatorLayoutPreference,
} from "./components/hardware_console";
import type {CreatorMode} from "./components/creator_mode";
import {OverviewDisplay} from "./components/overview_display";
import {PadSurface} from "./components/pad_surface";
import {PhysicalControls} from "./components/physical_controls";
import {PerformSurface} from "./components/perform_surface";
import {ProjectSurface} from "./components/project_surface";
import {ProjectTouchWorkspace} from "./components/project_touch_workspace";
import {SampleSurface} from "./components/sample_surface";
import {SequenceTouchWorkspace} from "./components/sequence_touch_workspace";
import {
  isSoundSetSession,
  SoundSetSurface,
} from "./components/soundset_surface";
import type {MidiStatus} from "./components/midi_status";
import {
  createAcceptanceReport,
  serializeAcceptanceReport,
} from "./report/acceptance_report";
import {
  createProjectActionLane,
  createProjectJourney,
  duplicateProjectJourney,
  importProjectJourney,
  listLocalProjectsJourney,
  openProjectJourney,
  refreshProjectProjectionJourney,
  type ProjectActionToken,
} from "./runtime/project_actions";
import type {CreatorBuildIdentity} from "./runtime/build_identity";
import type {
  ProjectTakeoverCoordinator,
  TakeoverOutcome,
} from "./runtime/project_takeover";
import {
  createCreatorInputController,
  type PerformancePadInputEvent,
} from "./runtime/input_controller";
import {captureCommitJourney, inspectSampleJourney, reloadPrepareJourney, retryPrepareJourney} from "./runtime/sample_actions";
import {createPadCapture, type PadCaptureState, type PadCaptureSource} from "./capture/pad_capture";
import {createPadCaptureSources} from "./capture/pad_capture_sources";
import {
  disarmSequenceCaptureJourney,
  editPatternEventsJourney,
  isPatternLengthSession,
  isSequenceSession,
  reconcileSequenceAuthoringRevision,
  refreshSequenceJourney,
} from "./runtime/sequence_actions";
import {
  inspectPatternTransportJourney,
  isPatternTransportSession,
  reconcilePatternTransportJourney,
  requestPatternTransportJourney,
} from "./runtime/pattern_transport_actions";
import {
  activateCreatorAudio,
  RuntimeProvider,
  useRuntime,
  type RuntimeProviderPhase,
} from "./runtime/runtime_context";
import type {PatternTransportIntent} from
  "@lmdj/web-runtime-platform/runtime_types";
import type {
  CreatorPatternLengthRuntimeSession,
  CreatorRuntimeSession,
  CreatorPerformanceRuntimeSession,
  CreatorSampleRuntimeSession,
  LocalProjectSummary,
  PatternEventsEditMutation,
  RuntimeSessionFactory,
  TypedRuntimeError,
  SequenceRecoveryCandidate,
} from "./runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  selectCanStartGesture,
  selectCanCreateProject,
  selectCanDuplicateProject,
  selectCanImportProject,
  selectCanOpenProject,
  selectCreatorPhase,
  type CreatorState,
} from "./state/creator_state";
import {readLastProjectId, writeLastProjectId} from "./state/last_project";
import {
  readMetronomePreference,
  writeMetronomePreference,
} from "./state/metronome_preference";
import {
  contextSecondsToEngineFrame,
  engineFrameToContextSeconds,
  hasAnchor as hasAudioClockAnchor,
  invalidate as invalidateAudioClockAnchor,
  retainedAudioContext,
  sampleAnchor as sampleAudioClockAnchor,
} from "./runtime/audio_clock";
import {beatsInWindow} from "./runtime/metronome_scheduler";
import {createMetronomeClickLoop} from "./runtime/metronome_click";
import {
  initialSequenceState,
  reduceSequence,
  type SequenceState,
} from "./state/sequence_state";
import {
  DEFAULT_SEQUENCE_GRID_SNAP,
  sequenceGridFlatSlot,
  sequenceGridLiveSelection,
  type SequenceGridEdit,
  type SequenceGridEditMode,
  type SequenceGridEventKey,
  type SequenceGridSnap,
  type SequenceGridViewport,
  clampSequenceOverviewRowOffset,
  SEQUENCE_BANK_PADS,
} from "./state/sequence_grid_model";
import {createEncoderTurn, type EncoderTurn} from "./state/encoder_input";
import {
  initialPatternTransportState,
  reducePatternTransport,
  selectTransportBusy,
  selectTransportPlaying,
  selectTransportRecording,
  type PatternTransportCommand,
  type PatternTransportState,
} from "./state/pattern_transport_state";
import {
  createPerformController,
  type PerformController,
  type PerformanceRecoverySummary,
} from "./state/perform_state";
import type {CapturePhase} from "./state/capture_state";

interface AppProps {
  initialState?: CreatorState;
  runtimeFactory?: RuntimeSessionFactory;
  buildIdentity?: CreatorBuildIdentity;
  projectTakeover?: ProjectTakeoverCoordinator | null;
}

interface WorkspaceProps {
  initialState: CreatorState;
  buildIdentity?: CreatorBuildIdentity;
  session?: CreatorRuntimeSession;
  runtimePhase?: RuntimeProviderPhase;
  runtimeErrorCode?: string | null;
  runtimeErrorDetails?: Readonly<Record<string, unknown>> | undefined;
  runtimeHostState?: string;
  runtimeRecoveryProbeReady?: boolean;
  onRetryRuntime?: () => void;
  onYieldRuntime?: () => Promise<boolean>;
  projectTakeover?: ProjectTakeoverCoordinator | null;
  registerRuntimeShutdownBarrier?: (
    barrier: () => Promise<unknown>,
  ) => () => void;
}

// Protocol details are JSON, but a malformed exception must not break error
// handling, as in diagnosticRecord: unserializable details key as the code.
function runtimeErrorDetailsKey(details: Readonly<Record<string, unknown>> | undefined): string {
  try {
    return JSON.stringify(details ?? {});
  } catch {
    return "";
  }
}

type BusyRetry =
  | {kind: "list"}
  | {kind: "open"; project: LocalProjectSummary};

interface SampleRetryToken {
  readonly session: CreatorSampleRuntimeSession;
  readonly pending: Readonly<{
    kind: "retry-prepare";
    slot: number;
    expectedRevision: number;
  }>;
}

function errorDetails(error: unknown): Readonly<Record<string, unknown>> {
  const details = (error as TypedRuntimeError | null)?.details;
  return details !== null && typeof details === "object" && !Array.isArray(details)
    ? details
    : {};
}

function midiStatusFrom(diagnostics: Readonly<Record<string, unknown>>): MidiStatus | null {
  const permission = diagnostics.midi_permission;
  const count = diagnostics.connected_input_count;
  if (typeof permission !== "string") return null;
  return {
    permission,
    connectedInputCount: Number.isSafeInteger(count) && (count as number) >= 0
      ? (count as number)
      : 0,
  };
}

function isSampleSession(
  session: CreatorRuntimeSession | undefined,
): session is CreatorSampleRuntimeSession {
  const candidate = session as Partial<CreatorSampleRuntimeSession> | undefined;
  return candidate !== undefined &&
    typeof candidate.inspectSample === "function" &&
    typeof candidate.querySampleQuota === "function" &&
    typeof candidate.sampleIngestLimits === "function" &&
    typeof candidate.queryWaveform === "function" &&
    typeof candidate.importAssignSample === "function" &&
    typeof candidate.updatePad === "function" &&
    typeof candidate.resetPad === "function" &&
    typeof candidate.deletePad === "function" &&
    typeof candidate.setSamplePreview === "function" &&
    typeof candidate.clearSamplePreview === "function" &&
    typeof candidate.release === "function" &&
    typeof candidate.stopPad === "function" &&
    typeof candidate.stopAll === "function" &&
    typeof candidate.retryPrepare === "function" &&
    typeof candidate.subscribeVoiceState === "function";
}

function isDefaultSeedSession(session: CreatorRuntimeSession | undefined):
  session is CreatorSlotSoundSetRuntimeSession & CreatorSampleRuntimeSession {
  const candidate = session as Partial<CreatorSlotSoundSetRuntimeSession> | undefined;
  return isSampleSession(session) && typeof candidate?.acquireSoundSetSlot === "function" &&
    typeof candidate?.installSoundSetSlot === "function" && typeof candidate?.describeSoundSetCatalog === "function";
}

function isPerformanceSession(
  session: CreatorRuntimeSession | undefined,
): session is CreatorPerformanceRuntimeSession {
  const candidate = session as Partial<CreatorPerformanceRuntimeSession> | undefined;
  return isSampleSession(session) && candidate !== undefined &&
    typeof candidate.performanceMasterCaptureStatus === "function" &&
    typeof candidate.subscribePerformanceMasterCaptureStatus === "function" &&
    typeof candidate.startPerformanceMasterCapture === "function" &&
    typeof candidate.beginPerformanceRecording === "function" &&
    typeof candidate.recordPerformanceEvent === "function" &&
    typeof candidate.requestPerformancePatternLaunch === "function" &&
    typeof candidate.flushPerformanceRecording === "function" &&
    typeof candidate.stopPerformanceRecording === "function" &&
    typeof candidate.queryPerformanceRecordingStatus === "function" &&
    typeof candidate.assignPatternSlot === "function" &&
    typeof candidate.clearPatternSlot === "function" &&
    typeof candidate.movePatternSlot === "function" &&
    typeof candidate.listPerformances === "function" &&
    typeof candidate.inspectPerformance === "function" &&
    typeof candidate.savePerformance === "function" &&
    typeof candidate.discardPerformance === "function" &&
    typeof candidate.renamePerformance === "function" &&
    typeof candidate.deletePerformance === "function" &&
    typeof candidate.listPerformanceRecovery === "function" &&
    typeof candidate.applyPerformanceRecovery === "function" &&
    typeof candidate.discardPerformanceRecovery === "function" &&
    typeof candidate.bindPerformanceRecording === "function" &&
    typeof candidate.beginPerformanceReplay === "function" &&
    typeof candidate.stopPerformanceReplay === "function" &&
    typeof candidate.queryPerformanceReplayStatus === "function" &&
    typeof candidate.commitPerformanceResample === "function";
}

function Workspace({
  initialState,
  buildIdentity,
  session,
  runtimePhase,
  runtimeErrorCode,
  runtimeErrorDetails,
  runtimeHostState,
  runtimeRecoveryProbeReady,
  onRetryRuntime,
  onYieldRuntime,
  projectTakeover = null,
  registerRuntimeShutdownBarrier,
}: WorkspaceProps) {
  const [state, dispatch] = useReducer(creatorReducer, initialState);
  const [sequence, dispatchSequence] = useReducer(reduceSequence, initialSequenceState);
  const [transport, dispatchTransport] = useReducer(
    reducePatternTransport,
    initialPatternTransportState,
  );
  const [diagnostics, setDiagnostics] = useState<readonly DiagnosticRecord[]>([]);
  const reportFailure = useCallback((operation: string, error: unknown): string => {
    const record = diagnosticRecord(operation, error);
    setDiagnostics((records) => appendDiagnostic(records, record));
    return record.code;
  }, []);
  const [defaultSeed, setDefaultSeed] = useState<DefaultSeed | null>(null);
  const defaultSeedRef = useRef(defaultSeed);
  defaultSeedRef.current = defaultSeed;
  const defaultSeedController = useRef<ReturnType<typeof createDefaultSeedController> | null>(null);
  const [defaultSeedError, setDefaultSeedError] = useState<string | null>(null);
  const [listAttempt, setListAttempt] = useState(0);
  const [busyRetry, setBusyRetry] = useState<BusyRetry | null>(null);
  // #1679: this tab handed its Project to another tab, a Continue here is
  // waiting for the holder, and why the last one did not end here.
  const [yieldedProject, setYieldedProject] = useState<string | null>(null);
  const [takeoverRequest, setTakeoverRequest] = useState<AbortController | null>(null);
  const [takeoverOutcome, setTakeoverOutcome] = useState<TakeoverOutcome | null>(null);
  const [showLocalProjects, setShowLocalProjects] = useState(false);
  const [activeMode, setActiveMode] = useState<CreatorMode>("project");
  const [systemOpen, setSystemOpen] = useState(false);
  const systemEntry = useRef<HTMLButtonElement>(null);
  const [inputControllerEpoch, setInputControllerEpoch] = useState(0);
  const [inputControllerRevision, setInputControllerRevision] = useState(0);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyPerformPhase, setHistoryPerformPhase] = useState("idle");
  // The rail's SHIFT modifier: toggled by its key, consumed by the ← / →
  // history chord or by any other rail action.
  const [railShift, setRailShift] = useState(false);
  const [capturePhase, setCapturePhase] = useState<CapturePhase>("idle");
  const [padCaptureState, setPadCaptureState] = useState<PadCaptureState | null>(null);
  const padCapture = useRef<ReturnType<typeof createPadCapture> | null>(null);
  const padCaptureSources = useRef<ReturnType<typeof createPadCaptureSources> | null>(null);
  const padCaptureWake = useRef<Promise<boolean> | null>(null);
  const capturePhaseRef = useRef(capturePhase);
  capturePhaseRef.current = capturePhase;
  const [armedCaptureSlot, setArmedCaptureSlot] = useState<number | null>(null);
  const [captureStopRequest, setCaptureStopRequest] = useState(0);
  const [midi, setMidi] = useState<MidiStatus | null>(null);
  const [sequenceGridSnap, setSequenceGridSnap] =
    useState<SequenceGridSnap>(DEFAULT_SEQUENCE_GRID_SNAP);
  const [sequenceGridViewport, setSequenceGridViewport] =
    useState<SequenceGridViewport | null>(null);
  // The Sequence upper screen's eight-row window: encoder 2 scrolls it a row
  // at a time and a Bank key moves it to that Bank's first row. View state.
  const [overviewRowOffset, setOverviewRowOffset] = useState(0);
  useEffect(() => {
    setOverviewRowOffset(state.activeBank * SEQUENCE_BANK_PADS);
  }, [state.activeBank]);
  // Encoder 3 / 4 turns preview Tempo / Swing and commit once at rest.
  const [tempoPreview, setTempoPreview] = useState<number | null>(null);
  const [swingPreview, setSwingPreview] = useState<number | null>(null);
  const settingsCommit = useRef<(changes: {bpm?: number; swingPercent?: number}) => void>(
    () => {});
  const encoderTurn = (min: number, max: number, onPreview: (value: number | null) => void,
    commit: (value: number) => void): EncoderTurn => createEncoderTurn({
    min, max, onPreview, onCommit: commit,
    schedule: (callback, delayMs) => window.setTimeout(callback, delayMs),
    clear: (handle) => window.clearTimeout(handle as number),
  });
  const tempoTurn = useRef<EncoderTurn | null>(null);
  tempoTurn.current ??= encoderTurn(40, 240, setTempoPreview,
    (bpm) => settingsCommit.current({bpm}));
  const swingTurn = useRef<EncoderTurn | null>(null);
  swingTurn.current ??= encoderTurn(50, 75, setSwingPreview,
    (swingPercent) => settingsCommit.current({swingPercent}));
  const [sequenceGridMode, setSequenceGridMode] =
    useState<SequenceGridEditMode>("note");
  const [sequenceGridSelection, setSequenceGridSelection] =
    useState<readonly SequenceGridEventKey[]>([]);
  // A new note takes the last velocity the grid set; the grid starts at 100.
  const [sequenceGridVelocity, setSequenceGridVelocity] = useState(100);
  const [performController, setPerformController] =
    useState<PerformController | null>(null);
  const [performCaptureConfigured, setPerformCaptureConfigured] = useState(false);
  const [captureTransportOverlay, setCaptureTransportOverlay] = useState(false);
  // Per-device monitoring preference, never Project Truth; boot reads it back
  // from the Host settings store.
  const [metronomeOn, setMetronomeOn] = useState(false);
  // The grid a bpm commit while playing activates at its activation frame:
  // the old grid owns beats before it, the committed grid restarts there.
  // State (not a ref) so the metronome effect rebuilds the moment a pending
  // grid is recorded, independent of the other dependencies' timing.
  const [metronomePendingGrid, setMetronomePendingGrid] = useState<Readonly<{
    fromFrame: number;
    previousBpm: number;
    bpm: number;
  }> | null>(null);
  const [candidateAudio, setCandidateAudio] = useState<Readonly<{
    projectId: string; revision: number; preparing: boolean;
  }> | null>(null);
  const candidateAudioRef = useRef(candidateAudio);
  candidateAudioRef.current = candidateAudio;
  const importController = useRef<AbortController | null>(null);
  const projectActions = useRef(createProjectActionLane()).current;
  const sequenceAuthoringTail = useRef<Promise<void>>(Promise.resolve());
  const sequenceAuthoringRevision = useRef(0);
  const sequenceAuthoringProjectId = useRef<string | null>(null);
  // The Sequence status object current when the open Project last changed.
  // Until a Sequence action replaces it, it still describes that previous
  // Project, so its revision must not reach the new Project's authoring.
  const sequenceStatusAtProjectChange = useRef<SequenceState["status"]>(null);
  const sampleRetryAction = useRef<SampleRetryToken | null>(null);
  const inputController = useRef<ReturnType<typeof createCreatorInputController> | null>(null);
  const inputAdverseState = useRef<string | null>(null);
  const activeModeRef = useRef(activeMode);
  const performControllerRef = useRef<PerformController | null>(null);
  const projectProjectionRefreshRef = useRef<Readonly<{
    id: string;
    projectId: string;
    patternId: string;
    baseRevision: number;
  }> | null>(null);
  const sampleFilePickIntent = useRef<(slot: number) => void>(() => {});
  const samplePadDropIntent = useRef<(slot: number, file: File, target: HTMLElement) => void>(() => {});
  const armedCaptureStopIntent = useRef<() => void>(() => {});
  const stateRef = useRef(state);
  const gestureEpoch = useRef(0);
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const runtimePhaseRef = useRef(runtimePhase);
  runtimePhaseRef.current = runtimePhase;
  const gestureActivation = useRef<(event: {isTrusted: boolean}) => Promise<boolean> | null>(() => null);
  const activationInFlight = useRef<{session: CreatorRuntimeSession; promise: Promise<boolean>} | null>(null);
  const sequenceRef = useRef(sequence);
  const transportRef = useRef<PatternTransportState>(transport);
  const transportRetriedCommandRef = useRef<Readonly<{
    commandId: string;
    attempts: number;
  }> | null>(null);
  const transportSettledEpochRef = useRef(0);
  const patternSelectionRef = useRef(0);
  const armedCaptureSlotRef = useRef(armedCaptureSlot);
  stateRef.current = state;
  sequenceRef.current = sequence;
  transportRef.current = transport;
  armedCaptureSlotRef.current = armedCaptureSlot;
  activeModeRef.current = activeMode;
  if (sequenceAuthoringProjectId.current !== (state.project.current?.projectId ?? null)) {
    sequenceAuthoringProjectId.current = state.project.current?.projectId ?? null;
    sequenceAuthoringRevision.current = state.project.current?.revision ?? 0;
    sequenceStatusAtProjectChange.current = sequence.status;
  } else {
    const currentStatus = sequence.status === sequenceStatusAtProjectChange.current
      ? null
      : sequence.status;
    sequenceAuthoringRevision.current = reconcileSequenceAuthoringRevision(
      sequenceAuthoringRevision.current,
      state.project.current?.revision ?? 0,
      currentStatus?.expectedRevision ?? 0,
    );
  }

  // The workspace shell and its stored layout preference are gone; clear the
  // stale key once so no browser keeps a value nothing reads.
  useEffect(() => { retireCreatorLayoutPreference(); }, []);
  const currentProjectId = state.project.current?.projectId ?? null;
  useEffect(() => {
    if (currentProjectId !== null) void writeLastProjectId(currentProjectId);
  }, [currentProjectId]);
  // A refused Duplicate describes the Project it was asked to copy.
  const [duplicateRefusal, setDuplicateRefusal] = useState<string | null>(null);
  useEffect(() => { setDuplicateRefusal(null); }, [currentProjectId]);

  useEffect(() => {
    const project = state.project.current;
    if (project === null) return;
    // The selection belongs to the open Project: a Project that opens while
    // another's selection is still held — boot, import, library open — moves
    // the selection to its own anchor Pattern, so every Pattern view resolves.
    if (sequence.selectedPatternId !== null &&
        project.patterns.some(
          ({patternId}) => patternId === sequence.selectedPatternId)) return;
    dispatchSequence({type: "selected", patternId: project.patternId});
  }, [state.project.current, sequence.selectedPatternId]);

  // The box selection belongs to the Pattern and Bank it was drawn on.
  useEffect(() => {
    setSequenceGridSelection([]);
  }, [sequence.selectedPatternId, state.activeBank, state.project.current?.projectId]);

  // Events can change in place (Undo/Redo, a transport settle, another
  // surface's edit); keys they removed leave the selection.
  const selectedGridPattern = state.project.current?.patterns.find(
    ({patternId}) => patternId ===
      (sequence.selectedPatternId ?? state.project.current?.patternId));
  useEffect(() => {
    setSequenceGridSelection((selection) =>
      sequenceGridLiveSelection(selectedGridPattern, selection));
  }, [selectedGridPattern]);

  useEffect(() => {
    setMidi(null);
    if (!session || runtimePhase !== "ready") return;
    // Diagnostics publish on every trigger outcome; only a MIDI change may
    // re-render the shell.
    const apply = (value: Readonly<Record<string, unknown>>) => {
      const next = midiStatusFrom(value);
      setMidi((current) =>
        current?.permission === next?.permission &&
        current?.connectedInputCount === next?.connectedInputCount
          ? current
          : next);
    };
    apply(session.diagnostics());
    return session.subscribeDiagnostics(apply);
  }, [session, runtimePhase]);

  useEffect(() => {
    setPerformCaptureConfigured(false);
    if (!isPerformanceSession(session) || runtimePhase !== "ready") return;
    return session.subscribePerformanceMasterCaptureStatus((status) => {
      setPerformCaptureConfigured(status.state !== "unconfigured");
    });
  }, [session, runtimePhase]);

  // The app's single session owner opts in to the global Pattern transport:
  // one engagement identity per open Project, regenerated on replacement
  // because the runtime engagement dies with the Project session. Navigation
  // between modes never touches it.
  useEffect(() => {
    const project = state.project.current;
    if (!isPatternTransportSession(session)) return;
    if (runtimePhase !== "ready") {
      // A replaced/restarting Runtime has no engagement; never keep showing
      // the retired projection.
      if (transportRef.current.sessionId !== null) {
        dispatchTransport({type: "disengaged"});
      }
      return;
    }
    if (project === null) {
      if (transportRef.current.sessionId !== null) {
        dispatchTransport({type: "disengaged"});
      }
      return;
    }
    if (transportRef.current.sessionId !== null &&
        transportRef.current.projectId === project.projectId) return;
    transportSettledEpochRef.current = 0;
    transportRetriedCommandRef.current = null;
    const sessionId = crypto.randomUUID();
    dispatchTransport({
      type: "engaged",
      sessionId,
      projectId: project.projectId,
      revision: project.revision,
    });
    void inspectPatternTransportJourney(session, sessionId).then(
      (status) => dispatchTransport({type: "observed", status}),
      (error) => { reportFailure("Inspect transport engagement", error); },
    );
    void refreshSequence();
  }, [session, runtimePhase, state.project.current]);

  useEffect(() => {
    defaultSeedController.current?.cancel();
    defaultSeedController.current = null;
    setDefaultSeed(null);
    if (!isDefaultSeedSession(session) || runtimePhase !== "ready" || currentProjectId === null) return;
    let seed: DefaultSeed | null;
    try {seed = readDefaultSeed(localStorage, CREATOR_DEFAULT_SOUND_SET);}
    catch (error) {setDefaultSeedError("Default sounds unavailable; existing content is preserved"); reportFailure("Read default sounds", error); return;}
    if (seed === null || seed.projectId !== currentProjectId) return;
    setDefaultSeed(seed);
    let mutations = Promise.resolve();
    const controller = createDefaultSeedController({
      seed, storage: localStorage, session,
      current: () => stateRef.current.project.phase === "ready" ? stateRef.current.project.current : null,
      changed: setDefaultSeed,
      failed: (_slot, error) => {reportFailure("Acquire default sound", error);},
      refresh: async () => {if (stateRef.current.project.current?.projectId === seed.projectId) await refreshPerformProject();},
      commit: (slot, request, admit) => {
        const result = mutations.then(async () => {
          if (sessionRef.current !== session || stateRef.current.project.current?.projectId !== seed.projectId ||
              stateRef.current.project.phase !== "ready") return null;
          if (selectTransportRecording(transportRef.current) ||
              !["idle", "permission-error"].includes(capturePhaseRef.current) ||
              (padCapture.current !== null && padCapture.current.getState().phase !== "idle") ||
              !["idle", "saved", "discarded"].includes(performControllerRef.current?.getState().recording.phase ?? "idle")) return null;
          const token = beginProjectAction("open", false);
          if (token === null) return null;
          try {
            if (!admit()) return null;
            const receipt = await session.installSoundSetSlot({...CREATOR_DEFAULT_SOUND_SET,
              slotIndex: slot, bankId: 0, ...request});
            // A fulfilled receipt is durable Truth, not Runtime readiness.
            const project = await refreshPerformProject();
            try {
              const publication = await reloadPrepareJourney(session, project.patternId);
              return {committedRevision: receipt.committedRevision, runtimeRevision: publication.runtimeRevision,
                published: publication.projectId === seed.projectId && publication.runtimeReady && publication.snapshotError === null};
            } catch (error) {
              reportFailure("Publish default sound", error);
              return {committedRevision: receipt.committedRevision, runtimeRevision: null, published: false};
            }
          } finally {finishProjectAction(token);}
        });
        mutations = result.then(() => {}, () => {});
        return result;
      },
    });
    defaultSeedController.current = controller;
    void controller.start().catch(error => {
      controller.cancel();
      setDefaultSeedError("Default sounds unavailable; existing content is preserved");
      reportFailure("Initialize default sounds", error);
    });
    return () => {controller.cancel(); if (defaultSeedController.current === controller) defaultSeedController.current = null;};
  }, [session, runtimePhase, currentProjectId]);

  useEffect(() => {
    if (state.project.phase === "ready" && state.project.current !== null) {
      defaultSeedController.current?.observeProject(state.project.current);
    }
  }, [state.project.phase, state.project.current]);

  const resetInputForAdverseLifecycle = () => {
    const current = inputController.current;
    if (current !== null) {
      inputController.current = null;
      current.dispose();
      setInputControllerEpoch((epoch) => epoch + 1);
    }
    if (stateRef.current.sample.draft !== null ||
      stateRef.current.sample.auditionPlayback !== null) {
      dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
    }
  };

  useEffect(() => {
    if (!isSampleSession(session) || runtimePhase !== "ready") return;
    const sources = padCaptureSources.current ??= createPadCaptureSources();
    let source: PadCaptureSource = "microphone";
    try {if (localStorage.getItem("lmdj.creator.pad-capture-source.v1") === "master") source = "master";} catch {}
    const deps: Parameters<typeof createPadCapture>[0] = {
      ...sources,
      start: (chosen, batch, failed, signal) => sources.start(chosen,
        isPerformanceSession(session) ? session : null, padCaptureWake.current, batch, failed, signal),
      canStart: target => {
        const current = stateRef.current;
        return sessionRef.current === session && runtimePhaseRef.current === "ready" && current.project.phase === "ready" &&
          current.project.current?.projectId === target.projectId && current.project.current.revision === target.revision &&
          current.project.current.pads[target.slot]?.assetId === null && current.transfer.phase === "idle" &&
          current.sample.pendingAction === null && !projectActions.busy &&
          ["idle", "permission-error"].includes(capturePhaseRef.current) &&
          !selectTransportRecording(transportRef.current) &&
          ["idle", "saved", "discarded"].includes(performControllerRef.current?.getState().recording.phase ?? "idle");
      },
      commit: async (target, buffer, selection, retry) => {
        if (sessionRef.current !== session || stateRef.current.project.current?.projectId !== target.projectId)
          throw new Error("Return to the original Project to save this take.");
        if (runtimePhaseRef.current !== "ready" || stateRef.current.project.phase !== "ready")
          throw new Error("Wait for the original Project to reopen before saving this take.");
        if (selectTransportRecording(transportRef.current) ||
          !["idle", "saved", "discarded"].includes(performControllerRef.current?.getState().recording.phase ?? "idle"))
          throw new Error("Stop the other recording before saving this take.");
        const token = beginProjectAction("open", false);
        if (token === null) throw new Error("Another Project operation is still running.");
        try {
          const inspect = await inspectSampleJourney(session, target.slot);
          if (inspect.assetId !== null) throw new Error("This Pad now contains a sound. Keep or discard this take.");
          const result = await captureCommitJourney(session, buffer, selection,
            {slot: target.slot, expectedRevision: retry ? inspect.projectRevision : target.revision});
          if (result.kind !== "committed") throw new Error("Project changed. Review this take and save again.");
          await refreshPerformProject().catch(error => {reportFailure("Refresh saved Pad recording", error);});
          dispatch({type: "sample-action", action: {type: "slot-selected", slot: target.slot}});
          if (!result.commit.runtimePublished) reportFailure("Prepare Pad recording", {code: "COOK_FAILED"});
        } finally {finishProjectAction(token);}
      },
      changed: next => {if (padCapture.current === controller) setPadCaptureState(next);},
    };
    const controller = padCapture.current ?? createPadCapture(deps, source);
    controller.updateDeps(deps);
    padCapture.current = controller;
    setPadCaptureState(controller.getState());
    const unregister = registerRuntimeShutdownBarrier?.(() => controller.cancel());
    return () => {unregister?.(); void controller.cancel();};
  }, [session, runtimePhase, registerRuntimeShutdownBarrier]);

  useEffect(() => () => {
    const retiring = padCapture.current;
    padCapture.current = null;
    void retiring?.cancel();
  }, []);

  useEffect(() => {void padCapture.current?.cancel();}, [currentProjectId]);

  useEffect(() => () => {
    projectActions.invalidate();
    setCandidateAudio(null);
    const retiringImport = importController.current;
    sampleRetryAction.current = null;
    inputAdverseState.current = null;
    importController.current = null;
    retiringImport?.abort();
    if (retiringImport) dispatch({type: "transfer-ended"});
  }, [session]);

  useEffect(() => {
    if (!session || runtimePhase !== "ready") return;
    const common = {
      session,
      getActiveBank: () => stateRef.current.activeBank,
      isAssigned: (slot: number) =>
        (stateRef.current.project.current?.pads[slot]?.assetId !== null &&
          stateRef.current.project.current?.pads[slot]?.assetId !== undefined) ||
        (stateRef.current.sample.selectedSlot === slot &&
          stateRef.current.sample.inspect?.assetId !== null &&
          stateRef.current.sample.inspect?.assetId !== undefined),
      dispatch,
      onAdverseLifecycle: () => { gestureEpoch.current += 1; },
      canUsePad: (slot: number) => {
        const seed = defaultSeedRef.current;
        return seed?.projectId !== stateRef.current.project.current?.projectId || slot >= 16 ||
          ["ready", "retired"].includes(seed!.slots[slot]!.phase);
      },
      activateAudioForGesture: (event: {isTrusted: boolean}) => gestureActivation.current(event),
      onEmptyPadPress: (slot: number, key: object, source: import("./runtime/runtime_types").RuntimeTriggerSource,
        activation: Promise<boolean> | null) => {
        if (padCapture.current === null) return false;
        if (source === "midi") return true;
        const project = stateRef.current.project.current;
        if (project !== null) {
          padCaptureWake.current = activation;
          padCapture.current.press({projectId: project.projectId, slot, revision: project.revision}, key);
        }
        return true;
      },
      onEmptyPadRelease: (key: object) => padCapture.current?.release(key),
      onEmptyPadCancel: (key?: object) => {void padCapture.current?.cancel(key);},
      getArmedCaptureSlot: () => armedCaptureSlotRef.current,
      onArmedCaptureStop: () => armedCaptureStopIntent.current(),
      onPerformancePadEvent: (event: PerformancePadInputEvent) => {
        if (activeModeRef.current !== "perform") return;
        void performControllerRef.current?.recordRawEvent(event).catch(() => {});
      },
    };
    const controller = isSampleSession(session)
      ? createCreatorInputController({
          ...common,
          session,
          isAvailable: () =>
            stateRef.current.project.phase === "ready" &&
            stateRef.current.transfer.phase === "idle" &&
            stateRef.current.sample.pendingAction === null &&
            !(candidateAudioRef.current?.projectId === stateRef.current.project.current?.projectId &&
              (candidateAudioRef.current?.preparing ||
                stateRef.current.sample.savedRevision !== stateRef.current.sample.runtimeRevision)),
          isRuntimeCurrent: () =>
            stateRef.current.sample.savedRevision !== null &&
            stateRef.current.sample.savedRevision ===
              stateRef.current.sample.runtimeRevision,
          getAuditionPlayback: (slot) =>
            stateRef.current.sample.selectedSlot === slot
              ? stateRef.current.sample.auditionPlayback
              : null,
          onFilePickIntent: (slot) => sampleFilePickIntent.current(slot),
        })
      : createCreatorInputController({
          ...common,
          isAssigned: (slot) => common.isAssigned(slot) &&
            selectCanStartGesture(stateRef.current),
        });
    inputController.current = controller;
    // Re-render so handlers detached while the controller was absent are
    // offered again; without this the ref mutation alone never reaches the
    // surface.
    setInputControllerRevision((revision) => revision + 1);
    return () => {
      if (inputController.current === controller) {
        inputController.current = null;
        controller.dispose();
      }
    };
  }, [session, runtimePhase, inputControllerEpoch]);

  useEffect(() => {
    if (!runtimeHostState) return;
    if (runtimeHostState === "running") {
      inputAdverseState.current = null;
      dispatch({type: "audio-changed", phase: "running"});
      // Suspend retires the transport engagement (the Engine stop wipes its
      // generation), so a fresh running state re-reads the projection and its
      // epoch authority instead of trusting the pre-Suspend one.
      const current = transportRef.current;
      if (isPatternTransportSession(session) && current.sessionId !== null) {
        void inspectPatternTransportJourney(session, current.sessionId).then(
          (status) => dispatchTransport({type: "observed", status}),
          () => {},
        );
      }
    } else if (
      runtimeHostState === "recovering" && runtimeRecoveryProbeReady === true
    ) {
      dispatch({type: "audio-changed", phase: "recovering"});
    } else if (
      runtimeHostState === "interrupted" ||
      runtimeHostState === "recovering" ||
      (runtimeHostState === "audio-suspended" &&
        stateRef.current.audio.phase !== "inactive")
    ) {
      if (inputAdverseState.current !== runtimeHostState) {
        inputAdverseState.current = runtimeHostState;
        resetInputForAdverseLifecycle();
        void performControllerRef.current?.leave().catch(() => {});
        if (stateRef.current.audio.phase !== "suspending") {
          dispatch({type: "audio-changed", phase: "suspended"});
        }
      }
    }
  }, [runtimeHostState, runtimeRecoveryProbeReady]);

  // Runtime boot and Host terminal errors reach the user only as the panel's
  // message, so their code and details are recorded here (#1680). Each Host
  // notification carries a fresh details object, so an error is identified
  // by its code and details content and recorded once until it changes.
  const runtimeErrorKey = runtimeErrorCode
    ? `${runtimeErrorCode}:${runtimeErrorDetailsKey(runtimeErrorDetails)}`
    : null;
  const reportedRuntimeError = useRef<string | null>(null);
  useEffect(() => {
    if (runtimeErrorKey === reportedRuntimeError.current) return;
    reportedRuntimeError.current = runtimeErrorKey;
    if (!runtimeErrorCode) return;
    reportFailure("Runtime", Object.assign(new Error(runtimeErrorCode), {
      code: runtimeErrorCode,
      details: runtimeErrorDetails ?? {},
    }));
    // The key captures the code and details content.
  }, [runtimeErrorKey, reportFailure]);

  useEffect(() => {
    if (!runtimePhase) return;
    dispatch({
      type: "runtime-changed",
      phase: runtimePhase,
      errorCode: runtimeErrorCode ?? null,
      errorDetails: runtimeErrorDetails ?? {},
    });
  }, [runtimePhase, runtimeErrorCode, runtimeErrorDetails]);

  useEffect(() => {
    if (!session || !runtimePhase) return;
    setBusyRetry(null);
    if (runtimePhase !== "ready") return;
    let active = true;
    dispatch({type: "projects-listing"});
    // Read alongside the listing, so the library never shows while it waits.
    const remembered = readLastProjectId();
    void readMetronomePreference().then((on) => {
      if (active) setMetronomeOn(on);
    });
    void listLocalProjectsJourney(session).then(
      async (projects) => {
        if (!active) return;
        const lastId = await remembered;
        if (!active) return;
        setBusyRetry(null);
        dispatch({type: "projects-loaded", projects});
        const retained = stateRef.current.project.current;
        if (!retained) {
          // Boot: reopen the Project this device used last, or start a new
          // one when none is stored. A remembered Project that is gone while
          // others exist leaves the user in the library to choose.
          const last = lastId === null ? undefined :
            projects.find(({projectId}) => projectId === lastId);
          if (last === undefined && projects.length > 0) return;
          const token = beginProjectAction(last ? "open" : "create", false);
          if (!token) return;
          dispatch({type: "project-opening"});
          try {
            const project = last
              ? await openProjectJourney(token.session, last)
              : await createProjectJourney(token.session);
            if (active && ownsProjectAction(token)) {
              if (!last && isDefaultSeedSession(token.session)) {
                try {
                  await navigator.locks.request("lmdj.creator.default-seed.claim", () =>
                    claimDefaultSeed(localStorage, CREATOR_DEFAULT_SOUND_SET, project.projectId));
                } catch (error) {
                  setDefaultSeedError("Default sounds unavailable; existing content is preserved");
                  reportFailure("Claim default sounds", error);
                }
              }
              if (!active || !ownsProjectAction(token)) return;
              dispatch({type: "project-ready", project});
              setActiveMode("sample");
            }
          } catch (error) {
            if (!active || !ownsProjectAction(token)) return;
            reportProjectError(
              error,
              last ? {kind: "open", project: last} : null,
              last ? "Open Project" : "Create Project",
            );
            // As with New Project: the Host may have stored the Project before
            // a later read failed, so list it rather than leave it unreachable.
            if (!last) {
              try {
                const listed = await listLocalProjectsJourney(token.session);
                if (active && ownsProjectAction(token)) {
                  dispatch({type: "project-inventory-updated", projects: listed});
                }
              } catch {
                // The reported creation failure stays the visible outcome.
              }
            }
          } finally {
            finishProjectAction(token);
          }
          return;
        }
        const token = beginProjectAction("open", false);
        if (!token) return;
        dispatch({type: "project-opening"});
        const summary = projects.find(({projectId, patternId}) =>
          projectId === retained.projectId && patternId === retained.patternId);
        if (!summary) {
          if (active && ownsProjectAction(token)) {
            dispatch({type: "project-error", errorCode: "NOT_FOUND"});
          }
          finishProjectAction(token);
          return;
        }
        try {
          const project = await openProjectJourney(token.session, summary);
          if (active && ownsProjectAction(token)) {
            dispatch({type: "project-ready", project});
          }
        } catch (error) {
          if (active && ownsProjectAction(token)) {
            reportProjectError(error, {kind: "open", project: summary});
          }
        } finally {
          finishProjectAction(token);
        }
      },
      (error: unknown) => {
        if (!active) return;
        const code = reportFailure("List local Projects", error);
        setBusyRetry(code === "PROJECT_BUSY" ? {kind: "list"} : null);
        if (code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT") {
          dispatch({
            type: "runtime-changed",
            phase: "restart-required",
            errorCode: code,
            errorDetails: errorDetails(error),
          });
        } else if (code === "UNSUPPORTED_WEB_RUNTIME") {
          dispatch({
            type: "runtime-changed",
            phase: "unsupported",
            errorCode: code,
            errorDetails: errorDetails(error),
          });
        } else {
          dispatch({
            type: "project-error",
            errorCode: code,
            errorDetails: errorDetails(error),
          });
        }
      },
    );
    return () => { active = false; };
  }, [
    session,
    runtimePhase,
    listAttempt,
  ]);

  const reportProjectError = (
    error: unknown,
    retry: BusyRetry | null = null,
    operation = "Open Project",
  ) => {
    if (error instanceof DOMException && error.name === "AbortError") return;
    const code = reportFailure(operation, error);
    const details = errorDetails(error);
    setBusyRetry(code === "PROJECT_BUSY" ? retry : null);
    if (code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT") {
      dispatch({
        type: "runtime-changed",
        phase: "restart-required",
        errorCode: code,
        errorDetails: details,
      });
      return;
    }
    dispatch({type: "project-error", errorCode: code, errorDetails: details});
  };

  // `settledRevision` is the authoritative revision the caller already
  // dispatched ahead of this refresh; the token must name it, because the
  // reducer sees that revision by the time the refresh actions land — a token
  // minted from the still-stale ref would be rejected and the refreshed
  // projection, Pattern events included, silently dropped.
  const refreshPerformProject = async (settledRevision?: number) => {
    if (!session) throw new Error("Runtime session is unavailable");
    const current = stateRef.current.project.current;
    if (current === null) throw new Error("Current Project is unavailable");
    if (projectProjectionRefreshRef.current !== null) {
      throw new Error("Project projection refresh is already active");
    }
    const token = Object.freeze({
      id: crypto.randomUUID(),
      projectId: current.projectId,
      patternId: current.patternId,
      baseRevision: settledRevision ?? current.revision,
    });
    projectProjectionRefreshRef.current = token;
    dispatch({type: "project-projection-refresh-started", token});
    try {
      const project = await refreshProjectProjectionJourney(session, current);
      if (project === null) {
        throw Object.assign(new Error("Project truth did not settle"), {
          code: "HOST_PROTOCOL_MISMATCH",
        });
      }
      dispatch({type: "project-projection-refreshed", token, project});
      return project;
    } catch (error) {
      dispatch({
        type: "project-projection-refresh-failed",
        token,
        errorCode: reportFailure("Refresh Project projection", error),
      });
      throw error;
    } finally {
      if (projectProjectionRefreshRef.current === token) {
        projectProjectionRefreshRef.current = null;
      }
    }
  };

  const refreshCandidateProject = async (projectId: string, committedRevision?: number) => {
    if (!isSampleSession(session) || stateRef.current.project.current?.projectId !== projectId) {
      throw new Error("Candidate Project is no longer open");
    }
    const token = projectActions.claim(session);
    if (token === null) throw new Error("Another Project action is active");
    const owns = () => projectActions.owns(token, session) &&
      stateRef.current.project.current?.projectId === projectId;
    try {
      if (committedRevision !== undefined) {
        dispatch({type: "candidate-audio-invalidated", projectId, revision: committedRevision});
        setCandidateAudio({projectId, revision: committedRevision, preparing: true});
      }
      const project = await refreshPerformProject();
      if (!owns()) return;
      dispatch({type: "candidate-audio-invalidated", projectId, revision: project.revision});
      setCandidateAudio({projectId, revision: project.revision, preparing: true});
      const selectedPattern = sequenceRef.current.selectedPatternId;
      const patternId = project.patterns.some(pattern => pattern.patternId === selectedPattern)
        ? selectedPattern! : project.patternId;
      try {
        const publication = await reloadPrepareJourney(session, patternId);
        if (!owns()) return;
        if (publication.projectId !== projectId || publication.projectRevision !== project.revision) {
          throw new Error("Candidate audio publication does not match the refreshed Project");
        }
        dispatch({type: "candidate-audio-published", projectId, revision: project.revision,
          runtimeRevision: publication.runtimeRevision});
        setCandidateAudio(publication.runtimeReady ? null : {
          projectId, revision: project.revision, preparing: false,
        });
      } catch {
        // The adoption is already durable. An unknown/failed publication never
        // resends that command or marks the old Bank as current.
        if (owns()) setCandidateAudio({projectId, revision: project.revision, preparing: false});
      }
    } catch (error) {
      if (owns()) setCandidateAudio(current => current?.projectId === projectId
        ? {...current, preparing: false} : current);
      throw error;
    } finally {
      projectActions.finish(token);
    }
  };

  useEffect(() => {
    const project = state.project.current;
    if (!isPerformanceSession(session) || runtimePhase !== "ready" ||
      project === null) {
      performControllerRef.current = null;
      setPerformController(null);
      return;
    }
    const controller = createPerformController({
      session,
      reportFailure,
      getCreatorState: () => stateRef.current,
      refreshProject: refreshPerformProject,
      opfsAvailable: () => session.diagnostics().capabilities.opfs === true &&
        session.diagnostics().capabilities.opfsWritableReplace === true,
    });
    performControllerRef.current = controller;
    setPerformController(controller);
    const unregisterShutdownBarrier = registerRuntimeShutdownBarrier?.(
      () => controller.close(),
    );
    return () => {
      unregisterShutdownBarrier?.();
      void controller.close().catch(() => {});
      if (performControllerRef.current === controller) {
        performControllerRef.current = null;
      }
      setPerformController((current) => current === controller ? null : current);
    };
  }, [session, runtimePhase, state.project.current?.projectId,
    state.project.current?.patternId, registerRuntimeShutdownBarrier]);

  useEffect(() => {
    if (performController === null) { setHistoryPerformPhase("idle"); return; }
    const update = () => setHistoryPerformPhase(performController.getState().recording.phase);
    update();
    return performController.subscribe(update);
  }, [performController]);

  const beginProjectAction = (
    kind: "open" | "import" | "create" | "duplicate",
    requireSelector = true,
  ): ProjectActionToken | null => {
    if (!session || projectActions.busy ||
      sampleRetryAction.current !== null ||
      stateRef.current.sample.pendingAction !== null) return null;
    if (requireSelector) {
      const allowed = kind === "open"
        ? selectCanOpenProject(stateRef.current)
        : kind === "create"
          ? selectCanCreateProject(stateRef.current)
          : kind === "duplicate"
            ? selectCanDuplicateProject(stateRef.current)
            : selectCanImportProject(stateRef.current);
      if (!allowed) return null;
    }
    return projectActions.claim(session);
  };

  const ownsProjectAction = (token: ProjectActionToken): boolean =>
    session !== undefined && projectActions.owns(token, session);

  const finishProjectAction = (token: ProjectActionToken) => {
    if (ownsProjectAction(token)) projectActions.finish(token);
  };

  // Holder side of #1679. A takeover is a Project change in this tab, so it
  // obeys the same guard as opening another Project, plus idle capture and
  // transport; otherwise it is refused and nothing changes. Accepting closes
  // this Runtime through the pagehide barrier, which commits every
  // acknowledged write before the writer lease is released.
  const heldProjectId = runtimePhase === "ready"
    ? state.project.current?.projectId ?? null
    : null;
  useEffect(() => {
    if (projectTakeover === null || !onYieldRuntime || heldProjectId === null) return;
    return projectTakeover.serve(heldProjectId, () => {
      const current = transportRef.current;
      if (capturePhaseRef.current !== "idle" || selectTransportBusy(current) ||
        selectTransportPlaying(current) || selectTransportRecording(current)) {
        return {accepted: false};
      }
      const token = beginProjectAction("open");
      if (!token) return {accepted: false};
      setYieldedProject(heldProjectId);
      setTakeoverOutcome(null);
      resetInputForAdverseLifecycle();
      dispatchTransport({type: "disengaged"});
      const released = onYieldRuntime().finally(() => finishProjectAction(token));
      return {accepted: true, released};
    });
    // The guard reads refs and the current action lane, so only a change of
    // holder identity re-registers.
  }, [projectTakeover, onYieldRuntime, heldProjectId]);

  // A note explains why a Continue here did not end with this tab holding
  // the Project, so it lasts until an open replaces the Project view. A fresh
  // Runtime reaching ready is not enough: a take-back reopen can still be busy.
  useEffect(() => {
    setTakeoverOutcome(null);
  }, [state.project.current]);

  // Requester side: ask the holder, then open as usual. Only a refusal or a
  // cancel skips the open; any other outcome may have freed the writer.
  const continueHere = async (projectId: string, open: () => unknown) => {
    if (projectTakeover === null || takeoverRequest !== null) return;
    const abort = new AbortController();
    setTakeoverRequest(abort);
    setTakeoverOutcome(null);
    const outcome = await projectTakeover.request(projectId, {signal: abort.signal});
    setTakeoverRequest((pending) => pending === abort ? null : pending);
    if (outcome === "cancelled") return;
    setTakeoverOutcome(outcome);
    if (outcome !== "refused") open();
  };

  const openProject = async (summary: LocalProjectSummary) => {
    const token = beginProjectAction("open");
    if (!token) return false;
    dispatch({type: "project-opening"});
    resetInputForAdverseLifecycle();
    // Project replacement retires the Runtime engagement even when the
    // incoming Project has the same id; the projection must not keep showing
    // the retired engagement's state. The engagement effect re-engages once
    // the replacement is ready.
    dispatchTransport({type: "disengaged"});
    try {
      const project = await openProjectJourney(token.session, summary);
      if (!ownsProjectAction(token)) return false;
      dispatch({type: "project-ready", project});
      setShowLocalProjects(false);
      return true;
    } catch (error) {
      if (ownsProjectAction(token)) {
        reportProjectError(error, {kind: "open", project: summary});
      }
      return false;
    } finally {
      finishProjectAction(token);
    }
  };

  const createProject = async () => {
    const token = beginProjectAction("create");
    if (!token) return false;
    dispatch({type: "project-opening"});
    resetInputForAdverseLifecycle();
    // Same as open: creation replaces the Project session.
    dispatchTransport({type: "disengaged"});
    try {
      const project = await createProjectJourney(token.session);
      if (!ownsProjectAction(token)) return false;
      dispatch({type: "project-ready", project});
      setShowLocalProjects(false);
      setActiveMode("sample");
      return true;
    } catch (error) {
      if (!ownsProjectAction(token)) return false;
      reportProjectError(error, null, "Create Project");
      // The Host may have stored the Project before a later read failed.
      // Listing it keeps the error visible while letting the user open the
      // created Project instead of creating a second one.
      try {
        const projects = await listLocalProjectsJourney(token.session);
        if (ownsProjectAction(token)) {
          dispatch({type: "project-inventory-updated", projects});
        }
      } catch {
        // The reported creation failure stays the visible outcome.
      }
      return false;
    } finally {
      finishProjectAction(token);
    }
  };

  const duplicateProject = async () => {
    const source = stateRef.current.project.current;
    if (source === null) return false;
    const token = beginProjectAction("duplicate");
    if (!token) return false;
    setDuplicateRefusal(null);
    let copy: LocalProjectSummary;
    try {
      copy = await duplicateProjectJourney(token.session, source.projectId);
    } catch (error) {
      if (ownsProjectAction(token)) {
        const code = reportFailure("Duplicate Project", error);
        if (code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT") {
          dispatch({
            type: "runtime-changed",
            phase: "restart-required",
            errorCode: code,
            errorDetails: errorDetails(error),
          });
        } else {
          // The open Project is untouched, so the failure is shown beside the
          // action instead of as a Project error.
          setDuplicateRefusal(code);
          // A refusal copies nothing, but a failure after the Host stored the
          // copy (an invalid summary) must not hide it: list, as New Project
          // does.
          try {
            const projects = await listLocalProjectsJourney(token.session);
            if (ownsProjectAction(token)) {
              dispatch({type: "project-inventory-updated", projects});
            }
          } catch {
            // The reported Duplicate failure stays the visible outcome.
          }
        }
      }
      finishProjectAction(token);
      return false;
    }
    try {
      if (!ownsProjectAction(token)) return false;
      dispatch({type: "project-opening"});
      resetInputForAdverseLifecycle();
      // Same as open: opening the copy replaces the Project session.
      dispatchTransport({type: "disengaged"});
      const project = await openProjectJourney(token.session, copy);
      if (!ownsProjectAction(token)) return false;
      dispatch({type: "project-ready", project});
      setShowLocalProjects(false);
      return true;
    } catch (error) {
      if (!ownsProjectAction(token)) return false;
      reportProjectError(error, {kind: "open", project: copy});
      // The copy is stored even though it did not open; list it so it can be
      // opened rather than duplicated again.
      try {
        const projects = await listLocalProjectsJourney(token.session);
        if (ownsProjectAction(token)) {
          dispatch({type: "project-inventory-updated", projects});
        }
      } catch {
        // The reported open failure stays the visible outcome.
      }
      return false;
    } finally {
      finishProjectAction(token);
    }
  };

  const importProject = async (file: File) => {
    const token = beginProjectAction("import");
    if (!token) return false;
    const controller = new AbortController();
    importController.current = controller;
    resetInputForAdverseLifecycle();
    // Same as open: an import replaces the Project session, so the transport
    // projection is disengaged until the replacement is ready.
    dispatchTransport({type: "disengaged"});
    dispatch({type: "transfer-started", totalBytes: file.size});
    try {
      const project = await importProjectJourney(
        token.session,
        file,
        controller.signal,
        ({completedBytes}) => {
          if (ownsProjectAction(token)) {
            dispatch({type: "transfer-progressed", completedBytes});
          }
        },
      );
      if (!ownsProjectAction(token)) return false;
      dispatch({type: "project-ready", project});
      setShowLocalProjects(false);
      return true;
    } catch (error) {
      if (ownsProjectAction(token)) reportProjectError(error, null, "Import Project");
      return false;
    } finally {
      if (ownsProjectAction(token)) {
        dispatch({type: "transfer-ended"});
        finishProjectAction(token);
      }
      if (importController.current === controller) {
        importController.current = null;
      }
    }
  };

  const reportAudioError = (error: unknown, activeSession: CreatorRuntimeSession) => {
    const code = reportFailure("Wake audio", error);
    const hostState = activeSession.diagnostics().state;
    const phase = hostState === "failed" || hostState === "closed" ||
      hostState === "unsupported" || hostState === "restart-required"
      ? hostState : stateRef.current.runtime.phase;
    // Audio failure must not invalidate a still-open Project. The Runtime
    // owns terminal status; advisory failures retain the next gesture retry.
    dispatch({type: "runtime-changed", phase, errorCode: code, errorDetails: errorDetails(error)});
  };

  const activateAudio = (event: {isTrusted: boolean}): Promise<boolean> | null => {
    if (!session || runtimePhase !== "ready") return Promise.resolve(false);
    const pending = activationInFlight.current;
    if (pending?.session === session) return pending.promise;
    if (stateRef.current.audio.phase === "running" ||
        stateRef.current.audio.phase === "recovering") return null;
    const hostState = session.diagnostics().state;
    if (hostState === "running" || hostState === "recovering") return null;
    if (hostState !== "audio-suspended") return Promise.resolve(false);
    const priorPhase = stateRef.current.audio.phase;
    if (priorPhase !== "inactive" && priorPhase !== "suspended") return Promise.resolve(false);
    dispatch({type: "audio-changed", phase: "activating"});
    // A refused activation is a non-destructive no-op: the surface returns
    // to the phase it held before the attempt, unless a Runtime publication
    // already moved it elsewhere.
    const restorePriorPhase = () => {
      if (sessionRef.current === session) {
        dispatch({type: "audio-activation-restored", phase: priorPhase});
      }
    };
    const reservation = {session, promise: Promise.resolve(false)};
    activationInFlight.current = reservation;
    reservation.promise = (async () => {
      try {
        const activated = await activateCreatorAudio(session, event);
        if (sessionRef.current !== session) return false;
        if (!activated) {
          const diagnostics = session.diagnostics();
          if (diagnostics.error_code) {
            reportAudioError(Object.assign(new Error(diagnostics.error_code), {
              code: diagnostics.error_code,
              details: diagnostics.error_details,
            }), session);
            restorePriorPhase();
          } else {
            restorePriorPhase();
          }
        } else if (session.diagnostics().state === "running") {
          dispatch({type: "audio-changed", phase: "running"});
        }
        return activated;
      } catch (error) {
        if (sessionRef.current !== session) return false;
        // An untrusted gesture never reached the Runtime. Other failures remain
        // visible through normal error reporting, but none may destroy the
        // pre-attempt audio phase.
        if (!(error instanceof TypeError)) reportAudioError(error, session);
        restorePriorPhase();
        return false;
      } finally {
        if (activationInFlight.current === reservation) activationInFlight.current = null;
      }
    })();
    return reservation.promise;
  };
  gestureActivation.current = activateAudio;

  const suspendAudio = async () => {
    if (!session || stateRef.current.audio.phase !== "running") return;
    dispatch({type: "audio-changed", phase: "suspending"});
    try {
      await performControllerRef.current?.leave();
    } catch {
      dispatch({type: "audio-changed", phase: "running"});
      return;
    }
    if (!(await session.suspendAudio())) {
      if (selectCreatorPhase(stateRef.current) === "suspending" &&
        session.diagnostics().state === "running") {
        dispatch({type: "audio-changed", phase: "running"});
      }
      return;
    }
    if (inputAdverseState.current !== "audio-suspended") {
      inputAdverseState.current = "audio-suspended";
      resetInputForAdverseLifecycle();
    }
    dispatch({type: "audio-changed", phase: "suspended"});
  };

  const retryPrepare = async () => {
    if (!isSampleSession(session) || projectActions.busy ||
      sampleRetryAction.current !== null) return;
    const current = stateRef.current;
    const slot = current.sample.selectedSlot;
    const expectedRevision = current.sample.savedRevision;
    const patternId = current.project.current?.patternId;
    if (slot === null || expectedRevision === null || patternId === undefined ||
      current.sample.pendingAction !== null ||
      current.sample.lastError?.retryPrepare !== true) return;
    const pending = Object.freeze({
      kind: "retry-prepare" as const,
      slot,
      expectedRevision,
    });
    const token = Object.freeze({session, pending});
    sampleRetryAction.current = token;
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    try {
      const publication = await retryPrepareJourney(session, patternId);
      if (sampleRetryAction.current === token) {
        dispatch({
          type: "sample-action",
          action: {type: "retry-published", pending, publication},
        });
      }
    } catch (error) {
      if (sampleRetryAction.current === token) {
        const candidate = reportFailure("Retry Sample preparation", error);
        const code = PUBLIC_ERROR_CODES.has(candidate) ? candidate : "INTERNAL_ERROR";
        dispatch({
          type: "sample-action",
          action: {
            type: "operation-failed",
            pending,
            error: {code, message: sampleMessage(code).message},
          },
        });
      }
    } finally {
      if (sampleRetryAction.current === token) sampleRetryAction.current = null;
    }
  };

  const exportReport = () => {
    if (!session) return;
    const diagnostics = session.diagnostics();
    const report = createAcceptanceReport({
      identity: {
        productBuild: diagnostics.product_build,
        hostId: diagnostics.host_id,
        hostVersion: diagnostics.host_version,
        platformVersion: diagnostics.platform_version,
        protocolVersion: diagnostics.protocol_version,
      },
      capabilities: diagnostics.capabilities,
      diagnostics,
      bankCount: 4,
      padCount: 64,
      sampleEvidence: {
        projectRevision: state.project.current?.revision ?? state.sample.savedRevision,
        runtimeRevision: state.sample.runtimeRevision,
        operationOutcomes: state.sample.lastError?.code === "COOK_FAILED"
          ? [{operation: "prepare", outcome: "failed", errorCode: "COOK_FAILED"}]
          : [],
        triggerModeCoverage: [],
      },
      sequenceEvidence: {
        semanticState: sequence.phase,
        sessionId: sequence.sessionId,
        lastCommandId: sequence.lastCommandId,
        projectRevision: state.project.current?.revision ?? null,
        expectedRevision: sequence.status?.expectedRevision ?? null,
        nextFlushSequence: sequence.status?.nextFlushSequence ?? 0,
        pendingEventCount: sequence.status?.pendingEventCount ?? 0,
        effectiveRuntimeFrame: sequence.status?.effectiveRuntimeFrame ?? null,
        recoveryCandidateCount: sequence.recovery.length,
      },
    });
    const url = URL.createObjectURL(new Blob(
      [serializeAcceptanceReport(report)],
      {type: "application/json"},
    ));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `lmdj-creator-web-${diagnostics.product_build}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  // #1680: each time a Project opens in a Runtime Session, ask once about
  // recordings an earlier owner left unfinished. The pair, not the revision,
  // identifies an open, so in-session changes never ask again.
  const recoveryOfferFor = useRef<Readonly<{session: unknown; projectId: string}> | null>(null);
  const recoveryOfferId = useRef(0);
  const [recoveryOffer, setRecoveryOffer] = useState<Readonly<{
    id: number;
    owner: Readonly<{session: unknown; projectId: string}>;
    projectId: string;
    sequence: readonly SequenceRecoveryCandidate[];
    performance: readonly PerformanceRecoverySummary[];
  }> | null>(null);
  const openProjectId = runtimePhase === "ready" && state.project.phase === "ready"
    ? state.project.current?.projectId ?? null
    : null;
  useEffect(() => {
    if (session === undefined || openProjectId === null) return;
    const last = recoveryOfferFor.current;
    if (last !== null && last.session === session && last.projectId === openProjectId) return;
    const owner = Object.freeze({session, projectId: openProjectId});
    recoveryOfferFor.current = owner;
    setRecoveryOffer(null);
    void listInterruptedRecordings(openProjectId).then(({sequence, performance}) => {
      if (recoveryOfferFor.current !== owner) return;
      if (sequence.length + performance.length > 0) {
        recoveryOfferId.current += 1;
        setRecoveryOffer(Object.freeze({
          id: recoveryOfferId.current, owner, projectId: openProjectId, sequence, performance,
        }));
      }
    });
    // Effects keep no cancellation: the owner check discards a stale reply,
    // and a phase change within the same open must not lose the offer.
  }, [session, openProjectId]);

  const listInterruptedRecordings = async (projectId: string) => {
    const [sequence, performance] = await Promise.all([
      isSequenceSession(session)
        ? session.listSequenceRecovery(projectId).catch((error: unknown) => {
            reportFailure("List interrupted Sequence recordings", error);
            return [] as readonly SequenceRecoveryCandidate[];
          })
        : Promise.resolve([] as readonly SequenceRecoveryCandidate[]),
      isPerformanceSession(session)
        ? (session.listPerformanceRecovery() as Promise<readonly PerformanceRecoverySummary[]>)
          .catch((error: unknown) => {
            reportFailure("List interrupted Performance recordings", error);
            return [] as readonly PerformanceRecoverySummary[];
          })
        : Promise.resolve([] as readonly PerformanceRecoverySummary[]),
    ]);
    return {sequence, performance};
  };

  // The remainder is read from the same refresh that the Sequence and
  // Perform lists project, so the counts the prompt reports are what the
  // Open buttons then show. A list that could not be refreshed is read once.
  const remainingRecordings = async (projectId: string): Promise<RecoveryCounts> => {
    const sequence = await refreshSequence();
    const controller = performControllerRef.current;
    const performanceRefreshed = controller === null ? false
      : await controller.refreshRecovery().then(() => true, () => false);
    const fallback = sequence === null || !performanceRefreshed
      ? await listInterruptedRecordings(projectId)
      : null;
    return {
      sequence: (sequence ?? fallback!.sequence).length,
      performance: performanceRefreshed
        ? controller!.getState().recovery.length
        : fallback!.performance.length,
    };
  };

  // An offer acts only while its (Session, Project) open is current, so a
  // Runtime replacement mid-Keep never sends the old list's commands.
  const offerIsCurrent = (offer: NonNullable<typeof recoveryOffer>) =>
    recoveryOfferFor.current === offer.owner;
  const untouched = (offer: NonNullable<typeof recoveryOffer>): RecoveryCounts => ({
    sequence: offer.sequence.length, performance: offer.performance.length,
  });

  // Keep restores each recording to where it was made; one the Core refuses
  // stays in its list and is counted as remaining.
  const keepInterruptedRecordings = async (): Promise<RecoveryCounts> => {
    const offer = recoveryOffer;
    if (offer === null) return {sequence: 0, performance: 0};
    for (const candidate of offer.sequence) {
      if (!isSequenceSession(session) || !offerIsCurrent(offer)) break;
      try {
        const status = await session.applySequenceRecovery({
          sessionId: candidate.sessionId,
          destinationPatternId: null,
        });
        if (status.committedRevision !== null) {
          dispatch({type: "project-revision-updated", revision: status.committedRevision});
        }
      } catch (error) {
        reportFailure("Keep interrupted Sequence recording", error);
      }
    }
    for (const candidate of offer.performance) {
      if (!offerIsCurrent(offer)) break;
      try {
        await performControllerRef.current?.applyRecovery(candidate.sessionId);
      } catch (error) {
        reportFailure("Keep interrupted Performance recording", error);
      }
    }
    // An open replaced mid-Keep claims nothing: its prompt is gone and the
    // new open asks again about whatever is still waiting.
    if (!offerIsCurrent(offer)) return untouched(offer);
    return remainingRecordings(offer.projectId);
  };

  const discardInterruptedRecordings = async (): Promise<RecoveryCounts> => {
    const offer = recoveryOffer;
    if (offer === null) return {sequence: 0, performance: 0};
    for (const candidate of offer.sequence) {
      if (!isSequenceSession(session) || !offerIsCurrent(offer)) break;
      try {
        await session.discardSequenceRecovery(candidate.sessionId);
      } catch (error) {
        reportFailure("Discard interrupted Sequence recording", error);
      }
    }
    for (const candidate of offer.performance) {
      if (!offerIsCurrent(offer)) break;
      try {
        await performControllerRef.current?.discardRecovery(candidate.sessionId);
      } catch (error) {
        reportFailure("Discard interrupted Performance recording", error);
      }
    }
    if (!offerIsCurrent(offer)) return untouched(offer);
    return remainingRecordings(offer.projectId);
  };

  const sequenceFailure = (operation: string, error: unknown) => {
    dispatchSequence({type: "failed", errorCode: reportFailure(operation, error)});
  };

  // Resolves the recovery list it projected, or null when none was read.
  const refreshSequence = async (): Promise<readonly SequenceRecoveryCandidate[] | null> => {
    const project = stateRef.current.project.current;
    if (!isSequenceSession(session) || project === null) return null;
    try {
      const authority = await refreshSequenceJourney(session, project.projectId);
      // The transport commits through its own coordinator, so the legacy
      // Sequence status can lag Project Truth; reconcile the revision against
      // the authoritative projection as well.
      const inspected = await session.inspectProject();
      const inspectedRevision =
        inspected !== null && typeof inspected === "object" &&
        "project_revision" in inspected &&
        typeof inspected.project_revision === "number" &&
        Number.isInteger(inspected.project_revision) &&
        inspected.project_revision >= 0
          ? inspected.project_revision
          : null;
      // A refresh that outlived its Project describes the previous one.
      if (stateRef.current.project.current?.projectId !== project.projectId) return null;
      const committedRevision = Math.max(
        authority.status.expectedRevision,
        inspectedRevision ?? 0,
      );
      sequenceAuthoringRevision.current = reconcileSequenceAuthoringRevision(
        sequenceAuthoringRevision.current,
        project.revision,
        committedRevision,
      );
      dispatchTransport({type: "revision", revision: committedRevision});
      if (transportRef.current.sessionId === null) {
        dispatchSequence({type: "authority", status: authority.status});
      } else {
        // The transport projection owns live playback/recording state, so the
        // legacy mirror only follows parked (closed) journal authority, with
        // the revision reconciled against the Project projection — the
        // transport coordinator commits outside the legacy journal status.
        if (authority.status.state === "inactive" ||
            authority.status.state === "recoverable") {
          dispatchSequence({
            type: "authority",
            status: {...authority.status, expectedRevision: committedRevision},
          });
        }
        if (committedRevision > project.revision) {
          // A transport commit advanced Project Truth. The revision display
          // follows the commit first: a failed re-read clears the Project
          // phase, which would reject this update and strand the revision.
          // Then the whole projection — Pattern events included — is re-read
          // so every view follows; the re-read reports its own failure. Its
          // token must name the committed revision just dispatched, not the
          // older one the ref still holds.
          dispatch({
            type: "project-revision-updated",
            revision: committedRevision,
          });
          await refreshPerformProject(committedRevision).catch(() => {});
        }
      }
      dispatchSequence({type: "recovery", candidates: authority.recovery});
      return authority.recovery;
    } catch (error) {
      sequenceFailure("Refresh Sequence authority", error);
      return null;
    }
  };

  // A failed submit is reconciled by inspection first; the retained command
  // is resent verbatim only when authority proves it never landed. Retry is
  // never a new inverse toggle.
  const reconcileTransport = async (): Promise<void> => {
    if (!isPatternTransportSession(session)) return;
    const current = transportRef.current;
    if (current.sessionId === null) return;
    try {
      const status = await inspectPatternTransportJourney(
        session,
        current.sessionId,
      );
      dispatchTransport({type: "observed", status});
      // The ref only advances at the next render; the retry decision below
      // needs the post-observation state, so apply the reducer locally.
      const after = reducePatternTransport(current, {type: "observed", status});
      const retained = after.lastFailed;
      const project = stateRef.current.project.current;
      const retry = transportRetriedCommandRef.current;
      // A refused command that never landed may be retried with its identical
      // identity — the Runtime sanctions this for transient pre-effect refusals
      // (a pending Pattern publication after a stopped-state switch) and for
      // lost-request classes where nothing executed. Terminal refusals (a
      // revision conflict, an invalid argument) are never resent: the error
      // stays visible and a fresh user intent gets fresh authority. Bound the
      // attempts either way.
      const RETRIABLE = after.errorCode === "HOST_STATE_INVALID" ||
        after.errorCode === "HOST_TIMEOUT" || after.errorCode === "ABORTED";
      if (retained === null || project === null || after.sessionId === null ||
          selectTransportBusy(after) || !RETRIABLE ||
          (after.status !== null && after.status.transportEpoch >= retained.epoch) ||
          (retry !== null && retry.commandId === retained.commandId &&
            retry.attempts >= 12)) {
        return;
      }
      transportRetriedCommandRef.current = {
        commandId: retained.commandId,
        attempts: retry !== null && retry.commandId === retained.commandId
          ? retry.attempts + 1
          : 1,
      };
      dispatchTransport({type: "requested", command: retained});
      try {
        const reconciled = await reconcilePatternTransportJourney(session, {
          sessionId: after.sessionId,
          projectId: project.projectId,
          commandId: retained.commandId,
          expectedEpoch: retained.epoch,
          intent: retained.intent,
          expectedRevision: retained.expectedRevision,
        });
        dispatchTransport({
          type: "submitted",
          commandId: retained.commandId,
          status: reconciled.ticket.status,
        });
        dispatchTransport({type: "observed", status: reconciled.status});
      } catch (error) {
        dispatchTransport({
          type: "failed",
          command: retained,
          errorCode: reportFailure(`Reconcile transport ${retained.intent}`, error),
        });
      }
    } catch (error) {
      dispatchTransport({type: "observe-failed", errorCode: reportFailure("Inspect transport", error)});
      return;
    }
  };

  const submitTransportIntent = async (intent: PatternTransportIntent) => {
    if (intent === "record" && (
      (padCapture.current !== null && padCapture.current.getState().phase !== "idle") ||
      !["idle", "permission-error"].includes(capturePhaseRef.current) ||
      !["idle", "saved", "discarded"].includes(performControllerRef.current?.getState().recording.phase ?? "idle")
    )) return;
    const project = stateRef.current.project.current;
    const current = transportRef.current;
    if (!isPatternTransportSession(session) || project === null ||
        current.sessionId === null || current.projectId !== project.projectId ||
        (stateRef.current.audio.phase !== "running" && session.diagnostics().state !== "running") ||
        selectTransportBusy(current)) {
      return;
    }
    const epoch = Math.max(
      current.status?.transportEpoch ?? 0,
      current.pending?.epoch ?? 0,
      current.lastFailed?.epoch ?? 0,
    ) + 1;
    const command: PatternTransportCommand = Object.freeze({
      commandId: crypto.randomUUID(),
      intent,
      epoch,
      // Journal creation is the only intent that needs revision authority;
      // an absent/null revision on any other intent preserves the retained
      // one.
      expectedRevision: intent === "record" &&
          current.status?.recording !== true
        ? sequenceAuthoringRevision.current
        : null,
    });
    dispatchTransport({type: "requested", command});
    try {
      const ticket = await requestPatternTransportJourney(session, {
        sessionId: current.sessionId,
        projectId: project.projectId,
        commandId: command.commandId,
        expectedEpoch: command.epoch,
        intent,
        expectedRevision: command.expectedRevision,
      });
      dispatchTransport({
        type: "submitted",
        commandId: command.commandId,
        status: ticket.status,
      });
    } catch (error) {
      dispatchTransport({type: "failed", command, errorCode: reportFailure(`Transport ${intent}`, error)});
      void reconcileTransport();
    }
  };

  const transportBusy = selectTransportBusy(transport);
  // Busy and failed operations are observed through inspection until they
  // settle; the runtime drives the continuation cadence, the Creator only
  // polls the projection.
  useEffect(() => {
    if (!isPatternTransportSession(session) || transport.sessionId === null) {
      return;
    }
    if (!transportBusy && transport.lastFailed === null) return;
    const timer = window.setInterval(() => {
      void reconcileTransport();
    }, 250);
    return () => window.clearInterval(timer);
  }, [session, transport.sessionId, transportBusy, transport.lastFailed]);

  // A newly settled operation re-reads journal/recovery authority once, so a
  // committed Record-off surfaces its revision and a failed one its recovery.
  useEffect(() => {
    const status = transport.status;
    if (status === null || !status.engaged || status.phase !== "idle" ||
        status.transportEpoch === 0 ||
        status.transportEpoch <= transportSettledEpochRef.current) {
      return;
    }
    transportSettledEpochRef.current = status.transportEpoch;
    transportRetriedCommandRef.current = null;
    void refreshSequence();
  }, [transport.status]);

  // The metronome is a Host monitoring loop: it runs only while the switch is
  // on, audio is running and the transport is playing or recording, and it
  // schedules clicks on the AudioContext clock from the engine-frame beat
  // grid through the audio clock anchor. The anchor is re-sampled whenever
  // audio (re)enters running — each activation is a new engine epoch — and
  // invalidated when audio leaves running. Any grid-affecting change (a new
  // transport origin, a committed bpm, a pending activation frame) rebuilds
  // the loop, which cancels every click that has not sounded.
  const metronomeAudioPhase = state.audio.phase;
  const metronomePlaying = selectTransportPlaying(transport) ||
    selectTransportRecording(transport);
  const metronomeOriginFrame = transport.status?.originFrame ?? null;
  const metronomeBpm = state.project.current?.bpm ?? null;
  useEffect(() => {
    const context = retainedAudioContext();
    if (!metronomeOn || metronomeAudioPhase !== "running" || !metronomePlaying ||
        session == null || context === null ||
        metronomeOriginFrame === null || metronomeBpm === null) {
      if (metronomeAudioPhase !== "running") invalidateAudioClockAnchor();
      if (!metronomePlaying && metronomePendingGrid !== null) {
        setMetronomePendingGrid(null);
      }
      return;
    }
    if (!hasAudioClockAnchor()) {
      try {
        sampleAudioClockAnchor(session);
      } catch {
        // Audio left running between the phase dispatch and this sample.
        return;
      }
    }
    if (metronomePendingGrid !== null &&
        metronomePendingGrid.fromFrame <= metronomeOriginFrame) {
      // The transport projection caught up with the committed grid.
      setMetronomePendingGrid(null);
    }
    const segments = metronomePendingGrid !== null
      ? [
          {
            fromFrame: 0,
            originFrame: metronomeOriginFrame,
            bpm: metronomePendingGrid.previousBpm,
          },
          {
            fromFrame: metronomePendingGrid.fromFrame,
            originFrame: metronomePendingGrid.fromFrame,
            bpm: metronomePendingGrid.bpm,
          },
        ]
      : [{fromFrame: 0, originFrame: metronomeOriginFrame, bpm: metronomeBpm}];
    const loop = createMetronomeClickLoop({
      context,
      supply: (fromSeconds, untilSeconds) => {
        const fromFrame = Math.max(
          0, Math.ceil(contextSecondsToEngineFrame(fromSeconds)));
        const toFrame = Math.max(
          fromFrame, Math.ceil(contextSecondsToEngineFrame(untilSeconds)));
        return beatsInWindow({fromFrame, toFrame, segments}).map((beat) => ({
          contextTime: engineFrameToContextSeconds(beat.frame),
          beat: beat.beat,
          accent: beat.accent,
        }));
      },
    });
    loop.start(context.currentTime);
    return () => loop.stop();
  }, [
    session,
    metronomeOn,
    metronomeAudioPhase,
    metronomePlaying,
    metronomeOriginFrame,
    metronomeBpm,
    metronomePendingGrid,
  ]);

  const onToggleMetronome = () => {
    const next = !metronomeOn;
    setMetronomeOn(next);
    void writeMetronomePreference(next);
  };

  const stopArmedCapture = async () => {
    const current = sequenceRef.current;
    if (current.phase === "flushing") return;
    setCaptureStopRequest((request) => request + 1);
  };
  armedCaptureStopIntent.current = () => { void stopArmedCapture(); };

  // One grid gesture commits one atomic edit at gesture end. The command goes
  // through the Runtime Session with flat Pad slots; a live or stopped edit of
  // the current Pattern swaps in place immediately, a deferred one is
  // committed Truth like any other, and only a failed swap is surfaced. A
  // transport-busy or publication-pending refusal lands before the commit, so
  // it is retried, never shown as a conflict; any other conflict or refusal
  // restores the grid from Truth and shows the reason.
  const editSequenceGridEvents = (edit: SequenceGridEdit): Promise<void> => {
    const operation = sequenceAuthoringTail.current.then(async () => {
      const project = stateRef.current.project.current;
      if (!isSequenceSession(session) || project === null) return;
      if (selectTransportRecording(transportRef.current)) {
        // The grid is disabled while recording; a gesture that raced the
        // transition is refused here as the Core would refuse it.
        return;
      }
      const patternId = sequenceRef.current.selectedPatternId ?? project.patternId;
      const request = {
        patternId,
        remove: edit.remove.map((key) => ({
          slot: sequenceGridFlatSlot(key.bank, key.pad),
          onsetTick: key.onsetTick,
        })),
        put: edit.put.map((event) => ({
          slot: sequenceGridFlatSlot(event.bank, event.pad),
          onsetTick: event.onsetTick,
          durationTick: event.durationTick,
          velocity: event.velocity,
        })),
      };
      try {
        let result: PatternEventsEditMutation | null = null;
        // A pending bar-boundary publication can hold the admission for a
        // bar; the bounded retry never reissues a committed edit because the
        // refusal happens before the commit. Each attempt is a fresh domain
        // command (the Session mints the command identity per call) naming
        // the current revision: the busy window is exactly when a settle can
        // land an intervening commit, so a frozen revision would die as a
        // conflict.
        for (let attempt = 0; attempt < 32; attempt += 1) {
          try {
            result = await editPatternEventsJourney(session, {
              ...request,
              expectedRevision: sequenceAuthoringRevision.current,
            });
            break;
          } catch (error) {
            const reason = errorDetails(error).reason;
            if ((reason !== "pattern_transport_busy" &&
                reason !== "pattern_publication_pending") ||
                attempt === 31) {
              throw error;
            }
            await new Promise((resolve) => {
              window.setTimeout(resolve, 250);
            });
            if (stateRef.current.project.current?.projectId !== project.projectId) {
              return;
            }
            // Re-read the revision the next attempt names, reconciled the
            // way refreshSequence does — without its dispatches, which would
            // put the project reducer ahead of this journey's own projection
            // refresh token.
            const inspected = await session.inspectProject();
            const inspectedRevision =
              inspected !== null && typeof inspected === "object" &&
              "project_revision" in inspected &&
              typeof inspected.project_revision === "number" &&
              Number.isInteger(inspected.project_revision) &&
              inspected.project_revision >= 0
                ? inspected.project_revision
                : null;
            // Without a readable revision the next attempt would name a
            // known-stale one and die as a conflict; surface this refusal.
            if (inspectedRevision === null) throw error;
            sequenceAuthoringRevision.current =
              reconcileSequenceAuthoringRevision(
                sequenceAuthoringRevision.current,
                stateRef.current.project.current?.revision ?? 0,
                inspectedRevision,
              );
          }
        }
        if (result === null) return;
        sequenceAuthoringRevision.current = result.committedRevision;
        dispatchTransport({type: "revision", revision: result.committedRevision});
        try {
          await refreshPerformProject();
        } catch {
          dispatch({
            type: "project-revision-updated",
            revision: result.committedRevision,
          });
        }
        if (result.snapshotError !== null) {
          // The edit committed; only the in-place swap failed. Say so
          // instead of letting the grid look unheard.
          dispatchSequence({
            type: "failed",
            errorCode: result.snapshotError.code,
          });
        }
      } catch (error) {
        try {
          await refreshPerformProject();
        } catch (refreshError) {
          reportFailure("Restore Sequence grid projection", refreshError);
        }
        sequenceFailure("Edit Pattern events", error);
      }
    });
    sequenceAuthoringTail.current = operation;
    return operation;
  };

  const updateSequenceSettings = (changes: Readonly<{
    bpm?: number;
    quantizeEnabled?: boolean;
    swingPercent?: number;
  }>): Promise<void> => {
    const operation = sequenceAuthoringTail.current.then(async () => {
      const project = stateRef.current.project.current;
      const currentSequence = sequenceRef.current;
      if (!isSequenceSession(session) || project === null) return;
      const currentTransport = transportRef.current;
      if (currentTransport.sessionId !== null &&
          (selectTransportBusy(currentTransport) ||
            selectTransportRecording(currentTransport))) {
        // The runtime rejects a settings write mid-recording: its admission
        // fence retains the timing authority.
        return;
      }
      const result = await session.updateSequenceSettings({
        expectedRevision: sequenceAuthoringRevision.current,
        sessionId: currentSequence.sessionId,
        bpm: changes.bpm ?? null,
        quantizeEnabled: changes.quantizeEnabled ?? null,
        swingPercent: changes.swingPercent ?? null,
      });
      sequenceAuthoringRevision.current = result.committedRevision;
      dispatchTransport({type: "revision", revision: result.committedRevision});
      if (result.patternPublication !== null &&
          selectTransportPlaying(currentTransport)) {
        // A bpm commit while playing activates the new grid at the returned
        // activation frame; the metronome switches grids there.
        setMetronomePendingGrid({
          fromFrame: result.patternPublication.activationFrame,
          previousBpm: project.bpm,
          bpm: result.bpm,
        });
      }
      dispatch({
        type: "project-sequence-settings-updated",
        revision: result.committedRevision,
        bpm: result.bpm,
        quantizeEnabled: result.quantizeEnabled,
        swingPercent: result.swingPercent,
      });
      await refreshSequence();
    }).catch((error) => sequenceFailure("Update Sequence settings", error));
    sequenceAuthoringTail.current = operation;
    return operation;
  };

  const createPattern = (bars: 1 | 2 | 4 | 8): Promise<void> => {
    const operation = sequenceAuthoringTail.current.then(async () => {
      const project = stateRef.current.project.current;
      const currentTransport = transportRef.current;
      const transportActive = currentTransport.sessionId !== null &&
        (selectTransportBusy(currentTransport) ||
          selectTransportPlaying(currentTransport) ||
          selectTransportRecording(currentTransport));
      if (!isSequenceSession(session) || project === null || transportActive ||
          (currentTransport.sessionId === null &&
            sequenceRef.current.phase !== "stopped")) return;
      const patternId = crypto.randomUUID();
      const result = await session.createPattern({
        patternId,
        bars,
        expectedRevision: sequenceAuthoringRevision.current,
      });
      sequenceAuthoringRevision.current = result.committedRevision;
      dispatchTransport({type: "revision", revision: result.committedRevision});
      dispatch({
        type: "project-pattern-created",
        revision: result.committedRevision,
        pattern: {patternId: result.patternId, bars: result.bars, events: []},
      });
      if (currentTransport.sessionId !== null &&
          isPatternTransportSession(session)) {
        // Make the new Pattern runtime-current so the next Play starts it.
        await session.reloadSnapshot(result.patternId);
      }
      dispatchSequence({type: "selected", patternId: result.patternId});
    }).catch((error) => sequenceFailure("Create Pattern", error));
    sequenceAuthoringTail.current = operation;
    return operation;
  };

  // SETUP's BARS, DOUBLE UP and COPY (#1823): one commit and one Undo entry
  // each, admitted only while stopped, as CREATE is, and serialized on the
  // same authoring tail. Bars, notes and slots are re-read from Truth, since
  // shortening drops and cuts notes and a copy may take a Pattern slot. The
  // Host republishes a resized runtime-current Pattern itself, so the next
  // Play uses the new length; only a failed swap is surfaced. A copy is
  // selected as a created Pattern is.
  const commitPatternStructure = (
    operationName: "Change Pattern Length" | "Double Up Pattern" | "Copy Pattern",
    commit: (
      session: CreatorPatternLengthRuntimeSession,
      patternId: string,
      expectedRevision: number,
    ) => Promise<Readonly<{
      committedRevision: number;
      patternId: string;
      snapshotError?: Readonly<{code: string}> | null;
    }>>,
  ): Promise<void> => {
    const operation = sequenceAuthoringTail.current.then(async () => {
      const project = stateRef.current.project.current;
      const currentTransport = transportRef.current;
      const transportActive = currentTransport.sessionId !== null &&
        (selectTransportBusy(currentTransport) ||
          selectTransportPlaying(currentTransport) ||
          selectTransportRecording(currentTransport));
      if (!isPatternLengthSession(session) || project === null || transportActive ||
          (currentTransport.sessionId === null &&
            sequenceRef.current.phase !== "stopped")) return;
      const patternId = sequenceRef.current.selectedPatternId ?? project.patternId;
      const result = await commit(session, patternId, sequenceAuthoringRevision.current);
      sequenceAuthoringRevision.current = result.committedRevision;
      dispatchTransport({type: "revision", revision: result.committedRevision});
      try {
        await refreshPerformProject();
      } catch {
        dispatch({type: "project-revision-updated", revision: result.committedRevision});
      }
      if (result.patternId !== patternId) {
        if (currentTransport.sessionId !== null &&
            isPatternTransportSession(session)) {
          // Make the copy runtime-current so the next Play starts it.
          await session.reloadSnapshot(result.patternId);
        }
        dispatchSequence({type: "selected", patternId: result.patternId});
      }
      if (result.snapshotError != null) {
        dispatchSequence({type: "failed", errorCode: result.snapshotError.code});
      }
    }).catch((error) => sequenceFailure(operationName, error));
    sequenceAuthoringTail.current = operation;
    return operation;
  };

  const resizePattern = (bars: 1 | 2 | 4 | 8) => commitPatternStructure(
    "Change Pattern Length",
    (target, patternId, expectedRevision) =>
      target.resizePattern({patternId, bars, expectedRevision}),
  );
  const doubleUpPattern = () => commitPatternStructure(
    "Double Up Pattern",
    (target, patternId, expectedRevision) =>
      target.doubleUpPattern({patternId, expectedRevision}),
  );
  const copyPattern = () => commitPatternStructure(
    "Copy Pattern",
    (target, sourcePatternId, expectedRevision) => target.copyPattern({
      sourcePatternId,
      patternId: crypto.randomUUID(),
      expectedRevision,
    }),
  );

  const capturePhaseChanged = useCallback((phase: CapturePhase) => {
    setCapturePhase(phase);
    if (phase === "trimming" || phase === "commit-error" || phase === "committing") {
      dispatchSequence({type: "trim-overlay"});
      // Capture owns recording exclusively in P1, while Pattern playback may
      // continue. Its trim dialog must be visible on Sequence even when no
      // Pattern journal exists; the Host-local flag carries that review.
      const legacySequenceActive =
        ["recording", "switch-pending"].includes(sequenceRef.current.phase) &&
        sequenceRef.current.sessionId !== null;
      if (!legacySequenceActive && activeModeRef.current === "sequence" &&
          armedCaptureSlotRef.current !== null) {
        setCaptureTransportOverlay(true);
      }
    } else if (phase === "idle" || phase === "permission-error") {
      setCaptureTransportOverlay(false);
      const currentSequence = sequenceRef.current;
      const slot = armedCaptureSlotRef.current;
      if (isSequenceSession(session) && currentSequence.sessionId !== null && slot !== null) {
        void disarmSequenceCaptureJourney(
          session, currentSequence.sessionId, slot,
        ).then(async () => {
          const project = stateRef.current.project.current;
          if (project !== null) {
            const authority = await refreshSequenceJourney(
              session, project.projectId,
            );
            sequenceAuthoringRevision.current = reconcileSequenceAuthoringRevision(
              sequenceAuthoringRevision.current,
              project.revision,
              authority.status.expectedRevision,
            );
            dispatchSequence({type: "authority", status: authority.status});
            dispatchSequence({type: "recovery", candidates: authority.recovery});
          }
          dispatchSequence({type: "trim-closed"});
        }, (error) => {
          dispatchSequence({type: "failed", errorCode: reportFailure("Disarm Sequence capture", error)});
          dispatchSequence({type: "trim-closed"});
        });
      } else {
        dispatchSequence({type: "trim-closed"});
      }
    }
  }, [session]);

  const selectSequencePattern = async (patternId: string) => {
    if (!session) return;
    const current = transportRef.current;
    if (isPatternTransportSession(session) && current.sessionId !== null) {
      if (selectTransportBusy(current)) return;
      // Under the global transport, selection publishes the chosen Pattern as
      // runtime-current. A playing engagement refuses the reload honestly
      // ("stop playback before reloading another Pattern"); a stopped one is
      // retired and re-vended on the next request against the current
      // Pattern, with the Engine generation — and therefore the epoch
      // sequence — continuing. Right after a committed Record-off the
      // replaced publication can still be retiring, so the identical publish
      // is retried a few times before the refusal is shown.
      const selection = ++patternSelectionRef.current;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        try {
          await session.reloadSnapshot(patternId);
          if (patternSelectionRef.current !== selection) return;
          dispatchSequence({type: "selected", patternId});
          return;
        } catch (error) {
          const code = reportFailure("Select Pattern", error);
          if (code !== "HOST_STATE_INVALID" || attempt === 4 ||
              patternSelectionRef.current !== selection) {
            if (patternSelectionRef.current === selection) {
              dispatchSequence({type: "failed", errorCode: code});
            }
            return;
          }
          await new Promise((resolve) => {
            window.setTimeout(resolve, 400);
          });
        }
      }
      return;
    }
    if (!isSequenceSession(session)) return;
    if (sequence.phase === "recording" && sequence.sessionId !== null) {
      try {
        const status = await session.requestPatternSwitch({
          sessionId: sequence.sessionId,
          nextPatternId: patternId,
        });
        dispatchSequence({type: "switch-pending", status});
      } catch (error) {
        sequenceFailure("Switch Pattern", error);
      }
      return;
    }
    dispatchSequence({type: "selected", patternId});
  };

  const canOpenProject = session !== undefined &&
    !projectActions.busy &&
    sampleRetryAction.current === null &&
    state.sample.pendingAction === null &&
    selectCanOpenProject(state);
  const canImportProject = session !== undefined &&
    !projectActions.busy &&
    sampleRetryAction.current === null &&
    state.sample.pendingAction === null &&
    selectCanImportProject(state);
  const canCreateProject = session !== undefined &&
    !projectActions.busy &&
    sampleRetryAction.current === null &&
    state.sample.pendingAction === null &&
    selectCanCreateProject(state);
  const canDuplicateProject = session !== undefined &&
    !projectActions.busy &&
    sampleRetryAction.current === null &&
    state.sample.pendingAction === null &&
    selectCanDuplicateProject(state);
  const staleSampleRuntime = state.sample.lastError?.code === "COOK_FAILED" &&
    state.sample.lastError.retryPrepare && state.sample.savedRevision !== null &&
    state.sample.runtimeRevision !== state.sample.savedRevision;
  const sequenceEnabled = isSequenceSession(session) &&
    state.project.phase === "ready" && state.project.current !== null;
  const performEnabled = performController !== null && performCaptureConfigured &&
    state.project.phase === "ready" && state.project.current !== null;
  const sliceEnabled = isCandidateSession(session) && state.project.phase === "ready" &&
    state.project.current !== null && sequence.phase === "stopped";
  const soundSetEnabled = isSoundSetSession(session);
  // Physical Play/Stop and Record always mean the global Pattern transport —
  // never Sample capture or master recording — and every mode consumes this
  // same projection.
  const transportReady = isPatternTransportSession(session) &&
    transport.sessionId !== null &&
    state.project.phase === "ready" && state.project.current !== null &&
    selectCanStartGesture(state) && (
      state.audio.phase === "running" ||
      (runtimeHostState === "audio-suspended" &&
        (state.audio.phase === "inactive" || state.audio.phase === "suspended"))
    );
  const recording = selectTransportRecording(transport);
  const playing = selectTransportPlaying(transport);
  // Tempo and Swing lock while recording or while a transport command
  // settles, as the touch controls do; a turn in progress is dropped.
  const sequenceSettingsLocked = transportBusy || recording;
  useEffect(() => {
    if (!sequenceSettingsLocked) return;
    tempoTurn.current?.cancel();
    swingTurn.current?.cancel();
  }, [sequenceSettingsLocked]);
  // A failed settings commit leaves Truth where it was; the next turn starts
  // from Truth rather than from the request that did not land.
  useEffect(() => {
    if (sequence.errorCode === null) return;
    tempoTurn.current?.forget();
    swingTurn.current?.forget();
  }, [sequence.errorCode]);
  settingsCommit.current = (changes) => { void updateSequenceSettings(changes); };
  const sequenceProject = state.project.current;
  const sequencePatterns = sequenceProject?.patterns ?? [];
  const sequencePatternIndex = sequencePatterns.findIndex((item) =>
    item.patternId === (sequence.selectedPatternId ?? sequenceProject?.patternId));
  // The direction keys switch Pattern only while stopped, like ‹ ›.
  const patternStepOpen = activeMode === "sequence" && sequenceProject !== null &&
    !playing && !sequenceSettingsLocked && sequencePatternIndex >= 0;
  const stepPatternBy = (offset: -1 | 1) => {
    const next = sequencePatterns[sequencePatternIndex + offset];
    if (patternStepOpen && next !== undefined) void selectSequencePattern(next.patternId);
  };
  // The armed-Capture trim overlay over an active recording, whether the
  // recording is a legacy Sequence session or the global Pattern transport.
  const trimOverlayOpen = sequence.phase === "trim-overlay" ||
    captureTransportOverlay;
  const applyMode = (mode: CreatorMode) => {
    setActiveMode(mode);
  };
  const openSystem = () => {
    inputController.current?.clearPressed();
    void padCapture.current?.cancel();
    setSystemOpen(true);
  };
  const selectMode = (mode: CreatorMode) => {
    setSystemOpen(false);
    inputController.current?.clearPressed();
    setRailShift(false);
    // Normal navigation never stops the global Pattern transport; only the
    // separately owned performance recording leaves with its mode.
    if (activeModeRef.current === "perform" && mode !== "perform" &&
      performControllerRef.current !== null) {
      void performControllerRef.current.leave().then(
        () => applyMode(mode),
        () => {},
      );
      return;
    }
    applyMode(mode);
  };
  const selectBank = (bank: typeof state.activeBank) => {
    inputController.current?.clearPressed();
    setRailShift(false);
    dispatch({type: "bank-selected", bank});
    const current = stateRef.current;
    if (activeMode === "sample" && armedCaptureSlot === null &&
        current.runtime.phase === "ready" && current.project.phase === "ready" &&
        current.project.current !== null && current.transfer.phase === "idle") {
      const localPad = (stateRef.current.sample.selectedSlot ?? 0) % 16;
      dispatch({type: "sample-action", action: {type: "slot-selected", slot: bank * 16 + localPad}});
    }
  };
  const runtimeActions = session && inputController.current
    ? {
        onSuspendAudio: () => { void suspendAudio(); },
        onEnableMidi: (event: ReactMouseEvent<HTMLButtonElement>) => {
          void activateAudio(event.nativeEvent);
          void inputController.current?.enableMidi();
        },
        onExportReport: exportReport,
      }
    : {};
  const padSurface = (
    <PadSurface
      state={state}
      emptyPadCapture={padCaptureState !== null}
      {...(defaultSeed?.projectId === currentProjectId ? {seedSlots: defaultSeed.slots} : {})}
      armedCaptureSlot={armedCaptureSlot}
      {...(activeMode === "sample" ? {
        onSelectSample: (slot: number) => {
          dispatch({type: "sample-action", action: {type: "slot-selected", slot}});
        },
        onChooseSample: (slot: number) => sampleFilePickIntent.current(slot),
        onDropSample: (slot: number, file: File, target: HTMLElement) =>
          samplePadDropIntent.current(slot, file, target),
      } : {})}
      {...(inputController.current ? {controller: inputController.current} : {})}
    />
  );

  const history = useAuthoringHistory({
    session,
    projectId: state.project.current?.projectId ?? null,
    revision: state.project.current?.revision ?? null,
    refreshKey: `${activeMode}:${sequence.phase}:${transport.status?.phase ?? "idle"}:${playing}:${recording}:${historyPerformPhase}`,
    disabledReason: state.project.phase !== "ready" ? "Open a Project to use its history." :
      state.runtime.phase !== "ready" ? "Wait for the audio session to become ready." :
      state.transfer.phase !== "idle" || state.sample.pendingAction !== null ||
      state.projectProjectionRefresh !== null ? "Wait for the current Project change to finish." :
      !["idle", "permission-error"].includes(capturePhase) ? "Finish or discard the sound recording first." :
      historyPerformPhase !== "idle" ? "Save or discard the Performance recording first." :
      state.sample.draft !== null ? "Finish the parameter edit first." : "",
    onBusy: setHistoryBusy,
    onChanged: async () => {
      const project = await refreshPerformProject();
      sequenceAuthoringRevision.current = project.revision;
      dispatchTransport({type: "revision", revision: project.revision});
      if (sequenceRef.current.selectedPatternId !== null &&
          !project.patterns.some(({patternId}) => patternId === sequenceRef.current.selectedPatternId)) {
        dispatchSequence({type: "selected", patternId: project.patternId});
      }
      dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
      await refreshSequence();
    },
  });

  return (
    <DiagnosticsProvider value={reportFailure}>
    <div className="hardware-workspace">
        {/* History status stays in the accessibility tree; rail lamps carry the visual state. */}
        <div role="status" className="visually-hidden" data-testid="authoring-history-status">
          {history.statusText}
        </div>
        <div inert={historyBusy} className="creator-console-frame">
        <HardwareConsole
          physicalControls={
            <PhysicalControls
              activeMode={activeMode}
              activeBank={state.activeBank}
              // The physical keys gate on the same reachability the mode rail
              // uses. A weaker condition mounted an operable-looking Sequence
              // editor whose every action silently returned without a Sequence
              // capability. Perform keeps the looser gate on purpose: its
              // touch workspace has a placeholder that names what is missing.
              sequenceEnabled={sequenceEnabled}
              performEnabled={state.project.phase === "ready" &&
                state.project.current !== null}
              onSelectMode={selectMode}
              onSelectBank={selectBank}
              onRecord={(event) => {
                setRailShift(false);
                const project = stateRef.current.project.current;
                const epoch = gestureEpoch.current;
                const activation = activateAudio(event.nativeEvent);
                if (activation === null) void submitTransportIntent("record");
                else void activation.then((ready) => {
                  if (ready && sessionRef.current === session &&
                      stateRef.current.project.current === project && gestureEpoch.current === epoch) {
                    void submitTransportIntent("record");
                  }
                });
              }}
              recordEnabled={transportReady && !transportBusy &&
                (padCaptureState === null || padCaptureState.phase === "idle") &&
                ["idle", "permission-error"].includes(capturePhase) &&
                ["idle", "saved", "discarded"].includes(historyPerformPhase)}
              recording={recording}
              onPlayStop={(event) => {
                setRailShift(false);
                const project = stateRef.current.project.current;
                const epoch = gestureEpoch.current;
                const activation = activateAudio(event.nativeEvent);
                if (activation === null) void submitTransportIntent("play_stop");
                else void activation.then((ready) => {
                  if (ready && sessionRef.current === session &&
                      stateRef.current.project.current === project && gestureEpoch.current === epoch) {
                    void submitTransportIntent("play_stop");
                  }
                });
              }}
              playEnabled={transportReady && !transportBusy}
              playing={playing}
              onOpenSystem={openSystem}
              systemOpen={systemOpen}
              systemEntryRef={systemEntry}
              // Sequence binds encoders 2–4 and the direction keys (2026-10-04
              // decision, items 4–5); encoder 1, ↑ ↓ and every other page's
              // controls wait for #1822.
              {...(activeMode === "sequence" && sequenceProject !== null ? {
                encoders: {
                  2: {
                    label: "scroll track rows",
                    onTurn: (detents: number) => setOverviewRowOffset((offset) =>
                      clampSequenceOverviewRowOffset(offset + detents)),
                  },
                  3: {
                    label: "Tempo",
                    disabled: sequenceSettingsLocked,
                    onTurn: (detents: number) => tempoTurn.current?.turn(detents, sequenceProject.bpm),
                  },
                  4: {
                    label: "Swing",
                    disabled: sequenceSettingsLocked,
                    onTurn: (detents: number) => swingTurn.current?.turn(
                      detents, sequenceProject.sequenceSettings.swingPercent),
                  },
                },
                directionStep: {
                  backLabel: "Pattern back — ←",
                  forwardLabel: "Pattern forward — →",
                  backAvailable: patternStepOpen && sequencePatternIndex > 0,
                  forwardAvailable: patternStepOpen &&
                    sequencePatternIndex < sequencePatterns.length - 1,
                  onBack: () => stepPatternBy(-1),
                  onForward: () => stepPatternBy(1),
                },
              } : {})}
              history={{
                shifted: railShift,
                onToggleShift: () => setRailShift((value) => !value),
                undoAvailable: history.undoAvailable,
                redoAvailable: history.redoAvailable,
                onUndo: () => {
                  setRailShift(false);
                  history.undo();
                },
                onRedo: () => {
                  setRailShift(false);
                  history.redo();
                },
                undoTitle: history.undoTitle,
                redoTitle: history.redoTitle,
              }}
            />
          }
          overview={
            <OverviewDisplay
              state={state}
              activeMode={activeMode}
              sequence={sequence}
              snap={sequenceGridSnap}
              viewport={sequenceGridViewport}
              selection={sequenceGridSelection}
              rowOffset={overviewRowOffset}
              tempoPreview={tempoPreview}
              swingPreview={swingPreview}
              transport={transport}
              midi={midi}
              {...(buildIdentity ? {buildIdentity} : {})}
            />
          }
          pads={padSurface}
          touchWorkspace={
            <>
      {/* The touch area belongs to the page; Pad recording appears only while
          a take is in progress, awaits review or reports a message. Its
          source is chosen in System. */}
      {padCaptureState !== null &&
        (padCaptureState.phase !== "idle" || padCaptureState.message !== null) && (
        <section aria-label="Pad recording">
          <output role="status">{padCaptureState.phase}{padCaptureState.target === null ? "" :
            ` · Pad ${slotAddress(padCaptureState.target.slot)}`} · {(padCaptureState.frames / 48_000).toFixed(2)} s</output>
          {padCaptureState.message !== null && <p role="status">{padCaptureState.message}</p>}
          {padCaptureState.phase === "review" && <>
            <button type="button" onClick={() => {void padCapture.current?.save();}}>Save Pad recording</button>
            <button type="button" onClick={() => padCapture.current?.discard()}>Discard Pad recording</button>
          </>}
        </section>
      )}
      {defaultSeedError !== null && <p role="status">{defaultSeedError}</p>}
      {defaultSeed?.projectId === currentProjectId && defaultSeed.slots.some(slot => slot.phase === "failed") &&
        <button type="button" onClick={() => {defaultSeed.slots.forEach((slot, index) => {
          if (slot.phase === "failed") void defaultSeedController.current?.retry(index);
        });}}>Retry default sounds</button>}
      {defaultSeed?.projectId === currentProjectId && defaultSeed.slots.some(slot => slot.phase === "saved-unavailable") &&
        <div><p role="status">Sounds saved; prepare playback to use them.</p>
          <button type="button" onClick={() => {
            const project = stateRef.current.project.current;
            if (project === null || !isSampleSession(session)) return;
            void retryPrepareJourney(session, project.patternId).then(
              publication => defaultSeedController.current?.acceptPublication(publication),
              error => reportFailure("Prepare default sounds", error));
          }}>Prepare default sounds</button></div>}

              {["project", "sample", "soundset", "slice"].includes(activeMode) &&
              <nav className="touch-navigation" aria-label="Workspace navigation">
                {activeMode === "project" && <button type="button" disabled={!soundSetEnabled}
                  onClick={() => selectMode("soundset")}>Sound Sets</button>}
                {activeMode === "sample" && <button type="button" disabled={!sliceEnabled}
                  onClick={() => selectMode("slice")}>Slice</button>}
                {(activeMode === "soundset" || activeMode === "slice") &&
                  <button type="button" onClick={() => selectMode(activeMode === "slice" ? "sample" : "project")}>
                    Back to {activeMode === "slice" ? "Sample" : "Project"}
                  </button>}
              </nav>}
              {systemOpen && <SystemSurface onBack={() => {
                setSystemOpen(false);
                // The entry stays mounted. Restore focus in this gesture so
                // a later frame cannot blur the user's next parameter edit.
                systemEntry.current?.focus();
              }}>
              <section className="touch-system" aria-label="Audio and MIDI settings">
                <button
                  type="button"
                  disabled={state.audio.phase !== "running" ||
                    runtimeActions.onSuspendAudio === undefined}
                  onClick={runtimeActions.onSuspendAudio}
                >
                  Suspend audio
                </button>
                <button
                  type="button"
                  disabled={state.runtime.phase !== "ready" ||
                    runtimeActions.onEnableMidi === undefined ||
                    midi?.permission === "granted" ||
                    midi?.permission === "requesting"}
                  onClick={runtimeActions.onEnableMidi}
                >
                  Enable MIDI
                </button>
                <button
                  type="button"
                  disabled={state.runtime.phase !== "ready" ||
                    runtimeActions.onExportReport === undefined}
                  onClick={runtimeActions.onExportReport}
                >
                  Export report
                </button>
              </section>
              {padCaptureState !== null && (
                <section className="touch-system" aria-label="Pad recording settings">
                  <label>Pad recording source
                    <select aria-label="Pad recording source" value={padCaptureState.source}
                      disabled={padCaptureState.phase !== "idle"}
                      onChange={event => {
                        const source = event.currentTarget.value as PadCaptureSource;
                        padCapture.current?.setSource(source);
                        try {localStorage.setItem("lmdj.creator.pad-capture-source.v1", source);} catch {}
                      }}>
                      <option value="microphone">Microphone</option>
                      <option value="master">Internal playback</option>
                    </select>
                  </label>
                </section>
              )}
                {isCandidateSession(session) && <ProviderSettings session={session} />}
                <DiagnosticsLog records={diagnostics} />
              </SystemSurface>}
              <div hidden={systemOpen}>
              {candidateAudio !== null && candidateAudio.projectId === state.project.current?.projectId &&
                (candidateAudio.preparing || state.sample.savedRevision !== state.sample.runtimeRevision) ? (
                <section className="sample-runtime-stale" aria-label="Project audio status">
                  <p role="status">{candidateAudio.preparing
                    ? `Preparing audio at revision ${candidateAudio.revision}…`
                    : `Saved at revision ${candidateAudio.revision}; audio is not ready.`}</p>
                  <button type="button" disabled={candidateAudio.preparing || projectActions.busy || runtimePhase !== "ready"}
                    onClick={() => { void refreshCandidateProject(candidateAudio.projectId).catch(() => {}); }}>
                    Retry audio preparation
                  </button>
                </section>
              ) : null}
              {activeMode === "project" ? (
                <ProjectTouchWorkspace
                  state={state}
                  canOpen={canOpenProject}
                  canImport={canImportProject}
                  canCreate={canCreateProject}
                  canDuplicate={canDuplicateProject}
                  duplicateRefusal={duplicateRefusal}
                  showLocalProjects={showLocalProjects}
                  onShowLocal={() => setShowLocalProjects(true)}
                  onHideLocal={() => setShowLocalProjects(false)}
                  onOpen={(summary) => { void openProject(summary); }}
                  onImport={(file) => { void importProject(file); }}
                  onCreate={() => { void createProject(); }}
                  onDuplicate={() => { void duplicateProject(); }}
                />
              ) : activeMode === "sample" ? (
                <>
                  {state.sample.lastError?.code === "UNSUPPORTED_AUDIO" ? (
                    <p className="sample-error" role="status">
                      Accepted format: PCM16 WAV, mono or stereo, 44.1 or 48 kHz
                    </p>
                  ) : null}
                  {staleSampleRuntime ? (
                    <section className="sample-runtime-stale" aria-label="Sample Runtime status">
                      <p role="status">
                        Saved at revision {state.sample.savedRevision}; Runtime is still revision{
                          " "}{state.sample.runtimeRevision === null
                          ? "unavailable"
                          : state.sample.runtimeRevision}
                      </p>
                      <button
                        type="button"
                        disabled={sampleRetryAction.current !== null ||
                          state.sample.pendingAction !== null}
                        onClick={() => { void retryPrepare(); }}
                      >
                        Retry Prepare
                      </button>
                    </section>
                  ) : null}
                </>
              ) : activeMode === "sequence" && state.project.current !== null ? (
              <SequenceTouchWorkspace
                project={state.project.current}
                state={sequence}
                transport={transport}
                bank={state.activeBank}
                snap={sequenceGridSnap}
                editMode={sequenceGridMode}
                selection={sequenceGridSelection}
                defaultVelocity={sequenceGridVelocity}
                projectionRefreshing={state.projectProjectionRefresh !== null}
                onSnapChange={setSequenceGridSnap}
                onEditModeChange={setSequenceGridMode}
                onViewportChange={setSequenceGridViewport}
                onEdit={(edit) => { void editSequenceGridEvents(edit); }}
                onSelectionChange={setSequenceGridSelection}
                onVelocityChange={setSequenceGridVelocity}
                metronomeOn={metronomeOn}
                onToggleMetronome={onToggleMetronome}
                onRefresh={() => {
                  void refreshSequence();
                  void reconcileTransport();
                }}
                onSwitch={(patternId) => { void selectSequencePattern(patternId); }}
                  onCreatePattern={(bars) => { void createPattern(bars); }}
                  {...(isPatternLengthSession(session) ? {
                    onResizePattern: (bars: 1 | 2 | 4 | 8) => { void resizePattern(bars); },
                    onDoubleUpPattern: () => { void doubleUpPattern(); },
                    onCopyPattern: () => { void copyPattern(); },
                  } : {})}
                  onSettingsChange={(changes) => { void updateSequenceSettings(changes); }}
                  onRecover={(candidate, destinationPatternId) => {
                    if (!isSequenceSession(session)) return;
                    void session.applySequenceRecovery({
                      sessionId: candidate.sessionId,
                      destinationPatternId,
                    }).then((status) => {
                      if (status.committedRevision !== null) {
                        dispatch({type: "project-revision-updated", revision: status.committedRevision});
                      }
                      return refreshSequence();
                    }, (error) => sequenceFailure("Recover Sequence Pattern", error));
                  }}
                  onDiscard={(candidate) => {
                    if (!isSequenceSession(session)) return;
                    void session.discardSequenceRecovery(candidate.sessionId)
                      .then(() => refreshSequence(), (error) => sequenceFailure("Discard Sequence recovery", error));
                  }}
                />
              ) : activeMode === "perform" && state.project.current !== null ? (
                performController !== null ? (
                  <PerformSurface
                    controller={performController}
                    project={state.project.current}
                    bank={state.activeBank}
                    onBankChange={selectBank}
                    transport={transport}
                    recordingBusy={(padCaptureState !== null && padCaptureState.phase !== "idle") ||
                      !["idle", "permission-error"].includes(capturePhase) || recording}
                  />
                ) : (
                  <main className="perform-surface" aria-label="Perform">
                    <h1>Perform</h1>
                    <p>Launch and FX wait for running audio and capture storage.</p>
                  </main>
                )
              ) : activeMode === "slice" && isCandidateSession(session) &&
                state.project.current !== null ? (
                <CandidateSurface key={state.project.current.projectId}
                  session={session} projectId={state.project.current.projectId}
                  projectRevision={state.project.current.revision}
                  onRefreshProject={(revision) => refreshCandidateProject(
                    state.project.current!.projectId, revision,
                  )} />
              ) : activeMode === "soundset" && isSoundSetSession(session) ? (
                <SoundSetSurface
                  session={session}
                  projectRevision={state.project.current?.revision ?? null}
                  activeBank={state.activeBank}
                  onInstalled={(revision) => {
                    dispatch({type: "project-revision-updated", revision});
                    void refreshPerformProject().catch(() => {});
                  }}
                />
              ) : (
                <p className="touch-fallback-note">
                  Open a Project with candidate or Sound Set support.
                </p>
              )}
              {/* One Sample surface, on the same terms the retired workspace
                  shell used: shown in Sample mode, carried hidden while an
                  armed capture, an open trim overlay or a Sequence-side
                  projection refresh must survive a mode switch, and unmounted
                  otherwise so a return to Sample resumes on a fresh mount. */}
              {(activeMode === "sample" ||
                armedCaptureSlot !== null ||
                trimOverlayOpen ||
                (activeMode === "sequence" && state.sampleProjectionRefresh !== null)) ? (
              <div className={trimOverlayOpen ? "sample-overlay-host" : ""}
                hidden={activeMode !== "sample" && !trimOverlayOpen}>
                <SampleSurface
                  state={state}
                  externalCaptureBusy={(padCaptureState !== null && padCaptureState.phase !== "idle") ||
                    recording || !["idle", "saved", "discarded"].includes(historyPerformPhase)}
                  dispatch={dispatch}
                  filePickIntent={sampleFilePickIntent}
                  padDropIntent={samplePadDropIntent}
                  captureStopRequest={captureStopRequest}
                  captureBackgrounded={activeMode !== "sample" && !trimOverlayOpen}
                  closeCaptureAfterResolution={activeMode !== "sample"}
                  {...(sequence.sessionId !== null && sequence.phase === "trim-overlay" &&
                    sequence.status !== null
                    ? {sequenceCapture: {
                        sessionId: sequence.sessionId,
                        expectedRevision: sequence.status.expectedRevision,
                      }}
                    : {})}
                  onCaptureSlotChange={setArmedCaptureSlot}
                  onCapturePhaseChange={capturePhaseChanged}
                  onCaptureGesture={(event) => { void activateAudio(event); }}
                  onContinueCaptureInSequence={() => {
                    if (isSequenceSession(session) && state.project.current !== null) {
                      setActiveMode("sequence");
                    }
                  }}
                  {...(isSampleSession(session) ? {session} : {})}
                />
              </div>
              ) : null}
              </div>
              {recoveryOffer !== null &&
                recoveryOffer.projectId === state.project.current?.projectId && (
                <RecoveryPrompt
                  key={recoveryOffer.id}
                  counts={{
                    sequence: recoveryOffer.sequence.length,
                    performance: recoveryOffer.performance.length,
                  }}
                  onKeep={keepInterruptedRecordings}
                  onDiscard={discardInterruptedRecordings}
                  onOpen={(mode) => {
                    selectMode(mode);
                    setRecoveryOffer(null);
                  }}
                  onClose={() => setRecoveryOffer(null)}
                />
              )}
              <ErrorPanel
                code={state.runtime.errorCode}
                details={state.runtime.errorDetails}
                {...(session && state.runtime.errorCode === "DUPLICATE_ID"
                  ? {onOpenLocalProject: () => {
                      setShowLocalProjects(true);
                      setListAttempt((attempt) => attempt + 1);
                    }}
                  : {})}
                {...(session && state.runtime.errorCode === "PROJECT_BUSY" && busyRetry &&
                  takeoverRequest === null
                  ? {onRetryProject: () => {
                      if (busyRetry.kind === "list") {
                        setListAttempt((attempt) => attempt + 1);
                      } else {
                        void openProject(busyRetry.project);
                      }
                    }}
                  : {})}
                {...(session && state.runtime.errorCode === "PROJECT_BUSY" &&
                  busyRetry?.kind === "open" && projectTakeover !== null &&
                  takeoverRequest === null
                  ? {onContinueHere: () => {
                      const project = busyRetry.project;
                      void continueHere(project.projectId, () => openProject(project));
                    }}
                  : {})}
                {...(state.runtime.errorCode === "PROJECT_BUSY" && takeoverOutcome !== null
                  ? {note: takeoverNote(takeoverOutcome)}
                  : {})}
                {...(state.runtime.errorCode === "HOST_RESTART_REQUIRED" ||
                  state.runtime.errorCode === "HOST_TIMEOUT") && onRetryRuntime
                  ? {onRetryRuntime}
                  : {}}
                {...(state.runtime.phase === "ready"
                  ? {onDismiss: () => dispatch({type: "runtime-error-dismissed"})}
                  : {})}
              />
              {yieldedProject !== null && runtimePhase === "closed" && (
                <TakenOverPanel
                  note={takeoverOutcome === null ? null : takeoverNote(takeoverOutcome)}
                  {...(takeoverRequest === null && onRetryRuntime
                    ? {onContinueHere: () => {
                        void continueHere(yieldedProject, () => {
                          setYieldedProject(null);
                          // The fresh Runtime's boot reopens the retained Project.
                          onRetryRuntime();
                        });
                      }}
                    : {})}
                />
              )}
              {takeoverRequest !== null && (
                <TakeoverPending onCancel={() => takeoverRequest.abort()} />
              )}
            </>
          }
        />
        </div>
    </div>
    </DiagnosticsProvider>
  );
}

function ManagedWorkspace({
  initialState,
  buildIdentity,
  projectTakeover,
}: {
  initialState: CreatorState;
  buildIdentity?: CreatorBuildIdentity;
  projectTakeover: ProjectTakeoverCoordinator | null;
}) {
  const runtime = useRuntime();
  return (
    <Workspace
      initialState={initialState}
      {...(buildIdentity ? {buildIdentity} : {})}
      session={runtime.session}
      runtimePhase={runtime.phase}
      runtimeErrorCode={runtime.errorCode}
      runtimeErrorDetails={runtime.issue?.details}
      runtimeHostState={runtime.hostState}
      runtimeRecoveryProbeReady={runtime.recoveryProbeReady}
      onRetryRuntime={runtime.retryRuntime}
      onYieldRuntime={runtime.yieldRuntime}
      projectTakeover={projectTakeover}
      registerRuntimeShutdownBarrier={runtime.registerShutdownBarrier}
    />
  );
}

export function App({
  initialState = initialCreatorState,
  runtimeFactory,
  buildIdentity,
  projectTakeover = null,
}: AppProps) {
  const identity = buildIdentity ? {buildIdentity} : {};
  if (runtimeFactory) {
    return (
      <RuntimeProvider factory={runtimeFactory}>
        <ManagedWorkspace
          initialState={initialState}
          projectTakeover={projectTakeover}
          {...identity}
        />
      </RuntimeProvider>
    );
  }
  return <Workspace initialState={initialState} {...identity} />;
}
