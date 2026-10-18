import type {StereoOutputMeter} from "@lmdj/web-runtime-platform/runtime_types";

export interface OutputMeterChannel {
  readonly peak: number;
  readonly dbfs: number;
  readonly heldPeak: number;
  readonly heldPeakFrame: string;
  readonly heldDbfs: number;
}

export type OutputMeterView = Extract<StereoOutputMeter, {state: "unavailable"}> |
  Readonly<{
    state: "available";
    owner: string;
    sampleRate: number;
    windowEndFrame: string;
    left: OutputMeterChannel;
    right: OutputMeterChannel;
  }>;

export const OUTPUT_METER_UNAVAILABLE: OutputMeterView = Object.freeze({
  state: "unavailable", reason: "tap-unavailable",
});

export function peakDbfs(peak: number): number {
  return peak === 0 ? -Infinity : Math.min(0, Math.max(-60, 20 * Math.log10(peak)));
}

export function formatDbfs(dbfs: number): string {
  if (dbfs === -Infinity) return "−∞";
  const rounded = Math.round(dbfs * 10) / 10;
  return rounded < 0 ? `−${Math.abs(rounded).toFixed(1)}` : "0.0";
}

export function meterPercent(dbfs: number): number {
  return dbfs === -Infinity ? 0 : (dbfs + 60) / 60 * 100;
}

function channel(peak: number, peakFrame: string, previous: OutputMeterChannel | null,
  contextFrame: number, sampleRate: number): OutputMeterChannel {
  // Age the actual measured peak, never this read or an animation timestamp.
  // Repeated reads of a packet cannot restart its one-second hold.
  const replace = previous === null || peak >= previous.heldPeak ||
    contextFrame - Number(previous.heldPeakFrame) >= sampleRate;
  const heldPeak = replace ? peak : previous.heldPeak;
  return Object.freeze({peak, dbfs: peakDbfs(peak), heldPeak,
    heldPeakFrame: replace ? peakFrame : previous.heldPeakFrame,
    heldDbfs: peakDbfs(heldPeak)});
}

// The SDK owns packet validation and freshness. This consumer only projects
// its typed measurement; unavailable discards the previous owner's hold.
export function projectOutputMeter(previous: OutputMeterView,
  measurement: StereoOutputMeter): OutputMeterView {
  if (measurement.state === "unavailable") {
    return previous.state === "unavailable" && previous.reason === measurement.reason
      ? previous : measurement;
  }
  const prior = previous.state === "available" && previous.owner === measurement.owner &&
    previous.sampleRate === measurement.sampleRate ? previous : null;
  // currentTime is a sample-clock value. Recover its nearest integer frame:
  // ceil can turn frame119999's floating representation into phantom120000.
  const contextFrame = Math.round(measurement.contextTimeSeconds * measurement.sampleRate);
  const left = channel(measurement.leftPeak, measurement.leftPeakFrame,
    prior?.left ?? null, contextFrame, measurement.sampleRate);
  const right = channel(measurement.rightPeak, measurement.rightPeakFrame,
    prior?.right ?? null, contextFrame, measurement.sampleRate);
  if (prior !== null && prior.windowEndFrame === measurement.windowEndFrame &&
      prior.left.heldPeakFrame === left.heldPeakFrame &&
      prior.right.heldPeakFrame === right.heldPeakFrame) return prior;
  return Object.freeze({state: "available", owner: measurement.owner,
    sampleRate: measurement.sampleRate, windowEndFrame: measurement.windowEndFrame,
    left, right});
}
