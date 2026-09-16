import {readFileSync} from "node:fs";
import {useRef, useState} from "react";

import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterAll, beforeAll, expect, test, vi} from "vitest";

import {CaptureBuffer} from "../src/capture/capture_buffer";
import {
  CapturePermissionError,
  type CaptureController,
  type CaptureListener,
} from "../src/capture/capture_controller";
import {CapturePanel} from "../src/components/capture_panel";

// jsdom has no real canvas 2d context (would require the native "canvas"
// package); stub just enough of it so the growing-waveform draw path runs
// without jsdom's "not implemented" console noise on every batch. fillRect is
// a vi.fn() (not a no-op) so tests can assert a paint actually happened,
// which is how Finding 1 (the paint effect must re-run once the canvas is
// remounted, even when neither frameCount nor peak changed) is verified.
const fillRectSpy = vi.fn();
const creatorStyles = readFileSync("src/styles.css", "utf8");
let styleElement: HTMLStyleElement;
beforeAll(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    clearRect: () => {},
    fillRect: fillRectSpy,
  } as unknown as CanvasRenderingContext2D);
  styleElement = document.createElement("style");
  styleElement.textContent = creatorStyles;
  document.head.append(styleElement);
});
afterAll(() => {
  styleElement.remove();
  vi.restoreAllMocks();
});

interface FakeController {
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
  inputLabel: string;
}

interface ControllerInstance {
  controller: FakeController;
  listener: CaptureListener;
}

function createFactory(options: {
  startImpl?: () => Promise<void>;
  inputLabel?: string;
} = {}) {
  const instances: ControllerInstance[] = [];
  const makeController = (listener: CaptureListener): CaptureController => {
    const controller: FakeController = {
      start: vi.fn(options.startImpl ?? (async () => {})),
      stop: vi.fn(async () => {}),
      inputLabel: options.inputLabel ?? "Test Microphone",
    };
    instances.push({controller, listener});
    return controller as unknown as CaptureController;
  };
  return {makeController, instances};
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof CapturePanel>> = {}) {
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "committed"}) as const,
  );
  const onClose = vi.fn();
  const view = render(
    <CapturePanel
      padLabel="Pad A1"
      maxCommitFrames={240_000}
      onCommit={onCommit}
      onClose={onClose}
      {...overrides}
    />,
  );
  return {onCommit, onClose, ...view};
}

async function startRecording(instances: ControllerInstance[]) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name: "Record into Pad A1"}));
  await waitFor(() => expect(instances).toHaveLength(1));
  await screen.findByRole("button", {name: "Stop"});
  return instances[0]!;
}

function mockTrimRect(container: HTMLElement, {left = 0, width = 400} = {}) {
  const waveform = container.querySelector<HTMLElement>("[data-capture-trim-waveform]")!;
  Object.defineProperty(waveform, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      left,
      right: left + width,
      width,
      top: 0,
      bottom: 96,
      height: 96,
      x: left,
      y: 0,
      toJSON: () => ({}),
    }),
  });
  return waveform;
}

function captureGrip(container: HTMLElement, kind: "start" | "end") {
  return container.querySelector<HTMLElement>(`[data-capture-grip-zone="${kind}"]`)!;
}

test("renders the idle Record button without ever building the real browser controller", () => {
  renderPanel();
  expect(screen.getByRole("button", {name: "Record into Pad A1"})).toBeTruthy();
});

test("a Sequence Pad stop request preserves the take in the trimming overlay", async () => {
  const {makeController, instances} = createFactory();
  const phases: string[] = [];
  const view = renderPanel({
    makeController,
    stopRequest: 0,
    onPhaseChange: (phase) => phases.push(phase),
  });
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(240_001).fill(0.25)], 0.25));
  view.rerender(
    <CapturePanel padLabel="Pad A1" onCommit={async () => ({kind: "committed"})}
      onClose={() => {}} makeController={makeController} stopRequest={1}
      maxCommitFrames={240_000}
      onPhaseChange={(phase) => phases.push(phase)} />,
  );
  await screen.findByRole("button", {name: "Commit"});
  expect(screen.getByRole("slider", {name: /Pad A1 End/})
    .getAttribute("max")).toBe("240000");
  expect(phases).toContain("trimming");
});

test("a full-buffer selection exposes independently operable Start and End values", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(96_000).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  const start = await screen.findByRole("slider", {name: "Pad A1 Start — 0.000 s"});
  const end = screen.getByRole("slider", {name: "Pad A1 End — 2.000 s"});
  expect((start as HTMLInputElement).value).toBe("0");
  expect(start.getAttribute("max")).toBe("95999");
  expect((end as HTMLInputElement).value).toBe("96000");
  expect(end.getAttribute("min")).toBe("1");
  expect(screen.getByLabelText("Pad A1 Duration").textContent).toBe("2.000 s");
});

