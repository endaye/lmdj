import {expect, test, vi} from "vitest";
import type {StereoOutputMeter} from "@lmdj/web-runtime-platform/runtime_types";
import {formatDbfs, meterPercent, OUTPUT_METER_UNAVAILABLE, peakDbfs,
  projectOutputMeter} from "../src/state/output_meter";

type Measurement = Extract<StereoOutputMeter, {state: "available"}>;
const owner = "11111111-1111-4111-8111-111111111111";
function measurement(contextFrame = 50_400, change: Partial<Measurement> = {}): Measurement {
  const sampleRate = change.sampleRate ?? 48_000;
  return {state: "available", owner, sampleRate, renderQuantumFrames: 128,
    windowStartFrame: "48000", windowEndFrame: "50400",
    leftPeak: 0.5, rightPeak: 0.25, leftPeakFrame: "48000", rightPeakFrame: "49000",
    contextTimeSeconds: contextFrame / sampleRate, ...change};
}
const low = (frame: number, change: Partial<Measurement> = {}) => measurement(frame, {
  windowStartFrame: "93600", windowEndFrame: "96000", leftPeakFrame: "95000",
  rightPeakFrame: "95000", leftPeak: 0.1, rightPeak: 0.01, ...change,
});
const available = (value: ReturnType<typeof projectOutputMeter>) => {
  expect(value.state).toBe("available");
  if (value.state !== "available") throw new Error("Missing measured view");
  return value;
};

test("L/R dBFS has independent literal amplitude oracles", () => {
  const value = available(projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement()));
  expect(value.left.dbfs).toBeCloseTo(-6.020599913, 8);
  expect(value.right.dbfs).toBeCloseTo(-12.041199827, 8);
});

test("only actual digital zero displays negative infinity", () => {
  expect(peakDbfs(0)).toBe(-Infinity);
  expect(formatDbfs(peakDbfs(0))).toBe("−∞");
  expect(formatDbfs(peakDbfs(1e-10))).toBe("−60.0");
});

test("nonzero display range clamps at minus60 and0 without changing measured peaks", () => {
  const value = available(projectOutputMeter(OUTPUT_METER_UNAVAILABLE,
    measurement(50_400, {leftPeak: 0.00001, rightPeak: 2})));
  expect(value.left).toMatchObject({peak: 0.00001, dbfs: -60});
  expect(value.right).toMatchObject({peak: 2, dbfs: 0});
});

test.each([[-Infinity, "−∞"], [-60, "−60.0"], [-6.020599913, "−6.0"],
  [-0.001, "0.0"], [0, "0.0"]])("formats %s dBFS as %s", (value, expected) => {
  expect(formatDbfs(value)).toBe(expected);
});

test.each([[-Infinity, 0], [-60, 0], [-30, 50], [0, 100]])(
  "%s dBFS occupies %s percent of the fixed range", (value, expected) => {
    expect(meterPercent(value)).toBe(expected);
  });

test("a lower measured value keeps each independent peak until its exact one-second frame", () => {
  const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement());
  const before = available(projectOutputMeter(initial, low(95_999)));
  expect(before.left.heldPeak).toBe(0.5);
  expect(before.right.heldPeak).toBe(0.25);
  const leftExpires = available(projectOutputMeter(before, low(96_000)));
  expect(leftExpires.left.heldPeak).toBe(0.1);
  expect(leftExpires.right.heldPeak).toBe(0.25);
  const rightExpires = available(projectOutputMeter(leftExpires, low(97_000)));
  expect(rightExpires.right.heldPeak).toBe(0.01);
});

test("re-reading one packet cannot restart a hold at its arrival time", () => {
  let value = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement());
  for (let frame = 95_900; frame < 96_000; frame += 10) value = projectOutputMeter(value, low(frame));
  expect(available(value).left.heldPeakFrame).toBe("48000");
  expect(available(projectOutputMeter(value, low(96_000))).left.heldPeak).toBe(0.1);
});

test("hold uses advancing AudioContext frames even when the wall clock is frozen", () => {
  const now = vi.spyOn(Date, "now").mockReturnValue(1);
  try {
    const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement());
    expect(available(projectOutputMeter(initial, low(96_000))).left.heldPeak).toBe(0.1);
    expect(now).not.toHaveBeenCalled();
  } finally { now.mockRestore(); }
});

test("an equal peak refreshes only to the actual new peak frame", () => {
  const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement());
  const equal = projectOutputMeter(initial, measurement(74_400, {
    windowStartFrame: "72000", windowEndFrame: "74400", leftPeakFrame: "72000",
    rightPeakFrame: "72000",
  }));
  const later = (frame: number) => low(frame, {windowStartFrame: "117600",
    windowEndFrame: "120000", leftPeakFrame: "119000", rightPeakFrame: "119000"});
  const before = available(projectOutputMeter(equal, later(119_999)));
  expect(before.left.heldPeakFrame).toBe("72000");
  expect(available(projectOutputMeter(before, later(120_000))).left.heldPeak).toBe(0.1);
});

test("one-second hold follows the actual sample rate rather than a fixed48000", () => {
  const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE,
    measurement(2_400, {sampleRate: 44_100, windowStartFrame: "0", windowEndFrame: "2205",
      leftPeakFrame: "0", rightPeakFrame: "0"}));
  const value = available(projectOutputMeter(initial, low(44_100, {sampleRate: 44_100,
    windowStartFrame: "41900", windowEndFrame: "44105", leftPeakFrame: "44000", rightPeakFrame: "44000"})));
  expect(value.left.heldPeak).toBe(0.1);
});

test("a replacement owner starts with its own current measurement", () => {
  const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement());
  const value = available(projectOutputMeter(initial, low(95_999,
    {owner: "22222222-2222-4222-8222-222222222222"})));
  expect(value.left.heldPeak).toBe(0.1);
});

test("a new rate cannot inherit a previous clock's held peak", () => {
  const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement());
  const value = measurement(50_000, {sampleRate: 44_100, windowStartFrame: "47595",
    windowEndFrame: "49800", leftPeakFrame: "49700", rightPeakFrame: "49700", leftPeak: 0.1});
  expect(available(projectOutputMeter(initial, value)).left.heldPeak).toBe(0.1);
});

test.each(["unconfigured", "not-running", "pending", "stale", "tap-unavailable",
  "processor-failed", "protocol-error", "clock-invalid", "closed"] as const)(
  "%s clears the measured view and its hold", reason => {
    const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, measurement());
    const unavailable = projectOutputMeter(initial, {state: "unavailable", reason});
    expect(unavailable).toEqual({state: "unavailable", reason});
    expect(available(projectOutputMeter(unavailable, low(95_999))).left.heldPeak).toBe(0.1);
  });

test("unchanged measured packets do not rerender at animation-frame frequency", () => {
  const input = Object.freeze(measurement());
  const initial = projectOutputMeter(OUTPUT_METER_UNAVAILABLE, input);
  expect(projectOutputMeter(initial, {...input, contextTimeSeconds: 1.06})).toBe(initial);
  expect(input.leftPeakFrame).toBe("48000");
  expect(Object.isFrozen(initial)).toBe(true);
});
