import {DEFAULT_KEYBOARD_MAPPING} from "@lmdj/web-runtime-platform/input_adapters.mjs";

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

const KEYBOARD_CODE_BY_LOCAL_PAD: ReadonlyMap<number, string> = new Map(
  Object.entries(DEFAULT_KEYBOARD_MAPPING).map(([code, localPad]) => [
    localPad,
    code,
  ] as const),
);
const KEYBOARD_KEY_BY_LOCAL_PAD: ReadonlyMap<number, string> = new Map(
  Object.entries(DEFAULT_KEYBOARD_MAPPING).map(([code, localPad]) => [
    localPad,
    code.replace(/^Key/, ""),
  ] as const),
);

export function PadSurface({state, controller}: PadSurfaceProps) {
  const canTrigger = selectCanTrigger(state);
  return (
    <div className="pad-grid" aria-label="Playable Pads">
      {selectVisiblePads(state).map((pad) => {
        const address = padAddress(pad);
        const assigned = pad.assetId !== null;
        const outcome = state.pressed.get(pad.slot);
        const keyboardKey = KEYBOARD_KEY_BY_LOCAL_PAD.get(pad.slot % 16) ?? "—";
        return (
          <button
            type="button"
            className="pad"
            data-outcome={outcome ?? "idle"}
            disabled={!assigned || !canTrigger}
            aria-label={`Pad ${address} — ${assigned ? "assigned" : "empty"} — Key ${keyboardKey}`}
            key={pad.slot}
            onPointerDown={(event) => controller?.pointerDown(event, pad.slot)}
            onMouseDown={(event) => controller?.pointerDown(event, pad.slot)}
            onPointerUp={(event) => controller?.pointerUp(event, pad.slot)}
            onMouseUp={(event) => controller?.pointerUp(event, pad.slot)}
            onPointerCancel={(event) => controller?.pointerCancel(event, pad.slot)}
            onKeyDown={(event) => {
              if (controller === undefined ||
                (event.key !== "Enter" && event.key !== " ")) return;
              event.preventDefault();
              if (event.repeat) return;
              const code = KEYBOARD_CODE_BY_LOCAL_PAD.get(
                pad.slot - state.activeBank * 16,
              );
              if (code !== undefined) {
                controller.keyDown({code, repeat: false, target: document.body});
              }
            }}
            onKeyUp={(event) => {
              if (controller === undefined ||
                (event.key !== "Enter" && event.key !== " ")) return;
              event.preventDefault();
              const code = KEYBOARD_CODE_BY_LOCAL_PAD.get(
                pad.slot - state.activeBank * 16,
              );
              if (code !== undefined) {
                controller.keyUp({code, repeat: false, target: document.body});
              }
            }}
          >
            <strong>{address}</strong>
            <span>{assigned ? "Assigned" : "Empty"}</span>
            <kbd aria-hidden="true">{keyboardKey}</kbd>
          </button>
        );
      })}
    </div>
  );
}
