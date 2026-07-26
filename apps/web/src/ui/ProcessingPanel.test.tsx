import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProcessingPanel } from "./ProcessingPanel";

const orderedStages = [
  ["queued", "Input Validated"],
  ["separating", "Stem Separation"],
  ["extracting", "Material Extraction"],
  ["patchifying", "Chop + Map"],
  ["completed", "Patch Verify"],
] as const;

function renderPanel(
  state: string,
  lastNonterminalState = state,
) {
  return render(
    <ProcessingPanel
      fileName="night-bloom.wav"
      state={state}
      lastNonterminalState={lastNonterminalState}
      jobs={[]}
      capacity={{ max_concurrency: 1, processing: 0, waiting: 0 }}
      onUpload={() => undefined}
      onOpenCompleted={() => undefined}
      onDelete={() => undefined}
    />,
  );
}

describe("ProcessingPanel", () => {
  it.each(orderedStages)(
    "maps %s to the truthful %s current stage",
    (state, label) => {
      renderPanel(state);

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
    renderPanel("spectralizing");

    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByText("spectralizing")).toBeInTheDocument();
    expect(screen.getByTestId("processing-panel")).not.toHaveTextContent(/feed it a sound/i);
  });

  it.each([
    ["failed", "Processing failed"],
    ["interrupted", "Service interrupted"],
  ])(
    "freezes completed stages at the last nonterminal state for %s",
    (state, label) => {
      renderPanel(state, "extracting");

      expect(screen.getByTestId("processing-stage-queued")).toHaveClass(
        "stage--done",
      );
      expect(screen.getByTestId("processing-stage-separating")).toHaveClass(
        "stage--done",
      );
      expect(screen.getByTestId("processing-stage-extracting")).toHaveClass(
        "stage--current",
      );
      expect(screen.getByTestId(`processing-terminal-${state}`)).toHaveTextContent(
        label,
      );
      expect(screen.queryByTestId("processing-stage-unknown")).not.toBeInTheDocument();
    },
  );
});
