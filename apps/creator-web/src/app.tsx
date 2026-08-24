import {useEffect, useReducer, useRef, useState} from "react";

import {BankSelector} from "./components/bank_selector";
import {ErrorPanel} from "./components/error_panel";
import {ModeRail, type CreatorMode} from "./components/mode_rail";
import {PadSurface} from "./components/pad_surface";
import {ProjectSurface} from "./components/project_surface";
import {SampleSurface} from "./components/sample_surface";
import {StatusBar} from "./components/status_bar";
import {
  createAcceptanceReport,
  serializeAcceptanceReport,
} from "./report/acceptance_report";
import {
  createProjectActionLane,
  importProjectJourney,
  listLocalProjectsJourney,
  openProjectJourney,
  type ProjectActionToken,
} from "./runtime/project_actions";
import {createCreatorInputController} from "./runtime/input_controller";
import {retryPrepareJourney} from "./runtime/sample_actions";
import {
  activateCreatorAudio,
  RuntimeProvider,
  useRuntime,
  type RuntimeProviderPhase,
} from "./runtime/runtime_context";
import type {
  CreatorRuntimeSession,
  CreatorSampleRuntimeSession,
  LocalProjectSummary,
  RuntimeSessionFactory,
  TypedRuntimeError,
} from "./runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  selectCanImportProject,
  selectCanOpenProject,
  selectCreatorPhase,
  type CreatorState,
} from "./state/creator_state";

interface AppProps {
  initialState?: CreatorState;
  runtimeFactory?: RuntimeSessionFactory;
}

interface WorkspaceProps {
  initialState: CreatorState;
  session?: CreatorRuntimeSession;
  runtimePhase?: RuntimeProviderPhase;
  runtimeErrorCode?: string | null;
  runtimeErrorDetails?: Readonly<Record<string, unknown>> | undefined;
  runtimeHostState?: string;
  runtimeRecoveryProbeReady?: boolean;
  onRetryRuntime?: () => void;
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

function isSampleSession(
  session: CreatorRuntimeSession | undefined,
): session is CreatorSampleRuntimeSession {
  const candidate = session as Partial<CreatorSampleRuntimeSession> | undefined;
  return candidate !== undefined &&
    typeof candidate.inspectSample === "function" &&
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

function Workspace({
  initialState,
  session,
  runtimePhase,
  runtimeErrorCode,
  runtimeErrorDetails,
  runtimeHostState,
  runtimeRecoveryProbeReady,
  onRetryRuntime,
}: WorkspaceProps) {
  const [state, dispatch] = useReducer(creatorReducer, initialState);
  const [listAttempt, setListAttempt] = useState(0);
  const [busyRetry, setBusyRetry] = useState<BusyRetry | null>(null);
  const [showLocalProjects, setShowLocalProjects] = useState(false);
  const [activeMode, setActiveMode] = useState<CreatorMode>("project");
  const [inputControllerEpoch, setInputControllerEpoch] = useState(0);
  const [inputControllerRevision, setInputControllerRevision] = useState(0);
  const importController = useRef<AbortController | null>(null);
  const projectActions = useRef(createProjectActionLane()).current;
  const sampleRetryAction = useRef<SampleRetryToken | null>(null);
  const inputController = useRef<ReturnType<typeof createCreatorInputController> | null>(null);
  const inputAdverseState = useRef<string | null>(null);
  const sampleFilePickIntent = useRef<(slot: number) => void>(() => {});
  const stateRef = useRef(state);
  stateRef.current = state;

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
    };
    const controller = isSampleSession(session)
      ? createCreatorInputController({
          ...common,
          session,
          isAvailable: () =>
            stateRef.current.project.phase === "ready" &&
            stateRef.current.transfer.phase === "idle" &&
            stateRef.current.sample.pendingAction === null,
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

  return (
    <div className="workspace">
      <StatusBar
        state={state}
        {...(session && inputController.current
          ? {
              audioActivationReady: runtimeHostState === "audio-suspended",
              onActivateAudio: (event) => { void activateAudio(event.nativeEvent); },
              onSuspendAudio: () => { void suspendAudio(); },
              onEnableMidi: () => { void inputController.current?.enableMidi(); },
              onExportReport: exportReport,
            }
          : {})}
      />
      <ModeRail
        activeMode={activeMode}
        onSelect={(mode) => {
          inputController.current?.clearPressed();
          setActiveMode(mode);
        }}
      />
      {activeMode === "project" ? (
        <>
          <ProjectSurface
            state={state}
            canOpen={canOpenProject}
            canImport={canImportProject}
            showLocalProjects={showLocalProjects}
            onShowLocal={() => setShowLocalProjects(true)}
            onOpen={(summary) => { void openProject(summary); }}
            onImport={(file) => { void importProject(file); }}
          />
          <section className="pads" aria-label="Instrument">
            <BankSelector
              activeBank={state.activeBank}
              onSelect={(bank) => {
                inputController.current?.clearPressed();
                dispatch({type: "bank-selected", bank});
              }}
            />
            <PadSurface
              state={state}
              {...(inputController.current ? {controller: inputController.current} : {})}
            />
          </section>
        </>
      ) : (
        <>
          <SampleSurface
            state={state}
            dispatch={dispatch}
            filePickIntent={sampleFilePickIntent}
            {...(isSampleSession(session) ? {session} : {})}
            {...(inputController.current ? {controller: inputController.current} : {})}
          />
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
      />
    </div>
  );
}

function ManagedWorkspace({initialState}: {initialState: CreatorState}) {
  const runtime = useRuntime();
  return (
    <Workspace
      initialState={initialState}
      session={runtime.session}
      runtimePhase={runtime.phase}
      runtimeErrorCode={runtime.errorCode}
      runtimeErrorDetails={runtime.issue?.details}
      runtimeHostState={runtime.hostState}
      runtimeRecoveryProbeReady={runtime.recoveryProbeReady}
      onRetryRuntime={runtime.retryRuntime}
    />
  );
}

export function App({
  initialState = initialCreatorState,
  runtimeFactory,
}: AppProps) {
  if (runtimeFactory) {
    return (
      <RuntimeProvider factory={runtimeFactory}>
        <ManagedWorkspace initialState={initialState} />
      </RuntimeProvider>
    );
  }
  return <Workspace initialState={initialState} />;
}
