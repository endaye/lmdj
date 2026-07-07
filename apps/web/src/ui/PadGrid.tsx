import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";

export const PAD_KEYS = ["A", "S", "D", "F", "Z", "X", "C", "V"];

export function PadGrid(_props: { engine: AudioEngine; bundle: PatchBundle<unknown> }) {
  return <div className="pad-grid" data-testid="pad-grid" />;
}
