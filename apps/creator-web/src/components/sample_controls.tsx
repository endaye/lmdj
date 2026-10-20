import {useCallback, useEffect, useRef, useState, type ReactNode} from "react";

import {EqEditor} from "./eq_editor";
import {ModalDialog} from "./modal_dialog";
import {ParameterSlider, type SampleParameterSpec} from "./parameter_slider";
import {SampleParameterEditor} from "./sample_parameter_editor";
import "./sample_controls_layout.css";
import type {
  PadPlayback,
  SampleLoopMode,
  SampleTriggerMode,
} from "../runtime/runtime_types";

export type SampleControlPage = "playback" | "tone" | "pad";

interface SampleControlsProps {
  page: SampleControlPage;
  padLabel: string;
  playback: Readonly<PadPlayback>;
  savedPlayback?: Readonly<PadPlayback>;
  numericEditingContext?: unknown;
  numericEditingDisabled?: boolean;
  onBeginNumericEdit?: () => void;
  onNumericEditorReady?: (cancel: (() => void) | null) => void;
  audioSuspended: boolean;
  disabled?: boolean;
  onPreview: (playback: Readonly<PadPlayback>) => void;
  onCommit: (playback: Readonly<PadPlayback>) => void;
  onCancel?: () => void;
  onReset: () => void;
  padAction?: ReactNode;
}

const NOOP = () => {};

interface NumericEdit {
  parameter: SampleParameterSpec;
  playback: Readonly<PadPlayback>;
  context: unknown;
  page: SampleControlPage;
  padLabel: string;
  audioSuspended: boolean;
  returnFocus: HTMLElement | null;
}

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

// A ramp never renders shorter than the 2 ms declick (lmdj.project.v5 5.2.0).
function formatRamp(ms: number): string {
  return ms <= 2 ? "2 ms" : `${ms} ms`;
}

