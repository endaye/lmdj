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

test("D03 upper screen names the Pad, the format and the trim selection over the whole waveform", () => {
  render(<SampleOverview state={stateWith(4_800, 43_200)} />);
  const overview = screen.getByTestId("sample-overview");
  expect(overview.textContent).toMatch(/^PAD A03/);
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
