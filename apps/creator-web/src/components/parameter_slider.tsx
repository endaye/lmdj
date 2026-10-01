import {useEffect, useRef, useState} from "react";

import type {PadPlayback} from "../runtime/runtime_types";

// One numeric Pad playback field edited by a range input. A gesture previews
// every move, commits once on release (pointer up, Arrow key up, or a window
// pointerup) when the value changed, and cancels on Escape or pointercancel.
export type ParameterField = "gainMillidb" | "pitchCents" | "pan";

interface ParameterSliderProps {
  label: string;
  ariaLabel: string;
  className: string;
  field: ParameterField;
  // The input works in display units; the stored value is display * scale.
  min: number;
  max: number;
  step: number;
  scale: number;
  format: (stored: number) => string;
  playback: Readonly<PadPlayback>;
  disabled: boolean;
  // Cleared gestures when audio is suspended mid-drag.
  audioSuspended: boolean;
  onPreview: (playback: Readonly<PadPlayback>) => void;
  onCommit: (playback: Readonly<PadPlayback>) => void;
  onCancel: () => void;
}

interface Gesture {
  base: Readonly<PadPlayback>;
  latest: Readonly<PadPlayback>;
}

export function ParameterSlider({
  label,
  ariaLabel,
  className,
  field,
  min,
  max,
  step,
  scale,
  format,
  playback,
  disabled,
  audioSuspended,
  onPreview,
  onCommit,
  onCancel,
}: ParameterSliderProps) {
  const [draft, setDraft] = useState<number | null>(null);
  const gesture = useRef<Gesture | null>(null);
  const pointerId = useRef<number | null>(null);
  const commitRef = useRef<() => void>(() => {});
  const cancelRef = useRef<() => void>(() => {});
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;
  const shown = draft ?? playback[field];

  useEffect(() => () => {
    pointerId.current = null;
    if (gesture.current !== null) {
      gesture.current = null;
      onCancelRef.current();
    }
  }, []);

  useEffect(() => {
    if (!audioSuspended) return;
    pointerId.current = null;
    gesture.current = null;
    setDraft(null);
  }, [audioSuspended]);

  const begin = () => {
    if (gesture.current === null) {
      gesture.current = {base: playback, latest: playback};
    }
  };
  const preview = (display: number) => {
    if (!Number.isFinite(display)) return;
    begin();
    const stored = Math.min(
      max * scale,
      Math.max(min * scale, Math.round(display * scale)),
    );
    const current = gesture.current!;
    const next = {...current.latest, [field]: stored};
    gesture.current = {base: current.base, latest: next};
    setDraft(stored);
    onPreview(next);
  };
  const commit = () => {
    const current = gesture.current;
    if (current === null) return;
    pointerId.current = null;
    gesture.current = null;
    setDraft(null);
    if (current.base[field] !== current.latest[field]) {
      onCommit(current.latest);
    }
  };
  const cancel = () => {
    if (gesture.current === null) return;
    pointerId.current = null;
    gesture.current = null;
    setDraft(null);
    onCancel();
  };
  commitRef.current = commit;
  cancelRef.current = cancel;

  useEffect(() => {
    const finish = (event: PointerEvent) => {
      if (pointerId.current === event.pointerId) commitRef.current();
    };
    const abort = (event: PointerEvent) => {
      if (pointerId.current === event.pointerId) cancelRef.current();
    };
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", abort);
    return () => {
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", abort);
    };
  }, []);

  const beginPointer = (event: React.PointerEvent<HTMLInputElement>) => {
    pointerId.current = event.pointerId;
    begin();
    if (typeof event.currentTarget.setPointerCapture === "function") {
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // The window-level release listener remains authoritative fallback.
      }
    }
  };

  return (
    <label className={className}>
      <span>{label}</span>
      <input
        type="range"
        min={String(min)}
        max={String(max)}
        step={String(step)}
        value={shown / scale}
        disabled={disabled}
        aria-label={ariaLabel}
        onPointerDown={beginPointer}
        onPointerUp={commit}
        onPointerCancel={cancel}
        onChange={(event) => preview(event.currentTarget.valueAsNumber)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            cancel();
          }
        }}
        onKeyUp={(event) => {
          if (event.key.startsWith("Arrow")) commit();
        }}
      />
      <output>{format(shown)}</output>
    </label>
  );
}
