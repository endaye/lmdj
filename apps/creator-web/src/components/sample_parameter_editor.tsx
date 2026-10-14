import {useEffect, useId, useRef, useState} from "react";

import {ModalDialog} from "./modal_dialog";
import type {SampleParameterSpec} from "./parameter_slider";
import "./sample_parameter_editor.css";

interface SampleParameterEditorProps {
  parameter: SampleParameterSpec;
  padLabel: string;
  value: number;
  returnFocus: HTMLElement | null;
  onPreview(value: number): void;
  onCommit(value: number): void;
  onDiscard(): void;
  onClose(): void;
}

const UNITS = {
  gainMillidb: "dB", pitchCents: "st", pan: "", attackMs: "ms",
  releaseMs: "ms", tone: "",
};

export function SampleParameterEditor({
  parameter, padLabel, value, returnFocus, onPreview, onCommit, onDiscard, onClose,
}: SampleParameterEditorProps) {
  const [draft, setDraft] = useState({text: String(value), number: value, valid: true});
  const previewing = useRef(false);
  const settled = useRef(false);
  const discardRef = useRef(onDiscard);
  discardRef.current = onDiscard;
  const unit = UNITS[parameter.field];
  const hintId = useId();
  const formatValue = (number: number) =>
    `${number.toFixed(parameter.step < 1 ? 1 : 0).replace("-", "−")}${unit === "" ? "" : ` ${unit}`}`;

  useEffect(() => () => {
    if (!settled.current && previewing.current) discardRef.current();
  }, []);

  const discard = () => {
    if (!previewing.current) return;
    previewing.current = false;
    onDiscard();
  };
  const cancel = () => {
    settled.current = true;
    discard();
    onClose();
  };
  const apply = () => {
    if (settled.current || !draft.valid) return;
    settled.current = true;
    if (draft.number === value) discard();
    else {
      previewing.current = false;
      onCommit(draft.number);
    }
    onClose();
  };
  const changeDraft = (input: HTMLInputElement) => {
    const next = input.valueAsNumber;
    const valid = Number.isFinite(next) && next >= parameter.min && next <= parameter.max &&
      input.validity.valid;
    setDraft({text: input.value, number: next, valid});
    if (!valid) {
      discard();
      return;
    }
    previewing.current = true;
    onPreview(next);
  };

  return (
    <ModalDialog
      label={`Edit ${parameter.ariaLabel}`}
      returnFocus={returnFocus}
      onCancel={cancel}
      placement="touch-workspace"
      dialogClassName="sample-confirmation sample-parameter-editor"
      resolveInitialFocus={(dialog) => {
        const input = dialog.querySelector("input");
        input?.select();
        return input;
      }}
    >
      <form
        onSubmit={(event) => { event.preventDefault(); apply(); }}
        onKeyDown={(event) => {
          // Escape and Tab reach ModalDialog's cancel/focus trap. Other keys
          // belong to this input session, including ordinary text Undo.
          if (event.key !== "Escape" && event.key !== "Tab") event.stopPropagation();
        }}
      >
        <header className="sample-parameter-header">
          <h2>PAD {parameter.label.toUpperCase()}</h2>
          <span className="sample-parameter-target" aria-label={padLabel}>{padLabel.replace(/^Pad /, "")}</span>
        </header>
        <div className="sample-parameter-content">
          <div className="sample-parameter-draft">
            <label className="sample-parameter-input">
              <span>PREVIEW</span>
              <span className="sample-parameter-number">
                <input
                  type="number"
                  aria-label={`${parameter.ariaLabel} value`}
                  aria-describedby={hintId}
                  min={parameter.min}
                  max={parameter.max}
                  step={parameter.step}
                  value={draft.text}
                  aria-invalid={!draft.valid}
                  onChange={(event) => changeDraft(event.currentTarget)}
                />
                {unit === "" ? null : <span aria-hidden="true">{unit}</span>}
              </span>
            </label>
            <p className="sample-parameter-saved">Saved value: {formatValue(value)}</p>
          </div>
          <label className="sample-parameter-range">
            <span className="sample-parameter-range-label">
              <span>{parameter.label.toUpperCase()}</span>
              <span>{draft.valid ? formatValue(draft.number) : "Invalid value"}</span>
            </span>
            <input
              type="range"
              aria-label={`${parameter.ariaLabel} preview`}
              aria-describedby={hintId}
              min={parameter.min}
              max={parameter.max}
              step={parameter.step}
              value={draft.valid ? draft.number : value}
              onChange={(event) => changeDraft(event.currentTarget)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  apply();
                }
              }}
            />
          </label>
          <p id={hintId} className="sample-parameter-hint">
            Range {parameter.min}…{parameter.max}{unit === "" ? "" : ` ${unit}`} · step {parameter.step} · live preview.
            {parameter.field === "pan" ? " Negative = left, 0 = centre, positive = right." : null}
            {parameter.field === "tone" ? " Negative = LP, positive = HP; −2…2 = off." : null}
          </p>
        </div>
        <footer className="sample-parameter-footer">
          <div className="confirmation-actions">
            <button className="touch-control is-primary" type="submit" aria-label={`Apply ${parameter.label}`} disabled={!draft.valid}>Apply</button>
            <button className="touch-control" type="button" aria-label={`Cancel ${parameter.label}`} onClick={cancel}>Cancel</button>
          </div>
          <p className="sample-parameter-keys">ENTER Apply <span>ESC Cancel</span></p>
        </footer>
      </form>
    </ModalDialog>
  );
}
