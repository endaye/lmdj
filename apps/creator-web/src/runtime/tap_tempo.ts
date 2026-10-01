// Tap Tempo: a chain of taps converts to a BPM by the median of the last up
// to 4 intervals, rounded and clamped to the 40..240 BPM range the Sequence
// settings accept. A gap longer than 2 seconds starts a new chain, and the
// first tap of a chain commits nothing.
export const TAP_TEMPO_MIN_BPM = 40;
export const TAP_TEMPO_MAX_BPM = 240;
export const TAP_TEMPO_GAP_MS = 2_000;
const TAP_TEMPO_MAX_INTERVALS = 4;

export interface TapTempo {
  tap(): number | null;
}

export function createTapTempo(now: () => number): TapTempo {
  let taps: number[] = [];
  return {
    tap() {
      const at = now();
      if (taps.length > 0 && at - taps[taps.length - 1]! > TAP_TEMPO_GAP_MS) {
        taps = [];
      }
      taps.push(at);
      if (taps.length > TAP_TEMPO_MAX_INTERVALS + 1) taps.shift();
      if (taps.length < 2) return null;
      const intervals: number[] = [];
      for (let index = 1; index < taps.length; index += 1) {
        intervals.push(taps[index]! - taps[index - 1]!);
      }
      intervals.sort((left, right) => left - right);
      const middle = intervals.length >> 1;
      const median = intervals.length % 2 === 1
        ? intervals[middle]!
        : (intervals[middle - 1]! + intervals[middle]!) / 2;
      const bpm = Math.round(60_000 / median);
      return Math.min(
        TAP_TEMPO_MAX_BPM,
        Math.max(TAP_TEMPO_MIN_BPM, bpm),
      );
    },
  };
}
