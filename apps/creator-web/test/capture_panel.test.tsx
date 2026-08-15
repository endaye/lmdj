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
// without jsdom's "not implemented" console noise on every batch.
beforeAll(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    clearRect: () => {},
    fillRect: () => {},
  } as unknown as CanvasRenderingContext2D);
});
afterAll(() => vi.restoreAllMocks());

interface FakeController {
  channelCount: number;
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
}

interface ControllerInstance {
  controller: FakeController;
  listener: CaptureListener;
}

function createFactory(options: {
  channelCount?: number;
  startImpl?: () => Promise<void>;
} = {}) {
  const instances: ControllerInstance[] = [];
  const makeController = (listener: CaptureListener): CaptureController => {
    const controller: FakeController = {
      channelCount: options.channelCount ?? 1,
      start: vi.fn(options.startImpl ?? (async () => {})),
      stop: vi.fn(async () => {}),
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

test("renders the idle Record button without ever building the real browser controller", () => {
  renderPanel();
  expect(screen.getByRole("button", {name: "Record into Pad A1"})).toBeTruthy();
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
  expect(await screen.findByText("Recording stopped: the input device became unavailable."))
    .toBeTruthy();
});

test("trimming clamps the selection sliders to COMMIT_MAX_FRAMES (behavior 4)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(480_000).fill(0.2)], 0.2));
  fireEvent.click(screen.getByRole("button", {name: "Stop"}));

  const length = await screen.findByRole("slider", {name: "Pad A1 Selection length"});
  expect((length as HTMLInputElement).value).toBe("240000");
  expect(length.getAttribute("max")).toBe("240000");

  fireEvent.change(length, {target: {value: "300000"}});
  expect((length as HTMLInputElement).value).toBe("240000");
});

test("shows the interruption reason once trimming (behavior 4)", async () => {
  const {makeController, instances} = createFactory();
  renderPanel({makeController});
  const {listener} = await startRecording(instances);
  act(() => listener.onBatch([new Float32Array(48_000).fill(0.2)], 0.2));
  act(() => listener.onEnded("device-lost"));
  expect(await screen.findByText("Recording stopped: the input device became unavailable."))
    .toBeTruthy();
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
  expect(screen.getByRole("slider", {name: "Pad A1 Selection length"})).toBeTruthy();

  // Retry keeps the same buffer instance — nothing was discarded.
  await userEvent.setup().click(screen.getByRole("button", {name: "Commit"}));
  await waitFor(() => expect(onCommit).toHaveBeenCalledTimes(2));
  expect(onCommit.mock.calls[1]![0]).toBe(onCommit.mock.calls[0]![0]);
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
