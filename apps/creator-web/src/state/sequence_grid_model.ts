import type {ProjectPatternView} from "../runtime/runtime_types";
import type {Bank} from "./creator_state";

// Tick geometry from the Sequence recording semantics: PPQ 960 in 4/4, so a
// bar is 3840 ticks and no event crosses the loop seam. The playhead mirrors
// the Core's transport math: tick_numerator integrates delta_frames × bpm ×
// ppq over 48000 × 60 (audio-runtime `integrate_tick_numerator`).
export const SEQUENCE_TICKS_PER_BAR = 3840;
export const SEQUENCE_BANK_COUNT = 4;
export const SEQUENCE_BANK_PADS = 16;
const SEQUENCE_PPQ = 960;
const SEQUENCE_TICK_DENOMINATOR = 2_880_000;

export type SequenceGridSnap = "1/4" | "1/8" | "1/16" | "1/32" | "off";
export const SEQUENCE_GRID_SNAPS: readonly SequenceGridSnap[] =
  Object.freeze(["1/4", "1/8", "1/16", "1/32", "off"]);
export const DEFAULT_SEQUENCE_GRID_SNAP: SequenceGridSnap = "1/16";

export function sequenceSnapTicks(snap: SequenceGridSnap): number | null {
  switch (snap) {
    case "1/4": return 960;
    case "1/8": return 480;
    case "1/16": return 240;
    case "1/32": return 120;
    case "off": return null;
  }
}

export type SequenceGridPattern = Pick<ProjectPatternView, "bars" | "events">;

export interface SequenceGridNote {
  readonly pad: number;
  readonly onsetTick: number;
  readonly durationTick: number;
  readonly velocity: number;
}

export interface SequenceGridRow {
  readonly pad: number;
  readonly notes: readonly SequenceGridNote[];
}

export interface SequenceGridViewport {
  readonly startTick: number;
  readonly endTick: number;
}

export interface SequenceGridModel {
  readonly bars: 1 | 2 | 4 | 8;
  readonly lengthTicks: number;
  readonly bank: Bank;
  readonly snap: SequenceGridSnap;
  readonly snapTicks: number | null;
  readonly columnCount: number;
  readonly rows: readonly SequenceGridRow[];
  readonly viewport: SequenceGridViewport;
}

// The upper display shows an eight-row window over all 64 Pad rows
// (row = bank × 16 + pad), each row 10 px high with a 3 px gap.
export const SEQUENCE_ROW_COUNT = SEQUENCE_BANK_COUNT * SEQUENCE_BANK_PADS;
export const SEQUENCE_OVERVIEW_ROWS = 8;
export const SEQUENCE_OVERVIEW_ROW_HEIGHT = 10;
export const SEQUENCE_OVERVIEW_ROW_PITCH = 13;
export const SEQUENCE_OVERVIEW_HEIGHT =
  SEQUENCE_OVERVIEW_ROWS * SEQUENCE_OVERVIEW_ROW_PITCH -
  (SEQUENCE_OVERVIEW_ROW_PITCH - SEQUENCE_OVERVIEW_ROW_HEIGHT);
export const SEQUENCE_TICKS_PER_BEAT = SEQUENCE_PPQ;

// One note on the overview: its onset step is drawn solid and the steps its
// length covers after that are drawn as a lighter tail.
export interface SequenceOverviewNote {
  readonly row: number;
  readonly windowRow: number;
  readonly onsetTick: number;
  readonly durationTick: number;
  readonly velocity: number;
  readonly onsetStepTick: number;
  readonly tailStartTick: number;
  readonly tailEndTick: number;
}

export interface SequenceOverviewWindow {
  readonly bars: 1 | 2 | 4 | 8;
  readonly lengthTicks: number;
  readonly stepTicks: number;
  readonly stepCount: number;
  readonly rowOffset: number;
  readonly rows: readonly number[];
  readonly notes: readonly SequenceOverviewNote[];
}

