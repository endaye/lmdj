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
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null);

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
  const [session] = useState<CreatorRuntimeSession>(() => factory());
  const [phase, setPhase] = useState<RuntimeProviderPhase>("booting");
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const closePromise = useRef<Promise<unknown> | null>(null);
  const closeOnce = useCallback(() => {
    if (closePromise.current === null) {
      closePromise.current = Promise.resolve(session.close()).catch(() => {});
    }
    return closePromise.current;
  }, [session]);

  useEffect(() => {
    let active = true;
    const pagehide = () => {
      if (active) setPhase("closed");
      void closeOnce();
    };
    window.addEventListener("pagehide", pagehide);
    void session.start().then(
      () => {
        if (active) setPhase("ready");
      },
      (error: unknown) => {
        if (!active) return;
        setErrorCode((error as TypedRuntimeError | null)?.code ?? "INTERNAL_ERROR");
        setPhase(phaseForError(error));
      },
    );
    return () => {
      active = false;
      window.removeEventListener("pagehide", pagehide);
      void closeOnce();
    };
  }, [closeOnce, session]);

  const value = useMemo(
    () => ({session, phase, errorCode}),
    [session, phase, errorCode],
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
