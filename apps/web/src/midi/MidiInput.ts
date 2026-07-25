export interface MidiSnapshot {
  support: "unknown" | "unsupported" | "available";
  connection:
    | "idle"
    | "requesting"
    | "connected"
    | "denied"
    | "disconnected";
  devices: string[];
}

type SnapshotListener = (snapshot: MidiSnapshot) => void;

const INITIAL_SNAPSHOT: MidiSnapshot = {
  support: "unknown",
  connection: "idle",
  devices: [],
};

export class MidiInput {
  private readonly requestAccess: () => Promise<MIDIAccess>;
  private readonly supported: boolean;
  private readonly listeners = new Set<SnapshotListener>();
  private readonly boundInputs = new Set<MIDIInput>();
  private access: MIDIAccess | null = null;
  private connecting: Promise<void> | null = null;
  private currentSnapshot: MidiSnapshot = INITIAL_SNAPSHOT;
  private disposed = false;

  constructor(
    private readonly onNote: (note: number) => void,
    requestAccess?: () => Promise<MIDIAccess>,
  ) {
    const nativeRequest =
      typeof navigator !== "undefined" &&
      typeof navigator.requestMIDIAccess === "function";
    this.supported = requestAccess !== undefined || nativeRequest;
    this.requestAccess =
      requestAccess ??
      (() => navigator.requestMIDIAccess({ sysex: false }));
  }

  get snapshot(): MidiSnapshot {
    return this.currentSnapshot;
  }

  subscribe(listener: SnapshotListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async connect(): Promise<void> {
    if (this.disposed || this.access) return;
    if (this.connecting) return this.connecting;
    if (!this.supported) {
      this.update({
        support: "unsupported",
        connection: "idle",
        devices: [],
      });
      return;
    }

    const attempt = this.requestConnection();
    this.connecting = attempt;
    try {
      await attempt;
    } finally {
      if (this.connecting === attempt) this.connecting = null;
    }
  }

  private async requestConnection(): Promise<void> {
    this.update({
      support: "available",
      connection: "requesting",
      devices: [],
    });
    try {
      const access = await this.requestAccess();
      if (this.disposed) return;
      this.access = access;
      access.onstatechange = () => this.refreshInputs();
      this.refreshInputs();
    } catch {
      if (this.disposed) return;
      this.update({
        support: "available",
        connection: "denied",
        devices: [],
      });
    }
  }

  dispose(): void {
    this.disposed = true;
    for (const input of this.boundInputs) input.onmidimessage = null;
    this.boundInputs.clear();
    if (this.access) this.access.onstatechange = null;
    this.access = null;
    this.listeners.clear();
  }

  private refreshInputs(): void {
    if (!this.access || this.disposed) return;

    for (const input of this.boundInputs) input.onmidimessage = null;
    this.boundInputs.clear();

    const devices: string[] = [];
    for (const input of this.access.inputs.values()) {
      if (input.state !== "connected") continue;
      input.onmidimessage = (event) => this.handleMessage(event);
      this.boundInputs.add(input);
      devices.push(input.name || input.id);
    }

    this.update({
      support: "available",
      connection: devices.length > 0 ? "connected" : "disconnected",
      devices,
    });
  }

  private handleMessage(event: MIDIMessageEvent): void {
    const data = event.data!;
    const command = data[0] & 0xf0;
    const note = data[1];
    const velocity = data[2];
    if (command === 0x90 && velocity > 0) this.onNote(note);
  }

  private update(snapshot: MidiSnapshot): void {
    this.currentSnapshot = {
      ...snapshot,
      devices: [...snapshot.devices],
    };
    for (const listener of this.listeners) listener(this.currentSnapshot);
  }
}
