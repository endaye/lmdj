import {userMessage} from "../state/error_messages";

interface ErrorPanelProps {
  code: string | null;
  details?: Readonly<Record<string, unknown>> | undefined;
  onRetryProject?: () => void;
  // Ask the tab holding a busy Project to hand it over (#1679).
  onContinueHere?: () => void;
  note?: string | null;
  onRetryRuntime?: () => void;
  onOpenLocalProject?: () => void;
  onDismiss?: () => void;
}

export function ErrorPanel({
  code,
  details = {},
  onRetryProject,
  onContinueHere,
  note = null,
  onRetryRuntime,
  onOpenLocalProject,
  onDismiss,
}: ErrorPanelProps) {
  if (code === null) return null;
  return (
    <aside className="error-panel" role="alert">
      <strong>{code === "DUPLICATE_ID"
        ? "Project already on this device"
        : "Creator unavailable"}</strong>
      <span>{userMessage(code, details).message}</span>
      <span className="error-next-step">{userMessage(code, details).nextStep}</span>
      {note !== null && <span className="takeover-note">{note}</span>}
      {code === "DUPLICATE_ID" && onOpenLocalProject && (
        <button type="button" onClick={onOpenLocalProject}>
          Open local Project
        </button>
      )}
      {onContinueHere && (
        <button type="button" onClick={onContinueHere}>Continue here</button>
      )}
      {onRetryProject && (
        <button type="button" onClick={onRetryProject}>Retry project</button>
      )}
      {onRetryRuntime && (
        <button type="button" onClick={onRetryRuntime}>Retry runtime</button>
      )}
      {onDismiss && (
        <button type="button" onClick={onDismiss}>Dismiss</button>
      )}
    </aside>
  );
}
