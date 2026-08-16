import {readFileSync} from "node:fs";

import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {useState} from "react";
import {afterAll, beforeAll, expect, test, vi} from "vitest";

import {SampleControls} from "../src/components/sample_controls";
import type {PadPlayback} from "../src/runtime/runtime_types";
const creatorStyles = readFileSync("src/styles.css", "utf8");

let styleElement: HTMLStyleElement;
beforeAll(() => {
  styleElement = document.createElement("style");
  styleElement.textContent = creatorStyles;
  document.head.append(styleElement);
});
afterAll(() => styleElement.remove());

const playback: Readonly<PadPlayback> = Object.freeze({
  trimStartFrame: 0,
  trimEndFrame: 48_000,
  triggerMode: "one_shot",
  gainMillidb: 0,
  muted: false,
});

function renderControls(overrides: Partial<React.ComponentProps<typeof SampleControls>> = {}) {
  const onPreview = vi.fn();
  const onCommit = vi.fn();
  const onReset = vi.fn();
  const view = render(
    <SampleControls
      padLabel="Pad A1"
      playback={playback}
      audioSuspended={false}
      onPreview={onPreview}
      onCommit={onCommit}
      onReset={onReset}
      {...overrides}
    />,
  );
  return {onPreview, onCommit, onReset, ...view};
}

test("Loop switches the trigger label from One Shot to Hold without overlapping state", async () => {
  const user = userEvent.setup();
  const first = renderControls();
  expect(screen.getByRole("button", {name: "One Shot"}).getAttribute("aria-pressed"))
    .toBe("true");
  await user.click(screen.getByRole("button", {name: "Loop"}));
  expect(first.onCommit).toHaveBeenLastCalledWith({...playback, triggerMode: "loop_toggle"});
  first.unmount();

  const looped = renderControls({playback: {...playback, triggerMode: "loop_toggle"}});
  expect(screen.queryByRole("button", {name: "One Shot"})).toBeNull();
  expect(screen.getByRole("button", {name: "Hold"}).getAttribute("aria-pressed"))
    .toBe("true");
  await user.click(screen.getByRole("button", {name: "Hold"}));
  expect(looped.onCommit).toHaveBeenLastCalledWith({...playback, triggerMode: "loop_gate"});
});

test("Mute is independent and Volume previews then commits in 0.1 dB steps", () => {
  const {onPreview, onCommit} = renderControls();
  fireEvent.click(screen.getByRole("button", {name: "Mute"}));
  expect(onCommit).toHaveBeenLastCalledWith({...playback, muted: true});

  const volume = screen.getByRole("slider", {name: "Pad A1 Volume"});
  expect(volume.getAttribute("step")).toBe("0.1");
  fireEvent.pointerDown(volume, {pointerId: 2});
  fireEvent.change(volume, {target: {value: "-3.2"}});
  expect(onPreview).toHaveBeenLastCalledWith({...playback, gainMillidb: -3_200});
  expect(onCommit).toHaveBeenCalledTimes(1);
  fireEvent.pointerUp(volume, {pointerId: 2});
  expect(onCommit).toHaveBeenLastCalledWith({...playback, gainMillidb: -3_200});
  expect(onCommit).toHaveBeenCalledTimes(2);
});

test("ignores a non-finite Volume input without previewing or committing NaN", () => {
  const {onPreview, onCommit} = renderControls();
  const volume = screen.getByRole("slider", {name: "Pad A1 Volume"});
  Object.defineProperty(volume, "valueAsNumber", {
    configurable: true,
    get: () => Number.NaN,
  });

  fireEvent.pointerDown(volume, {pointerId: 3});
  fireEvent.change(volume, {target: {value: "-3"}});
  fireEvent.pointerUp(volume, {pointerId: 3});

  expect(onPreview).not.toHaveBeenCalled();
  expect(onCommit).not.toHaveBeenCalled();
});

test("commits Volume once when the pointer is released off the control", () => {
  const {onCommit} = renderControls();
  const volume = screen.getByRole("slider", {name: "Pad A1 Volume"});

  fireEvent.pointerDown(volume, {pointerId: 4});
  fireEvent.change(volume, {target: {value: "-2.5"}});
  fireEvent.pointerUp(window, {pointerId: 4});
  fireEvent.pointerUp(window, {pointerId: 4});

  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenCalledWith({...playback, gainMillidb: -2_500});
});

