import {useCallback, useEffect, useReducer, useRef, useState} from "react";

import {CAPTURE_SAMPLE_RATE, COMMIT_MAX_FRAMES, CaptureBuffer} from "../capture/capture_buffer";
import {
  CaptureController,
  CapturePermissionError,
  browserCaptureDeps,
  type CaptureListener,
} from "../capture/capture_controller";
import {ModalDialog} from "./modal_dialog";
import {
  captureStopReasonMessage,
  initialCaptureState,
  reduceCapture,
  type CapturePhase,
  type CaptureStopReason,
} from "../state/capture_state";

const WAVEFORM_BINS = 400;
const WAVEFORM_HEIGHT = 96;

// F4 (2026-08-24 decision, option a): a whole-take peak of exactly zero is
// digital silence — the observed symptom of the OS silently switching the
// default input (macOS Continuity rerouting to an iPhone). The commit is
// refused with this explanation and the take is kept. Strict zero only:
// quiet-but-nonzero real takes must never be blocked.
const SILENT_TAKE_MESSAGE =
  "Nothing but digital silence was captured. The input device may have been " +
  "switched by the system. The take is unchanged — discard it to record again.";
// F4 (option b): non-blocking notice when the device set changes mid-take.
const DEVICE_CHANGE_NOTICE =
  "The system's input devices changed during this recording.";

export interface CapturePanelProps {
  padLabel: string;
  onCommit(
    buffer: CaptureBuffer,
    selection: {startFrame: number; frameCount: number},
  ): Promise<
    {kind: "committed"} | {kind: "conflict"; message: string} | {kind: "failed"; message: string}
  >;
  onClose(): void;
  // Element focus returns to when the panel closes (P2-D2); the modal dialog
  // owns the restore so there is exactly one restore path.
  returnFocus?: HTMLElement | null;
  makeController?(listener: CaptureListener): CaptureController;
  stopRequest?: number;
  onPhaseChange?(phase: CapturePhase): void;
  onContinueInSequence?(): void;
  closeAfterResolution?: boolean;
}

function defaultMakeController(listener: CaptureListener): CaptureController {
  return new CaptureController(browserCaptureDeps(), listener);
}

function permissionErrorMessage(error: unknown): string {
  if (error instanceof CapturePermissionError) {
    return `Microphone access failed (${error.message}).`;
  }
  return "Recording could not start.";
}

function secondsLabel(frames: number): string {
  return `${(frames / CAPTURE_SAMPLE_RATE).toFixed(1)} s`;
}

