import type {TakeoverOutcome} from "../runtime/project_takeover";

// Why a Continue here did not end with this tab holding the Project. A
// released holder can still be followed by a busy open (another tab claimed it
// first, or its writer is still closing), so every outcome has a note.
export function takeoverNote(outcome: TakeoverOutcome): string | null {
  switch (outcome) {
    case "refused":
      return "The other tab is playing, recording or saving. Finish there, then choose Continue here again.";
    case "unanswered":
      return "The other tab did not respond. Switch to it or close it, then try again.";
    case "release-failed":
      return "The other tab did not confirm a clean release. Try again in a moment.";
    case "released":
      return "The other tab let go, but the Project is still busy. Try again in a moment.";
    case "cancelled":
      return null;
  }
}

export function TakeoverPending({onCancel}: {onCancel: () => void}) {
  return (
    <aside className="takeover-panel" role="status">
      <span>Asking the other tab to hand over this Project…</span>
      <button type="button" onClick={onCancel}>Cancel</button>
    </aside>
  );
}

export type ProjectReleaseState = "pending" | "released" | "unconfirmed";

interface TakenOverPanelProps {
  releaseState: ProjectReleaseState;
  note: string | null;
  onContinueHere?: (() => void) | undefined;
}

// Closing admission happens before the original close settles. Even a clean
// release says nothing about whether a requester actually opened the Project.
export function TakenOverPanel({releaseState, note, onContinueHere}: TakenOverPanelProps) {
  const message = releaseState === "pending"
    ? {title: "Releasing Project from this tab",
      detail: "Waiting for this page to finish closing its Project. The next tab may still be waiting."}
    : releaseState === "released"
      ? {title: "Project released from this tab",
        detail: "Changes made here are saved on this device. Choose Continue here to reopen it in this tab."}
      : {title: "Project release could not be confirmed",
        detail: "There is no confirmation that this page released the Project. Continue here can reopen only after release is confirmed."};
  return (
    <aside className="takeover-panel" role={releaseState === "pending" ? "status" : "alert"}>
      <strong>{message.title}</strong>
      <span>{message.detail}</span>
      {note !== null && <span className="takeover-note">{note}</span>}
      {onContinueHere && (
        <button type="button" onClick={onContinueHere}>Continue here</button>
      )}
    </aside>
  );
}
