import {fireEvent, render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {HardwareConsole} from "../src/components/hardware_console";
import {PhysicalControls} from "../src/components/physical_controls";
import {SequenceOverview} from "../src/components/sequence_overview";
import {SequenceTouchWorkspace} from "../src/components/sequence_touch_workspace";
import {initialSequenceState} from "../src/state/sequence_state";
import {initialPatternTransportState} from "../src/state/pattern_transport_state";

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

// The Sequence editor is the same component in the hardware touch workspace
// that the retired workspace shell used to wrap; its recovery semantics are
// asserted on it directly.
function renderSurface(recovery = false) {
  const callbacks = {
    onRefresh: vi.fn(), onSwitch: vi.fn(),
    onCreatePattern: vi.fn(), onSettingsChange: vi.fn(),
    onRecover: vi.fn(), onDiscard: vi.fn(),
  };
  render(<SequenceTouchWorkspace project={project}
    transport={initialPatternTransportState}
    state={{
      ...initialSequenceState,
      recovery: recovery ? [{sessionId: "session-1", patternId: project.patternId,
        bars: 1, reason: "interrupted", eventCount: 3}] : [],
      phase: recovery ? "recovery" : "stopped",
    }} {...callbacks} />);
  return callbacks;
}

test("hardware Sequence overview is read-only and the touch workspace owns editing", () => {
  const onRecord = vi.fn();
  const onPlayStop = vi.fn();
  const onSettingsChange = vi.fn();
  const onCreatePattern = vi.fn();
  const onSwitch = vi.fn();
  const onRecover = vi.fn();
  const onDiscard = vi.fn();
  const onRefresh = vi.fn();
  const sequenceState = {
    ...initialSequenceState,
    recovery: [{
      sessionId: "session-1",
      patternId: project.patternId,
      bars: 1 as const,
      reason: "interrupted",
      eventCount: 3,
    }],
    phase: "recovery" as const,
  };
  render(<HardwareConsole
    physicalControls={<PhysicalControls
      activeMode="sequence" activeBank={0} sequenceEnabled performEnabled
      onSelectMode={() => {}} onSelectBank={() => {}}
      onRecord={onRecord} recordEnabled
      onPlayStop={onPlayStop} playEnabled
    />}
    overview={<SequenceOverview
      project={project} state={sequenceState}
      transport={initialPatternTransportState}
    />}
    pads={<span>pads</span>}
    touchWorkspace={<SequenceTouchWorkspace
      project={project} state={sequenceState}
      transport={initialPatternTransportState}
      onRefresh={onRefresh} onSwitch={onSwitch}
      onCreatePattern={onCreatePattern} onSettingsChange={onSettingsChange}
      onRecover={onRecover} onDiscard={onDiscard}
    />}
  />);

  const display = screen.getByRole("region", {name: "Overview display"});
  expect(within(display).queryAllByRole("button")).toHaveLength(0);
  expect(within(display).queryAllByRole("checkbox")).toHaveLength(0);
  expect(within(display).queryAllByRole("textbox")).toHaveLength(0);
  expect(within(display).queryAllByRole("slider")).toHaveLength(0);
  expect(display.textContent ?? "").toMatch(/Quantize/);
  expect(display.textContent ?? "").toMatch(/Swing/);
  expect(display.textContent ?? "").not.toMatch(/Copy/);

  const touch = screen.getByRole("region", {name: "Touch workspace"});
  expect(within(touch).queryByRole("button", {name: "COPY"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "1/16"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Play"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Stop"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Record"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Record off"})).toBeNull();
  fireEvent.click(within(touch).getByRole("checkbox", {name: "Quantize"}));
  expect(onSettingsChange).toHaveBeenCalledWith({quantizeEnabled: false});
  fireEvent.change(within(touch).getByRole("slider", {name: /Swing/}), {
    target: {value: "62"},
  });
  fireEvent.click(within(touch).getByRole("button", {name: "Apply Swing"}));
  expect(onSettingsChange).toHaveBeenCalledWith({swingPercent: 62});
  fireEvent.click(within(touch).getByRole("button", {name: "4 bars"}));
  fireEvent.click(within(touch).getByRole("button", {name: "Create Pattern"}));
  expect(onCreatePattern).toHaveBeenCalledWith(4);
  fireEvent.click(within(touch).getByRole("button", {
    name: "Recover original Pattern",
  }));
  expect(onRecover).toHaveBeenCalledWith(expect.anything(), null);
  fireEvent.click(within(touch).getByRole("button", {name: "Discard"}));
  expect(onDiscard).toHaveBeenCalledTimes(1);
  fireEvent.click(within(touch).getByRole("button", {name: "Refresh authority"}));
  expect(onRefresh).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", {name: "Record"}));
  expect(onRecord).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", {name: "Play/Stop"}));
  expect(onPlayStop).toHaveBeenCalledTimes(1);
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
