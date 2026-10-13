import {render, screen, within} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {OverviewDisplay} from "../src/components/overview_display";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import {initialSequenceState} from "../src/state/sequence_state";
import {initialPatternTransportState} from "../src/state/pattern_transport_state";
import {projectSamplePlayback} from "../src/state/sample_state";

const state: CreatorState = {...initialCreatorState,
  audio: {phase: "suspended"},
  project: {...initialCreatorState.project, phase: "ready", current: {
    projectId: "11111111-1111-4111-8111-111111111111",
    patternId: "22222222-2222-4222-8222-222222222222",
    revision: 7, bpm: 120, assetCount: 0, assignedPadCount: 0,
    bundleDigest: "a".repeat(64), key: "—", pads: [],
    patterns: [{patternId: "22222222-2222-4222-8222-222222222222", bars: 2, events: []}],
    patternSlots: Array<string | null>(16).fill(null),
    sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
  }},
};

const common = {state, sequence: initialSequenceState, snap: "1/16" as const,
  viewport: null, selection: []};

test.each(["project", "sample", "sequence", "perform", "soundset", "slice"] as const)(
  "%s presents actual encoder bindings after its read-only body", activeMode => {
    const onTurn = vi.fn();
    const view = render(<OverviewDisplay {...common} activeMode={activeMode}
      encoders={{1: {label: "Actual parameter", value: "pending", onTurn},
        4: {label: "Output Volume", value: "61%", onTurn}}} />);
    const row = view.container.querySelector('.encoder-readbacks [data-encoder="4"]')!;
    expect(row.querySelector("dd")?.textContent).toBe("61%");
    expect(view.container.querySelector('.encoder-readbacks [data-encoder="1"] dd')?.textContent)
      .toBe("pending");
    expect(view.container.querySelector('.encoder-readbacks [data-encoder="2"] dd')?.textContent)
      .toBe("—");
    expect(view.container.querySelector(".overview-body")?.nextElementSibling?.className)
      .toBe("encoder-readbacks");
    expect(view.container.querySelector("button,input,select,a,[tabindex]")).toBeNull();
    expect(onTurn).not.toHaveBeenCalled();
  });

test.each(["sample", "sequence", "perform"] as const)(
  "System replaces the %s body and returning restores it", activeMode => {
    const view = render(<OverviewDisplay {...common} activeMode={activeMode} />);
    expect(screen.getByTestId(`${activeMode}-overview`)).toBeDefined();
    view.rerender(<OverviewDisplay {...common} activeMode={activeMode} systemOpen
      midi={{permission: "denied", connectedInputCount: 0}} />);
    expect(view.container.querySelector(".overview-context")?.textContent).toBe("SYSTEM");
    expect(screen.queryByTestId(`${activeMode}-overview`)).toBeNull();
    const overview = screen.getByTestId("project-overview");
    expect(within(overview).getByText("suspended")).toBeDefined();
    expect(within(overview).getByText("denied")).toBeDefined();
    expect(screen.getByTestId("audio-state").textContent).toBe("Audio suspended");
    view.rerender(<OverviewDisplay {...common} activeMode={activeMode} />);
    expect(screen.getByTestId(`${activeMode}-overview`)).toBeDefined();
  });

test("no Project has neither an invented transport position nor populated Project facts", () => {
  render(<OverviewDisplay {...common} state={initialCreatorState} activeMode="project" />);
  expect(screen.getByTestId("opened-project").textContent).toBe("NO PROJECT");
  expect(screen.getByLabelText("Transport position").textContent).toBe("—");
  expect(screen.getByText("NO PROJECT OPEN")).toBeDefined();
});

test("opening and failed Project state keep their qualified status instead of autosave", () => {
  const view = render(<OverviewDisplay {...common} activeMode="project"
    state={{...state, project: {...state.project, phase: "opening"}}} />);
  expect(screen.getByText("OPENING")).toBeDefined();
  expect(screen.queryByText("LOCAL AUTOSAVE")).toBeNull();
  view.rerender(<OverviewDisplay {...common} activeMode="project"
    state={{...state, project: {...state.project, phase: "error"},
      runtime: {...state.runtime, errorCode: "IO_ERROR"}}} />);
  expect(screen.getByText("NEEDS ATTENTION")).toBeDefined();
  expect(screen.getByText("Needs attention").getAttribute("data-error-code")).toBe("IO_ERROR");
});

