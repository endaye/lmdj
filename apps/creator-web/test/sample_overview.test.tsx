import {render, screen, within} from "@testing-library/react";
import {expect, test} from "vitest";

import type {PadPlayback} from "../src/runtime/runtime_types";
import {SampleOverview} from "../src/components/sample_overview";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";

const metadata = {sampleRate: 48_000 as const, channels: 1 as const, sourceFrames: 48_000};

function stateWith(trimStartFrame: number, trimEndFrame: number | null): CreatorState {
  const playback = {trimStartFrame, trimEndFrame} as unknown as PadPlayback;
  return {
    ...initialCreatorState,
    sample: {
      ...initialCreatorState.sample,
      selectedSlot: 2,
      inspect: {projectRevision: 4, slot: 2, assetId: "a".repeat(64), playback, metadata,
        waveformCacheIdentity: "w"},
      waveform: {metadata, algorithmVersion: 1, projectRevision: 4, buckets: [
        {startFrame: 0, endFrame: 24_000, peakMagnitude: 16_384},
        {startFrame: 24_000, endFrame: 48_000, peakMagnitude: 32_768},
      ]},
    },
  } as CreatorState;
}

test("D03 upper screen shows the format and trim selection over the whole waveform", () => {
  render(<SampleOverview state={stateWith(4_800, 43_200)} />);
  const overview = screen.getByTestId("sample-overview");
  expect(overview.textContent).toContain("mono 48000 Hz · 1.000 s");
  expect(overview.textContent).toContain("0.100 – 0.900 s");
  const waveform = within(overview).getByRole("img", {name: /trim selection/});
  expect(waveform.querySelectorAll(".sample-overview-peak")).toHaveLength(2);
  // The masks cover exactly what lies outside the selection: 72 px either side.
  const outside = waveform.querySelectorAll(".sample-overview-outside");
  expect([...outside].map((rect) => rect.getAttribute("width"))).toEqual(["72", "72"]);
});

test("an untrimmed end selects through the last frame", () => {
  render(<SampleOverview state={stateWith(0, null)} />);
  expect(screen.getByTestId("sample-overview").textContent).toContain("0.000 – 1.000 s");
});

test("a trim beyond the Sample's frames is drawn at the waveform's edge", () => {
  render(<SampleOverview state={stateWith(4_800, 96_000)} />);
  const overview = screen.getByTestId("sample-overview");
  expect(overview.textContent).toContain("0.100 – 1.000 s");
  const outside = overview.querySelectorAll(".sample-overview-outside");
  expect([...outside].map((rect) => rect.getAttribute("width"))).toEqual(["72", "0"]);
});

test("selecting a different Pad cannot show the previous Pad's format or waveform", () => {
  const state = stateWith(4_800, 43_200);
  const view = render(<SampleOverview state={state} />);
  expect(screen.getByTestId("sample-overview").textContent).toContain("mono 48000 Hz");
  view.rerender(<SampleOverview state={{...state, sample: {...state.sample, selectedSlot: 18}}} />);
  expect(screen.getByTestId("sample-overview").textContent).not.toContain("48000");
  expect(screen.getByRole("img", {name: "No Sample waveform"})
    .querySelectorAll(".sample-overview-peak,.sample-overview-edge")).toHaveLength(0);
});


test.each([
  {assetId: "sample-id", category: "melodic" as const, inspect: false, pending: false, error: false, label: "MELODIC · LOADING"},
  {assetId: "sample-id", category: "melodic" as const, inspect: true, pending: true, error: false, label: "MELODIC · UPDATING"},
  {assetId: "sample-id", category: null, inspect: true, pending: false, error: true, label: "SAMPLE · CHECK LAST ACTION"},
  {assetId: null, category: null, inspect: false, pending: false, error: false, label: "EMPTY"},
])("selected Pad reports $label from its actual projection", (scenario) => {
  const base = stateWith(0, null);
  const state: CreatorState = {...base,
    project: {...base.project, current: {
      projectId: "11111111-1111-4111-8111-111111111111",
      patternId: "22222222-2222-4222-8222-222222222222",
      revision: 4, bpm: 120, assetCount: 1, assignedPadCount: scenario.assetId === null ? 0 : 1,
      bundleDigest: "a".repeat(64), key: "—", patterns: [],
      patternSlots: Array<string | null>(16).fill(null),
      sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
      pads: [{slot: 2, assetId: scenario.assetId, category: scenario.category,
        colour: null, colourOverride: null}],
    }},
    sample: {...base.sample, inspect: scenario.inspect ? base.sample.inspect : null,
      pendingAction: scenario.pending ? {kind: "update", slot: 2, expectedRevision: 4} : null,
      lastError: scenario.error ? {code: "IO_ERROR", message: "Save failed", retryPrepare: false} : null,
    },
  };
  render(<SampleOverview state={state} />);
  const overview = screen.getByTestId("sample-overview");
  expect(overview.querySelector(".sample-overview-pad")?.textContent).toBe(scenario.label);
  expect(within(overview).getByText("Format").nextElementSibling?.textContent)
    .toBe(scenario.inspect ? "mono 48000 Hz · 1.000 s" : "—");
});


test("a background update names its actual Pad after the selection changes", () => {
  const state = stateWith(0, null);
  render(<SampleOverview state={{...state, sample: {...state.sample,
    selectedSlot: 18,
    pendingAction: {kind: "update", slot: 2, expectedRevision: 4},
  }}} />);
  expect(screen.getByTestId("sample-overview").querySelector(".sample-overview-pad")?.textContent)
    .toBe("UNAVAILABLE · UPDATING PAD A03");
});
