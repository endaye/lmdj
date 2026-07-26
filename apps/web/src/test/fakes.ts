export class FakeGain {
  gain = { value: 1 };
  connected: unknown[] = [];
  disconnected = false;
  connect(dst: unknown): void {
    this.connected.push(dst);
  }
  disconnect(): void {
    this.disconnected = true;
  }
}

export class FakeSource {
  buffer: unknown = null;
  loop = false;
  onended: ((event: unknown) => void) | null = null;
  connectedTo: unknown = null;
  startedAt: number[] = [];
  stoppedAt: number[] = [];
  connect(dst: unknown): void {
    this.connectedTo = dst;
  }
  start(when = 0): void {
    this.startedAt.push(when);
  }
  stop(when = 0): void {
    this.stoppedAt.push(when);
    this.onended?.({ type: "ended" });
  }
}

export class FakeAudioContext {
  currentTime = 0;
  destination = { fake: "destination" };
  gains: FakeGain[] = [];
  sources: FakeSource[] = [];
  resumed = 0;

  createGain(): FakeGain {
    const gain = new FakeGain();
    this.gains.push(gain);
    return gain;
  }
  createBufferSource(): FakeSource {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }
  async resume(): Promise<void> {
    this.resumed += 1;
  }
}
