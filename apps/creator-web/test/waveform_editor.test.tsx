import {readFileSync} from "node:fs";

import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterAll, beforeAll, expect, test, vi} from "vitest";

import {WaveformEditor} from "../src/components/waveform_editor";
import type {
  PadPlayback,
  WaveformEnvelope,
} from "../src/runtime/runtime_types";
const creatorStyles = readFileSync("src/styles.css", "utf8");

let styleElement: HTMLStyleElement;
beforeAll(() => {
  styleElement = document.createElement("style");
  styleElement.textContent = creatorStyles;
  document.head.append(styleElement);
});
afterAll(() => styleElement.remove());

const playback: Readonly<PadPlayback> = Object.freeze({
  trimStartFrame: 1,
  trimEndFrame: 7,
  triggerMode: "one_shot",
  gainMillidb: 0,
  muted: false,
});

const envelope: Readonly<WaveformEnvelope> = Object.freeze({
  metadata: Object.freeze({
    sampleRate: 44_100,
    channels: 1,
    sourceFrames: 8,
  }),
  algorithmVersion: 1,
  buckets: Object.freeze([
    Object.freeze({startFrame: 0, endFrame: 2, peakMagnitude: 0}),
    Object.freeze({startFrame: 2, endFrame: 4, peakMagnitude: 8_192}),
    Object.freeze({startFrame: 4, endFrame: 6, peakMagnitude: 32_768}),
    Object.freeze({startFrame: 6, endFrame: 8, peakMagnitude: 16_384}),
  ]),
  projectRevision: 4,
});

function renderEditor(overrides: Partial<React.ComponentProps<typeof WaveformEditor>> = {}) {
  const onPreview = vi.fn();
  const onCommit = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <WaveformEditor
      padLabel="Pad A1"
      envelope={envelope}
      metadata={envelope.metadata}
      projectRevision={envelope.projectRevision}
      playback={playback}
      playheadFrame={4}
      onPreview={onPreview}
      onCommit={onCommit}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return {onPreview, onCommit, onCancel, ...view};
}

test("renders one integer-bucket path mirrored around the zero line", () => {
  const {container} = renderEditor();
  const waveform = container.querySelector<SVGPathElement>("path[data-waveform]");
  expect(waveform).not.toBeNull();
  const coordinates = [...waveform!.getAttribute("d")!.matchAll(/(?:M|L) (\d+) (\d+)/g)]
    .map((match) => [Number(match[1]), Number(match[2])] as const);
  expect(coordinates).toHaveLength(16);
  expect(coordinates.slice(0, 8).map((point) => point[0])).toEqual([
    0, 100, 100, 200, 200, 300, 300, 400,
  ]);
  expect(coordinates.slice(0, 8).map((point) => point[1])).toEqual([
    80, 80, 64, 64, 16, 16, 48, 48,
  ]);
  expect(coordinates.slice(8).map((point) => point[1])).toEqual([
    112, 112, 144, 144, 96, 96, 80, 80,
  ]);
  for (let index = 0; index < 8; index += 1) {
    expect(coordinates[index]![1] + coordinates[15 - index]![1]).toBe(160);
  }
  expect(container.querySelectorAll("rect[data-selection-mask]")).toHaveLength(2);
  expect(container.querySelector("line[data-zero-line]")).not.toBeNull();
  expect(container.querySelector("line[data-playhead]")).not.toBeNull();
});

test("positions uneven peak buckets from their source-frame bounds", () => {
  const unevenEnvelope: WaveformEnvelope = {
    ...envelope,
    buckets: [
      {startFrame: 0, endFrame: 1, peakMagnitude: 0},
      {startFrame: 1, endFrame: 7, peakMagnitude: 8_192},
      {startFrame: 7, endFrame: 8, peakMagnitude: 32_768},
    ],
  };
  const {container} = renderEditor({envelope: unevenEnvelope});
  const coordinates = [
    ...container.querySelector<SVGPathElement>("path[data-waveform]")!
      .getAttribute("d")!.matchAll(/(?:M|L) (\d+) (\d+)/g),
  ].map((match) => [Number(match[1]), Number(match[2])] as const);
  expect(coordinates.slice(0, 6).map(([x]) => x)).toEqual([
    0, 50, 50, 350, 350, 400,
  ]);
});

