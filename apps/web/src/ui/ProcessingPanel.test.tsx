import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProcessingPanel } from "./ProcessingPanel";

const orderedStages = [
  ["queued", "Input Validated"],
  ["separating", "Stem Separation"],
  ["patchifying", "Chop + Map"],
  ["completed", "Patch Verify"],
] as const;

describe("ProcessingPanel", () => {
  it.each(orderedStages)(
    "maps %s to the truthful %s current stage",
    (state, label) => {
      render(<ProcessingPanel fileName="night-bloom.wav" state={state} />);

      expect(screen.getByText("night-bloom.wav")).toBeInTheDocument();
      expect(screen.getByTestId(`processing-stage-${state}`)).toHaveTextContent(label);
      expect(screen.getByTestId(`processing-stage-${state}`)).toHaveAttribute(
        "aria-current",
        "step",
      );
      expect(screen.getByTestId("processing-panel").textContent).not.toMatch(/\d+%/);
    },
  );

  it("shows an unknown worker state without pretending it is Source", () => {
    render(<ProcessingPanel fileName="night-bloom.wav" state="spectralizing" />);

    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByText("spectralizing")).toBeInTheDocument();
    expect(screen.getByTestId("processing-panel")).not.toHaveTextContent(/feed it a sound/i);
  });
});
