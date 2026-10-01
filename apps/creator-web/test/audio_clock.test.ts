import {afterEach, expect, test} from "vitest";

import {
  createRetainedAudioContext,
  contextSecondsToEngineFrame,
  engineFrameToContextSeconds,
  hasAnchor,
  invalidate,
  retainedAudioContext,
  sampleAnchor,
} from "../src/runtime/audio_clock";

function fakeSession(sample: {
  contextTimeSeconds: number;
  callbackHeartbeat: number;
  engineEpochHeartbeat: number;
}) {
  return {sampleAudioClock: () => sample};
}

afterEach(() => invalidate());

test("the injected factory retains the created context", () => {
  const created = {kind: "fake-context"};
  const original = globalThis.AudioContext;
  globalThis.AudioContext = function (this: unknown) {
    return created;
  } as unknown as typeof AudioContext;
  try {
    const context = createRetainedAudioContext({sampleRate: 48_000});
    expect(context).toBe(created);
    expect(retainedAudioContext()).toBe(created);
  } finally {
    globalThis.AudioContext = original;
  }
});

test("conversions are the identity at the sample and linear within an epoch", () => {
  const anchor = sampleAnchor(fakeSession({
    contextTimeSeconds: 10,
    callbackHeartbeat: 12,
    engineEpochHeartbeat: 2,
  }));
  expect(anchor).toEqual({contextTimeSeconds: 10, engineFrameAtSample: 1_280});
  expect(hasAnchor()).toBe(true);

  expect(engineFrameToContextSeconds(1_280)).toBe(10);
  expect(engineFrameToContextSeconds(1_280 + 48_000)).toBe(11);
  expect(contextSecondsToEngineFrame(10)).toBe(1_280);
  expect(contextSecondsToEngineFrame(10.5)).toBe(1_280 + 24_000);
});

test("a heartbeat wrap inside one epoch still converts forward", () => {
  const anchor = sampleAnchor(fakeSession({
    contextTimeSeconds: 3,
    callbackHeartbeat: 1,
    engineEpochHeartbeat: 0xffff_fffe,
  }));
  expect(anchor.engineFrameAtSample).toBe(3 * 128);
  expect(engineFrameToContextSeconds(3 * 128)).toBe(3);
});

test("a session without the accessor is refused like audio not running", () => {
  expect(() => sampleAnchor({})).toThrow(/Audio clock is unavailable/);
  expect(hasAnchor()).toBe(false);
});

test("invalidate drops the anchor and conversions refuse until re-sampled", () => {
  sampleAnchor(fakeSession({
    contextTimeSeconds: 10,
    callbackHeartbeat: 2,
    engineEpochHeartbeat: 2,
  }));
  expect(hasAnchor()).toBe(true);

  invalidate();
  expect(hasAnchor()).toBe(false);
  expect(() => engineFrameToContextSeconds(0)).toThrow(
    /Audio clock anchor is not sampled/);
  expect(() => contextSecondsToEngineFrame(0)).toThrow(
    /Audio clock anchor is not sampled/);
});

test("a new epoch re-samples the anchor and replaces the mapping", () => {
  sampleAnchor(fakeSession({
    contextTimeSeconds: 10,
    callbackHeartbeat: 2,
    engineEpochHeartbeat: 2,
  }));
  expect(engineFrameToContextSeconds(48_000)).toBe(11);

  // New epoch: the frame counter reset to zero at audio.activate, so the
  // same engine frame now maps to the new epoch's context time.
  const anchor = sampleAnchor(fakeSession({
    contextTimeSeconds: 42,
    callbackHeartbeat: 5,
    engineEpochHeartbeat: 5,
  }));
  expect(anchor.engineFrameAtSample).toBe(0);
  expect(engineFrameToContextSeconds(0)).toBe(42);
  expect(contextSecondsToEngineFrame(43)).toBe(48_000);
});