export function sequencePatternLengthTicks(bars: 1 | 2 | 4 | 8): number {
  return bars * SEQUENCE_TICKS_PER_BAR;
}

export function clampSequenceGridViewport(
  viewport: SequenceGridViewport | null,
  lengthTicks: number,
): SequenceGridViewport {
  if (viewport === null) return {startTick: 0, endTick: lengthTicks};
  const startTick = Math.min(Math.max(Math.floor(viewport.startTick), 0), lengthTicks);
  const endTick = Math.min(Math.max(Math.ceil(viewport.endTick), 0), lengthTicks);
  return endTick > startTick
    ? {startTick, endTick}
    : {startTick: 0, endTick: lengthTicks};
}

// The touch grid's visible time window, derived from the timeline lane's own
// geometry — never from the scroll port, which also holds the Pad label
// column. windowStart/windowEnd are the scroller's visible edges and
// timelineStart/timelineWidth the lane's, in the same coordinate space.
export function sequenceGridViewportForWindow(options: Readonly<{
  windowStart: number;
  windowEnd: number;
  timelineStart: number;
  timelineWidth: number;
  lengthTicks: number;
}>): SequenceGridViewport {
  const {windowStart, windowEnd, timelineStart, timelineWidth, lengthTicks} = options;
  if (!Number.isFinite(timelineWidth) || timelineWidth <= 0 ||
      !Number.isSafeInteger(lengthTicks) || lengthTicks <= 0) {
    return {startTick: 0, endTick: Math.max(0, lengthTicks)};
  }
  const timelineEnd = timelineStart + timelineWidth;
  const start = Math.min(Math.max(windowStart, timelineStart), timelineEnd);
  const end = Math.min(Math.max(windowEnd, timelineStart), timelineEnd);
  if (end <= start) return {startTick: 0, endTick: lengthTicks};
  return clampSequenceGridViewport({
    startTick: Math.floor((start - timelineStart) / timelineWidth * lengthTicks),
    endTick: Math.ceil((end - timelineStart) / timelineWidth * lengthTicks),
  }, lengthTicks);
}

function compareNotes(left: SequenceGridNote, right: SequenceGridNote): number {
  return left.onsetTick - right.onsetTick || left.pad - right.pad;
}

// One Pattern on the touch grid: the active Bank's sixteen Pad rows, note
// rectangles clamped to the loop, snap columns and the visible time window.
export function createSequenceGridModel(
  pattern: SequenceGridPattern,
  bank: Bank,
  snap: SequenceGridSnap,
  viewport: SequenceGridViewport | null = null,
): SequenceGridModel {
  const lengthTicks = sequencePatternLengthTicks(pattern.bars);
  const snapTicks = sequenceSnapTicks(snap);
  const notes: SequenceGridNote[][] =
    Array.from({length: SEQUENCE_BANK_PADS}, () => []);
  for (const event of pattern.events) {
    if (event.slot.bank !== bank) continue;
    notes[event.slot.pad]?.push({
      pad: event.slot.pad,
      onsetTick: event.onsetTick,
      durationTick: Math.min(event.durationTick, lengthTicks - event.onsetTick),
      velocity: event.velocity,
    });
  }
  const rows = notes.map((rowNotes, pad) => {
    rowNotes.sort(compareNotes);
    return Object.freeze({pad, notes: Object.freeze(rowNotes)});
  });
  return Object.freeze({
    bars: pattern.bars,
    lengthTicks,
    bank,
    snap,
    snapTicks,
    columnCount: snapTicks === null ? 0 : Math.floor(lengthTicks / snapTicks),
    rows: Object.freeze(rows),
    viewport: Object.freeze(clampSequenceGridViewport(viewport, lengthTicks)),
  });
}

export function clampSequenceOverviewRowOffset(offset: number): number {
  const last = SEQUENCE_ROW_COUNT - SEQUENCE_OVERVIEW_ROWS;
  if (!Number.isFinite(offset)) return 0;
  return Math.min(Math.max(Math.trunc(offset), 0), last);
}

