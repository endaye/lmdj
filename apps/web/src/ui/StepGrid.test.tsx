import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { scenePatterns, type Patch, type PatchBundle } from "../patch/loader";
import { buildTimelineCells, StepGrid } from "./StepGrid";

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

function renderGrid(bundle: PatchBundle<unknown>, playheadStep: number | null = null) {
  render(<StepGrid bundle={bundle} playheadStep={playheadStep} />);
}

describe("StepGrid", () => {
  it("renders one note start per unique event step", () => {
    const bundle = makeBundle();
    renderGrid(bundle);
    const pattern = scenePatterns(bundle.patch)[0];
    const elementIds = new Set(pattern.notes.map((n) => n.element_id));
    expect(elementIds.size).toBeGreaterThan(0);
    for (const id of elementIds) {
      const row = screen.getByTestId(`step-row-${id}`);
      const starts = row.querySelectorAll('[data-note-state="start"]');
      const steps = new Set(
        pattern.notes.filter((n) => n.element_id === id).map((n) => n.step),
      );
      expect(starts).toHaveLength(steps.size);
    }
  });

  it("labels lanes with stable display indexes without a separate legend bar", () => {
    const bundle = makeBundle();
    renderGrid(bundle);

    const rows = screen.getAllByTestId(/^step-row-/);
    expect(rows[0]).toHaveAttribute("data-lane-index", "1");
    expect(within(rows[0]).getByText("01")).toBeInTheDocument();
    expect(rows.at(-1)).toHaveAttribute("data-lane-index", String(rows.length));
    expect(screen.queryByLabelText("Pattern timeline legend")).not.toBeInTheDocument();
    expect(screen.queryByText("Sequence map")).not.toBeInTheDocument();
  });

  it("renders one-shots as hits and loops as spans to their next trigger", () => {
    const bundle = makeBundle();
    renderGrid(bundle);

    const kick = screen.getByTestId("step-row-el_kick");
    const kickCells = within(kick).getAllByRole("cell");
    expect(kick).toHaveAttribute("data-duration-mode", "hit");
    expect(kickCells[10]).toHaveAttribute("data-note-state", "start");
    expect(kickCells[10]).toHaveAttribute("data-note-length", "1");
    expect(kickCells[10]).toHaveClass("note-start", "note-end", "note-hit");

    const bass = screen.getByTestId("step-row-el_bass");
    const bassCells = within(bass).getAllByRole("cell");
    expect(bass).toHaveAttribute("data-duration-mode", "loop");
    expect(bassCells[0]).toHaveAttribute("data-note-state", "start");
    expect(bassCells[0]).toHaveAttribute("data-note-length", "64");
    expect(bassCells[1]).toHaveAttribute("data-note-state", "sustain");
    expect(bassCells[63]).toHaveAttribute("data-note-state", "end");

    const melody = screen.getByTestId("step-row-el_melody_a");
    const melodyCells = within(melody).getAllByRole("cell");
    expect(melodyCells[0]).toHaveAttribute("data-note-length", "16");
    expect(melodyCells[15]).toHaveAttribute("data-note-state", "end");
    expect(melodyCells[16]).toHaveAttribute("data-note-length", "12");
  });

  it("uses an explicit duration_steps value when the contract supplies one", () => {
    const bundle = makeBundle((b) => {
      const note = b.patch.patterns[0].notes.find((candidate) =>
        candidate.element_id === "el_kick"
      );
      expect(note).toBeDefined();
      note!.duration_steps = 3;
    });
    renderGrid(bundle);

    const cells = within(screen.getByTestId("step-row-el_kick")).getAllByRole("cell");
    expect(cells[10]).toHaveAttribute("data-note-length", "3");
    expect(cells[11]).toHaveAttribute("data-note-state", "sustain");
    expect(cells[12]).toHaveAttribute("data-note-state", "end");
  });

  it("renders bar and beat hierarchy across the complete pattern", () => {
    const bundle = makeBundle();
    renderGrid(bundle);

    expect(
      screen.getByRole("table", { name: "Pattern Original timeline" }),
    ).toHaveAccessibleName("Pattern Original timeline");
    const bars = screen.getAllByTestId(/^step-bar-/);
    expect(bars).toHaveLength(4);
    expect(bars.map((bar) => bar.textContent)).toEqual(["Bar 1", "Bar 2", "Bar 3", "Bar 4"]);
    expect(bars.every((bar) => bar.getAttribute("colspan") === "16")).toBe(true);

    const firstRow = screen.getByTestId(`step-row-${bundle.patch.patterns[0].notes[0].element_id}`);
    const cells = within(firstRow).getAllByRole("cell");
    expect(cells[0]).not.toHaveClass("step-bar-start");
    expect(cells[4]).toHaveClass("step-beat-start");
    expect(cells[16]).toHaveClass("step-bar-start");
  });

  it("marks the current playhead across the ruler and every lane", () => {
    const bundle = makeBundle();
    renderGrid(bundle, 4);

    const ruler = screen.getByRole("columnheader", {
      name: "Bar 1, beat 2, step 5",
    });
    expect(ruler).toHaveAttribute("aria-current", "true");
    for (const row of screen.getAllByTestId(/^step-row-/)) {
      expect(within(row).getAllByRole("cell")[4]).toHaveClass("step-playhead");
    }
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

describe("buildTimelineCells", () => {
  it("clips explicit durations to the visible pattern boundary", () => {
    const cells = buildTimelineCells(
      [{
        element_id: "el_test",
        lane: 0,
        pitch: 36,
        step: 6,
        velocity: 100,
        duration_steps: 8,
      }],
      8,
      false,
    );

    expect(cells[6]).toMatchObject({ active: true, start: true, durationSteps: 2 });
    expect(cells[7]).toMatchObject({ active: true, end: true });
  });
});
