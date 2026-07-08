import { describe, expect, it } from "vitest";
import type { Note } from "../patch/loader";
import { notesInWindow, playheadStep, stepDuration } from "./clock";

const note = (step: number, element_id = "el_kick"): Note => ({
  element_id,
  lane: 0,
  pitch: 36,
  step,
  velocity: 100,
});

describe("stepDuration", () => {
  it("is a 16th note at the given bpm", () => {
    expect(stepDuration(120)).toBeCloseTo(0.125);
    expect(stepDuration(89.1)).toBeCloseTo(60 / 89.1 / 4);
  });
});

describe("notesInWindow", () => {
  const stepDur = 0.125; // bpm 120
  const lengthSteps = 16; // loop = 2s

  it("returns notes whose time falls in [from, to)", () => {
    const notes = [note(0), note(4), note(8)];
    const hits = notesInWindow(notes, lengthSteps, stepDur, 0.4, 1.1);
    expect(hits.map((h) => [h.note.step, h.time])).toEqual([[4, 0.5], [8, 1.0]]);
  });

  it("is half-open: a note exactly at `to` is excluded, at `from` included", () => {
    const notes = [note(4)];
    expect(notesInWindow(notes, lengthSteps, stepDur, 0.5, 0.6)).toHaveLength(1);
    expect(notesInWindow(notes, lengthSteps, stepDur, 0.4, 0.5)).toHaveLength(0);
  });

  it("wraps across the loop boundary", () => {
    const notes = [note(0), note(15)];
    // loop 长 2s；窗口 [1.9, 2.1) 不含 step15@1.875，应含下一圈 step0@2.0
    const hits = notesInWindow(notes, lengthSteps, stepDur, 1.9, 2.1);
    expect(hits.map((h) => [h.note.step, h.time])).toEqual([[0, 2.0]]);
  });

  it("covers multiple loops in one window", () => {
    const notes = [note(0)];
    const hits = notesInWindow(notes, 4, stepDur, 0, 1.6); // loop=0.5s → step0 @ 0,0.5,1.0,1.5
    expect(hits.map((h) => h.time)).toEqual([0, 0.5, 1.0, 1.5]);
  });
});

describe("playheadStep", () => {
  it("advances and wraps", () => {
    expect(playheadStep(0, 16, 0.125)).toBe(0);
    expect(playheadStep(0.13, 16, 0.125)).toBe(1);
    expect(playheadStep(2.0, 16, 0.125)).toBe(0); // 整圈回卷
    expect(playheadStep(1.999, 16, 0.125)).toBe(15);
  });
});
