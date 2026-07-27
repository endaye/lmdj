import type { Pad } from "../../patch/loader";

export type SignatureShape = "circle" | "grid" | "slice" | "wave";
export type VisualRole =
  | "drums"
  | "bass"
  | "harmony"
  | "lead"
  | "action"
  | "empty";

export type ProjectVisualPhase =
  | "idle"
  | "preflight"
  | "queued"
  | "separating"
  | "extracting"
  | "patchifying"
  | "processing"
  | "ready"
  | "review"
  | "error";

export interface VisualSignature {
  id: string;
  shape: SignatureShape;
  angle: number;
  offset: number;
  density: number;
  phase: number;
}

function hashSeed(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function createVisualSignature(seed: string): VisualSignature {
  const hash = hashSeed(seed);
  const shapes = ["circle", "grid", "slice", "wave"] as const;
  const shape = shapes[hash % shapes.length];
  const angle = (hash >>> 4) % 180;
  const offset = 18 + ((hash >>> 12) % 55);
  const density = 2 + ((hash >>> 20) % 5);
  const phase = (hash >>> 24) % 100;
  return {
    id: `${shape}-${angle}-${offset}-${density}-${phase}`,
    shape,
    angle,
    offset,
    density,
    phase,
  };
}

export function roleForPad(
  pad: Pick<Pad, "action" | "index">,
): VisualRole {
  if (pad.action === "empty") return "empty";
  if (pad.index === 0) return "drums";
  if (pad.index === 1) return "bass";
  if (pad.index === 2) return "harmony";
  if (pad.index === 3) return "lead";
  return "action";
}

export function projectVisualPhase(
  state: string | null | undefined,
  failed = false,
): ProjectVisualPhase {
  if (failed || state === "failed") return "error";
  if (!state) return "idle";
  if (state === "preflight") return "preflight";
  if (state === "queued") return "queued";
  if (state === "separating") return "separating";
  if (state === "extracting") return "extracting";
  if (state === "patchifying") return "patchifying";
  if (state === "completed") return "ready";
  if (state === "interrupted" || state === "cancelled") return "review";
  return "processing";
}
