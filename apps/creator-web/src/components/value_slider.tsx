import {useEffect, useRef, useState} from "react";

// One numeric value edited by a range input. A gesture previews every move,
// commits once on release (pointer up, a window pointerup, the release of any
// key a range input moves on, or blur) when the value changed, and cancels on
// Escape or pointercancel.
const MOVE_KEYS = new Set([
  "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
  "Home", "End", "PageUp", "PageDown",
]);

interface ValueSliderProps {
  label: string;
  ariaLabel: string;
  className: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (value: number) => string;
  disabled: boolean;
  // Cleared gestures when audio is suspended mid-drag.
  audioSuspended?: boolean;
  onPreview: (value: number) => void;
  onCommit: (value: number) => void;
  onCancel: () => void;
}

interface Gesture {
  base: number;
  latest: number;
}

export function ValueSlider({
  label,
  ariaLabel,
  className,
  value,
  min,
  max,
  step,
  format,
  disabled,
  audioSuspended = false,
  onPreview,
  onCommit,
  onCancel,
}: ValueSliderProps) {
  const [draft, setDraft] = useState<number | null>(null);
  const gesture = useRef<Gesture | null>(null);
  const pointerId = useRef<number | null>(null);
  const commitRef = useRef<() => void>(() => {});
  const cancelRef = useRef<() => void>(() => {});
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;
  const shown = draft ?? value;

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
      gesture.current = {base: value, latest: value};
    }
  };
  const preview = (next: number) => {
    if (!Number.isFinite(next)) return;
    begin();
    const clamped = Math.min(max, Math.max(min, next));
    gesture.current = {base: gesture.current!.base, latest: clamped};
    setDraft(clamped);
    onPreview(clamped);
  };
  const commit = () => {
    const current = gesture.current;
    if (current === null) return;
    pointerId.current = null;
    gesture.current = null;
    setDraft(null);
    if (current.base !== current.latest) {
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
        value={shown}
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
          if (MOVE_KEYS.has(event.key)) commit();
        }}
        onBlur={commit}
      />
      <output>{format(shown)}</output>
    </label>
  );
}
