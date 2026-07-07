import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";

export function StepGrid(_props: { engine: AudioEngine; bundle: PatchBundle<unknown> }) {
  return <div className="step-grid" data-testid="step-grid" />;
}
