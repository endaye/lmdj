import {fireEvent, render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {PadColourControls} from "../src/components/pad_colour_controls";
import {PadSurface} from "../src/components/pad_surface";
import {SequenceOverview} from "../src/components/sequence_overview";
import {SequenceTouchWorkspace} from "../src/components/sequence_touch_workspace";
import type {ProjectPadView, ProjectView} from "../src/runtime/runtime_types";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import {initialPatternTransportState} from "../src/state/pattern_transport_state";
import {initialSampleState} from "../src/state/sample_state";
import {initialSequenceState} from "../src/state/sequence_state";

const PATTERN_ID = "22222222-2222-4222-8222-222222222222";
const empty = (slot: number): ProjectPadView =>
  ({slot, assetId: null, category: null, colourOverride: null, colour: null});
// A01: BASS asset with a MELODIC override. A02: DRUMS asset, no override.
// A03: unclassified asset (neutral). A04: empty. A05: BASS default.
const PADS: Readonly<Record<number, ProjectPadView>> = {
  0: {slot: 0, assetId: "a1", category: "bass", colourOverride: 2, colour: 2},
  1: {slot: 1, assetId: "a2", category: "drums", colourOverride: null, colour: 0},
  2: {slot: 2, assetId: "a3", category: null, colourOverride: null, colour: null},
  4: {slot: 4, assetId: "a5", category: "bass", colourOverride: null, colour: 1},
};

const project: ProjectView = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: PATTERN_ID,
  revision: 7, bpm: 120, assetCount: 4, assignedPadCount: 4,
  bundleDigest: "a".repeat(64), key: "—",
  pads: Array.from({length: 64}, (_, slot) => PADS[slot] ?? empty(slot)),
  patterns: [{
    patternId: PATTERN_ID,
    bars: 1,
    events: [0, 1, 2, 3, 4].map((pad) => Object.freeze({
      slot: Object.freeze({bank: 0, pad}),
      onsetTick: pad * 240, durationTick: 240, velocity: 100,
    })),
  }],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};

function creatorState(selectedSlot: number | null = null): CreatorState {
  return {
    ...initialCreatorState,
    project: {phase: "ready", projects: [], current: project},
    runtime: {phase: "ready", errorCode: null},
    sample: {...initialSampleState, selectedSlot},
  };
}

const matrixColour = (address: string) =>
  screen.getByRole("button", {name: new RegExp(`^Pad ${address} `)})
    .getAttribute("data-pad-colour");

test("the Pad matrix, Sequence overview rows and touch grid notes draw the same colour for each Pad", () => {
  render(<PadSurface state={creatorState()} />);
  const overview = render(<SequenceOverview project={project} state={initialSequenceState}
    bank={0} snap="1/16" viewport={null} selection={[]} />);
  const touch = render(<SequenceTouchWorkspace project={project} state={initialSequenceState}
    transport={initialPatternTransportState} bank={0} snap="1/16" editMode="note"
    selection={[]} defaultVelocity={100} projectionRefreshing={false} metronomeOn={false}
    onToggleMetronome={vi.fn()} onRefresh={vi.fn()} onSwitch={vi.fn()}
    onCreatePattern={vi.fn()} onSnapChange={vi.fn()} onEditModeChange={vi.fn()}
    onViewportChange={vi.fn()} onEdit={vi.fn()} onSelectionChange={vi.fn()}
    onVelocityChange={vi.fn()} onSettingsChange={vi.fn()} onRecover={vi.fn()}
    onDiscard={vi.fn()} />);
  // Override wins over the category, the category default applies without
  // one, and an unclassified or empty Pad is neutral.
  const expected = [["A01", "2"], ["A02", "0"], ["A03", "neutral"], ["A04", "neutral"],
    ["A05", "1"]] as const;
  const overviewNotes = overview.container.querySelectorAll(".sequence-overview-note");
  const overviewNames = overview.container.querySelectorAll(".sequence-overview-names li");
  const gridNotes = within(touch.container).getAllByTestId("sequence-grid-note");
  expected.forEach(([address, colour], slot) => {
    expect(matrixColour(address)).toBe(colour);
    expect(overviewNames[slot]?.getAttribute("data-pad-colour")).toBe(colour);
    expect(overviewNotes[slot]?.getAttribute("data-row")).toBe(String(slot));
    expect(overviewNotes[slot]?.getAttribute("data-pad-colour")).toBe(colour);
    expect(gridNotes[slot]?.closest("[data-pad-colour]")?.getAttribute("data-pad-colour"))
      .toBe(colour);
  });
  // The slot rotation is gone.
  expect(document.querySelector("[data-identity]")).toBeNull();
});