test("Start and End grips shrink an initial full selection and commit exact frame values", async () => {
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "committed"}) as const,
  );
  const {container} = renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(8).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);

  const startGrip = captureGrip(container, "start");
  fireEvent.pointerDown(startGrip, {pointerId: 1, clientX: 0, button: 0});
  fireEvent.pointerMove(startGrip, {pointerId: 1, clientX: 100});
  fireEvent.pointerUp(startGrip, {pointerId: 1});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("8");

  const endGrip = captureGrip(container, "end");
  fireEvent.pointerDown(endGrip, {pointerId: 2, clientX: 400, button: 0});
  fireEvent.pointerMove(endGrip, {pointerId: 2, clientX: 300});
  fireEvent.pointerUp(endGrip, {pointerId: 2});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("6");

  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));
  await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(1));
  expect(onCommit.mock.calls[0]![1]).toEqual({startFrame: 2, frameCount: 4});
});

test("releasing outside a Capture grip ends the pointer drag", async () => {
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(8).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);

  const startGrip = captureGrip(container, "start");
  fireEvent.pointerDown(startGrip, {pointerId: 3, clientX: 0, button: 0});
  fireEvent.pointerMove(startGrip, {pointerId: 3, clientX: 100});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");

  fireEvent.pointerUp(window, {pointerId: 3});
  fireEvent.pointerMove(startGrip, {pointerId: 3, clientX: 200});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");
});

test("pointer cancellation restores the Capture selection from before the drag", async () => {
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(8).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);

  const startGrip = captureGrip(container, "start");
  fireEvent.pointerDown(startGrip, {pointerId: 4, clientX: 0, button: 0});
  fireEvent.pointerMove(startGrip, {pointerId: 4, clientX: 100});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");

  fireEvent.pointerCancel(window, {pointerId: 4});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("0");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("8");
});

test("keyboard Start and End move by one frame or 10 ms, cancel, and never cross", async () => {
  const {makeController, instances} = createFactory();
  const {onClose} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  let start = await screen.findByRole("slider", {name: /Pad A1 Start/});
  fireEvent.keyDown(start, {key: "ArrowRight"});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("1");
  start = screen.getByRole("slider", {name: /Pad A1 Start/});
  fireEvent.keyDown(start, {key: "Escape"});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("0");
  expect(onClose).not.toHaveBeenCalled();

  const end = screen.getByRole("slider", {name: /Pad A1 End/});
  fireEvent.keyDown(end, {key: "ArrowLeft", shiftKey: true});
  fireEvent.keyUp(screen.getByRole("slider", {name: /Pad A1 End/}), {key: "ArrowLeft"});
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("47520");
  expect(screen.getByLabelText("Pad A1 Duration").textContent).toBe("0.990 s");

  start = screen.getByRole("slider", {name: /Pad A1 Start/});
  fireEvent.change(start, {target: {value: "47519"}});
  start = screen.getByRole("slider", {name: /Pad A1 Start/});
  fireEvent.keyDown(start, {key: "ArrowRight"});
  fireEvent.keyUp(start, {key: "ArrowRight"});
  fireEvent.keyDown(screen.getByRole("slider", {name: /Pad A1 End/}), {key: "ArrowLeft"});
  fireEvent.keyUp(screen.getByRole("slider", {name: /Pad A1 End/}), {key: "ArrowLeft"});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("47519");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("47520");
});

test("Escape cancels an active pointer trim without closing the Capture panel", async () => {
  const {makeController, instances} = createFactory();
  const {container, onClose} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(8).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);

  const startGrip = captureGrip(container, "start");
  fireEvent.pointerDown(startGrip, {pointerId: 9, clientX: 0, button: 0});
  fireEvent.pointerMove(startGrip, {pointerId: 9, clientX: 100});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");

  fireEvent.keyDown(screen.getByRole("button", {name: "Commit"}), {key: "Escape"});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("0");
  expect(screen.getByRole("dialog", {name: "Pad A1 Pad Capture"})).toBeTruthy();
  expect(onClose).not.toHaveBeenCalled();
});

