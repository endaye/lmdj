import {useEffect, useRef, useState, type ReactNode} from "react";

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

interface ContainedBackground {
  element: HTMLElement;
  hadInert: boolean;
  ariaHidden: string | null;
}

interface GainGesture {
  base: Readonly<PadPlayback>;
  latest: Readonly<PadPlayback>;
}

function focusableElements(dialog: HTMLDialogElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
  ));
}

function validFocusTarget(element: HTMLElement | null): element is HTMLElement {
  return element !== null && element.isConnected && element.tabIndex >= 0 &&
    !element.matches(":disabled") &&
    element.closest('[inert], [aria-hidden="true"]') === null;
}

function restoreConfirmationFocus(returnFocus: HTMLElement | null): void {
  if (validFocusTarget(returnFocus)) {
    returnFocus.focus();
    return;
  }
  const fallback = Array.from(document.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
  )).find((element) => validFocusTarget(element) &&
    element.closest(".sample-modal-backdrop") === null);
  fallback?.focus();
}

export function ConfirmationDialog({
  labelledBy,
  returnFocus,
  onCancel,
  children,
}: ConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const contained: ContainedBackground[] = [];
    let branch: HTMLElement = dialog;
    let parent = branch.parentElement;
    while (parent !== null && parent !== document.body) {
      for (const sibling of parent.children) {
        if (sibling === branch || !(sibling instanceof HTMLElement)) continue;
        contained.push({
          element: sibling,
          hadInert: sibling.hasAttribute("inert"),
          ariaHidden: sibling.getAttribute("aria-hidden"),
        });
        sibling.setAttribute("inert", "");
        sibling.setAttribute("aria-hidden", "true");
      }
      branch = parent;
      parent = parent.parentElement;
    }

    if (typeof dialog.showModal === "function") {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      dialog.showModal();
    }
    focusableElements(dialog)[0]?.focus();

    return () => {
      for (const {element, hadInert, ariaHidden} of contained) {
        if (!hadInert) element.removeAttribute("inert");
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      }
      restoreConfirmationFocus(returnFocus);
    };
  }, [returnFocus]);

  return (
    <div
      className="sample-modal-backdrop"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) event.preventDefault();
      }}
    >
      <dialog
        ref={dialogRef}
        open
        className="sample-confirmation"
        aria-labelledby={labelledBy}
        aria-modal="true"
        onCancel={(event) => {
          event.preventDefault();
          cancelRef.current();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            cancelRef.current();
            return;
          }
          if (event.key !== "Tab") return;
          const focusable = focusableElements(event.currentTarget);
          if (focusable.length === 0) {
            event.preventDefault();
            return;
          }
          const first = focusable[0]!;
          const last = focusable.at(-1)!;
          if ((event.shiftKey && document.activeElement === first) ||
            (!event.shiftKey && document.activeElement === last) ||
            !event.currentTarget.contains(document.activeElement)) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
          }
        }}
      >
        {children}
      </dialog>
    </div>
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
