// Touch-area controls to the Desktop Final spec (2026-10-04 Sequence hardware
// UI decision, item 6): 44 px controls with an 8 px radius on the raised
// fill, the selected one solid accent with dark text, and no native selects
// or checkboxes. Selection is announced with aria-pressed.

export interface TouchSegmentOption<T extends string | number> {
  value: T;
  label: string;
  ariaLabel?: string;
}

interface TouchSegmentProps<T extends string | number> {
  label: string;
  options: readonly TouchSegmentOption<T>[];
  value: T | null;
  disabled?: boolean;
  className?: string;
  onChange(value: T): void;
}

export function TouchSegment<T extends string | number>({
  label,
  options,
  value,
  disabled = false,
  className,
  onChange,
}: TouchSegmentProps<T>) {
  return (
    <div className={`touch-segment${className === undefined ? "" : ` ${className}`}`}
      role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          className="touch-control"
          aria-pressed={value === option.value}
          {...(option.ariaLabel === undefined ? {} : {"aria-label": option.ariaLabel})}
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

interface PatternStepperProps {
  index: number;
  count: number;
  patternId: string;
  disabled: boolean;
  onStep(offset: -1 | 1): void;
}

// `‹ GROOVE / NN ›` with the current position among the Project's Patterns.
export function PatternStepper({index, count, patternId, disabled, onStep}: PatternStepperProps) {
  return (
    <div className="pattern-stepper" data-testid="sequence-pattern"
      data-pattern-id={patternId} data-pattern-count={count}>
      <button type="button" className="touch-control" aria-label="Previous Pattern"
        disabled={disabled || index <= 1} onClick={() => onStep(-1)}>‹</button>
      <h1>GROOVE / {String(Math.max(index, 1)).padStart(2, "0")}</h1>
      <span className="pattern-stepper-count">{Math.max(index, 1)}/{Math.max(count, 1)}</span>
      <button type="button" className="touch-control" aria-label="Next Pattern"
        disabled={disabled || index >= count} onClick={() => onStep(1)}>›</button>
    </div>
  );
}
