import {expect, test} from "vitest";
import {eqMagnitudeDb, eqResponseCurve} from "../src/components/eq_response";
import type {PadEq} from "../src/runtime/runtime_types";

const flat: PadEq = {low: null, mid: null, high: null};

test("a bypassed EQ is exactly flat across the displayed spectrum", () => {
  const curve = eqResponseCurve(flat);
  expect(curve[0]?.hz).toBe(20);
  expect(curve.at(-1)?.hz).toBe(20_000);
  expect(curve.every(point => point.db === 0)).toBe(true);
});

test("a bell reaches its stored millidB gain at its centre frequency", () => {
  // Native/display agreement could share a gain-sign or unit defect. The
  // prescribed +6 dB centre is an independent absolute expectation.
  expect(eqMagnitudeDb({...flat, mid: {freqHz: 1200, gainMillidb: 6000, qMilli: 707}}, 1200)).toBeCloseTo(6, 3);
});

test("shelf centre response is half its asymptotic gain", () => {
  expect(eqMagnitudeDb({...flat, low: {kind: "shelf", freqHz: 100, gainMillidb: 6000}}, 100)).toBeCloseTo(3, 2);
  expect(eqMagnitudeDb({...flat, high: {kind: "shelf", freqHz: 8000, gainMillidb: -6000}}, 8000)).toBeCloseTo(-3, 3);
});

test("Butterworth cuts have the original minus3dB corner", () => {
  expect(eqMagnitudeDb({...flat, low: {kind: "cut", freqHz: 100, gainMillidb: -18000}}, 100)).toBeCloseTo(-10 * Math.log10(2), 2);
  expect(eqMagnitudeDb({...flat, high: {kind: "cut", freqHz: 8000, gainMillidb: 18000}}, 8000)).toBeCloseTo(-10 * Math.log10(2), 3);
});

test("a cut ignores its retained gain just as the engine does", () => {
  const a = eqResponseCurve({...flat, low: {kind: "cut", freqHz: 120, gainMillidb: -18000}});
  const b = eqResponseCurve({...flat, low: {kind: "cut", freqHz: 120, gainMillidb: 18000}});
  expect(a).toEqual(b);
});

test("higher mid Q narrows the response without changing its centre gain", () => {
  const bell = {freqHz: 1000, gainMillidb: 6000, qMilli: 707};
  const wide = {...flat, mid: bell}, narrow = {...flat, mid: {...bell, qMilli: 4000}};
  expect(eqMagnitudeDb(narrow, 500)).toBeLessThan(eqMagnitudeDb(wide, 500));
  expect(eqMagnitudeDb(narrow, 1000)).toBeCloseTo(eqMagnitudeDb(wide, 1000), 3);
});

test("the display projection neither clamps summed gain nor mutates playback", () => {
  const eq: PadEq = Object.freeze({
    low: Object.freeze({kind: "shelf", freqHz: 1000, gainMillidb: 18000}),
    mid: Object.freeze({freqHz: 1000, gainMillidb: 18000, qMilli: 707}),
    high: Object.freeze({kind: "shelf", freqHz: 1000, gainMillidb: 18000}),
  });
  expect(eqMagnitudeDb(eq, 1000)).toBeCloseTo(36, 2);
  expect(eqResponseCurve(eq).every(point => Number.isFinite(point.db))).toBe(true);
  expect(eq.mid?.gainMillidb).toBe(18000);
});

test("display frequencies reject zero and Nyquist instead of inventing a value", () => {
  expect(() => eqMagnitudeDb(flat, 0)).toThrow(RangeError);
  expect(() => eqMagnitudeDb(flat, 24000)).toThrow(RangeError);
});