// The eight Pad rows from rowOffset, with step cells at the grid snap (1/16
// when snap is off) and each note's onset step and tail in step bounds.
export function createSequenceOverviewWindow(
  pattern: SequenceGridPattern,
  options: Readonly<{rowOffset: number; snap: SequenceGridSnap}>,
): SequenceOverviewWindow {
  const lengthTicks = sequencePatternLengthTicks(pattern.bars);
  const stepTicks = sequenceSnapTicks(options.snap) ?? 240;
  const rowOffset = clampSequenceOverviewRowOffset(options.rowOffset);
  const rows = Array.from({length: SEQUENCE_OVERVIEW_ROWS}, (_, index) => rowOffset + index);
  const notes: SequenceOverviewNote[] = [];
  for (const event of pattern.events) {
    const row = event.slot.bank * SEQUENCE_BANK_PADS + event.slot.pad;
    const windowRow = row - rowOffset;
    if (windowRow < 0 || windowRow >= SEQUENCE_OVERVIEW_ROWS) continue;
    const durationTick = Math.min(event.durationTick, lengthTicks - event.onsetTick);
    const onsetStepTick = Math.floor(event.onsetTick / stepTicks) * stepTicks;
    const tailStartTick = Math.min(onsetStepTick + stepTicks, lengthTicks);
    const tailEndTick = Math.min(
      Math.ceil((event.onsetTick + durationTick) / stepTicks) * stepTicks, lengthTicks);
    notes.push({
      row,
      windowRow,
      onsetTick: event.onsetTick,
      durationTick,
      velocity: event.velocity,
      onsetStepTick,
      tailStartTick,
      tailEndTick: Math.max(tailStartTick, tailEndTick),
    });
  }
  notes.sort((left, right) =>
    left.onsetTick - right.onsetTick || left.row - right.row);
  return Object.freeze({
    bars: pattern.bars,
    lengthTicks,
    stepTicks,
    stepCount: lengthTicks / stepTicks,
    rowOffset,
    rows: Object.freeze(rows),
    notes: Object.freeze(notes),
  });
}

// The touch grid's Bank and time window, cut to the overview's eight rows.
// Null when the touch grid's Bank is scrolled out of the overview.
export function sequenceOverviewFrame(
  viewport: SequenceGridViewport,
  bank: Bank,
  rowOffset: number,
): Readonly<{startTick: number; endTick: number; firstWindowRow: number; rowCount: number}> | null {
  const offset = clampSequenceOverviewRowOffset(rowOffset);
  const first = Math.max(bank * SEQUENCE_BANK_PADS, offset);
  const end = Math.min((bank + 1) * SEQUENCE_BANK_PADS, offset + SEQUENCE_OVERVIEW_ROWS);
  if (end <= first) return null;
  return {
    startTick: viewport.startTick,
    endTick: viewport.endTick,
    firstWindowRow: first - offset,
    rowCount: end - first,
  };
}

// Bar and beat of a tick, both one-based: 001:01 is the Pattern start.
export function sequenceBarBeat(tick: number | null): string {
  const at = tick === null || !Number.isSafeInteger(tick) || tick < 0 ? 0 : tick;
  const bar = Math.floor(at / SEQUENCE_TICKS_PER_BAR) + 1;
  const beat = Math.floor((at % SEQUENCE_TICKS_PER_BAR) / SEQUENCE_TICKS_PER_BEAT) + 1;
  return `${String(bar).padStart(3, "0")}:${String(beat).padStart(2, "0")}`;
}

// Grid editing gestures map to one atomic Truth change each: keys to remove,
// then events to insert or replace by key, committed as a single
// `pattern.events.edit` at gesture end. A gesture that ends where it started
// maps to null and sends nothing.
export type SequenceGridEditMode = "note" | "vel";

export interface SequenceGridEventKey {
  readonly bank: number;
  readonly pad: number;
  readonly onsetTick: number;
}

export interface SequenceGridDraftEvent extends SequenceGridEventKey {
  readonly durationTick: number;
  readonly velocity: number;
}

