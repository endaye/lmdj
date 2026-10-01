import {expect, test, vi} from "vitest";

import {createMetronomeClickLoop} from "../src/runtime/metronome_click";

class FakeParam {
  value = 0;
  setValueAtTime = vi.fn();
  exponentialRampToValueAtTime = vi.fn();
}

class FakeOscillator {
  type = "";
  frequency = new FakeParam();
  connects: unknown[] = [];
  startedAt: number | null = null;
  scheduledStopAt: number | null = null;
  stopCalls = 0;
  disconnected = false;
  connect(node: unknown) {
    this.connects.push(node);
    return node;
  }
  start(when: number) {
    this.startedAt = when;
  }
  stop(when?: number) {
    this.stopCalls += 1;
    if (when !== undefined) this.scheduledStopAt = when;
  }
  disconnect() {
    this.disconnected = true;
  }
}

class FakeGain {
  gain = new FakeParam();
  connects: unknown[] = [];
  disconnected = false;
  connect(node: unknown) {
    this.connects.push(node);
    return node;
  }
  disconnect() {
    this.disconnected = true;
  }
}

function fakeContext() {
  const oscillators: FakeOscillator[] = [];
  const gains: FakeGain[] = [];
  const context = {
    currentTime: 0,
    destination: {role: "destination"},
    createOscillator() {
      const oscillator = new FakeOscillator();
      oscillators.push(oscillator);
      return oscillator;
    },
    createGain() {
      const gain = new FakeGain();
      gains.push(gain);
      return gain;
    },
  };
  return {
    context: context as unknown as AudioContext & {currentTime: number},
    oscillators,
    gains,
  };
}

function fakeTimers() {
  let tick: (() => void) | null = null;
  return {
    setTimer: (next: () => void) => {
      tick = next;
      return next;
    },
    clearTimer: () => {
      tick = null;
    },
    fire() {
      tick?.();
    },
  };
}

function collectClicks() {
  const events: Array<{contextTime: number; beat: number; accent: boolean}> = [];
  const target = {
    dispatchEvent(event: Event) {
      events.push((event as CustomEvent).detail);
      return true;
    },
  };
  return {target, events};
}

test("a scheduled click starts on its context time and connects straight to the destination", () => {
  const {context, oscillators, gains} = fakeContext();
  const {target, events} = collectClicks();
  const loop = createMetronomeClickLoop({
    context,
    eventTarget: target,
    supply: () => [{contextTime: 1.5, beat: 2, accent: false}],
  });
  loop.start(0);

  expect(oscillators).toHaveLength(1);
  expect(gains).toHaveLength(1);
  const oscillator = oscillators[0]!;
  const gain = gains[0]!;
  expect(oscillator.startedAt).toBe(1.5);
  expect(oscillator.scheduledStopAt).toBeCloseTo(1.54, 9);
  expect(oscillator.frequency.value).toBe(1_200);
  // Oscillator → envelope → destination, and nowhere else: the Perform
  // master tap is the only capture point and the click never touches it.
  expect(oscillator.connects).toEqual([gain]);
  expect(gain.connects).toEqual([context.destination]);
  expect(gain.gain.setValueAtTime).toHaveBeenCalledWith(0.2, 1.5);
  expect(gain.gain.exponentialRampToValueAtTime)
    .toHaveBeenCalledWith(0.0001, expect.closeTo(1.54, 9));
  expect(events).toEqual([{contextTime: 1.5, beat: 2, accent: false}]);
  loop.stop();
});

test("an accented click uses the higher pitch", () => {
  const {context, oscillators} = fakeContext();
  const loop = createMetronomeClickLoop({
    context,
    supply: () => [{contextTime: 0.5, beat: 0, accent: true}],
  });
  loop.start(0);
  expect(oscillators[0]!.frequency.value).toBe(1_800);
  loop.stop();
});

test("the timer only tops up: overlapping windows never double-schedule a beat", () => {
  const {context, oscillators} = fakeContext();
  const timers = fakeTimers();
  const beats = [{contextTime: 1.0, beat: 0, accent: true}];
  const loop = createMetronomeClickLoop({
    context,
    ...timers,
    supply: () => beats,
  });
  loop.start(0);
  timers.fire();
  timers.fire();
  expect(oscillators).toHaveLength(1);
  loop.stop();
});

test("stop cancels every click that has not sounded and keeps sounded ones", () => {
  const {context, oscillators, gains} = fakeContext();
  const loop = createMetronomeClickLoop({
    context,
    supply: () => [
      {contextTime: 0.01, beat: 0, accent: true},
      {contextTime: 10, beat: 1, accent: false},
    ],
  });
  loop.start(0);
  expect(oscillators).toHaveLength(2);
  context.currentTime = 0.05;
  loop.stop();

  const sounded = oscillators[0]!;
  const pending = oscillators[1]!;
  // The already-sounding click keeps its one scheduled stop and is left to
  // decay; the pending one is stopped and disconnected immediately.
  expect(sounded.stopCalls).toBe(1);
  expect(sounded.disconnected).toBe(false);
  expect(pending.stopCalls).toBe(2);
  expect(pending.disconnected).toBe(true);
  expect(gains[1]!.disconnected).toBe(true);
  expect(loop.isRunning()).toBe(false);
});

test("each scheduled click dispatches lmdj:metronome-click with its identity", () => {
  const {context} = fakeContext();
  const {target, events} = collectClicks();
  const timers = fakeTimers();
  const loop = createMetronomeClickLoop({
    context,
    eventTarget: target,
    ...timers,
    supply: (from, until) =>
      [{contextTime: 1.0, beat: 4, accent: true}]
        .filter(({contextTime}) => contextTime >= from && contextTime < until),
  });
  loop.start(0);
  expect(events).toEqual([]);
  context.currentTime = 0.95;
  timers.fire();
  expect(events).toEqual([{contextTime: 1.0, beat: 4, accent: true}]);
  loop.stop();
});

test("the loop observes lmdj:metronome-click on the window by default", () => {
  const {context} = fakeContext();
  const events: Array<{contextTime: number; beat: number; accent: boolean}> = [];
  const listener = (event: Event) => {
    events.push((event as CustomEvent).detail);
  };
  window.addEventListener("lmdj:metronome-click", listener);
  try {
    const loop = createMetronomeClickLoop({
      context,
      supply: () => [{contextTime: 0.25, beat: 3, accent: false}],
    });
    loop.start(0);
    expect(events).toEqual([{contextTime: 0.25, beat: 3, accent: false}]);
    loop.stop();
  } finally {
    window.removeEventListener("lmdj:metronome-click", listener);
  }
});
