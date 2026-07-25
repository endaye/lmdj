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
          keyHint="1"
          onSelect={() => undefined}
          onTrigger={() => undefined}
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
        keyHint="1"
        onSelect={() => undefined}
        onTrigger={() => undefined}
      />,
    );
    const first = screen.getByTestId("pad-0").dataset.geometrySignature;

    rerender(
      <PadButton
        pad={structuredClone(drumPad)}
        visualState="idle"
        keyHint="1"
        onSelect={() => undefined}
        onTrigger={() => undefined}
      />,
    );
    expect(screen.getByTestId("pad-0")).toHaveAttribute("data-geometry-signature", first);

    rerender(
      <PadButton
        pad={replacement}
        visualState="idle"
        keyHint="1"
        onSelect={() => undefined}
        onTrigger={() => undefined}
      />,
    );
    expect(screen.getByTestId("pad-0").dataset.geometrySignature).not.toBe(first);
  });

  it("selects and triggers from the same button activation", () => {
    const onSelect = vi.fn();
    const onTrigger = vi.fn();
    render(
      <PadButton
        pad={drumPad}
        visualState="idle"
        keyHint="1"
        onSelect={onSelect}
        onTrigger={onTrigger}
      />,
    );

    fireEvent.click(screen.getByTestId("pad-0"));

    expect(onSelect).toHaveBeenCalledWith(0);
    expect(onTrigger).toHaveBeenCalledWith(0);
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
        keyHint="1"
        onSelect={() => undefined}
        onTrigger={() => undefined}
      />,
    );

    const button = screen.getByTestId("pad-0");
    expect(button).toHaveAttribute("data-reduced-motion", "true");
    expect(button).toHaveAccessibleName(/playing/i);
    expect(screen.getByTestId("pad-state-0")).toHaveTextContent("PLAYING");
  });
});
