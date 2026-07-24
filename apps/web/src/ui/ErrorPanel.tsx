export function ErrorPanel({
  title,
  issues,
}: {
  title: string;
  issues: string[];
}) {
  return (
    <div className="error-panel" data-testid="error-panel">
      <strong>{title}：</strong>
      {"\n"}
      {issues.join("\n")}
    </div>
  );
}
