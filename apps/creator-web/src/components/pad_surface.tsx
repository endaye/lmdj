import type {SeedSlot} from "../state/default_seed";
import {DEFAULT_KEYBOARD_MAPPING} from "@lmdj/web-runtime-platform/input_adapters.mjs";

import {
  selectCanStartGesture,
  selectVisiblePads,
  type CreatorState,
} from "../state/creator_state";
import {padColourAttribute} from "../state/pad_colour";
import {padAddress} from "../state/view_model";
import type {createCreatorInputController} from "../runtime/input_controller";

interface PadSurfaceProps {
  state: CreatorState;
  seedSlots?: readonly SeedSlot[];
  emptyPadCapture?: boolean;
  controller?: ReturnType<typeof createCreatorInputController>;
  armedCaptureSlot?: number | null;
  currentSlot?: number;
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
  state, seedSlots, emptyPadCapture = false, controller, armedCaptureSlot = null, currentSlot, onSelectSample, onChooseSample, onDropSample,
}: PadSurfaceProps) {
  const canTrigger = selectCanStartGesture(state);
  return (
    <div className="pad-grid" aria-label="Playable Pads">
      {selectVisiblePads(state).map((pad) => {
        const address = padAddress(pad);
        const selected = state.sample.selectedSlot === pad.slot;
        const highlighted = currentSlot === pad.slot || (onSelectSample !== undefined && selected);
        const assigned = pad.assetId !== null || (onSelectSample !== undefined &&
          selected && state.sample.inspect?.assetId != null);
        const seedPhase = pad.slot < 16 ? seedSlots?.[pad.slot]?.phase : undefined;
        const blocked = seedPhase !== undefined && !["ready", "retired"].includes(seedPhase);
        const status = blocked ? seedPhase === "processing" ? "Processing" :
          seedPhase === "failed" || seedPhase === "saved-unavailable" ? "Failed" : "Loading" : null;
        const capturing = armedCaptureSlot === pad.slot;
        const outcome = state.pressed.get(pad.slot);
        const keyboardKey = KEYBOARD_KEY_BY_LOCAL_PAD.get(pad.slot % 16) ?? "—";
        return (
          <button
            type="button"
            className={`pad${highlighted ? " is-selected" : ""}`}
            aria-current={currentSlot === pad.slot ? "true" : undefined}
            aria-pressed={onSelectSample === undefined ? undefined : selected}
            // One effective colour from Project Truth (#1207); null is the
            // neutral EMPTY outline. Selection is drawn separately (white
            // border + lime dot) so a BASS Pad never reads as selected.
            data-pad-colour={padColourAttribute(pad.colour)}
            data-assigned={assigned ? "true" : "false"}
            data-outcome={outcome ?? "idle"}
            disabled={blocked || (onSelectSample !== undefined
              ? state.project.phase !== "ready" || state.project.current === null
              : (!assigned && !capturing && !emptyPadCapture) || !canTrigger)}
            aria-label={`Pad ${address} — ${status?.toLowerCase() ?? (capturing ? "capturing" : assigned ? "assigned" : "empty")} — Key ${keyboardKey}`}
            key={pad.slot}
            onPointerDown={(event) => controller?.pointerDown(event, pad.slot)}
            onMouseDown={(event) => controller?.pointerDown(event, pad.slot)}
            onPointerUp={(event) => controller?.pointerUp(event, pad.slot)}
            onMouseUp={(event) => controller?.pointerUp(event, pad.slot)}
            onPointerCancel={(event) => controller?.pointerCancel(event, pad.slot)}
            onClick={(event) => {
              if (armedCaptureSlot !== null) return;
              onSelectSample?.(pad.slot);
              if (!assigned && !emptyPadCapture && (controller === undefined || event.detail === 0)) {
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
              if ((!assigned && !capturing && !emptyPadCapture) || controller === undefined ||
                (event.key !== "Enter" && event.key !== " ")) return;
              event.preventDefault();
              if (event.repeat) return;
              const code = KEYBOARD_CODE_BY_LOCAL_PAD.get(
                pad.slot - state.activeBank * 16,
              );
              if (code !== undefined) {
                controller.keyDown({code, repeat: false, target: document.body,
                  nativeEvent: event.nativeEvent});
              }
            }}
            onKeyUp={(event) => {
              if ((!assigned && !capturing && !emptyPadCapture) || controller === undefined ||
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
            <span>{status ?? (capturing ? "Capturing" : assigned ? "Assigned" : "Empty")}</span>
            <kbd aria-hidden="true">{keyboardKey}</kbd>
            {highlighted ? (
              <i className="pad-selected-dot" data-testid="pad-selected-dot" aria-hidden="true" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