export function CapturePanel({
  padLabel,
  onCommit,
  onClose,
  returnFocus = null,
  makeController,
  stopRequest = 0,
  onPhaseChange,
  onContinueInSequence,
  closeAfterResolution = false,
}: CapturePanelProps) {
  const [state, dispatch] = useReducer(reduceCapture, initialCaptureState);
  const bufferRef = useRef<CaptureBuffer | null>(null);
  // The buffer is now created lazily from the first delivered batch (Finding
  // 1), so "buffer === null" no longer means "not recording" — it can also
  // mean "recording, but no batch has landed yet". This ref is the actual
  // recording guard onBatch uses to no-op once capture has been stopped.
  const recordingRef = useRef(false);
  const controllerRef = useRef<CaptureController | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // The current phase's primary action (idle/permission-error: Record;
  // recording: Stop; trimming/commit-error: Commit) and the dialog element
  // itself, which is the focus fallback for phases with no primary action
  // (requesting-permission, committing).
  const primaryRef = useRef<HTMLButtonElement | null>(null);
  const dialogElementRef = useRef<HTMLDialogElement | null>(null);
  const resolvePrimaryFocus = useCallback(() => primaryRef.current, []);
  // F4 (option b): the capture track's label as the controller reported it
  // when start() resolved; "" renders as the "Default input" placeholder.
  const [inputLabel, setInputLabel] = useState("");
  const [deviceChanged, setDeviceChanged] = useState(false);
  // F4 (option a): set when Commit was refused for a digitally silent take;
  // cleared by discard and by starting a new recording.
  const [silenceRefused, setSilenceRefused] = useState(false);

  const requestStop = useCallback((reason: CaptureStopReason) => {
    recordingRef.current = false;
    dispatch({kind: "stop", reason});
    const controller = controllerRef.current;
    controllerRef.current = null;
    if (controller !== null) {
      void controller.stop().catch(() => {});
    }
  }, []);

  useEffect(() => {
    onPhaseChange?.(state.phase);
  }, [onPhaseChange, state.phase]);

  const priorStopRequest = useRef(stopRequest);
  useEffect(() => {
    if (priorStopRequest.current === stopRequest) return;
    priorStopRequest.current = stopRequest;
    if (state.phase === "recording") requestStop("user");
  }, [requestStop, state.phase, stopRequest]);

  // Single-owner lifecycle: whatever controller is active when this component
  // unmounts must be stopped exactly once, even if that happens mid-recording.
  useEffect(() => () => {
    recordingRef.current = false;
    const controller = controllerRef.current;
    controllerRef.current = null;
    if (controller !== null) {
      void controller.stop().catch(() => {});
    }
  }, []);

  // S8B-D5: blur/hidden only stop an in-progress recording, and the listeners
  // must not exist outside the recording phase.
  useEffect(() => {
    if (state.phase !== "recording") return;
    const onBlur = () => requestStop("blur");
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") requestStop("hidden");
    };
    window.addEventListener("blur", onBlur);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [state.phase, requestStop]);

  // F4 (option b): a device-set change mid-recording is the observable half
  // of the silent-input-switch failure mode, so surface it as a non-blocking
  // notice. Scoped to the recording phase exactly like the blur/hidden
  // listeners above; mediaDevices is absent in some contexts (jsdom, older
  // browsers), so availability is guarded.
  useEffect(() => {
    if (state.phase !== "recording") return;
    const mediaDevices = navigator.mediaDevices as MediaDevices | undefined;
    if (mediaDevices === undefined) return;
    const onDeviceChange = () => setDeviceChanged(true);
    mediaDevices.addEventListener("devicechange", onDeviceChange);
    return () => mediaDevices.removeEventListener("devicechange", onDeviceChange);
  }, [state.phase]);

  // P2-D2: opening the panel focuses the phase's primary action (handled by
  // the dialog's resolveInitialFocus), and a phase transition that unmounts
  // the focused control moves focus to the new phase's primary action — focus
  // must never drop to <body>. Focus resting on a control that survived the
  // transition (e.g. Close or a selection slider) is left where it is.
  const previousPhase = useRef(state.phase);
  useEffect(() => {
    if (previousPhase.current === state.phase) return;
    previousPhase.current = state.phase;
    const active = document.activeElement;
    // Real browsers drop focus to <body> when the focused control unmounts;
    // jsdom instead lands it on whatever was inserted at the same position
    // (here the disabled Crop button), so a disabled active element counts as
    // dropped too.
    const focusDropped = !(active instanceof HTMLElement) ||
      active === document.body || !active.isConnected ||
      active.matches(":disabled");
    const onDialogFallback = active === dialogElementRef.current;
    if (focusDropped || onDialogFallback) {
      (primaryRef.current ?? dialogElementRef.current)?.focus();
    }
  }, [state.phase]);

  // Paint the growing waveform straight from the capture buffer ref; the
  // buffer itself never lives in React state (S8B design note #4). Recording
  // shows the complete take, while trimming and commit retry zoom the current
  // selection at the same fixed canvas resolution (CR-D2).
  //
  // The canvas element is unmounted during "committing" (which renders only a
  // status paragraph) and remounted in "commit-error" (and again on the
  // recording -> trimming transition). Neither frameCount nor peak need to
  // change across those transitions — peak is already 0 by the time trimming
  // starts, and neither commit nor commit-failed touch frameCount — so
  // `state.phase` must be in the dependency array too, or the effect never
  // re-runs against the freshly (re)mounted canvas and the user is left
  // looking at a blank waveform (S8B-D6).
  useEffect(() => {
    const canvas = canvasRef.current;
    const buffer = bufferRef.current;
    if (canvas === null || buffer === null || buffer.frameCount === 0) return;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return;
    const selectionView = state.phase === "trimming" || state.phase === "commit-error";
    const startFrame = selectionView ? state.selectionStart : 0;
    const frameCount = selectionView ? state.selectionFrames : buffer.frameCount;
    const bins = buffer.envelope(WAVEFORM_BINS, startFrame, frameCount);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const mid = canvas.height / 2;
    for (let i = 0; i < bins.length; i += 1) {
      const magnitude = bins[i] ?? 0;
      const barHeight = Math.max(1, magnitude * canvas.height);
      ctx.fillRect(i, mid - barHeight / 2, 1, barHeight);
    }
  }, [
    state.phase,
    state.frameCount,
    state.peak,
    state.selectionStart,
    state.selectionFrames,
  ]);

  const handleRecord = async () => {
    // Single-owner lifecycle: the ref (not the reducer phase, which can lag a
    // render behind a rapid double click) is the guard against ever owning
    // two controllers at once.
    if (controllerRef.current !== null) return;
    dispatch({kind: "record"});
    bufferRef.current = null;
    setInputLabel("");
    setDeviceChanged(false);
    setSilenceRefused(false);
    const listener: CaptureListener = {
      onBatch(channels, peak) {
        // The delivered audio is the single authority on channel width
        // (Finding 1): the buffer is sized from the first real batch, never
        // from a value inferred ahead of time.
        if (!recordingRef.current) return;
        if (bufferRef.current === null) {
          bufferRef.current = new CaptureBuffer(channels.length === 2 ? 2 : 1);
        }
        const buffer = bufferRef.current;
        try {
          buffer.append(channels);
        } catch {
          // A shape mismatch here means the delivered audio disagreed with
          // the buffer it was sized from. Stopping the capture releases the
          // microphone; letting this escape into the event handler would
          // strand it live with the UI stuck in "recording".
          requestStop("device-lost");
          return;
        }
        dispatch({kind: "frames", frames: buffer.frameCount, peak});
        if (buffer.atCapacity) requestStop("capacity");
      },
      onEnded(reason) {
        requestStop(reason);
      },
    };
    const controller = (makeController ?? defaultMakeController)(listener);
    controllerRef.current = controller;
    try {
      await controller.start();
      recordingRef.current = true;
      setInputLabel(controller.inputLabel);
      dispatch({kind: "granted"});
    } catch (error) {
      controllerRef.current = null;
      dispatch({kind: "denied", message: permissionErrorMessage(error)});
    }
  };

  const handleStop = () => requestStop("user");

  // Finding 3: Close is rendered in every phase including "recording"; it
  // must stop any in-progress capture itself rather than relying on the
  // unmount cleanup, which never runs if the parent hides the panel instead
  // of unmounting it (single-owner lifecycle — the microphone must never be
  // left live with no owner able to stop it).
  const handleClose = () => {
    if (controllerRef.current !== null) {
      requestStop("user");
    }
    onClose();
  };

  // The reducer is the single source of truth for what a selection may be
  // (COMMIT_MAX_FRAMES, in-range); the sliders below only need correct
  // min/max attributes so the browser's own range-input clamp never lets the
  // user pick an out-of-range value in the first place (mirrors
  // waveform_editor.tsx's start/end handle bounds).
  const handleSelectStart = (start: number) => {
    dispatch({kind: "select", start: Math.round(start), frames: state.selectionFrames});
  };

  const handleSelectFrames = (frames: number) => {
    dispatch({kind: "select", start: state.selectionStart, frames: Math.round(frames)});
  };

  const handleDiscard = () => {
    bufferRef.current = null;
    setSilenceRefused(false);
    dispatch({kind: "discard"});
    if (closeAfterResolution) onClose();
  };

  const handleCrop = () => {
    const buffer = bufferRef.current;
    if (buffer === null) return;
    buffer.crop(state.selectionStart, state.selectionFrames);
    dispatch({kind: "crop", frames: buffer.frameCount});
  };

  const handleCommit = async () => {
    const buffer = bufferRef.current;
    if (buffer === null) return;
    // F4 (option a): refuse to commit a digitally silent take. The gate reads
    // the WHOLE take's peak — never the current selection — and only strict
    // zero refuses, so a quiet-but-nonzero take always commits. The take is
    // kept intact and the phase does not change; the operator can re-record
    // (via Discard) or keep editing.
    if (buffer.peak === 0) {
      setSilenceRefused(true);
      return;
    }
    const selection = {startFrame: state.selectionStart, frameCount: state.selectionFrames};
    dispatch({kind: "commit"});
    const result = await onCommit(buffer, selection);
    if (result.kind === "committed") {
      bufferRef.current = null;
      dispatch({kind: "committed"});
      if (closeAfterResolution) onClose();
    } else {
      dispatch({
        kind: "commit-failed",
        message: result.message,
        conflict: result.kind === "conflict",
      });
    }
  };

  // P2-D1: the panel is a viewport-anchored modal with fixed outer geometry.
  // Three fixed regions — header, a fixed-height waveform/meter view that is
  // always rendered, and a bottom action row — so entering "recording" only
  // swaps region contents and "Stop" sits exactly where "Record into Pad N"
  // was. Phase details (messages, selection sliders) scroll inside the
  // content region under the view.
  const renderView = () => {
    switch (state.phase) {
      case "recording":
        return (
          <>
            <p>{secondsLabel(state.frameCount)} recorded</p>
            <meter
              min={0}
              max={1}
              value={state.peak}
              aria-label={`${padLabel} input level`}
            />
            <canvas
              ref={canvasRef}
              role="img"
              aria-label={`${padLabel} capture waveform`}
              data-frame-count={state.frameCount}
              width={WAVEFORM_BINS}
              height={WAVEFORM_HEIGHT}
            />
          </>
        );
      case "trimming":
      case "commit-error":
        return (
          <>
            <p>{secondsLabel(state.frameCount)} captured</p>
            <canvas
              ref={canvasRef}
              role="img"
              aria-label={`${padLabel} capture waveform`}
              data-frame-count={state.frameCount}
              width={WAVEFORM_BINS}
              height={WAVEFORM_HEIGHT}
            />
          </>
        );
      case "requesting-permission":
        return <p role="status">Requesting microphone access…</p>;
      case "committing":
        return <p role="status">Committing…</p>;
      case "idle":
      case "permission-error":
        return (
          <p className="capture-panel-view-placeholder">
            Ready to record into {padLabel}
          </p>
        );
    }
  };

  // F4 (option b): the label the browser gave the capture track, or the
  // placeholder when it withheld one (empty string).
  const inputLabelText = inputLabel === "" ? "Default input" : inputLabel;

  const renderDetails = () => {
    switch (state.phase) {
      case "permission-error":
        return <p role="alert">{state.errorMessage}</p>;
      case "recording":
        return (
          <>
            <p>Input: {inputLabelText}</p>
            {deviceChanged && <p role="status">{DEVICE_CHANGE_NOTICE}</p>}
          </>
        );
      case "trimming":
      case "commit-error": {
        const maxSelectionFrames = Math.min(
          COMMIT_MAX_FRAMES,
          state.frameCount - state.selectionStart,
        );
        return (
          <>
            <p>Input: {inputLabelText}</p>
            {silenceRefused && <p role="alert">{SILENT_TAKE_MESSAGE}</p>}
            {captureStopReasonMessage(state.stopReason) !== null && (
              <p>{captureStopReasonMessage(state.stopReason)}</p>
            )}
            {state.phase === "commit-error" && (
              <p role="alert">{state.errorMessage}</p>
            )}
            <label>
              <span>Selection start</span>
              <input
                type="range"
                min={0}
                max={Math.max(0, state.frameCount - state.selectionFrames)}
                step={1}
                value={state.selectionStart}
                aria-label={`${padLabel} Selection start`}
                onChange={(event) =>
                  handleSelectStart(event.currentTarget.valueAsNumber)}
              />
            </label>
            <label>
              <span>Selection length</span>
              <input
                type="range"
                min={1}
                max={Math.max(1, maxSelectionFrames)}
                step={1}
                value={state.selectionFrames}
                aria-label={`${padLabel} Selection length`}
                onChange={(event) =>
                  handleSelectFrames(event.currentTarget.valueAsNumber)}
              />
            </label>
          </>
        );
      }
      default:
        return null;
    }
  };

  const renderActions = () => {
    switch (state.phase) {
      case "idle":
      case "permission-error":
        return (
          <button
            ref={primaryRef}
            type="button"
            onClick={() => void handleRecord()}
          >
            Record into {padLabel}
          </button>
        );
      case "recording":
        return (
          <>
            <button ref={primaryRef} type="button" onClick={handleStop}>Stop</button>
            {onContinueInSequence === undefined ? null : (
              <button type="button" onClick={onContinueInSequence}>
                Continue in Sequence
              </button>
            )}
          </>
        );
      case "trimming":
      case "commit-error":
        return (
          <>
            <button
              type="button"
              disabled={state.selectionStart === 0 &&
                        state.selectionFrames === state.frameCount}
              onClick={handleCrop}
            >
              Crop to selection
            </button>
            <button
              ref={primaryRef}
              type="button"
              onClick={() => void handleCommit()}
            >
              Commit
            </button>
            <button type="button" onClick={handleDiscard}>Discard</button>
          </>
        );
      default:
        return null;
    }
  };

  return (
    <ModalDialog
      label={`${padLabel} Pad Capture`}
      returnFocus={returnFocus}
      onCancel={handleClose}
      dialogClassName="capture-panel-dialog"
      resolveInitialFocus={resolvePrimaryFocus}
      dialogRef={dialogElementRef}
    >
      <div className="capture-panel-header">
        <h2>{padLabel} Capture</h2>
        <button type="button" onClick={handleClose}>Close</button>
      </div>
      <div className="capture-panel-content">
        <div className="capture-panel-view">{renderView()}</div>
        {renderDetails()}
      </div>
      <div className="capture-panel-actions">{renderActions()}</div>
    </ModalDialog>
  );
}