export interface SequenceGridEdit {
  readonly remove: readonly SequenceGridEventKey[];
  readonly put: readonly SequenceGridDraftEvent[];
}

// A new note with snap off lasts one 1/16 step (240 ticks at PPQ 960).
const SEQUENCE_GRID_OFF_SNAP_NOTE_TICKS = 240;
const SEQUENCE_GRID_MAX_VELOCITY = 127;

function clampVelocity(velocity: number): number {
  return Math.max(1, Math.min(Math.round(velocity), SEQUENCE_GRID_MAX_VELOCITY));
}

function snapDown(tick: number, snapTicks: number): number {
  return Math.floor(tick / snapTicks) * snapTicks;
}

function snapNearest(tick: number, snapTicks: number): number {
  return Math.round(tick / snapTicks) * snapTicks;
}

function freezeEdit(
  remove: readonly SequenceGridEventKey[],
  put: readonly SequenceGridDraftEvent[],
): SequenceGridEdit {
  return Object.freeze({
    remove: Object.freeze(remove),
    put: Object.freeze(put),
  });
}

export function sameSequenceGridKey(
  left: SequenceGridEventKey,
  right: SequenceGridEventKey,
): boolean {
  return left.bank === right.bank && left.pad === right.pad &&
    left.onsetTick === right.onsetTick;
}

// The Host addresses Pads as flat slots 0..63 (bank × 16 + pad), as for
// deletePad and trigger; the grid itself works in bank/pad rows.
export function sequenceGridFlatSlot(bank: number, pad: number): number {
  return bank * SEQUENCE_BANK_PADS + pad;
}

// A pen tap on an empty cell adds a note at the cell's snapped onset; its
// length is one snap step (1/16 with snap off), clamped to the loop seam.
export function sequenceGridAddNote(options: Readonly<{
  bank: Bank;
  pad: number;
  tick: number;
  snapTicks: number | null;
  velocity: number;
  lengthTicks: number;
}>): SequenceGridEdit | null {
  const {bank, pad, tick, snapTicks, velocity, lengthTicks} = options;
  if (!Number.isInteger(pad) || pad < 0 || pad >= SEQUENCE_BANK_PADS ||
      !Number.isFinite(tick) || lengthTicks <= 0) {
    return null;
  }
  const onsetTick = snapTicks === null
    ? Math.max(0, Math.min(Math.floor(tick), lengthTicks - 1))
    : Math.max(0, Math.min(snapDown(tick, snapTicks), lengthTicks - snapTicks));
  const durationTick = Math.min(
    snapTicks ?? SEQUENCE_GRID_OFF_SNAP_NOTE_TICKS,
    lengthTicks - onsetTick,
  );
  if (durationTick < 1) return null;
  return freezeEdit([], [{
    bank, pad, onsetTick, durationTick,
    velocity: clampVelocity(velocity),
  }]);
}

export function sequenceGridRemoveNote(
  key: SequenceGridEventKey,
): SequenceGridEdit {
  return freezeEdit([key], []);
}

// A body drag moves a note: the new onset snaps to the grid and clamps so the
// note never crosses the seam. A move onto an occupied key replaces that note
// by the key rule — remove the old key and put the new one in one command.
export function sequenceGridMoveNote(options: Readonly<{
  bank: Bank;
  note: SequenceGridNote;
  toPad: number;
  toTick: number;
  snapTicks: number | null;
  lengthTicks: number;
}>): SequenceGridEdit | null {
  const {bank, note, snapTicks, lengthTicks} = options;
  if (lengthTicks <= 0 || note.durationTick < 1 ||
      note.durationTick > lengthTicks) {
    return null;
  }
  const toPad = Math.max(0, Math.min(Math.round(options.toPad), SEQUENCE_BANK_PADS - 1));
  const raw = snapTicks === null
    ? Math.round(options.toTick)
    : snapNearest(options.toTick, snapTicks);
  const onsetTick = Math.max(0, Math.min(raw, lengthTicks - note.durationTick));
  if (toPad === note.pad && onsetTick === note.onsetTick) return null;
  return freezeEdit(
    [{bank, pad: note.pad, onsetTick: note.onsetTick}],
    [{bank, pad: toPad, onsetTick,
      durationTick: note.durationTick, velocity: note.velocity}],
  );
}

