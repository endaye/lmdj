import {act, render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {OverviewDisplay} from "../src/components/overview_display";
import {SequenceOverview} from "../src/components/sequence_overview";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import {initialSequenceState} from "../src/state/sequence_state";
import {
  initialPatternTransportState,
  type PatternTransportState,
} from "../src/state/pattern_transport_state";

const project = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 7, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—" as const,
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null})),
  patterns: [
    {
      patternId: "22222222-2222-4222-8222-222222222222",
      bars: 2 as const,
      events: [
        Object.freeze({
          slot: Object.freeze({bank: 0, pad: 0}),
          onsetTick: 0, durationTick: 240, velocity: 100,
        }),
        Object.freeze({
          slot: Object.freeze({bank: 2, pad: 5}),
          onsetTick: 480, durationTick: 480, velocity: 90,
        }),
      ],
    },
  ],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};

const playingTransport: PatternTransportState = {
  ...initialPatternTransportState,
  sessionId: "session-1",
  status: {
    engaged: true,
    playing: true,
    recording: false,
    phase: "idle",
    runtimeGeneration: 1,
    transportEpoch: 1,
    originFrame: 0,
    runtimeFrame: 0,
    observedAtMilliseconds: 1_000,
    commandId: null,
    publicationPending: false,
    error: null,
  } satisfies PatternTransportStatus,
};

function renderOverview(
  overrides: Partial<Parameters<typeof SequenceOverview>[0]> = {},
) {
  return render(
    <SequenceOverview
      project={project}
      state={initialSequenceState}
      bank={0}
      snap="1/16"
      viewport={null}
      selection={[]}
      {...overrides}
    />,
  );
}

const overviewNotes = () => within(
  screen.getByTestId("sequence-pattern-overview") as unknown as HTMLElement,
).queryAllByTestId("sequence-overview-note");
const rowNames = () => [...screen.getByTestId("sequence-overview")
  .querySelectorAll(".sequence-overview-names li")].map((item) => item.textContent);

test("shows eight Pad rows from the active Bank's first row", () => {
  const view = renderOverview();
  expect(rowNames()).toEqual(["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08"]);
  expect(overviewNotes().map((note) => note.getAttribute("data-row"))).toEqual(["0"]);
  // The C06 note (row 37) appears once the window is on Bank C.
  view.rerender(<SequenceOverview project={project} state={initialSequenceState}
    bank={2} snap="1/16" viewport={null} selection={[]} />);
  expect(rowNames()[0]).toBe("C01");
  expect(overviewNotes().map((note) => note.getAttribute("data-row"))).toEqual(["37"]);
  expect(screen.getByTestId("sequence-overview").textContent ?? "")
    .not.toMatch(/live projection target/);
});

test("draws step cells at the snap, alternating shade per beat", () => {
  const view = renderOverview({snap: "1/4"});
  const cells = () => view.container.querySelectorAll(".sequence-overview-cell");
  // Two bars at 1/4 are eight steps on each of eight rows.
  expect(cells()).toHaveLength(64);
  expect([...cells()].slice(0, 3).map((cell) => cell.getAttribute("class")))
    .toEqual([
      "sequence-overview-cell is-even",
      "sequence-overview-cell is-odd",
      "sequence-overview-cell is-even",
    ]);
  view.rerender(<SequenceOverview project={project} state={initialSequenceState}
    bank={0} snap="off" viewport={null} selection={[]} />);
  expect(cells()).toHaveLength(8 * 32);
});

test("marks the touch grid's Bank and time window as the overview frame", () => {
  renderOverview({bank: 1, viewport: {startTick: 960, endTick: 4800}});
  const frame = screen.getByTestId("sequence-overview-frame");
  expect(frame.getAttribute("x")).toBe("960");
  expect(frame.getAttribute("width")).toBe("3840");
  expect(frame.getAttribute("y")).toBe("0");
  expect(frame.getAttribute("height")).toBe("101");
});

