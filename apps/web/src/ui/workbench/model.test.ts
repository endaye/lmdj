import { describe, expect, it } from "vitest";
import golden from "../../patch/__fixtures__/patch.golden.json";
import type { Patch, PatchBundle } from "../../patch/loader";
import { buildWorkbenchViewModel } from "./model";

function bundle(overrides: Partial<PatchBundle<unknown>> = {}): PatchBundle<unknown> {
  const patch = structuredClone(golden) as unknown as Patch;
  return {
    patch,
    buffers: new Map(),
    playableElementIds: new Set(),
    missingElementIds: new Set(),
    warnings: [],
    ...overrides,
  };
}

describe("buildWorkbenchViewModel", () => {
  it("projects the loaded patch into the fixed sixteen-pad workbench", () => {
    const source = bundle();

    const model = buildWorkbenchViewModel(source, 3);

    expect(model.padCount).toBe(16);
    expect(model.selectedPad?.index).toBe(3);
    expect(model.durationSeconds).toBe(source.patch.loop_seconds);
    expect(model.key).toBeNull();
    expect(model.readiness).toBe("ready");
    expect(model.blockers).toEqual([]);
    expect(model.schema).toBe(source.patch.schema);
    expect(model.quality).toEqual({ status: "passed", score: 0.6556 });
    expect(model.elements).toHaveLength(source.patch.elements.length);
  });

  it("marks missing audio and decoder warnings for review", () => {
    const model = buildWorkbenchViewModel(bundle({
      missingElementIds: new Set(["kick", "bass"]),
      warnings: ["failed to decode: samples/kick.wav (kick)"],
    }));

    expect(model.readiness).toBe("needs-review");
    expect(model.blockers).toHaveLength(3);
    expect(model.blockers).toContain("missing audio: kick");
    expect(model.blockers).toContain("missing audio: bass");
  });

  it("surfaces partial export blockers ahead of an otherwise ready patch", () => {
    const model = buildWorkbenchViewModel(bundle(), undefined, {
      status: "partial",
      missing: ["render.wav"],
      key: "C minor",
    });

    expect(model.key).toBe("C minor");
    expect(model.readiness).toBe("partial");
    expect(model.blockers).toEqual(["export missing: render.wav"]);
  });

  it("leaves the selected pad undefined for an invalid pad index", () => {
    expect(buildWorkbenchViewModel(bundle(), 99).selectedPad).toBeUndefined();
  });

  it("projects unmapped ids, warnings, and source availability for inspection", () => {
    const source = bundle();
    const missingId = source.patch.pads[2].element_id!;
    source.missingElementIds.add(missingId);
    source.warnings.push("decoder failed");
    (source.patch.metadata as Record<string, unknown>).unmapped_element_ids = ["el_orphan"];

    const model = buildWorkbenchViewModel(source, 2);

    expect(model.unmappedElementIds).toEqual(["el_orphan"]);
    expect(model.warnings).toEqual(["decoder failed"]);
    expect(model.selectedPadSources).toEqual([
      expect.objectContaining({ elementId: missingId, status: "missing" }),
    ]);
  });
});
