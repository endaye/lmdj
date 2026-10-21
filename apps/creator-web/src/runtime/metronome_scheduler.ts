// The metronome beat grid, in engine frames. Beat k (k = 0, 1, 2, …) of a
// grid sits at tick 960k (PPQ 960, one quarter note per beat), and the frame
// of a beat is the engine's own ceiling formula — tick_boundary_frame in
// prepared_sample_bank.cpp: ceil(tick × 2 880 000 / (bpm × 960)), where
// 2 880 000 = 48 000 fps × 60 s. The shared 960 factor cancels exactly, so
// the integer math below stays inside f64 precision for any session length
// while producing the identical frame the engine computes. A bar is 3 840
// ticks (4 beats); every 4th beat is accented.
//
// A grid change (a bpm commit while playing) activates at the returned
// activation_frame: the old grid owns beats before it, the new grid owns
// beats from it. The new publication restarts the Pattern at the activation
// frame, so the new grid's originFrame is that frame. Beats are selected per
// frame — the last segment whose fromFrame is at or before the frame owns it
// — so a boundary frame carries exactly one beat: no double, no gap.
//
// The module is pure: it never reads a clock. The click layer converts the
// returned frames to AudioContext seconds through the audio clock anchor.

export interface MetronomeBeat {
  readonly frame: number;
  readonly beat: number;
  readonly accent: boolean;
}

export interface MetronomeGridSegment {
  readonly fromFrame: number;
  readonly originFrame: number;
  readonly bpm: number;
}

export type MetronomeWindow = Readonly<{
  fromFrame: number;
  toFrame: number;
}> & Readonly<
  | {originFrame: number; bpm: number}
  | {segments: readonly MetronomeGridSegment[]}
>;

const BEATS_PER_BAR = 4;
// 48 000 fps × 60 s; the engine's kTickDenominator.
const TICK_DENOMINATOR = 2_880_000;

// ceil(beat × TICK_DENOMINATOR / bpm), the engine's tick_boundary_frame for
// tick = beat × 960 with the shared 960 factor cancelled.
function beatBoundaryFrame(beat: number, bpm: number): number {
  const numerator = beat * TICK_DENOMINATOR;
  return Math.floor(numerator / bpm) + (numerator % bpm === 0 ? 0 : 1);
}

// The first beat index whose frame is at or after `fromFrame`, estimated from
// the real-valued position and corrected against the exact formula.
function firstBeatAtOrAfter(
  fromFrame: number,
  originFrame: number,
  bpm: number,
): number {
  const realBeat = ((fromFrame - originFrame) * bpm) / TICK_DENOMINATOR;
  let beat = Math.max(0, Math.floor(realBeat) - 1);
  while (originFrame + beatBoundaryFrame(beat, bpm) < fromFrame) beat += 1;
  return beat;
}

function segmentBeats(
  segment: MetronomeGridSegment,
  fromFrame: number,
  toFrame: number,
  beats: MetronomeBeat[],
): void {
  const start = Math.max(fromFrame, segment.fromFrame);
  if (start >= toFrame) return;
  for (
    let beat = firstBeatAtOrAfter(start, segment.originFrame, segment.bpm);
    ;
    beat += 1
  ) {
    const frame = segment.originFrame + beatBoundaryFrame(beat, segment.bpm);
    if (frame < start) continue;
    if (frame >= toFrame) return;
    beats.push({frame, beat, accent: beat % BEATS_PER_BAR === 0});
  }
}

// Beats with fromFrame <= frame < toFrame, frame-first. A single grid passes
// {originFrame, bpm}; a grid change passes ordered {segments}.
export function beatsInWindow(window: MetronomeWindow): MetronomeBeat[] {
  const beats: MetronomeBeat[] = [];
  if (window.toFrame <= window.fromFrame) return beats;
  if ("segments" in window) {
    const segments = window.segments;
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index]!;
      const next = segments[index + 1];
      const until = next !== undefined
        ? Math.min(window.toFrame, next.fromFrame)
        : window.toFrame;
      segmentBeats(segment, window.fromFrame, until, beats);
    }
    return beats;
  }
  segmentBeats(
    {fromFrame: 0, originFrame: window.originFrame, bpm: window.bpm},
    window.fromFrame,
    window.toFrame,
    beats,
  );
  return beats;
}
