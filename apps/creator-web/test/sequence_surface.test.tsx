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
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null, category: null, colourOverride: null, colour: null})),
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
// Tempo, Swing, Quantize, the metronome, + NEW, TAP and Refresh live in the
// SETUP layer; EDIT (the grid) is the default.
const openSetup = () => fireEvent.click(screen.getByRole("button", {name: "SETUP"}));

function renderSurface(recovery = false, options: {
  transport?: PatternTransportState;
  state?: Partial<Parameters<typeof SequenceTouchWorkspace>[0]["state"]>;
  projectionRefreshing?: boolean;
} = {}) {
  const callbacks = {
    onRefresh: vi.fn(), onSwitch: vi.fn(),
    onCreatePattern: vi.fn(), onSettingsChange: vi.fn(), onSettingsPreview: vi.fn(),
    onResizePattern: vi.fn(), onDoubleUpPattern: vi.fn(), onCopyPattern: vi.fn(),
    onToggleMetronome: vi.fn(),
    onRecover: vi.fn(), onDiscard: vi.fn(),
    onSnapChange: vi.fn(), onViewportChange: vi.fn(),
    onEditModeChange: vi.fn(), onEdit: vi.fn(),
    onSelectionChange: vi.fn(), onVelocityChange: vi.fn(),
  };
  const props: Parameters<typeof SequenceTouchWorkspace>[0] = {
    project, transport: options.transport ?? initialPatternTransportState,
    bank: 0, snap: "1/16", editMode: "note", selection: [], defaultVelocity: 100,
    projectionRefreshing: options.projectionRefreshing ?? false, metronomeOn: false,
    state: {
      ...initialSequenceState,
      recovery: recovery ? [{sessionId: "session-1", patternId: project.patternId,
        bars: 1, reason: "interrupted", eventCount: 3}] : [],
      phase: recovery ? "recovery" : "stopped",
      ...options.state,
    }, ...callbacks,
  };
  const view = render(<SequenceTouchWorkspace {...props} />);
  return {...callbacks,
    update: (changes: Partial<typeof props>) => view.rerender(<SequenceTouchWorkspace {...props} {...changes} />),
  };
}

test.each([{name: "BPM", field: "bpm", value: "132"},
  {name: "Swing", field: "swingPercent", value: "61"}])(
  "$name shares a draft, cancels it, and clears it before committing once", ({name, field, value}) => {
    const callbacks = renderSurface();
    openSetup();
    const slider = screen.getByRole("slider", {name});
    fireEvent.pointerDown(slider, {pointerId: 1});
    fireEvent.change(slider, {target: {value}});
    expect(callbacks.onSettingsPreview).toHaveBeenLastCalledWith({[field]: Number(value)});
    expect(callbacks.onSettingsChange).not.toHaveBeenCalled();
    fireEvent.keyDown(slider, {key: "Escape"});
    expect(callbacks.onSettingsPreview).toHaveBeenLastCalledWith({[field]: null});
    fireEvent.pointerUp(window, {pointerId: 1});
    expect(callbacks.onSettingsChange).not.toHaveBeenCalled();
    fireEvent.change(slider, {target: {value}});
    fireEvent.pointerUp(slider);
    expect(callbacks.onSettingsPreview).toHaveBeenLastCalledWith({[field]: null});
    expect(callbacks.onSettingsChange).toHaveBeenCalledExactlyOnceWith({[field]: Number(value)});
  });

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
  expect(display.textContent ?? "").toMatch(/Tracks/);
  expect(display.textContent ?? "").toMatch(/STOPPED \/ 001:01/);
  expect(display.textContent ?? "").not.toMatch(/Copy/);

  const touch = screen.getByRole("region", {name: "Touch workspace"});
  expect(within(touch).queryByRole("button", {name: "COPY"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "1/16"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Play"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Stop"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Record"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Record off"})).toBeNull();
  openSetup();
  const quantize = within(touch).getByRole("button", {name: "Quantize"});
  expect(quantize.getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(quantize);
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
  // + NEW opens the length choice for the new Pattern; BARS above it is the
  // current Pattern's length and is not a choice.
  fireEvent.click(within(touch).getByRole("button", {name: "New Pattern"}));
  fireEvent.click(within(touch).getByRole("button", {name: "4 bars"}));
  fireEvent.click(within(touch).getByRole("button", {name: "Create Pattern"}));
  expect(onCreatePattern).toHaveBeenCalledWith(4);
  fireEvent.click(within(touch).getByRole("button", {
    name: "Recover original Pattern",
  }));
  expect(onRecover).toHaveBeenCalledWith(expect.anything(), null);
  fireEvent.click(within(touch).getByRole("button", {name: "Discard"}));
  expect(onDiscard).toHaveBeenCalledTimes(1);
  fireEvent.click(within(touch).getByText("Playback details", {selector: "summary"}));
  fireEvent.click(within(touch).getByRole("button", {name: "Refresh playback"}));
  expect(onRefresh).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", {name: "Record"}));
  expect(onRecord).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", {name: "Play/Stop"}));
  expect(onPlayStop).toHaveBeenCalledTimes(1);
});

