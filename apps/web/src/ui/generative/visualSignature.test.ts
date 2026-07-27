import { describe, expect, it } from "vitest";
import golden from "../../patch/__fixtures__/patch.golden.json";
import type { Pad } from "../../patch/loader";
import {
  createVisualSignature,
  projectVisualPhase,
  roleForPad,
} from "./visualSignature";

describe("createVisualSignature", () => {
  it("is stable and versionable for the same public seed", () => {
    expect(createVisualSignature("submission-a")).toEqual({
      id: "wave-173-71-6-84",
      shape: "wave",
      angle: 173,
      offset: 71,
      density: 6,
      phase: 84,
    });
    expect(createVisualSignature("submission-a")).toEqual(
      createVisualSignature("submission-a"),
    );
  });

  it("changes for a different public seed", () => {
    expect(createVisualSignature("submission-b").id).toBe(
      "slice-94-42-2-85",
    );
    expect(createVisualSignature("submission-b")).not.toEqual(
      createVisualSignature("submission-a"),
    );
  });
});

describe("roleForPad", () => {
  const pads = structuredClone(golden.pads) as unknown as Pad[];

  it("preserves the current role mapping while the signature moves modules", () => {
    expect(pads.slice(0, 5).map(roleForPad)).toEqual([
      "drums",
      "bass",
      "harmony",
      "empty",
      "action",
    ]);
  });
});

describe("projectVisualPhase", () => {
  it.each([
    [undefined, false, "idle"],
    ["preflight", false, "preflight"],
    ["queued", false, "queued"],
    ["separating", false, "separating"],
    ["extracting", false, "extracting"],
    ["patchifying", false, "patchifying"],
    ["completed", false, "ready"],
    ["interrupted", false, "review"],
    ["failed", false, "error"],
    ["spectralizing", false, "processing"],
    [undefined, true, "error"],
  ] as const)("maps %s / failed=%s to %s", (state, failed, phase) => {
    expect(projectVisualPhase(state, failed)).toBe(phase);
  });
});
