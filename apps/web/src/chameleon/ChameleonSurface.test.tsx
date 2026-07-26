import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { createVisualSignature } from "./visualSignature";
import { ChameleonSurface } from "./ChameleonSurface";

describe("ChameleonSurface", () => {
  it("uses a real button for the Gallery upload entrance", async () => {
    const state = deriveChameleonVisualState({ appPhase: "source" });
    const activate = vi.fn();
    render(
      <ChameleonSurface
        state={state}
        signature={createVisualSignature("lmdj", state)}
        onActivate={activate}
        onToggle={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", {
        name: "Choose a WAV or MP3 to make a Patch",
      }),
    );
    expect(activate).toHaveBeenCalledTimes(1);
  });

  it("announces error text and exposes an explicit close action", async () => {
    const dock = deriveChameleonVisualState({
      appPhase: "failed",
      errorKey: "submission-1:upload",
      errorLabel: "Upload failed",
    });
    const state = { ...dock, placement: "floating" as const };
    const dismiss = vi.fn();
    render(
      <ChameleonSurface
        state={state}
        signature={createVisualSignature("submission-1", state)}
        onActivate={vi.fn()}
        onToggle={vi.fn()}
        onDismiss={dismiss}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Upload failed");
    await userEvent.click(screen.getByRole("button", { name: "Close assistant" }));
    expect(dismiss).toHaveBeenCalledTimes(1);
  });

  it("keeps processing collapsed in a labeled Dock button", () => {
    const state = deriveChameleonVisualState({
      appPhase: "processing",
      jobState: "separating",
    });
    render(
      <ChameleonSurface
        state={state}
        signature={createVisualSignature("submission-1", state)}
        onActivate={vi.fn()}
        onToggle={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", {
        name: "Chameleon assistant · Separating stems",
      }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("chameleon-dock-state")).toHaveTextContent("S");
  });
});
