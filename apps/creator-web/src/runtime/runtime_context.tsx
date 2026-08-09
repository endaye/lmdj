import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {createUserGestureToken} from
  "@lmdj/web-runtime-platform/input_adapters.mjs";

import type {
  CreatorRuntimeSession,
  RuntimeSessionFactory,
  TypedRuntimeError,
} from "./runtime_types";

export type RuntimeProviderPhase =
  | "booting"
  | "ready"
  | "unsupported"
  | "restart-required"
  | "failed"
  | "closed";

interface RuntimeContextValue {
  session: CreatorRuntimeSession;
  phase: RuntimeProviderPhase;
  errorCode: string | null;
  hostState: string;
  recoveryProbeReady: boolean;
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null);

export function activateCreatorAudio(
  session: CreatorRuntimeSession,
  event: {isTrusted: boolean},
): Promise<boolean> {
  return session.activateAudio(createUserGestureToken(event));
}

function phaseForError(error: unknown): RuntimeProviderPhase {
  const code = (error as TypedRuntimeError | null)?.code;
  if (code === "UNSUPPORTED_WEB_RUNTIME") return "unsupported";
  if (code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT") {
    return "restart-required";
  }
  return "failed";
}

interface RuntimeProviderProps {
  factory: RuntimeSessionFactory;
  children: ReactNode;
}

export function RuntimeProvider({factory, children}: RuntimeProviderProps) {
  const factoryRef = useRef(factory);
  factoryRef.current = factory;
  const [session, setSession] = useState<CreatorRuntimeSession>(() => factory());
  const [phase, setPhase] = useState<RuntimeProviderPhase>("booting");
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [hostState, setHostState] = useState("cold");
  const [recoveryProbeReady, setRecoveryProbeReady] = useState(false);
  const closePromises = useRef(new WeakMap<CreatorRuntimeSession, Promise<unknown>>());
  const restartCount = useRef(0);
  const closeOnce = useCallback((target: CreatorRuntimeSession) => {
    let pending = closePromises.current.get(target);
    if (!pending) {
      pending = Promise.resolve().then(() => target.close()).catch(() => {});
      closePromises.current.set(target, pending);
    }
    return pending;
  }, []);

  useEffect(() => {
    let active = true;
    let replacementStarted = false;
    let recoveryTimer: number | null = null;
    setPhase("booting");
    setErrorCode(null);
    setHostState("cold");
    setRecoveryProbeReady(false);

    const stopRecoveryProbeWatch = () => {
      if (recoveryTimer !== null) window.clearTimeout(recoveryTimer);
      recoveryTimer = null;
    };
    const watchRecoveryProbe = () => {
      if (!active) return;
      const diagnostics = session.diagnostics();
      if (diagnostics.state !== "recovering") {
        setRecoveryProbeReady(false);
        recoveryTimer = null;
        return;
      }
      setRecoveryProbeReady(diagnostics.recovery_probe_ready === true);
      recoveryTimer = window.setTimeout(watchRecoveryProbe, 16);
    };

    const observe = ({state, errorCode: observedError}: {
      state: string;
      errorCode: string | null;
    }) => {
      if (!active) return;
      setHostState(state);
      setErrorCode(observedError);
      stopRecoveryProbeWatch();
      if (state === "recovering") {
        watchRecoveryProbe();
      } else {
        setRecoveryProbeReady(false);
      }
      if (state === "restart-required") {
        setPhase("restart-required");
        if (restartCount.current === 0 && !replacementStarted) {
          restartCount.current += 1;
          replacementStarted = true;
          void closeOnce(session).then(() => {
            if (active) setSession(factoryRef.current());
          });
        }
      } else if (state === "failed") {
        setPhase("failed");
      } else if (state === "closed") {
        setPhase("closed");
      }
    };
    const unsubscribeHostState = session.subscribeHostState(observe);
    const pagehide = (event: PageTransitionEvent) => {
      if (event.persisted) return;
      if (active) setPhase("closed");
      void closeOnce(session);
    };
    window.addEventListener("pagehide", pagehide);
    void session.start().then(
      (started) => {
        if (!active) return;
        const diagnostics = session.diagnostics();
        setHostState(diagnostics.state);
        if (!started) {
          const code = diagnostics.error_code ?? "HOST_STATE_INVALID";
          setErrorCode(code);
          observe({state: diagnostics.state, errorCode: code});
          if (code === "UNSUPPORTED_WEB_RUNTIME") {
            setPhase("unsupported");
          } else if (!["restart-required", "failed", "closed"].includes(diagnostics.state)) {
            setPhase(phaseForError(Object.assign(new Error(code), {code})));
          }
          return;
        }
        setPhase("ready");
      },
      (error: unknown) => {
        if (!active) return;
        setErrorCode((error as TypedRuntimeError | null)?.code ?? "INTERNAL_ERROR");
        setPhase(phaseForError(error));
      },
    );
    return () => {
      active = false;
      stopRecoveryProbeWatch();
      window.removeEventListener("pagehide", pagehide);
      unsubscribeHostState();
      void closeOnce(session);
    };
  }, [closeOnce, session]);

  const value = useMemo(
    () => ({session, phase, errorCode, hostState, recoveryProbeReady}),
    [session, phase, errorCode, hostState, recoveryProbeReady],
  );
  return <RuntimeContext value={value}>{children}</RuntimeContext>;
}

export function useRuntime(): RuntimeContextValue {
  const value = useContext(RuntimeContext);
  if (value === null) {
    throw new Error("Creator RuntimeProvider is missing");
  }
  return value;
}