test("shows the context line, and the selection only when notes are selected", () => {
  renderOverview({snap: "1/32"});
  const overview = screen.getByTestId("sequence-overview");
  const fact = (name: string) =>
    within(overview).getByText(name).nextElementSibling?.textContent;
  expect(fact("Bars")).toBe("01–02");
  expect(fact("Steps")).toBe("64");
  expect(fact("Snap")).toBe("1/32");
  expect(fact("Tracks")).toBe("A01–A08 / 64");
  expect(fact("Bank")).toBe("A");
  expect(within(overview).queryByText("Selected")).toBeNull();
  expect(within(overview).queryByText("Velocity")).toBeNull();
  // Quantize and Swing moved to the touch SETUP layer and the status line.
  expect(within(overview).queryByText("Quantize")).toBeNull();
  expect(within(overview).queryByText("Swing")).toBeNull();
  expect(screen.getByTestId("sequence-position").textContent).toBe("STOPPED / 001:01");
});

test("shows one status line, the most severe first", () => {
  const pending = {
    ...playingTransport,
    status: {...playingTransport.status!, publicationPending: true},
  };
  const view = renderOverview({transport: pending});
  const status = () => screen.getByTestId("sequence-overview")
    .querySelectorAll(".sequence-overview-status");
  expect(status()).toHaveLength(1);
  expect(status()[0]!.textContent).toBe("Committed, publication pending");
  view.rerender(
    <SequenceOverview project={project}
      state={{...initialSequenceState, errorCode: "HOST_TIMEOUT"}}
      bank={0} snap="1/16" viewport={null} selection={[]}
      transport={{...pending, errorCode: "HOST_STATE_INVALID"}} />);
  expect(status()).toHaveLength(1);
  expect(status()[0]!.textContent).toBe("That can't be done right now.");
});

test("a playhead frame that outlives its effect never reschedules", () => {
  let animationFrame: FrameRequestCallback | undefined;
  const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame")
    .mockImplementation((callback) => {
      animationFrame = callback;
      return 71;
    });
  const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame")
    .mockImplementation(() => {});
  const now = vi.spyOn(performance, "now").mockReturnValue(1_000);
  try {
    const view = renderOverview({transport: playingTransport});
    expect(view.container.querySelector("line[data-playhead]")).not.toBeNull();

    // The transport stops: the effect cleans up. A frame that was already
    // dequeued escapes cancelAnimationFrame, and it must not reschedule or
    // write state afterwards.
    view.rerender(
      <SequenceOverview
        project={project}
        state={initialSequenceState}
        bank={0}
        snap="1/16"
        viewport={null}
        selection={[]}
      />,
    );
    expect(cancelAnimationFrame).toHaveBeenCalledWith(71);
    const escaped = animationFrame;
    animationFrame = undefined;
    act(() => escaped?.(2_000));
    expect(animationFrame).toBeUndefined();
    expect(view.container.querySelector("line[data-playhead]")).toBeNull();
  } finally {
    requestAnimationFrame.mockRestore();
    cancelAnimationFrame.mockRestore();
    now.mockRestore();
  }
});

test("advances the playhead on the render clock while the transport plays", () => {
  let animationFrame: FrameRequestCallback | undefined;
  const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame")
    .mockImplementation((callback) => {
      animationFrame = callback;
      return 71;
    });
  const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame")
    .mockImplementation(() => {});
  const now = vi.spyOn(performance, "now").mockReturnValue(1_000);
  try {
    const view = renderOverview({transport: playingTransport});
    const playhead = () =>
      view.container.querySelector("line[data-playhead]");
    expect(playhead()?.getAttribute("x1")).toBe("0");
    // Half a second at 120 BPM is 960 ticks; the loop is 7680 ticks.
    act(() => animationFrame?.(1_500));
    expect(playhead()?.getAttribute("x1")).toBe("960");
    expect(screen.getByTestId("sequence-position").textContent).toBe("PLAYING / 001:02");

    view.rerender(
      <SequenceOverview
        project={project}
        state={initialSequenceState}
        bank={0}
        snap="1/16"
        viewport={null}
        selection={[]}
      />,
    );
    expect(playhead()).toBeNull();
    expect(cancelAnimationFrame).toHaveBeenCalledWith(71);
  } finally {
    requestAnimationFrame.mockRestore();
    cancelAnimationFrame.mockRestore();
    now.mockRestore();
  }
});