test.each(["pointer", "keyboard"] as const)(
  "commits controlled Volume feedback once on $completion completion",
  (completion) => {
    const onPreview = vi.fn();
    const onCommit = vi.fn();
    function ControlledControls() {
      const [current, setCurrent] = useState(playback);
      return (
        <SampleControls
          padLabel="Pad A1"
          playback={current}
          audioSuspended={false}
          onPreview={(next) => {
            onPreview(next);
            setCurrent(next);
          }}
          onCommit={onCommit}
          onReset={() => {}}
        />
      );
    }
    render(<ControlledControls />);
    const volume = screen.getByRole("slider", {name: "Pad A1 Volume"});

    if (completion === "pointer") {
      fireEvent.pointerDown(volume, {pointerId: 14});
    }
    fireEvent.change(volume, {target: {value: "-4.5"}});
    expect(onPreview).toHaveBeenCalledTimes(1);
    expect(onCommit).not.toHaveBeenCalled();
    if (completion === "pointer") {
      fireEvent.pointerUp(volume, {pointerId: 14});
    } else {
      fireEvent.keyUp(volume, {key: "ArrowLeft"});
    }

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith({...playback, gainMillidb: -4_500});
  },
);

test("Reset requires an explicit accessible confirmation", async () => {
  const user = userEvent.setup();
  const {onReset} = renderControls();
  await user.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
  expect(screen.getByRole("dialog", {name: "Reset Pad A1?"})).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Cancel reset"}));
  expect(onReset).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
  await user.click(screen.getByRole("button", {name: "Confirm reset"}));
  expect(onReset).toHaveBeenCalledTimes(1);
});

test("contains Reset focus, cancels with Escape, and restores its trigger", async () => {
  const user = userEvent.setup();
  renderControls();
  const reset = screen.getByRole("button", {name: "Reset Pad to Defaults"});
  const loop = screen.getByRole("button", {name: "Loop"});
  reset.focus();
  await user.click(reset);

  const dialog = screen.getByRole("dialog", {name: "Reset Pad A1?"});
  const cancel = screen.getByRole("button", {name: "Cancel reset"});
  const confirm = screen.getByRole("button", {name: "Confirm reset"});
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(document.activeElement).toBe(cancel);
  expect(loop.closest("[inert]")).not.toBeNull();

  confirm.focus();
  fireEvent.keyDown(dialog, {key: "Tab"});
  expect(document.activeElement).toBe(cancel);
  cancel.focus();
  fireEvent.keyDown(dialog, {key: "Tab", shiftKey: true});
  expect(document.activeElement).toBe(confirm);

  fireEvent.keyDown(dialog, {key: "Escape"});
  expect(screen.queryByRole("dialog", {name: "Reset Pad A1?"})).toBeNull();
  expect(document.activeElement).toBe(reset);
});

test("restores Reset confirmation focus to a safe enabled fallback", async () => {
  const user = userEvent.setup();
  function DisablingResetControls() {
    const [disabled, setDisabled] = useState(false);
    return (
      <div>
        <button type="button">Safe focus fallback</button>
        <SampleControls
          padLabel="Pad A1"
          playback={playback}
          audioSuspended={false}
          disabled={disabled}
          onPreview={() => {}}
          onCommit={() => {}}
          onReset={() => setDisabled(true)}
        />
      </div>
    );
  }

  render(<DisablingResetControls />);
  const reset = screen.getByRole("button", {name: "Reset Pad to Defaults"});
  await user.click(reset);
  await user.click(screen.getByRole("button", {name: "Confirm reset"}));

  await waitFor(() => expect(reset.hasAttribute("disabled")).toBe(true));
  expect(document.activeElement).toBe(
    screen.getByRole("button", {name: "Safe focus fallback"}),
  );
});

test("keeps editing available while audio preview is suspended", () => {
  renderControls({audioSuspended: true});
  expect(screen.getByText("Activate Audio to preview")).toBeTruthy();
  expect(screen.getByRole("button", {name: "Loop"}).hasAttribute("disabled"))
    .toBe(false);
  expect(screen.getByRole("slider", {name: "Pad A1 Volume"}).hasAttribute("disabled"))
    .toBe(false);
});

test("every toggle, value control, and confirmation action has a 44 px target", async () => {
  const user = userEvent.setup();
  renderControls();
  const backgroundActions = [
    ...screen.getAllByRole("button"),
    ...screen.getAllByRole("slider"),
  ];
  await user.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
  for (const action of [
    ...backgroundActions,
    ...screen.getAllByRole("button"),
  ]) {
    expect(
      getComputedStyle(action).minHeight,
      action.getAttribute("aria-label") ?? action.textContent ?? action.tagName,
    ).toBe("44px");
  }
});
