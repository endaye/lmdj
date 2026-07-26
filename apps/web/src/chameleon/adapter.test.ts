import { describe, expect, it } from "vitest";
import { deriveChameleonVisualState } from "./adapter";

describe("deriveChameleonVisualState", () => {
  it("maps source interaction without inventing progress", () => {
    expect(
      deriveChameleonVisualState({
        appPhase: "source",
        interaction: "drag-ready",
      }),
    ).toMatchObject({
      phase: "drag-ready",
      placement: "stage",
      label: "Drop WAV or MP3",
      event: null,
    });
  });

  it.each([
    ["preflight", "uploading", "Uploading source"],
    ["queued", "queued", "Queued · position 2"],
    ["separating", "separating", "Separating stems"],
    ["extracting", "extracting", "Extracting materials"],
    ["patchifying", "patchifying", "Building 16-pad Patch"],
  ] as const)("maps %s to truthful %s", (jobState, phase, label) => {
    expect(
      deriveChameleonVisualState({
        appPhase: "processing",
        jobState,
        queuePosition: 2,
      }),
    ).toMatchObject({ phase, placement: "dock", label, event: null });
  });

  it("retains an unknown worker state in the visible label", () => {
    const state = deriveChameleonVisualState({
      appPhase: "processing",
      jobState: "spectralizing",
    });
    expect(state.label).toBe("Processing · spectralizing");
    expect(state.label).not.toMatch(/\d+%/);
  });

  it("gives error priority over playback", () => {
    expect(
      deriveChameleonVisualState({
        appPhase: "failed",
        errorKey: "submission-1:separating",
        errorLabel: "Service interrupted",
        isPlaying: true,
      }),
    ).toMatchObject({
      phase: "error",
      tone: "danger",
      label: "Service interrupted",
      event: { kind: "error", key: "submission-1:separating" },
    });
  });

  it("uses a stable Patch identity for ready and actual role for playing", () => {
    expect(
      deriveChameleonVisualState({
        appPhase: "loaded",
        patchId: "source-abc-patch",
      }),
    ).toMatchObject({
      phase: "ready",
      event: { kind: "ready", key: "source-abc-patch" },
    });
    expect(
      deriveChameleonVisualState({
        appPhase: "loaded",
        patchId: "source-abc-patch",
        isPlaying: true,
        playbackRole: "bass",
      }),
    ).toMatchObject({
      phase: "playing",
      label: "Playing bass",
      event: null,
    });
  });
});