test("Escape on a focused trim handle with no gesture still closes the Capture panel", async () => {
  const {makeController, instances} = createFactory();
  const {onClose} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  // A focused handle owns Escape only while a trim gesture is in flight; with
  // nothing to abort it must reach ModalDialog and dismiss the session.
  fireEvent.keyDown(await screen.findByRole("slider", {name: /Pad A1 Start/}), {
    key: "Escape",
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  fireEvent.keyDown(screen.getByRole("slider", {name: /Pad A1 End/}), {key: "Escape"});
  expect(onClose).toHaveBeenCalledTimes(2);
});

test("focus leaving a trim handle ends the keyboard gesture that Escape would abort", async () => {
  const {makeController, instances} = createFactory();
  const {onClose} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  // An arrow nudge whose keyup never reaches the handle: the browser sends it
  // to whatever took focus, so a window switch mid-nudge leaves the gesture
  // base behind unless focus loss also ends the gesture.
  const start = await screen.findByRole("slider", {name: /Pad A1 Start/});
  start.focus();
  fireEvent.keyDown(start, {key: "ArrowRight"});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("1");

  screen.getByRole("button", {name: "Commit"}).focus();
  fireEvent.keyDown(screen.getByRole("dialog", {name: "Pad A1 Pad Capture"}), {
    key: "Escape",
  });
  // A stale base would both revert the nudge and swallow the dismissal.
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("1");
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("a stale keyboard base never shadows the abort base of a live grip drag", async () => {
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);

  const start = screen.getByRole("slider", {name: /Pad A1 Start/});
  start.focus();
  fireEvent.keyDown(start, {key: "ArrowRight"});
  fireEvent.keyDown(start, {key: "ArrowRight"});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");

  // Focus deliberately stays on the handle: handleGripPointerDown calls
  // preventDefault(), which suppresses the compatibility mouse event, so a real
  // grip press does not blur the slider either. The pointer gesture itself has
  // to retire the keyboard base.
  // 400 px over 48 000 frames: End sits at clientX 400, drag it to 300.
  const endGrip = captureGrip(container, "end");
  fireEvent.pointerDown(endGrip, {pointerId: 21, clientX: 400, button: 0});
  fireEvent.pointerMove(endGrip, {pointerId: 21, clientX: 300});
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("36000");

  // Escape must abort the drag back to its own base, not to whatever the
  // earlier keyboard nudge recorded.
  fireEvent.keyDown(window, {key: "Escape"});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("48000");
});

test("keyboard Start moves clamp to the remaining Bank quota instead of dead-zoning", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController, maxCommitFrames: 2_400});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  // Walk the 2 400-frame window off zero so the quota, not frame 0, is what
  // bounds Start from below: start 1 200, end 3 000, 1 800 frames selected.
  fireEvent.change(await screen.findByRole("slider", {name: /Pad A1 Start/}),
    {target: {value: "1200"}});
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 End/}),
    {target: {value: "3000"}});
  expect(screen.getByRole("slider", {name: /Pad A1 Start/}).getAttribute("min"))
    .toBe("600");

  fireEvent.keyDown(screen.getByRole("slider", {name: /Pad A1 Start/}),
    {key: "ArrowLeft", shiftKey: true});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("720");

  // 720 - 480 = 240 would ask for 2 760 frames, over the 2 400 quota. The
  // handle must land on the quota bound rather than refuse to move at all.
  fireEvent.keyDown(screen.getByRole("slider", {name: /Pad A1 Start/}),
    {key: "ArrowLeft", shiftKey: true});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("600");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("3000");
  expect(screen.getByLabelText("Pad A1 Duration").textContent).toBe("0.050 s");
});

test("dragging the Start grip past the Bank quota clamps to the quota bound", async () => {
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController, maxCommitFrames: 2_400});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);

  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 Start/}),
    {target: {value: "1200"}});
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 End/}),
    {target: {value: "3000"}});

  // 400 px over 48 000 frames: Start sits at 1 200 frames, i.e. clientX 10.
  const startGrip = captureGrip(container, "start");
  fireEvent.pointerDown(startGrip, {pointerId: 11, clientX: 10, button: 0});
  fireEvent.pointerMove(startGrip, {pointerId: 11, clientX: 0});
  fireEvent.pointerUp(startGrip, {pointerId: 11});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("600");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("3000");
});

test("Capture grip presses preserve grab offset and the waveform middle stays inert", async () => {
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(8).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);

  const startGrip = captureGrip(container, "start");
  fireEvent.pointerDown(startGrip, {pointerId: 5, clientX: 12, button: 0});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("0");
  fireEvent.pointerMove(startGrip, {pointerId: 5, clientX: 175});
  fireEvent.pointerUp(startGrip, {pointerId: 5});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("3");

  const waveform = screen.getByRole("img", {name: "Pad A1 capture waveform"});
  fireEvent.pointerDown(waveform, {pointerId: 6, clientX: 250, button: 0});
  fireEvent.pointerMove(waveform, {pointerId: 6, clientX: 300});
  fireEvent.pointerUp(window, {pointerId: 6});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("3");
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("8");
});

test("adjacent Capture endpoints partition grip zones at their midpoint", async () => {
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(8).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  mockTrimRect(container);
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 End/}), {
    target: {value: "4"},
  });
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 Start/}), {
    target: {value: "3"},
  });

  const startGrip = captureGrip(container, "start");
  const endGrip = captureGrip(container, "end");
  expect(startGrip.style.right).toContain("min(43.75%");
  expect(endGrip.style.left).toContain("max(43.75%");

  fireEvent.pointerDown(startGrip, {pointerId: 7, clientX: 155, button: 0});
  fireEvent.pointerMove(startGrip, {pointerId: 7, clientX: 105});
  fireEvent.pointerUp(startGrip, {pointerId: 7});
  expect((screen.getByRole("slider", {name: /Pad A1 Start/}) as HTMLInputElement).value)
    .toBe("2");

  fireEvent.pointerDown(endGrip, {pointerId: 8, clientX: 195, button: 0});
  fireEvent.pointerMove(endGrip, {pointerId: 8, clientX: 245});
  fireEvent.pointerUp(endGrip, {pointerId: 8});
  expect((screen.getByRole("slider", {name: /Pad A1 End/}) as HTMLInputElement).value)
    .toBe("5");
});

