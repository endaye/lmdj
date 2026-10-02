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
      return "The other tab is still closing. Try again in a moment.";
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

interface TakenOverPanelProps {
  note: string | null;
  onContinueHere?: (() => void) | undefined;
}

// This tab released its Project to another tab; its Runtime is closed, so
// nothing here can write until it takes the Project back.
export function TakenOverPanel({note, onContinueHere}: TakenOverPanelProps) {
  return (
    <aside className="takeover-panel" role="alert">
      <strong>Project open in another tab</strong>
      <span>
        Changes made here are saved on this device. Continue here to take the
        Project back.
      </span>
      {note !== null && <span className="takeover-note">{note}</span>}
      {onContinueHere && (
        <button type="button" onClick={onContinueHere}>Continue here</button>
      )}
    </aside>
  );
}
