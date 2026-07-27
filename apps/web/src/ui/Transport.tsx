import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";
import { useEngineTick } from "./useEngine";

const COMPACT_NUMBER = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  useGrouping: false,
});

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
        aria-label={engine.playing ? "Stop Pattern" : "Play Pattern"}
        onClick={() => (engine.playing ? engine.stop() : void engine.play())}
      >
        {engine.playing ? "■" : "▶"}
      </button>
      <div className="transport-metrics">
        <span
          className="transport-readout"
          title={`BPM ${bundle.patch.bpm}`}
        >
          <span>BPM</span>
          <b data-testid="transport-bpm">
            {COMPACT_NUMBER.format(bundle.patch.bpm)}
          </b>
        </span>
        <span
          className="transport-readout"
          title={`Loop ${bundle.patch.loop_seconds} seconds`}
        >
          <span>Loop</span>
          <b data-testid="transport-loop">
            {COMPACT_NUMBER.format(bundle.patch.loop_seconds)}s
          </b>
        </span>
      </div>
      <div
        className="transport-source"
        data-testid="transport-source"
        title={bundle.patch.patch_id}
        tabIndex={0}
        aria-label="Patch source identifier"
      >
        <span>Source</span>
        <code>{bundle.patch.patch_id}</code>
      </div>
    </div>
  );
}
