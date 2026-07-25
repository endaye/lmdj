export type MidiBank = "A" | "B";

export type MidiMapping =
  | { mode: "direct-16"; notes: number[] }
  | { mode: "banked-8"; notes: number[] };

const STORAGE_KEY = "lmdj.midi.mapping.v1";

export const DEFAULT_DIRECT_MAPPING: MidiMapping = {
  mode: "direct-16",
  notes: Array.from({ length: 16 }, (_, index) => 36 + index),
};

export function padIndexForNote(
  mapping: MidiMapping,
  note: number,
  bank: MidiBank,
): number | null {
  const physical = mapping.notes.indexOf(note);
  if (physical < 0) return null;
  return mapping.mode === "direct-16"
    ? physical
    : physical + (bank === "A" ? 0 : 8);
}

export class MidiLearnSession {
  private readonly notes: number[] = [];
  private readonly targetCount: number;

  constructor(private readonly mode: MidiMapping["mode"]) {
    this.targetCount = mode === "direct-16" ? 16 : 8;
  }

  capture(note: number): MidiMapping | null {
    if (
      !Number.isInteger(note) ||
      note < 0 ||
      note > 127 ||
      this.notes.includes(note)
    ) {
      return null;
    }

    this.notes.push(note);
    if (this.notes.length !== this.targetCount) {
      return null;
    }

    const notes = Object.freeze([...this.notes]) as unknown as number[];
    return Object.freeze({ mode: this.mode, notes }) as MidiMapping;
  }
}

type ReadableStorage = Pick<Storage, "getItem">;
type WritableStorage = Pick<Storage, "setItem">;

export function loadMidiMapping(storage: ReadableStorage): MidiMapping {
  const serialized = storage.getItem(STORAGE_KEY);
  if (serialized === null) {
    return DEFAULT_DIRECT_MAPPING;
  }

  try {
    const value: unknown = JSON.parse(serialized);
    return isMidiMapping(value) ? value : DEFAULT_DIRECT_MAPPING;
  } catch {
    return DEFAULT_DIRECT_MAPPING;
  }
}

export function saveMidiMapping(
  storage: WritableStorage,
  mapping: MidiMapping,
): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(mapping));
}

function isMidiMapping(value: unknown): value is MidiMapping {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as { mode?: unknown; notes?: unknown };
  if (
    candidate.mode !== "direct-16" &&
    candidate.mode !== "banked-8"
  ) {
    return false;
  }
  if (!Array.isArray(candidate.notes)) {
    return false;
  }

  const expectedCount = candidate.mode === "direct-16" ? 16 : 8;
  return (
    candidate.notes.length === expectedCount &&
    candidate.notes.every(
      (note) =>
        typeof note === "number" &&
        Number.isInteger(note) &&
        note >= 0 &&
        note <= 127,
    ) &&
    new Set(candidate.notes).size === expectedCount
  );
}
