const STAGES = ["queued", "separating", "patchifying", "completed"];

export function UploadingView({
  state,
  error,
  onBack,
}: {
  state: string;
  error: string | null;
  onBack: () => void;
}) {
  const currentIndex = STAGES.indexOf(state);
  return (
    <div className="uploading" data-testid="uploading">
      <div className="uploading-title">PROCESSING…</div>
      <ol className="stages">
        {STAGES.map((stage, i) => {
          const cls = error
            ? "stage--pending"
            : i < currentIndex
              ? "stage--done"
              : i === currentIndex
                ? "stage--current"
                : "stage--pending";
          return (
            <li key={stage} className={`stage ${cls}`} data-testid={`stage-${stage}`}>
              {stage}
            </li>
          );
        })}
      </ol>
      {error && (
        <div className="uploading-error" data-testid="uploading-error">
          {error}
        </div>
      )}
      {error && <button onClick={onBack}>返回</button>}
    </div>
  );
}