test("a preview never commits and a failed commit restores the committed readout", () => {
  const callbacks = renderSurface();
  openSetup();
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
    metronomeOn: false, onToggleMetronome: () => {},
    onRefresh: () => {}, onSwitch: () => {},
    onCreatePattern: () => {}, onSettingsChange,
    onRecover: () => {}, onDiscard: () => {},
  };
  const view = render(<SequenceTouchWorkspace project={project} {...props} />);
  openSetup();
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
    metronomeOn: false, onToggleMetronome: () => {},
    onRefresh: () => {}, onSwitch: () => {},
    onCreatePattern: () => {}, onSettingsChange,
    onRecover: () => {}, onDiscard: () => {},
  };
  const view = render(<SequenceTouchWorkspace project={project}
    state={{...initialSequenceState, phase: "stopped"}} {...props} />);
  openSetup();
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
        runtimeFrame: 0, observedAtMilliseconds: 0,
        commandId: "command-1", publicationPending: false, error: null,
        currentPatternId: null, pendingSwitch: null,
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
  openSetup();
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
  openSetup();
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
    runtimeFrame: 0,
    observedAtMilliseconds: 0,
    commandId: null,
    publicationPending: false,
    currentPatternId: null, pendingSwitch: null,
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

test("EDIT is the default layer and SETUP swaps the grid for the settings", () => {
  renderSurface();
  const sequence = screen.getByRole("region", {name: "Sequence editor"});
  expect(within(sequence).getByRole("button", {name: "EDIT"}).getAttribute("aria-pressed"))
    .toBe("true");
  expect(within(sequence).getByTestId("sequence-grid")).toBeTruthy();
  expect(within(sequence).queryByRole("region", {name: "Sequence settings"})).toBeNull();
  openSetup();
  expect(within(sequence).queryByTestId("sequence-grid")).toBeNull();
  expect(within(sequence).getByRole("region", {name: "Sequence settings"})).toBeTruthy();
  // BARS shows the selected Pattern's length, not the new-Pattern choice.
  expect(within(sequence).getByRole("button", {name: "Length 1 bars"})
    .getAttribute("aria-pressed")).toBe("true");
  // No browser-native select or checkbox in either layer.
  expect(sequence.querySelectorAll("select, input[type='checkbox']")).toHaveLength(0);
  fireEvent.click(within(sequence).getByRole("button", {name: "EDIT"}));
  expect(within(sequence).getByTestId("sequence-grid")).toBeTruthy();
  expect(sequence.querySelectorAll("select, input[type='checkbox']")).toHaveLength(0);
});

test("the touch picker directly selects a Pattern and preserves its identity/count", () => {
  const stopped = renderSurface(false, {state: {selectedPatternId: project.patterns[1]!.patternId}});
  const stepper = screen.getByTestId("sequence-pattern");
  expect(stepper.getAttribute("data-pattern-id")).toBe(project.patterns[1]!.patternId);
  expect(stepper.textContent).toContain("GROOVE / 02");
  expect(stepper.textContent).toContain("2/2");
  fireEvent.click(screen.getByRole("button", {name: "Choose Pattern"}));
  fireEvent.click(screen.getByRole("button", {name: "GROOVE / 01"}));
  expect(stopped.onSwitch).toHaveBeenCalledWith(project.patterns[0]!.patternId);
});

