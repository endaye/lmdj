import { useCallback, useEffect, useRef, useState } from "react";
import type { ChameleonVisualState } from "./model";

export function useChameleonController(
  input: ChameleonVisualState,
  readyDurationMs = 4000,
) {
  const seenEvents = useRef(new Set<string>());
  const [manualOpen, setManualOpen] = useState(false);
  const [automaticOpen, setAutomaticOpen] = useState(false);
  const eventKind = input.event?.kind ?? null;
  const eventKey = input.event?.key ?? null;

  useEffect(() => {
    if (input.placement === "stage") {
      setManualOpen(false);
      setAutomaticOpen(false);
      return;
    }
    if (!eventKind || !eventKey) return;
    if (seenEvents.current.has(`${eventKind}:${eventKey}`)) return;
    seenEvents.current.add(`${eventKind}:${eventKey}`);
    setAutomaticOpen(true);
    if (eventKind !== "ready") return;
    const timer = window.setTimeout(
      () => setAutomaticOpen(false),
      readyDurationMs,
    );
    return () => window.clearTimeout(timer);
  }, [eventKey, eventKind, input.placement, readyDurationMs]);

  const reveal = useCallback(() => setManualOpen(true), []);
  const dismiss = useCallback(() => {
    setManualOpen(false);
    setAutomaticOpen(false);
  }, []);
  const expanded =
    input.placement === "stage" || manualOpen || automaticOpen;
  const toggle = useCallback(() => {
    if (expanded) dismiss();
    else reveal();
  }, [dismiss, expanded, reveal]);

  return {
    expanded,
    visualState: {
      ...input,
      placement:
        input.placement === "stage"
          ? "stage" as const
          : expanded
            ? "floating" as const
            : "dock" as const,
    },
    reveal,
    dismiss,
    toggle,
  };
}
