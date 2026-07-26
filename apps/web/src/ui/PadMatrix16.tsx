import { useEffect, useRef, useState } from "react";
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
  onSelect,
}: {
  bundle: PatchBundle<unknown>;
  engine: AudioEngine;
  selectedPadIndex: number | undefined;
  onSelect: (index: number) => void;
}) {
  useEngineTick(engine);
  const [playingPadIndex, setPlayingPadIndex] = useState<number>();
  const resetTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  const trigger = (pad: Pad) => {
    const ids = padElementIds(pad);
    if (ids.length === 0) return;
    engine.triggerPad(pad.index);
    if (!ids.some((id) => bundle.playableElementIds.has(id))) return;
    if (pad.behavior.trigger === "loop") return;
    if (resetTimer.current) clearTimeout(resetTimer.current);
    setPlayingPadIndex(pad.index);
    resetTimer.current = setTimeout(() => setPlayingPadIndex(undefined), 120);
  };

  return (
    <div
      className="pad-matrix"
      data-testid="pad-matrix"
      aria-label="16 Pad instrument"
    >
      {bundle.patch.pads.map((pad) => {
        const state = staticState(pad, bundle, engine, selectedPadIndex);
        const visualState = state === "missing" || playingPadIndex !== pad.index
          ? state
          : "playing";
        const interactive = padElementIds(pad).length > 0;
        return (
          <PadButton
            key={pad.index}
            pad={pad}
            visualState={visualState}
            keyHint={PAD_KEYS[pad.index]}
            onSelect={onSelect}
            onTrigger={interactive ? () => trigger(pad) : undefined}
            onToggleMute={interactive ? () => engine.toggleMutePad(pad.index) : undefined}
          />
        );
      })}
    </div>
  );
}
