import {createEvent, fireEvent, render, screen} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {EQ_VIEW, EqEditor, freqToX, gainToY} from "../src/components/eq_editor";
import type {PadPlayback} from "../src/runtime/runtime_types";

const playback: Readonly<PadPlayback> = Object.freeze({
  trimStartFrame: 0,
  trimEndFrame: 48_000,
  triggerMode: "gate",
  gainMillidb: 0,
  muted: false,
  reverse: false,
  pitchCents: 0,
  pan: 0,
  loopMode: "forward" as const,
  loopStartFrame: null,
  loopCrossfadeFrames: 0,
  attackMs: 0,
  releaseMs: 0,
  tone: 0,
  eq: {low: null, mid: null, high: null},
});

// jsdom has no layout: pin the plot to its viewBox, so a client coordinate is
// a viewBox coordinate.
function renderEditor(overrides: Partial<React.ComponentProps<typeof EqEditor>> = {}) {
  const onPreview = vi.fn();
  const onCommit = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <EqEditor
      padLabel="Pad A1"
      playback={playback}
      disabled={false}
      audioSuspended={false}
      onPreview={onPreview}
      onCommit={onCommit}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  const plot = view.container.querySelector("svg")!;
  Object.defineProperty(plot, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      left: 0, top: 0, right: EQ_VIEW.width, bottom: EQ_VIEW.height,
      width: EQ_VIEW.width, height: EQ_VIEW.height, x: 0, y: 0, toJSON: () => ({}),
    }),
  });
  return {onPreview, onCommit, onCancel, ...view};
}

const pole = (band: "Low" | "Mid" | "High") =>
  screen.getByRole("slider", {name: `Pad A1 EQ ${band}`});

// jsdom ignores a timeStamp in the event init; a double tap is timed from the
// event's own timeStamp, so the press carries one explicitly.
function press(target: Element, pointerId: number, point: {x: number; y: number}, timeStamp: number) {
  const event = createEvent.pointerDown(target, {pointerId, button: 0, clientX: point.x, clientY: point.y});
  Object.defineProperty(event, "timeStamp", {value: timeStamp});
  fireEvent(target, event);
}

function drag(target: Element, points: {x: number; y: number}[], pointerId = 1, timeStamp = 0) {
  press(target, pointerId, points[0]!, timeStamp);
  for (const point of points.slice(1)) {
    fireEvent.pointerMove(target, {pointerId, clientX: point.x, clientY: point.y});
  }
}

test("a neutral EQ shows three bypassed poles", () => {
  renderEditor();
  for (const band of ["Low", "Mid", "High"] as const) {
    expect(pole(band).getAttribute("aria-valuetext")).toBe(`${band} off`);
  }
});

test("dragging the mid pole previews each move and commits one bell", () => {
  const {onPreview, onCommit} = renderEditor();
  drag(pole("Mid"), [
    {x: freqToX(1_000), y: gainToY(0)},
    {x: freqToX(2_000), y: gainToY(6_000)},
  ]);
  const bell = {freqHz: 2_000, gainMillidb: 6_000, qMilli: 707};
  expect(onPreview).toHaveBeenLastCalledWith({...playback, eq: {low: null, mid: bell, high: null}});
  expect(onCommit).not.toHaveBeenCalled();
  fireEvent.pointerUp(pole("Mid"), {pointerId: 1});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith({...playback, eq: {low: null, mid: bell, high: null}});
});

test("dragging a shelf into the Cut strip makes it a cut", () => {
  const {onCommit} = renderEditor();
  drag(pole("Low"), [
    {x: freqToX(100), y: gainToY(0)},
    {x: freqToX(80), y: EQ_VIEW.floor + EQ_VIEW.cutThreshold + 6},
  ]);
  fireEvent.pointerUp(pole("Low"), {pointerId: 1});
  expect(onCommit).toHaveBeenLastCalledWith({
    ...playback,
    eq: {low: {kind: "cut", freqHz: 80, gainMillidb: -18_000}, mid: null, high: null},
  });
  expect(pole("Low").getAttribute("aria-valuetext")).toBe("Low off");
});

test("a band dragged back to flat is bypassed", () => {
  const shelved = {...playback, eq: {low: null, mid: null, high: {kind: "shelf" as const, freqHz: 8_000, gainMillidb: 4_000}}};
  const {onCommit} = renderEditor({playback: shelved});
  drag(pole("High"), [
    {x: freqToX(8_000), y: gainToY(4_000)},
    {x: freqToX(8_000), y: gainToY(300)},
  ]);
  fireEvent.pointerUp(pole("High"), {pointerId: 1});
  expect(onCommit).toHaveBeenLastCalledWith({...shelved, eq: {low: null, mid: null, high: null}});
});

test("a double tap on the mid pole and a vertical drag set its Q only", () => {
  const bell = {freqHz: 1_200, gainMillidb: -600, qMilli: 1_000};
  const toned = {...playback, eq: {low: null, mid: bell, high: null}};
  const {onCommit} = renderEditor({playback: toned});
  const start = {x: freqToX(1_200), y: gainToY(-600)};
  press(pole("Mid"), 1, start, 100);
  fireEvent.pointerUp(pole("Mid"), {pointerId: 1});
  expect(onCommit).not.toHaveBeenCalled();
  drag(pole("Mid"), [start, {x: start.x + 30, y: start.y - 40}], 2, 300);
  fireEvent.pointerUp(pole("Mid"), {pointerId: 2});
  expect(onCommit).toHaveBeenLastCalledWith({...toned, eq: {low: null, mid: {...bell, qMilli: 2_000}, high: null}});
});

