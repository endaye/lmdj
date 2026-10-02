import {userMessage} from "../state/error_messages";
import {useReportFailure} from "../runtime/diagnostics_context";
import {useCallback, useEffect, useRef, useState} from "react";
import type {
  AuthoringHistoryMutation,
  AuthoringHistoryRequest,
  AuthoringHistoryRuntimeSession,
  AuthoringHistoryStatus,
} from "@lmdj/web-runtime-platform/runtime_types";
import type {CreatorRuntimeSession} from "../runtime/runtime_types";

export function isAuthoringHistorySession(
  session: CreatorRuntimeSession | undefined,
): session is CreatorRuntimeSession & AuthoringHistoryRuntimeSession {
  const candidate = session as Partial<AuthoringHistoryRuntimeSession> | undefined;
  return typeof candidate?.inspectAuthoringHistory === "function" &&
    typeof candidate.undoAuthoring === "function" && typeof candidate.redoAuthoring === "function";
}

export function historyDisabledMessage(reason: string): string {
  switch (reason) {
    case "sequence_session_active": return "Finish Pattern recording to undo or redo.";
    case "performance_session_active": return "Save or discard the Performance recording first.";
    case "sample_import_pending": return "Wait for the sound import to finish.";
    case "pattern_transport_busy": return "Stop Pattern playback to undo or redo.";
    case "sequence_recovery_pending": case "performance_recovery_pending":
      return "Resolve the pending recording recovery first.";
    case "authoring_history_result_unknown": return "Checking whether the last change was saved…";
    case "authoring_history_owner_lost": case "authoring_history_invalidated":
      return "History ended because the Project changed outside this session. Reopen it to start a new history.";
    case "authoring_history_not_open": return "Open a Project to start its history.";
    case "": return "";
    default: return "Undo and redo are temporarily unavailable.";
  }
}

interface UseAuthoringHistoryOptions {
  session: CreatorRuntimeSession | undefined;
  projectId: string | null;
  revision: number | null;
  refreshKey: string;
  disabledReason: string;
  onChanged(mutation: AuthoringHistoryMutation): Promise<void>;
  onBusy(busy: boolean): void;
}

// #1680: what the user sees for a failed history request; the code and the
// Host message are recorded in Developer diagnostics.
function historyFailureCopy(failure: unknown): string {
  const code = typeof failure === "object" && failure !== null && "code" in failure &&
    typeof failure.code === "string" ? failure.code : "INTERNAL_ERROR";
  const {message, nextStep} = userMessage(code);
  return `${message} ${nextStep}`;
}

export interface AuthoringHistoryController {
  busy: boolean;
  reason: string;
  statusText: string;
  undoAvailable: boolean;
  redoAvailable: boolean;
  undoTitle: string;
  redoTitle: string;
  undo(): void;
  redo(): void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.closest("input, textarea, select") !== null) return true;
  // The nearest contenteditable host decides: every value but "false" edits
  // ("", "true", "plaintext-only"), matching isContentEditable without
  // depending on it (jsdom does not implement the property).
  const host = target.closest("[contenteditable]");
  return host !== null && host.getAttribute("contenteditable")?.toLowerCase() !== "false";
}

