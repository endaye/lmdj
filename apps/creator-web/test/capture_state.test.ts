import {describe, expect, test} from "vitest";
import {
  CAPTURE_BLUR_STOP_MESSAGE,
  CAPTURE_CAPACITY_STOP_MESSAGE,
  CAPTURE_DEVICE_LOST_MESSAGE,
  CAPTURE_HIDDEN_STOP_MESSAGE,
  CAPTURE_USER_STOP_MESSAGE,
  captureStopReasonMessage,
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
      {kind: "stop", reason: "user", maximumFrames: 240_000},
    ]);
    expect(state.phase).toBe("trimming");
    expect(state.selectionFrames).toBe(96_000); // clamped default ≤ 240,000
    state = reduceCapture(state, {kind: "commit"});
    expect(state.phase).toBe("committing");
    state = reduceCapture(state, {kind: "committed"});
    expect(state).toEqual(initialCaptureState);
  });

  test("clamps the default selection to the queried effective quota", () => {
    const state = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 2_880_000, peak: 1},
      {kind: "stop", reason: "capacity", maximumFrames: 1_000_000},
    ]);
    expect(state.selectionFrames).toBe(1_000_000);
    expect(state.stopReason).toBe("capacity");
  });

  test("rejects selections above the queried effective quota", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 480_000, peak: 0.2},
      {kind: "stop", reason: "hidden", maximumFrames: 240_000},
    ]);
    const rejected = reduceCapture(trimming, {kind: "select", start: 0, frames: 240_001});
    expect(rejected).toBe(trimming); // unchanged
  });

  test("keeps the buffer through every interruption reason", () => {
    for (const reason of ["user", "capacity", "blur", "hidden", "device-lost"] as const) {
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

  test("rebases an exact commit-error selection after Crop and clears retry errors", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 480_000, peak: 0.4},
      {kind: "stop", reason: "device-lost"},
      {kind: "select", start: 1_000, frames: 200_000},
    ]);
    const failed = reduceCapture(
      reduceCapture(trimming, {kind: "commit"}),
      {kind: "commit-failed", message: "conflict", conflict: true},
    );

    const cropped = reduceCapture(failed, {kind: "crop", frames: 200_000});

    expect(cropped).toMatchObject({
      phase: "trimming",
      frameCount: 200_000,
      selectionStart: 0,
      selectionFrames: 200_000,
      errorMessage: null,
      conflict: false,
      stopReason: "device-lost",
    });
  });

  test("ignores Crop outside editing phases or when frames diverge from the selection", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 96_000, peak: 0.4},
      {kind: "stop", reason: "user"},
      {kind: "select", start: 12_000, frames: 48_000},
    ]);

    expect(reduceCapture(initialCaptureState, {kind: "crop", frames: 1}))
      .toBe(initialCaptureState);
    expect(reduceCapture(trimming, {kind: "crop", frames: 47_999})).toBe(trimming);
    expect(reduceCapture(trimming, {kind: "crop", frames: 48_000.5})).toBe(trimming);
  });

  test("surfaces a failure reason when nothing was captured", () => {
    const lost = run([{kind: "record"}, {kind: "granted"},
                      {kind: "stop", reason: "device-lost"}]);
    expect(lost.phase).toBe("permission-error");
    expect(lost.errorMessage).toBe(CAPTURE_DEVICE_LOST_MESSAGE);
    expect(lost.frameCount).toBe(0);
    // still retryable
    expect(reduceCapture(lost, {kind: "record"}).phase).toBe("requesting-permission");
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

describe("captureStopReasonMessage", () => {
  // This is the single source of truth the panel imports instead of keeping
  // its own copy (Finding 4): asserting every branch here is what would
  // catch the two copies drifting apart again.
  test("maps every stop reason to its message, and null to null", () => {
    expect(captureStopReasonMessage("user")).toBe(CAPTURE_USER_STOP_MESSAGE);
    expect(captureStopReasonMessage("capacity")).toBe(CAPTURE_CAPACITY_STOP_MESSAGE);
    expect(captureStopReasonMessage("blur")).toBe(CAPTURE_BLUR_STOP_MESSAGE);
    expect(captureStopReasonMessage("hidden")).toBe(CAPTURE_HIDDEN_STOP_MESSAGE);
    expect(captureStopReasonMessage("device-lost")).toBe(CAPTURE_DEVICE_LOST_MESSAGE);
    expect(captureStopReasonMessage(null)).toBeNull();
  });

  test("the device-lost message covers both device loss and permission revocation (S8B-D11)", () => {
    // The browser reports both causes identically (the track's "ended"
    // event) and there is no cross-browser way to tell them apart, so the
    // single remaining message must not claim it was specifically the device.
    expect(CAPTURE_DEVICE_LOST_MESSAGE).toContain("unavailable");
    expect(CAPTURE_DEVICE_LOST_MESSAGE).toContain("permission");
  });
});
