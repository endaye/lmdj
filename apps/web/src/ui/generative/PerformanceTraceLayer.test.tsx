import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import golden from "../../patch/__fixtures__/patch.golden.json";
import type { Pad } from "../../patch/loader";
import { PerformanceTraceLayer } from "./PerformanceTraceLayer";

const pads = structuredClone(golden.pads) as unknown as Pad[];

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function motionPreference(reduced: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: reduced,
    media: "(prefers-reduced-motion: reduce)",
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

describe("PerformanceTraceLayer", () => {
  it("renders a direct Pad press and removes it after one beat", () => {
    vi.useFakeTimers();
    motionPreference(false);
    render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );

    const layer = screen.getByTestId("performance-trace-layer");
    expect(layer).toHaveAttribute("aria-hidden", "true");
    expect(layer).toHaveStyle({ pointerEvents: "none" });
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);

    act(() => vi.advanceTimersByTime(499));
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
  });

  it("clears the previous bar at the next bar boundary", () => {
    vi.useFakeTimers();
    motionPreference(false);
    const { rerender } = render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={60}
        playheadStep={15}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);

    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={60}
        playheadStep={16}
        projectSeed="patch-a"
      />,
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
  });

  it("keeps a new press that arrives at the next bar boundary", () => {
    vi.useFakeTimers();
    motionPreference(false);
    const { rerender } = render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={60}
        playheadStep={15}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);

    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 2, padIndex: 1 }}
        pads={pads}
        bpm={60}
        playheadStep={16}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);
    expect(screen.getByTestId("performance-trace")).toHaveAttribute(
      "data-pad-index",
      "1",
    );
  });

  it("does not replay a retained press after the project seed changes", () => {
    vi.useFakeTimers();
    motionPreference(false);
    const { rerender } = render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);

    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-b"
      />,
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();

    rerender(
      <PerformanceTraceLayer
        press={null}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-b"
      />,
    );
    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 1 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-b"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);
    expect(screen.getByTestId("performance-trace")).toHaveAttribute(
      "data-pad-index",
      "1",
    );

    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 1 }}
        pads={pads}
        bpm={120}
        playheadStep={16}
        projectSeed="patch-b"
      />,
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
  });

  it("leaves static Pad feedback to PadButton under reduced motion", () => {
    vi.useFakeTimers();
    motionPreference(true);
    render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getByTestId("performance-trace-layer")).toHaveAttribute(
      "data-reduced-motion",
      "true",
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
  });

  it("does not replay a press suppressed by reduced motion", () => {
    vi.useFakeTimers();
    motionPreference(true);
    const { rerender } = render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();

    motionPreference(false);
    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();

    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 2, padIndex: 1 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);
    expect(screen.getByTestId("performance-trace")).toHaveAttribute(
      "data-pad-index",
      "1",
    );
  });
});
