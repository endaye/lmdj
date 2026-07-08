import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { AudioEngine } from "../engine/AudioEngine";
import { scenePatterns, type Patch, type PatchBundle } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { Inspector } from "./Inspector";
import { StepGrid } from "./StepGrid";

function makeBundle(mutate?: (b: PatchBundle<unknown>) => void): PatchBundle<unknown> {
  const patch = structuredClone(golden) as unknown as Patch;
  const bundle: PatchBundle<unknown> = {
    patch,
    buffers: new Map(patch.elements.map((e) => [e.element_id, {}])),
    playableElementIds: new Set(patch.elements.map((e) => e.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
  mutate?.(bundle);
  return bundle;
}

function renderGrid(bundle: PatchBundle<unknown>) {
  const engine = new AudioEngine(new FakeAudioContext());
  engine.load(bundle);
  render(<StepGrid engine={engine} bundle={bundle} />);
  return engine;
}

describe("StepGrid", () => {
  it("renders one row per element with notes, cells matching the pattern", () => {
    const bundle = makeBundle();
    renderGrid(bundle);
    const pattern = scenePatterns(bundle.patch)[0];
    const elementIds = new Set(pattern.notes.map((n) => n.element_id));
    expect(elementIds.size).toBeGreaterThan(0);
    for (const id of elementIds) {
      const row = screen.getByTestId(`step-row-${id}`);
      const filled = row.textContent?.match(/█/g)?.length ?? 0;
      const steps = new Set(
        pattern.notes.filter((n) => n.element_id === id).map((n) => n.step),
      );
      expect(filled).toBe(steps.size);
    }
  });

  it("marks rows of missing elements", () => {
    const bundle = makeBundle((b) => {
      const first = b.patch.patterns[0].notes[0].element_id;
      b.missingElementIds.add(first);
    });
    renderGrid(bundle);
    const first = bundle.patch.patterns[0].notes[0].element_id;
    expect(screen.getByTestId(`step-row-${first}`)).toHaveClass("step-missing");
  });
});

describe("Inspector", () => {
  it("shows patch facts, score, and unmapped/warnings", () => {
    const bundle = makeBundle((b) => {
      b.warnings.push("missing sample file: samples/ghost.wav (el_ghost)");
      (b.patch.metadata as Record<string, unknown>).unmapped_element_ids = ["el_orphan"];
    });
    render(<Inspector bundle={bundle} />);

    expect(screen.getByTestId("inspector")).toHaveTextContent(bundle.patch.patch_id);
    expect(screen.getByTestId("inspector")).toHaveTextContent("el_orphan");
    expect(screen.getByTestId("inspector")).toHaveTextContent("ghost.wav");
    for (const el of bundle.patch.elements) {
      expect(screen.getByTestId("inspector")).toHaveTextContent(el.name);
    }
  });
});
