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
  armedCaptureSlot?: number | null;
  onSelectSample?: (slot: number) => void;
  onChooseSample?: (slot: number) => void;
  onDropSample?: (slot: number, file: File, target: HTMLElement) => void;
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

export function PadSurface({
  state, controller, armedCaptureSlot = null, onSelectSample, onChooseSample, onDropSample,
}: PadSurfaceProps) {
  const canTrigger = selectCanTrigger(state);
  return (
    <div className="pad-grid" aria-label="Playable Pads">
      {selectVisiblePads(state).map((pad) => {
        const address = padAddress(pad);
        const selected = state.sample.selectedSlot === pad.slot;
        const assigned = pad.assetId !== null || (onSelectSample !== undefined &&
          selected && state.sample.inspect?.assetId != null);
        const capturing = armedCaptureSlot === pad.slot;
        const outcome = state.pressed.get(pad.slot);
        const keyboardKey = KEYBOARD_KEY_BY_LOCAL_PAD.get(pad.slot % 16) ?? "—";
        return (
          <button
            type="button"
            className={`pad${onSelectSample !== undefined && selected ? " is-selected" : ""}`}
            aria-pressed={onSelectSample === undefined ? undefined : selected}
            data-identity={String(pad.slot % 5)}
            data-assigned={assigned ? "true" : "false"}
            data-outcome={outcome ?? "idle"}
            disabled={onSelectSample !== undefined
              ? state.project.phase !== "ready" || state.project.current === null
              : (!assigned && !capturing) || !canTrigger}
            aria-label={`Pad ${address} — ${capturing ? "capturing" : assigned ? "assigned" : "empty"} — Key ${keyboardKey}`}
            key={pad.slot}
            onPointerDown={(event) => controller?.pointerDown(event, pad.slot)}
            onMouseDown={(event) => controller?.pointerDown(event, pad.slot)}
            onPointerUp={(event) => controller?.pointerUp(event, pad.slot)}
            onMouseUp={(event) => controller?.pointerUp(event, pad.slot)}
            onPointerCancel={(event) => controller?.pointerCancel(event, pad.slot)}
            onClick={(event) => {
              if (armedCaptureSlot !== null) return;
              onSelectSample?.(pad.slot);
              if (!assigned && (controller === undefined || event.detail === 0)) {
                onChooseSample?.(pad.slot);
              }
            }}
            onDragOver={onDropSample === undefined ? undefined : (event) => event.preventDefault()}
            onDrop={onDropSample === undefined ? undefined : (event) => {
              event.preventDefault();
              const file = event.dataTransfer.files[0];
              if (file !== undefined && armedCaptureSlot === null) {
                onDropSample(pad.slot, file, event.currentTarget);
              }
            }}
            onKeyDown={(event) => {
              if ((!assigned && !capturing) || controller === undefined ||
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
              if ((!assigned && !capturing) || controller === undefined ||
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
            <span>{capturing ? "Capturing" : assigned ? "Assigned" : "Empty"}</span>
            <kbd aria-hidden="true">{keyboardKey}</kbd>
          </button>
        );
      })}
    </div>
  );
}
