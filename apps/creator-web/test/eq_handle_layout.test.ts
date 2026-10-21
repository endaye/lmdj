import {expect, test} from "vitest";
import {layoutEqHandles, minimumEqPlotHeight, type EqHandlePoints} from "../src/components/eq_handle_layout";

function expectWholeDistinctTargets(points: EqHandlePoints, width: number, height: number) {
  for (const p of points) {
    expect(p.x - 22).toBeGreaterThanOrEqual(0); expect(p.x + 22).toBeLessThanOrEqual(width);
    expect(p.y - 22).toBeGreaterThanOrEqual(0); expect(p.y + 22).toBeLessThanOrEqual(height);
  }
  for (let a = 0; a < 3; ++a) for (let b = a + 1; b < 3; ++b) {
    expect(Math.abs(points[a]!.x - points[b]!.x) >= 44 ||
      Math.abs(points[a]!.y - points[b]!.y) >= 44).toBe(true);
  }
}

test("separated contained controls retain their data positions", () => {
  const points: EqHandlePoints = [{x: 60, y: 65}, {x: 130, y: 65}, {x: 210, y: 65}];
  expect(layoutEqHandles(points, 250, 132)).toEqual(points);
});

test.each([45, 64, 89, 90.25, 132, 152, 200, 226, 336, 680])(
  "three complete targets remain distinct at canvas width %s", width => {
    const height = Math.max(132, minimumEqPlotHeight(width));
    const cases: EqHandlePoints[] = [
      [{x: width / 2, y: height / 2}, {x: width / 2, y: height / 2}, {x: width / 2, y: height / 2}],
      [{x: 0, y: 0}, {x: 1, y: 1}, {x: 2, y: 2}],
      [{x: width, y: height}, {x: width - 1, y: height - 1}, {x: width - 2, y: height - 2}],
      [{x: 0, y: height}, {x: width, y: 0}, {x: width / 2, y: height / 2}],
      [{x: width / 2, y: 30}, {x: width / 2 + 2, y: 31}, {x: width / 2 + 4, y: 32}],
    ];
    for (const points of cases) for (const active of [undefined, 0, 1, 2]) {
      const before = structuredClone(points);
      const placed = layoutEqHandles(points, width, height, active);
      expectWholeDistinctTargets(placed, width, height);
      expect(points).toEqual(before);
      expect(layoutEqHandles(points, width, height, active)).toEqual(placed);
    }
  },
);

test("the grabbed control retains its preferred pointer offset while neighbours yield", () => {
  const points: EqHandlePoints = [{x: 140, y: 60}, {x: 143, y: 65}, {x: 145, y: 62}];
  for (const active of [0, 1, 2]) {
    const placed = layoutEqHandles(points, 226, 132, active);
    expect(placed[active]).toEqual(points[active]);
    expectWholeDistinctTargets(placed, 226, 132);
  }
});

test("the reported phone Mid/High overlap retains both full targets", () => {
  const points: EqHandlePoints = [{x: 61.5, y: 57.4}, {x: 143, y: 48.7}, {x: 183.5, y: 57.4}];
  expectWholeDistinctTargets(layoutEqHandles(points, 226, 132), 226, 132);
});

test("only a plot narrower than two targets needs more than the normal132px height", () => {
  expect(minimumEqPlotHeight(90.25)).toBeLessThanOrEqual(132);
  expect(minimumEqPlotHeight(80)).toBeGreaterThan(132);
});