test("Capture trim styles anchor visible grips and keep range inputs out of the pointer path", async () => {
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(8).fill(0.25)], 0.25));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});

  const waveform = container.querySelector<HTMLElement>("[data-capture-trim-waveform]")!;
  const mask = container.querySelector<HTMLElement>("[data-capture-selection-mask=before]")!;
  const grip = container.querySelector<HTMLElement>("[data-capture-grip=start]")!;
  const slider = screen.getByRole("slider", {name: /Pad A1 Start/});
  expect(getComputedStyle(waveform).position).toBe("relative");
  expect(getComputedStyle(waveform).overflow).toBe("visible");
  expect(getComputedStyle(mask).position).toBe("absolute");
  expect(getComputedStyle(grip).width).toBe("14px");
  expect(getComputedStyle(captureGrip(container, "start")).cursor).toBe("ew-resize");
  expect(getComputedStyle(slider).pointerEvents).toBe("none");
});

test("opens as a modal dialog and moves focus to the phase's primary action (P2-D1/P2-D2)", () => {
  renderPanel();
  const dialog = screen.getByRole("dialog", {name: "Pad A1 Pad Capture"});
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(document.activeElement).toBe(
    screen.getByRole("button", {name: "Record into Pad A1"}),
  );
});

test("releases native modal ownership while capture continues behind Sequence", () => {
  const view = renderPanel({backgrounded: false});
  const dialog = view.container.querySelector<HTMLDialogElement>(
    ".capture-panel-dialog",
  )!;
  expect(dialog.open).toBe(true);

  view.rerender(
    <CapturePanel padLabel="Pad A1"
      onCommit={async () => ({kind: "committed"})}
      onClose={() => {}} backgrounded />,
  );
  expect(screen.queryByRole("dialog", {name: "Pad A1 Pad Capture"})).toBeNull();
  expect(view.container.querySelector(".capture-panel-background")?.hasAttribute("hidden"))
    .toBe(true);

  view.rerender(
    <CapturePanel padLabel="Pad A1"
      onCommit={async () => ({kind: "committed"})}
      onClose={() => {}} backgrounded={false} />,
  );
  expect(screen.getByRole("dialog", {name: "Pad A1 Pad Capture"})
    .getAttribute("aria-modal")).toBe("true");
});

test("focus lands on Stop after entering recording and on Commit in trimming (P2-D2)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);

  // Clicking Record unmounted the focused control; the phase transition must
  // land focus on the new phase's primary action, never on <body>.
  const stop = screen.getByRole("button", {name: "Stop"});
  expect(document.activeElement).toBe(stop);

  act(() => listener.onBatch([new Float32Array(4_800).fill(0.2)], 0.2));
  fireEvent.click(stop);
  const commit = await screen.findByRole("button", {name: "Commit"});
  expect(document.activeElement).toBe(commit);
});

test("focus returns to the invoking button on close, restored by the dialog alone (P2-D2)", async () => {
  const user = userEvent.setup();
  function Harness() {
    const [open, setOpen] = useState(false);
    const invokeRef = useRef<HTMLButtonElement | null>(null);
    return (
      <div>
        <button type="button" ref={invokeRef} onClick={() => setOpen(true)}>
          Invoke capture
        </button>
        {open ? (
          <CapturePanel
            padLabel="Pad A1"
            onCommit={async () => ({kind: "committed"}) as const}
            onClose={() => setOpen(false)}
            returnFocus={invokeRef.current}
          />
        ) : null}
      </div>
    );
  }
  render(<Harness />);
  const invoke = screen.getByRole("button", {name: "Invoke capture"});
  await user.click(invoke);
  expect(await screen.findByRole("button", {name: "Record into Pad A1"}))
    .toBeTruthy();
  expect(document.activeElement).toBe(
    screen.getByRole("button", {name: "Record into Pad A1"}),
  );

  await user.click(screen.getByRole("button", {name: "Close"}));
  await waitFor(() => expect(document.activeElement).toBe(invoke));
});

