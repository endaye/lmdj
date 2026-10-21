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
  const message = userMessage(code, details);
  const onlyProjectRetry = code === "PROJECT_BUSY" && onRetryProject && !onContinueHere;
  const nextStep = onlyProjectRetry
    ? "Close the Project where it is already open, then choose Retry project."
    : message.nextStep;
  return (
    <aside className="error-panel" role="alert">
      <strong>{code === "DUPLICATE_ID"
        ? "Project already on this device"
        : "Creator unavailable"}</strong>
      <span>{message.message}</span>
      <span className="error-next-step">{nextStep}</span>
      {note !== null && <span className="takeover-note">{note}</span>}
      <div className="error-panel-actions">
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
      </div>
    </aside>
  );
}
