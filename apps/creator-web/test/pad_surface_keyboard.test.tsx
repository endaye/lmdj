import {createEvent, fireEvent, render, screen} from "@testing-library/react";
import {expect, test, vi} from "vitest";
import {PadSurface} from "../src/components/pad_surface";
import {initialCreatorState, type CreatorState, type ProjectView} from "../src/state/creator_state";
import type {createCreatorInputController} from "../src/runtime/input_controller";

const project: ProjectView = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 4, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—",
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null})),
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
  const pad = screen.getAllByRole("button")[0]!;
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
