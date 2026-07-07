import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch, PatchBundle } from "../patch/loader";
import { padElementIds } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "./AudioEngine";

function makeBundle(patch: Patch = structuredClone(golden) as Patch): PatchBundle<unknown> {
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
    const patch = structuredClone(golden) as Patch;
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

  it("notifies subscribers on play/stop/mute", async () => {
    const bundle = makeBundle();
    engine.load(bundle);
    const events: number[] = [];
    const unsubscribe = engine.subscribe(() => events.push(1));

    await engine.play();
    engine.toggleMutePad(0);
    engine.stop();
    unsubscribe();
    engine.toggleMutePad(0);
    expect(events.length).toBe(3);
  });
});
