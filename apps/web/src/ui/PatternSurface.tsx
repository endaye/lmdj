import type { AudioEngine } from "../engine/AudioEngine";
import { scenePatterns, type PatchBundle } from "../patch/loader";
import { StepGrid } from "./StepGrid";
import { Transport } from "./Transport";

export function PatternSurface({
  bundle,
  engine,
  playheadStep,
}: {
  bundle: PatchBundle<unknown>;
  engine: AudioEngine;
  playheadStep: number | null;
}) {
  const pattern = scenePatterns(bundle.patch)[0];

  return (
    <section className="pattern-surface" data-testid="pattern-surface">
      <div className="pattern-surface__header">
        <div>
          <span className="pattern-surface__eyebrow">Pattern</span>
          <h2>{pattern?.name ?? "Pattern unavailable"}</h2>
        </div>
        <span className="pattern-playhead" data-testid="pattern-playhead">
          {pattern && playheadStep !== null
            ? `Step ${String(playheadStep + 1).padStart(2, "0")} / ${pattern.length_steps}`
            : "Stopped"}
        </span>
      </div>
      <Transport engine={engine} bundle={bundle} />
      {pattern ? (
        <>
          <div className="pattern-summary" data-testid="pattern-summary">
            <span>{pattern.name}</span>
            <span>{pattern.resolution}</span>
            <span>{pattern.length_steps} steps</span>
            <span>{pattern.notes.length} notes</span>
          </div>
          <StepGrid engine={engine} bundle={bundle} />
        </>
      ) : (
        <div className="pattern-empty" data-testid="pattern-empty" role="status">
          No active pattern · load or map a Pattern to this Scene.
        </div>
      )}
    </section>
  );
}
