import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { AudioEngine } from "../engine/AudioEngine";
import type { Patch, PatchBundle } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { PadGrid } from "./PadGrid";

function setup(mutate?: (patch: Patch, bundle: PatchBundle<unknown>) => void) {
  const patch = structuredClone(golden) as unknown as Patch;
  const bundle: PatchBundle<unknown> = {
    patch,
    buffers: new Map(patch.elements.map((e) => [e.element_id, { buf: e.element_id }])),
    playableElementIds: new Set(patch.elements.map((e) => e.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
  mutate?.(patch, bundle);
  const ctx = new FakeAudioContext();
  const engine = new AudioEngine(ctx);
  engine.load(bundle);
  render(<PadGrid engine={engine} bundle={bundle} />);
  return { ctx, engine, bundle };
}

describe("PadGrid", () => {
  it("renders 8 pads with slot names and key hints", () => {
    setup();
    const pads = screen.getAllByTestId(/^pad-\d$/);
    expect(pads).toHaveLength(8);
    expect(screen.getByText("Drums")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument(); // pad 0 键提示
  });

  it("reserved pads are disabled, empty pads marked empty", () => {
    const { bundle } = setup();
    const reserved = bundle.patch.pads.find((p) => p.action === "scene_fill")!;
    expect(screen.getByTestId(`pad-${reserved.index}`)).toHaveClass("pad--reserved");
    const empty = bundle.patch.pads.find((p) => p.action === "empty");
    if (empty) expect(screen.getByTestId(`pad-${empty.index}`)).toHaveClass("pad--empty");
  });

  it("click triggers the whole group", () => {
    const { ctx } = setup();
    fireEvent.click(screen.getByTestId("pad-0")); // Drums trigger_group
    expect(ctx.sources.length).toBeGreaterThan(1);
  });

  it("contextmenu toggles mute (and is prevented)", () => {
    const { engine } = setup();
    const pad = screen.getByTestId("pad-0");
    const notPrevented = fireEvent.contextMenu(pad);
    expect(notPrevented).toBe(false); // preventDefault() 已调用
    expect(engine.isPadMuted(0)).toBe(true);
    expect(pad).toHaveClass("pad--muted");
    fireEvent.contextMenu(pad);
    expect(engine.isPadMuted(0)).toBe(false);
  });

  it("pads with missing assets render the error state", () => {
    const { bundle } = setup((patch, b) => {
      const drums = patch.pads[0];
      const ids = (drums.behavior as { element_ids: string[] }).element_ids;
      b.missingElementIds.add(ids[0]);
      b.playableElementIds.delete(ids[0]);
    });
    expect(bundle.missingElementIds.size).toBe(1);
    expect(screen.getByTestId("pad-0")).toHaveClass("pad--error");
  });
});
