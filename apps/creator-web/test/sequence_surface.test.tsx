import {fireEvent, render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {HardwareConsole} from "../src/components/hardware_console";
import {PhysicalControls} from "../src/components/physical_controls";
import {SequenceOverview} from "../src/components/sequence_overview";
import {SequenceTouchWorkspace} from "../src/components/sequence_touch_workspace";
import {initialSequenceState} from "../src/state/sequence_state";
import {
  initialPatternTransportState,
  type PatternTransportState,
} from "../src/state/pattern_transport_state";
import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";

const project = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 7, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—" as const,
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null})),
  patterns: [
    {patternId: "22222222-2222-4222-8222-222222222222", bars: 1 as const, events: []},
    {patternId: "33333333-3333-4333-8333-333333333333", bars: 4 as const, events: []},
  ],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};

// The Sequence editor is the same component in the hardware touch workspace
// that the retired workspace shell used to wrap; its recovery semantics are
// asserted on it directly.
function renderSurface(recovery = false, options: {
  transport?: PatternTransportState;
  state?: Partial<Parameters<typeof SequenceTouchWorkspace>[0]["state"]>;
  projectionRefreshing?: boolean;
} = {}) {
  const callbacks = {
    onRefresh: vi.fn(), onSwitch: vi.fn(),
    onCreatePattern: vi.fn(), onSettingsChange: vi.fn(),
    onToggleMetronome: vi.fn(),
    onRecover: vi.fn(), onDiscard: vi.fn(),
    onSnapChange: vi.fn(), onViewportChange: vi.fn(),
    onEditModeChange: vi.fn(), onEdit: vi.fn(),
    onSelectionChange: vi.fn(), onVelocityChange: vi.fn(),
  };
  render(<SequenceTouchWorkspace project={project}
    transport={options.transport ?? initialPatternTransportState}
    bank={0} snap="1/16"
    editMode="note" selection={[]} defaultVelocity={100}
    projectionRefreshing={options.projectionRefreshing ?? false}
    metronomeOn={false}
    state={{
      ...initialSequenceState,
      recovery: recovery ? [{sessionId: "session-1", patternId: project.patternId,
        bars: 1, reason: "interrupted", eventCount: 3}] : [],
      phase: recovery ? "recovery" : "stopped",
      ...options.state,
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
  const onSnapChange = vi.fn();
  const onViewportChange = vi.fn();
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
      bank={0} snap="1/16" viewport={null} selection={[]}
    />}
    pads={<span>pads</span>}
    touchWorkspace={<SequenceTouchWorkspace
      project={project} state={sequenceState}
      transport={initialPatternTransportState}
      bank={0} snap="1/16"
      editMode="note" selection={[]} defaultVelocity={100}
      projectionRefreshing={false}
      onSnapChange={onSnapChange} onViewportChange={onViewportChange}
      onEditModeChange={vi.fn()} onEdit={vi.fn()}
      onSelectionChange={vi.fn()} onVelocityChange={vi.fn()}
      metronomeOn={false} onToggleMetronome={() => {}}
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
  // Direct controls: a drag previews locally and commits once on release,
  // step buttons and TAP commit immediately, and no Apply button exists.
  expect(within(touch).queryByRole("button", {name: /Apply/})).toBeNull();
  const swingSlider = within(touch).getByRole("slider", {name: "Swing"});
  fireEvent.pointerDown(swingSlider, {pointerId: 1});
  fireEvent.change(swingSlider, {target: {value: "62"}});
  expect(within(touch).getByText("62%")).toBeTruthy();
  expect(onSettingsChange).toHaveBeenCalledTimes(1);
  fireEvent.pointerUp(swingSlider, {pointerId: 1});
  expect(onSettingsChange).toHaveBeenCalledTimes(2);
  expect(onSettingsChange).toHaveBeenLastCalledWith({swingPercent: 62});
  // A step right after the slider's commit continues from the value that
  // commit requested; the committed prop has not caught up yet.
  fireEvent.click(within(touch).getByRole("button", {name: "Increase Swing"}));
  expect(onSettingsChange).toHaveBeenLastCalledWith({swingPercent: 63});
  fireEvent.click(within(touch).getByRole("button", {name: "Decrease BPM"}));
  expect(onSettingsChange).toHaveBeenLastCalledWith({bpm: 119});
  expect(onSettingsChange).toHaveBeenCalledTimes(4);
  const now = vi.spyOn(performance, "now")
    .mockReturnValueOnce(1_000).mockReturnValueOnce(1_600);
  const tapTempo = within(touch).getByRole("button", {name: "Tap Tempo"});
  fireEvent.click(tapTempo);
  expect(onSettingsChange).toHaveBeenCalledTimes(4);
  fireEvent.click(tapTempo);
  expect(onSettingsChange).toHaveBeenLastCalledWith({bpm: 100});
  now.mockRestore();
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

test("a preview never commits and a failed commit restores the committed readout", () => {
  const callbacks = renderSurface();
  const bpmSlider = screen.getByRole("slider", {name: "BPM"});
  fireEvent.pointerDown(bpmSlider, {pointerId: 2});
  fireEvent.change(bpmSlider, {target: {value: "132"}});
  expect(screen.getByText("132 BPM")).toBeTruthy();
  expect(callbacks.onSettingsChange).not.toHaveBeenCalled();
  fireEvent.pointerUp(bpmSlider, {pointerId: 2});
  expect(callbacks.onSettingsChange).toHaveBeenCalledTimes(1);
  expect(callbacks.onSettingsChange).toHaveBeenLastCalledWith({bpm: 132});
  // The commit path owns the outcome: until Truth moves, the readout falls
  // back to the committed value, not the abandoned preview.
  expect(screen.getByText("120 BPM")).toBeTruthy();
});

test("rapid step clicks accumulate from the last requested value until Truth catches up", () => {
  const onSettingsChange = vi.fn();
  const props = {
    transport: initialPatternTransportState,
    state: {...initialSequenceState, phase: "stopped" as const},
    bank: 0 as const, snap: "1/16" as const,
    editMode: "note" as const, selection: [], defaultVelocity: 100,
    projectionRefreshing: false,
    onSnapChange: () => {}, onEditModeChange: () => {}, onViewportChange: () => {},
    onEdit: () => {}, onSelectionChange: () => {}, onVelocityChange: () => {},
    onRefresh: () => {}, onSwitch: () => {},
    onCreatePattern: () => {}, onSettingsChange,
    onRecover: () => {}, onDiscard: () => {},
  };
  const view = render(<SequenceTouchWorkspace project={project} {...props} />);
  // Each click commits through the Host; until the committed prop catches up,
  // the next click must step from the last requested value, not the stale
  // committed one.
  fireEvent.click(screen.getByRole("button", {name: "Increase BPM"}));
  fireEvent.click(screen.getByRole("button", {name: "Increase BPM"}));
  expect(onSettingsChange).toHaveBeenNthCalledWith(1, {bpm: 121});
  expect(onSettingsChange).toHaveBeenNthCalledWith(2, {bpm: 122});
  fireEvent.click(screen.getByRole("button", {name: "Increase Swing"}));
  fireEvent.click(screen.getByRole("button", {name: "Increase Swing"}));
  expect(onSettingsChange).toHaveBeenNthCalledWith(3, {swingPercent: 51});
  expect(onSettingsChange).toHaveBeenNthCalledWith(4, {swingPercent: 52});
  // Once Truth lands on the requested value, stepping continues from it.
  view.rerender(<SequenceTouchWorkspace
    project={{
      ...project, bpm: 122,
      sequenceSettings: {quantizeEnabled: true, swingPercent: 52},
    }} {...props} />);
  fireEvent.click(screen.getByRole("button", {name: "Increase BPM"}));
  expect(onSettingsChange).toHaveBeenNthCalledWith(5, {bpm: 123});
  fireEvent.click(screen.getByRole("button", {name: "Decrease Swing"}));
  expect(onSettingsChange).toHaveBeenNthCalledWith(6, {swingPercent: 51});
});

test("a failed settings commit resyncs the step base to the committed truth", () => {
  const onSettingsChange = vi.fn();
  const props = {
    transport: initialPatternTransportState,
    bank: 0 as const, snap: "1/16" as const,
    editMode: "note" as const, selection: [], defaultVelocity: 100,
    projectionRefreshing: false,
    onSnapChange: () => {}, onEditModeChange: () => {}, onViewportChange: () => {},
    onEdit: () => {}, onSelectionChange: () => {}, onVelocityChange: () => {},
    onRefresh: () => {}, onSwitch: () => {},
    onCreatePattern: () => {}, onSettingsChange,
    onRecover: () => {}, onDiscard: () => {},
  };
  const view = render(<SequenceTouchWorkspace project={project}
    state={{...initialSequenceState, phase: "stopped"}} {...props} />);
  fireEvent.click(screen.getByRole("button", {name: "Increase BPM"}));
  expect(onSettingsChange).toHaveBeenNthCalledWith(1, {bpm: 121});
  // The commit failed: the requested value never landed, so the next step
  // derives from the committed truth again, not from the failed request.
  view.rerender(<SequenceTouchWorkspace project={project}
    state={{...initialSequenceState, phase: "stopped", errorCode: "HOST_TIMEOUT"}}
    {...props} />);
  fireEvent.click(screen.getByRole("button", {name: "Increase BPM"}));
  expect(onSettingsChange).toHaveBeenNthCalledWith(2, {bpm: 121});
});

test("locks every Tempo and Swing control while recording and says why", () => {
  render(<SequenceTouchWorkspace project={project}
    transport={{
      ...initialPatternTransportState,
      sessionId: "session-1",
      status: {
        engaged: true, playing: true, recording: true, phase: "idle",
        runtimeGeneration: 1, transportEpoch: 1, originFrame: 0,
        commandId: "command-1", publicationPending: false, error: null,
      },
    }}
    state={initialSequenceState}
    bank={0} snap="1/16"
    editMode="note" selection={[]} defaultVelocity={100}
    projectionRefreshing={false}
    onSnapChange={() => {}} onEditModeChange={() => {}} onViewportChange={() => {}}
    onEdit={() => {}} onSelectionChange={() => {}} onVelocityChange={() => {}}
    metronomeOn={true} onToggleMetronome={() => {}}
    onRefresh={() => {}} onSwitch={() => {}}
    onCreatePattern={() => {}} onSettingsChange={() => {}}
    onRecover={() => {}} onDiscard={() => {}} />);
  for (const name of [
    "BPM", "Swing",
  ]) {
    expect(screen.getByRole("slider", {name}).hasAttribute("disabled")).toBe(true);
  }
  for (const name of [
    "Decrease BPM", "Increase BPM", "Tap Tempo",
    "Decrease Swing", "Increase Swing",
  ]) {
    expect(screen.getByRole("button", {name}).hasAttribute("disabled")).toBe(true);
  }
  // The metronome is a monitoring switch, not a Transport setting: it stays
  // toggleable while recording.
  const metronome = screen.getByRole("button", {name: "Metronome"});
  expect(metronome.hasAttribute("disabled")).toBe(false);
  expect(metronome.getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText(/locked while recording/)).toBeTruthy();
});

test("the metronome toggle reports its state and fires the callback", () => {
  const callbacks = renderSurface();
  const metronome = screen.getByRole("button", {name: "Metronome"});
  expect(metronome.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(metronome);
  expect(callbacks.onToggleMetronome).toHaveBeenCalledTimes(1);
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

test("keeps restoring into another Pattern behind a collapsed More disclosure", () => {
  renderSurface(true);
  const more = screen.getByText("More", {selector: "summary"}).closest("details");
  expect(more).not.toBeNull();
  expect(more!.open).toBe(false);
  expect(more!.contains(screen.getByRole("button", {name: "Recover to selected Pattern"}))).toBe(true);
  expect(more!.contains(screen.getByRole("button", {name: "Recover original Pattern"}))).toBe(false);
  expect(more!.contains(screen.getByRole("button", {name: "Discard"}))).toBe(false);
});

const transportStatus = (overrides: Partial<PatternTransportStatus>): PatternTransportState => ({
  ...initialPatternTransportState,
  sessionId: "session-1",
  status: {
    engaged: true,
    playing: false,
    recording: false,
    phase: "idle",
    runtimeGeneration: 1,
    transportEpoch: 1,
    originFrame: 0,
    commandId: null,
    publicationPending: false,
    error: null,
    ...overrides,
  },
});

test("recording disables grid editing and the workspace names why", () => {
  const callbacks = renderSurface(false, {
    transport: transportStatus({playing: true, recording: true}),
  });
  expect(screen.getByTestId("sequence-grid")
    .getAttribute("data-editing-disabled")).toBe("true");
  const statuses = screen.getAllByRole("status").map((node) => node.textContent);
  expect(statuses).toContain("Recording — stop recording to edit the grid.");
  const lane = document.querySelector(
    ".sequence-grid-row[data-pad='3'] .sequence-grid-lane") as HTMLElement;
  fireEvent.pointerDown(lane, {pointerId: 31, clientX: 60, clientY: 76, button: 0});
  fireEvent.pointerUp(window, {pointerId: 31});
  expect(callbacks.onEdit).not.toHaveBeenCalled();
});

test("no gesture starts while the projection re-reads Truth after a commit", () => {
  const callbacks = renderSurface(false, {projectionRefreshing: true});
  expect(screen.getByTestId("sequence-grid")
    .getAttribute("data-editing-disabled")).toBe("true");
  const lane = document.querySelector(
    ".sequence-grid-row[data-pad='3'] .sequence-grid-lane") as HTMLElement;
  fireEvent.pointerDown(lane, {pointerId: 32, clientX: 60, clientY: 76, button: 0});
  fireEvent.pointerMove(lane, {pointerId: 32, clientX: 120, clientY: 100});
  fireEvent.pointerUp(window, {pointerId: 32});
  expect(callbacks.onEdit).not.toHaveBeenCalled();
  expect(callbacks.onSelectionChange).not.toHaveBeenCalled();
});
