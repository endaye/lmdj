import {useEffect, useRef, useState} from "react";
import {ModalDialog} from "./modal_dialog";

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

interface PatternSelectorProps {
  index: number;
  patternIds: readonly string[];
  patternId: string;
  disabled: boolean;
  // #1958: while a playing-state switch is queued, the 1-based index of the
  // queued target, shown after the current one (`GROOVE / 01 → 03`). Null or
  // omitted when nothing is queued.
  queuedIndex?: number | null;
  onSelect(patternId: string): void;
}

export function PatternSelector({index, patternIds, patternId, disabled, queuedIndex, onSelect}: PatternSelectorProps) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  return (
    <div className="pattern-selector" data-testid="sequence-pattern"
      data-pattern-id={patternId} data-pattern-count={patternIds.length}>
      <button ref={trigger} type="button" className="touch-control"
        aria-label="Choose Pattern" aria-haspopup="dialog" disabled={disabled}
        onClick={() => setOpen(true)}>
        <span>GROOVE / {String(Math.max(index, 1)).padStart(2, "0")}{
          queuedIndex !== undefined && queuedIndex !== null && queuedIndex > 0
            ? ` → ${String(queuedIndex).padStart(2, "0")}` : ""
        }</span>
        <span className="pattern-selector-count">{Math.max(index, 1)}/{Math.max(patternIds.length, 1)}</span>
      </button>
      {open ? <ModalDialog returnFocus={trigger.current} onCancel={() => setOpen(false)}
        dialogClassName="sequence-picker-dialog" label="Choose Pattern"
        resolveInitialFocus={(dialog) => dialog.querySelector('[aria-pressed="true"]')}>
        <h2>CHOOSE PATTERN</h2>
        <div className="sequence-picker-options">
          {patternIds.map((id, position) => <button key={id} type="button"
            className="touch-control" data-pattern-choice={id}
            aria-pressed={id === patternId} disabled={disabled}
            onClick={() => {
              setOpen(false);
              if (id !== patternId) onSelect(id);
            }}>GROOVE / {String(position + 1).padStart(2, "0")}</button>)}
        </div>
        <button type="button" className="touch-control" onClick={() => setOpen(false)}>Cancel</button>
      </ModalDialog> : null}
    </div>
  );
}
