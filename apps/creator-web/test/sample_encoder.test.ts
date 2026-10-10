import {expect, test, vi} from "vitest";
import {projectSamplePlayback} from "../src/state/sample_state";
import {adjustSampleEncoder, createSampleEncoderTurn} from "../src/state/sample_encoder";

const DEFAULT_PLAYBACK = projectSamplePlayback(undefined);
const metadata = {sampleRate: 48_000 as const, sourceFrames: 48_000, channels: 1 as const};

test("trim uses source frames, fine pitch/gain steps and valid loop bounds", () => {
  expect(adjustSampleEncoder(DEFAULT_PLAYBACK, metadata, "start", 1, false).trimStartFrame).toBe(480);
  expect(adjustSampleEncoder(DEFAULT_PLAYBACK, metadata, "start", 1, true).trimStartFrame).toBe(1);
  expect(adjustSampleEncoder(DEFAULT_PLAYBACK, metadata, "pitch", 1, true).pitchCents).toBe(10);
  expect(adjustSampleEncoder(DEFAULT_PLAYBACK, metadata, "gain", -1, true).gainMillidb).toBe(-100);
  const looping = {...DEFAULT_PLAYBACK, trimStartFrame: 10, trimEndFrame: 100,
    loopStartFrame: 80, loopCrossfadeFrames: 10};
  expect(adjustSampleEncoder(looping, metadata, "end", -50, true)).toMatchObject({
    trimEndFrame: 50, loopStartFrame: 49, loopCrossfadeFrames: 0,
  });
  expect(adjustSampleEncoder(looping, metadata, "start", 1000, true).trimStartFrame).toBe(99);
  expect(adjustSampleEncoder(DEFAULT_PLAYBACK, metadata, "pan", 100, false).pan).toBe(100);
});

test("all Pad parameters share one 400 ms turn and return-to-start saves nothing", () => {
  vi.useFakeTimers();
  try {
    const preview = vi.fn(), commit = vi.fn(), cancel = vi.fn();
    const turn = createSampleEncoderTurn({preview, commit, cancel,
      schedule: (cb, ms) => setTimeout(cb, ms), clear: (id) => clearTimeout(id as ReturnType<typeof setTimeout>)});
    turn.turn("pitch", 1, false, DEFAULT_PLAYBACK, metadata);
    vi.advanceTimersByTime(399);
    turn.turn("gain", -1, true, DEFAULT_PLAYBACK, metadata);
    vi.advanceTimersByTime(399);
    expect(commit).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(commit).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({pitchCents: 100, gainMillidb: -100}));
    turn.turn("tone", 1, false, DEFAULT_PLAYBACK, metadata);
    turn.turn("tone", -1, false, DEFAULT_PLAYBACK, metadata);
    vi.advanceTimersByTime(400);
    expect(commit).toHaveBeenCalledTimes(1);
    expect(cancel).toHaveBeenCalledTimes(1);
  } finally {vi.useRealTimers();}
});

test("cancel drops the pending mutation and the next Pad starts from its own Truth", () => {
  vi.useFakeTimers();
  try {
    const commit = vi.fn(), cancel = vi.fn();
    const turn = createSampleEncoderTurn({preview() {}, commit, cancel,
      schedule: (cb, ms) => setTimeout(cb, ms), clear: (id) => clearTimeout(id as ReturnType<typeof setTimeout>)});
    turn.turn("pitch", 10, false, DEFAULT_PLAYBACK, metadata);
    turn.cancel();
    vi.advanceTimersByTime(400);
    expect(commit).not.toHaveBeenCalled();
    const other = {...DEFAULT_PLAYBACK, pitchCents: -100};
    turn.turn("pitch", 1, true, other, metadata);
    vi.advanceTimersByTime(400);
    expect(commit).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({pitchCents: -90}));
    expect(cancel).toHaveBeenCalledTimes(1);
  } finally {vi.useRealTimers();}
});


test("continued turns at a limit still postpone the save until 400 ms of rest", () => {
  vi.useFakeTimers();
  try {
    const commit = vi.fn();
    const turn = createSampleEncoderTurn({preview() {}, commit, cancel() {},
      schedule: (cb, ms) => setTimeout(cb, ms), clear: (id) => clearTimeout(id as ReturnType<typeof setTimeout>)});
    turn.turn("pitch", 100, false, DEFAULT_PLAYBACK, metadata);
    vi.advanceTimersByTime(399);
    turn.turn("pitch", 1, false, DEFAULT_PLAYBACK, metadata);
    vi.advanceTimersByTime(399);
    expect(commit).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(commit).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({pitchCents: 2400}));
  } finally {vi.useRealTimers();}
});
