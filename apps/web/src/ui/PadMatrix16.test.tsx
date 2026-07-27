import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { AudioEngine } from "../engine/AudioEngine";
import { padElementIds, type Patch, type PatchBundle } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { PAD_KEYS, PadMatrix16 } from "./PadMatrix16";

function setup(mutate?: (bundle: PatchBundle<unknown>) => void) {
  const patch = structuredClone(golden) as unknown as Patch;
  const bundle: PatchBundle<unknown> = {
    patch,
    buffers: new Map(patch.elements.map((element) => [element.element_id, {}])),
    playableElementIds: new Set(patch.elements.map((element) => element.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
  mutate?.(bundle);
  const engine = new AudioEngine(new FakeAudioContext());
  engine.load(bundle);
  const triggerPad = vi.spyOn(engine, "triggerPad");
  const onSelect = vi.fn();
  const onPress = vi.fn((index: number) => engine.triggerPad(index));
  const onRelease = vi.fn();
  function Harness() {
    const [pressedPadIndices, setPressedPadIndices] = useState<Set<number>>(
      () => new Set(),
    );
    return (
      <PadMatrix16
        bundle={bundle}
        engine={engine}
        selectedPadIndex={undefined}
        pressedPadIndices={pressedPadIndices}
        onSelect={onSelect}
        onPress={(index) => {
          setPressedPadIndices((current) => new Set(current).add(index));
          onPress(index);
        }}
        onRelease={(index) => {
          setPressedPadIndices((current) => {
            const next = new Set(current);
            next.delete(index);
            return next;
          });
          onRelease(index);
        }}
      />
    );
  }
  render(
    <Harness />,
  );
  return { bundle, engine, onPress, onRelease, onSelect, triggerPad };
}

describe("PadMatrix16", () => {
  it("always maps all sixteen contract pads with fixed keyboard hints", () => {
    const { bundle } = setup();
    const buttons = screen.getAllByTestId(/^pad-\d+$/);

    expect(buttons).toHaveLength(16);
    expect(buttons.map((button) => Number(button.dataset.padIndex))).toEqual(
      Array.from({ length: 16 }, (_, index) => index),
    );
    for (const pad of bundle.patch.pads) {
      const button = screen.getByTestId(`pad-${pad.index}`);
      expect(button).toHaveAccessibleName(
        new RegExp(`Pad ${pad.index + 1}: ${pad.label}, (idle|empty|reserved)`),
      );
      expect(button).toHaveTextContent(PAD_KEYS[pad.index]);
    }
  });

  it("selects and triggers a material-backed pad through AudioEngine.triggerPad", () => {
    const { onPress, onRelease, onSelect, triggerPad } = setup();
    const pad = screen.getByTestId("pad-0");

    fireEvent.pointerDown(pad, { button: 0, pointerId: 1 });

    expect(onPress).toHaveBeenCalledWith(0);
    expect(triggerPad).toHaveBeenCalledWith(0);
    expect(pad).toHaveAttribute("data-pressed", "true");
    expect(pad).toHaveAttribute("data-visual-state", "playing");

    fireEvent.pointerUp(pad, { button: 0, pointerId: 1 });
    fireEvent.click(pad, { detail: 1 });

    expect(onRelease).toHaveBeenCalledWith(0);
    expect(onSelect).toHaveBeenCalledWith(0);
    expect(pad).toHaveAttribute("data-pressed", "false");
  });

  it("selects empty and reserved pads without faking playback", () => {
    const { bundle, onSelect, triggerPad } = setup();
    const noOpPads = bundle.patch.pads.filter((pad) => padElementIds(pad).length === 0);

    for (const pad of noOpPads) {
      fireEvent.click(screen.getByTestId(`pad-${pad.index}`));
      expect(onSelect).toHaveBeenLastCalledWith(pad.index);
    }

    expect(triggerPad).not.toHaveBeenCalled();
    expect(noOpPads.some((pad) => pad.action === "empty")).toBe(true);
    expect(noOpPads.some((pad) => pad.action !== "empty")).toBe(true);
  });

  it("uses visible missing and muted states from the loaded bundle and engine", () => {
    const patch = structuredClone(golden) as unknown as Patch;
    const missingId = padElementIds(patch.pads[2])[0];
    const { engine } = setup((bundle) => {
      bundle.missingElementIds.add(missingId);
      bundle.playableElementIds.delete(missingId);
    });

    expect(screen.getByTestId("pad-2")).toHaveAttribute("data-visual-state", "missing");
    fireEvent.contextMenu(screen.getByTestId("pad-0"));
    expect(engine.isPadMuted(0)).toBe(true);
    expect(screen.getByTestId("pad-0")).toHaveAttribute("data-visual-state", "muted");
  });

  it("keeps a loop playing after release without keeping its pressed color", () => {
    const { bundle } = setup((loaded) => {
      loaded.patch.pads[1].behavior = {
        ...loaded.patch.pads[1].behavior,
        trigger: "loop",
      };
    });
    const loopPad = screen.getByTestId("pad-1");

    fireEvent.pointerDown(loopPad, { button: 0, pointerId: 1 });
    expect(loopPad).toHaveAttribute("data-pressed", "true");
    fireEvent.pointerUp(loopPad, { button: 0, pointerId: 1 });
    expect(loopPad).toHaveAttribute("data-visual-state", "playing");
    expect(loopPad).toHaveAttribute("data-pressed", "false");

    fireEvent.pointerDown(loopPad, { button: 0, pointerId: 2 });
    fireEvent.pointerUp(loopPad, { button: 0, pointerId: 2 });
    expect(bundle.patch.pads[1].behavior.trigger).toBe("loop");
    expect(loopPad).toHaveAttribute("data-visual-state", "idle");
  });
});
