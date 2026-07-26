import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch, PatchBundle } from "../patch/loader";
import { padElementIds } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "./AudioEngine";

function makeBundle(patch: Patch = structuredClone(golden) as unknown as Patch): PatchBundle<unknown> {
  const buffers = new Map<string, unknown>();
  for (const el of patch.elements) buffers.set(el.element_id, { buf: el.element_id });
  return {
    patch,
    buffers,
    playableElementIds: new Set(patch.elements.map((e) => e.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
}

function materialPlaybackPatch(): Patch {
  const patch = structuredClone(golden) as unknown as Patch;
  const ordinary = patch.elements[0].element_id;
  const phrase = patch.elements[1].element_id;
  patch.pads[0] = {
    index: 0,
    slot: "Kick A",
    label: "Kick A",
    action: "trigger_element",
    element_id: ordinary,
    behavior: {
      trigger: "loop",
      quantize: "1/16",
      element_ids: [ordinary],
    },
  };
  patch.pads[7] = {
    index: 7,
    slot: "Phrase A",
    label: "Phrase A",
    action: "trigger_element",
    element_id: phrase,
    behavior: {
      trigger: "loop",
      quantize: "1/16",
      exclusive_group: "full_mix_exclusive",
      element_ids: [phrase],
    },
  };
  return patch;
}

describe("AudioEngine", () => {
  let ctx: FakeAudioContext;
  let engine: AudioEngine;

  beforeEach(() => {
    vi.useFakeTimers();
    ctx = new FakeAudioContext();
    engine = new AudioEngine(ctx);
  });
  afterEach(() => {
    engine.stop();
    vi.useRealTimers();
  });

  it("triggerPad plays the whole group simultaneously", () => {
    const bundle = makeBundle();
    engine.load(bundle);
    const drums = bundle.patch.pads[0]; // trigger_group
    const ids = padElementIds(drums);
    expect(ids.length).toBeGreaterThan(1);

    engine.triggerPad(0);
    expect(ctx.sources).toHaveLength(ids.length); // kick+snare+hat 同击
  });

  it("reserved and empty pads are no-ops", () => {
    const bundle = makeBundle();
    engine.load(bundle);
    for (const pad of bundle.patch.pads) {
      if (pad.action === "trigger_element" || pad.action === "trigger_group") continue;
      engine.triggerPad(pad.index);
      engine.toggleMutePad(pad.index);
    }
    expect(ctx.sources).toHaveLength(0);
    expect(bundle.patch.pads.every((p) => !engine.isPadMuted(p.index))).toBe(true);
  });

  it("enforces Phrase and ordinary playback exclusivity in both directions", () => {
    engine.load(makeBundle(materialPlaybackPatch()));

    engine.triggerPad(0);
    const ordinary = ctx.sources.at(-1)!;
    expect(ordinary.loop).toBe(true);
    expect(ordinary.stoppedAt).toHaveLength(0);

    engine.triggerPad(7);
    const phrase = ctx.sources.at(-1)!;
    expect(ordinary.stoppedAt).toEqual([0]);
    expect(phrase.loop).toBe(true);
    expect(phrase.stoppedAt).toHaveLength(0);

    engine.triggerPad(0);
    expect(phrase.stoppedAt).toEqual([0]);
  });

  it("retriggering a loop replaces the earlier source", () => {
    engine.load(makeBundle(materialPlaybackPatch()));
    engine.triggerPad(0);
    const first = ctx.sources.at(-1)!;
    engine.triggerPad(0);
    const second = ctx.sources.at(-1)!;

    expect(first.stoppedAt).toEqual([0]);
    expect(second.stoppedAt).toHaveLength(0);
  });

  it("stop terminates active material sources even without transport", () => {
    engine.load(makeBundle(materialPlaybackPatch()));
    engine.triggerPad(7);
    const phrase = ctx.sources.at(-1)!;

    engine.stop();

    expect(phrase.stoppedAt).toEqual([0]);
  });

  it("toggleMutePad zeroes the whole group's gains and restores them", () => {
    const bundle = makeBundle();
    engine.load(bundle);
    const ids = new Set(padElementIds(bundle.patch.pads[0]));

    engine.toggleMutePad(0);
    expect(engine.isPadMuted(0)).toBe(true);
    const groupGains = ctx.gains.filter((_, i) =>
      ids.has(bundle.patch.elements[i].element_id),
    );
    expect(groupGains.length).toBe(ids.size);
    expect(groupGains.every((g) => g.gain.value === 0)).toBe(true);

    engine.toggleMutePad(0);
    expect(engine.isPadMuted(0)).toBe(false);
    expect(groupGains.every((g) => g.gain.value === 1)).toBe(true);
  });

  it("schedules only the active scene's patterns (decoy pattern is never played)", async () => {
    const patch = structuredClone(golden) as unknown as Patch;
    const real = structuredClone(patch.patterns[0]);
    const decoy = structuredClone(patch.patterns[0]);
    decoy.pattern_id = "pattern_decoy";
    decoy.notes = decoy.notes.map((n) => ({ ...n, element_id: "el_ghost" }));
    patch.patterns = [decoy, real];
    patch.scenes[0].pattern_ids = [real.pattern_id];

    const bundle = makeBundle(patch);
    bundle.buffers.set("el_ghost", { buf: "ghost" });
    engine.load(bundle);
    await engine.play();

    // 首个 tick 已排 [0, 0.12) 窗口——step0 的 note 应来自 real pattern
    const scheduledBuffers = ctx.sources.map((s) => (s.buffer as { buf: string }).buf);
    expect(scheduledBuffers.length).toBeGreaterThan(0);
    expect(scheduledBuffers).not.toContain("ghost");
  });

  it("skips notes whose element has no buffer (missing asset)", async () => {
    const bundle = makeBundle();
    const step0Elements = new Set(
      bundle.patch.patterns[0].notes.filter((n) => n.step === 0).map((n) => n.element_id),
    );
    expect(step0Elements.size).toBeGreaterThan(0);
    for (const id of step0Elements) bundle.buffers.delete(id); // 模拟缺失

    engine.load(bundle);
    await engine.play();
    const played = ctx.sources.map((s) => (s.buffer as { buf: string }).buf);
    for (const id of step0Elements) expect(played).not.toContain(id);
  });

  it("playhead is null when stopped and a step index while playing", async () => {
    const bundle = makeBundle();
    engine.load(bundle);
    expect(engine.playhead()).toBeNull();

    await engine.play();
    ctx.currentTime = 0.01;
    expect(engine.playhead()).toBe(0);
    engine.stop();
    expect(engine.playhead()).toBeNull();
  });

  it("catches up notes within the bound after a delayed tick", async () => {
    const bundle = makeBundle();
    engine.load(bundle);
    await engine.play(); // 首个 tick 已排 [0, 0.12)
    const afterFirstTick = ctx.sources.length;

    ctx.currentTime = 0.3; // 停顿 0.3s：错过 [0.12, 0.3)，其中 [0.05, 0.3) 在 0.25s 界内
    vi.advanceTimersByTime(25);

    const newSources = ctx.sources.slice(afterFirstTick);
    expect(newSources.length).toBeGreaterThan(0);
    // 界内错过的 note 被补排：存在 startedAt 早于当前时刻的（钳到 now 前的过去时间）
    expect(newSources.some((s) => s.startedAt[0] < 0.3)).toBe(true);
  });

  it("drops pathological backlog beyond the catch-up bound", async () => {
    const bundle = makeBundle();
    engine.load(bundle);
    await engine.play();
    const afterFirstTick = ctx.sources.length;

    ctx.currentTime = 60; // 模拟后台节流 1 分钟
    vi.advanceTimersByTime(25);

    const newSources = ctx.sources.slice(afterFirstTick);
    // 只补 [60-0.25, 60.12) 窗口，不是 6 圈 × 45 note 的爆发
    expect(newSources.length).toBeLessThan(20);
  });

  it("reports real active sources and notifies when the final source ends", () => {
    engine.load(makeBundle(materialPlaybackPatch()));
    const events: boolean[] = [];
    const unsubscribe = engine.subscribe(() => events.push(engine.active));

    engine.triggerPad(0);
    expect(engine.active).toBe(true);
    expect(engine.activeElementIds().size).toBe(1);

    ctx.sources.at(-1)!.onended?.({ type: "ended" });
    expect(engine.active).toBe(false);
    expect(engine.activeElementIds()).toEqual(new Set());
    expect(events).toEqual([true, false]);
    unsubscribe();
  });

  it("notifies subscribers on play/stop/mute", async () => {
    const bundle = makeBundle();
    engine.load(bundle);
    const events: number[] = [];
    const unsubscribe = engine.subscribe(() => events.push(1));

    await engine.play();
    engine.toggleMutePad(0);
    engine.stop();
    expect(events.length).toBeGreaterThanOrEqual(3);
    const countBeforeUnsubscribe = events.length;
    unsubscribe();
    engine.toggleMutePad(0);
    expect(events).toHaveLength(countBeforeUnsubscribe);
  });
});
