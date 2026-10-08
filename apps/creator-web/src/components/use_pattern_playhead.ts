import {useEffect, useState} from "react";

import {sequencePlayheadTick} from "../state/sequence_grid_model";
import type {PatternTransportState} from "../state/pattern_transport_state";

// The Runtime advances 48 frames per millisecond at its fixed 48 kHz.
const FRAMES_PER_MILLISECOND = 48;

// The playing Pattern's tick on the render clock, or null while stopped. The
// last observed Runtime frame anchors it, so a display that mounts
// mid-playback resumes at the playing position instead of the origin.
export function usePatternPlayheadTick(
  transport: PatternTransportState | undefined,
  bpm: number | null,
  lengthTicks: number | null,
): number | null {
  const status = transport?.status ?? null;
  const playing = status !== null && status.playing === true &&
    lengthTicks !== null && bpm !== null;
  const originFrame = playing && status !== null ? status.originFrame : null;
  const anchorFrame = playing && status !== null ? status.runtimeFrame : null;
  const anchorObservedAt = playing && status !== null
    ? status.observedAtMilliseconds
    : null;
  const [playheadTick, setPlayheadTick] = useState<number | null>(null);
  useEffect(() => {
    if (originFrame === null || anchorFrame === null || anchorObservedAt === null ||
        lengthTicks === null || bpm === null) {
      setPlayheadTick(null);
      return;
    }
    const tickAt = (now: number) => sequencePlayheadTick({
      originFrame,
      runtimeFrame: anchorFrame +
        Math.floor(Math.max(0, now - anchorObservedAt) * FRAMES_PER_MILLISECOND),
      bpm,
      lengthTicks,
    });
    setPlayheadTick(tickAt(performance.now()));
    // A frame already dequeued when the cleanup runs escapes
    // cancelAnimationFrame; the flag is what stops it rescheduling.
    let cancelled = false;
    let animationFrame = window.requestAnimationFrame(function advance(now) {
      if (cancelled) return;
      setPlayheadTick(tickAt(now));
      animationFrame = window.requestAnimationFrame(advance);
    });
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(animationFrame);
    };
  }, [originFrame, anchorFrame, anchorObservedAt, lengthTicks, bpm]);
  return playheadTick;
}
