import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";
import { useEngineTick } from "./useEngine";

export function Transport({
  engine,
  bundle,
}: {
  engine: AudioEngine;
  bundle: PatchBundle<unknown>;
}) {
  useEngineTick(engine);
  return (
    <div className="transport">
      <button
        data-testid="play-toggle"
        onClick={() => (engine.playing ? engine.stop() : void engine.play())}
      >
        {engine.playing ? "■" : "▶"}
      </button>
      <span>BPM {bundle.patch.bpm}</span>
      <span>loop {bundle.patch.loop_seconds}s</span>
      <span>patch: {bundle.patch.patch_id}</span>
    </div>
  );
}
