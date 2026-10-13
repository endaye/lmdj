import {useState} from "react";
import "./recovery_prompt.css";

// Asked once when a Project opens holding interrupted recordings (#1680).
// It is not an error and not modal: ignoring it, opening either destination
// and Decide later change nothing, and recordings stay in Sequence and Perform
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
  const openButtons = (remaining: RecoveryCounts) => remaining.sequence + remaining.performance > 0 && (
    <div className="recovery-prompt-destinations">
      {remaining.sequence > 0 && (
        <button type="button" className="touch-control" onClick={() => onOpen("sequence")}>Open Sequence</button>
      )}
      {remaining.performance > 0 && (
        <button type="button" className="touch-control" onClick={() => onOpen("perform")}>Open Perform</button>
      )}
    </div>
  );
  const phaseLabel = phase.kind === "confirm-discard" ? "Confirm discard"
    : phase.kind === "working" ? (phase.action === "keep" ? "Keeping" : "Discarding")
    : phase.kind === "done" && phase.remaining.sequence + phase.remaining.performance === 0
      ? "Complete" : "Action needed";

  let body: React.ReactNode;
  if (phase.kind === "asking") {
    body = <>
      <div className="recovery-prompt-notice">
        <h3>{total === 1 ? "An unfinished recording is here" : `${total} unfinished recordings are here`}</h3>
        <p>
          {total === 1 ? "A recording" : `${total} recordings`} stopped before
          {total === 1 ? " it was" : " they were"} saved ({describe(counts)}).
          Keep {total === 1 ? "it" : "them"} in this Project?
        </p>
      </div>
      <div className="recovery-prompt-actions">
        <button type="button" className="touch-control is-primary" onClick={() => run("keep")}>
          Keep recording
        </button>
        {openButtons(counts)}
        <button type="button" className="touch-control" onClick={onClose}>Decide later</button>
        <button type="button" className="touch-control is-danger" onClick={() => setPhase({kind: "confirm-discard"})}>
          Discard…
        </button>
      </div>
    </>;
  } else if (phase.kind === "confirm-discard") {
    body = <>
      <p className="recovery-prompt-notice">Discard the interrupted {total === 1 ? "recording" : "recordings"}? This cannot be undone.</p>
      <div className="recovery-prompt-actions">
        <button type="button" className="touch-control is-danger" onClick={() => run("discard")}>
          {total === 1 ? "Discard recording" : `Discard ${total} recordings`}
        </button>
        <button type="button" className="touch-control" onClick={() => setPhase({kind: "asking"})}>Cancel</button>
      </div>
    </>;
  } else if (phase.kind === "working") {
    body = <p className="recovery-prompt-notice" role="status">{phase.action === "keep" ? "Keeping…" : "Discarding…"}</p>;
  } else {
    const left = phase.remaining.sequence + phase.remaining.performance;
    body = <>
      <p className="recovery-prompt-notice" role="status">
        {left === 0
          ? (phase.action === "keep"
            ? (total === 1
              ? "The interrupted recording is back in this Project."
              : `The ${total} interrupted recordings are back in this Project.`)
            : (total === 1
              ? "The interrupted recording was discarded."
              : `The ${total} interrupted recordings were discarded.`))
          : `Some of it could not be ${phase.action === "keep" ? "kept" : "discarded"} here
            (${describe(phase.remaining)}). Open it to keep or discard it there.`}
      </p>
      <div className="recovery-prompt-actions">
        {openButtons(phase.remaining)}
        <button type="button" className="touch-control" onClick={onClose}>Close</button>
      </div>
    </>;
  }
  return (
    <section className="recovery-prompt recovery-layout" aria-label="Interrupted recording">
      <header className="recovery-prompt-heading">
        <h2>Recording recovery</h2>
        <span>{phaseLabel}</span>
      </header>
      {body}
    </section>
  );
}
