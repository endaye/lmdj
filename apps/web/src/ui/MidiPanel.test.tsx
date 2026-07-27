import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MidiBank } from "../midi/mapping";
import { MidiPanel } from "./MidiPanel";

class FakeMidiInput {
  readonly id = "controller";
  readonly name = "Stage Controller";
  readonly type = "input";
  readonly state = "connected";
  onmidimessage: ((event: MIDIMessageEvent) => void) | null = null;

  emit(note: number, velocity = 100): void {
    this.onmidimessage?.({
      data: new Uint8Array([0x90, note, velocity]),
    } as MIDIMessageEvent);
  }
}

class FakeMidiAccess {
  readonly inputs: Map<string, MIDIInput>;
  onstatechange: ((event: MIDIConnectionEvent) => void) | null = null;

  constructor(input: FakeMidiInput) {
    this.inputs = new Map([
      [input.id, input as unknown as MIDIInput],
    ]);
  }
}

const originalRequestMidiAccess = Object.getOwnPropertyDescriptor(
  Navigator.prototype,
  "requestMIDIAccess",
);

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

function installWebMidi() {
  const input = new FakeMidiInput();
  const access = new FakeMidiAccess(input);
  const request = vi.fn(async () => access as unknown as MIDIAccess);
  Object.defineProperty(Navigator.prototype, "requestMIDIAccess", {
    configurable: true,
    value: request,
  });
  return { input, request };
}

function BankHarness({
  onTrigger,
  onStatusChange,
}: {
  onTrigger: (index: number) => void;
  onStatusChange?: Parameters<typeof MidiPanel>[0]["onStatusChange"];
}) {
  const [bank, setBank] = useState<MidiBank>("A");
  return (
    <MidiPanel
      onTrigger={onTrigger}
      bank={bank}
      onBankChange={setBank}
      onStatusChange={onStatusChange}
    />
  );
}

beforeEach(() => {
  vi.stubGlobal("localStorage", new MemoryStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
  if (originalRequestMidiAccess) {
    Object.defineProperty(
      Navigator.prototype,
      "requestMIDIAccess",
      originalRequestMidiAccess,
    );
  } else {
    delete (Navigator.prototype as Partial<Navigator>).requestMIDIAccess;
  }
});

describe("MidiPanel", () => {
  it("connects only after the user clicks Connect and shows every device", async () => {
    const { request } = installWebMidi();
    const onStatusChange = vi.fn();
    render(
      <BankHarness
        onTrigger={() => undefined}
        onStatusChange={onStatusChange}
      />,
    );

    expect(request).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /Connect MIDI/i }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("midi-connection")).toHaveTextContent("Connected");
    expect(screen.getByTestId("midi-devices")).toHaveTextContent("Stage Controller");
    expect(onStatusChange).toHaveBeenLastCalledWith({
      connection: "Connected",
      devices: ["Stage Controller"],
    });
  });

  it("learns and saves a complete direct sixteen-note mapping", async () => {
    const { input } = installWebMidi();
    render(<BankHarness onTrigger={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: /Connect MIDI/i }));
    await userEvent.click(screen.getByRole("button", { name: /Learn Direct 16/i }));

    for (let note = 52; note < 68; note += 1) input.emit(note);

    await waitFor(() =>
      expect(screen.getByTestId("midi-mapping-mode")).toHaveTextContent("Direct 16"),
    );
    expect(JSON.parse(localStorage.getItem("lmdj.midi.mapping.v1") ?? "")).toEqual({
      mode: "direct-16",
      notes: Array.from({ length: 16 }, (_, index) => 52 + index),
    });
  });

  it("keeps the previous mapping when a new Learn session is incomplete", async () => {
    const previous = {
      mode: "banked-8",
      notes: [36, 37, 38, 39, 40, 41, 42, 43],
    };
    localStorage.setItem("lmdj.midi.mapping.v1", JSON.stringify(previous));
    const { input } = installWebMidi();
    render(<BankHarness onTrigger={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: /Connect MIDI/i }));
    await userEvent.click(screen.getByRole("button", { name: /Learn Direct 16/i }));

    input.emit(60);
    input.emit(61);

    await waitFor(() =>
      expect(screen.getByTestId("midi-learn-progress")).toHaveTextContent("2 / 16"),
    );
    expect(screen.getByTestId("midi-mapping-mode")).toHaveTextContent("8-pad");
    expect(JSON.parse(localStorage.getItem("lmdj.midi.mapping.v1") ?? "")).toEqual(previous);
  });

  it("learns eight notes and maps the same controller across Bank A and B", async () => {
    const { input } = installWebMidi();
    const onTrigger = vi.fn();
    render(<BankHarness onTrigger={onTrigger} />);
    await userEvent.click(screen.getByRole("button", { name: /Connect MIDI/i }));
    await userEvent.click(screen.getByRole("button", { name: /Learn 8-pad/i }));
    for (let note = 60; note < 68; note += 1) input.emit(note);

    input.emit(60);
    expect(onTrigger).toHaveBeenLastCalledWith(0);
    await userEvent.click(
      await screen.findByRole("button", { name: /Bank B/i }),
    );
    input.emit(60);

    expect(onTrigger).toHaveBeenLastCalledWith(8);
    expect(screen.getByRole("button", { name: /Bank B/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("marks Bank as not applicable for Direct 16 and maps independently of the bank prop", async () => {
    const { input } = installWebMidi();
    const onTrigger = vi.fn();
    const onBankChange = vi.fn();
    render(
      <MidiPanel
        onTrigger={onTrigger}
        bank="B"
        onBankChange={onBankChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Connect MIDI/i }));

    expect(screen.getByTestId("midi-bank-status")).toHaveTextContent("不适用");
    expect(screen.queryByRole("button", { name: /Bank A/i })).not.toBeInTheDocument();
    input.emit(51);

    expect(onTrigger).toHaveBeenCalledWith(15);
    expect(onBankChange).not.toHaveBeenCalled();
  });
});
