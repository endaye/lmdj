export type ChameleonPhase =
  | "idle"
  | "drag-ready"
  | "uploading"
  | "queued"
  | "separating"
  | "extracting"
  | "patchifying"
  | "ready"
  | "playing"
  | "error";

export type ChameleonPlacement = "stage" | "dock" | "floating";
export type ChameleonTone = "neutral" | "active" | "success" | "danger";
export type ChameleonMotion =
  | "still"
  | "ambient"
  | "processing"
  | "celebrate"
  | "recoil";
export type ChameleonPlaybackRole =
  | "drums"
  | "bass"
  | "harmony"
  | "lead"
  | "loop"
  | "action"
  | "mixed"
  | null;

export interface ChameleonEvent {
  kind: "ready" | "error";
  key: string;
}

export interface ChameleonVisualState {
  phase: ChameleonPhase;
  placement: ChameleonPlacement;
  label: string;
  tone: ChameleonTone;
  motion: ChameleonMotion;
  playbackRole: ChameleonPlaybackRole;
  event: ChameleonEvent | null;
}

export interface ChameleonStateInput {
  appPhase: "source" | "processing" | "failed" | "loaded";
  jobState?: string | null;
  queuePosition?: number | null;
  patchId?: string | null;
  errorKey?: string | null;
  errorLabel?: string | null;
  isPlaying?: boolean;
  playbackRole?: ChameleonPlaybackRole;
  interaction?: "none" | "drag-ready";
}

export interface ChameleonVisualSignature {
  seed: number;
  angle: number;
  offset: number;
  density: number;
  accent:
    | "neutral"
    | "drums"
    | "bass"
    | "harmony"
    | "lead"
    | "loop"
    | "action"
    | "mixed"
    | "success"
    | "danger";
}
