interface ErrorPanelProps {
  code: string | null;
}

export function ErrorPanel({code}: ErrorPanelProps) {
  if (code === null) return null;
  return (
    <aside className="error-panel" role="alert">
      <strong>Creator unavailable</strong>
      <span>{code}</span>
    </aside>
  );
}
