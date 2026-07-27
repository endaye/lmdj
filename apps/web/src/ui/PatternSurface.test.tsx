import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { AudioEngine } from "../engine/AudioEngine";
import type { Patch, PatchBundle } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { PatternSurface } from "./PatternSurface";

function makeBundle(): PatchBundle<unknown> {
  const patch = structuredClone(golden) as unknown as Patch;
  return {
    patch,
    buffers: new Map(patch.elements.map((element) => [element.element_id, {}])),
    playableElementIds: new Set(patch.elements.map((element) => element.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
}

function renderSurface(bundle: PatchBundle<unknown>, playheadStep: number | null) {
  const engine = new AudioEngine(new FakeAudioContext());
  engine.load(bundle);
  render(<PatternSurface bundle={bundle} engine={engine} playheadStep={playheadStep} />);
}

describe("PatternSurface", () => {
  it("combines transport, pattern facts, step state, and the current playhead", () => {
    const bundle = makeBundle();
    const pattern = bundle.patch.patterns[0];
    renderSurface(bundle, 4);

    const surface = screen.getByTestId("pattern-surface");
    expect(within(surface).getByTestId("play-toggle")).toBeInTheDocument();
    expect(within(surface).getByRole("heading", { name: pattern.name })).toBeInTheDocument();
    expect(within(surface).getByTestId("pattern-summary")).toHaveTextContent(
      `${pattern.length_steps} steps`,
    );
    expect(within(surface).getByTestId("pattern-summary")).toHaveTextContent(
      `${pattern.notes.length} notes`,
    );
    const playhead = within(surface).getByTestId("pattern-playhead");
    expect(playhead).toHaveTextContent("Bar 1 · Beat 2 · Step 05 / 64");
    expect(playhead).toHaveClass("pattern-playhead--running");
    expect(playhead).not.toHaveAttribute("aria-live");
    expect(
      within(surface)
        .getByTestId("pattern-summary")
        .closest(".pattern-surface__header"),
    ).toBeInTheDocument();
    const controls = within(surface).getByTestId("pattern-controls");
    expect(within(controls).getByTestId("transport-bpm")).toBeInTheDocument();
    expect(within(controls).getByTestId("transport-loop")).toBeInTheDocument();
    expect(within(controls).getByTestId("play-toggle")).toBeInTheDocument();
    expect(controls.lastElementChild?.lastElementChild).toBe(
      within(controls).getByTestId("play-toggle"),
    );
    expect(within(surface).getByTestId("step-grid")).toBeInTheDocument();
  });

  it("shows compact timing values with full precision but omits duplicate source identity", () => {
    const bundle = makeBundle();
    bundle.patch.bpm = 117.453835;
    bundle.patch.loop_seconds = 8.173424052096724;
    bundle.patch.patch_id =
      "source-09f69a8fcc1461ff3631657100ffe2b1eae58f6a2b96e2f9aa3ce6fa3f02d99e-2280ebab";

    renderSurface(bundle, null);

    expect(screen.getByTestId("transport-bpm")).toHaveTextContent("117.45");
    expect(screen.getByTestId("transport-bpm").parentElement).toHaveAttribute(
      "title",
      "BPM 117.453835",
    );
    expect(screen.getByTestId("transport-loop")).toHaveTextContent("8.17s");
    expect(screen.getByTestId("transport-loop").parentElement).toHaveAttribute(
      "title",
      "Loop 8.173424052096724 seconds",
    );
    expect(screen.queryByTestId("transport-source")).not.toBeInTheDocument();
    expect(screen.queryByText(bundle.patch.patch_id)).not.toBeInTheDocument();
  });

  it("renders an explicit empty state when the active scene has no pattern", () => {
    const bundle = makeBundle();
    bundle.patch.scenes[0].pattern_ids = [];

    renderSurface(bundle, null);

    expect(screen.getByTestId("pattern-empty")).toHaveTextContent("No active pattern");
    expect(screen.queryByTestId("step-grid")).not.toBeInTheDocument();
    expect(screen.getByTestId("play-toggle")).toBeInTheDocument();
  });
});
