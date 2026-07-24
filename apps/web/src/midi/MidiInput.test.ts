import { describe, expect, it, vi } from "vitest";
import { DEFAULT_DIRECT_MAPPING, padIndexForNote } from "./mapping";
import { MidiInput, type MidiSnapshot } from "./MidiInput";

class FakeMidiInput {
  readonly id: string;
  readonly name: string;
  readonly type = "input";
  state: MIDIPortDeviceState = "connected";
  onmidimessage: ((event: MIDIMessageEvent) => void) | null = null;

  constructor(id: string, name: string) {
    this.id = id;
    this.name = name;
  }

  emit(data: number[]): void {
    this.onmidimessage?.({ data: new Uint8Array(data) } as MIDIMessageEvent);
  }
}

class FakeMidiAccess {
  readonly inputs = new Map<string, MIDIInput>();
  onstatechange: ((event: MIDIConnectionEvent) => void) | null = null;

  add(input: FakeMidiInput): void {
    this.inputs.set(input.id, input as unknown as MIDIInput);
    this.onstatechange?.({ port: input } as unknown as MIDIConnectionEvent);
  }

  change(input: FakeMidiInput): void {
    this.onstatechange?.({ port: input } as unknown as MIDIConnectionEvent);
  }
}

describe("MidiInput", () => {
  it("shares one in-flight permission request across concurrent connect calls", async () => {
    const input = new FakeMidiInput("one", "Controller One");
    const access = new FakeMidiAccess();
    access.add(input);
    let resolveAccess!: (access: MIDIAccess) => void;
    const pendingAccess = new Promise<MIDIAccess>((resolve) => {
      resolveAccess = resolve;
    });
    const requestAccess = vi.fn(() => pendingAccess);
    const midi = new MidiInput(() => undefined, requestAccess);

    const first = midi.connect();
    const second = midi.connect();
    const third = midi.connect();

    expect(requestAccess).toHaveBeenCalledTimes(1);
    expect(midi.snapshot.connection).toBe("requesting");

    resolveAccess(access as unknown as MIDIAccess);
    await Promise.all([first, second, third]);

    expect(midi.snapshot).toEqual({
      support: "available",
      connection: "connected",
      devices: ["Controller One"],
    });
    midi.dispose();
    expect(input.onmidimessage).toBeNull();
    expect(access.onstatechange).toBeNull();
  });

  it("accepts Note On with positive velocity and ignores note-off forms", async () => {
    const input = new FakeMidiInput("one", "Controller One");
    const access = new FakeMidiAccess();
    access.add(input);
    const triggered: number[] = [];
    const midi = new MidiInput(
      (note) => {
        const index = padIndexForNote(DEFAULT_DIRECT_MAPPING, note, "A");
        if (index !== null) triggered.push(index);
      },
      async () => access as unknown as MIDIAccess,
    );

    await midi.connect();
    input.emit([0x90, 36, 100]);
    input.emit([0x90, 36, 0]);
    input.emit([0x80, 36, 100]);

    expect(triggered).toEqual([0]);
  });

  it("listens to every connected input and binds devices added later", async () => {
    const first = new FakeMidiInput("one", "Controller One");
    const second = new FakeMidiInput("two", "Controller Two");
    const access = new FakeMidiAccess();
    access.add(first);
    const triggered: number[] = [];
    const midi = new MidiInput(
      (note) => triggered.push(note),
      async () => access as unknown as MIDIAccess,
    );

    await midi.connect();
    access.add(second);
    first.emit([0x90, 40, 100]);
    second.emit([0x90, 41, 100]);

    expect(triggered).toEqual([40, 41]);
    expect(midi.snapshot).toEqual({
      support: "available",
      connection: "connected",
      devices: ["Controller One", "Controller Two"],
    });
  });

  it("reports disconnected and stops listening when all inputs disconnect", async () => {
    const input = new FakeMidiInput("one", "Controller One");
    const access = new FakeMidiAccess();
    access.add(input);
    const triggered: number[] = [];
    const snapshots: MidiSnapshot[] = [];
    const midi = new MidiInput(
      (note) => triggered.push(note),
      async () => access as unknown as MIDIAccess,
    );
    midi.subscribe((snapshot) => snapshots.push(snapshot));

    await midi.connect();
    input.state = "disconnected";
    access.change(input);
    input.emit([0x90, 36, 100]);

    expect(triggered).toEqual([]);
    expect(midi.snapshot).toEqual({
      support: "available",
      connection: "disconnected",
      devices: [],
    });
    expect(snapshots.at(-1)).toEqual(midi.snapshot);
  });

  it("keeps denied stable and permits a later explicit retry", async () => {
    const input = new FakeMidiInput("one", "Controller One");
    const access = new FakeMidiAccess();
    access.add(input);
    const requestAccess = vi
      .fn<() => Promise<MIDIAccess>>()
      .mockRejectedValueOnce(
        new DOMException("Permission denied", "NotAllowedError"),
      )
      .mockResolvedValueOnce(access as unknown as MIDIAccess);
    const midi = new MidiInput(() => undefined, requestAccess);

    await midi.connect();

    expect(requestAccess).toHaveBeenCalledTimes(1);
    expect(midi.snapshot).toEqual({
      support: "available",
      connection: "denied",
      devices: [],
    });

    await midi.connect();

    expect(requestAccess).toHaveBeenCalledTimes(2);
    expect(midi.snapshot).toEqual({
      support: "available",
      connection: "connected",
      devices: ["Controller One"],
    });
  });

  it("reports unsupported without starting a permission request", async () => {
    const descriptor = Object.getOwnPropertyDescriptor(
      Navigator.prototype,
      "requestMIDIAccess",
    );
    Object.defineProperty(Navigator.prototype, "requestMIDIAccess", {
      configurable: true,
      value: undefined,
    });
    const midi = new MidiInput(() => undefined);

    await midi.connect();

    expect(midi.snapshot).toEqual({
      support: "unsupported",
      connection: "idle",
      devices: [],
    });

    if (descriptor) {
      Object.defineProperty(Navigator.prototype, "requestMIDIAccess", descriptor);
    } else {
      delete (Navigator.prototype as Partial<Navigator>).requestMIDIAccess;
    }
  });

  it("removes every message and state-change handler on dispose", async () => {
    const input = new FakeMidiInput("one", "Controller One");
    const later = new FakeMidiInput("two", "Controller Two");
    const access = new FakeMidiAccess();
    access.add(input);
    const triggered: number[] = [];
    const midi = new MidiInput(
      (note) => triggered.push(note),
      async () => access as unknown as MIDIAccess,
    );

    await midi.connect();
    midi.dispose();
    input.emit([0x90, 36, 100]);
    access.add(later);
    later.emit([0x90, 37, 100]);

    expect(triggered).toEqual([]);
    expect(input.onmidimessage).toBeNull();
    expect(access.onstatechange).toBeNull();
  });
});
