import {fireEvent, render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {SequenceGrid} from "../src/components/sequence_grid";
import type {SequenceGridEditMode} from "../src/state/sequence_grid_model";

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

// The grid maps pointer geometry to ticks and rows: 2 bars are 7680 ticks
// over a 768 px lane (10 ticks per pixel), rows are 20 px lanes on a 22 px
// pitch inside the body.
const LANE_WIDTH = 768;
const ROW_PITCH = 22;
const LANE_HEIGHT = 20;

function mockGridGeometry(container: HTMLElement) {
  const body = container.querySelector(".sequence-grid-body") as HTMLElement;
  Object.defineProperty(body, "getBoundingClientRect", {
    configurable: true,
    value: () => ({left: 0, top: 0, width: LANE_WIDTH, height: ROW_PITCH * 16,
      right: LANE_WIDTH, bottom: ROW_PITCH * 16, x: 0, y: 0, toJSON: () => {}}),
  });
  container.querySelectorAll(".sequence-grid-lane").forEach((lane, index) => {
    Object.defineProperty(lane, "getBoundingClientRect", {
      configurable: true,
      value: () => ({left: 0, top: index * ROW_PITCH, width: LANE_WIDTH,
        height: LANE_HEIGHT, right: LANE_WIDTH, bottom: index * ROW_PITCH + LANE_HEIGHT,
        x: 0, y: index * ROW_PITCH, toJSON: () => {}}),
    });
  });
}

function renderGrid(options: {
  bank?: 0 | 1;
  editMode?: SequenceGridEditMode;
  editing?: {enabled: boolean; reason: string | null};
  selection?: readonly {bank: number; pad: number; onsetTick: number}[];
  defaultVelocity?: number;
} = {}) {
  const callbacks = {
    onSnapChange: vi.fn(),
    onEditModeChange: vi.fn(),
    onViewportChange: vi.fn(),
    onEdit: vi.fn(),
    onSelectionChange: vi.fn(),
    onVelocityChange: vi.fn(),
  };
  const gridProps = {
    pattern,
    bank: options.bank ?? 0 as 0 | 1,
    snap: "1/16" as const,
    editMode: options.editMode ?? "note" as SequenceGridEditMode,
    editing: options.editing ?? {enabled: true, reason: null},
    selection: options.selection ?? [],
    defaultVelocity: options.defaultVelocity ?? 100,
  };
  const view = render(<SequenceGrid {...gridProps} {...callbacks} />);
  mockGridGeometry(view.container);
  const rerender = (overrides: Partial<typeof gridProps> = {}) =>
    view.rerender(<SequenceGrid {...gridProps} {...overrides} {...callbacks} />);
  return {callbacks, view, rerender};
}

const row = (pad: number) =>
  document.querySelector(`.sequence-grid-row[data-pad="${pad}"]`) as HTMLElement;
const lane = (pad: number) =>
  row(pad).querySelector(".sequence-grid-lane") as HTMLElement;
const note = (pad: number) =>
  within(row(pad)).getByTestId("sequence-grid-note");

test("renders the active Bank's sixteen Pad rows with their notes", () => {
  renderGrid({bank: 0});
  const grid = screen.getByTestId("sequence-grid");
  expect(within(grid).getAllByText(/^A(?:[1-9]|1[0-6])$/)).toHaveLength(16);
  const first = note(0);
  expect(first.getAttribute("data-onset-tick")).toBe("0");
  expect(first.getAttribute("data-duration-tick")).toBe("240");
  expect(first.getAttribute("data-velocity")).toBe("100");
  const second = note(1);
  expect(second.getAttribute("data-onset-tick")).toBe("240");
  expect(second.getAttribute("data-duration-tick")).toBe("480");
  expect(within(row(2)).queryByTestId("sequence-grid-note")).toBeNull();
  expect(screen.getByRole("img", {
    name: "Pad A2 note · onset 240 · length 480 · velocity 80",
  })).toBeTruthy();
});

test("follows Bank switching to the other Bank's Pads and notes", () => {
  const {rerender} = renderGrid({bank: 0});
  rerender({bank: 1});
  const grid = screen.getByTestId("sequence-grid");
  expect(within(grid).getAllByText(/^B(?:[1-9]|1[0-6])$/)).toHaveLength(16);
  expect(within(row(0)).queryByTestId("sequence-grid-note")).toBeNull();
  const otherBankNote = note(2);
  expect(otherBankNote.getAttribute("data-onset-tick")).toBe("480");
  expect(otherBankNote.getAttribute("data-velocity")).toBe("127");
});

test("the snap selector marks the current snap and reports a change", () => {
  const {callbacks} = renderGrid({bank: 0});
  const group = screen.getByRole("group", {name: "Snap"});
  expect(within(group).getByRole("button", {name: "Snap 1/16"})
    .getAttribute("aria-pressed")).toBe("true");
  expect(within(group).getByRole("button", {name: "Snap 1/4"})
    .getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(within(group).getByRole("button", {name: "Snap off"}));
  expect(callbacks.onSnapChange).toHaveBeenCalledWith("off");
});

test("reports the whole Pattern as the viewport when the grid is not scrolled", () => {
  const {callbacks} = renderGrid({bank: 0});
  expect(callbacks.onViewportChange).toHaveBeenCalledWith({
    startTick: 0, endTick: 7680,
  });
});

test("scrolling the grid moves the reported viewport window", () => {
  const {callbacks, view} = renderGrid({bank: 0});
  const scroller = view.container.querySelector(".sequence-grid-scroll") as HTMLElement;
  // A 384 px window over the 768 px, two-bar timeline.
  Object.defineProperty(scroller, "getBoundingClientRect", {
    configurable: true,
    value: () => ({left: 0, top: 0, width: 384, height: 352,
      right: 384, bottom: 352, x: 0, y: 0, toJSON: () => {}}),
  });
  const scrollTo = (left: number) => {
    view.container.querySelectorAll(".sequence-grid-lane").forEach((lane, index) => {
      Object.defineProperty(lane, "getBoundingClientRect", {
        configurable: true,
        value: () => ({left: -left, top: index * ROW_PITCH, width: LANE_WIDTH,
          height: LANE_HEIGHT, right: LANE_WIDTH - left,
          bottom: index * ROW_PITCH + LANE_HEIGHT, x: -left, y: index * ROW_PITCH,
          toJSON: () => {}}),
      });
    });
    fireEvent.scroll(scroller);
  };
  scrollTo(0);
  expect(callbacks.onViewportChange).toHaveBeenLastCalledWith({startTick: 0, endTick: 3840});
  scrollTo(384);
  expect(callbacks.onViewportChange).toHaveBeenLastCalledWith({startTick: 3840, endTick: 7680});
});

test("a tap on an empty cell adds one note with the grid defaults", () => {
  const {callbacks} = renderGrid();
  fireEvent.pointerDown(lane(2), {pointerId: 1, clientX: 60, clientY: 54, button: 0});
  fireEvent.pointerUp(window, {pointerId: 1});
  expect(callbacks.onEdit).toHaveBeenCalledTimes(1);
  expect(callbacks.onEdit).toHaveBeenCalledWith({
    remove: [],
    put: [{bank: 0, pad: 2, onsetTick: 480, durationTick: 240, velocity: 100}],
  });
});

test("a tap on a note removes it", () => {
  const {callbacks} = renderGrid();
  fireEvent.pointerDown(note(0), {pointerId: 2, clientX: 5, clientY: 10, button: 0});
  fireEvent.pointerUp(window, {pointerId: 2});
  expect(callbacks.onEdit).toHaveBeenCalledTimes(1);
  expect(callbacks.onEdit).toHaveBeenCalledWith({
    remove: [{bank: 0, pad: 0, onsetTick: 0}],
    put: [],
  });
});

test("a Bank switch mid-gesture cancels it instead of editing the new Bank", () => {
  const {callbacks, rerender} = renderGrid({bank: 0});
  fireEvent.pointerDown(note(0), {pointerId: 9, clientX: 5, clientY: 10, button: 0});
  fireEvent.pointerMove(note(0), {pointerId: 9, clientX: 125, clientY: 10});
  rerender({bank: 1});
  fireEvent.pointerUp(window, {pointerId: 9});
  expect(callbacks.onEdit).not.toHaveBeenCalled();
});

test("dragging a note's body moves it; dragging back to the start sends nothing", () => {
  const {callbacks} = renderGrid();
  fireEvent.pointerDown(note(0), {pointerId: 3, clientX: 5, clientY: 10, button: 0});
  fireEvent.pointerMove(note(0), {pointerId: 3, clientX: 125, clientY: 10});
  fireEvent.pointerUp(window, {pointerId: 3});
  expect(callbacks.onEdit).toHaveBeenCalledTimes(1);
  expect(callbacks.onEdit).toHaveBeenCalledWith({
    remove: [{bank: 0, pad: 0, onsetTick: 0}],
    put: [{bank: 0, pad: 0, onsetTick: 1200, durationTick: 240, velocity: 100}],
  });

  callbacks.onEdit.mockClear();
  fireEvent.pointerDown(note(0), {pointerId: 4, clientX: 5, clientY: 10, button: 0});
  fireEvent.pointerMove(note(0), {pointerId: 4, clientX: 125, clientY: 10});
  fireEvent.pointerMove(note(0), {pointerId: 4, clientX: 5, clientY: 10});
  fireEvent.pointerUp(window, {pointerId: 4});
  expect(callbacks.onEdit).not.toHaveBeenCalled();
});

test("dragging a note's end resizes it", () => {
  const {callbacks} = renderGrid();
  const handle = within(note(1)).getByTestId("sequence-grid-note-end");
  fireEvent.pointerDown(handle, {pointerId: 5, clientX: 72, clientY: 32, button: 0});
  fireEvent.pointerMove(handle, {pointerId: 5, clientX: 168, clientY: 32});
  fireEvent.pointerUp(window, {pointerId: 5});
  expect(callbacks.onEdit).toHaveBeenCalledTimes(1);
  expect(callbacks.onEdit).toHaveBeenCalledWith({
    remove: [],
    put: [{bank: 0, pad: 1, onsetTick: 240, durationTick: 1440, velocity: 80}],
  });
});

test("a vertical drag in VEL mode sets velocity and the grid's default", () => {
  const {callbacks} = renderGrid({editMode: "vel"});
  fireEvent.pointerDown(note(0), {pointerId: 6, clientX: 5, clientY: 2, button: 0});
  fireEvent.pointerMove(note(0), {pointerId: 6, clientX: 5, clientY: 10});
  fireEvent.pointerUp(window, {pointerId: 6});
  expect(callbacks.onEdit).toHaveBeenCalledTimes(1);
  expect(callbacks.onEdit).toHaveBeenCalledWith({
    remove: [],
    put: [{bank: 0, pad: 0, onsetTick: 0, durationTick: 240, velocity: 64}],
  });
  expect(callbacks.onVelocityChange).toHaveBeenCalledWith(64);
});

test("a moveless tap in VEL mode sends nothing", () => {
  const {callbacks} = renderGrid({editMode: "vel"});
  fireEvent.pointerDown(note(0), {pointerId: 7, clientX: 5, clientY: 10, button: 0});
  fireEvent.pointerUp(window, {pointerId: 7});
  expect(callbacks.onEdit).not.toHaveBeenCalled();
  expect(callbacks.onVelocityChange).not.toHaveBeenCalled();
});

test("a drag on empty space box-selects the covered notes", () => {
  const {callbacks} = renderGrid();
  fireEvent.pointerDown(lane(0), {pointerId: 8, clientX: 700, clientY: 10, button: 0});
  fireEvent.pointerMove(lane(0), {pointerId: 8, clientX: 20, clientY: 40});
  expect(screen.getByTestId("sequence-grid-box")).toBeTruthy();
  fireEvent.pointerUp(window, {pointerId: 8});
  expect(callbacks.onEdit).not.toHaveBeenCalled();
  expect(callbacks.onSelectionChange).toHaveBeenCalledWith([
    {bank: 0, pad: 0, onsetTick: 0},
    {bank: 0, pad: 1, onsetTick: 240},
  ]);
});

test("a selection deletes and moves as one batch command", () => {
  const selection = [
    {bank: 0, pad: 0, onsetTick: 0},
    {bank: 0, pad: 1, onsetTick: 240},
  ];
  const {callbacks, rerender} = renderGrid();
  rerender({selection});
  const batch = screen.getByRole("group", {name: "Note selection"});
  expect(batch.textContent).toContain("2 selected");
  fireEvent.click(within(batch).getByRole("button", {name: "Delete"}));
  expect(callbacks.onEdit).toHaveBeenCalledTimes(1);
  expect(callbacks.onEdit).toHaveBeenCalledWith({remove: selection, put: []});
  expect(callbacks.onSelectionChange).toHaveBeenCalledWith([]);

  callbacks.onEdit.mockClear();
  rerender({selection});
  fireEvent.pointerDown(note(0), {pointerId: 9, clientX: 5, clientY: 10, button: 0});
  fireEvent.pointerMove(note(0), {pointerId: 9, clientX: 125, clientY: 54});
  fireEvent.pointerUp(window, {pointerId: 9});
  expect(callbacks.onEdit).toHaveBeenCalledTimes(1);
  expect(callbacks.onEdit).toHaveBeenCalledWith({
    remove: selection,
    put: [
      {bank: 0, pad: 2, onsetTick: 1200, durationTick: 240, velocity: 100},
      {bank: 0, pad: 3, onsetTick: 1440, durationTick: 480, velocity: 80},
    ],
  });
});

test("a disabled grid shows the reason and admits no gesture", () => {
  const {callbacks} = renderGrid({
    editing: {enabled: false, reason: "Recording — stop recording to edit the grid."},
    selection: [{bank: 0, pad: 0, onsetTick: 0}],
  });
  expect(screen.getByRole("status")
    .textContent).toBe("Recording — stop recording to edit the grid.");
  fireEvent.pointerDown(lane(3), {pointerId: 10, clientX: 60, clientY: 76, button: 0});
  fireEvent.pointerUp(window, {pointerId: 10});
  fireEvent.pointerDown(note(0), {pointerId: 11, clientX: 5, clientY: 10, button: 0});
  fireEvent.pointerUp(window, {pointerId: 11});
  expect(callbacks.onEdit).not.toHaveBeenCalled();
  expect(callbacks.onSelectionChange).not.toHaveBeenCalled();
  expect(within(screen.getByRole("group", {name: "Note selection"}))
    .getByRole("button", {name: "Delete"})).toHaveProperty("disabled", true);
});