test("initializes the real source viewport before an asynchronous envelope arrives", async () => {
  const view = renderEditor({envelope: null});
  const editor = view.container.querySelector<HTMLElement>("[data-waveform-viewport]")!;
  expect([editor.dataset.viewportStart, editor.dataset.viewportEnd]).toEqual(["0", "8"]);

  view.rerender(
    <WaveformEditor
      padLabel="Pad A1"
      envelope={envelope}
      metadata={envelope.metadata}
      projectRevision={envelope.projectRevision}
      playback={playback}
      playheadFrame={4}
      onPreview={view.onPreview}
      onCommit={view.onCommit}
      onCancel={view.onCancel}
    />,
  );

  await waitFor(() => {
    expect([editor.dataset.viewportStart, editor.dataset.viewportEnd]).toEqual(["0", "8"]);
  });
});

test("refuses to draw a waveform from a non-integer peak bucket", () => {
  const malformed = {
    ...envelope,
    buckets: [{startFrame: 0, endFrame: 8, peakMagnitude: 0.5}],
  } as WaveformEnvelope;
  const {container} = renderEditor({envelope: malformed});
  expect(container.querySelector("path[data-waveform]")).toBeNull();
  expect(screen.getByText("Waveform unavailable")).toBeTruthy();
});

test("exposes Pad and time labels on focusable handles and numeric inputs", () => {
  renderEditor();
  expect(screen.getByRole("slider", {name: "Pad A1 Start — 0.000 s"})).toBeTruthy();
  expect(screen.getByRole("slider", {name: "Pad A1 End — 0.000 s"})).toBeTruthy();
  expect(screen.getByRole("spinbutton", {name: "Pad A1 Start time (seconds)"})).toBeTruthy();
  expect(screen.getByRole("spinbutton", {name: "Pad A1 End time (seconds)"})).toBeTruthy();
});

test("previews a pointer drag without mutation and commits once on release", () => {
  const {onPreview, onCommit} = renderEditor();
  const start = screen.getByRole("slider", {name: /Pad A1 Start/});

  fireEvent.pointerDown(start, {pointerId: 7, clientX: 50});
  fireEvent.change(start, {target: {value: "2"}});
  fireEvent.change(start, {target: {value: "3"}});

  expect(onPreview).toHaveBeenLastCalledWith({...playback, trimStartFrame: 3});
  expect(onCommit).not.toHaveBeenCalled();
  fireEvent.pointerUp(start, {pointerId: 7});
  fireEvent.pointerUp(start, {pointerId: 7});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenCalledWith({...playback, trimStartFrame: 3});
});

test("captures the pointer so a release outside the handle still completes the gesture", () => {
  const {onCommit} = renderEditor();
  const start = screen.getByRole("slider", {name: /Pad A1 Start/});
  const setPointerCapture = vi.fn();
  Object.defineProperty(start, "setPointerCapture", {
    configurable: true,
    value: setPointerCapture,
  });

  fireEvent.pointerDown(start, {pointerId: 17});
  fireEvent.change(start, {target: {value: "2"}});
  expect(setPointerCapture).toHaveBeenCalledWith(17);
  fireEvent.pointerUp(window, {pointerId: 17});
  fireEvent.pointerUp(window, {pointerId: 17});
  expect(onCommit).toHaveBeenCalledTimes(1);
  expect(onCommit).toHaveBeenCalledWith({...playback, trimStartFrame: 2});
});

test.each(["pointercancel", "Escape"] as const)(
  "%s cancels a draft without committing",
  (cancellation) => {
    const {onCancel, onCommit} = renderEditor();
    const start = screen.getByRole("slider", {name: /Pad A1 Start/});
    fireEvent.pointerDown(start, {pointerId: 9});
    fireEvent.change(start, {target: {value: "2"}});
    if (cancellation === "pointercancel") {
      fireEvent.pointerCancel(start, {pointerId: 9});
    } else {
      fireEvent.keyDown(start, {key: "Escape"});
    }
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onCommit).not.toHaveBeenCalled();
  },
);