// #1958: playing no longer locks the picker — a press queues the transport's
// switch — while recording (until S3) still does.
test("the Pattern picker stays available while the transport plays and is disabled while recording", () => {
  const view = renderSurface(false, {transport: transportStatus({playing: true})});
  expect(screen.getByRole("button", {name: "Choose Pattern"}).hasAttribute("disabled"))
    .toBe(false);
  view.update({transport: transportStatus({playing: true, recording: true})});
  expect(screen.getByRole("button", {name: "Choose Pattern"}).hasAttribute("disabled"))
    .toBe(true);
});

// #1958: while the transport plays, the header names the Pattern the engine
// plays and, while a switch is queued, the queued target (`GROOVE / 01 → 02`).
test("the GROOVE header names the playing Pattern and the queued switch target", () => {
  renderSurface(false, {
    transport: transportStatus({
      playing: true,
      currentPatternId: project.patterns[0]!.patternId,
      pendingSwitch: {patternId: project.patterns[1]!.patternId, activationFrame: 96_000},
    }),
    state: {selectedPatternId: project.patterns[0]!.patternId},
  });
  const header = screen.getByRole("button", {name: "Choose Pattern"});
  expect(header.textContent).toContain("GROOVE / 01 → 02");
  expect(header.textContent).toContain("1/2");
  expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
    .toBe(project.patterns[0]!.patternId);
});

// #1823: BARS, DOUBLE UP and COPY act on the selected Pattern in SETUP.
test("BARS asks to resize the selected Pattern to the chosen length", () => {
  const callbacks = renderSurface();
  openSetup();
  fireEvent.click(screen.getByRole("button", {name: "Length 4 bars"}));
  expect(callbacks.onResizePattern).toHaveBeenCalledExactlyOnceWith(4);
});

test("choosing the selected Pattern's current length makes no call", () => {
  const callbacks = renderSurface();
  openSetup();
  fireEvent.click(screen.getByRole("button", {name: "Length 1 bars"}));
  expect(callbacks.onResizePattern).not.toHaveBeenCalled();
});

test("DOUBLE UP is disabled at 8 bars", () => {
  const eightBars = project.patterns[1]!.patternId;
  render(<SequenceTouchWorkspace
    project={{...project, patterns: [project.patterns[0]!,
      {patternId: eightBars, bars: 8 as const, events: []}]}}
    transport={initialPatternTransportState}
    state={{...initialSequenceState, phase: "stopped", selectedPatternId: eightBars}}
    bank={0} snap="1/16" editMode="note" selection={[]} defaultVelocity={100}
    projectionRefreshing={false}
    onSnapChange={() => {}} onEditModeChange={() => {}} onViewportChange={() => {}}
    onEdit={() => {}} onSelectionChange={() => {}} onVelocityChange={() => {}}
    metronomeOn={false} onToggleMetronome={() => {}}
    onRefresh={() => {}} onSwitch={() => {}}
    onCreatePattern={() => {}} onSettingsChange={() => {}}
    onResizePattern={() => {}} onDoubleUpPattern={() => {}} onCopyPattern={() => {}}
    onRecover={() => {}} onDiscard={() => {}} />);
  openSetup();
  expect(screen.getByRole("button", {name: "Double Up Pattern"}).hasAttribute("disabled"))
    .toBe(true);
});

test("DOUBLE UP and COPY ask for the selected Pattern while stopped", () => {
  const callbacks = renderSurface();
  openSetup();
  fireEvent.click(screen.getByRole("button", {name: "Double Up Pattern"}));
  fireEvent.click(screen.getByRole("button", {name: "Copy Pattern"}));
  expect(callbacks.onDoubleUpPattern).toHaveBeenCalledTimes(1);
  expect(callbacks.onCopyPattern).toHaveBeenCalledTimes(1);
});