test("Escape closes the panel from idle (P2-D2)", () => {
  const {onClose} = renderPanel();
  fireEvent.keyDown(screen.getByRole("dialog", {name: "Pad A1 Pad Capture"}), {
    key: "Escape",
  });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("Escape during recording stops the capture before closing (P2-D2)", async () => {
  const {makeController, instances} = createFactory();
  const {onClose} = renderPanel({makeController});
  const {controller} = await startRecording(instances);

  fireEvent.keyDown(screen.getByRole("dialog", {name: "Pad A1 Pad Capture"}), {
    key: "Escape",
  });

  expect(controller.stop).toHaveBeenCalledTimes(1);
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("pointer-down on the backdrop does not close the panel (P2-D1)", () => {
  const {onClose} = renderPanel();
  const dialog = screen.getByRole("dialog", {name: "Pad A1 Pad Capture"});
  fireEvent.pointerDown(dialog.parentElement!);
  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog", {name: "Pad A1 Pad Capture"})).toBeTruthy();
});

test("Record drives record then granted, and denial renders a retryable alert (behavior 1)", async () => {
  const user = userEvent.setup();
  const {makeController, instances} = createFactory({
    startImpl: async () => {
      throw new CapturePermissionError("NotAllowedError");
    },
  });
  renderPanel({makeController});

  await user.click(screen.getByRole("button", {name: "Record into Pad A1"}));
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("NotAllowedError");
  const retry = screen.getByRole("button", {name: "Record into Pad A1"});
  expect(retry).toBeTruthy();

  await user.click(retry);
  await waitFor(() => expect(instances).toHaveLength(2));
  expect(instances[1]!.controller.start).toHaveBeenCalledTimes(1);
});

test("recording shows elapsed time, a level meter, and a growing waveform canvas fed by batches (behavior 2)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);

  const canvas = screen.getByRole("img", {name: "Pad A1 capture waveform"});
  expect(canvas.getAttribute("data-frame-count")).toBe("0");

  act(() => listener.onBatch([new Float32Array(4_800).fill(0.5)], 0.5));
  await waitFor(() => expect(canvas.getAttribute("data-frame-count")).toBe("4800"));
  expect(screen.getByText("0.1 s recorded")).toBeTruthy();
  const meter = screen.getByRole("meter", {name: "Pad A1 input level"}) as HTMLMeterElement;
  expect(meter.value).toBeCloseTo(0.5);

  act(() => listener.onBatch([new Float32Array(4_800).fill(0.25)], 0.25));
  await waitFor(() => expect(canvas.getAttribute("data-frame-count")).toBe("9600"));
});

test("a stereo batch sizes the buffer from the batch itself and the frame count advances (behavior 2, Finding 1/5)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);

  const canvas = screen.getByRole("img", {name: "Pad A1 capture waveform"});
  expect(canvas.getAttribute("data-frame-count")).toBe("0");

  // The worklet is the single authority on channel width now (Finding 1): the
  // panel must size CaptureBuffer from the delivered batch, not from any
  // value inferred ahead of time. If it were still sized from a stale
  // mono assumption, CaptureBuffer.append would throw on this 2-channel
  // batch and the frame count would never advance.
  act(() => listener.onBatch(
    [new Float32Array(4_800).fill(0.5), new Float32Array(4_800).fill(-0.5)], 0.5,
  ));
  await waitFor(() => expect(canvas.getAttribute("data-frame-count")).toBe("4800"));
  expect(screen.getByText("0.1 s recorded")).toBeTruthy();

  act(() => listener.onBatch(
    [new Float32Array(4_800).fill(0.25), new Float32Array(4_800).fill(-0.25)], 0.25,
  ));
  await waitFor(() => expect(canvas.getAttribute("data-frame-count")).toBe("9600"));
});

test("a batch that disagrees with the buffer's channel shape stops the capture as device-lost instead of throwing into the event handler (Finding 1)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {controller, listener} = await startRecording(instances);

  // The first batch is mono, sizing the buffer as 1-channel.
  act(() => listener.onBatch([new Float32Array(4_800).fill(0.3)], 0.3));
  await screen.findByText("0.1 s recorded");

  // A later batch disagrees in shape (2 channels): CaptureBuffer.append
  // throws TypeError. Without a try/catch around it, this would escape into
  // the event handler, leaving the UI stuck "recording" with the microphone
  // still live rather than being caught and stopped.
  expect(() => act(() => listener.onBatch(
    [new Float32Array(4_800).fill(0.1), new Float32Array(4_800).fill(0.1)], 0.1,
  ))).not.toThrow();

  await waitFor(() => expect(controller.stop).toHaveBeenCalledTimes(1));
  expect(await screen.findByText(
    "Recording stopped: the microphone became unavailable or its permission changed.",
  )).toBeTruthy();
});

test("reaching capacity stops recording and the controller (S8B-D3, behavior 2)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {controller, listener} = await startRecording(instances);

  act(() => listener.onBatch([new Float32Array(2_880_000).fill(0.1)], 0.1));

  await waitFor(() => expect(controller.stop).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("Recording stopped: reached the 60-second limit."))
    .toBeTruthy();
});

test("blur and hidden stop recording only while recording, then the listeners are gone (behavior 3)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {controller, listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.3)], 0.3));

  fireEvent(window, new Event("blur"));
  await waitFor(() => expect(controller.stop).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("Recording stopped: the window lost focus.")).toBeTruthy();
  expect(screen.getByRole("button", {name: "Commit"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Discard"})).toBeTruthy();

  // Now out of the recording phase: another blur must be a no-op (listener removed).
  fireEvent(window, new Event("blur"));
  expect(controller.stop).toHaveBeenCalledTimes(1);
});

test("document hidden stops recording with the hidden reason (behavior 3)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {controller, listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.3)], 0.3));

  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "hidden",
  });
  fireEvent(document, new Event("visibilitychange"));
  delete (document as {visibilityState?: string}).visibilityState;

  await waitFor(() => expect(controller.stop).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("Recording stopped: the tab was hidden.")).toBeTruthy();
});