test("unmount cancels an active draft without committing", () => {
  const {onCancel, onCommit, unmount} = renderEditor();
  const start = screen.getByRole("slider", {name: /Pad A1 Start/});
  fireEvent.pointerDown(start, {pointerId: 11});
  fireEvent.change(start, {target: {value: "2"}});
  unmount();
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onCommit).not.toHaveBeenCalled();
});

test("keyboard handles move one frame or the nearest 10 ms without crossing", () => {
  const oneFrame = renderEditor();
  const start = screen.getByRole("slider", {name: /Pad A1 Start/});
  fireEvent.keyDown(start, {key: "ArrowRight"});
  fireEvent.keyUp(start, {key: "ArrowRight"});
  expect(oneFrame.onPreview).toHaveBeenLastCalledWith({...playback, trimStartFrame: 2});
  expect(oneFrame.onCommit).toHaveBeenLastCalledWith({...playback, trimStartFrame: 2});
  oneFrame.unmount();

  const longEnvelope = {
    ...envelope,
    metadata: {...envelope.metadata, sourceFrames: 2_000},
    buckets: [{startFrame: 0, endFrame: 2_000, peakMagnitude: 32_768}],
  } as WaveformEnvelope;
  const shifted = renderEditor({
    envelope: longEnvelope,
    playback: {...playback, trimStartFrame: 1, trimEndFrame: 1_000},
  });
  const shiftedStart = screen.getByRole("slider", {name: /Pad A1 Start/});
  fireEvent.keyDown(shiftedStart, {key: "ArrowRight", shiftKey: true});
  fireEvent.keyUp(shiftedStart, {key: "ArrowRight", shiftKey: true});
  expect(shifted.onCommit).toHaveBeenLastCalledWith({
    ...playback,
    trimStartFrame: 442,
    trimEndFrame: 1_000,
  });
  shifted.unmount();

  const bounded = renderEditor({playback: {...playback, trimStartFrame: 6}});
  const boundedStart = screen.getByRole("slider", {name: /Pad A1 Start/});
  fireEvent.keyDown(boundedStart, {key: "ArrowRight"});
  fireEvent.keyUp(boundedStart, {key: "ArrowRight"});
  expect(bounded.onCommit).not.toHaveBeenCalled();
});

test("ignores non-finite numeric input instead of creating a NaN draft", () => {
  const {onPreview, onCommit} = renderEditor();
  const start = screen.getByRole("spinbutton", {name: "Pad A1 Start time (seconds)"});
  Object.defineProperty(start, "valueAsNumber", {
    configurable: true,
    get: () => Number.NaN,
  });

  fireEvent.focus(start);
  fireEvent.change(start, {target: {value: "0.0001"}});
  fireEvent.blur(start);

  expect(onPreview).not.toHaveBeenCalled();
  expect(onCommit).not.toHaveBeenCalled();
});

test("Zoom In, Zoom Out, Fit, and pan remain local and bounded", async () => {
  const user = userEvent.setup();
  const {container, onPreview, onCommit} = renderEditor();
  const editor = container.querySelector<HTMLElement>("[data-waveform-viewport]")!;
  expect([editor.dataset.viewportStart, editor.dataset.viewportEnd]).toEqual(["0", "8"]);

  await user.click(screen.getByRole("button", {name: "Zoom In"}));
  expect([editor.dataset.viewportStart, editor.dataset.viewportEnd]).toEqual(["2", "6"]);
  await user.click(screen.getByRole("button", {name: "Pan Right"}));
  await user.click(screen.getByRole("button", {name: "Pan Right"}));
  await user.click(screen.getByRole("button", {name: "Pan Right"}));
  expect([editor.dataset.viewportStart, editor.dataset.viewportEnd]).toEqual(["4", "8"]);
  await user.click(screen.getByRole("button", {name: "Pan Left"}));
  expect([editor.dataset.viewportStart, editor.dataset.viewportEnd]).toEqual(["3", "7"]);
  await user.click(screen.getByRole("button", {name: "Zoom Out"}));
  await user.click(screen.getByRole("button", {name: "Fit waveform"}));
  expect([editor.dataset.viewportStart, editor.dataset.viewportEnd]).toEqual(["0", "8"]);
  expect(onPreview).not.toHaveBeenCalled();
  expect(onCommit).not.toHaveBeenCalled();
});

