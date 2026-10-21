import {fireEvent, render, screen} from "@testing-library/react";
import {expect, test, vi} from "vitest";
import {TakeAudioReadout} from "../src/components/take_audio_readout";
import type {ProjectView} from "../src/runtime/runtime_types";
import type {TakeAudioState} from "../src/state/perform_state";

const project: ProjectView = {projectId: "11111111-1111-4111-8111-111111111111", revision: 7,
  patternId: "22222222-2222-4222-8222-222222222222", bpm: 120, assetCount: 0,
  assignedPadCount: 0, bundleDigest: "b".repeat(64), key: "—", pads: [], patterns: [],
  patternSlots: [], sequenceSettings: {quantizeEnabled: true, swingPercent: 50}};
const performance = {performanceId: "55555555-5555-4555-8555-555555555555", name: "Silent",
  eventCount: 0, createdBpm: 120, recordingArtifact: {sha256: "a".repeat(64),
    mediaType: "audio/wav" as const, byteLength: 192124}};

function verified(frames = 48017, rate: 44100 | 48000 = 48000,
  artifact = performance.recordingArtifact): TakeAudioState {
  return {owner: project, performanceId: performance.performanceId,
    artifact, state: "verified", metadata: {
      projectId: project.projectId, projectRevision: 7, performanceId: performance.performanceId,
      recordingRevision: 0, recordingArtifact: artifact,
      audioMetadata: {sampleRate: rate, channels: 2, sourceFrames: frames}, audioError: null}};
}

test.each([
  [0, 48000, "00:00.000", 56], [48017, 48000, "00:01.000", 192124],
  [44144, 44100, "00:01.000", 176632], [44145, 44100, "00:01.001", 176636],
  [48048, 48000, "00:01.001", 192248], [88641, 44100, "00:02.010", 354620],
  [86400017, 48000, "30:00.000", 345600124],
] as const)("Take WAV time uses verified frames %i at rate %i", (frames, rate, time, byteLength) => {
  const take = {...performance, recordingArtifact: {...performance.recordingArtifact, byteLength}};
  render(<TakeAudioReadout project={project} performance={take} value={verified(frames, rate, take.recordingArtifact)} onRetry={() => {}} />);
  expect(screen.getByRole("status", {name: "Take WAV audio"}).textContent).toBe(time);
  expect(screen.getByText("Recording completeness unknown")).not.toBeNull();
});

test("same-ID new Project owner and every revision/ref change hide a prior verified time before effects", () => {
  const value = verified();
  const view = render(<TakeAudioReadout project={project} performance={performance} value={value} onRetry={() => {}} />);
  expect(screen.getByRole("status", {name: "Take WAV audio"}).textContent).toBe("00:01.000");
  for (const [owner, take] of [
    [{...project}, performance],
    [{...project, revision: 8}, performance],
    [project, {...performance, performanceId: "66666666-6666-4666-8666-666666666666"}],
    [project, {...performance, recordingArtifact: {...performance.recordingArtifact, sha256: "f".repeat(64)}}],
    [project, {...performance, recordingArtifact: {...performance.recordingArtifact, byteLength: 192125}}],
  ] as const) {
    view.rerender(<TakeAudioReadout project={owner} performance={take} value={value} onRetry={() => {}} />);
    const output = screen.getByRole("status", {name: "Take WAV audio"});
    expect(output.textContent).toBe("Audio duration unavailable");
    expect(output.hasAttribute("data-frames")).toBe(false);
    expect(output.hasAttribute("data-sha256")).toBe(false);
  }
});

test.each([
  ["reading", "Checking WAV…"], ["no-wav", "No WAV attached"],
  ["damaged", "WAV integrity check failed"], ["unavailable", "Audio duration unavailable"],
] as const)("Take %s state never publishes a duration or private error", (state, label) => {
  const take = state === "no-wav" ? {...performance, recordingArtifact: null} : performance;
  const value: TakeAudioState = {owner: project, performanceId: performance.performanceId,
    artifact: take.recordingArtifact, state, metadata: null};
  render(<TakeAudioReadout project={project} performance={take} value={value} onRetry={() => {}} />);
  const output = screen.getByRole("status", {name: "Take WAV audio"});
  expect(output.textContent).toBe(label);expect(output.hasAttribute("data-frames")).toBe(false);
});

test("verified unsupported WAV retains its exact identity without invented frame count", () => {
  const value = verified();
  if (value.metadata === null) throw new Error("fixture metadata missing");
  render(<TakeAudioReadout project={project} performance={performance} value={{...value, state: "unsupported",
    metadata: {...value.metadata, audioMetadata: null,
      audioError: {code: "UNSUPPORTED_AUDIO", message: "unsupported audio", details: {}}}}} onRetry={() => {}} />);
  const output = screen.getByRole("status", {name: "Take WAV audio"});
  expect(output.textContent).toBe("WAV format unsupported");
  expect(output.getAttribute("data-sha256")).toBe("a".repeat(64));
  expect(output.hasAttribute("data-frames")).toBe(false);
});

test("the explicit retry action belongs to the selected Take readout", () => {
  const retry = vi.fn();
  render(<TakeAudioReadout project={project} performance={performance} value={null} onRetry={retry} />);
  fireEvent.click(screen.getByRole("button", {name: "Retry audio check"}));
  expect(retry).toHaveBeenCalledTimes(1);
});
