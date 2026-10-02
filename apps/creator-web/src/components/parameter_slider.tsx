import {ValueSlider} from "./value_slider";
import type {PadPlayback} from "../runtime/runtime_types";

// One numeric Pad playback field edited by a range input. The gesture
// machinery (preview, commit-once-on-release, Escape/pointercancel cancel)
// lives in ValueSlider; this wrapper keeps the PadPlayback-shaped interface:
// the input works in display units and the stored value is display * scale.
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
  const toStored = (display: number) => Math.round(display * scale);
  const withField = (display: number): Readonly<PadPlayback> => ({
    ...playback,
    [field]: toStored(display),
  });
  return (
    <ValueSlider
      label={label}
      ariaLabel={ariaLabel}
      className={className}
      value={playback[field] / scale}
      min={min}
      max={max}
      step={step}
      format={(display) => format(toStored(display))}
      disabled={disabled}
      audioSuspended={audioSuspended}
      onPreview={(display) => onPreview(withField(display))}
      onCommit={(display) => onCommit(withField(display))}
      onCancel={onCancel}
    />
  );
}
