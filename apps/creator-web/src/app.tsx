import {useEffect, useReducer, useRef, useState} from "react";

import {BankSelector} from "./components/bank_selector";
import {ErrorPanel} from "./components/error_panel";
import {ModeRail} from "./components/mode_rail";
import {PadSurface} from "./components/pad_surface";
import {ProjectSurface} from "./components/project_surface";
import {StatusBar} from "./components/status_bar";
import {
  importProjectJourney,
  listLocalProjectsJourney,
  openProjectJourney,
} from "./runtime/project_actions";
import {
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
}

function errorCode(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "ABORTED";
  }
  return (error as TypedRuntimeError | null)?.code ?? "INTERNAL_ERROR";
}

function Workspace({
  initialState,
  session,
  runtimePhase,
  runtimeErrorCode,
}: WorkspaceProps) {
  const [state, dispatch] = useReducer(creatorReducer, initialState);
  const [listAttempt, setListAttempt] = useState(0);
  const importController = useRef<AbortController | null>(null);

  useEffect(() => () => importController.current?.abort(), []);

  useEffect(() => {
    if (!session || !runtimePhase) return;
    dispatch({
      type: "runtime-changed",
      phase: runtimePhase,
      errorCode: runtimeErrorCode ?? null,
    });
    if (runtimePhase !== "ready") return;
    let active = true;
    dispatch({type: "projects-listing"});
    void listLocalProjectsJourney(session).then(
      (projects) => {
        if (active) dispatch({type: "projects-loaded", projects});
      },
      (error: unknown) => {
        if (!active) return;
        const code = errorCode(error);
        if (code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT") {
          dispatch({type: "runtime-changed", phase: "restart-required", errorCode: code});
        } else if (code === "UNSUPPORTED_WEB_RUNTIME") {
          dispatch({type: "runtime-changed", phase: "unsupported", errorCode: code});
        } else {
          dispatch({type: "project-error", errorCode: code});
        }
      },
    );
    return () => { active = false; };
  }, [session, runtimePhase, runtimeErrorCode, listAttempt]);

  const reportProjectError = (error: unknown) => {
    if (error instanceof DOMException && error.name === "AbortError") return;
    const code = errorCode(error);
    if (code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT") {
      dispatch({type: "runtime-changed", phase: "restart-required", errorCode: code});
      return;
    }
    dispatch({type: "project-error", errorCode: code});
  };

  const openProject = async (summary: LocalProjectSummary) => {
    if (!session) return;
    dispatch({type: "project-opening"});
    try {
      dispatch({type: "project-ready", project: await openProjectJourney(session, summary)});
    } catch (error) {
      reportProjectError(error);
    }
  };

  const importProject = async (file: File) => {
    if (!session) return;
    importController.current?.abort();
    const controller = new AbortController();
    importController.current = controller;
    dispatch({type: "transfer-started", totalBytes: file.size});
    try {
      const project = await importProjectJourney(
        session,
        file,
        controller.signal,
        ({completedBytes}) => dispatch({type: "transfer-progressed", completedBytes}),
      );
      dispatch({type: "project-ready", project});
    } catch (error) {
      reportProjectError(error);
    } finally {
      if (importController.current === controller) {
        importController.current = null;
      }
      dispatch({type: "transfer-ended"});
    }
  };

  return (
    <div className="workspace">
      <StatusBar state={state} />
      <ModeRail />
      <ProjectSurface
        state={state}
        onOpen={(summary) => { void openProject(summary); }}
        onImport={(file) => { void importProject(file); }}
      />
      <section className="pads" aria-label="Instrument">
        <BankSelector
          activeBank={state.activeBank}
          onSelect={(bank) => dispatch({type: "bank-selected", bank})}
        />
        <PadSurface state={state} />
      </section>
      <ErrorPanel
        code={state.runtime.errorCode}
        {...(session && state.runtime.errorCode === "PROJECT_BUSY"
          ? {onRetry: () => setListAttempt((attempt) => attempt + 1)}
          : {})}
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
