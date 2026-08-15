import {describe, expect, test} from "vitest";
import {initialCaptureState, reduceCapture} from "../src/state/capture_state";

const run = (events: Parameters<typeof reduceCapture>[1][]) =>
  events.reduce(reduceCapture, initialCaptureState);

describe("reduceCapture", () => {
  test("follows the happy path record→stop→trim→commit→idle", () => {
    let state = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 96_000, peak: 0.5},
      {kind: "stop", reason: "user"},
    ]);
    expect(state.phase).toBe("trimming");
    expect(state.selectionFrames).toBe(96_000); // clamped default ≤ 240,000
    state = reduceCapture(state, {kind: "commit"});
    expect(state.phase).toBe("committing");
    state = reduceCapture(state, {kind: "committed"});
    expect(state).toEqual(initialCaptureState);
  });

  test("clamps the default selection to COMMIT_MAX_FRAMES", () => {
    const state = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 2_880_000, peak: 1},
      {kind: "stop", reason: "capacity"},
    ]);
    expect(state.selectionFrames).toBe(240_000);
    expect(state.stopReason).toBe("capacity");
  });

  test("rejects selections above COMMIT_MAX_FRAMES", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 480_000, peak: 0.2},
      {kind: "stop", reason: "hidden"},
    ]);
    const rejected = reduceCapture(trimming, {kind: "select", start: 0, frames: 240_001});
    expect(rejected).toBe(trimming); // unchanged
  });

  test("keeps the buffer through every interruption and commit failure", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 48_000, peak: 0.4},
      {kind: "stop", reason: "device-lost"},
    ]);
    expect(trimming.frameCount).toBe(48_000);
    const failed = reduceCapture(
      reduceCapture(trimming, {kind: "commit"}),
      {kind: "commit-failed", message: "conflict", conflict: true});
    expect(failed.phase).toBe("commit-error");
    expect(failed.frameCount).toBe(48_000);
    expect(failed.conflict).toBe(true);
    expect(reduceCapture(failed, {kind: "commit"}).phase).toBe("committing");
    expect(reduceCapture(failed, {kind: "discard"})).toEqual(initialCaptureState);
  });

  test("routes permission denial to a retryable error state", () => {
    const denied = run([{kind: "record"}, {kind: "denied", message: "blocked"}]);
    expect(denied.phase).toBe("permission-error");
    expect(reduceCapture(denied, {kind: "record"}).phase).toBe("requesting-permission");
  });

  test("ignores events that are invalid for the phase", () => {
    expect(reduceCapture(initialCaptureState, {kind: "committed"})).toBe(initialCaptureState);
    expect(reduceCapture(initialCaptureState, {kind: "stop", reason: "user"})).toBe(initialCaptureState);
  });
});