test("controller onEnded maps to a device-lost stop (behavior 3)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {controller, listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.3)], 0.3));

  act(() => listener.onEnded("device-lost"));

  await waitFor(() => expect(controller.stop).toHaveBeenCalledTimes(1));
  expect(await screen.findByText(
    "Recording stopped: the microphone became unavailable or its permission changed.",
  )).toBeTruthy();
});

test("trimming clamps the End handle to the queried effective quota", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(480_000).fill(0.2)], 0.2));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  const end = await screen.findByRole("slider", {name: /Pad A1 End/});
  expect((end as HTMLInputElement).value).toBe("240000");
  expect(end.getAttribute("max")).toBe("240000");

  fireEvent.change(end, {target: {value: "300000"}});
  expect((end as HTMLInputElement).value).toBe("240000");
});

test("trimming keeps the complete waveform visible and dims outside the selection", async () => {
  const envelopeSpy = vi.spyOn(CaptureBuffer.prototype, "envelope");
  const {makeController, instances} = createFactory();
  const {container} = renderPanel({makeController});
  const {listener} = await startRecording(instances);

  act(() => listener.onBatch([new Float32Array(480_000).fill(0.2)], 0.2));
  await waitFor(() => expect(envelopeSpy).toHaveBeenLastCalledWith(400, 0, 480_000));

  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await waitFor(() => expect(envelopeSpy).toHaveBeenLastCalledWith(400, 0, 480_000));
  const before = container.querySelector<HTMLElement>("[data-capture-selection-mask=before]")!;
  const after = container.querySelector<HTMLElement>("[data-capture-selection-mask=after]")!;
  expect(before.style.width).toBe("0%");
  expect(after.style.left).toBe("50%");

  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 Start/}), {
    target: {value: "120000"},
  });
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 End/}), {
    target: {value: "192000"},
  });
  await waitFor(() => expect(envelopeSpy).toHaveBeenLastCalledWith(400, 0, 480_000));
  expect(before.style.width).toBe("25%");
  expect(after.style.left).toBe("40%");
  envelopeSpy.mockRestore();
});

test("Crop to selection mutates the same buffer, rebases PCM, and resets the view", async () => {
  const envelopeSpy = vi.spyOn(CaptureBuffer.prototype, "envelope");
  const cropSpy = vi.spyOn(CaptureBuffer.prototype, "crop");
  try {
    const {makeController, instances} = createFactory();
    const onCommit = vi.fn(
      async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
        ({kind: "committed"}) as const,
    );
    renderPanel({makeController, onCommit});
    const {listener} = await startRecording(instances);
    act(() => listener.onBatch([
      Float32Array.from([0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 1]),
    ], 1));
    fireEvent.click(screen.getByRole("button", {name: "Stop"}));

    const cropButton = await screen.findByRole("button", {name: "Crop to selection"});
    expect((cropButton as HTMLButtonElement).disabled).toBe(true);
    const startSlider = screen.getByRole("slider", {name: /Pad A1 Start/});
    fireEvent.change(startSlider, {target: {value: "2"}});
    const endSlider = screen.getByRole("slider", {name: /Pad A1 End/});
    fireEvent.change(endSlider, {target: {value: "6"}});
    expect((cropButton as HTMLButtonElement).disabled).toBe(false);

    await userEvent.setup().click(cropButton);

    await waitFor(() => expect(envelopeSpy).toHaveBeenLastCalledWith(400, 0, 4));
    expect((startSlider as HTMLInputElement).value).toBe("0");
    expect((endSlider as HTMLInputElement).value).toBe("4");
    expect((cropButton as HTMLButtonElement).disabled).toBe(true);

    await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));
    await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(1));
    const [committedBuffer, selection] = onCommit.mock.calls[0]!;
    const originalBuffer = cropSpy.mock.instances[0] as CaptureBuffer;
    expect(committedBuffer).toBe(originalBuffer);
    expect(committedBuffer.frameCount).toBe(4);
    expect(Array.from(committedBuffer.slice(0, 4)[0] ?? []))
      .toEqual([0.25, 0.375, 0.5, 0.625]);
    expect(selection).toEqual({startFrame: 0, frameCount: 4});
  } finally {
    cropSpy.mockRestore();
    envelopeSpy.mockRestore();
  }
});

