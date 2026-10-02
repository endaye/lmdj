import {expect, test} from "vitest";

import {createTapTempo} from "../src/runtime/tap_tempo";

function clock() {
  let at = 1_000;
  return {
    now: () => at,
    advance(ms: number) {
      at += ms;
    },
  };
}

test("a single tap commits nothing", () => {
  const time = clock();
  const tapTempo = createTapTempo(time.now);
  expect(tapTempo.tap()).toBeNull();
});

test("two taps commit the interval BPM", () => {
  const time = clock();
  const tapTempo = createTapTempo(time.now);
  tapTempo.tap();
  time.advance(500);
  expect(tapTempo.tap()).toBe(120);
});

test("the committed BPM is rounded to an integer", () => {
  const time = clock();
  const tapTempo = createTapTempo(time.now);
  tapTempo.tap();
  time.advance(501);
  expect(tapTempo.tap()).toBe(120);
});

test("the median of the last up-to-4 intervals wins", () => {
  const time = clock();
  const tapTempo = createTapTempo(time.now);
  tapTempo.tap();
  let committed: number | null = null;
  for (const interval of [400, 500, 600]) {
    time.advance(interval);
    committed = tapTempo.tap();
  }
  // Intervals 400, 500, 600: the median is 500 ms = 120 BPM, and the outlier
  // never moves it.
  expect(committed).toBe(120);

  const drifted = createTapTempo(time.now);
  drifted.tap();
  for (const interval of [400, 600, 500, 800]) {
    time.advance(interval);
    drifted.tap();
  }
  // The oldest interval has fallen off: 600, 500, 800, 400 sort to
  // 400, 500, 600, 800 and the median is 550 ms.
  time.advance(400);
  expect(drifted.tap()).toBe(109);
});

test("the committed BPM clamps to the 40..240 range", () => {
  const fast = clock();
  const fastTap = createTapTempo(fast.now);
  fastTap.tap();
  fast.advance(100);
  expect(fastTap.tap()).toBe(240);

  const slow = clock();
  const slowTap = createTapTempo(slow.now);
  slowTap.tap();
  slow.advance(2_000);
  expect(slowTap.tap()).toBe(40);
});

test("a gap longer than 2 seconds starts a new chain", () => {
  const time = clock();
  const tapTempo = createTapTempo(time.now);
  tapTempo.tap();
  time.advance(500);
  tapTempo.tap();
  time.advance(2_001);
  expect(tapTempo.tap()).toBeNull();
  time.advance(400);
  expect(tapTempo.tap()).toBe(150);
});
