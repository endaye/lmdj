import {useEffect, useRef, useState, type ReactNode} from "react";

import {ModalDialog} from "./modal_dialog";
import type {PadPlayback, SampleTriggerMode} from "../runtime/runtime_types";

interface SampleControlsProps {
  padLabel: string;
  playback: Readonly<PadPlayback>;
  audioSuspended: boolean;
  disabled?: boolean;
  onPreview: (playback: Readonly<PadPlayback>) => void;
  onCommit: (playback: Readonly<PadPlayback>) => void;
  onCancel?: () => void;
  onReset: () => void;
}

const NOOP = () => {};

interface ConfirmationDialogProps {
  labelledBy: string;
  returnFocus: HTMLElement | null;
  onCancel: () => void;
  children: ReactNode;
}

interface GainGesture {
  base: Readonly<PadPlayback>;
  latest: Readonly<PadPlayback>;
}

// Behaviour is unchanged; the modal machinery (inert background walk,
// backdrop, focus on open, Tab trap, Escape, returnFocus restore) now lives
// in the shared ModalDialog primitive.
export function ConfirmationDialog({
  labelledBy,
  returnFocus,
  onCancel,
  children,
}: ConfirmationDialogProps) {
  return (
    <ModalDialog
      labelledBy={labelledBy}
      returnFocus={returnFocus}
      onCancel={onCancel}
      dialogClassName="sample-confirmation"
    >
      {children}
    </ModalDialog>
  );
}

function loopEnabled(mode: SampleTriggerMode): boolean {
  return mode === "loop_gate" || mode === "loop_toggle";
}

function primaryEnabled(mode: SampleTriggerMode): boolean {
  return mode === "one_shot" || mode === "loop_toggle";
}

function modeFor(loop: boolean, primary: boolean): SampleTriggerMode {
  if (loop) return primary ? "loop_toggle" : "loop_gate";
  return primary ? "one_shot" : "gate";
}

export function SampleControls({
  padLabel,
  playback,
  audioSuspended,
  disabled = false,
  onPreview,
  onCommit,
  onCancel = NOOP,
  onReset,
}: SampleControlsProps) {
  const [confirmingReset, setConfirmingReset] = useState(false);
  const resetTrigger = useRef<HTMLButtonElement | null>(null);
  const [draftGain, setDraftGain] = useState<number | null>(null);
  const gainGesture = useRef<GainGesture | null>(null);
  const gainPointerId = useRef<number | null>(null);
  const commitGainRef = useRef<() => void>(() => {});
  const cancelGainRef = useRef<() => void>(() => {});
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;
  const loop = loopEnabled(playback.triggerMode);
  const primary = primaryEnabled(playback.triggerMode);
  const shownGain = draftGain ?? playback.gainMillidb;

  useEffect(() => () => {
    gainPointerId.current = null;
    if (gainGesture.current !== null) {
      gainGesture.current = null;
      cancelRef.current();
    }
  }, []);

  useEffect(() => {
    if (!audioSuspended) return;
    gainPointerId.current = null;
    gainGesture.current = null;
    setDraftGain(null);
    setConfirmingReset(false);
  }, [audioSuspended]);

  const beginGain = () => {
    if (gainGesture.current === null) {
      gainGesture.current = {base: playback, latest: playback};
    }
  };
  const previewGain = (decibels: number) => {
    if (!Number.isFinite(decibels)) return;
    beginGain();
    const gainMillidb = Math.min(6_000, Math.max(-60_000, Math.round(decibels * 1_000)));
    const current = gainGesture.current!;
    const next = {...current.latest, gainMillidb};
    gainGesture.current = {base: current.base, latest: next};
    setDraftGain(gainMillidb);
    onPreview(next);
  };
  const commitGain = () => {
    const current = gainGesture.current;
    if (current === null) return;
    gainPointerId.current = null;
    gainGesture.current = null;
    setDraftGain(null);
    if (current.base.gainMillidb !== current.latest.gainMillidb) {
      onCommit(current.latest);
    }
  };
  const cancelGain = () => {
    if (gainGesture.current === null) return;
    gainPointerId.current = null;
    gainGesture.current = null;
    setDraftGain(null);
    onCancel();
  };
  commitGainRef.current = commitGain;
  cancelGainRef.current = cancelGain;

  useEffect(() => {
    const finish = (event: PointerEvent) => {
      if (gainPointerId.current === event.pointerId) commitGainRef.current();
    };
    const cancel = (event: PointerEvent) => {
      if (gainPointerId.current === event.pointerId) cancelGainRef.current();
    };
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", cancel);
    return () => {
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
    };
  }, []);

  const beginGainPointer = (event: React.PointerEvent<HTMLInputElement>) => {
    gainPointerId.current = event.pointerId;
    beginGain();
    if (typeof event.currentTarget.setPointerCapture === "function") {
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // The window-level release listener remains authoritative fallback.
      }
    }
  };

  return (
    <section className="sample-controls" aria-label={`${padLabel} Sample controls`}>
      {audioSuspended ? (
        <p className="audio-preview-copy" role="status">Activate Audio to preview</p>
      ) : null}
      <div className="sample-toggle-row">
        <button
          type="button"
          aria-pressed={loop}
          disabled={disabled}
          onClick={() => onCommit({
            ...playback,
            triggerMode: modeFor(!loop, primary),
          })}
        >
          Loop
        </button>
        <button
          type="button"
          aria-pressed={primary}
          disabled={disabled}
          onClick={() => onCommit({
            ...playback,
            triggerMode: modeFor(loop, !primary),
          })}
        >
          {loop ? "Hold" : "One Shot"}
        </button>
        <button
          type="button"
          aria-pressed={playback.muted}
          disabled={disabled}
          onClick={() => onCommit({...playback, muted: !playback.muted})}
        >
          Mute
        </button>
      </div>
      <label className="volume-control">
        <span>Volume</span>
        <input
          type="range"
          min="-60"
          max="6"
          step="0.1"
          value={shownGain / 1_000}
          disabled={disabled}
          aria-label={`${padLabel} Volume`}
          onPointerDown={beginGainPointer}
          onPointerUp={commitGain}
          onPointerCancel={cancelGain}
          onChange={(event) => previewGain(event.currentTarget.valueAsNumber)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              cancelGain();
            }
          }}
          onKeyUp={(event) => {
            if (event.key.startsWith("Arrow")) commitGain();
          }}
        />
        <output>{(shownGain / 1_000).toFixed(1)} dB</output>
      </label>
      <button
        ref={resetTrigger}
        type="button"
        className="reset-sample"
        disabled={disabled}
        onClick={() => setConfirmingReset(true)}
      >
        Reset Pad to Defaults
      </button>
      {confirmingReset ? (
        <ConfirmationDialog
          labelledBy="reset-heading"
          returnFocus={resetTrigger.current}
          onCancel={() => setConfirmingReset(false)}
        >
          <h2 id="reset-heading">Reset {padLabel}?</h2>
          <p>Keep the Sample, restore its full range, One Shot, 0.0 dB, and Mute off.</p>
          <div className="confirmation-actions">
            <button type="button" onClick={() => setConfirmingReset(false)}>
              Cancel reset
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirmingReset(false);
                onReset();
              }}
            >
              Confirm reset
            </button>
          </div>
        </ConfirmationDialog>
      ) : null}
    </section>
  );
}
