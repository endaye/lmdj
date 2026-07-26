import type { Pattern, PatchBundle } from "../patch/loader";
import { padElementIds, scenePatterns } from "../patch/loader";
import { notesInWindow, playheadStep, stepDuration } from "./clock";

export interface GainLike {
  gain: { value: number };
  connect(dst: unknown): void;
  disconnect?(): void;
}
export interface SourceLike {
  buffer: unknown;
  loop: boolean;
  connect(dst: unknown): void;
  start(when?: number): void;
  stop(when?: number): void;
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
const MAX_CATCHUP_SEC = 0.25;
const PHRASE_EXCLUSIVE_GROUP = "full_mix_exclusive";

interface PlaybackBehavior {
  trigger: "one_shot" | "loop";
  exclusiveGroup: string | null;
}

interface ActiveSource {
  source: SourceLike;
  elementId: string;
  behavior: PlaybackBehavior;
}

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
  private behaviorByElement = new Map<string, PlaybackBehavior>();
  private activeSources = new Set<ActiveSource>();

  constructor(ctx: AudioLike) {
    this.ctx = ctx;
  }

  load(bundle: PatchBundle<unknown>): void {
    this.stop();
    for (const gain of this.gains.values()) gain.disconnect?.();
    this.bundle = bundle;
    // scene 契约：activeScene → pattern_ids → patterns（不得直读 patterns[0]）
    this.patterns = scenePatterns(bundle.patch);
    this.stepDur = stepDuration(bundle.patch.bpm);
    this.gains = new Map();
    this.behaviorByElement = new Map();
    for (const element of bundle.patch.elements) {
      const gain = this.ctx.createGain();
      gain.connect(this.ctx.destination);
      this.gains.set(element.element_id, gain);
    }
    for (const pad of bundle.patch.pads) {
      const raw = pad.behavior as {
        trigger?: unknown;
        exclusive_group?: unknown;
      };
      const behavior: PlaybackBehavior = {
        trigger: raw.trigger === "loop" ? "loop" : "one_shot",
        exclusiveGroup:
          typeof raw.exclusive_group === "string"
            ? raw.exclusive_group
            : null,
      };
      for (const elementId of padElementIds(pad)) {
        this.behaviorByElement.set(elementId, behavior);
      }
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
    const changed = this.timer !== null || this.activeSources.size > 0;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.stopSources(() => true);
    if (changed) this.emit();
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
    // 有界 catch-up（终审决策）：正常 tick 抖动内补排错过的 note（不丢拍）；
    // 超过 MAX_CATCHUP_SEC 的病态积压（后台节流/系统休眠）直接丢弃，
    // 避免唤醒瞬间数百个 note 同时钳到当前时间爆发。
    const from = Math.max(this.scheduledUntil, now - MAX_CATCHUP_SEC);
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
    const behavior = this.behaviorByElement.get(elementId) ?? {
      trigger: "one_shot",
      exclusiveGroup: null,
    };
    if (behavior.exclusiveGroup === PHRASE_EXCLUSIVE_GROUP) {
      this.stopSources(
        (active) => active.behavior.exclusiveGroup !== PHRASE_EXCLUSIVE_GROUP,
      );
    } else {
      this.stopSources(
        (active) => active.behavior.exclusiveGroup === PHRASE_EXCLUSIVE_GROUP,
      );
    }
    if (behavior.trigger === "loop") {
      this.stopSources((active) => active.elementId === elementId);
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = behavior.trigger === "loop";
    source.connect(gain);
    const active: ActiveSource = { source, elementId, behavior };
    const endedSource = source as SourceLike & {
      onended: ((event: Event) => unknown) | null;
    };
    endedSource.onended = () => this.activeSources.delete(active);
    this.activeSources.add(active);
    source.start(when ?? this.ctx.currentTime);
  }

  private stopSources(predicate: (active: ActiveSource) => boolean): void {
    for (const active of [...this.activeSources]) {
      if (!predicate(active)) continue;
      this.activeSources.delete(active);
      (
        active.source as SourceLike & {
          onended: ((event: Event) => unknown) | null;
        }
      ).onended = null;
      try {
        active.source.stop();
      } catch {
        // Browser may throw when a source has already ended; bookkeeping wins.
      }
    }
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }
}
