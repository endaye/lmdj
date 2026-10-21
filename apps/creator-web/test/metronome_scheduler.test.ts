import {expect, test} from "vitest";

import {beatsInWindow} from "../src/runtime/metronome_scheduler";

test("beats land on the exact engine ceiling formula at 120 BPM", () => {
  // 2 880 000 / 120 = 24 000 exactly: a beat every 24 000 frames.
  expect(beatsInWindow({fromFrame: 0, toFrame: 96_000, originFrame: 0, bpm: 120}))
    .toEqual([
      {frame: 0, beat: 0, accent: true},
      {frame: 24_000, beat: 1, accent: false},
      {frame: 48_000, beat: 2, accent: false},
      {frame: 72_000, beat: 3, accent: false},
    ]);
});

test("beats land on the exact engine ceiling formula at 121 BPM", () => {
  // ceil(k × 2 880 000 / 121): the same values tick_boundary_frame computes.
  expect(beatsInWindow({fromFrame: 0, toFrame: 120_000, originFrame: 0, bpm: 121}))
    .toEqual([
      {frame: 0, beat: 0, accent: true},
      {frame: 23_802, beat: 1, accent: false},
      {frame: 47_604, beat: 2, accent: false},
      {frame: 71_405, beat: 3, accent: false},
      {frame: 95_207, beat: 4, accent: true},
      {frame: 119_009, beat: 5, accent: false},
    ]);
});

test("every fourth beat is accented", () => {
  const beats = beatsInWindow(
    {fromFrame: 0, toFrame: 24_000 * 9, originFrame: 0, bpm: 120});
  expect(beats.map(({accent}) => accent)).toEqual([
    true, false, false, false, true, false, false, false, true,
  ]);
});

test("the origin frame offsets the whole grid", () => {
  expect(beatsInWindow(
    {fromFrame: 0, toFrame: 50_000, originFrame: 1_000, bpm: 120}))
    .toEqual([
      {frame: 1_000, beat: 0, accent: true},
      {frame: 25_000, beat: 1, accent: false},
      {frame: 49_000, beat: 2, accent: false},
    ]);
});

test("the window is half-open and starts at the first contained beat", () => {
  expect(beatsInWindow(
    {fromFrame: 24_000, toFrame: 48_000, originFrame: 0, bpm: 120}))
    .toEqual([{frame: 24_000, beat: 1, accent: false}]);
  expect(beatsInWindow(
    {fromFrame: 12_000, toFrame: 24_000, originFrame: 0, bpm: 120}))
    .toEqual([]);
  expect(beatsInWindow(
    {fromFrame: 48_000, toFrame: 48_000, originFrame: 0, bpm: 120}))
    .toEqual([]);
  expect(beatsInWindow(
    {fromFrame: 48_000, toFrame: 24_000, originFrame: 0, bpm: 120}))
    .toEqual([]);
});

test("a grid change at the activation frame switches grids with no double and no gap", () => {
  // A bpm commit while playing: the old 120 BPM grid owns beats before the
  // activation frame 96 000 (a bar boundary of the old grid); the new 121 BPM
  // grid restarts there, so beat 0 of the new grid sits exactly on it.
  const beats = beatsInWindow({
    fromFrame: 48_000,
    toFrame: 150_000,
    segments: [
      {fromFrame: 0, originFrame: 0, bpm: 120},
      {fromFrame: 96_000, originFrame: 96_000, bpm: 121},
    ],
  });
  expect(beats).toEqual([
    {frame: 48_000, beat: 2, accent: false},
    {frame: 72_000, beat: 3, accent: false},
    {frame: 96_000, beat: 0, accent: true},
    {frame: 119_802, beat: 1, accent: false},
    {frame: 143_604, beat: 2, accent: false},
  ]);
  // Exactly one beat owns the boundary frame.
  expect(beats.filter(({frame}) => frame === 96_000)).toHaveLength(1);
});

test("a segment emits nothing before its own activation frame", () => {
  // The new grid's beat 1 lands after its activation; nothing of the new
  // grid may appear earlier even though the formula would place beats there
  // if the origin were earlier.
  const beats = beatsInWindow({
    fromFrame: 0,
    toFrame: 130_000,
    segments: [
      {fromFrame: 0, originFrame: 0, bpm: 120},
      {fromFrame: 96_000, originFrame: 96_000, bpm: 121},
    ],
  });
  expect(beats.filter(({frame}) => frame < 96_000).map(({frame}) => frame))
    .toEqual([0, 24_000, 48_000, 72_000]);
});
