import {describe, expect, test} from "vitest";

import {
  clampSequenceGridViewport,
  createSequenceGridModel,
  createSequenceGridThumbnail,
  DEFAULT_SEQUENCE_GRID_SNAP,
  SEQUENCE_GRID_SNAPS,
  sequenceGridViewportForWindow,
  sequencePatternLengthTicks,
  sequencePlayheadTick,
  sequenceSnapTicks,
  type SequenceGridPattern,
} from "../src/state/sequence_grid_model";

function event(
  bank: number,
  pad: number,
  onsetTick: number,
  durationTick: number,
  velocity = 100,
) {
  return Object.freeze({
    slot: Object.freeze({bank, pad}),
    onsetTick,
    durationTick,
    velocity,
  });
}

const pattern = (bars: 1 | 2 | 4 | 8, events: SequenceGridPattern["events"] = []) =>
  Object.freeze({bars, events});

test("the snap choices map to tick columns with 1/16 as the default", () => {
  expect(SEQUENCE_GRID_SNAPS).toEqual(["1/4", "1/8", "1/16", "1/32", "off"]);
  expect(DEFAULT_SEQUENCE_GRID_SNAP).toBe("1/16");
  expect(sequenceSnapTicks("1/4")).toBe(960);
  expect(sequenceSnapTicks("1/8")).toBe(480);
  expect(sequenceSnapTicks("1/16")).toBe(240);
  expect(sequenceSnapTicks("1/32")).toBe(120);
  expect(sequenceSnapTicks("off")).toBeNull();
});

test.each([
  {bars: 1 as const, lengthTicks: 3840, columns: 16},
  {bars: 2 as const, lengthTicks: 7680, columns: 32},
  {bars: 4 as const, lengthTicks: 15360, columns: 64},
  {bars: 8 as const, lengthTicks: 30720, columns: 128},
])("a $bars-bar Pattern spans $lengthTicks ticks and $columns snap columns at 1/16", ({bars, lengthTicks, columns}) => {
  const model = createSequenceGridModel(pattern(bars), 0, "1/16");
  expect(model.lengthTicks).toBe(lengthTicks);
  expect(sequencePatternLengthTicks(bars)).toBe(lengthTicks);
  expect(model.columnCount).toBe(columns);
});

test("snap off renders no snap columns while notes keep their tick positions", () => {
  const model = createSequenceGridModel(
    pattern(1, [event(0, 3, 120, 240)]), 0, "off");
  expect(model.snapTicks).toBeNull();
  expect(model.columnCount).toBe(0);
  expect(model.rows[3]?.notes[0]).toMatchObject({onsetTick: 120, durationTick: 240});
});

test("a note ending exactly on the loop seam keeps its full length", () => {
  const model = createSequenceGridModel(
    pattern(1, [event(0, 0, 3600, 240)]), 0, "1/16");
  const seam = model.rows[0]!.notes[0]!;
  expect(seam).toMatchObject({onsetTick: 3600, durationTick: 240});
  expect(seam.onsetTick + seam.durationTick).toBe(3840);
});

test("a note is clamped so no rectangle crosses the loop seam", () => {
  const model = createSequenceGridModel(
    pattern(1, [event(0, 0, 3800, 240)]), 0, "1/16");
  expect(model.rows[0]?.notes[0]?.durationTick).toBe(40);
});

test("overlapping notes at different onsets on one Pad all render, in onset order", () => {
  const model = createSequenceGridModel(
    pattern(1, [
      event(0, 2, 480, 960, 90),
      event(0, 2, 240, 480, 110),
    ]), 0, "1/16");
  expect(model.rows[2]?.notes).toEqual([
    {pad: 2, onsetTick: 240, durationTick: 480, velocity: 110},
    {pad: 2, onsetTick: 480, durationTick: 960, velocity: 90},
  ]);
});

test("only the active Bank's events become rows", () => {
  const model = createSequenceGridModel(
    pattern(2, [
      event(0, 0, 0, 240),
      event(2, 5, 480, 240),
      event(0, 15, 960, 240),
    ]), 0, "1/16");
  expect(model.rows).toHaveLength(16);
  expect(model.rows.map((row) => row.notes.length)).toEqual([
    1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  ]);
  const otherBank = createSequenceGridModel(
    pattern(2, [event(0, 0, 0, 240), event(2, 5, 480, 240)]), 2, "1/16");
  expect(otherBank.rows.flatMap((row) => row.notes)).toEqual([
    {pad: 5, onsetTick: 480, durationTick: 240, velocity: 100},
  ]);
});

