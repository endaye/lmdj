import type { CSSProperties } from "react";
import {
  createVisualSignature,
  type ProjectVisualPhase,
} from "./visualSignature";

export type ProjectSignatureVariant = "band" | "stage" | "stamp";

const PHASE_CELLS: Record<ProjectVisualPhase, number> = {
  idle: 0,
  preflight: 1,
  queued: 1,
  separating: 2,
  extracting: 3,
  patchifying: 4,
  processing: 3,
  ready: 6,
  review: 5,
  error: 2,
};

export function ProjectSignature({
  seed,
  phase,
  variant,
  testId,
}: {
  seed: string;
  phase: ProjectVisualPhase;
  variant: ProjectSignatureVariant;
  testId?: string;
}) {
  const signature = createVisualSignature(seed);
  const style = {
    "--signature-angle": `${signature.angle}deg`,
    "--signature-offset": `${signature.offset}%`,
    "--signature-density": String(signature.density),
    "--signature-phase": `${signature.phase}%`,
  } as CSSProperties;

  return (
    <div
      className="project-signature"
      data-testid={testId}
      data-signature={signature.id}
      data-shape={signature.shape}
      data-phase={phase}
      data-variant={variant}
      aria-hidden="true"
      style={style}
    >
      <span className="project-signature__grid">
        {Array.from({ length: 6 }, (_, index) => (
          <i key={index} data-active={String(index < PHASE_CELLS[phase])} />
        ))}
      </span>
      <span className="project-signature__motif" data-shape={signature.shape} />
    </div>
  );
}
