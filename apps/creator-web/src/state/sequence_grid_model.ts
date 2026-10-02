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

export interface SequenceThumbnailNote {
  readonly row: number;
  readonly onsetTick: number;
  readonly durationTick: number;
  readonly velocity: number;
}

export interface SequenceGridThumbnail {
  readonly bars: 1 | 2 | 4 | 8;
  readonly lengthTicks: number;
  readonly rowCount: number;
  readonly notes: readonly SequenceThumbnailNote[];
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

// The upper display's whole-Pattern overview: every note of all four Banks on
// one 64-row thumbnail, row = bank × 16 + pad.
export function createSequenceGridThumbnail(
  pattern: SequenceGridPattern,
): SequenceGridThumbnail {
  const lengthTicks = sequencePatternLengthTicks(pattern.bars);
  const notes: SequenceThumbnailNote[] = [];
  for (const event of pattern.events) {
    notes.push({
      row: event.slot.bank * SEQUENCE_BANK_PADS + event.slot.pad,
      onsetTick: event.onsetTick,
      durationTick: Math.min(event.durationTick, lengthTicks - event.onsetTick),
      velocity: event.velocity,
    });
  }
  notes.sort((left, right) =>
    left.onsetTick - right.onsetTick || left.row - right.row);
  return Object.freeze({
    bars: pattern.bars,
    lengthTicks,
    rowCount: SEQUENCE_BANK_COUNT * SEQUENCE_BANK_PADS,
    notes: Object.freeze(notes),
  });
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
