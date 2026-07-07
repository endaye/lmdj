export function ErrorPanel({ issues }: { issues: string[] }) {
  return (
    <div className="error-panel" data-testid="error-panel">
      <strong>patch.json 未通过 lmdj.patch.v1 校验：</strong>
      {"\n"}
      {issues.join("\n")}
    </div>
  );
}
