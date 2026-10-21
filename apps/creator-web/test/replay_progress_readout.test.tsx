import {render, screen} from "@testing-library/react";
import {expect, test} from "vitest";
import type {PerformanceReplayStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {ReplayProgressReadout} from "../src/components/replay_progress_readout";

const playing: PerformanceReplayStatus = {replayId: "replay-1", state: "playing",
  resolvedRevision: 7, eventCursor: 0, eventCount: 4, projectRevision: null};

test("no replay never claims a count or neutral reset", () => {
  render(<ReplayProgressReadout replay={null} neutral />);
  expect(screen.getByRole("heading", {name: "No replay selected"})).not.toBeNull();
  expect(screen.queryByRole("status", {name: "Replay events"})).toBeNull();
  expect(screen.queryByText(/Neutral reset confirmed/)).toBeNull();
});

test.each([[0, "0 / 4 events"], [3, "3 / 4 events"]] as const)(
  "public cursor %i is displayed without a clock or interpolation", (eventCursor, literal) => {
    render(<ReplayProgressReadout replay={{...playing, eventCursor}} neutral={false} />);
    const output = screen.getByRole("status", {name: "Replay events"});
    expect(output.textContent).toBe(literal);
    expect(output.getAttribute("data-event-cursor")).toBe(String(eventCursor));
    expect(output.getAttribute("data-event-count")).toBe("4");
    const progress = screen.getByRole("progressbar", {name: "Replay event progress"});
    expect(progress.getAttribute("value")).toBe(String(eventCursor));
    expect(progress.getAttribute("max")).toBe("4");
    const card = screen.getByRole("region", {name: "Replay event readout"});
    expect(card.getAttribute("data-replay-id")).toBe("replay-1");
    expect(card.getAttribute("data-resolved-revision")).toBe("7");
  },
);

test("a full cursor remains playing until the public producer reports a terminal state", () => {
  render(<ReplayProgressReadout replay={{...playing, eventCursor: 4}} neutral />);
  expect(screen.getByRole("heading", {name: "Replay playing"})).not.toBeNull();
  expect(screen.getByText("Replay controls active")).not.toBeNull();
  expect(screen.queryByText(/Neutral reset confirmed/)).toBeNull();
});

test.each(["stopped", "complete"] as const)("%s before neutral acknowledgement stays pending", state => {
  render(<ReplayProgressReadout replay={{...playing, state, eventCursor: 4}} neutral={false} />);
  expect(screen.getByText("Neutral reset pending")).not.toBeNull();
  expect(screen.queryByText(/Neutral reset confirmed/)).toBeNull();
});

test("only a terminal receipt plus the existing neutral acknowledgement confirms reset", () => {
  render(<ReplayProgressReadout replay={{...playing, state: "stopped", eventCursor: 2}} neutral hold={false} />);
  expect(screen.getByText("Neutral reset confirmed · HOLD off")).not.toBeNull();
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("2 / 4 events");
});

test("a later live HOLD change is not overwritten by the historical Replay reset fact", () => {
  render(<ReplayProgressReadout replay={{...playing, state: "stopped", eventCursor: 2}} neutral hold />);
  expect(screen.getByText("Neutral reset confirmed · HOLD on")).not.toBeNull();
  expect(screen.queryByText(/HOLD off/)).toBeNull();
});

test("an empty complete replay has no invented duration or percentage", () => {
  render(<ReplayProgressReadout replay={{...playing, state: "complete", eventCount: 0}} neutral />);
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("0 / 0 events");
  expect(screen.queryByRole("progressbar")).toBeNull();
});

test.each([
  [-1, 4], [1.5, 4], [5, 4], [0, -1], [0, Number.NaN], [0, Infinity],
  [0, Number.MAX_SAFE_INTEGER + 1],
])("invalid cursor/count %s/%s is unavailable rather than clamped", (eventCursor, eventCount) => {
  render(<ReplayProgressReadout replay={{...playing, eventCursor, eventCount}} neutral={false} />);
  const output = screen.getByRole("status", {name: "Replay events"});
  expect(output.textContent).toBe("Event progress unavailable");
  expect(output.hasAttribute("data-event-cursor")).toBe(false);
  expect(output.hasAttribute("data-event-count")).toBe(false);
  expect(screen.queryByRole("progressbar")).toBeNull();
});

test("requesting Stop does not manufacture a terminal or neutral receipt", () => {
  render(<ReplayProgressReadout replay={{...playing, eventCursor: 3}} neutral stopping />);
  expect(screen.getByRole("heading", {name: "Stopping Replay…"})).not.toBeNull();
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("3 / 4 events");
  expect(screen.getByText("Neutral reset pending")).not.toBeNull();
});

test("a replacement replay renders its own receipt without retaining the prior count", () => {
  const view = render(<ReplayProgressReadout replay={{...playing, eventCursor: 3}} neutral={false} />);
  view.rerender(<ReplayProgressReadout replay={{...playing, replayId: "replay-2", resolvedRevision: 9,
    eventCount: 1}} neutral={false} />);
  const card = screen.getByRole("region", {name: "Replay event readout"});
  expect(card.getAttribute("data-replay-id")).toBe("replay-2");
  expect(card.getAttribute("data-resolved-revision")).toBe("9");
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("0 / 1 events");
});
