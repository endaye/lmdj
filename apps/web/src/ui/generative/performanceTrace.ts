import type { VisualRole } from "./visualSignature";

export interface PadPressEvent {
  sequence: number;
  padIndex: number;
}

export interface PerformanceTrace {
  id: string;
  padIndex: number;
  role: VisualRole;
  signatureSeed: string;
  expiresAt: number;
}

const MAX_TRACES = 8;

export function beatDurationMs(bpm: number): number {
  return 60_000 / Math.max(1, bpm);
}

export function appendPerformanceTrace(
  current: readonly PerformanceTrace[],
  press: PadPressEvent,
  role: VisualRole,
  projectSeed: string,
  bpm: number,
  now: number,
): PerformanceTrace[] {
  const next = [
    ...current,
    {
      id: `${projectSeed}:${press.sequence}:${press.padIndex}`,
      padIndex: press.padIndex,
      role,
      signatureSeed: `${projectSeed}:${press.padIndex}:${press.sequence}`,
      expiresAt: now + beatDurationMs(bpm),
    },
  ];
  return next.slice(-MAX_TRACES);
}

export function prunePerformanceTraces(
  current: readonly PerformanceTrace[],
  now: number,
): PerformanceTrace[] {
  return current.filter((trace) => trace.expiresAt > now);
}
