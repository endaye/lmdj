import {COMMIT_MAX_FRAMES} from "../capture/capture_buffer";

export type CapturePhase =
  "idle" | "requesting-permission" | "permission-error" |
  "recording" | "trimming" | "committing" | "commit-error";
export type CaptureStopReason =
  "user" | "capacity" | "blur" | "hidden" | "device-lost" | "permission-revoked";

export interface CaptureState {
  phase: CapturePhase;
  stopReason: CaptureStopReason | null;
  frameCount: number;
  peak: number;
  selectionStart: number;
  selectionFrames: number;
  errorMessage: string | null;
  conflict: boolean;
}

export const CAPTURE_DEVICE_LOST_MESSAGE =
  "Recording stopped: the input device became unavailable";
export const CAPTURE_PERMISSION_REVOKED_MESSAGE =
  "Recording stopped: microphone permission was revoked";

export const initialCaptureState: CaptureState = Object.freeze({
  phase: "idle", stopReason: null, frameCount: 0, peak: 0,
  selectionStart: 0, selectionFrames: 0, errorMessage: null, conflict: false,
});

export type CaptureEvent =
  | {kind: "record"} | {kind: "granted"} | {kind: "denied"; message: string}
  | {kind: "frames"; frames: number; peak: number}
  | {kind: "stop"; reason: CaptureStopReason}
  | {kind: "select"; start: number; frames: number}
  | {kind: "discard"} | {kind: "commit"} | {kind: "committed"}
  | {kind: "commit-failed"; message: string; conflict: boolean};

export function reduceCapture(state: CaptureState, event: CaptureEvent): CaptureState {
  switch (event.kind) {
    case "record":
      return state.phase === "idle" || state.phase === "permission-error"
        ? {...initialCaptureState, phase: "requesting-permission"} : state;
    case "granted":
      return state.phase === "requesting-permission" ? {...state, phase: "recording"} : state;
    case "denied":
      return state.phase === "requesting-permission"
        ? {...state, phase: "permission-error", errorMessage: event.message} : state;
    case "frames":
      return state.phase === "recording"
        ? {...state, frameCount: event.frames, peak: event.peak} : state;
    case "stop": {
      if (state.phase !== "recording") { return state; }
      if (state.frameCount > 0) {
        return {...state, phase: "trimming", stopReason: event.reason, peak: 0,
                selectionStart: 0,
                selectionFrames: Math.min(state.frameCount, COMMIT_MAX_FRAMES)};
      }
      // Nothing captured yet (interrupted before the first batch landed), so
      // there is nothing to trim. A failure reason must still reach the user;
      // a benign reason just returns to idle (S8B-D5 as amended).
      return event.reason === "device-lost" || event.reason === "permission-revoked"
        ? {...initialCaptureState, phase: "permission-error",
           stopReason: event.reason,
           errorMessage: event.reason === "device-lost"
             ? CAPTURE_DEVICE_LOST_MESSAGE
             : CAPTURE_PERMISSION_REVOKED_MESSAGE}
        : initialCaptureState;
    }
    case "select":
      return (state.phase === "trimming" || state.phase === "commit-error") &&
             Number.isInteger(event.start) && Number.isInteger(event.frames) &&
             event.start >= 0 && event.frames > 0 &&
             event.frames <= COMMIT_MAX_FRAMES &&
             event.start + event.frames <= state.frameCount
        ? {...state, phase: "trimming", selectionStart: event.start,
           selectionFrames: event.frames, errorMessage: null, conflict: false}
        : state;
    case "discard":
      return state.phase === "trimming" || state.phase === "commit-error"
        ? initialCaptureState : state;
    case "commit":
      return (state.phase === "trimming" || state.phase === "commit-error") &&
             state.selectionFrames > 0
        ? {...state, phase: "committing", errorMessage: null, conflict: false} : state;
    case "committed":
      return state.phase === "committing" ? initialCaptureState : state;
    case "commit-failed":
      return state.phase === "committing"
        ? {...state, phase: "commit-error", errorMessage: event.message,
           conflict: event.conflict}
        : state;
  }
}