test("BARS, DOUBLE UP and COPY are disabled while playing", () => {
  const callbacks = renderSurface(false, {transport: transportStatus({playing: true})});
  openSetup();
  for (const name of ["Length 1 bars", "Length 2 bars", "Length 4 bars", "Length 8 bars",
    "Double Up Pattern", "Copy Pattern"]) {
    const control = screen.getByRole("button", {name});
    expect(control.hasAttribute("disabled")).toBe(true);
    fireEvent.click(control);
  }
  expect(callbacks.onResizePattern).not.toHaveBeenCalled();
  expect(callbacks.onDoubleUpPattern).not.toHaveBeenCalled();
  expect(callbacks.onCopyPattern).not.toHaveBeenCalled();
});

test("BARS, DOUBLE UP and COPY are disabled while recording", () => {
  renderSurface(false, {transport: transportStatus({playing: true, recording: true})});
  openSetup();
  for (const name of ["Length 2 bars", "Double Up Pattern", "Copy Pattern"]) {
    expect(screen.getByRole("button", {name}).hasAttribute("disabled")).toBe(true);
  }
});


test("Pattern picker cancellation and selecting the current Pattern preserve the view", () => {
  const callbacks = renderSurface();
  const trigger = screen.getByRole("button", {name: "Choose Pattern"});
  fireEvent.click(trigger);
  const dialog = screen.getByRole("dialog", {name: "Choose Pattern"});
  expect(dialog.querySelectorAll("select, input[type='checkbox']")).toHaveLength(0);
  fireEvent.keyDown(dialog, {key:"Escape"});
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);
  expect(callbacks.onSwitch).not.toHaveBeenCalled();
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("button", {name: "GROOVE / 01"}));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(callbacks.onSwitch).not.toHaveBeenCalled();
});


test.each(["Project", "Pattern", "recording"] as const)(
  "%s transition cancels a held timing draft before a late release", (change) => {
    const callbacks = renderSurface();
    openSetup();
    const slider = screen.getByRole("slider", {name: "BPM"});
    fireEvent.pointerDown(slider, {pointerId: 88});
    fireEvent.change(slider, {target: {value: "132"}});
    expect(callbacks.onSettingsPreview).toHaveBeenLastCalledWith({bpm: 132});
    if (change === "Project") callbacks.update({project: {...project,
      projectId: "44444444-4444-4444-8444-444444444444", bpm: 88}});
    else if (change === "Pattern") callbacks.update({state: {...initialSequenceState,
      selectedPatternId: project.patterns[1]!.patternId}});
    else callbacks.update({transport: transportStatus({playing: true, recording: true})});
    expect(callbacks.onSettingsPreview).toHaveBeenLastCalledWith({bpm: null});
    expect((screen.getByRole("slider", {name: "BPM"}) as HTMLInputElement).value)
      .toBe(change === "Project" ? "88" : "120");
    fireEvent.pointerUp(window, {pointerId: 88});
    expect(callbacks.onSettingsChange).not.toHaveBeenCalled();
  });

test("normal Sequence setup keeps manual playback refresh in details", () => {
  const callbacks = renderSurface();
  openSetup();
  // jsdom does not model closed-details accessibility visibility; assert
  // disclosure ownership here and actual visibility in the browser journey.
  expect((screen.getByRole("button", {name: "Refresh playback"})
    .closest("details") as HTMLDetailsElement).open).toBe(false);
  expect(screen.queryByRole("button", {name: "Retry playback"})).toBeNull();
  fireEvent.click(screen.getByText("Playback details", {selector: "summary"}));
  fireEvent.click(screen.getByRole("button", {name: "Refresh playback"}));
  expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
});

test("failed Sequence offers playback recovery directly even in the editing page", () => {
  const callbacks = renderSurface(false, {state: {errorCode: "IO_ERROR"}});
  fireEvent.click(screen.getByRole("button", {name: "Retry playback"}));
  expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert")).toBeTruthy();
});
