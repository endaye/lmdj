import {fireEvent, render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {SequenceGrid} from "../src/components/sequence_grid";

const pattern = {
  patternId: "22222222-2222-4222-8222-222222222222",
  bars: 2 as const,
  events: [
    Object.freeze({
      slot: Object.freeze({bank: 0, pad: 0}),
      onsetTick: 0, durationTick: 240, velocity: 100,
    }),
    Object.freeze({
      slot: Object.freeze({bank: 0, pad: 1}),
      onsetTick: 240, durationTick: 480, velocity: 80,
    }),
    Object.freeze({
      slot: Object.freeze({bank: 1, pad: 2}),
      onsetTick: 480, durationTick: 240, velocity: 127,
    }),
  ],
};

function renderGrid(bank: 0 | 1 = 0) {
  const callbacks = {
    onSnapChange: vi.fn(),
    onViewportChange: vi.fn(),
  };
  const view = render(
    <SequenceGrid pattern={pattern} bank={bank} snap="1/16" {...callbacks} />,
  );
  return {callbacks, view};
}

const row = (pad: number) =>
  document.querySelector(`.sequence-grid-row[data-pad="${pad}"]`) as HTMLElement;

test("renders the active Bank's sixteen Pad rows with their notes", () => {
  renderGrid(0);
  const grid = screen.getByTestId("sequence-grid");
  expect(within(grid).getAllByText(/^A(?:[1-9]|1[0-6])$/)).toHaveLength(16);
  const first = within(row(0)).getByTestId("sequence-grid-note");
  expect(first.getAttribute("data-onset-tick")).toBe("0");
  expect(first.getAttribute("data-duration-tick")).toBe("240");
  expect(first.getAttribute("data-velocity")).toBe("100");
  const second = within(row(1)).getByTestId("sequence-grid-note");
  expect(second.getAttribute("data-onset-tick")).toBe("240");
  expect(second.getAttribute("data-duration-tick")).toBe("480");
  expect(within(row(2)).queryByTestId("sequence-grid-note")).toBeNull();
  expect(screen.getByRole("img", {
    name: "Pad A2 note · onset 240 · length 480 · velocity 80",
  })).toBeTruthy();
});

test("follows Bank switching to the other Bank's Pads and notes", () => {
  const {view} = renderGrid(0);
  view.rerender(
    <SequenceGrid pattern={pattern} bank={1} snap="1/16"
      onSnapChange={() => {}} onViewportChange={() => {}} />,
  );
  const grid = screen.getByTestId("sequence-grid");
  expect(within(grid).getAllByText(/^B(?:[1-9]|1[0-6])$/)).toHaveLength(16);
  expect(within(row(0)).queryByTestId("sequence-grid-note")).toBeNull();
  const note = within(row(2)).getByTestId("sequence-grid-note");
  expect(note.getAttribute("data-onset-tick")).toBe("480");
  expect(note.getAttribute("data-velocity")).toBe("127");
});

test("the snap selector marks the current snap and reports a change", () => {
  const {callbacks} = renderGrid(0);
  const group = screen.getByRole("group", {name: "Snap"});
  expect(within(group).getByRole("button", {name: "Snap 1/16"})
    .getAttribute("aria-pressed")).toBe("true");
  expect(within(group).getByRole("button", {name: "Snap 1/4"})
    .getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(within(group).getByRole("button", {name: "Snap off"}));
  expect(callbacks.onSnapChange).toHaveBeenCalledWith("off");
});

test("reports the whole Pattern as the viewport when the grid is not scrolled", () => {
  const {callbacks} = renderGrid(0);
  expect(callbacks.onViewportChange).toHaveBeenCalledWith({
    startTick: 0, endTick: 7680,
  });
});
