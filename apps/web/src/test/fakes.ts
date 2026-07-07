export class FakeGain {
  gain = { value: 1 };
  connected: unknown[] = [];
  connect(dst: unknown): void {
    this.connected.push(dst);
  }
}

export class FakeSource {
  buffer: unknown = null;
  connectedTo: unknown = null;
  startedAt: number[] = [];
  connect(dst: unknown): void {
    this.connectedTo = dst;
  }
  start(when = 0): void {
    this.startedAt.push(when);
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
