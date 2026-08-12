import {useEffect, useReducer, useRef, useState} from "react";

import {BankSelector} from "./components/bank_selector";
import {ErrorPanel} from "./components/error_panel";
import {ModeRail} from "./components/mode_rail";
import {PadSurface} from "./components/pad_surface";
import {ProjectSurface} from "./components/project_surface";
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
import {
  activateCreatorAudio,
  RuntimeProvider,
  useRuntime,
  type RuntimeProviderPhase,
} from "./runtime/runtime_context";
import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
  RuntimeSessionFactory,
  TypedRuntimeError,
} from "./runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  selectCanImportProject,
  selectCanOpenProject,
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
  const importController = useRef<AbortController | null>(null);
  const projectActions = useRef(createProjectActionLane()).current;
  const inputController = useRef<ReturnType<typeof createCreatorInputController> | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => () => {
    projectActions.invalidate();
    importController.current?.abort();
    importController.current = null;
  }, [session]);

  useEffect(() => {
    if (!session || runtimePhase !== "ready") return;
    const controller = createCreatorInputController({
      session,
      getActiveBank: () => stateRef.current.activeBank,
      isAssigned: (slot) =>
        stateRef.current.project.current?.pads[slot]?.assetId !== null &&
        stateRef.current.project.current?.pads[slot]?.assetId !== undefined &&
        (stateRef.current.audio.phase === "running" ||
          stateRef.current.audio.phase === "recovering"),
      dispatch,
    });
    inputController.current = controller;
    return () => {
      if (inputController.current === controller) inputController.current = null;
      controller.dispose();
    };
  }, [session, runtimePhase]);

  useEffect(() => {
    if (!runtimeHostState) return;
    if (runtimeHostState === "running") {
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
      dispatch({type: "audio-changed", phase: "suspended"});
    }
  }, [runtimeHostState, runtimeRecoveryProbeReady]);

  useEffect(() => {
    if (!session || !runtimePhase) return;
    setBusyRetry(null);
    dispatch({
      type: "runtime-changed",
      phase: runtimePhase,
      errorCode: runtimeErrorCode ?? null,
      errorDetails: runtimeErrorDetails ?? {},
    });
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
    runtimeErrorCode,
    runtimeErrorDetails,
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
    if (!session || projectActions.busy) return null;
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
    dispatch({type: "audio-changed", phase: "activating"});
    try {
      const activated = await activateCreatorAudio(session, event);
      if (!activated) {
        const diagnostics = session.diagnostics();
        if (diagnostics.error_code) {
          reportProjectError(Object.assign(new Error(diagnostics.error_code), {
            code: diagnostics.error_code,
            details: diagnostics.error_details,
          }));
        } else {
          dispatch({type: "audio-changed", phase: "inactive"});
        }
      } else if (session.diagnostics().state === "running") {
        dispatch({type: "audio-changed", phase: "running"});
      }
    } catch (error) {
      if (!(error instanceof TypeError)) reportProjectError(error);
      dispatch({type: "audio-changed", phase: "inactive"});
    }
  };

  const suspendAudio = async () => {
    if (!session) return;
    if (await session.suspendAudio()) {
      inputController.current?.clearPressed();
      dispatch({type: "audio-changed", phase: "suspended"});
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
    selectCanOpenProject(state);
  const canImportProject = session !== undefined &&
    !projectActions.busy &&
    selectCanImportProject(state);

  return (
    <div className="workspace">
      <StatusBar
        state={state}
        {...(session && inputController.current
          ? {
              onActivateAudio: (event) => { void activateAudio(event.nativeEvent); },
              onSuspendAudio: () => { void suspendAudio(); },
              onEnableMidi: () => { void inputController.current?.enableMidi(); },
              onExportReport: exportReport,
            }
          : {})}
      />
      <ModeRail />
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
      <ErrorPanel
        code={state.runtime.errorCode}
        details={state.runtime.errorDetails}
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
