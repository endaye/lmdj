const STAGES = [
  {
    state: "queued",
    label: "Input Validated",
    description: "Upload accepted; source evidence retained.",
  },
  {
    state: "separating",
    label: "Stem Separation",
    description: "Building canonical stems.",
  },
  {
    state: "extracting",
    label: "Material Extraction",
    description: "Selecting quality-gated one-shots and aligned loops.",
  },
  {
    state: "patchifying",
    label: "Chop + Map",
    description: "Mapping playable material to 16 Pads.",
  },
  {
    state: "completed",
    label: "Patch Verify",
    description: "Verifying the shared patch contract.",
  },
] as const;

export function UploadingView({
  state,
  lastNonterminalState,
}: {
  state: string;
  lastNonterminalState: string;
}) {
  if (state === "preflight") {
    return (
      <div
        className="processing-preflight"
        data-testid="processing-preflight"
        aria-live="polite"
      >
        <span className="stage-icon" aria-hidden="true">↻</span>
        <span>
          <strong>Validating Input</strong>
          <small>Checking size, format, codec, and duration before creating a Job.</small>
        </span>
        <code>preflight</code>
      </div>
    );
  }

  const terminal =
    state === "failed" || state === "interrupted" || state === "cancelled";
  const effectiveState = terminal ? lastNonterminalState : state;
  const currentIndex = STAGES.findIndex(
    (stage) => stage.state === effectiveState,
  );
  return (
    <ol className="stages" aria-label="Processing stages">
      {STAGES.map((stage, index) => {
          const status =
            index < currentIndex
              ? "done"
              : index === currentIndex
                ? "current"
                : "pending";
          return (
            <li
              key={stage.state}
              className={`stage stage--${status}`}
              data-testid={`processing-stage-${stage.state}`}
              aria-current={status === "current" ? "step" : undefined}
            >
              <span className="stage-icon" aria-hidden="true">
                {status === "done" ? "✓" : index + 1}
              </span>
              <span>
                <strong>{stage.label}</strong>
                <small>{stage.description}</small>
              </span>
              <code>{stage.state}</code>
            </li>
          );
        })}
      {currentIndex === -1 && (
        <li className="stage stage--unknown" data-testid="processing-stage-unknown">
          <span className="stage-icon" aria-hidden="true">?</span>
          <span>
            <strong>Unknown</strong>
            <small>The worker reported an unmapped state.</small>
          </span>
          <code>{effectiveState}</code>
        </li>
      )}
      {terminal && (
        <li
          className={`stage stage--terminal stage--terminal-${state}`}
          data-testid={`processing-terminal-${state}`}
        >
          <span className="stage-icon" aria-hidden="true">!</span>
          <span>
            <strong>
              {state === "interrupted"
                ? "Service interrupted"
                : state === "cancelled"
                  ? "Processing cancelled"
                  : "Processing failed"}
            </strong>
            <small>
              {state === "interrupted"
                ? "The API restarted before this Job completed."
                : "Completed stages above remain the last confirmed evidence."}
            </small>
          </span>
          <code>{state}</code>
        </li>
      )}
      </ol>
  );
}
