import {fireEvent, render, screen} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {ValueSlider} from "../src/components/value_slider";

function renderSlider(
  overrides: Partial<React.ComponentProps<typeof ValueSlider>> = {},
) {
  const onPreview = vi.fn();
  const onCommit = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <ValueSlider
      label="Level"
      ariaLabel="Level"
      className="level-control"
      value={10}
      min={0}
      max={100}
      step={1}
      format={(value) => `${value} units`}
      disabled={false}
      onPreview={onPreview}
      onCommit={onCommit}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return {onPreview, onCommit, onCancel, ...view};
}

test("a drag previews every move and commits once on release", () => {
  const {onPreview, onCommit} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.pointerDown(level, {pointerId: 2});
  fireEvent.change(level, {target: {value: "42"}});
  expect(onPreview).toHaveBeenLastCalledWith(42);
  expect(screen.getByText("42 units")).toBeTruthy();
  expect(onCommit).not.toHaveBeenCalled();
  fireEvent.change(level, {target: {value: "43"}});
  expect(onPreview).toHaveBeenLastCalledWith(43);
  expect(onCommit).not.toHaveBeenCalled();
  fireEvent.pointerUp(level, {pointerId: 2});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith(43);
});

test("commits once when the pointer is released off the control", () => {
  const {onCommit} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.pointerDown(level, {pointerId: 4});
  fireEvent.change(level, {target: {value: "25"}});
  fireEvent.pointerUp(window, {pointerId: 4});
  fireEvent.pointerUp(window, {pointerId: 4});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith(25);
});

test("a preview clamps to the range instead of committing past it", () => {
  const {onPreview, onCommit} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.pointerDown(level, {pointerId: 5});
  fireEvent.change(level, {target: {value: "999"}});
  expect(onPreview).toHaveBeenLastCalledWith(100);
  fireEvent.pointerUp(level, {pointerId: 5});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith(100);
});

test("a gesture that returns to its base value never commits", () => {
  const {onCommit} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.pointerDown(level, {pointerId: 6});
  fireEvent.change(level, {target: {value: "42"}});
  fireEvent.change(level, {target: {value: "10"}});
  fireEvent.pointerUp(level, {pointerId: 6});
  expect(onCommit).not.toHaveBeenCalled();
  expect(screen.getByText("10 units")).toBeTruthy();
});

test.each([
  "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
  "Home", "End", "PageUp", "PageDown",
])("a %s key gesture commits on release", (key) => {
  const {onPreview, onCommit} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.keyDown(level, {key});
  fireEvent.change(level, {target: {value: "64"}});
  expect(onPreview).toHaveBeenLastCalledWith(64);
  expect(onCommit).not.toHaveBeenCalled();
  fireEvent.keyUp(level, {key});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith(64);
});

test("Escape cancels a gesture and restores the committed readout", () => {
  const {onCommit, onCancel} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.pointerDown(level, {pointerId: 7});
  fireEvent.change(level, {target: {value: "80"}});
  expect(screen.getByText("80 units")).toBeTruthy();
  fireEvent.keyDown(level, {key: "Escape"});
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(screen.getByText("10 units")).toBeTruthy();
  fireEvent.pointerUp(level, {pointerId: 7});
  expect(onCommit).not.toHaveBeenCalled();
});

test("pointercancel cancels a gesture without committing", () => {
  const {onCommit, onCancel} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.pointerDown(level, {pointerId: 8});
  fireEvent.change(level, {target: {value: "80"}});
  fireEvent.pointerCancel(level, {pointerId: 8});
  expect(onCancel).toHaveBeenCalledTimes(1);
  fireEvent.pointerUp(level, {pointerId: 8});
  expect(onCommit).not.toHaveBeenCalled();
});

test("leaving the slider commits a pending keyboard gesture once", () => {
  const {onCommit} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.change(level, {target: {value: "30"}});
  fireEvent.blur(level);
  fireEvent.blur(level);
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith(30);
});

test("a disabled slider takes no gesture", () => {
  renderSlider({disabled: true});
  const level = screen.getByRole("slider", {name: "Level"});
  expect(level.hasAttribute("disabled")).toBe(true);
});

test("ignores a non-finite input without previewing or committing NaN", () => {
  const {onPreview, onCommit} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  Object.defineProperty(level, "valueAsNumber", {
    configurable: true,
    get: () => Number.NaN,
  });
  fireEvent.pointerDown(level, {pointerId: 9});
  fireEvent.change(level, {target: {value: "42"}});
  fireEvent.pointerUp(level, {pointerId: 9});
  expect(onPreview).not.toHaveBeenCalled();
  expect(onCommit).not.toHaveBeenCalled();
});

test("suspending audio mid-gesture clears it without committing or cancelling", () => {
  const {onCommit, onCancel, rerender} = renderSlider();
  const level = screen.getByRole("slider", {name: "Level"});
  fireEvent.pointerDown(level, {pointerId: 10});
  fireEvent.change(level, {target: {value: "80"}});
  expect(screen.getByText("80 units")).toBeTruthy();
  rerender(
    <ValueSlider
      label="Level"
      ariaLabel="Level"
      className="level-control"
      value={10}
      min={0}
      max={100}
      step={1}
      format={(value) => `${value} units`}
      disabled={false}
      audioSuspended
      onPreview={() => {}}
      onCommit={onCommit}
      onCancel={onCancel}
    />,
  );
  expect(screen.getByText("10 units")).toBeTruthy();
  fireEvent.pointerUp(level, {pointerId: 10});
  expect(onCommit).not.toHaveBeenCalled();
  expect(onCancel).not.toHaveBeenCalled();
});