// Negative is a low-pass and positive a high-pass; |tone| <= 2 is bypassed.
function formatTone(tone: number): string {
  if (tone >= -2 && tone <= 2) return "Off";
  return tone < 0 ? `LP ${-tone}` : `HP ${tone}`;
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
  page,
  padLabel,
  playback,
  savedPlayback = playback,
  numericEditingContext,
  numericEditingDisabled = false,
  onBeginNumericEdit = NOOP,
  onNumericEditorReady,
  audioSuspended,
  disabled = false,
  onPreview,
  onCommit,
  onCancel = NOOP,
  onReset,
  padAction,
}: SampleControlsProps) {
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [numericEdit, setNumericEdit] = useState<NumericEdit | null>(null);
  const numericEditRef = useRef(numericEdit);
  numericEditRef.current = numericEdit;
  const numericPreviewing = useRef(false);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;
  const numericContext = useRef({context: numericEditingContext, page, padLabel,
    audioSuspended, disabled: disabled || numericEditingDisabled});
  numericContext.current = {context: numericEditingContext, page, padLabel,
    audioSuspended, disabled: disabled || numericEditingDisabled};
  const discardNumeric = useCallback(() => {
    if (!numericPreviewing.current) return;
    numericPreviewing.current = false;
    onCancelRef.current();
  }, []);
  const closeNumeric = useCallback(() => {
    discardNumeric();
    numericEditRef.current = null;
    setNumericEdit(null);
  }, [discardNumeric]);
  const currentNumeric = (edit: NumericEdit): boolean =>
    numericEditRef.current === edit &&
    numericContext.current.context === edit.context &&
    numericContext.current.page === edit.page &&
    numericContext.current.padLabel === edit.padLabel &&
    numericContext.current.audioSuspended === edit.audioSuspended &&
    !numericContext.current.disabled;
  const openNumeric = (parameter: SampleParameterSpec) => {
    if (disabled || numericEditingDisabled) return;
    onBeginNumericEdit();
    setNumericEdit({parameter, playback: savedPlayback,
      context: numericEditingContext, page, padLabel, audioSuspended,
      returnFocus: document.activeElement instanceof HTMLElement
        ? document.activeElement : null});
  };
  const resetTrigger = useRef<HTMLButtonElement | null>(null);
  const loop = loopEnabled(playback.triggerMode);
  const primary = primaryEnabled(playback.triggerMode);

  useEffect(() => {
    if (!audioSuspended) return;
    setConfirmingReset(false);
  }, [audioSuspended]);

  useEffect(closeNumeric, [closeNumeric, numericEditingContext, page, padLabel,
    disabled, numericEditingDisabled, audioSuspended]);
  useEffect(() => {
    onNumericEditorReady?.(numericEdit === null ? null : closeNumeric);
    return () => onNumericEditorReady?.(null);
  }, [closeNumeric, onNumericEditorReady, numericEdit]);

  return (
    <section className="sample-controls" aria-label={`${padLabel} Sample controls`}>
      {audioSuspended ? (
        <p className="audio-preview-copy" role="status">Tap a Pad to preview</p>
      ) : null}
      {page === "playback" ? <>
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
          Loop<span aria-hidden="true">: {loop ? "On" : "Off"}</span>
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
          {loop ? "Hold" : "One Shot"}<span aria-hidden="true">: {primary ? "On" : "Off"}</span>
        </button>
        <button
          type="button"
          aria-pressed={playback.muted}
          disabled={disabled}
          onClick={() => onCommit({...playback, muted: !playback.muted})}
        >
          Mute<span aria-hidden="true">: {playback.muted ? "On" : "Off"}</span>
        </button>
        <button
          type="button"
          aria-pressed={playback.reverse}
          disabled={disabled}
          onClick={() => onCommit({...playback, reverse: !playback.reverse})}
        >
          Reverse<span aria-hidden="true">: {playback.reverse ? "On" : "Off"}</span>
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
        onEditValue={openNumeric}
        editValueDisabled={numericEditingDisabled}
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
        onEditValue={openNumeric}
        editValueDisabled={numericEditingDisabled}
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
        onEditValue={openNumeric}
        editValueDisabled={numericEditingDisabled}
        format={formatPan}
        playback={playback}
        disabled={disabled}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
      <ParameterSlider
        label="Attack"
        ariaLabel={`${padLabel} Attack`}
        className="attack-control"
        field="attackMs"
        min={0}
        max={2_000}
        step={1}
        scale={1}
        onEditValue={openNumeric}
        editValueDisabled={numericEditingDisabled}
        format={formatRamp}
        playback={playback}
        disabled={disabled}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
      {/* A one-shot plays through and never plays its release. */}
      <ParameterSlider
        label="Release"
        ariaLabel={`${padLabel} Release`}
        className="release-control"
        field="releaseMs"
        min={0}
        max={4_000}
        step={1}
        scale={1}
        onEditValue={openNumeric}
        editValueDisabled={numericEditingDisabled}
        format={formatRamp}
        playback={playback}
        disabled={disabled || playback.triggerMode === "one_shot"}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
      </> : null}
      {page === "tone" ? <>
      <ParameterSlider
        label="Tone"
        ariaLabel={`${padLabel} Tone`}
        className="tone-control"
        field="tone"
        min={-100}
        max={100}
        step={1}
        scale={1}
        onEditValue={openNumeric}
        editValueDisabled={numericEditingDisabled}
        format={formatTone}
        playback={playback}
        disabled={disabled}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
      <EqEditor
        padLabel={padLabel}
        playback={playback}
        disabled={disabled}
        audioSuspended={audioSuspended}
        onPreview={onPreview}
        onCommit={onCommit}
        onCancel={onCancel}
      />
      </> : null}
      {page === "pad" ? <div className="sample-pad-edit-actions">
        {padAction}
        <button
        ref={resetTrigger}
        type="button"
        className="reset-sample"
        aria-label="Reset Pad to Defaults"
        disabled={disabled}
        onClick={() => setConfirmingReset(true)}
      >
        Reset defaults
      </button></div> : null}
      {confirmingReset ? (
        <ConfirmationDialog
          labelledBy="reset-heading"
          returnFocus={resetTrigger.current}
          onCancel={() => setConfirmingReset(false)}
        >
          <h2 id="reset-heading">Reset {padLabel}?</h2>
          <p>Keep the Sample, restore its full range, One Shot, 0.0 dB, Mute off, and no reverse, pitch, pan, loop, envelope, tone or EQ settings.</p>
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
      {numericEdit !== null ? (
        <SampleParameterEditor
          parameter={numericEdit.parameter}
          padLabel={numericEdit.padLabel}
          value={numericEdit.playback[numericEdit.parameter.field] / numericEdit.parameter.scale}
          returnFocus={numericEdit.returnFocus}
          onPreview={(display) => {
            if (!currentNumeric(numericEdit)) return;
            numericPreviewing.current = true;
            onPreview({...numericEdit.playback,
              [numericEdit.parameter.field]: Math.round(display * numericEdit.parameter.scale)});
          }}
          onCommit={(display) => {
            if (!currentNumeric(numericEdit)) return;
            numericPreviewing.current = false;
            onCommit({...numericEdit.playback,
              [numericEdit.parameter.field]: Math.round(display * numericEdit.parameter.scale)});
          }}
          onDiscard={discardNumeric}
          onClose={closeNumeric}
        />
      ) : null}
    </section>
  );
}
