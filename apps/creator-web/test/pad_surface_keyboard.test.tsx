import {createEvent, fireEvent, render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";
import {PadSurface} from "../src/components/pad_surface";
import {initialCreatorState, type CreatorState, type ProjectView} from "../src/state/creator_state";
import type {createCreatorInputController} from "../src/runtime/input_controller";

const project: ProjectView = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 4, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—",
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null, category: null, colourOverride: null, colour: null})),
  patterns: [{patternId: "22222222-2222-4222-8222-222222222222", bars: 1, events: []}],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};
const state: CreatorState = {...initialCreatorState,
  project: {phase: "ready", projects: [], current: project},
  runtime: {phase: "ready", errorCode: null},
};

test.each(["Enter", " "])("focused empty Pad forwards %j press/release to capture without opening a picker", key => {
  const keyDown = vi.fn(() => true);
  const keyUp = vi.fn(() => true);
  const choose = vi.fn();
  const controller = {keyDown, keyUp} as unknown as ReturnType<typeof createCreatorInputController>;
  render(<PadSurface state={state} emptyPadCapture controller={controller}
    onSelectSample={() => {}} onChooseSample={choose}/>);
  const pad = screen.getByRole("button", {name: /^Pad A01 /});
  pad.focus();
  const down = createEvent.keyDown(pad, {key, code: key === "Enter" ? "Enter" : "Space"});
  fireEvent(pad, down);
  fireEvent.keyDown(pad, {key, repeat: true});
  fireEvent.keyUp(pad, {key});
  expect(keyDown).toHaveBeenCalledExactlyOnceWith({code: "KeyQ", repeat: false,
    target: document.body, nativeEvent: down});
  expect(keyUp).toHaveBeenCalledExactlyOnceWith({code: "KeyQ", repeat: false, target: document.body});
  expect(choose).not.toHaveBeenCalled();
});

test.each([0, 1, 2, 3] as const)("Bank %i traverses the visible matrix from top left with stable addresses", activeBank => {
  render(<PadSurface state={{...state, activeBank}} emptyPadCapture />);
  // Absolute oracle: a shared wrong display-order helper must not make the
  // two matrices agree on an incorrect layout.
  const bank = ["A", "B", "C", "D"][activeBank];
  const buttons = within(screen.getByLabelText("Playable Pads")).getAllByRole("button");
  expect(buttons.map(button => button.querySelector("strong")?.textContent)).toEqual(
    ["13", "14", "15", "16", "09", "10", "11", "12",
      "05", "06", "07", "08", "01", "02", "03", "04"].map(pad => `${bank}${pad}`),
  );
});

test("reordered pointer and drop targets keep the Bank's original slot identity", () => {
  const pointerDown = vi.fn();
  const pointerUp = vi.fn();
  const select = vi.fn();
  const drop = vi.fn();
  const controller = {pointerDown, pointerUp} as unknown as ReturnType<typeof createCreatorInputController>;
  render(<PadSurface state={{...state, activeBank: 2}} emptyPadCapture controller={controller}
    onSelectSample={select} onDropSample={drop} />);
  const topLeft = screen.getByRole("button", {name: /^Pad C13 /});
  fireEvent.pointerDown(topLeft);
  fireEvent.pointerUp(topLeft);
  fireEvent.click(topLeft);
  expect(pointerDown.mock.calls[0]?.[1]).toBe(44);
  expect(pointerUp.mock.calls[0]?.[1]).toBe(44);
  expect(select).toHaveBeenCalledExactlyOnceWith(44);
  const bottomLeft = screen.getByRole("button", {name: /^Pad C01 /});
  const file = new File(["sample"], "sample.wav", {type: "audio/wav"});
  fireEvent.drop(bottomLeft, {dataTransfer: {files: [file]}});
  expect(drop).toHaveBeenCalledExactlyOnceWith(32, file, bottomLeft);
  expect(bottomLeft.querySelector("kbd")?.textContent).toBe("Q");
});
