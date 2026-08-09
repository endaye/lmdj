import {
  selectCanTrigger,
  selectVisiblePads,
  type CreatorState,
} from "../state/creator_state";
import {padAddress} from "../state/view_model";
import type {createCreatorInputController} from "../runtime/input_controller";

interface PadSurfaceProps {
  state: CreatorState;
  controller?: ReturnType<typeof createCreatorInputController>;
}

export function PadSurface({state, controller}: PadSurfaceProps) {
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
            onPointerDown={(event) => controller?.pointerDown(event, pad.slot)}
            onMouseDown={(event) => controller?.pointerDown(event, pad.slot)}
            onPointerUp={(event) => controller?.pointerUp(event, pad.slot)}
            onMouseUp={(event) => controller?.pointerUp(event, pad.slot)}
            onPointerCancel={(event) => controller?.pointerCancel(event, pad.slot)}
          >
            <strong>{address}</strong>
            <span>{assigned ? "Assigned" : "Empty"}</span>
          </button>
        );
      })}
    </div>
  );
}
