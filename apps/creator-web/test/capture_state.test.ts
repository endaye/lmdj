import {describe, expect, test} from "vitest";
import {
  CAPTURE_DEVICE_LOST_MESSAGE,
  CAPTURE_PERMISSION_REVOKED_MESSAGE,
  initialCaptureState,
  reduceCapture,
} from "../src/state/capture_state";

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

  test("keeps the buffer through every interruption reason", () => {
    for (const reason of ["user", "capacity", "blur", "hidden",
                          "device-lost", "permission-revoked"] as const) {
      const trimming = run([
        {kind: "record"}, {kind: "granted"},
        {kind: "frames", frames: 48_000, peak: 0.4},
        {kind: "stop", reason},
      ]);
      expect(trimming.phase).toBe("trimming");
      expect(trimming.frameCount).toBe(48_000);
      expect(trimming.stopReason).toBe(reason);
    }
  });

  test("retains buffer and selection through commit failure", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 480_000, peak: 0.4},
      {kind: "stop", reason: "device-lost"},
      {kind: "select", start: 1_000, frames: 200_000},
    ]);
    const failed = reduceCapture(
      reduceCapture(trimming, {kind: "commit"}),
      {kind: "commit-failed", message: "conflict", conflict: true});
    expect(failed.phase).toBe("commit-error");
    expect(failed.frameCount).toBe(480_000);
    expect(failed.selectionStart).toBe(1_000);
    expect(failed.selectionFrames).toBe(200_000);
    expect(failed.conflict).toBe(true);
    expect(reduceCapture(failed, {kind: "commit"}).phase).toBe("committing");
    expect(reduceCapture(failed, {kind: "discard"})).toEqual(initialCaptureState);
  });

  test("surfaces a failure reason when nothing was captured", () => {
    const lost = run([{kind: "record"}, {kind: "granted"},
                      {kind: "stop", reason: "device-lost"}]);
    expect(lost.phase).toBe("permission-error");
    expect(lost.errorMessage).toBe(CAPTURE_DEVICE_LOST_MESSAGE);
    expect(lost.frameCount).toBe(0);
    // still retryable
    expect(reduceCapture(lost, {kind: "record"}).phase).toBe("requesting-permission");

    const revoked = run([{kind: "record"}, {kind: "granted"},
                         {kind: "stop", reason: "permission-revoked"}]);
    expect(revoked.phase).toBe("permission-error");
    expect(revoked.errorMessage).toBe(CAPTURE_PERMISSION_REVOKED_MESSAGE);
  });

  test("returns to idle when a benign stop captured nothing", () => {
    for (const reason of ["user", "blur", "hidden"] as const) {
      expect(run([{kind: "record"}, {kind: "granted"}, {kind: "stop", reason}]))
        .toEqual(initialCaptureState);
    }
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
