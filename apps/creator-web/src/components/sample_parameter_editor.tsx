import {useEffect, useRef, useState} from "react";

import {ModalDialog} from "./modal_dialog";
import type {SampleParameterSpec} from "./parameter_slider";
import "./sample_parameter_editor.css";

interface SampleParameterEditorProps {
  parameter: SampleParameterSpec;
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
  parameter, value, returnFocus, onPreview, onCommit, onDiscard, onClose,
}: SampleParameterEditorProps) {
  const [draft, setDraft] = useState({text: String(value), number: value, valid: true});
  const previewing = useRef(false);
  const settled = useRef(false);
  const discardRef = useRef(onDiscard);
  discardRef.current = onDiscard;
  const unit = UNITS[parameter.field];

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

  return (
    <ModalDialog
      label={`Edit ${parameter.ariaLabel}`}
      returnFocus={returnFocus}
      onCancel={cancel}
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
        <h2>{parameter.label}</h2>
        <label className="sample-parameter-input">
          <span>{parameter.label}{unit === "" ? "" : ` (${unit})`}</span>
          <input
            type="number"
            aria-label={`${parameter.ariaLabel} value`}
            min={parameter.min}
            max={parameter.max}
            step={parameter.step}
            value={draft.text}
            aria-invalid={!draft.valid}
            onChange={(event) => {
              const nextText = event.currentTarget.value;
              const next = event.currentTarget.valueAsNumber;
              const valid = Number.isFinite(next) && next >= parameter.min && next <= parameter.max &&
                event.currentTarget.validity.valid;
              setDraft({text: nextText, number: next, valid});
              if (!valid) {
                discard();
                return;
              }
              previewing.current = true;
              onPreview(next);
            }}
          />
        </label>
        <p className="sample-parameter-hint">
          {parameter.min}…{parameter.max}{unit === "" ? "" : ` ${unit}`}; step {parameter.step}.
          {parameter.field === "pan" ? " Negative = left, 0 = centre, positive = right." : null}
          {parameter.field === "tone" ? " Negative = LP, positive = HP; −2…2 = off." : null}
        </p>
        <div className="confirmation-actions">
          <button type="button" onClick={cancel}>Cancel {parameter.label}</button>
          <button type="submit" disabled={!draft.valid}>Apply {parameter.label}</button>
        </div>
      </form>
    </ModalDialog>
  );
}
