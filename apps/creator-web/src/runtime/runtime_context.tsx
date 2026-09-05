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
  RuntimeHostState,
  RuntimeIssue,
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
  issue: RuntimeIssue | null;
  hostState: string;
  recoveryProbeReady: boolean;
  retryRuntime: () => void;
  registerShutdownBarrier: (barrier: () => Promise<unknown>) => () => void;
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null);
const EMPTY_DETAILS = Object.freeze({});

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

function detailsForError(error: unknown): Readonly<Record<string, unknown>> {
  const details = (error as TypedRuntimeError | null)?.details;
  return details !== null && typeof details === "object" && !Array.isArray(details)
    ? details
    : EMPTY_DETAILS;
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
  const [errorDetails, setErrorDetails] =
    useState<Readonly<Record<string, unknown>>>(EMPTY_DETAILS);
  const [hostState, setHostState] = useState("cold");
  const [recoveryProbeReady, setRecoveryProbeReady] = useState(false);
  const closePromises = useRef(new WeakMap<CreatorRuntimeSession, Promise<unknown>>());
  const shutdownBarriers = useRef(new WeakMap<
    CreatorRuntimeSession,
    Set<() => Promise<unknown>>
  >());
  const generation = useRef(0);
  const automaticRestartAvailable = useRef(true);
  const manualRetryInFlight = useRef(false);
  const closeOnce = useCallback((target: CreatorRuntimeSession) => {
    let pending = closePromises.current.get(target);
    if (!pending) {
      pending = Promise.resolve().then(async () => {
        const barriers = shutdownBarriers.current.get(target);
        if (barriers !== undefined) {
          await Promise.all([...barriers].map((barrier) => barrier()));
          shutdownBarriers.current.delete(target);
        }
        await target.close();
      }).catch(() => {});
      closePromises.current.set(target, pending);
    }
    return pending;
  }, []);
  const registerShutdownBarrier = useCallback((
    barrier: () => Promise<unknown>,
  ) => {
    let barriers = shutdownBarriers.current.get(session);
    if (barriers === undefined) {
      barriers = new Set();
      shutdownBarriers.current.set(session, barriers);
    }
    let pending: Promise<unknown> | null = null;
    const runOnce = () => {
      pending ??= Promise.resolve().then(barrier).catch(() => {});
      return pending;
    };
    barriers.add(runOnce);
    return () => {
      void runOnce().finally(() => barriers?.delete(runOnce));
    };
  }, [session]);

  const retryRuntime = useCallback(() => {
    if (manualRetryInFlight.current) return;
    manualRetryInFlight.current = true;
    automaticRestartAvailable.current = true;
    const replacementGeneration = generation.current + 1;
    generation.current = replacementGeneration;
    setPhase("booting");
    setErrorCode(null);
    setErrorDetails(EMPTY_DETAILS);
    setHostState("cold");
    setRecoveryProbeReady(false);
    void closeOnce(session).then(() => {
      if (generation.current === replacementGeneration) {
        setSession(factoryRef.current());
      }
    });
  }, [closeOnce, session]);

  useEffect(() => {
    const ownedGeneration = generation.current + 1;
    generation.current = ownedGeneration;
    let active = true;
    let replacementStarted = false;
    manualRetryInFlight.current = false;
    setPhase("booting");
    setErrorCode(null);
    setErrorDetails(EMPTY_DETAILS);
    setHostState("cold");
    setRecoveryProbeReady(false);

    const ownsGeneration = () =>
      active && generation.current === ownedGeneration;

    const startAutomaticReplacement = () => {
      if (
        replacementStarted ||
        automaticRestartAvailable.current !== true ||
        !ownsGeneration()
      ) {
        return;
      }
      replacementStarted = true;
      automaticRestartAvailable.current = false;
      const replacementGeneration = generation.current + 1;
      generation.current = replacementGeneration;
      void closeOnce(session).then(() => {
        if (generation.current === replacementGeneration) {
          setSession(factoryRef.current());
        }
      });
    };

    const observe = ({
      state,
      errorCode: observedError,
      errorDetails: observedDetails,
    }: RuntimeHostState) => {
      if (!ownsGeneration()) return;
      setHostState(state);
      setErrorCode(observedError);
      setErrorDetails(observedDetails);
      if (state !== "recovering") {
        setRecoveryProbeReady(false);
      }
      if (state === "running") {
        automaticRestartAvailable.current = true;
      } else if (state === "restart-required") {
        setPhase("restart-required");
        startAutomaticReplacement();
      } else if (state === "failed") {
        setPhase(observedError === "UNSUPPORTED_WEB_RUNTIME"
          ? "unsupported"
          : "failed");
      } else if (state === "closed") {
        setPhase("closed");
      }
    };
    const unsubscribeHostState = session.subscribeHostState(observe);
    const unsubscribeDiagnostics = session.subscribeDiagnostics((value) => {
      if (!ownsGeneration()) return;
      setRecoveryProbeReady(
        value.state === "recovering" && value.recovery_probe_ready === true,
      );
    });
    const pagehide = (event: PageTransitionEvent) => {
      if (event.persisted || !ownsGeneration()) return;
      generation.current += 1;
      setPhase("closed");
      void closeOnce(session);
    };
    window.addEventListener("pagehide", pagehide);
    void session.start().then(
      (started) => {
        if (!ownsGeneration()) return;
        const diagnostics = session.diagnostics();
        setHostState(diagnostics.state);
        setErrorCode(diagnostics.error_code);
        setErrorDetails(diagnostics.error_details);
        setRecoveryProbeReady(
          diagnostics.state === "recovering" &&
          diagnostics.recovery_probe_ready === true,
        );
        if (!started) {
          const code = diagnostics.error_code ?? "HOST_STATE_INVALID";
          if (code === "UNSUPPORTED_WEB_RUNTIME") {
            setPhase("unsupported");
          } else if (diagnostics.state === "restart-required") {
            observe({
              state: diagnostics.state,
              errorCode: code,
              errorDetails: diagnostics.error_details,
            });
          } else if (!["failed", "closed"].includes(diagnostics.state)) {
            setPhase(phaseForError(Object.assign(new Error(code), {code})));
          } else {
            setPhase(diagnostics.state as "failed" | "closed");
          }
          return;
        }
        setPhase("ready");
      },
      (error: unknown) => {
        if (!ownsGeneration()) return;
        const code = (error as TypedRuntimeError | null)?.code ?? "INTERNAL_ERROR";
        const details = detailsForError(error);
        setErrorCode(code);
        setErrorDetails(details);
        if (code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT") {
          observe({
            state: "restart-required",
            errorCode: code,
            errorDetails: details,
          });
        } else {
          setPhase(phaseForError(error));
        }
      },
    );
    return () => {
      active = false;
      generation.current += 1;
      window.removeEventListener("pagehide", pagehide);
      unsubscribeDiagnostics();
      unsubscribeHostState();
      void closeOnce(session);
    };
  }, [closeOnce, session]);

  const issue = useMemo<RuntimeIssue | null>(
    () => errorCode === null
      ? null
      : Object.freeze({code: errorCode, details: errorDetails}),
    [errorCode, errorDetails],
  );
  const value = useMemo(
    () => ({
      session,
      phase,
      errorCode,
      issue,
      hostState,
      recoveryProbeReady,
      retryRuntime,
      registerShutdownBarrier,
    }),
    [
      session,
      phase,
      errorCode,
      issue,
      hostState,
      recoveryProbeReady,
      retryRuntime,
      registerShutdownBarrier,
    ],
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
