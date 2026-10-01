import {useState} from "react";

// Asked once when a Project opens holding interrupted recordings (#1680).
// It is not an error and not modal: ignoring it, More options and Decide
// later change nothing, and the recordings stay in the Sequence and Perform
// recovery lists. Only Keep or a confirmed Discard acts on them.

export interface RecoveryCounts {
  readonly sequence: number;
  readonly performance: number;
}

type Phase =
  | {readonly kind: "asking"}
  | {readonly kind: "confirm-discard"}
  | {readonly kind: "working"; readonly action: "keep" | "discard"}
  | {readonly kind: "done"; readonly action: "keep" | "discard"; readonly remaining: RecoveryCounts};

interface RecoveryPromptProps {
  counts: RecoveryCounts;
  // Each resolves to the recordings still waiting afterwards.
  onKeep: () => Promise<RecoveryCounts>;
  onDiscard: () => Promise<RecoveryCounts>;
  onOpen: (mode: "sequence" | "perform") => void;
  onClose: () => void;
}

function describe({sequence, performance}: RecoveryCounts): string {
  const parts = [
    sequence > 0 ? `${sequence} in Sequence` : null,
    performance > 0 ? `${performance} in Perform` : null,
  ].filter((part) => part !== null);
  return parts.join(" and ");
}

export function RecoveryPrompt({counts, onKeep, onDiscard, onOpen, onClose}: RecoveryPromptProps) {
  const [phase, setPhase] = useState<Phase>({kind: "asking"});
  const total = counts.sequence + counts.performance;
  const run = (action: "keep" | "discard") => {
    setPhase({kind: "working", action});
    void (action === "keep" ? onKeep() : onDiscard()).then(
      (remaining) => setPhase({kind: "done", action, remaining}),
      () => setPhase({kind: "done", action, remaining: counts}),
    );
  };
  const openButtons = (remaining: RecoveryCounts) => <>
    {remaining.sequence > 0 && (
      <button type="button" onClick={() => onOpen("sequence")}>Open Sequence</button>
    )}
    {remaining.performance > 0 && (
      <button type="button" onClick={() => onOpen("perform")}>Open Perform</button>
    )}
  </>;

  let body: React.ReactNode;
  if (phase.kind === "asking") {
    body = <>
      <p>
        {total === 1 ? "A recording" : `${total} recordings`} stopped before
        {total === 1 ? " it was" : " they were"} saved ({describe(counts)}).
        Keep {total === 1 ? "it" : "them"} in this Project?
      </p>
      <div className="recovery-prompt-actions">
        <button type="button" className="primary" onClick={() => run("keep")}>
          Keep recording
        </button>
        <button type="button" onClick={() => setPhase({kind: "confirm-discard"})}>
          Discard…
        </button>
        <button type="button" onClick={() => onOpen(counts.sequence > 0 ? "sequence" : "perform")}>
          More options
        </button>
        <button type="button" onClick={onClose}>Decide later</button>
      </div>
    </>;
  } else if (phase.kind === "confirm-discard") {
    body = <>
      <p>Discard the interrupted {total === 1 ? "recording" : "recordings"}? This cannot be undone.</p>
      <div className="recovery-prompt-actions">
        <button type="button" onClick={() => run("discard")}>Discard recording</button>
        <button type="button" onClick={() => setPhase({kind: "asking"})}>Cancel</button>
      </div>
    </>;
  } else if (phase.kind === "working") {
    body = <p role="status">{phase.action === "keep" ? "Keeping…" : "Discarding…"}</p>;
  } else {
    const left = phase.remaining.sequence + phase.remaining.performance;
    body = <>
      <p role="status">
        {left === 0
          ? (phase.action === "keep"
            ? "The interrupted recording is back in this Project."
            : "The interrupted recording was discarded.")
          : `Some of it could not be ${phase.action === "keep" ? "kept" : "discarded"} here
            (${describe(phase.remaining)}). Open it to keep or discard it there.`}
      </p>
      <div className="recovery-prompt-actions">
        {openButtons(phase.remaining)}
        <button type="button" onClick={onClose}>Close</button>
      </div>
    </>;
  }
  return (
    <section className="recovery-prompt" aria-label="Interrupted recording">
      <strong>Interrupted recording</strong>
      {body}
    </section>
  );
}