test("the viewport clamps to the Pattern and an empty window falls back to the whole Pattern", () => {
  expect(clampSequenceGridViewport(null, 3840)).toEqual({startTick: 0, endTick: 3840});
  expect(clampSequenceGridViewport({startTick: -50, endTick: 9999}, 3840))
    .toEqual({startTick: 0, endTick: 3840});
  expect(clampSequenceGridViewport({startTick: 960, endTick: 1920}, 3840))
    .toEqual({startTick: 960, endTick: 1920});
  expect(clampSequenceGridViewport({startTick: 2000, endTick: 1000}, 3840))
    .toEqual({startTick: 0, endTick: 3840});
  const model = createSequenceGridModel(pattern(2), 0, "1/16", {
    startTick: 3840, endTick: 5760,
  });
  expect(model.viewport).toEqual({startTick: 3840, endTick: 5760});
});

test("the thumbnail maps every Bank and Pad to one of 64 rows", () => {
  const thumbnail = createSequenceGridThumbnail(pattern(4, [
    event(0, 0, 0, 240),
    event(1, 15, 480, 240, 80),
    event(3, 15, 960, 240, 127),
    event(2, 8, 480, 240, 64),
  ]));
  expect(thumbnail.rowCount).toBe(64);
  expect(thumbnail.lengthTicks).toBe(15360);
  expect(thumbnail.notes).toEqual([
    {row: 0, onsetTick: 0, durationTick: 240, velocity: 100},
    {row: 31, onsetTick: 480, durationTick: 240, velocity: 80},
    {row: 40, onsetTick: 480, durationTick: 240, velocity: 64},
    {row: 63, onsetTick: 960, durationTick: 240, velocity: 127},
  ]);
});

describe("sequenceGridViewportForWindow", () => {
  // A 48px Pad label column beside a 768px two-bar lane; the scroller shows
  // 368px at a time. The label column must never count as timeline.
  const geometry = {timelineStart: 48, timelineWidth: 768, lengthTicks: 7680};

  test("excludes the Pad label column from the reported window", () => {
    expect(sequenceGridViewportForWindow({
      windowStart: 0, windowEnd: 416, ...geometry,
    })).toEqual({startTick: 0, endTick: 3680});
  });

  test("tracks the window at a non-zero scroll offset", () => {
    expect(sequenceGridViewportForWindow({
      windowStart: 448, windowEnd: 816, ...geometry,
    })).toEqual({startTick: 4000, endTick: 7680});
  });

  test("reports the whole Pattern when the lane is fully visible or unmeasurable", () => {
    expect(sequenceGridViewportForWindow({
      windowStart: 0, windowEnd: 1000, ...geometry,
    })).toEqual({startTick: 0, endTick: 7680});
    expect(sequenceGridViewportForWindow({
      windowStart: 0, windowEnd: 0, timelineStart: 0, timelineWidth: 0,
      lengthTicks: 7680,
    })).toEqual({startTick: 0, endTick: 7680});
  });
});

describe("sequencePlayheadTick", () => {
  test("advances whole ticks from the origin frame at the Project tempo", () => {
    expect(sequencePlayheadTick({
      originFrame: 0, runtimeFrame: 24_000, bpm: 120, lengthTicks: 3840,
    })).toBe(960);
    expect(sequencePlayheadTick({
      originFrame: 96_000, runtimeFrame: 108_000, bpm: 120, lengthTicks: 3840,
    })).toBe(480);
  });

  test("wraps at the loop seam", () => {
    expect(sequencePlayheadTick({
      originFrame: 0, runtimeFrame: 96_000, bpm: 120, lengthTicks: 3840,
    })).toBe(0);
    expect(sequencePlayheadTick({
      originFrame: 0, runtimeFrame: 120_000, bpm: 120, lengthTicks: 3840,
    })).toBe(960);
  });

  test("has no playhead before the origin or for invalid timing", () => {
    expect(sequencePlayheadTick({
      originFrame: 100, runtimeFrame: 50, bpm: 120, lengthTicks: 3840,
    })).toBeNull();
    expect(sequencePlayheadTick({
      originFrame: 0, runtimeFrame: 100, bpm: 20, lengthTicks: 3840,
    })).toBeNull();
    expect(sequencePlayheadTick({
      originFrame: 0, runtimeFrame: 100, bpm: 120, lengthTicks: 0,
    })).toBeNull();
  });
});
