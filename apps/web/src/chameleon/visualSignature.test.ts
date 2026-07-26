import { describe, expect, it } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { createVisualSignature } from "./visualSignature";

describe("createVisualSignature", () => {
  const ready = deriveChameleonVisualState({
    appPhase: "loaded",
    patchId: "patch-a",
  });

  it("is deterministic for the same public seed and state", () => {
    expect(createVisualSignature("patch-a", ready)).toEqual(
      createVisualSignature("patch-a", ready),
    );
  });

  it("changes when the public Patch identity changes", () => {
    expect(createVisualSignature("patch-a", ready)).not.toEqual(
      createVisualSignature("patch-b", ready),
    );
  });

  it("uses semantic accents rather than private pipeline data", () => {
    expect(createVisualSignature("patch-a", ready).accent).toBe("success");
    const playing = deriveChameleonVisualState({
      appPhase: "loaded",
      patchId: "patch-a",
      isPlaying: true,
      playbackRole: "drums",
    });
    expect(createVisualSignature("patch-a", playing).accent).toBe("drums");
  });
});
