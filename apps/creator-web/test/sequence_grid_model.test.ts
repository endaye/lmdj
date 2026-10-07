import {describe, expect, test} from "vitest";

import {
  clampSequenceGridViewport,
  createSequenceGridModel,
  clampSequenceOverviewRowOffset,
  createSequenceOverviewWindow,
  DEFAULT_SEQUENCE_GRID_SNAP,
  SEQUENCE_GRID_SNAPS,
  sequenceGridAddNote,
  sequenceGridBatchDelete,
  sequenceGridBatchMove,
  sequenceGridMoveNote,
  sequenceGridNotesInBox,
  sequenceGridRemoveNote,
  sequenceGridResizeNote,
  sequenceGridLiveSelection,
  sequenceGridSelectionVelocity,
  sequenceGridVelocityNote,
  sequenceGridFlatSlot,
  sequenceGridViewportForWindow,
  sequenceBarBeat,
  sequenceOverviewFrame,
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

test("the overview window shows eight Pad rows and only their notes", () => {
  const window = createSequenceOverviewWindow(pattern(4, [
    event(0, 0, 0, 240),
    event(0, 9, 480, 240, 80),
    event(1, 4, 960, 240, 127),
    event(3, 15, 960, 240, 64),
  ]), {rowOffset: 16, snap: "1/16"});
  expect(window.rows).toEqual([16, 17, 18, 19, 20, 21, 22, 23]);
  expect(window.lengthTicks).toBe(15360);
  expect(window.stepCount).toBe(64);
  expect(window.notes.map((note) => [note.row, note.windowRow])).toEqual([[20, 4]]);
});

test("the overview row offset stays within the 64 Pad rows", () => {
  expect(clampSequenceOverviewRowOffset(-3)).toBe(0);
  expect(clampSequenceOverviewRowOffset(56)).toBe(56);
  expect(clampSequenceOverviewRowOffset(60)).toBe(56);
  expect(clampSequenceOverviewRowOffset(Number.NaN)).toBe(0);
});

test("an overview note fills its onset step solid and the steps it covers as tail", () => {
  const notes = (snap: "1/16" | "off" | "1/4") => createSequenceOverviewWindow(pattern(1, [
    event(0, 0, 250, 500),
    event(0, 1, 0, 100),
  ]), {rowOffset: 0, snap}).notes;
  // 250–750 at 1/16 (240): onset step 240, tail 480–960.
  expect(notes("1/16")[1]).toMatchObject({onsetStepTick: 240, tailStartTick: 480, tailEndTick: 960});
  // A note shorter than its step has no tail.
  expect(notes("1/16")[0]).toMatchObject({onsetStepTick: 0, tailStartTick: 240, tailEndTick: 240});
  // Snap off draws 1/16 steps; 1/4 draws beat steps.
  expect(createSequenceOverviewWindow(pattern(1), {rowOffset: 0, snap: "off"}).stepTicks).toBe(240);
  expect(notes("1/4")[1]).toMatchObject({onsetStepTick: 0, tailStartTick: 960, tailEndTick: 960});
});

test("the overview frame is the touch grid's Bank cut to the eight rows", () => {
  const viewport = {startTick: 960, endTick: 4800};
  expect(sequenceOverviewFrame(viewport, 1, 16)).toEqual(
    {startTick: 960, endTick: 4800, firstWindowRow: 0, rowCount: 8});
  expect(sequenceOverviewFrame(viewport, 1, 12)).toEqual(
    {startTick: 960, endTick: 4800, firstWindowRow: 4, rowCount: 4});
  expect(sequenceOverviewFrame(viewport, 0, 16)).toBeNull();
});

test("bar and beat count from 001:01", () => {
  expect(sequenceBarBeat(null)).toBe("001:01");
  expect(sequenceBarBeat(0)).toBe("001:01");
  expect(sequenceBarBeat(959)).toBe("001:01");
  expect(sequenceBarBeat(960)).toBe("001:02");
  expect(sequenceBarBeat(3840 * 7 + 960 * 3)).toBe("008:04");
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

describe("grid editing gestures map to one exact command each", () => {
  const gridNote = (pad: number, onsetTick: number, durationTick: number, velocity = 100) =>
    Object.freeze({pad, onsetTick, durationTick, velocity});

  test("a tap on an empty cell adds one snapped note with the grid defaults", () => {
    expect(sequenceGridAddNote({
      bank: 0, pad: 2, tick: 700, snapTicks: 240, velocity: 100, lengthTicks: 3840,
    })).toEqual({
      remove: [],
      put: [{bank: 0, pad: 2, onsetTick: 480, durationTick: 240, velocity: 100}],
    });
    // Snap off keeps the exact tick and gives the note one 1/16 step.
    expect(sequenceGridAddNote({
      bank: 1, pad: 0, tick: 700, snapTicks: null, velocity: 100, lengthTicks: 3840,
    })).toEqual({
      remove: [],
      put: [{bank: 1, pad: 0, onsetTick: 700, durationTick: 240, velocity: 100}],
    });
    // The last velocity set in the grid becomes the new note's velocity.
    expect(sequenceGridAddNote({
      bank: 0, pad: 2, tick: 0, snapTicks: 240, velocity: 88, lengthTicks: 3840,
    })?.put[0]?.velocity).toBe(88);
  });

  test("an add clamps its length to the loop seam", () => {
    expect(sequenceGridAddNote({
      bank: 0, pad: 0, tick: 3700, snapTicks: 240, velocity: 100, lengthTicks: 3840,
    })).toEqual({
      remove: [],
      put: [{bank: 0, pad: 0, onsetTick: 3600, durationTick: 240, velocity: 100}],
    });
    expect(sequenceGridAddNote({
      bank: 0, pad: 0, tick: 3820, snapTicks: null, velocity: 100, lengthTicks: 3840,
    })).toEqual({
      remove: [],
      put: [{bank: 0, pad: 0, onsetTick: 3820, durationTick: 20, velocity: 100}],
    });
    expect(sequenceGridAddNote({
      bank: 0, pad: 0, tick: 3840, snapTicks: null, velocity: 100, lengthTicks: 3840,
    })).toEqual({
      remove: [],
      put: [{bank: 0, pad: 0, onsetTick: 3839, durationTick: 1, velocity: 100}],
    });
  });

  test("a tap on a note removes exactly its key", () => {
    expect(sequenceGridRemoveNote({bank: 0, pad: 1, onsetTick: 240})).toEqual({
      remove: [{bank: 0, pad: 1, onsetTick: 240}],
      put: [],
    });
  });

  test("a body drag moves by remove plus put; ending where it started sends nothing", () => {
    const note = gridNote(1, 240, 480, 80);
    expect(sequenceGridMoveNote({
      bank: 0, note, toPad: 3, toTick: 1240, snapTicks: 240, lengthTicks: 3840,
    })).toEqual({
      remove: [{bank: 0, pad: 1, onsetTick: 240}],
      put: [{bank: 0, pad: 3, onsetTick: 1200, durationTick: 480, velocity: 80}],
    });
    expect(sequenceGridMoveNote({
      bank: 0, note, toPad: 1, toTick: 240, snapTicks: 240, lengthTicks: 3840,
    })).toBeNull();
    // A drag shorter than half a snap step snaps to the nearest grid line.
    expect(sequenceGridMoveNote({
      bank: 0, note, toPad: 1, toTick: 100, snapTicks: 240, lengthTicks: 3840,
    })).toEqual({
      remove: [{bank: 0, pad: 1, onsetTick: 240}],
      put: [{bank: 0, pad: 1, onsetTick: 0, durationTick: 480, velocity: 80}],
    });
  });

  test("a move snaps, clamps to the seam and replaces an occupied key", () => {
    const note = gridNote(0, 0, 240);
    // Snap nearest on the landing onset.
    expect(sequenceGridMoveNote({
      bank: 0, note, toPad: 0, toTick: 300, snapTicks: 240, lengthTicks: 3840,
    })?.put[0]?.onsetTick).toBe(240);
    // Duration can never cross the seam, so the onset clamps back.
    expect(sequenceGridMoveNote({
      bank: 0, note, toPad: 0, toTick: 3700, snapTicks: 240, lengthTicks: 3840,
    })?.put[0]?.onsetTick).toBe(3600);
    expect(sequenceGridMoveNote({
      bank: 0, note, toPad: 0, toTick: 3700, snapTicks: null, lengthTicks: 3840,
    })).toEqual({
      remove: [{bank: 0, pad: 0, onsetTick: 0}],
      put: [{bank: 0, pad: 0, onsetTick: 3600, durationTick: 240, velocity: 100}],
    });
    // The occupant at the landing key is replaced by the put (key rule).
    const occupied = gridNote(2, 960, 240, 70);
    const edit = sequenceGridMoveNote({
      bank: 0, note: occupied, toPad: 2, toTick: 480, snapTicks: 240, lengthTicks: 3840,
    });
    expect(edit).toEqual({
      remove: [{bank: 0, pad: 2, onsetTick: 960}],
      put: [{bank: 0, pad: 2, onsetTick: 480, durationTick: 240, velocity: 70}],
    });
  });

  test("an end drag resizes by same-key put with seam and minimum clamps", () => {
    const note = gridNote(1, 240, 480, 80);
    expect(sequenceGridResizeNote({
      bank: 0, note, toEndTick: 1690, snapTicks: 240, lengthTicks: 3840,
    })).toEqual({
      remove: [],
      put: [{bank: 0, pad: 1, onsetTick: 240, durationTick: 1440, velocity: 80}],
    });
    // Never longer than the seam, never shorter than one snap step.
    expect(sequenceGridResizeNote({
      bank: 0, note, toEndTick: 9999, snapTicks: 240, lengthTicks: 3840,
    })?.put[0]?.durationTick).toBe(3600);
    expect(sequenceGridResizeNote({
      bank: 0, note, toEndTick: 100, snapTicks: 240, lengthTicks: 3840,
    })?.put[0]?.durationTick).toBe(240);
    expect(sequenceGridResizeNote({
      bank: 0, note, toEndTick: 241, snapTicks: null, lengthTicks: 3840,
    })?.put[0]?.durationTick).toBe(1);
    expect(sequenceGridResizeNote({
      bank: 0, note, toEndTick: 720, snapTicks: 240, lengthTicks: 3840,
    })).toBeNull();
  });

  test("a velocity drag sets a clamped same-key put and suppresses no-ops", () => {
    const note = gridNote(0, 0, 240, 100);
    expect(sequenceGridVelocityNote({bank: 0, note, velocity: 64})).toEqual({
      remove: [],
      put: [{bank: 0, pad: 0, onsetTick: 0, durationTick: 240, velocity: 64}],
    });
    expect(sequenceGridVelocityNote({bank: 0, note, velocity: 999})?.put[0]?.velocity)
      .toBe(127);
    expect(sequenceGridVelocityNote({bank: 0, note, velocity: -5})?.put[0]?.velocity)
      .toBe(1);
    expect(sequenceGridVelocityNote({bank: 0, note, velocity: 100})).toBeNull();
  });

  test("a box selection deletes as one remove batch and moves as one rigid batch", () => {
    const notes = [gridNote(0, 0, 240), gridNote(1, 240, 480, 80)];
    const keys = notes.map((note) => ({bank: 0, pad: note.pad, onsetTick: note.onsetTick}));
    expect(sequenceGridBatchDelete([])).toBeNull();
    expect(sequenceGridBatchDelete(keys)).toEqual({remove: keys, put: []});
    expect(sequenceGridBatchMove({
      bank: 0, notes, deltaTicks: 1250, deltaPads: 2, snapTicks: 240, lengthTicks: 3840,
    })).toEqual({
      remove: keys,
      put: [
        {bank: 0, pad: 2, onsetTick: 1200, durationTick: 240, velocity: 100},
        {bank: 0, pad: 3, onsetTick: 1440, durationTick: 480, velocity: 80},
      ],
    });
    // The delta clamps so no selected note leaves the grid or crosses the seam.
    expect(sequenceGridBatchMove({
      bank: 0, notes, deltaTicks: 9999, deltaPads: 99, snapTicks: 240, lengthTicks: 3840,
    })).toEqual({
      remove: keys,
      put: [
        {bank: 0, pad: 14, onsetTick: 3120, durationTick: 240, velocity: 100},
        {bank: 0, pad: 15, onsetTick: 3360, durationTick: 480, velocity: 80},
      ],
    });
    expect(sequenceGridBatchMove({
      bank: 0, notes, deltaTicks: 100, deltaPads: 0, snapTicks: 240, lengthTicks: 3840,
    })).toBeNull();
  });

  test("a batch whose origin-side note binds moves every note by the one clamped delta", () => {
    const notes = [gridNote(1, 240, 240, 90), gridNote(2, 1200, 480, 110)];
    // The note at onset 240 can move back at most 240 ticks; the whole
    // selection moves by that one delta, never by per-note deltas.
    expect(sequenceGridBatchMove({
      bank: 0, notes, deltaTicks: -9999, deltaPads: -99, snapTicks: 240,
      lengthTicks: 3840,
    })).toEqual({
      remove: [
        {bank: 0, pad: 1, onsetTick: 240},
        {bank: 0, pad: 2, onsetTick: 1200},
      ],
      put: [
        {bank: 0, pad: 0, onsetTick: 0, durationTick: 240, velocity: 90},
        {bank: 0, pad: 1, onsetTick: 960, durationTick: 480, velocity: 110},
      ],
    });
  });

  test("a batch that hits an off-grid edge stops on the snap grid", () => {
    // A recorded note at onset 100 can move back at most 100 ticks; with
    // 1/16 snap the selection must not land 100 ticks back, off the grid.
    const notes = [gridNote(0, 100, 240), gridNote(1, 1200, 240, 80)];
    expect(sequenceGridBatchMove({
      bank: 0, notes, deltaTicks: -9999, deltaPads: 0, snapTicks: 240,
      lengthTicks: 3840,
    })).toBeNull();
    // A rightward drag still clamps inside the seam: the tightened bounds
    // stay around zero, so no note lands past L − duration.
    expect(sequenceGridBatchMove({
      bank: 0, notes, deltaTicks: 9999, deltaPads: 0, snapTicks: 240,
      lengthTicks: 3840,
    })?.put.map((event) => event.onsetTick)).toEqual([2500, 3600]);
    // Snap off keeps the exact edge.
    expect(sequenceGridBatchMove({
      bank: 0, notes, deltaTicks: -9999, deltaPads: 0, snapTicks: null,
      lengthTicks: 3840,
    })?.put.map((event) => event.onsetTick)).toEqual([0, 1100]);
  });

  test("the box hit test covers pads and intersecting tick windows", () => {
    const notes = [
      gridNote(0, 0, 240),
      gridNote(1, 240, 480, 80),
      gridNote(3, 480, 240, 127),
      gridNote(1, 4800, 240, 64),
    ];
    expect(sequenceGridNotesInBox({
      notes, fromPad: 0, toPad: 1, fromTick: 7000, toTick: 200,
    })).toEqual([notes[0], notes[1], notes[3]]);
    expect(sequenceGridNotesInBox({
      notes, fromPad: 2, toPad: 2, fromTick: 0, toTick: 7680,
    })).toEqual([]);
    expect(sequenceGridSelectionVelocity(pattern(1, [
      event(0, 0, 0, 240, 100), event(0, 1, 240, 480, 80),
    ]), [{bank: 0, pad: 0, onsetTick: 0}])).toBe(100);
    expect(sequenceGridSelectionVelocity(pattern(1, [
      event(0, 0, 0, 240, 100), event(0, 1, 240, 480, 80),
    ]), [
      {bank: 0, pad: 0, onsetTick: 0},
      {bank: 0, pad: 1, onsetTick: 240},
    ])).toBe("mixed");
    expect(sequenceGridSelectionVelocity(pattern(1, [
      event(0, 0, 0, 240, 100),
    ]), [])).toBeNull();
    expect(sequenceGridSelectionVelocity(pattern(1, [
      event(0, 0, 0, 240, 100),
    ]), [{bank: 0, pad: 0, onsetTick: 480}])).toBeNull();
  });
});

test("the Host addresses Pads as flat slots, bank × 16 + pad", () => {
  expect(sequenceGridFlatSlot(0, 0)).toBe(0);
  expect(sequenceGridFlatSlot(0, 15)).toBe(15);
  expect(sequenceGridFlatSlot(1, 0)).toBe(16);
  expect(sequenceGridFlatSlot(3, 15)).toBe(63);
});

test("the live selection keeps only keys the Pattern still holds", () => {
  const events = pattern(1, [
    {slot: {bank: 0, pad: 1}, onsetTick: 0, durationTick: 240, velocity: 100},
    {slot: {bank: 0, pad: 2}, onsetTick: 480, durationTick: 240, velocity: 90},
  ]);
  const kept = {bank: 0, pad: 2, onsetTick: 480} as const;
  const selection = [kept, {bank: 0, pad: 3, onsetTick: 0}] as const;
  expect(sequenceGridLiveSelection(events, selection)).toEqual([kept]);
  const unchanged = [kept];
  expect(sequenceGridLiveSelection(events, unchanged)).toBe(unchanged);
  expect(sequenceGridLiveSelection(undefined, unchanged)).toEqual([]);
});
