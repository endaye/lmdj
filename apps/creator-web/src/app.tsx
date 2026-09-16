import {CandidateSurface, isCandidateSession} from "./components/candidate_surface";
import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";

import {BankSelector} from "./components/bank_selector";
import {ErrorPanel} from "./components/error_panel";
import {
  HardwareConsole,
  readCreatorLayout,
  writeCreatorLayout,
  type CreatorLayout,
} from "./components/hardware_console";
import {ModeRail, type CreatorMode} from "./components/mode_rail";
import {OverviewDisplay} from "./components/overview_display";
import {PadSurface} from "./components/pad_surface";
import {PhysicalControls} from "./components/physical_controls";
import {PerformSurface} from "./components/perform_surface";
import {ProjectSurface} from "./components/project_surface";
import {ProjectTouchWorkspace} from "./components/project_touch_workspace";
import {SampleSurface} from "./components/sample_surface";
import {SequenceSurface} from "./components/sequence_surface";
import {SequenceTouchWorkspace} from "./components/sequence_touch_workspace";
import {
  isSoundSetSession,
  SoundSetSurface,
} from "./components/soundset_surface";
import {StatusBar, type MidiStatus} from "./components/status_bar";
import {
  createAcceptanceReport,
  serializeAcceptanceReport,
} from "./report/acceptance_report";
import {
  createProjectActionLane,
  importProjectJourney,
  listLocalProjectsJourney,
  openProjectJourney,
  refreshProjectProjectionJourney,
  type ProjectActionToken,
} from "./runtime/project_actions";
import type {CreatorBuildIdentity} from "./runtime/build_identity";
import {
  createCreatorInputController,
  type PerformancePadInputEvent,
} from "./runtime/input_controller";
import {reloadPrepareJourney, retryPrepareJourney} from "./runtime/sample_actions";
import {
  disarmSequenceCaptureJourney,
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
  CreatorRuntimeSession,
  CreatorPerformanceRuntimeSession,
  CreatorSampleRuntimeSession,
  LocalProjectSummary,
  RuntimeSessionFactory,
  TypedRuntimeError,
} from "./runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  selectCanActivateAudio,
  selectCanImportProject,
  selectCanOpenProject,
  selectCreatorPhase,
  type CreatorState,
} from "./state/creator_state";
import {initialSequenceState, reduceSequence} from "./state/sequence_state";
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
} from "./state/perform_state";
import type {CapturePhase} from "./state/capture_state";

interface AppProps {
  initialState?: CreatorState;
  runtimeFactory?: RuntimeSessionFactory;
  buildIdentity?: CreatorBuildIdentity;
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
  registerRuntimeShutdownBarrier?: (
    barrier: () => Promise<unknown>,
  ) => () => void;
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

const SAMPLE_ERROR_CODES = new Set([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "REVISION_CONFLICT",
  "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO",
  "MISSING_ASSET",
  "INVALID_PROJECT",
  "COOK_FAILED",
  "BANK_QUOTA_EXHAUSTED",
  "PROJECT_QUOTA_EXHAUSTED",
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
function errorCode(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "ABORTED";
  }
  return (error as TypedRuntimeError | null)?.code ?? "INTERNAL_ERROR";
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
    typeof candidate.setSamplePreview === "function" &&
    typeof candidate.clearSamplePreview === "function" &&
    typeof candidate.release === "function" &&
    typeof candidate.stopPad === "function" &&
    typeof candidate.stopAll === "function" &&
    typeof candidate.retryPrepare === "function" &&
    typeof candidate.subscribeVoiceState === "function";
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
  registerRuntimeShutdownBarrier,
}: WorkspaceProps) {
  const [state, dispatch] = useReducer(creatorReducer, initialState);
  const [sequence, dispatchSequence] = useReducer(reduceSequence, initialSequenceState);
  const [transport, dispatchTransport] = useReducer(
    reducePatternTransport,
    initialPatternTransportState,
  );
  const [listAttempt, setListAttempt] = useState(0);
  const [busyRetry, setBusyRetry] = useState<BusyRetry | null>(null);
  const [showLocalProjects, setShowLocalProjects] = useState(false);
  const [activeMode, setActiveMode] = useState<CreatorMode>("project");
  const [layout, setLayout] = useState<CreatorLayout>(readCreatorLayout);
  const [inputControllerEpoch, setInputControllerEpoch] = useState(0);
  const [inputControllerRevision, setInputControllerRevision] = useState(0);
  const [armedCaptureSlot, setArmedCaptureSlot] = useState<number | null>(null);
  const [captureStopRequest, setCaptureStopRequest] = useState(0);
  const [midi, setMidi] = useState<MidiStatus | null>(null);
  const [performController, setPerformController] =
    useState<PerformController | null>(null);
  const [performCaptureConfigured, setPerformCaptureConfigured] = useState(false);
  const [captureTransportOverlay, setCaptureTransportOverlay] = useState(false);
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
  const sampleRetryAction = useRef<SampleRetryToken | null>(null);
  const inputController = useRef<ReturnType<typeof createCreatorInputController> | null>(null);
  const inputAdverseState = useRef<string | null>(null);
  const activeModeRef = useRef(activeMode);
  const hardwareSessionRef = useRef(layout === "hardware");
  const performControllerRef = useRef<PerformController | null>(null);
  const projectProjectionRefreshRef = useRef<Readonly<{
    id: string;
    projectId: string;
    patternId: string;
    baseRevision: number;
  }> | null>(null);
  const sampleFilePickIntent = useRef<(slot: number) => void>(() => {});
  const armedCaptureStopIntent = useRef<() => void>(() => {});
  const stateRef = useRef(state);
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
  } else {
    sequenceAuthoringRevision.current = reconcileSequenceAuthoringRevision(
      sequenceAuthoringRevision.current,
      state.project.current?.revision ?? 0,
      sequence.status?.expectedRevision ?? 0,
    );
  }

