import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { createVisualSignature } from "./visualSignature";
import { Chameleon2D } from "./Chameleon2D";

describe("Chameleon2D", () => {
  const state = deriveChameleonVisualState({ appPhase: "source" });
  const signature = createVisualSignature("lmdj", state);

  it("renders decorative media with explicit visual-state attributes", () => {
    const { container } = render(
      <Chameleon2D state={state} signature={signature} />,
    );
    expect(screen.getByTestId("chameleon-2d")).toHaveAttribute(
      "data-phase",
      "idle",
    );
    // Decorative: an empty alt keeps the character out of the accessibility
    // tree (role presentation), so readable state comes from ChameleonSurface.
    expect(container.querySelector("img")).toHaveAttribute("alt", "");
  });

  it("shows a non-image silhouette fallback when the asset fails", () => {
    const { container } = render(
      <Chameleon2D state={state} signature={signature} />,
    );
    fireEvent.error(container.querySelector("img")!);
    expect(screen.getByTestId("chameleon-fallback")).toBeVisible();
  });
});
