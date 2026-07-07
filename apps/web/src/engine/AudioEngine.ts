import type { Pattern, PatchBundle } from "../patch/loader";
import { padElementIds, scenePatterns } from "../patch/loader";
import { notesInWindow, playheadStep, stepDuration } from "./clock";

export interface GainLike {
  gain: { value: number };
  connect(dst: unknown): void;
}
export interface SourceLike {
  buffer: unknown;
  connect(dst: unknown): void;
  start(when?: number): void;
}
export interface AudioLike {
  currentTime: number;
  destination: unknown;
  createGain(): GainLike;
  createBufferSource(): SourceLike;
  resume(): Promise<void>;
}

const TICK_MS = 25;
const LOOKAHEAD_SEC = 0.12;

export class AudioEngine {
  private readonly ctx: AudioLike;
  private bundle: PatchBundle<unknown> | null = null;
  private patterns: Pattern[] = [];
  private stepDur = 0;
  private gains = new Map<string, GainLike>();
  private mutedPads = new Set<number>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private startTime = 0;
  private scheduledUntil = 0;
  private listeners = new Set<() => void>();

  constructor(ctx: AudioLike) {
    this.ctx = ctx;
  }

  load(bundle: PatchBundle<unknown>): void {
    this.stop();
    this.bundle = bundle;
    // scene 契约：activeScene → pattern_ids → patterns（不得直读 patterns[0]）
    this.patterns = scenePatterns(bundle.patch);
    this.stepDur = stepDuration(bundle.patch.bpm);
    this.gains = new Map();
    for (const element of bundle.patch.elements) {
      const gain = this.ctx.createGain();
      gain.connect(this.ctx.destination);
      this.gains.set(element.element_id, gain);
    }
    this.mutedPads = new Set();
    this.emit();
  }

  get playing(): boolean {
    return this.timer !== null;
  }

  async play(): Promise<void> {
    if (!this.bundle || this.timer) return;
    await this.ctx.resume(); // 浏览器手势解锁
    this.startTime = this.ctx.currentTime;
    this.scheduledUntil = 0;
    this.tick();
    this.timer = setInterval(() => this.tick(), TICK_MS);
    this.emit();
  }

  stop(): void {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null; // 已发声的 one-shot 自然播完（v1 不做硬切）
    this.emit();
  }

  triggerPad(index: number): void {
    const pad = this.bundle?.patch.pads[index];
    if (!pad) return;
    const ids = padElementIds(pad); // reserved/empty → [] → no-op
    if (ids.length === 0) return;
    void this.ctx.resume();
    for (const id of ids) this.playElement(id);
  }

  toggleMutePad(index: number): void {
    const pad = this.bundle?.patch.pads[index];
    if (!pad) return;
    const ids = padElementIds(pad);
    if (ids.length === 0) return;
    const muted = this.mutedPads.has(index);
    for (const id of ids) {
      const gain = this.gains.get(id);
      if (gain) gain.gain.value = muted ? 1 : 0;
    }
    if (muted) this.mutedPads.delete(index);
    else this.mutedPads.add(index);
    this.emit();
  }

  isPadMuted(index: number): boolean {
    return this.mutedPads.has(index);
  }

  /** 播放中返回当前 step（取 scene 首 pattern 的 length_steps），停止时 null */
  playhead(): number | null {
    if (!this.timer || this.patterns.length === 0) return null;
    const elapsed = this.ctx.currentTime - this.startTime;
    return playheadStep(elapsed, this.patterns[0].length_steps, this.stepDur);
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private tick(): void {
    const now = this.ctx.currentTime - this.startTime;
    // catch-up 策略（评审决策）：tick 延迟时补排 [scheduledUntil, now) 的 note，
    // 宁可稍晚发声也不静默丢拍；WebAudio 会把过去的 start 时间钳到当前。
    const from = this.scheduledUntil;
    const to = now + LOOKAHEAD_SEC;
    if (to <= from) return;
    for (const pattern of this.patterns) {
      for (const hit of notesInWindow(pattern.notes, pattern.length_steps, this.stepDur, from, to)) {
        this.playElement(hit.note.element_id, this.startTime + hit.time);
      }
    }
    this.scheduledUntil = to;
  }

  private playElement(elementId: string, when?: number): void {
    const buffer = this.bundle?.buffers.get(elementId);
    const gain = this.gains.get(elementId);
    if (!buffer || !gain) return; // 缺失素材：跳过发声，note 数据不动
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(gain);
    source.start(when ?? this.ctx.currentTime);
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }
}