test("a selected BASS Pad shows a white border and lime dot that an unselected BASS Pad lacks", () => {
  const bassProject: ProjectView = {
    ...project,
    pads: project.pads.map((pad) => pad.slot === 0
      ? {...pad, colourOverride: null, colour: 1} : pad),
  };
  render(<PadSurface state={{...creatorState(0), project: {phase: "ready", projects: [],
    current: bassProject}}} onSelectSample={vi.fn()} />);
  const selected = screen.getByRole("button", {name: /^Pad A01 /});
  const unselected = screen.getByRole("button", {name: /^Pad A05 /});
  expect(selected.getAttribute("data-pad-colour")).toBe("1");
  expect(unselected.getAttribute("data-pad-colour")).toBe("1");
  expect(selected.getAttribute("aria-pressed")).toBe("true");
  expect(unselected.getAttribute("aria-pressed")).toBe("false");
  expect(selected.classList.contains("is-selected")).toBe(true);
  expect(unselected.classList.contains("is-selected")).toBe(false);
  expect(within(selected).getByTestId("pad-selected-dot")).toBeTruthy();
  expect(within(unselected).queryByTestId("pad-selected-dot")).toBeNull();
});

test("choosing a colour sets the override, restore clears it, and the stored override makes no call", () => {
  const onChoose = vi.fn();
  const view = render(<PadColourControls pad={PADS[1]!} disabledReason={null} error={null}
    onChoose={onChoose} />);
  expect(screen.getByTestId("pad-colour-source").textContent).toBe("DRUMS default");
  expect(screen.getByRole("button", {name: "DRUMS colour"}).getAttribute("aria-pressed"))
    .toBe("true");
  // No override yet: restore has nothing to clear.
  expect(screen.getByRole("button", {name: "Restore category default"})
    .hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", {name: "VOCAL colour"}));
  expect(onChoose).toHaveBeenLastCalledWith(3);

  view.rerender(<PadColourControls pad={PADS[0]!} disabledReason={null} error={null}
    onChoose={onChoose} />);
  expect(screen.getByTestId("pad-colour-source").textContent).toBe("Custom colour");
  onChoose.mockClear();
  fireEvent.click(screen.getByRole("button", {name: "MELODIC colour"}));
  expect(onChoose).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", {name: "Restore category default"}));
  expect(onChoose).toHaveBeenCalledExactlyOnceWith(null);
});

test("the colour controls are disabled for an empty Pad and while recording", () => {
  const onChoose = vi.fn();
  const view = render(<PadColourControls pad={empty(3)} disabledReason={null} error={null}
    onChoose={onChoose} />);
  const all = () => [...screen.getByRole("region", {name: "Pad colour"})
    .querySelectorAll("button")];
  expect(all()).toHaveLength(6);
  expect(all().every((button) => button.hasAttribute("disabled"))).toBe(true);
  expect(screen.getByText("Assign a sound to this Pad to choose its colour.")).toBeTruthy();

  view.rerender(<PadColourControls pad={PADS[0]!}
    disabledReason="Stop recording to change the Pad colour." error={null}
    onChoose={onChoose} />);
  expect(all().every((button) => button.hasAttribute("disabled"))).toBe(true);
  expect(screen.getByText("Stop recording to change the Pad colour.")).toBeTruthy();
  all().forEach((button) => fireEvent.click(button));
  expect(onChoose).not.toHaveBeenCalled();
});
