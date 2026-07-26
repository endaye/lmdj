import type {
  ChameleonStateInput,
  ChameleonVisualState,
} from "./model";

function state(
  value: Omit<ChameleonVisualState, "playbackRole">,
  input: ChameleonStateInput,
): ChameleonVisualState {
  return {
    ...value,
    playbackRole: input.playbackRole ?? null,
  };
}

export function deriveChameleonVisualState(
  input: ChameleonStateInput,
): ChameleonVisualState {
  if (input.appPhase === "failed") {
    return state({
      phase: "error",
      placement: "dock",
      label: input.errorLabel ?? "Processing failed",
      tone: "danger",
      motion: "recoil",
      event: {
        kind: "error",
        key: input.errorKey ?? "error:unknown",
      },
    }, input);
  }

  if (input.appPhase === "source") {
    const dragReady = input.interaction === "drag-ready";
    return state({
      phase: dragReady ? "drag-ready" : "idle",
      placement: "stage",
      label: dragReady ? "Drop WAV or MP3" : "Ready for a track",
      tone: dragReady ? "active" : "neutral",
      motion: dragReady ? "processing" : "ambient",
      event: null,
    }, input);
  }

  if (input.appPhase === "loaded") {
    if (input.isPlaying) {
      const role = input.playbackRole ?? "mixed";
      return state({
        phase: "playing",
        placement: "dock",
        label: `Playing ${role}`,
        tone: "active",
        motion: "processing",
        event: null,
      }, input);
    }
    const patchId = input.patchId ?? "patch:unknown";
    return state({
      phase: "ready",
      placement: "dock",
      label: "Patch ready",
      tone: "success",
      motion: "celebrate",
      event: { kind: "ready", key: patchId },
    }, input);
  }

  const jobState = input.jobState ?? "preflight";
  if (jobState === "preflight") {
    return state({
      phase: "uploading",
      placement: "dock",
      label: "Uploading source",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  if (jobState === "queued") {
    return state({
      phase: "queued",
      placement: "dock",
      label: input.queuePosition == null
        ? "Queued"
        : `Queued · position ${input.queuePosition}`,
      tone: "active",
      motion: "ambient",
      event: null,
    }, input);
  }
  if (jobState === "separating") {
    return state({
      phase: "separating",
      placement: "dock",
      label: "Separating stems",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  if (jobState === "extracting") {
    return state({
      phase: "extracting",
      placement: "dock",
      label: "Extracting materials",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  if (jobState === "patchifying") {
    return state({
      phase: "patchifying",
      placement: "dock",
      label: "Building 16-pad Patch",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  return state({
    phase: "patchifying",
    placement: "dock",
    label: `Processing · ${jobState}`,
    tone: "active",
    motion: "processing",
    event: null,
  }, input);
}
