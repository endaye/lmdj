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
  runtimeHostState?: string;
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
  runtimeHostState,
}: WorkspaceProps) {
  const [state, dispatch] = useReducer(creatorReducer, initialState);
  const [listAttempt, setListAttempt] = useState(0);
  const importController = useRef<AbortController | null>(null);
  const inputController = useRef<ReturnType<typeof createCreatorInputController> | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => () => importController.current?.abort(), []);

  useEffect(() => {
    if (!session || runtimePhase !== "ready") return;
    const controller = createCreatorInputController({
      session,
      getActiveBank: () => stateRef.current.activeBank,
      isAssigned: (slot) =>
        stateRef.current.project.current?.pads[slot]?.assetId !== null &&
        stateRef.current.project.current?.pads[slot]?.assetId !== undefined &&
        stateRef.current.audio.phase === "running",
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
      runtimeHostState === "interrupted" ||
      runtimeHostState === "recovering" ||
      (runtimeHostState === "audio-suspended" &&
        stateRef.current.audio.phase !== "inactive")
    ) {
      dispatch({type: "audio-changed", phase: "suspended"});
    }
  }, [runtimeHostState]);

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
      async (projects) => {
        if (!active) return;
        dispatch({type: "projects-loaded", projects});
        const retained = stateRef.current.project.current;
        if (!retained) return;
        const summary = projects.find(({projectId, patternId}) =>
          projectId === retained.projectId && patternId === retained.patternId);
        if (!summary) {
          dispatch({type: "project-error", errorCode: "NOT_FOUND"});
          return;
        }
        dispatch({type: "project-opening"});
        try {
          const project = await openProjectJourney(session, summary);
          if (active) dispatch({type: "project-ready", project});
        } catch (error) {
          if (active) reportProjectError(error);
        }
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
          }));
        } else {
          dispatch({type: "audio-changed", phase: "inactive"});
        }
      } else if (session.diagnostics().state === "running") {
        dispatch({type: "audio-changed", phase: "running"});
      }
    } catch (error) {
      dispatch({type: "audio-changed", phase: "inactive"});
      if (!(error instanceof TypeError)) reportProjectError(error);
    }
  };

  const suspendAudio = async () => {
    if (!session) return;
    if (await session.suspendAudio()) {
      inputController.current?.clearPressed();
      dispatch({type: "audio-changed", phase: "suspended"});
    }
  };

  return (
    <div className="workspace">
      <StatusBar
        state={state}
        {...(session && inputController.current
          ? {
              onActivateAudio: (event) => { void activateAudio(event.nativeEvent); },
              onSuspendAudio: () => { void suspendAudio(); },
              onEnableMidi: () => { void inputController.current?.enableMidi(); },
            }
          : {})}
      />
      <ModeRail />
      <ProjectSurface
        state={state}
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
      runtimeHostState={runtime.hostState}
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