test("Crop clears a commit error and remains available for another edit", async () => {
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "conflict", message: "Pad slot changed"}) as const,
  );
  renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([
    Float32Array.from([0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 1]),
  ], 1));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await userEvent.setup().click(await screen.findByRole("button", {name: "Commit"}));
  expect((await screen.findByRole("alert")).textContent).toBe("Pad slot changed");

  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 Start/}), {
    target: {value: "2"},
  });
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 End/}), {
    target: {value: "6"},
  });
  await userEvent.setup().click(screen.getByRole("button", {name: "Crop to selection"}));

  expect(screen.queryByRole("alert")).toBeNull();
  const endSlider = screen.getByRole("slider", {name: /Pad A1 End/});
  fireEvent.change(endSlider, {target: {value: "2"}});
  const secondCrop = screen.getByRole("button", {name: "Crop to selection"});
  expect((secondCrop as HTMLButtonElement).disabled).toBe(false);
  await userEvent.setup().click(secondCrop);
  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));

  await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(2));
  const [buffer, selection] = onCommit.mock.calls[1]!;
  expect(buffer.frameCount).toBe(2);
  expect(Array.from(buffer.slice(0, 2)[0] ?? [])).toEqual([0.25, 0.375]);
  expect(selection).toEqual({startFrame: 0, frameCount: 2});
});

test("shows the interruption reason once trimming (behavior 4)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.2)], 0.2));
  act(() => listener.onEnded("device-lost"));
  expect(await screen.findByText(
    "Recording stopped: the microphone became unavailable or its permission changed.",
  )).toBeTruthy();
});

test("Commit calls onCommit with the buffer and selection, then resets to idle (behavior 5)", async () => {
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "committed"}) as const,
  );
  renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(96_000).fill(0.4)], 0.4));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});

  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));

  await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(1));
  const [buffer, selection] = onCommit.mock.calls[0]!;
  expect(buffer).toBeInstanceOf(CaptureBuffer);
  expect(selection).toEqual({startFrame: 0, frameCount: 96_000});
  await screen.findByRole("button", {name: "Record into Pad A1"});
});

test("a conflict result renders a retry affordance with the buffer intact (behavior 5, S8B-D6)", async () => {
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "conflict", message: "Pad slot changed"}) as const,
  );
  renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(96_000).fill(0.4)], 0.4));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await userEvent.setup().click(await screen.findByRole("button", {name: "Commit"}));

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Pad slot changed");
  expect(screen.getByRole("button", {name: "Commit"})).toBeTruthy();
  expect(screen.getByRole("slider", {name: /Pad A1 End/})).toBeTruthy();

  // Retry keeps the same buffer instance — nothing was discarded.
  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));
  await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(2));
  expect(onCommit.mock.calls[1]![0]).toBe(onCommit.mock.calls[0]![0]);
});

test("a digitally silent take is refused at Commit with an explanation, and the take is kept (F4)", async () => {
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "committed"}) as const,
  );
  renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  // The observed F4 failure shape: getUserMedia succeeded, but the whole
  // take is digital silence (the OS silently switched the default input).
  act(() => listener.onBatch([new Float32Array(48_000)], 0));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  await userEvent.setup().click(await screen.findByRole("button", {name: "Commit"}));

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Nothing but digital silence was captured");
  expect(alert.textContent).toContain("switched by the system");
  expect(onCommit).not.toHaveBeenCalled();

  // The take is intact: Commit stays available and is refused again, and
  // Discard still clears the take so the operator can re-record.
  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));
  expect(onCommit).not.toHaveBeenCalled();
  expect(screen.getByRole("slider", {name: /Pad A1 End/})).toBeTruthy();
  await userEvent.setup().click(screen.getByRole("button", {name: "Discard"}));
  expect(await screen.findByRole("button", {name: "Record into Pad A1"})).toBeTruthy();
});

test("a quiet-but-nonzero take commits — the gate is strict zero only (F4)", async () => {
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "committed"}) as const,
  );
  renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.0001)], 0.0001));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  await userEvent.setup().click(await screen.findByRole("button", {name: "Commit"}));

  await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("alert")).toBeNull();
});

test("the silence gate reads the whole take, not the current selection (F4)", async () => {
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "committed"}) as const,
  );
  renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  // The take's only nonzero content sits in its first half; the selection
  // below covers only the silent second half. A selection-scoped gate would
  // refuse this commit; the whole-take gate must let it through.
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.5)], 0.5));
  act(() => listener.onBatch([new Float32Array(48_000)], 0));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  fireEvent.change(await screen.findByRole("slider", {name: /Pad A1 Start/}), {
    target: {value: "48000"},
  });
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 End/}), {
    target: {value: "96000"},
  });

  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));

  await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(1));
  expect(onCommit.mock.calls[0]![1]).toEqual({startFrame: 48_000, frameCount: 48_000});
});

test("shows the current input device name during recording and trimming (F4)", async () => {
  const {makeController, instances} = createFactory({inputLabel: "USB Microphone"});
  renderPanel({makeController});
  const {listener} = await startRecording(instances);
  expect(screen.getByText("Input: USB Microphone")).toBeTruthy();

  act(() => listener.onBatch([new Float32Array(48_000).fill(0.3)], 0.3));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  expect(screen.getByText("Input: USB Microphone")).toBeTruthy();
});

