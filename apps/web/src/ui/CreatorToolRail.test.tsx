import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { CreatorToolRail } from "./CreatorToolRail";

describe("CreatorToolRail", () => {
  it("renders the three persistent creator views and reports an available mode change", async () => {
    const onModeChange = vi.fn();
    render(
      <CreatorToolRail
        mode="source"
        onModeChange={onModeChange}
        availableModes={["source", "performance", "export"]}
      />,
    );

    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([
      "Source",
      "Performance",
      "Export",
    ]);
    await userEvent.click(screen.getByRole("button", { name: "Performance" }));
    expect(onModeChange).toHaveBeenCalledWith("performance");
  });

  it("keeps unavailable views visible but disabled and unselected", async () => {
    const onModeChange = vi.fn();
    render(
      <CreatorToolRail
        mode="source"
        onModeChange={onModeChange}
        availableModes={[]}
      />,
    );

    expect(screen.queryByText("Creator Tools")).not.toBeInTheDocument();
    for (const name of ["Source", "Performance", "Export"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("aria-pressed", "false");
      await userEvent.click(button);
    }
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it("has no false-entry controls for unavailable creator capabilities", () => {
    render(
      <CreatorToolRail
        mode="source"
        onModeChange={() => undefined}
        availableModes={["source", "performance", "export"]}
      />,
    );

    for (const name of ["Generate", "Line-in", "Chop", "AI Preview", "Take", "Pattern A", "Pattern B", "Pattern C", "Pattern D"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("changes the tool mode without changing externally owned pad selection", async () => {
    function RailHarness() {
      const [mode, setMode] = useState<"source" | "performance" | "export">("source");
      const selectedPadIndex = 3;
      return (
        <>
          <span data-testid="selected-pad">{selectedPadIndex}</span>
          <CreatorToolRail
            mode={mode}
            onModeChange={setMode}
            availableModes={["source", "performance", "export"]}
          />
        </>
      );
    }

    render(<RailHarness />);
    await userEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(screen.getByTestId("selected-pad")).toHaveTextContent("3");
  });
});
