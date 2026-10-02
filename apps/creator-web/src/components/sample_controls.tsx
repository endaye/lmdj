import {useEffect, useRef, useState, type ReactNode} from "react";

import {ModalDialog} from "./modal_dialog";
import {ParameterSlider} from "./parameter_slider";
import type {
  PadPlayback,
  SampleLoopMode,
  SampleTriggerMode,
} from "../runtime/runtime_types";

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

function formatPitch(cents: number): string {
  const semitones = cents / 100;
  return `${semitones > 0 ? "+" : ""}${semitones.toFixed(1)} st`;
}

function formatPan(pan: number): string {
  if (pan === 0) return "C";
  return pan < 0 ? `L${-pan}` : `R${pan}`;
}

// Ping-pong has no seam to blend, so choosing it clears the crossfade.
function withLoopMode(
  playback: Readonly<PadPlayback>,
  loopMode: SampleLoopMode,
): Readonly<PadPlayback> {
  return loopMode === "ping_pong"
    ? {...playback, loopMode, loopCrossfadeFrames: 0}
    : {...playback, loopMode};
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
  const loop = loopEnabled(playback.triggerMode);
  const primary = primaryEnabled(playback.triggerMode);

  useEffect(() => {
    if (!audioSuspended) return;
    setConfirmingReset(false);
  }, [audioSuspended]);

  return (
    <section className="sample-controls" aria-label={`${padLabel} Sample controls`}>
      {audioSuspended ? (
        <p className="audio-preview-copy" role="status">Tap a Pad to preview</p>
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
        <button
          type="button"
          aria-pressed={playback.reverse}
          disabled={disabled}
          onClick={() => onCommit({...playback, reverse: !playback.reverse})}
        >
          Reverse
        </button>
      </div>
      {loop ? (
        <div className="sample-loop-mode" role="group" aria-label={`${padLabel} Loop mode`}>
          <button
            type="button"
            aria-pressed={playback.loopMode === "forward"}
            disabled={disabled}
            onClick={() => {
              if (playback.loopMode !== "forward") {
                onCommit(withLoopMode(playback, "forward"));
              }
            }}
          >
            Forward
          </button>
          <button
            type="button"
            aria-pressed={playback.loopMode === "ping_pong"}
            disabled={disabled}
            onClick={() => {
              if (playback.loopMode !== "ping_pong") {
                onCommit(withLoopMode(playback, "ping_pong"));
              }
            }}
          >
            Ping-pong
          </button>
        </div>
      ) : null}
      <ParameterSlider
        label="Volume"
        ariaLabel={`${padLabel} Volume`}
        className="volume-control"
        field="gainMillidb"
        min={-60}
        max={6}
        step={0.1}
        scale={1_000}
        format={(gain) => `${(gain / 1_000).toFixed(1)} dB`}
        playback={playback}
        disabled={disabled}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
      <ParameterSlider
        label="Pitch"
        ariaLabel={`${padLabel} Pitch`}
        className="pitch-control"
        field="pitchCents"
        min={-24}
        max={24}
        step={0.1}
        scale={100}
        format={formatPitch}
        playback={playback}
        disabled={disabled}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
      <ParameterSlider
        label="Pan"
        ariaLabel={`${padLabel} Pan`}
        className="pan-control"
        field="pan"
        min={-100}
        max={100}
        step={1}
        scale={1}
        format={formatPan}
        playback={playback}
        disabled={disabled}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
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
          <p>Keep the Sample, restore its full range, One Shot, 0.0 dB, Mute off, and no reverse, pitch, pan or loop settings.</p>
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