test("falls back to a placeholder when the browser withholds the input label (F4)", async () => {
  const {makeController, instances} = createFactory({inputLabel: ""});
  renderPanel({makeController});
  await startRecording(instances);
  expect(screen.getByText("Input: Default input")).toBeTruthy();
});

test("a device-set change mid-recording shows a non-blocking notice, and the listener leaves with the recording phase (F4)", async () => {
  const mediaDevices = new EventTarget();
  const removeSpy = vi.spyOn(mediaDevices, "removeEventListener");
  Object.defineProperty(window.navigator, "mediaDevices", {
    configurable: true,
    value: mediaDevices,
  });
  try {
    const {makeController, instances} = createFactory();
    renderPanel({makeController});
    const {listener} = await startRecording(instances);

    expect(screen.queryByText(/input devices changed/)).toBeNull();
    act(() => { mediaDevices.dispatchEvent(new Event("devicechange")); });
    expect(await screen.findByText(/input devices changed/)).toBeTruthy();

    act(() => listener.onBatch([new Float32Array(48_000).fill(0.3)], 0.3));
    fireEvent.click(screen.getByRole("button", {name: "Stop"}));
    await screen.findByRole("button", {name: "Commit"});

    // The listener is scoped to the recording phase exactly like the
    // blur/hidden listeners: recording is over, so it was removed, the
    // notice is not part of the trimming view, and a later change is a no-op.
    expect(removeSpy).toHaveBeenCalledWith("devicechange", expect.any(Function));
    expect(screen.queryByText(/input devices changed/)).toBeNull();
    act(() => { mediaDevices.dispatchEvent(new Event("devicechange")); });
    expect(screen.queryByText(/input devices changed/)).toBeNull();
  } finally {
    delete (window.navigator as {mediaDevices?: EventTarget}).mediaDevices;
  }
});

test("the waveform canvas repaints after remounting from committing into commit-error (Finding 1)", async () => {
  const envelopeSpy = vi.spyOn(CaptureBuffer.prototype, "envelope");
  const {makeController, instances} = createFactory();
  const onCommit = vi.fn(
    async (_buffer: CaptureBuffer, _selection: {startFrame: number; frameCount: number}) =>
      ({kind: "conflict", message: "Pad slot changed"}) as const,
  );
  renderPanel({makeController, onCommit});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(96_000).fill(0.4)], 0.4));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await screen.findByRole("button", {name: "Commit"});
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 Start/}), {
    target: {value: "24000"},
  });
  fireEvent.change(screen.getByRole("slider", {name: /Pad A1 End/}), {
    target: {value: "72000"},
  });

  // Baseline: the trimming canvas has painted at least once already.
  expect(fillRectSpy).toHaveBeenCalled();
  fillRectSpy.mockClear();

  // Committing renders only a status paragraph (no canvas), then the conflict
  // result moves the panel into commit-error, which remounts the canvas.
  // Neither state.frameCount nor state.peak changes anywhere across this
  // trimming -> committing -> commit-error path (peak is already 0 once
  // trimming starts, and neither the "commit" nor "commit-failed" reducer
  // cases touch frameCount), so a paint effect depending only on those two
  // values never re-runs against the freshly remounted canvas and the user is
  // left trimming against a blank waveform (S8B-D6). Repainting requires
  // state.phase in the dependency array too.
  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));
  await screen.findByRole("alert");

  expect(fillRectSpy).toHaveBeenCalled();
  expect(envelopeSpy).toHaveBeenLastCalledWith(400, 0, 96_000);
  envelopeSpy.mockRestore();
});

test("Discard resets to idle and clears the buffer", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.2)], 0.2));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));
  await userEvent.setup().click(await screen.findByRole("button", {name: "Discard"}));
  expect(await screen.findByRole("button", {name: "Record into Pad A1"})).toBeTruthy();
});

test("unmounting while recording stops the controller exactly once (behavior 6)", async () => {
  const {makeController, instances} = createFactory();
  const {unmount} = renderPanel({makeController});
  const {controller} = await startRecording(instances);

  unmount();

  await waitFor(() => expect(controller.stop).toHaveBeenCalledTimes(1));
});

test("Close calls onClose", async () => {
  const user = userEvent.setup();
  const {onClose} = renderPanel();
  await user.click(screen.getByRole("button", {name: "Close"}));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("Close stops an in-progress recording exactly once before closing (Finding 3)", async () => {
  const {makeController, instances} = createFactory();
  const {onClose} = renderPanel({makeController});
  const {controller} = await startRecording(instances);

  // Close is rendered even in the "recording" phase. Relying solely on the
  // unmount cleanup would strand the microphone live if the eventual parent
  // hides the panel instead of unmounting it (single-owner lifecycle).
  await userEvent.setup().click(screen.getByRole("button", {name: "Close"}));

  expect(controller.stop).toHaveBeenCalledTimes(1);
  expect(onClose).toHaveBeenCalledTimes(1);
});
