import {expect, test} from "vitest";

import {createEncoderTurn} from "../src/state/encoder_input";

function harness(min = 40, max = 240) {
  const timers = new Map<number, () => void>();
  let next = 0;
  const previews: (number | null)[] = [];
  const commits: number[] = [];
  const turn = createEncoderTurn({
    min, max,
    schedule: (callback) => { timers.set(++next, callback); return next; },
    clear: (handle) => { timers.delete(handle as number); },
    onPreview: (value) => previews.push(value),
    onCommit: (value) => commits.push(value),
  });
  const rest = () => { const pending = [...timers.values()]; timers.clear(); pending.forEach((run) => run()); };
  return {turn, previews, commits, rest, pending: () => timers.size};
}

test("detents preview at once and one rest commits the whole turn once", () => {
  const {turn, previews, commits, rest, pending} = harness();
  turn.turn(1, 120);
  turn.turn(1, 120);
  turn.turn(1, 120);
  expect(previews).toEqual([121, 122, 123]);
  expect(commits).toEqual([]);
  expect(pending()).toBe(1);
  rest();
  expect(commits).toEqual([123]);
  expect(previews.at(-1)).toBeNull();
});

test("a turn that returns to its start commits nothing", () => {
  const {turn, commits, rest} = harness();
  turn.turn(2, 120);
  turn.turn(-2, 120);
  rest();
  expect(commits).toEqual([]);
});

test("a turn clamps to the value's range", () => {
  const {turn, previews, commits, rest} = harness(50, 75);
  turn.turn(-3, 51);
  rest();
  expect(previews[0]).toBe(50);
  expect(commits).toEqual([50]);
});

test("a cancelled turn clears its preview and never commits", () => {
  const {turn, previews, commits, rest, pending} = harness();
  turn.turn(1, 120);
  turn.cancel();
  expect(pending()).toBe(0);
  expect(previews).toEqual([121, null]);
  rest();
  expect(commits).toEqual([]);
});

test("a new turn starts from the committed value it is given", () => {
  const {turn, commits, rest} = harness();
  turn.turn(1, 120);
  rest();
  turn.turn(1, 121);
  rest();
  expect(commits).toEqual([121, 122]);
});

test("a turn begun before the previous commit lands continues from that commit", () => {
  const {turn, commits, rest} = harness();
  turn.turn(3, 120);
  rest();
  // Truth still reads 120 while the 123 commit is in flight.
  turn.turn(1, 120);
  rest();
  expect(commits).toEqual([123, 124]);
  // Once Truth catches up, turns start from it again.
  turn.turn(1, 124);
  rest();
  expect(commits).toEqual([123, 124, 125]);
});

test("a forgotten request lets the next turn start from Truth", () => {
  const {turn, commits, rest} = harness();
  turn.turn(3, 120);
  rest();
  turn.forget();
  turn.turn(1, 120);
  rest();
  expect(commits).toEqual([123, 121]);
});