// An end drag changes length: the snapped end clamps to at least one snap
// step (one tick with snap off) and never crosses the seam. Same-key put.
export function sequenceGridResizeNote(options: Readonly<{
  bank: Bank;
  note: SequenceGridNote;
  toEndTick: number;
  snapTicks: number | null;
  lengthTicks: number;
}>): SequenceGridEdit | null {
  const {bank, note, snapTicks, lengthTicks} = options;
  if (lengthTicks <= 0 || note.onsetTick < 0 || note.onsetTick >= lengthTicks) {
    return null;
  }
  const rawEnd = snapTicks === null
    ? Math.round(options.toEndTick)
    : snapNearest(options.toEndTick, snapTicks);
  const durationTick = Math.max(
    snapTicks ?? 1,
    Math.min(rawEnd - note.onsetTick, lengthTicks - note.onsetTick),
  );
  if (durationTick === note.durationTick) return null;
  return freezeEdit([], [{
    bank, pad: note.pad, onsetTick: note.onsetTick,
    durationTick, velocity: note.velocity,
  }]);
}

export function sequenceGridVelocityNote(options: Readonly<{
  bank: Bank;
  note: SequenceGridNote;
  velocity: number;
}>): SequenceGridEdit | null {
  const {bank, note} = options;
  const velocity = clampVelocity(options.velocity);
  if (velocity === note.velocity) return null;
  return freezeEdit([], [{
    bank, pad: note.pad, onsetTick: note.onsetTick,
    durationTick: note.durationTick, velocity,
  }]);
}

export function sequenceGridBatchDelete(
  keys: readonly SequenceGridEventKey[],
): SequenceGridEdit | null {
  if (keys.length === 0) return null;
  return freezeEdit([...keys], []);
}

// A drag on a selected note moves the whole selection by one rigid delta:
// snapped once, then clamped once to the intersection of every note's legal
// range so the group keeps its shape. Each note's range contains zero
// (onset ≥ 0, duration ≤ L − onset), so the intersection always holds at
// least the no-op point. Occupied landing keys are replaced by the key rule.
export function sequenceGridBatchMove(options: Readonly<{
  bank: Bank;
  notes: readonly SequenceGridNote[];
  deltaTicks: number;
  deltaPads: number;
  snapTicks: number | null;
  lengthTicks: number;
}>): SequenceGridEdit | null {
  const {bank, notes, snapTicks, lengthTicks} = options;
  if (notes.length === 0 || lengthTicks <= 0) return null;
  let lowTicks = -lengthTicks;
  let highTicks = lengthTicks;
  let lowPads = -(SEQUENCE_BANK_PADS - 1);
  let highPads = SEQUENCE_BANK_PADS - 1;
  for (const note of notes) {
    if (note.durationTick < 1 || note.durationTick > lengthTicks) return null;
    lowTicks = Math.max(lowTicks, -note.onsetTick);
    highTicks = Math.min(highTicks, lengthTicks - note.durationTick - note.onsetTick);
    lowPads = Math.max(lowPads, -note.pad);
    highPads = Math.min(highPads, SEQUENCE_BANK_PADS - 1 - note.pad);
  }
  // With snap on, the bounds tighten to snap multiples so a drag that hits
  // an edge stops on the grid instead of at the edge's off-grid tick. Zero
  // is a snap multiple inside every range, so the no-op point survives.
  if (snapTicks !== null) {
    lowTicks = Math.ceil(lowTicks / snapTicks) * snapTicks;
    highTicks = Math.floor(highTicks / snapTicks) * snapTicks;
  }
  const deltaTicks = Math.max(lowTicks, Math.min(
    snapTicks === null
      ? Math.round(options.deltaTicks)
      : snapNearest(options.deltaTicks, snapTicks),
    highTicks,
  ));
  const deltaPads = Math.max(lowPads, Math.min(
    Math.round(options.deltaPads),
    highPads,
  ));
  if (deltaTicks === 0 && deltaPads === 0) return null;
  return freezeEdit(
    notes.map((note) => ({bank, pad: note.pad, onsetTick: note.onsetTick})),
    notes.map((note) => ({
      bank,
      pad: note.pad + deltaPads,
      onsetTick: note.onsetTick + deltaTicks,
      durationTick: note.durationTick,
      velocity: note.velocity,
    })),
  );
}

