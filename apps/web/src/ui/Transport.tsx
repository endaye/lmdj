import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";

export function Transport({ bundle }: { engine: AudioEngine; bundle: PatchBundle<unknown> }) {
  return (
    <div className="transport">
      <span>BPM {bundle.patch.bpm}</span>
      <span>patch: {bundle.patch.patch_id}</span>
    </div>
  );
}
