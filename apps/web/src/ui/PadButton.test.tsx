import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Pad } from "../patch/loader";
import { PadButton, type PadVisualState } from "./PadButton";

const drumPad = structuredClone(golden.pads[0]) as unknown as Pad;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PadButton", () => {
  it.each([
    ["idle", "READY", "●"],
    ["selected", "SELECTED", "◎"],
    ["playing", "PLAYING", "▶"],
    ["muted", "MUTED", "⊘"],
    ["missing", "ERROR", "!"],
    ["empty", "EMPTY", "○"],
  ] satisfies [PadVisualState, string, string][])(
    "expresses %s with a visible state label and icon",
    (visualState, label, icon) => {
      render(
        <PadButton
          pad={drumPad}
          visualState={visualState}
          pressed={false}
          keyHint="1"
          onSelect={() => undefined}
          onPress={() => undefined}
          onRelease={() => undefined}
        />,
      );

      const button = screen.getByRole("button", {
        name: new RegExp(`Pad 1: kick, ${visualState}`),
      });
      expect(button).toHaveAttribute("data-visual-state", visualState);
      expect(screen.getByTestId("pad-state-0")).toHaveTextContent(label);
      expect(screen.getByTestId("pad-state-icon-0")).toHaveTextContent(icon);
    },
  );

  it("keeps geometry stable for the same source and changes it after replacement", () => {
    const replacement = {
      ...structuredClone(drumPad),
      element_id: "el_replacement",
      behavior: { element_ids: ["el_replacement"] },
    } as Pad;
    const { rerender } = render(
      <PadButton
        pad={drumPad}
        visualState="idle"
        pressed={false}
        keyHint="1"
        onSelect={() => undefined}
        onPress={() => undefined}
        onRelease={() => undefined}
      />,
    );
    const first = screen.getByTestId("pad-0").dataset.geometrySignature;

    rerender(
      <PadButton
        pad={structuredClone(drumPad)}
        visualState="idle"
        pressed={false}
        keyHint="1"
        onSelect={() => undefined}
        onPress={() => undefined}
        onRelease={() => undefined}
      />,
    );
    expect(screen.getByTestId("pad-0")).toHaveAttribute("data-geometry-signature", first);

    rerender(
      <PadButton
        pad={replacement}
        visualState="idle"
        pressed={false}
        keyHint="1"
        onSelect={() => undefined}
        onPress={() => undefined}
        onRelease={() => undefined}
      />,
    );
    expect(screen.getByTestId("pad-0").dataset.geometrySignature).not.toBe(first);
  });

  it("starts on pointer down, releases on pointer up, and selects on click", () => {
    const onSelect = vi.fn();
    const onPress = vi.fn();
    const onRelease = vi.fn();
    render(
      <PadButton
        pad={drumPad}
        visualState="idle"
        pressed
        keyHint="1"
        onSelect={onSelect}
        onPress={onPress}
        onRelease={onRelease}
      />,
    );

    const pad = screen.getByTestId("pad-0");
    fireEvent.pointerDown(pad, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(pad, { button: 0, pointerId: 1 });
    fireEvent.click(pad, { detail: 1 });

    expect(onPress).toHaveBeenCalledWith(0);
    expect(onRelease).toHaveBeenCalledWith(0);
    expect(onSelect).toHaveBeenCalledWith(0);
    expect(pad).toHaveAttribute("data-pressed", "true");
  });

  it("keeps assistive click activation playable without a pointer event", () => {
    const onPress = vi.fn();
    const onRelease = vi.fn();
    render(
      <PadButton
        pad={drumPad}
        visualState="idle"
        pressed={false}
        keyHint="1"
        onSelect={() => undefined}
        onPress={onPress}
        onRelease={onRelease}
      />,
    );

    fireEvent.click(screen.getByTestId("pad-0"), { detail: 0 });

    expect(onPress).toHaveBeenCalledWith(0);
    expect(onRelease).toHaveBeenCalledWith(0);
  });

  it("retains static text and icon state when reduced motion is preferred", () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    render(
      <PadButton
        pad={drumPad}
        visualState="playing"
        pressed
        keyHint="1"
        onSelect={() => undefined}
        onPress={() => undefined}
        onRelease={() => undefined}
      />,
    );

    const button = screen.getByTestId("pad-0");
    expect(button).toHaveAttribute("data-reduced-motion", "true");
    expect(button).toHaveAccessibleName(/playing/i);
    expect(screen.getByTestId("pad-state-0")).toHaveTextContent("PLAYING");
  });
});
