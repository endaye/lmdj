import {expect, test} from "vitest";
import type {PatternCountInReceipt, PatternCountInStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {countInMetronomeArm, initialCountInState, type CountInState} from "../src/runtime/count_in_controller";

// #2394: the JS click loop used to start only after a polled transport
// inspect saw `playing`; a Control stall right after S then lost beat 1. The
// loop now pre-arms from the count-in's planned start frame S: beat 0 at S
// stays Native's, so JS's first click is beat 1 at S + one beat, scheduled
// without waiting for any poll.
const S = 196_000;
const ticket = {sessionId: "s", commandId: "c", runtimeGeneration: "1", frameEpoch: "2", scheduleSerial: "3"};
const receipt = (result: PatternCountInReceipt["result"]): PatternCountInReceipt => ({
  runtimeGeneration: "1", frameEpoch: "2", scheduleSerial: "3", transportEpoch: "1",
  patternGeneration: "1", patternId: "p", result,
  effectiveFrame: result === "applied" ? S : null, originFrame: result === "applied" ? S : null,
  playing: result === "applied",
});
function counting(change: Partial<PatternCountInStatus> = {}, countIn: Partial<NonNullable<PatternCountInStatus["countIn"]>> = {}): CountInState {
  return {...initialCountInState, active: true, phase: "counting", ticket,
    status: {ticket, countIn: {runtimeGeneration: "1", frameEpoch: "2", scheduleSerial: "3", phase: "armed",
      bars: 1, bpm: 120, barFrames: 96_000, countInFrame: 100_000, startFrame: S, ...countIn},
    startReceipt: null, cancelReceipt: null, openingPending: false, openingComplete: false,
    observedAtMilliseconds: 0, error: null, ...change}};
}

test("an armed count-in arms the metronome at its planned S and leaves S to Native", () => {
  expect(countInMetronomeArm(counting())).toEqual({originFrame: S, downbeatFrame: S});
});

test("an Applied start keeps the same arm, so the loop is not rebuilt at S", () => {
  const applied: CountInState = {...counting({startReceipt: receipt("applied")}),
    recording: true, phase: "recording", nativeDownbeatFrame: S};
  expect(countInMetronomeArm(applied)).toEqual({originFrame: S, downbeatFrame: S});
});

test("no plan, a refused or cancelled start, or a cancellation disarms it", () => {
  expect(countInMetronomeArm(initialCountInState)).toBeNull();
  expect(countInMetronomeArm(counting({}, {startFrame: null}))).toBeNull();
  expect(countInMetronomeArm(counting({startReceipt: receipt("refused")}))).toBeNull();
  expect(countInMetronomeArm(counting({startReceipt: receipt("cancelled")}))).toBeNull();
  expect(countInMetronomeArm(counting({cancelReceipt: receipt("cancelled")}))).toBeNull();
  expect(countInMetronomeArm({...counting(), active: false})).toBeNull();
});
