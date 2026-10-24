import {useEffect, useState} from "react";
import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {countInBeatsRemaining, type CountInState} from "../runtime/count_in_controller";
import {userMessage} from "../state/error_messages";

// Like the ordinary playhead, this read-only display extrapolates a real
// observed native frame. Reaching planned S never fabricates an Applied receipt.
export function CountInReadout({state, transport, running}: {
  state: CountInState;
  transport: PatternTransportStatus | null;
  running: boolean;
}) {
  const anchorFrame = transport?.runtimeFrame ?? null;
  const observedAt = transport?.observedAtMilliseconds ?? null;
  const [frame, setFrame] = useState<number | null>(null);
  useEffect(() => {
    if (!state.active || state.recording || !running || anchorFrame === null || observedAt === null) {
      setFrame(null);
      return;
    }
    const advance = (now: number) => setFrame(anchorFrame + Math.floor(Math.max(0, now - observedAt) * 48));
    advance(performance.now());
    let cancelled = false;
    let animation = window.requestAnimationFrame(function tick(now) {
      if (cancelled) return;
      advance(now);
      animation = window.requestAnimationFrame(tick);
    });
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(animation);
    };
  }, [state.active, state.recording, running, anchorFrame, observedAt]);
  const beats = frame === null ? null : countInBeatsRemaining(state.status, frame);
  const label = state.phase === "cancelling" ? "COUNT-IN · Cancelling"
    : state.phase === "settling" || state.phase === "handoff" ? "COUNT-IN · Finishing"
    : beats === null ? "COUNT-IN · Preparing"
    : beats === 0 ? "COUNT-IN · Starting"
    : `COUNT-IN · ${beats} ${beats === 1 ? "beat" : "beats"} left`;
  return <>
    {state.active && !state.recording
      ? <output aria-label="Count-in status" aria-live="off">{label}</output> : null}
    {state.errorMessage === null ? null : <span role="alert">
      {state.errorCode === "UNSUPPORTED_AUDIO" ? state.errorMessage
        : `COUNT-IN: ${userMessage(state.errorCode ?? "INTERNAL_ERROR").message}`}
    </span>}
  </>;
}
