import type {PadEq} from "../runtime/runtime_types";

// Display projection of the existing 48 kHz voice EQ. These are the same
// RBJ shelf/bell/Butterworth-cut designs as voice_dsp.cpp, including its
// float coefficient storage. This evaluates a response; it processes no PCM.
const RATE = 48_000;
const BUTTERWORTH_Q = Math.SQRT1_2;
type Coefficients = readonly [number, number, number, number, number];

function normalized(b0: number, b1: number, b2: number, a0: number, a1: number, a2: number): Coefficients {
  return [Math.fround(b0 / a0), Math.fround(b1 / a0), Math.fround(b2 / a0), Math.fround(a1 / a0), Math.fround(a2 / a0)];
}

function pass(hz: number, high: boolean): Coefficients {
  const w = 2 * Math.PI * hz / RATE, c = Math.cos(w), alpha = Math.sin(w) / (2 * BUTTERWORTH_Q);
  const side = high ? (1 + c) / 2 : (1 - c) / 2;
  return normalized(side, high ? -(1 + c) : 1 - c, side, 1 + alpha, -2 * c, 1 - alpha);
}

function shelf(hz: number, db: number, high: boolean): Coefficients {
  const a = 10 ** (db / 40), w = 2 * Math.PI * hz / RATE, c = Math.cos(w);
  const root = 2 * Math.sqrt(a) * Math.sin(w) / (2 * BUTTERWORTH_Q), sign = high ? -1 : 1;
  return normalized(
    a * ((a + 1) - sign * (a - 1) * c + root),
    sign * 2 * a * ((a - 1) - sign * (a + 1) * c),
    a * ((a + 1) - sign * (a - 1) * c - root),
    (a + 1) + sign * (a - 1) * c + root,
    -sign * 2 * ((a - 1) + sign * (a + 1) * c),
    (a + 1) + sign * (a - 1) * c - root,
  );
}

function stages(eq: Readonly<PadEq>): Coefficients[] {
  const result: Coefficients[] = [];
  if (eq.low !== null) result.push(eq.low.kind === "cut"
    ? pass(eq.low.freqHz, true) : shelf(eq.low.freqHz, eq.low.gainMillidb / 1000, false));
  if (eq.mid !== null) {
    const a = 10 ** (eq.mid.gainMillidb / 40_000), w = 2 * Math.PI * eq.mid.freqHz / RATE;
    const c = Math.cos(w), alpha = Math.sin(w) / (2 * eq.mid.qMilli / 1000);
    result.push(normalized(1 + alpha * a, -2 * c, 1 - alpha * a, 1 + alpha / a, -2 * c, 1 - alpha / a));
  }
  if (eq.high !== null) result.push(eq.high.kind === "cut"
    ? pass(eq.high.freqHz, false) : shelf(eq.high.freqHz, eq.high.gainMillidb / 1000, true));
  return result;
}

function response(filters: readonly Coefficients[], hz: number): number {
  const w = 2 * Math.PI * hz / RATE, c1 = Math.cos(w), s1 = Math.sin(w);
  const c2 = Math.cos(2 * w), s2 = Math.sin(2 * w);
  let db = 0;
  for (const [b0, b1, b2, a1, a2] of filters) {
    const nr = b0 + b1 * c1 + b2 * c2, ni = -b1 * s1 - b2 * s2;
    const dr = 1 + a1 * c1 + a2 * c2, di = -a1 * s1 - a2 * s2;
    db += 10 * Math.log10((nr * nr + ni * ni) / (dr * dr + di * di));
  }
  return db;
}

export function eqMagnitudeDb(eq: Readonly<PadEq>, hz: number): number {
  if (!(hz > 0 && hz < RATE / 2)) throw new RangeError("EQ display frequency must be below Nyquist and above zero");
  return response(stages(eq), hz);
}

export function eqResponseCurve(eq: Readonly<PadEq>): readonly {hz: number; db: number}[] {
  const filters = stages(eq);
  const frequencies = new Set(Array.from({length: 97}, (_, index) => 20 * 1000 ** (index / 96)));
  for (const band of [eq.low, eq.mid, eq.high]) if (band !== null) frequencies.add(band.freqHz);
  return [...frequencies].sort((a, b) => a - b).map(hz => {
    return {hz, db: response(filters, hz)};
  });
}