test("two taps further apart than a double tap move the pole instead", () => {
  const bell = {freqHz: 1_200, gainMillidb: -600, qMilli: 1_000};
  const toned = {...playback, eq: {low: null, mid: bell, high: null}};
  const {onCommit} = renderEditor({playback: toned});
  const start = {x: freqToX(1_200), y: gainToY(-600)};
  press(pole("Mid"), 1, start, 100);
  fireEvent.pointerUp(pole("Mid"), {pointerId: 1});
  drag(pole("Mid"), [start, {x: start.x, y: gainToY(6_000)}], 2, 1_000);
  fireEvent.pointerUp(pole("Mid"), {pointerId: 2});
  expect(onCommit).toHaveBeenLastCalledWith({
    ...toned,
    eq: {low: null, mid: {freqHz: 1_200, gainMillidb: 6_000, qMilli: 1_000}, high: null},
  });
});

test("Escape cancels a drag without committing", () => {
  const {onPreview, onCommit, onCancel} = renderEditor();
  drag(pole("Mid"), [
    {x: freqToX(1_000), y: gainToY(0)},
    {x: freqToX(1_000), y: gainToY(9_000)},
  ]);
  expect(onPreview).toHaveBeenCalled();
  fireEvent.keyDown(pole("Mid"), {key: "Escape"});
  expect(onCancel).toHaveBeenCalledTimes(1);
  fireEvent.pointerUp(pole("Mid"), {pointerId: 1});
  expect(onCommit).not.toHaveBeenCalled();
  expect(pole("Mid").getAttribute("aria-valuetext")).toBe("Mid off");
});

test("pointercancel cancels a drag", () => {
  const {onCommit, onCancel} = renderEditor();
  drag(pole("Low"), [
    {x: freqToX(100), y: gainToY(0)},
    {x: freqToX(100), y: gainToY(-6_000)},
  ]);
  fireEvent.pointerCancel(pole("Low"), {pointerId: 1});
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onCommit).not.toHaveBeenCalled();
});

test("arrow keys step gain and frequency, previewing each and committing on release", () => {
  const {onPreview, onCommit} = renderEditor();
  fireEvent.keyDown(pole("High"), {key: "ArrowUp"});
  fireEvent.keyDown(pole("High"), {key: "ArrowUp"});
  expect(onPreview).toHaveBeenLastCalledWith({
    ...playback,
    eq: {low: null, mid: null, high: {kind: "shelf", freqHz: 8_000, gainMillidb: 1_000}},
  });
  fireEvent.keyDown(pole("High"), {key: "ArrowRight"});
  fireEvent.keyUp(pole("High"), {key: "ArrowRight"});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith({
    ...playback,
    eq: {low: null, mid: null, high: {kind: "shelf", freqHz: 8_476, gainMillidb: 1_000}},
  });
});

test("ArrowDown past the floor makes a shelf a cut, and Delete bypasses it", () => {
  const floor = {...playback, eq: {low: {kind: "shelf" as const, freqHz: 120, gainMillidb: -18_000}, mid: null, high: null}};
  const {onCommit, rerender} = renderEditor({playback: floor});
  fireEvent.keyDown(pole("Low"), {key: "ArrowDown"});
  fireEvent.keyUp(pole("Low"), {key: "ArrowDown"});
  const cut = {...floor, eq: {...floor.eq, low: {kind: "cut" as const, freqHz: 120, gainMillidb: -18_000}}};
  expect(onCommit).toHaveBeenLastCalledWith(cut);
  rerender(
    <EqEditor padLabel="Pad A1" playback={cut} disabled={false} audioSuspended={false}
      onPreview={vi.fn()} onCommit={onCommit} onCancel={vi.fn()} />,
  );
  fireEvent.keyDown(pole("Low"), {key: "Delete"});
  fireEvent.keyUp(pole("Low"), {key: "Delete"});
  expect(onCommit).toHaveBeenLastCalledWith({...cut, eq: {low: null, mid: null, high: null}});
});

test("Shift with the arrows sets the mid Q", () => {
  const bell = {freqHz: 1_200, gainMillidb: -600, qMilli: 1_000};
  const toned = {...playback, eq: {low: null, mid: bell, high: null}};
  const {onCommit} = renderEditor({playback: toned});
  fireEvent.keyDown(pole("Mid"), {key: "ArrowUp", shiftKey: true});
  fireEvent.keyUp(pole("Mid"), {key: "ArrowUp", shiftKey: true});
  expect(onCommit).toHaveBeenLastCalledWith({...toned, eq: {low: null, mid: {...bell, qMilli: 1_189}, high: null}});
});

test("a disabled editor ignores pointers and keys", () => {
  const {onPreview, onCommit} = renderEditor({disabled: true});
  drag(pole("Mid"), [
    {x: freqToX(1_000), y: gainToY(0)},
    {x: freqToX(1_000), y: gainToY(9_000)},
  ]);
  fireEvent.keyDown(pole("High"), {key: "ArrowUp"});
  expect(onPreview).not.toHaveBeenCalled();
  expect(onCommit).not.toHaveBeenCalled();
});

test("suspending audio drops a live drag", () => {
  const {onCancel, onCommit, rerender} = renderEditor();
  drag(pole("Mid"), [
    {x: freqToX(1_000), y: gainToY(0)},
    {x: freqToX(1_000), y: gainToY(9_000)},
  ]);
  rerender(
    <EqEditor padLabel="Pad A1" playback={playback} disabled={false} audioSuspended
      onPreview={vi.fn()} onCommit={onCommit} onCancel={onCancel} />,
  );
  expect(onCancel).toHaveBeenCalledTimes(1);
  fireEvent.pointerUp(pole("Mid"), {pointerId: 1});
  expect(onCommit).not.toHaveBeenCalled();
});