test("queries each viewport at its own resolution and suppresses stale responses", async () => {
  const pending: Array<{
    viewport: {sourceFrames: number; startFrame: number; endFrame: number};
    resolve: (value: WaveformEnvelope) => void;
  }> = [];
  const onQueryWaveform = vi.fn((viewport) => new Promise<WaveformEnvelope>((resolve) => {
    pending.push({viewport, resolve});
  }));
  const {container} = renderEditor({onQueryWaveform});

  await userEvent.click(screen.getByRole("button", {name: "Zoom In"}));
  await userEvent.click(screen.getByRole("button", {name: "Pan Right"}));
  expect(onQueryWaveform).toHaveBeenNthCalledWith(1, {
    sourceFrames: 8,
    startFrame: 2,
    endFrame: 6,
  });
  expect(onQueryWaveform).toHaveBeenNthCalledWith(2, {
    sourceFrames: 8,
    startFrame: 3,
    endFrame: 7,
  });

  await act(async () => pending[1]!.resolve({
    ...envelope,
    buckets: [
      {startFrame: 3, endFrame: 5, peakMagnitude: 0},
      {startFrame: 5, endFrame: 7, peakMagnitude: 32_768},
    ],
  }));
  const path = container.querySelector<SVGPathElement>("path[data-waveform]")!;
  await waitFor(() => expect(path.getAttribute("d")).toContain("L 200 16"));
  const newestPath = path.getAttribute("d");

  await act(async () => pending[0]!.resolve({
    ...envelope,
    buckets: [
      {startFrame: 2, endFrame: 4, peakMagnitude: 32_768},
      {startFrame: 4, endFrame: 6, peakMagnitude: 0},
    ],
  }));
  expect(path.getAttribute("d")).toBe(newestPath);
});

test("does not let an old Project query hide the current revision waveform", async () => {
  let resolveOld: ((value: WaveformEnvelope) => void) | undefined;
  const onQueryWaveform = vi.fn(() => new Promise<WaveformEnvelope>((resolve) => {
    resolveOld = resolve;
  }));
  const view = renderEditor({onQueryWaveform});
  await userEvent.click(screen.getByRole("button", {name: "Zoom In"}));

  const currentEnvelope: WaveformEnvelope = {
    ...envelope,
    projectRevision: 5,
  };
  view.rerender(
    <WaveformEditor
      padLabel="Pad A1"
      envelope={currentEnvelope}
      metadata={currentEnvelope.metadata}
      projectRevision={currentEnvelope.projectRevision}
      playback={playback}
      playheadFrame={4}
      onPreview={view.onPreview}
      onCommit={view.onCommit}
      onCancel={view.onCancel}
      onQueryWaveform={onQueryWaveform}
    />,
  );
  const currentPath = view.container.querySelector<SVGPathElement>("path[data-waveform]")!;
  const expectedPath = currentPath.getAttribute("d");

  await act(async () => resolveOld?.({
    ...envelope,
    buckets: [
      {startFrame: 2, endFrame: 4, peakMagnitude: 32_768},
      {startFrame: 4, endFrame: 6, peakMagnitude: 0},
    ],
  }));

  expect(view.container.querySelector<SVGPathElement>("path[data-waveform]")
    ?.getAttribute("d")).toBe(expectedPath);
});

test("every handle and viewport action exposes a 44 px hit target", () => {
  renderEditor();
  const actions = [
    ...screen.getAllByRole("button"),
    ...screen.getAllByRole("slider"),
    ...screen.getAllByRole("spinbutton"),
  ];
  for (const action of actions) {
    expect(
      getComputedStyle(action).minHeight,
      action.getAttribute("aria-label") ?? action.textContent ?? action.tagName,
    ).toBe("44px");
  }
});
