interface ErrorPanelProps {
  code: string | null;
  details?: Readonly<Record<string, unknown>> | undefined;
  onRetryProject?: () => void;
  onRetryRuntime?: () => void;
  onOpenLocalProject?: () => void;
  onDismiss?: () => void;
}

const STORAGE_CONDITIONS = new Set([
  "already_exists",
  "atomic_publish_unsupported",
  "invalid_state",
  "io_failure",
  "project_busy",
  "quota_exceeded",
]);

function safeName(value: unknown, fallback: string): string {
  return typeof value === "string" && /^[a-z0-9._-]{1,64}$/.test(value)
    ? value
    : fallback;
}

function safeCount(value: unknown): string {
  return Number.isSafeInteger(value) && (value as number) >= 0
    ? String(value)
    : "unknown";
}

function messageFor(
  code: string,
  details: Readonly<Record<string, unknown>>,
): string {
  switch (code) {
    case "INVALID_PROJECT":
      return "The Project Bundle is invalid.";
    case "LOCAL_PROJECT_UNREADABLE":
      return "The local copy of this Project on this device could not be read. The imported file is not at fault.";
    case "DUPLICATE_ID":
      return "The import was refused because the local copy of this Project has newer changes. Nothing was lost.";
    case "PROJECT_BUSY":
      return "The local Project is busy in another tab or process.";
    case "WEB_RUNTIME_RESOURCE_LIMIT":
      return `${safeName(details.resource, "resource")}: observed ${
        safeCount(details.observed)
      }, limit ${safeCount(details.limit)}.`;
    case "IO_ERROR": {
      const condition = STORAGE_CONDITIONS.has(String(details.storage_condition))
        ? String(details.storage_condition)
        : "unavailable";
      return `Storage condition: ${condition}.`;
    }
    case "HOST_PROTOCOL_MISMATCH":
      return "Creator and Runtime could not verify a compatible protocol.";
    case "INTERNAL_ERROR":
      return "Creator encountered an internal failure.";
    case "HOST_RESTART_REQUIRED":
    case "HOST_TIMEOUT":
      return "Runtime must be restarted before continuing.";
    default:
      return `Creator cannot continue (${
        /^[A-Z0-9_]{1,64}$/.test(code) ? code : "UNKNOWN_ERROR"
      }).`;
  }
}

export function ErrorPanel({
  code,
  details = {},
  onRetryProject,
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
      <span>{messageFor(code, details)}</span>
      {code === "DUPLICATE_ID" && onOpenLocalProject && (
        <button type="button" onClick={onOpenLocalProject}>
          Open local Project
        </button>
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
