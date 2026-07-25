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
    expect(playhead).toHaveTextContent("Step 05 / 64");
    expect(playhead).not.toHaveAttribute("aria-live");
    expect(within(surface).getByTestId("pattern-summary")).toHaveTextContent("Original");
    expect(within(surface).getByTestId("step-grid")).toBeInTheDocument();
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
