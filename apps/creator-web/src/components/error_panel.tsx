interface ErrorPanelProps {
  code: string | null;
  onRetry?: () => void;
}

export function ErrorPanel({code, onRetry}: ErrorPanelProps) {
  if (code === null) return null;
  return (
    <aside className="error-panel" role="alert">
      <strong>Creator unavailable</strong>
      <span>{code}</span>
      {onRetry && <button type="button" onClick={onRetry}>Retry</button>}
    </aside>
  );
}