// The box-select hit test: a note joins the selection when its Pad sits
// between the drag's rows and its [onset, onset + duration) interval
// intersects the drag's tick window.
export function sequenceGridNotesInBox(options: Readonly<{
  notes: readonly SequenceGridNote[];
  fromPad: number;
  toPad: number;
  fromTick: number;
  toTick: number;
}>): SequenceGridNote[] {
  const padLow = Math.min(options.fromPad, options.toPad);
  const padHigh = Math.max(options.fromPad, options.toPad);
  const tickLow = Math.min(options.fromTick, options.toTick);
  const tickHigh = Math.max(options.fromTick, options.toTick);
  return options.notes.filter((note) =>
    note.pad >= padLow && note.pad <= padHigh &&
    note.onsetTick < tickHigh && note.onsetTick + note.durationTick > tickLow);
}

// The selection keys that still name an event of the Pattern. An Undo, a
// transport settle or an edit from another surface can change events in
// place; a key it removed must leave the selection. Returns the same array
// when nothing was dropped, so a caller can skip the state update.
export function sequenceGridLiveSelection(
  pattern: SequenceGridPattern | undefined,
  selection: readonly SequenceGridEventKey[],
): readonly SequenceGridEventKey[] {
  if (selection.length === 0) return selection;
  if (pattern === undefined) return [];
  const live = new Set(pattern.events.map((event) =>
    `${event.slot.bank}:${event.slot.pad}:${event.onsetTick}`));
  const kept = selection.filter((key) =>
    live.has(`${key.bank}:${key.pad}:${key.onsetTick}`));
  return kept.length === selection.length ? selection : kept;
}

// The overview's velocity fact: the one velocity every selected note shares,
// "mixed" when they differ, null with no live selection.
export function sequenceGridSelectionVelocity(
  pattern: SequenceGridPattern,
  selection: readonly SequenceGridEventKey[],
): number | "mixed" | null {
  if (selection.length === 0) return null;
  const selected = new Set(selection.map((key) =>
    `${key.bank}:${key.pad}:${key.onsetTick}`));
  const velocities = new Set<number>();
  for (const event of pattern.events) {
    if (selected.has(
      `${event.slot.bank}:${event.slot.pad}:${event.onsetTick}`)) {
      velocities.add(event.velocity);
    }
  }
  if (velocities.size === 0) return null;
  return velocities.size === 1 ? [...velocities][0]! : "mixed";
}

// The live playhead for a playing transport: whole ticks since the Pattern
// origin frame, wrapped into the loop. Frames run at the transport's 48 kHz.
export function sequencePlayheadTick(options: Readonly<{
  originFrame: number;
  runtimeFrame: number;
  bpm: number;
  lengthTicks: number;
}>): number | null {
  const {originFrame, runtimeFrame, bpm, lengthTicks} = options;
  if (!Number.isSafeInteger(originFrame) || !Number.isSafeInteger(runtimeFrame) ||
      runtimeFrame < originFrame ||
      !Number.isSafeInteger(bpm) || bpm < 40 || bpm > 240 ||
      !Number.isSafeInteger(lengthTicks) || lengthTicks <= 0) {
    return null;
  }
  const numerator = (runtimeFrame - originFrame) * bpm * SEQUENCE_PPQ;
  return Math.floor(numerator / SEQUENCE_TICK_DENOMINATOR) % lengthTicks;
}