test("a remounted overview resumes the playhead at the playing position", () => {
  const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame")
    .mockImplementation(() => 72);
  const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame")
    .mockImplementation(() => {});
  // The status was observed at 1000 ms with the Runtime at the origin; the
  // overview mounts 750 ms later, as after leaving Sequence mid-playback.
  // 0.75 s at 120 BPM is 1440 ticks.
  const now = vi.spyOn(performance, "now").mockReturnValue(1_750);
  try {
    const view = renderOverview({transport: playingTransport});
    expect(view.container.querySelector("line[data-playhead]")
      ?.getAttribute("x1")).toBe("1440");
    // An observation already past the origin counts from its own frame:
    // 24000 frames after a 96000 origin is half a second, 960 ticks.
    view.rerender(
      <SequenceOverview project={project} state={initialSequenceState}
        bank={0} snap="1/16" viewport={null} selection={[]}
        transport={{...playingTransport, status: {...playingTransport.status!,
          originFrame: 96_000, runtimeFrame: 120_000,
          observedAtMilliseconds: 1_750}}} />);
    expect(view.container.querySelector("line[data-playhead]")
      ?.getAttribute("x1")).toBe("960");
  } finally {
    requestAnimationFrame.mockRestore();
    cancelAnimationFrame.mockRestore();
    now.mockRestore();
  }
});

test("the selection facts follow the touch grid's live selection", () => {
  const overview = () => screen.getByTestId("sequence-overview");
  const fact = (name: string) =>
    within(overview()).getByText(name).nextElementSibling?.textContent;
  const view = renderOverview({selection: [
    {bank: 0, pad: 0, onsetTick: 0},
  ]});
  expect(fact("Selected")).toBe("1");
  expect(fact("Velocity")).toBe("100");
  view.rerender(
    <SequenceOverview
      project={project}
      state={initialSequenceState}
      bank={0}
      snap="1/16"
      viewport={null}
      selection={[
        {bank: 0, pad: 0, onsetTick: 0},
        {bank: 2, pad: 5, onsetTick: 480},
      ]}
    />,
  );
  expect(fact("Selected")).toBe("2");
  expect(fact("Velocity")).toBe("mixed");
});

test("Sequence draws only its status and rows; the phase and facts stay readable", () => {
  const state: CreatorState = {
    ...initialCreatorState,
    project: {...initialCreatorState.project, phase: "ready", current: project},
  };
  const display = (activeMode: "sequence" | "project" | "sample") => (
    <OverviewDisplay state={state} activeMode={activeMode} sequence={initialSequenceState}
      snap="1/16" viewport={null} selection={[]} />
  );
  const view = render(display("sequence"));
  const hidden = (selector: string) =>
    view.container.querySelector(selector)?.classList.contains("visually-hidden");
  expect(view.container.querySelector(".overview-swing")?.textContent).toBe("SWING 50%");
  expect(hidden(".overview-phase")).toBe(true);
  expect(hidden(".overview-facts")).toBe(true);
  expect(screen.getByTestId("audio-state").textContent).toMatch(/^Audio /);
  expect(screen.getByText("Rev").nextElementSibling?.textContent).toBe("7");

  // Project draws its own summary and columns (D01) and hides them too;
  // Sample still draws the shared phase and facts.
  view.rerender(display("project"));
  expect(view.container.querySelector(".overview-swing")).toBeNull();
  expect(hidden(".overview-facts")).toBe(true);
  view.rerender(display("sample"));
  expect(hidden(".overview-phase")).toBe(false);
  expect(hidden(".overview-facts")).toBe(false);
});