  useEffect(() => {
    const project = state.project.current;
    if (project === null || sequence.selectedPatternId !== null) return;
    dispatchSequence({type: "selected", patternId: project.patternId});
  }, [state.project.current, sequence.selectedPatternId]);

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
      () => {},
    );
    void refreshSequence();
  }, [session, runtimePhase, state.project.current]);

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
            (stateRef.current.audio.phase === "running" ||
              stateRef.current.audio.phase === "recovering"),
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
    void listLocalProjectsJourney(session).then(
      async (projects) => {
        if (!active) return;
        setBusyRetry(null);
        dispatch({type: "projects-loaded", projects});
        const retained = stateRef.current.project.current;
        if (!retained) return;
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
        const code = errorCode(error);
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
  ) => {
    if (error instanceof DOMException && error.name === "AbortError") return;
    const code = errorCode(error);
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

  const refreshPerformProject = async () => {
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
      baseRevision: current.revision,
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
        errorCode: errorCode(error),
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

  const beginProjectAction = (
    kind: "open" | "import",
    requireSelector = true,
  ): ProjectActionToken | null => {
    if (!session || projectActions.busy ||
      sampleRetryAction.current !== null ||
      stateRef.current.sample.pendingAction !== null) return null;
    if (requireSelector) {
      const allowed = kind === "open"
        ? selectCanOpenProject(stateRef.current)
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
      if (ownsProjectAction(token)) reportProjectError(error);
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

  const activateAudio = async (event: MouseEvent) => {
    if (!session) return;
    const priorPhase = stateRef.current.audio.phase;
    if (priorPhase !== "inactive" && priorPhase !== "suspended") return;
    dispatch({type: "audio-changed", phase: "activating"});
    // A refused activation is a non-destructive no-op: the surface returns
    // to the phase it held before the attempt, unless a Runtime publication
    // already moved it elsewhere.
    const restorePriorPhase = () => {
      dispatch({type: "audio-activation-restored", phase: priorPhase});
    };
    try {
      const activated = await activateCreatorAudio(session, event);
      if (!activated) {
        const diagnostics = session.diagnostics();
        if (diagnostics.error_code) {
          reportProjectError(Object.assign(new Error(diagnostics.error_code), {
            code: diagnostics.error_code,
            details: diagnostics.error_details,
          }));
          restorePriorPhase();
        } else {
          restorePriorPhase();
        }
      } else if (session.diagnostics().state === "running") {
        dispatch({type: "audio-changed", phase: "running"});
      }
    } catch (error) {
      // An untrusted gesture never reached the Runtime. Other failures remain
      // visible through normal error reporting, but none may destroy the
      // pre-attempt audio phase.
      if (!(error instanceof TypeError)) reportProjectError(error);
      restorePriorPhase();
    }
  };

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
        const candidate = errorCode(error);
        const code = SAMPLE_ERROR_CODES.has(candidate) ? candidate : "INTERNAL_ERROR";
        dispatch({
          type: "sample-action",
          action: {
            type: "operation-failed",
            pending,
            error: {code, message: "Sample operation failed"},
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

  const sequenceFailure = (error: unknown) => {
    dispatchSequence({type: "failed", errorCode: errorCode(error)});
  };

  const refreshSequence = async () => {
    const project = stateRef.current.project.current;
    if (!isSequenceSession(session) || project === null) return;
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
          // A transport commit advanced Project Truth; the revision display
          // follows the commit.
          dispatch({
            type: "project-revision-updated",
            revision: committedRevision,
          });
        }
      }
      dispatchSequence({type: "recovery", candidates: authority.recovery});
    } catch (error) {
      sequenceFailure(error);
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
          errorCode: errorCode(error),
        });
      }
    } catch (error) {
      dispatchTransport({type: "observe-failed", errorCode: errorCode(error)});
      return;
    }
  };

  const submitTransportIntent = async (intent: PatternTransportIntent) => {
    const project = stateRef.current.project.current;
    const current = transportRef.current;
    if (!isPatternTransportSession(session) || project === null ||
        current.sessionId === null || current.projectId !== project.projectId ||
        stateRef.current.audio.phase !== "running" ||
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
      dispatchTransport({type: "failed", command, errorCode: errorCode(error)});
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

  const stopArmedCapture = async () => {
    const current = sequenceRef.current;
    if (current.phase === "flushing") return;
    setCaptureStopRequest((request) => request + 1);
  };
  armedCaptureStopIntent.current = () => { void stopArmedCapture(); };

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
      dispatch({
        type: "project-sequence-settings-updated",
        revision: result.committedRevision,
        bpm: result.bpm,
        quantizeEnabled: result.quantizeEnabled,
        swingPercent: result.swingPercent,
      });
      await refreshSequence();
    }).catch(sequenceFailure);
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
        pattern: {patternId: result.patternId, bars: result.bars},
      });
      if (currentTransport.sessionId !== null &&
          isPatternTransportSession(session)) {
        // Make the new Pattern runtime-current so the next Play starts it.
        await session.reloadSnapshot(result.patternId);
      }
      dispatchSequence({type: "selected", patternId: result.patternId});
    }).catch(sequenceFailure);
    sequenceAuthoringTail.current = operation;
    return operation;
  };

  const capturePhaseChanged = useCallback((phase: CapturePhase) => {
    if (phase === "trimming" || phase === "commit-error" || phase === "committing") {
      dispatchSequence({type: "trim-overlay"});
      // The legacy overlay gate needs a legacy Sequence session. Under the
      // global transport the journal has no legacy session, so an armed
      // Capture trimmed over an active transport recording opens the overlay
      // through this Host-local flag instead.
      const legacySequenceActive =
        ["recording", "switch-pending"].includes(sequenceRef.current.phase) &&
        sequenceRef.current.sessionId !== null;
      if (!legacySequenceActive && selectTransportRecording(transportRef.current)) {
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
          dispatchSequence({type: "failed", errorCode: errorCode(error)});
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
          if (errorCode(error) !== "HOST_STATE_INVALID" || attempt === 4 ||
              patternSelectionRef.current !== selection) {
            if (patternSelectionRef.current === selection) {
              sequenceFailure(error);
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
        sequenceFailure(error);
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
    state.audio.phase === "running";
  const recording = selectTransportRecording(transport);
  const playing = selectTransportPlaying(transport);
  // The armed-Capture trim overlay over an active recording, whether the
  // recording is a legacy Sequence session or the global Pattern transport.
  const trimOverlayOpen = sequence.phase === "trim-overlay" ||
    captureTransportOverlay;
  const applyMode = (mode: CreatorMode) => {
    if (hardwareSessionRef.current) {
      setLayout("hardware");
    }
    setActiveMode(mode);
  };
  const selectMode = (mode: CreatorMode) => {
    inputController.current?.clearPressed();
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
    dispatch({type: "bank-selected", bank});
  };
  const enterHardwareLayout = () => {
    writeCreatorLayout("hardware");
    hardwareSessionRef.current = true;
    setLayout("hardware");
  };
  const enterWorkspaceLayout = () => {
    writeCreatorLayout("workspace");
    hardwareSessionRef.current = false;
    setLayout("workspace");
  };
  const runtimeActions = session && inputController.current
    ? {
        audioActivationReady: runtimeHostState === "audio-suspended",
        onActivateAudio: (event: ReactMouseEvent<HTMLButtonElement>) => {
          void activateAudio(event.nativeEvent);
        },
        onSuspendAudio: () => { void suspendAudio(); },
        onEnableMidi: () => { void inputController.current?.enableMidi(); },
        onExportReport: exportReport,
      }
    : {};
  const padSurface = (
    <PadSurface
      state={state}
      armedCaptureSlot={armedCaptureSlot}
      {...(inputController.current ? {controller: inputController.current} : {})}
    />
  );

  return (
    <div className={layout === "hardware" ? "hardware-workspace" : "workspace"}>
      {layout === "hardware" ? (
        <HardwareConsole
          physicalControls={
            <PhysicalControls
              activeMode={activeMode}
              activeBank={state.activeBank}
              sequenceEnabled={state.project.phase === "ready" &&
                state.project.current !== null}
              performEnabled={state.project.phase === "ready" &&
                state.project.current !== null}
              onSelectMode={selectMode}
              onSelectBank={selectBank}
              onRecord={() => { void submitTransportIntent("record"); }}
              recordEnabled={transportReady && !transportBusy}
              recording={recording}
              onPlayStop={() => { void submitTransportIntent("play_stop"); }}
              playEnabled={transportReady && !transportBusy}
              playing={playing}
            />
          }
          overview={
            <OverviewDisplay
              state={state}
              activeMode={activeMode}
              sequence={sequence}
              transport={transport}
              midi={midi}
              {...(buildIdentity ? {buildIdentity} : {})}
            />
          }
          pads={padSurface}
          touchWorkspace={
            <>
              <section className="touch-system" aria-label="System">
                <button
                  type="button"
                  disabled={!selectCanActivateAudio(state) ||
                    runtimeActions.onActivateAudio === undefined ||
                    runtimeActions.audioActivationReady !== true}
                  onClick={runtimeActions.onActivateAudio}
                >
                  Activate audio
                </button>
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
                <button type="button" onClick={enterWorkspaceLayout}>
                  Existing workspace
                </button>
                <button
                  type="button"
                  disabled={!sliceEnabled}
                  aria-label={sliceEnabled
                    ? "Slice"
                    : "Slice — open a Project with candidate support"}
                  onClick={() => selectMode("slice")}
                >
                  Slice
                </button>
                <button
                  type="button"
                  disabled={!soundSetEnabled}
                  aria-label={soundSetEnabled
                    ? "Sound Sets"
                    : "Sound Sets — wait for the Runtime to start"}
                  onClick={() => selectMode("soundset")}
                >
                  Sound Sets
                </button>
              </section>
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
                  showLocalProjects={showLocalProjects}
                  onShowLocal={() => setShowLocalProjects(true)}
                  onHideLocal={() => setShowLocalProjects(false)}
                  onOpen={(summary) => { void openProject(summary); }}
                  onImport={(file) => { void importProject(file); }}
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
                  <SampleSurface
                    state={state}
                    dispatch={dispatch}
                    filePickIntent={sampleFilePickIntent}
                    captureStopRequest={captureStopRequest}
                    onCaptureSlotChange={setArmedCaptureSlot}
                    onCapturePhaseChange={capturePhaseChanged}
                    onContinueCaptureInSequence={() => {
                      if (isSequenceSession(session) && state.project.current !== null) {
                        setActiveMode("sequence");
                      }
                    }}
                    {...(isSampleSession(session) ? {session} : {})}
                    {...(inputController.current ? {controller: inputController.current} : {})}
                  />
                </>
              ) : activeMode === "sequence" && state.project.current !== null ? (
              <SequenceTouchWorkspace
                project={state.project.current}
                state={sequence}
                transport={transport}
                onRefresh={() => {
                  void refreshSequence();
                  void reconcileTransport();
                }}
                onSwitch={(patternId) => { void selectSequencePattern(patternId); }}
                  onCreatePattern={(bars) => { void createPattern(bars); }}
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
                    }, sequenceFailure);
                  }}
                  onDiscard={(candidate) => {
                    if (!isSequenceSession(session)) return;
                    void session.discardSequenceRecovery(candidate.sessionId)
                      .then(() => refreshSequence(), sequenceFailure);
                  }}
                />
              ) : activeMode === "perform" && state.project.current !== null ? (
                performController !== null ? (
                  <PerformSurface
                    controller={performController}
                    creatorState={state}
                    project={state.project.current}
                    bank={state.activeBank}
                    onBankChange={selectBank}
                    transport={transport}
                    {...(inputController.current ? {padController: inputController.current} : {})}
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
                  onBankChange={selectBank}
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
              <ErrorPanel
                code={state.runtime.errorCode}
                details={state.runtime.errorDetails}
                {...(session && state.runtime.errorCode === "DUPLICATE_ID"
                  ? {onOpenLocalProject: () => {
                      setShowLocalProjects(true);
                      setListAttempt((attempt) => attempt + 1);
                    }}
                  : {})}
                {...(session && state.runtime.errorCode === "PROJECT_BUSY" && busyRetry
                  ? {onRetryProject: () => {
                      if (busyRetry.kind === "list") {
                        setListAttempt((attempt) => attempt + 1);
                      } else {
                        void openProject(busyRetry.project);
                      }
                    }}
                  : {})}
                {...(state.runtime.errorCode === "HOST_RESTART_REQUIRED" ||
                  state.runtime.errorCode === "HOST_TIMEOUT") && onRetryRuntime
                  ? {onRetryRuntime}
                  : {}}
                {...(state.runtime.phase === "ready"
                  ? {onDismiss: () => dispatch({type: "runtime-error-dismissed"})}
                  : {})}
              />
            </>
          }
        />
      ) : (
        <>
          <header className="status-bar-host">
            <StatusBar
              state={state}
              midi={midi}
              {...(buildIdentity ? {buildIdentity} : {})}
              {...runtimeActions}
            />
            <button type="button" className="layout-opt-in" onClick={enterHardwareLayout}>
              Hardware layout
            </button>
          </header>
          <ModeRail
            activeMode={activeMode}
            soundSetEnabled={soundSetEnabled}
            sliceEnabled={sliceEnabled}
            sequenceEnabled={sequenceEnabled}
            performEnabled={performEnabled}
            onSelect={selectMode}
          />
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
            <>
              <ProjectSurface
                state={state}
                canOpen={canOpenProject}
                canImport={canImportProject}
                showLocalProjects={showLocalProjects}
                onShowLocal={() => setShowLocalProjects(true)}
                onHideLocal={() => setShowLocalProjects(false)}
                onOpen={(summary) => { void openProject(summary); }}
                onImport={(file) => { void importProject(file); }}
              />
              <section className="pads" aria-label="Instrument">
                <BankSelector
                  activeBank={state.activeBank}
                  onSelect={selectBank}
                />
                {padSurface}
              </section>
            </>
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
            <>
              <SequenceSurface
                project={state.project.current}
                state={sequence}
                transport={transport}
                ready={isPatternTransportSession(session) &&
                  state.audio.phase === "running"}
                onPlayStop={() => { void submitTransportIntent("play_stop"); }}
                onRecord={() => { void submitTransportIntent("record"); }}
                onRefresh={() => {
                  void refreshSequence();
                  void reconcileTransport();
                }}
                onSwitch={(patternId) => { void selectSequencePattern(patternId); }}
                onCreatePattern={(bars) => { void createPattern(bars); }}
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
                  }, sequenceFailure);
                }}
                onDiscard={(candidate) => {
                  if (!isSequenceSession(session)) return;
                  void session.discardSequenceRecovery(candidate.sessionId)
                    .then(() => refreshSequence(), sequenceFailure);
                }}
              />
              <section className="pads" aria-label="Sequence instrument">
                <BankSelector activeBank={state.activeBank} onSelect={selectBank} />
                {padSurface}
              </section>
            </>
          ) : activeMode === "slice" && isCandidateSession(session) && state.project.current !== null ? (
            <CandidateSurface key={state.project.current.projectId}
              session={session} projectId={state.project.current.projectId}
              projectRevision={state.project.current.revision}
              onRefreshProject={(revision) => refreshCandidateProject(state.project.current!.projectId, revision)} />
          ) : activeMode === "soundset" && isSoundSetSession(session) ? (
            <SoundSetSurface
              session={session}
              projectRevision={state.project.current?.revision ?? null}
              activeBank={state.activeBank}
              onBankChange={selectBank}
              onInstalled={(revision) => {
                dispatch({type: "project-revision-updated", revision});
                void refreshPerformProject().catch(() => {});
              }}
            />
          ) : activeMode === "perform" && state.project.current !== null &&
            performController !== null ? (
            <PerformSurface
              controller={performController}
              creatorState={state}
              project={state.project.current}
              bank={state.activeBank}
              onBankChange={selectBank}
              transport={transport}
              {...(inputController.current ? {padController: inputController.current} : {})}
            />
          ) : null}
          <ErrorPanel
            code={state.runtime.errorCode}
            details={state.runtime.errorDetails}
            {...(session && state.runtime.errorCode === "DUPLICATE_ID"
              ? {onOpenLocalProject: () => {
                  setShowLocalProjects(true);
                  setListAttempt((attempt) => attempt + 1);
                }}
              : {})}
            {...(session && state.runtime.errorCode === "PROJECT_BUSY" && busyRetry
              ? {onRetryProject: () => {
                  if (busyRetry.kind === "list") {
                    setListAttempt((attempt) => attempt + 1);
                  } else {
                    void openProject(busyRetry.project);
                  }
                }}
              : {})}
            {...(state.runtime.errorCode === "HOST_RESTART_REQUIRED" ||
              state.runtime.errorCode === "HOST_TIMEOUT") && onRetryRuntime
              ? {onRetryRuntime}
              : {}}
            {...(state.runtime.phase === "ready"
              ? {onDismiss: () => dispatch({type: "runtime-error-dismissed"})}
              : {})}
          />
        </>
      )}
      {(layout === "workspace" && activeMode === "sample") ||
      ((armedCaptureSlot !== null ||
        trimOverlayOpen ||
        (activeMode === "sequence" && state.sampleProjectionRefresh !== null)) &&
        !(layout === "hardware" && activeMode === "sample")) ? (
        <div className={trimOverlayOpen ? "sample-overlay-host" : ""}
          hidden={activeMode !== "sample" && !trimOverlayOpen}>
          <SampleSurface
            state={state}
            dispatch={dispatch}
            filePickIntent={sampleFilePickIntent}
            captureStopRequest={captureStopRequest}
            captureBackgrounded={activeMode !== "sample" &&
              !trimOverlayOpen}
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
            onContinueCaptureInSequence={() => {
              if (isSequenceSession(session) && state.project.current !== null) {
                setActiveMode("sequence");
              }
            }}
            {...(isSampleSession(session) ? {session} : {})}
            {...(inputController.current ? {controller: inputController.current} : {})}
          />
        </div>
      ) : null}
    </div>
  );
}

function ManagedWorkspace({
  initialState,
  buildIdentity,
}: {initialState: CreatorState; buildIdentity?: CreatorBuildIdentity}) {
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
      registerRuntimeShutdownBarrier={runtime.registerShutdownBarrier}
    />
  );
}

export function App({
  initialState = initialCreatorState,
  runtimeFactory,
  buildIdentity,
}: AppProps) {
  const identity = buildIdentity ? {buildIdentity} : {};
  if (runtimeFactory) {
    return (
      <RuntimeProvider factory={runtimeFactory}>
        <ManagedWorkspace initialState={initialState} {...identity} />
      </RuntimeProvider>
    );
  }
  return <Workspace initialState={initialState} {...identity} />;
}
