import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import {LongSourceEditor} from "../src/components/long_source_editor";
import {DecodedLongSource} from "../src/ingest/long_source_ingest";
import type {SampleQuota} from "../src/runtime/runtime_types";

function source(): DecodedLongSource {
  const samples = Float32Array.from({length: 100}, (_, index) => index / 100);
  return new DecodedLongSource("flac", "whole-song.flac", {
    length: samples.length,
    numberOfChannels: 1,
    sampleRate: 48_000,
    getChannelData: () => samples,
  });
}

const quota: Readonly<SampleQuota> = Object.freeze({
  projectRevision: 7,
  slot: 1,
  bankQuotaBytes: 400,
  bankUsedBytes: 240,
  bankRemainingBytes: 160,
  projectQuotaBytes: 800,
  projectUsedBytes: 240,
  projectRemainingBytes: 560,
  effectiveRemainingBytes: 160,
  effectiveRemainingFrames: 40,
  consumed: Object.freeze([
    Object.freeze({slot: 0, preparedBytes: 240, preparedFrames: 60}),
  ]),
});

test("bounds selection by effective quota and retains it after a failed commit", async () => {
  const decoded = source();
  const commit = vi.fn()
    .mockResolvedValueOnce({kind: "failed", message: "quota changed; choose a shorter range"})
    .mockResolvedValueOnce({kind: "committed"});
  render(
    <LongSourceEditor
      source={decoded}
      quota={quota}
      onCommit={commit}
      onCancel={() => {}}
    />,
  );

  expect(screen.getByText(/Bank A: 0.00 s remaining/)).toBeTruthy();
  expect(screen.getByText(/Pad usage: A1: 0.00 s/)).toBeTruthy();
  const length = screen.getByRole("slider", {name: "Long source selection length"});
  expect(length.getAttribute("max")).toBe("40");
  fireEvent.change(length, {target: {value: "25"}});
  fireEvent.click(screen.getByRole("button", {name: "Commit selection"}));

  expect((await screen.findByRole("alert")).textContent).toContain("quota changed");
  expect((length as HTMLInputElement).value).toBe("25");
  expect(commit).toHaveBeenLastCalledWith({startFrame: 0, frameCount: 25});

  fireEvent.click(screen.getByRole("button", {name: "Commit selection"}));
  await waitFor(() => expect(commit).toHaveBeenCalledTimes(2));
});
