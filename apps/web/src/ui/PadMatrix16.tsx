import type { AudioEngine } from "../engine/AudioEngine";
import { padElementIds, type Pad, type PatchBundle } from "../patch/loader";
import { PadButton, type PadVisualState } from "./PadButton";
import { useEngineTick } from "./useEngine";

export const PAD_KEYS = [
  "1", "2", "3", "4", "5", "6", "7", "8",
  "Q", "W", "E", "R", "T", "Y", "U", "I",
] as const;
export const PAD_KEY_HINTS = PAD_KEYS;

function staticState(
  pad: Pad,
  bundle: PatchBundle<unknown>,
  engine: AudioEngine,
  selectedPadIndex: number | undefined,
): PadVisualState {
  const ids = padElementIds(pad);
  if (ids.some((id) => bundle.missingElementIds.has(id))) return "missing";
  if (engine.isPadMuted(pad.index)) return "muted";
  if (engine.isPadLooping(pad.index)) return "playing";
  if (pad.index === selectedPadIndex) return "selected";
  if (pad.action === "empty") return "empty";
  if (ids.length === 0) return "reserved";
  return "idle";
}

export function PadMatrix16({
  bundle,
  engine,
  selectedPadIndex,
  pressedPadIndices,
  onSelect,
  onPress,
  onRelease,
}: {
  bundle: PatchBundle<unknown>;
  engine: AudioEngine;
  selectedPadIndex: number | undefined;
  pressedPadIndices: ReadonlySet<number>;
  onSelect: (index: number) => void;
  onPress: (index: number) => void;
  onRelease: (index: number) => void;
}) {
  useEngineTick(engine);

  return (
    <div
      className="pad-matrix"
      data-testid="pad-matrix"
      aria-label="16 Pad instrument"
    >
      {bundle.patch.pads.map((pad) => {
        const state = staticState(pad, bundle, engine, selectedPadIndex);
        const ids = padElementIds(pad);
        const interactive = ids.length > 0;
        const pressed = state !== "missing"
          && pressedPadIndices.has(pad.index)
          && ids.some((id) => bundle.playableElementIds.has(id));
        const visualState = pressed ? "playing" : state;
        return (
          <PadButton
            key={pad.index}
            pad={pad}
            visualState={visualState}
            pressed={pressed}
            keyHint={PAD_KEYS[pad.index]}
            onSelect={onSelect}
            onPress={interactive ? onPress : undefined}
            onRelease={interactive ? onRelease : undefined}
            onToggleMute={interactive ? () => engine.toggleMutePad(pad.index) : undefined}
          />
        );
      })}
    </div>
  );
}
