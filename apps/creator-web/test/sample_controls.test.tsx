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

test("Sample controls stay an editor, not an overview projection", () => {
  renderControls();
  expect(screen.getByRole("button", {name: "One Shot"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Loop"})).toBeTruthy();
  expect(screen.getByRole("slider", {name: "Pad A1 Volume"})).toBeTruthy();
});

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

// --- Sample playback parity (lmdj.project.v5 5.1.0) ---

test("Reverse toggles the Pad's playback direction", async () => {
  const user = userEvent.setup();
  const {onCommit} = renderControls();
  const reverse = screen.getByRole("button", {name: "Reverse"});
  expect(reverse.getAttribute("aria-pressed")).toBe("false");
  await user.click(reverse);
  expect(onCommit).toHaveBeenLastCalledWith({...playback, reverse: true});
});

test("Loop mode appears only while Loop is on", () => {
  const plain = renderControls();
  expect(screen.queryByRole("group", {name: "Pad A1 Loop mode"})).toBeNull();
  plain.unmount();
  renderControls({playback: {...playback, triggerMode: "loop_gate"}});
  expect(screen.getByRole("group", {name: "Pad A1 Loop mode"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Forward"}).getAttribute("aria-pressed"))
    .toBe("true");
});

test("Ping-pong clears the crossfade it cannot use", async () => {
  const user = userEvent.setup();
  const looped = {...playback, triggerMode: "loop_gate" as const, loopCrossfadeFrames: 480};
  const {onCommit} = renderControls({playback: looped});
  await user.click(screen.getByRole("button", {name: "Ping-pong"}));
  expect(onCommit).toHaveBeenLastCalledWith({
    ...looped,
    loopMode: "ping_pong",
    loopCrossfadeFrames: 0,
  });
});

test("Pitch previews every move and commits once in cents", () => {
  const {onPreview, onCommit} = renderControls();
  const pitch = screen.getByRole("slider", {name: "Pad A1 Pitch"});
  fireEvent.pointerDown(pitch, {pointerId: 3});
  fireEvent.change(pitch, {target: {value: "3.5"}});
  expect(onPreview).toHaveBeenLastCalledWith({...playback, pitchCents: 350});
  // The draft shows while previewing; after commit the parent's value shows.
  expect(screen.getByText("+3.5 st")).toBeTruthy();
  fireEvent.pointerUp(pitch, {pointerId: 3});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith({...playback, pitchCents: 350});
});

// Home, End and Page keys move a range input as Arrow keys do, so their
// release must commit too, or the preview plays a value Truth never gets.
test.each(["Home", "End", "PageUp", "PageDown"])(
  "a %s key gesture commits on release",
  (key) => {
    const {onPreview, onCommit} = renderControls();
    const pitch = screen.getByRole("slider", {name: "Pad A1 Pitch"});
    fireEvent.keyDown(pitch, {key});
    fireEvent.change(pitch, {target: {value: "24"}});
    expect(onPreview).toHaveBeenLastCalledWith({...playback, pitchCents: 2_400});
    fireEvent.keyUp(pitch, {key});
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenLastCalledWith({...playback, pitchCents: 2_400});
  },
);

test("leaving a slider commits its pending keyboard gesture once", () => {
  const {onCommit} = renderControls();
  const pan = screen.getByRole("slider", {name: "Pad A1 Pan"});
  fireEvent.change(pan, {target: {value: "30"}});
  fireEvent.blur(pan);
  fireEvent.blur(pan);
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith({...playback, pan: 30});
});

test("Pan previews every move and Escape cancels it", () => {
  const onCancel = vi.fn();
  const {onPreview, onCommit} = renderControls({onCancel});
  const pan = screen.getByRole("slider", {name: "Pad A1 Pan"});
  fireEvent.pointerDown(pan, {pointerId: 4});
  fireEvent.change(pan, {target: {value: "-40"}});
  expect(onPreview).toHaveBeenLastCalledWith({...playback, pan: -40});
  fireEvent.keyDown(pan, {key: "Escape"});
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onCommit).not.toHaveBeenCalled();
  expect(screen.getByText("C")).toBeTruthy();
});

// --- Sample tone parity (lmdj.project.v5 5.2.0) ---

test("Attack previews every move and commits once in milliseconds", () => {
  const {onPreview, onCommit} = renderControls();
  const attack = screen.getByRole("slider", {name: "Pad A1 Attack"});
  fireEvent.pointerDown(attack, {pointerId: 5});
  fireEvent.change(attack, {target: {value: "250"}});
  expect(onPreview).toHaveBeenLastCalledWith({...playback, attackMs: 250});
  expect(screen.getByText("250 ms")).toBeTruthy();
  fireEvent.pointerUp(attack, {pointerId: 5});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith({...playback, attackMs: 250});
});

// The rendered ramp is never shorter than the 2 ms declick, so 0..2 ms show
// as the declick they render.
test("a ramp at or under the declick reads as 2 ms", () => {
  renderControls({playback: {...playback, triggerMode: "gate", attackMs: 1, releaseMs: 0}});
  expect(screen.getAllByText("2 ms")).toHaveLength(2);
});

test("Release edits a releasing Pad and is unavailable on a one-shot", () => {
  const oneShot = renderControls();
  expect(screen.getByRole("slider", {name: "Pad A1 Release"}).hasAttribute("disabled"))
    .toBe(true);
  oneShot.unmount();
  const gated = {...playback, triggerMode: "gate" as const};
  const {onCommit} = renderControls({playback: gated});
  const release = screen.getByRole("slider", {name: "Pad A1 Release"});
  expect(release.hasAttribute("disabled")).toBe(false);
  fireEvent.change(release, {target: {value: "1200"}});
  fireEvent.blur(release);
  expect(onCommit).toHaveBeenLastCalledWith({...gated, releaseMs: 1_200});
});

test("Tone is bipolar: low-pass below centre, high-pass above, off in the deadband", () => {
  const {onPreview, onCommit} = renderControls();
  const tone = screen.getByRole("slider", {name: "Pad A1 Tone"});
  expect(screen.getByText("Off")).toBeTruthy();
  fireEvent.pointerDown(tone, {pointerId: 6});
  fireEvent.change(tone, {target: {value: "-40"}});
  expect(onPreview).toHaveBeenLastCalledWith({...playback, tone: -40});
  expect(screen.getByText("LP 40")).toBeTruthy();
  fireEvent.change(tone, {target: {value: "2"}});
  expect(screen.getByText("Off")).toBeTruthy();
  fireEvent.change(tone, {target: {value: "60"}});
  expect(screen.getByText("HP 60")).toBeTruthy();
  fireEvent.pointerUp(tone, {pointerId: 6});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenLastCalledWith({...playback, tone: 60});
});
