import { describe, expect, it } from "vitest";
import golden from "./__fixtures__/patch.golden.json";
import { loadPatch, PatchValidationError, padElementIds, scenePatterns, type Patch } from "./loader";

const enc = (data: unknown) => new TextEncoder().encode(JSON.stringify(data)).buffer as ArrayBuffer;
const fakeDecode = async (data: ArrayBuffer) => ({ decodedBytes: data.byteLength });

/** golden patch + 每个 element 一份占位 wav 字节 */
function goldenFiles(patch: unknown = golden): Map<string, ArrayBuffer> {
  const files = new Map<string, ArrayBuffer>([["patch.json", enc(patch)]]);
  for (const el of (patch as Patch).elements) {
    files.set(el.source_path, new ArrayBuffer(8));
  }
  return files;
}

describe("loadPatch", () => {
  it("loads the golden patch with all elements playable", async () => {
    const bundle = await loadPatch(goldenFiles(), fakeDecode);

    expect(bundle.patch.schema).toBe("lmdj.patch.v1");
    expect(bundle.playableElementIds.size).toBe(bundle.patch.elements.length);
    expect(bundle.missingElementIds.size).toBe(0);
    expect(bundle.warnings).toEqual([]);
    expect(bundle.buffers.size).toBe(bundle.patch.elements.length);
  });

  it("rejects a directory without patch.json", async () => {
    await expect(loadPatch(new Map(), fakeDecode)).rejects.toThrow(PatchValidationError);
  });

  it("rejects schema-invalid patch.json with issue paths", async () => {
    const broken = structuredClone(golden) as Patch;
    (broken.pads[0] as { action: string }).action = "definitely_not_an_action";
    const err = await loadPatch(goldenFiles(broken), fakeDecode).catch((e) => e);

    expect(err).toBeInstanceOf(PatchValidationError);
    expect((err as PatchValidationError).issues.join("\n")).toContain("/pads/0/action");
  });

  it("marks missing wav as missing element without blocking the patch", async () => {
    const files = goldenFiles();
    const first = (golden as Patch).elements[0];
    files.delete(first.source_path);

    const bundle = await loadPatch(files, fakeDecode);
    expect(bundle.missingElementIds.has(first.element_id)).toBe(true);
    expect(bundle.playableElementIds.has(first.element_id)).toBe(false);
    expect(bundle.warnings.some((w) => w.includes(first.source_path))).toBe(true);
    // note 数据不预过滤
    expect(bundle.patch.patterns[0].notes.length).toBe((golden as Patch).patterns[0].notes.length);
  });

  it("marks undecodable wav as missing element", async () => {
    const failing = async () => {
      throw new Error("decode failed");
    };
    const bundle = await loadPatch(goldenFiles(), failing);
    expect(bundle.missingElementIds.size).toBe((golden as Patch).elements.length);
  });

  it("rejects a scene referencing an unknown pattern", async () => {
    const broken = structuredClone(golden) as Patch;
    broken.scenes[0].pattern_ids = ["pattern_ghost"];
    await expect(loadPatch(goldenFiles(broken), fakeDecode)).rejects.toThrow(/pattern_ghost/);
  });
});

describe("scenePatterns", () => {
  it("resolves patterns via activeScene.pattern_ids, not patterns[0]", () => {
    const patch = structuredClone(golden) as Patch;
    const real = structuredClone(patch.patterns[0]);
    real.pattern_id = "pattern_real";
    const decoy = structuredClone(patch.patterns[0]);
    decoy.pattern_id = "pattern_decoy";
    decoy.notes = [];
    patch.patterns = [decoy, real]; // decoy 在前
    patch.scenes[0].pattern_ids = ["pattern_real"];

    const resolved = scenePatterns(patch);
    expect(resolved.map((p) => p.pattern_id)).toEqual(["pattern_real"]);
    expect(resolved[0].notes.length).toBeGreaterThan(0);
  });
});

describe("padElementIds", () => {
  it("returns the full group for trigger_group pads", () => {
    const drums = (golden as Patch).pads[0];
    expect(padElementIds(drums)).toEqual(
      (drums.behavior as { element_ids: string[] }).element_ids,
    );
    expect(padElementIds(drums).length).toBeGreaterThan(1);
  });

  it("returns [] for empty/reserved pads", () => {
    const patch = golden as Patch;
    const reserved = patch.pads.find((p) => p.action === "scene_fill")!;
    expect(padElementIds(reserved)).toEqual([]);
  });
});
