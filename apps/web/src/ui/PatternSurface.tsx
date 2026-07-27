import type { AudioEngine } from "../engine/AudioEngine";
import { scenePatterns, type PatchBundle } from "../patch/loader";
import { StepGrid } from "./StepGrid";
import { Transport } from "./Transport";
import type { WorkbenchReadiness } from "./workbench/model";

export function PatternSurface({
  bundle,
  engine,
  padCount,
  playheadStep,
  readiness,
}: {
  bundle: PatchBundle<unknown>;
  engine: AudioEngine;
  padCount: number;
  playheadStep: number | null;
  readiness: WorkbenchReadiness;
}) {
  const pattern = scenePatterns(bundle.patch)[0];
  const playheadPosition = playheadStep === null
    ? null
    : {
        bar: Math.floor(playheadStep / 16) + 1,
        beat: Math.floor((playheadStep % 16) / 4) + 1,
        step: playheadStep + 1,
      };

  return (
    <section className="pattern-surface" data-testid="pattern-surface">
      <div className="pattern-surface__header">
        <div className="pattern-surface__performance">
          <strong>Performance</strong>
          <small>{padCount} live slots</small>
        </div>
        <span className="workbench-readiness">{readiness}</span>
        <div className="pattern-surface__identity">
          <span className="pattern-surface__eyebrow">Pattern</span>
          <h2>{pattern?.name ?? "Pattern unavailable"}</h2>
          {pattern && (
            <div className="pattern-summary" data-testid="pattern-summary">
              <span>{pattern.resolution}</span>
              <span>{pattern.length_steps} steps</span>
              <span>{pattern.notes.length} notes</span>
            </div>
          )}
        </div>
        <div className="pattern-surface__controls" data-testid="pattern-controls">
          <span
            className={`pattern-playhead${playheadPosition ? " pattern-playhead--running" : ""}`}
            data-testid="pattern-playhead"
          >
            {pattern && playheadPosition
              ? `Bar ${playheadPosition.bar} · Beat ${playheadPosition.beat} · Step ${String(
                  playheadPosition.step,
                ).padStart(2, "0")} / ${pattern.length_steps}`
              : "Stopped"}
          </span>
          <Transport engine={engine} bundle={bundle} />
        </div>
      </div>
      {pattern ? (
        <StepGrid bundle={bundle} playheadStep={playheadStep} />
      ) : (
        <div className="pattern-empty" data-testid="pattern-empty" role="status">
          No active pattern · load or map a Pattern to this Scene.
        </div>
      )}
    </section>
  );
}