test("Slice context never claims the selected Sample Pad is the analysis source", () => {
  render(<OverviewDisplay {...common} activeMode="slice"
    state={{...state, sample: {...state.sample, selectedSlot: 2}}} />);
  const overview = screen.getByTestId("slice-overview");
  expect(overview.textContent).toContain("Source selection in touch workspace");
  expect(overview.textContent).toContain("Adopt to save them to Pads");
  expect(overview.textContent).not.toMatch(/A03|4 slices/);
  expect(screen.getByTestId("opened-project").textContent).toBe("11111111");
});

test("Sequence header preserves unsettled tempo and swing without changing transport truth", () => {
  render(<OverviewDisplay {...common} activeMode="sequence"
    tempoPreview={135} swingPreview={60} transport={initialPatternTransportState} />);
  const header = screen.getByLabelText("Pattern transport");
  expect(header.textContent).toBe("STOPPED135 BPMSWING 60%001:01");
  expect(state.project.current?.bpm).toBe(120);
});

test("an empty Pad is explicit and does not draw example audio", () => {
  render(<OverviewDisplay {...common} activeMode="sample"
    state={{...state, sample: {...state.sample, selectedSlot: 2},
      project: {...state.project, current: {...state.project.current!, pads: [
        {slot: 2, assetId: null, category: null, colour: null, colourOverride: null},
      ]}}}} />);
  expect(screen.getByText("EMPTY PAD")).toBeDefined();
  expect(screen.getByText("No audio assigned")).toBeDefined();
  expect(screen.getByRole("img", {name: "No Sample waveform"}).querySelectorAll("rect"))
    .toHaveLength(0);
});

test("an assigned Pad shows loading until inspect replaces the overlay with real format", () => {
  const loading: CreatorState = {...state,
    sample: {...state.sample, selectedSlot: 2},
    project: {...state.project, current: {...state.project.current!, pads: [
      {slot: 2, assetId: "asset-id", category: "melodic", colour: null, colourOverride: null},
    ]}},
  };
  const view = render(<OverviewDisplay {...common} state={loading} activeMode="sample" />);
  expect(screen.getByText("LOADING")).toBeDefined();
  expect(screen.getByText("Loading Sample details…")).toBeDefined();
  expect(screen.queryByText("Sample details unavailable")).toBeNull();
  expect(screen.queryByText("EMPTY PAD")).toBeNull();
  view.rerender(<OverviewDisplay {...common} activeMode="sample" state={{...loading,
    sample: {...loading.sample, inspect: {
      projectRevision: 7, slot: 2, assetId: "asset-id", playback: projectSamplePlayback(undefined),
      metadata: {sampleRate: 48_000, channels: 1, sourceFrames: 48_000},
      waveformCacheIdentity: "waveform",
    }},
  }} />);
  expect(view.container.querySelector(".sample-overview-empty")).toBeNull();
  expect(screen.getByText("mono 48000 Hz · 1.000 s")).toBeDefined();
});

test("Sample loading failure remains qualified and does not claim an empty Pad", () => {
  render(<OverviewDisplay {...common} activeMode="sample"
    state={{...state, sample: {...state.sample, selectedSlot: 2,
      lastError: {code: "IO_ERROR", message: "Inspect failed", retryPrepare: false}},
      project: {...state.project, current: {...state.project.current!, pads: [
        {slot: 2, assetId: "asset-id", category: "melodic", colour: null, colourOverride: null},
      ]}}}} />);
  expect(screen.getByText("CHECK LAST ACTION")).toBeDefined();
  expect(screen.getByText("Sample details unavailable")).toBeDefined();
  expect(screen.queryByText("EMPTY PAD")).toBeNull();
});
