import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { AudioEngine } from "../engine/AudioEngine";
import { scenePatterns, type Patch, type PatchBundle } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
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

  it("renders bar and beat hierarchy across the complete pattern", () => {
    const bundle = makeBundle();
    renderGrid(bundle);

    expect(
      screen.getByRole("table", { name: "Pattern Original step grid" }),
    ).toHaveAccessibleName("Pattern Original step grid");
    const bars = screen.getAllByTestId(/^step-bar-/);
    expect(bars).toHaveLength(4);
    expect(bars.map((bar) => bar.textContent)).toEqual(["Bar 1", "Bar 2", "Bar 3", "Bar 4"]);
    expect(bars.every((bar) => bar.getAttribute("colspan") === "16")).toBe(true);

    const firstRow = screen.getByTestId(`step-row-${bundle.patch.patterns[0].notes[0].element_id}`);
    const cells = within(firstRow).getAllByRole("cell");
    expect(cells[0]).toHaveClass("step-bar-start");
    expect(cells[4]).toHaveClass("step-beat-start");
    expect(cells[16]).toHaveClass("step-bar-start");
  });

  it("keeps the final partial bar aligned with the remaining steps", () => {
    const bundle = makeBundle((b) => {
      b.patch.patterns[0].length_steps = 18;
      b.patch.patterns[0].notes = b.patch.patterns[0].notes.filter((note) => note.step < 18);
    });
    renderGrid(bundle);

    const bars = screen.getAllByTestId(/^step-bar-/);
    expect(bars).toHaveLength(2);
    expect(bars[0]).toHaveAttribute("colspan", "16");
    expect(bars[1]).toHaveAttribute("colspan", "2");
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
