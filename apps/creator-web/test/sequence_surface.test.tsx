import {fireEvent, render, screen} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {SequenceSurface} from "../src/components/sequence_surface";
import {initialSequenceState} from "../src/state/sequence_state";

const project = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 7, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—" as const,
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null})),
  patterns: [
    {patternId: "22222222-2222-4222-8222-222222222222", bars: 1 as const},
    {patternId: "33333333-3333-4333-8333-333333333333", bars: 4 as const},
  ],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};

function renderSurface(recovery = false) {
  const callbacks = {
    onRecord: vi.fn(), onStop: vi.fn(), onRefresh: vi.fn(), onSwitch: vi.fn(),
    onCreatePattern: vi.fn(), onSettingsChange: vi.fn(),
    onRecover: vi.fn(), onDiscard: vi.fn(),
  };
  render(<SequenceSurface project={project} ready state={{
    ...initialSequenceState,
    recovery: recovery ? [{sessionId: "session-1", patternId: project.patternId,
      bars: 1, reason: "interrupted", eventCount: 3}] : [],
    phase: recovery ? "recovery" : "stopped",
  }} {...callbacks} />);
  return callbacks;
}

test("issues authoritative settings and Pattern creation operations", () => {
  const callbacks = renderSurface();
  fireEvent.click(screen.getByRole("checkbox", {name: "Quantize"}));
  expect(callbacks.onSettingsChange).toHaveBeenCalledWith({quantizeEnabled: false});
  fireEvent.change(screen.getByRole("slider", {name: /Swing/}), {target: {value: "62"}});
  fireEvent.click(screen.getByRole("button", {name: "Apply Swing"}));
  expect(callbacks.onSettingsChange).toHaveBeenCalledWith({swingPercent: 62});
  fireEvent.change(screen.getByRole("combobox", {name: "Bars"}), {target: {value: "4"}});
  fireEvent.click(screen.getByRole("button", {name: "Create Pattern"}));
  expect(callbacks.onCreatePattern).toHaveBeenCalledWith(4);
});

test("requires an explicit destination and preserves original recovery semantics", () => {
  const callbacks = renderSurface(true);
  fireEvent.click(screen.getByRole("button", {name: "Recover original Pattern"}));
  expect(callbacks.onRecover).toHaveBeenCalledWith(expect.anything(), null);
  const destination = screen.getByRole("combobox", {name: "Recovery destination session-1"});
  const recoverToSelected = screen.getByRole("button", {name: "Recover to selected Pattern"});
  expect(recoverToSelected.hasAttribute("disabled")).toBe(true);
  fireEvent.change(destination, {target: {value: project.patterns[1]!.patternId}});
  fireEvent.click(recoverToSelected);
  expect(callbacks.onRecover).toHaveBeenLastCalledWith(
    expect.anything(), project.patterns[1]!.patternId,
  );
});
