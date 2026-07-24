import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_DIRECT_MAPPING,
  MidiLearnSession,
  loadMidiMapping,
  padIndexForNote,
  saveMidiMapping,
  type MidiMapping,
} from "./mapping";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

describe("padIndexForNote", () => {
  it("maps the default sixteen-note range directly regardless of bank", () => {
    expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 36, "A")).toBe(0);
    expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 51, "B")).toBe(15);
  });

  it("maps one eight-note controller onto the selected bank", () => {
    const mapping: MidiMapping = {
      mode: "banked-8",
      notes: [36, 37, 38, 39, 40, 41, 42, 43],
    };

    expect(padIndexForNote(mapping, 36, "A")).toBe(0);
    expect(padIndexForNote(mapping, 36, "B")).toBe(8);
  });

  it("ignores notes that are not mapped", () => {
    expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 52, "A")).toBeNull();
  });
});

describe("MidiLearnSession", () => {
  it("completes direct learning only after sixteen unique valid notes", () => {
    const session = new MidiLearnSession("direct-16");

    expect(session.capture(-1)).toBeNull();
    expect(session.capture(128)).toBeNull();
    expect(session.capture(36)).toBeNull();
    expect(session.capture(36)).toBeNull();

    for (let note = 37; note < 51; note += 1) {
      expect(session.capture(note)).toBeNull();
    }

    const mapping = session.capture(51);
    expect(mapping).toEqual({
      mode: "direct-16",
      notes: Array.from({ length: 16 }, (_, index) => 36 + index),
    });
    expect(Object.isFrozen(mapping)).toBe(true);
    expect(Object.isFrozen(mapping?.notes)).toBe(true);
  });

  it("completes banked learning on the eighth unique note", () => {
    const session = new MidiLearnSession("banked-8");

    for (let note = 60; note < 67; note += 1) {
      expect(session.capture(note)).toBeNull();
    }

    expect(session.capture(67)).toEqual({
      mode: "banked-8",
      notes: [60, 61, 62, 63, 64, 65, 66, 67],
    });
  });
});

describe("MIDI mapping storage", () => {
  let storage: MemoryStorage;

  beforeEach(() => {
    storage = new MemoryStorage();
  });

  it("saves and loads a valid mapping", () => {
    const mapping: MidiMapping = {
      mode: "banked-8",
      notes: [60, 61, 62, 63, 64, 65, 66, 67],
    };

    saveMidiMapping(storage, mapping);

    expect(storage.getItem("lmdj.midi.mapping.v1")).toBe(
      JSON.stringify(mapping),
    );
    expect(loadMidiMapping(storage)).toEqual(mapping);
  });

  it.each([
    ["invalid JSON", "not-json"],
    ["unknown mode", JSON.stringify({ mode: "other", notes: [36] })],
    [
      "wrong note count",
      JSON.stringify({ mode: "direct-16", notes: [36, 37] }),
    ],
    [
      "out-of-range note",
      JSON.stringify({
        mode: "banked-8",
        notes: [36, 37, 38, 39, 40, 41, 42, 128],
      }),
    ],
    [
      "duplicate note",
      JSON.stringify({
        mode: "banked-8",
        notes: [36, 37, 38, 39, 40, 41, 42, 42],
      }),
    ],
  ])("falls back to the default for %s", (_case, serialized) => {
    storage.setItem("lmdj.midi.mapping.v1", serialized);

    expect(loadMidiMapping(storage)).toEqual(DEFAULT_DIRECT_MAPPING);
  });
});