// Headless session-history controller. The rail renders it as a SHIFT chord
// (SHIFT + ← / SHIFT + →) with lamp availability; this hook owns inspection,
// exact-retry identity and the desktop Cmd/Ctrl+Z shortcuts.
export function useAuthoringHistory(props: UseAuthoringHistoryOptions): AuthoringHistoryController {
  const reportFailure = useReportFailure();
  const [status, setStatus] = useState<Readonly<AuthoringHistoryStatus> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const retained = useRef<{direction: "undo" | "redo"; request: AuthoringHistoryRequest} | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const latestStatus = useRef(status);
  latestStatus.current = status;
  const available = isAuthoringHistorySession(props.session) && props.projectId !== null;

  useEffect(() => {
    retained.current = null;
    setError(null);
  }, [props.session, props.projectId]);

  useEffect(() => {
    const epoch = ++generation.current;
    setStatus(null);
    if (!isAuthoringHistorySession(props.session) || props.projectId === null) return;
    const session = props.session;
    const inspect = async () => {
      try {
        const value = await session.inspectAuthoringHistory();
        if (epoch === generation.current) setStatus(value);
      } catch (failure) {
        if (epoch === generation.current) {
          setStatus(null);
          reportFailure("Check Undo history", failure);
          setError(`History could not be checked. ${userMessage(
            typeof failure === "object" && failure !== null && "code" in failure &&
              typeof failure.code === "string" ? failure.code : "INTERNAL_ERROR").nextStep}`);
        }
      }
    };
    void inspect();
    window.addEventListener("focus", inspect);
    return () => {
      ++generation.current;
      window.removeEventListener("focus", inspect);
    };
  }, [props.session, props.projectId, props.revision, props.refreshKey]);

  // One synchronous admission reading for the rail chord, the keyboard
  // shortcut and restore itself, so preventDefault only happens when a
  // history action will actually run.
  const canRestoreNow = useRef<(direction: "undo" | "redo") => boolean>(() => false);
  canRestoreNow.current = (direction) => {
    const current = latest.current;
    const snapshot = latestStatus.current;
    if (!isAuthoringHistorySession(current.session) || snapshot === null ||
        inFlight.current || current.disabledReason) return false;
    return (retained.current?.direction === direction &&
        retained.current.request.sessionId === snapshot.sessionId) ||
      (direction === "undo" ? snapshot.canUndo : snapshot.canRedo);
  };

  const restore = useCallback(async (direction: "undo" | "redo") => {
    if (!canRestoreNow.current(direction)) return;
    const current = latest.current;
    const session = current.session;
    const snapshot = latestStatus.current;
    if (!isAuthoringHistorySession(session) || snapshot === null) return;
    inFlight.current = true;
    setBusy(true);
    current.onBusy(true);
    setError(null);
    const projectId = current.projectId;
    const stillCurrent = () => latest.current.session === session && latest.current.projectId === projectId;
    // A refused or failed request keeps its identity for an explicit retry.
    // An advanced revision may be our lost acknowledgement. Replay the original
    // command even when inspection now reports an empty source stack.
    const previous = retained.current;
    const request = previous?.direction === direction &&
        previous.request.sessionId === snapshot.sessionId
      ? previous.request
      : {sessionId: snapshot.sessionId, commandId: crypto.randomUUID(), expectedRevision: snapshot.projectRevision};
    retained.current = {direction, request};
    try {
      const mutation = await (direction === "undo" ? session.undoAuthoring(request) : session.redoAuthoring(request));
      retained.current = null;
      if (!stillCurrent()) return;
      await current.onChanged(mutation);
      if (stillCurrent() && mutation.snapshotError !== null) {
        reportFailure("Prepare sound after Undo or Redo", mutation.snapshotError);
        setError("The change was saved, but the sound is not ready to play yet. Try preparing the audio again.");
      }
    } catch (failure) {
      // The Core checks an existing receipt before revision validation, so an
      // explicit conflict proves this request did not commit. The next click
      // can target the newly inspected revision instead of retrying forever.
      if (failure instanceof Error && "code" in failure && failure.code === "REVISION_CONFLICT") {
        retained.current = null;
      }
      if (stillCurrent()) {
        reportFailure(direction === "undo" ? "Undo" : "Redo", failure);
        setError(historyFailureCopy(failure));
      }
    } finally {
      if (stillCurrent()) {
        try {
          const observed = await session.inspectAuthoringHistory();
          if (stillCurrent()) setStatus(observed);
        } catch { if (stillCurrent()) setStatus(null); }
      }
      inFlight.current = false;
      setBusy(false);
      current.onBusy(false);
    }
  }, []);

  const undo = useCallback(() => { void restore("undo"); }, [restore]);
  const redo = useCallback(() => { void restore("redo"); }, [restore]);

  // Desktop parity: Cmd/Ctrl+Z undoes, Cmd/Ctrl+Shift+Z redoes. Editable
  // fields keep their native text undo, a widget that already handled the
  // key keeps precedence, and the key is only intercepted when a history
  // action will actually run.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (event.code !== "KeyZ" || event.altKey || !(event.metaKey || event.ctrlKey)) return;
      if (isEditableTarget(event.target)) return;
      const direction = event.shiftKey ? "redo" : "undo";
      if (!canRestoreNow.current(direction)) return;
      event.preventDefault();
      void restore(direction);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [restore]);

  const canRetry = (direction: "undo" | "redo") => retained.current?.direction === direction &&
    retained.current.request.sessionId === status?.sessionId;
  const reason = props.disabledReason || historyDisabledMessage(status?.disabledReason ?? "authoring_history_not_open");
  const undoAvailable = available && !busy && !reason && (status?.canUndo === true || canRetry("undo"));
  const redoAvailable = available && !busy && !reason && (status?.canRedo === true || canRetry("redo"));
  return {
    busy,
    reason,
    statusText: error || (busy ? "Updating Project…" : reason ||
      (status?.undoLabel ? `Undo: ${status.undoLabel}` : status?.redoLabel ? `Redo: ${status.redoLabel}` :
        available ? "No changes in this session" : "")),
    undoAvailable,
    redoAvailable,
    undoTitle: reason || (status?.undoLabel ? `Undo ${status.undoLabel}` : "Nothing to undo"),
    redoTitle: reason || (status?.redoLabel ? `Redo ${status.redoLabel}` : "Nothing to redo"),
    undo,
    redo,
  };
}
