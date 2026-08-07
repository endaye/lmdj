import {
  selectCanTrigger,
  selectVisiblePads,
  type CreatorState,
} from "../state/creator_state";
import {padAddress} from "../state/view_model";

interface PadSurfaceProps {
  state: CreatorState;
}

export function PadSurface({state}: PadSurfaceProps) {
  const canTrigger = selectCanTrigger(state);
  return (
    <div className="pad-grid" aria-label="Playable Pads">
      {selectVisiblePads(state).map((pad) => {
        const address = padAddress(pad);
        const assigned = pad.assetId !== null;
        const outcome = state.pressed.get(pad.slot);
        return (
          <button
            type="button"
            className="pad"
            data-outcome={outcome ?? "idle"}
            disabled={!assigned || !canTrigger}
            aria-label={`Pad ${address} — ${assigned ? "assigned" : "empty"}`}
            key={pad.slot}
          >
            <strong>{address}</strong>
            <span>{assigned ? "Assigned" : "Empty"}</span>
          </button>
        );
      })}
    </div>
  );
}
