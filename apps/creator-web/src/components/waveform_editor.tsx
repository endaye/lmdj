import {useEffect, useRef, useState} from "react";

import type {
  PadPlayback,
  SampleMetadata,
  WaveformBucket,
  WaveformEnvelope,
} from "../runtime/runtime_types";
import {
  fitSampleViewport,
  panSampleViewport,
  zoomSampleViewport,
  type SampleViewport,
} from "../state/sample_state";

const SVG_WIDTH = 400;
const SVG_HEIGHT = 160;
const ZERO_LINE = SVG_HEIGHT / 2;
const PEAK_HEIGHT = 64;
const GRIP_HIT_PX = 20;
const GRIP_BAR_PX = 20;

interface WaveformEditorProps {
  padLabel: string;
  envelope: Readonly<WaveformEnvelope> | null;
  metadata: Readonly<SampleMetadata>;
  projectRevision: number;
  playback: Readonly<PadPlayback>;
  playheadFrame: number | null;
  disabled?: boolean;
  onPreview: (playback: Readonly<PadPlayback>) => void;
  onCommit: (playback: Readonly<PadPlayback>) => void;
  onCancel: () => void;
  onQueryWaveform?: (
    viewport: Readonly<SampleViewport>,
  ) => Promise<Readonly<WaveformEnvelope> | null>;
}

interface EditGesture {
  base: Readonly<PadPlayback>;
  latest: Readonly<PadPlayback>;
}

interface GripDrag {
  kind: "start" | "end";
  pointerId: number;
  grabOffset: number;
}

interface AcceptedViewportEnvelope {
  readonly viewport: Readonly<SampleViewport>;
  readonly envelope: Readonly<WaveformEnvelope>;
}

function sameViewport(
  left: Readonly<SampleViewport>,
  right: Readonly<SampleViewport>,
): boolean {
  return left.sourceFrames === right.sourceFrames &&
    left.startFrame === right.startFrame && left.endFrame === right.endFrame;
}

function validEnvelope(
  value: Readonly<WaveformEnvelope> | null,
): value is Readonly<WaveformEnvelope> {
  if (value === null || value.algorithmVersion !== 1 ||
    !Number.isSafeInteger(value.projectRevision) || value.projectRevision < 0 ||
    !Number.isSafeInteger(value.metadata.sourceFrames) ||
    value.metadata.sourceFrames <= 0 ||
    ![44_100, 48_000].includes(value.metadata.sampleRate) ||
    ![1, 2].includes(value.metadata.channels) ||
    !Array.isArray(value.buckets) || value.buckets.length === 0) {
    return false;
  }
  let previousEnd = -1;
  return value.buckets.every((bucket) => {
    const valid = Number.isSafeInteger(bucket.startFrame) &&
      Number.isSafeInteger(bucket.endFrame) &&
      Number.isSafeInteger(bucket.peakMagnitude) &&
      bucket.startFrame >= 0 && bucket.startFrame < bucket.endFrame &&
      bucket.endFrame <= value.metadata.sourceFrames &&
      bucket.peakMagnitude >= 0 && bucket.peakMagnitude <= 32_768 &&
      bucket.startFrame >= previousEnd;
    previousEnd = bucket.endFrame;
    return valid;
  });
}

function validMetadata(
  value: Readonly<SampleMetadata>,
): value is Readonly<SampleMetadata> {
  return Number.isSafeInteger(value.sourceFrames) && value.sourceFrames > 0 &&
    [44_100, 48_000].includes(value.sampleRate) && [1, 2].includes(value.channels);
}

function waveformPath(
  buckets: readonly Readonly<WaveformBucket>[],
  viewport: Readonly<SampleViewport>,
): string {
  const span = viewport.endFrame - viewport.startFrame;
  const frameToX = (frame: number) => Math.round(
    (Math.min(viewport.endFrame, Math.max(viewport.startFrame, frame)) -
      viewport.startFrame) * SVG_WIDTH / span,
  );
  const top = buckets.flatMap((bucket) => {
    const y = Math.round(ZERO_LINE - bucket.peakMagnitude * PEAK_HEIGHT / 32_768);
    return [
      {x: frameToX(bucket.startFrame), y},
      {x: frameToX(bucket.endFrame), y},
    ];
  });
  const lower = top.toReversed().map(({x, y}) => ({x, y: SVG_HEIGHT - y}));
  return [...top, ...lower].map(({x, y}, index) =>
    `${index === 0 ? "M" : "L"} ${x} ${y}`
  ).join(" ") + " Z";
}

function samePlayback(left: PadPlayback, right: PadPlayback): boolean {
  return left.trimStartFrame === right.trimStartFrame &&
    left.trimEndFrame === right.trimEndFrame &&
    left.triggerMode === right.triggerMode &&
    left.gainMillidb === right.gainMillidb &&
    left.muted === right.muted;
}

function seconds(frame: number, sampleRate: number): string {
  return (frame / sampleRate).toFixed(3);
}

export function WaveformEditor({
  padLabel,
  envelope,
  metadata,
  projectRevision,
  playback,
  playheadFrame,
  disabled = false,
  onPreview,
  onCommit,
  onCancel,
  onQueryWaveform,
}: WaveformEditorProps) {
  const [viewportEnvelope, setViewportEnvelope] =
    useState<AcceptedViewportEnvelope | null>(null);
  const metadataIsValid = validMetadata(metadata);
  const sourceFrames = metadataIsValid ? metadata.sourceFrames : 1;
  const sampleRate = metadataIsValid ? metadata.sampleRate : 48_000;
  const [viewport, setViewport] = useState<Readonly<SampleViewport>>(() =>
    fitSampleViewport(sourceFrames)
  );
  const activeEnvelope = viewportEnvelope !== null &&
      sameViewport(viewportEnvelope.viewport, viewport)
    ? viewportEnvelope.envelope
    : envelope;
  const envelopeIsValid = metadataIsValid && validEnvelope(activeEnvelope) &&
    activeEnvelope.projectRevision === projectRevision &&
    activeEnvelope.metadata.sourceFrames === metadata.sourceFrames &&
    activeEnvelope.metadata.sampleRate === metadata.sampleRate &&
    activeEnvelope.metadata.channels === metadata.channels;
  const [draftPlayback, setDraftPlayback] = useState<Readonly<PadPlayback> | null>(null);
  const gesture = useRef<EditGesture | null>(null);
  const gesturePointerId = useRef<number | null>(null);
  const gripDrag = useRef<GripDrag | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const commitGestureRef = useRef<() => void>(() => {});
  const cancelGestureRef = useRef<() => void>(() => {});
  const queryEpoch = useRef(0);
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;
  const effective = draftPlayback ?? playback;
  const resolvedEnd = effective.trimEndFrame ?? sourceFrames;

  useEffect(() => () => {
    queryEpoch.current += 1;
    gesturePointerId.current = null;
    if (gesture.current !== null) {
      gesture.current = null;
      cancelRef.current();
    }
  }, []);

  useEffect(() => {
    setViewport((current) => current.sourceFrames === sourceFrames
      ? current
      : fitSampleViewport(sourceFrames));
  }, [sourceFrames]);

  useEffect(() => {
    queryEpoch.current += 1;
    setViewportEnvelope(null);
  }, [
    projectRevision,
    metadata.sourceFrames,
    metadata.sampleRate,
    metadata.channels,
  ]);

  useEffect(() => {
    setViewportEnvelope((current) => {
      if (current === null || envelope === null ||
        current.envelope.projectRevision === envelope.projectRevision) {
        return current;
      }
      return null;
    });
  }, [envelope]);

  const beginGesture = () => {
    if (gesture.current === null) {
      gesture.current = {base: playback, latest: playback};
    }
  };

  const preview = (kind: "start" | "end", requestedFrame: number) => {
    if (!Number.isFinite(requestedFrame)) return;
    beginGesture();
    const current = gesture.current?.latest ?? playback;
    const currentEnd = current.trimEndFrame ?? sourceFrames;
    const frame = kind === "start"
      ? Math.min(currentEnd - 1, Math.max(0, requestedFrame))
      : Math.min(sourceFrames, Math.max(current.trimStartFrame + 1, requestedFrame));
    const next: Readonly<PadPlayback> = kind === "start"
      ? {...current, trimStartFrame: frame}
      : {...current, trimEndFrame: frame};
    if (samePlayback(current, next)) return;
    gesture.current = {base: gesture.current!.base, latest: next};
    setDraftPlayback(next);
    onPreview(next);
  };

  const commitGesture = () => {
    const current = gesture.current;
    if (current === null) return;
    gesturePointerId.current = null;
    gripDrag.current = null;
    gesture.current = null;
    setDraftPlayback(null);
    if (!samePlayback(current.base, current.latest)) onCommit(current.latest);
  };

  const cancelGesture = () => {
    if (gesture.current === null) return;
    gesturePointerId.current = null;
    gripDrag.current = null;
    gesture.current = null;
    setDraftPlayback(null);
    onCancel();
  };
  commitGestureRef.current = commitGesture;
  cancelGestureRef.current = cancelGesture;

  useEffect(() => {
    const finish = (event: PointerEvent) => {
      if (gesturePointerId.current === event.pointerId) {
        commitGestureRef.current();
      }
    };
    const cancel = (event: PointerEvent) => {
      if (gesturePointerId.current === event.pointerId) {
        cancelGestureRef.current();
      }
    };
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", cancel);
    return () => {
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
    };
  }, []);

  const keyboardEdit = (
    event: React.KeyboardEvent<HTMLInputElement>,
    kind: "start" | "end",
  ) => {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelGesture();
      return;
    }
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const increment = event.shiftKey ? Math.round(sampleRate / 100) : 1;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    const current = gesture.current?.latest ?? effective;
    preview(
      kind,
      (kind === "start" ? current.trimStartFrame : current.trimEndFrame ?? sourceFrames) +
        direction * increment,
    );
  };

  const frameToX = (frame: number): number => {
    const clamped = Math.min(viewport.endFrame, Math.max(viewport.startFrame, frame));
    return Math.round(
      (clamped - viewport.startFrame) * SVG_WIDTH /
        (viewport.endFrame - viewport.startFrame),
    );
  };
  const startX = frameToX(effective.trimStartFrame);
  const endX = frameToX(resolvedEnd);
  const visibleBuckets = envelopeIsValid
    ? activeEnvelope.buckets.filter((bucket) =>
        bucket.endFrame > viewport.startFrame && bucket.startFrame < viewport.endFrame
      )
    : [];

  const applyViewport = (next: Readonly<SampleViewport>) => {
    setViewportEnvelope(null);
    setViewport(next);
    if (onQueryWaveform === undefined) return;
    const epoch = ++queryEpoch.current;
    void onQueryWaveform(next).then(
      (queried) => {
        if (queryEpoch.current !== epoch || queried === null ||
          !validEnvelope(queried) ||
          queried.metadata.sourceFrames !== next.sourceFrames ||
          queried.buckets.some((bucket) =>
            bucket.startFrame < next.startFrame || bucket.endFrame > next.endFrame
          )) {
          return;
        }
        setViewportEnvelope({viewport: next, envelope: queried});
      },
      () => {},
    );
  };

  const capturePointer = (event: React.PointerEvent<HTMLElement>) => {
    gesturePointerId.current = event.pointerId;
    if (typeof event.currentTarget.setPointerCapture === "function") {
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // The window-level release listener remains authoritative fallback.
      }
    }
  };

  const frameAtClientX = (clientX: number): number => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect === undefined || rect.width <= 0) return Number.NaN;
    const fraction = (clientX - rect.left) / rect.width;
    return viewport.startFrame +
      fraction * (viewport.endFrame - viewport.startFrame);
  };

  const gripPointerDown = (
    event: React.PointerEvent<HTMLElement>,
    kind: "start" | "end",
  ) => {
    if (disabled || !envelopeIsValid || event.button !== 0) return;
    event.preventDefault();
    const handleFrame = kind === "start" ? effective.trimStartFrame : resolvedEnd;
    gripDrag.current = {
      kind,
      pointerId: event.pointerId,
      grabOffset: handleFrame - frameAtClientX(event.clientX),
    };
    capturePointer(event);
    beginGesture();
  };

  const gripPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const drag = gripDrag.current;
    if (drag === null || drag.pointerId !== event.pointerId) return;
    // The handle follows the pointer delta from the press, never the pointer
    // position itself, so a press can never jump a trim point.
    preview(
      drag.kind,
      Math.round(frameAtClientX(event.clientX) + drag.grabOffset),
    );
  };

  const gripsInteractive = !disabled && envelopeIsValid &&
    visibleBuckets.length > 0;
  const startPct = startX / SVG_WIDTH * 100;
  const endPct = endX / SVG_WIDTH * 100;
  const midPct = (startPct + endPct) / 2;
  const gripZone = (handlePct: number, boundaryPct: number, isStart: boolean) => ({
    left: isStart
      ? `max(0px, calc(${handlePct}% - ${GRIP_HIT_PX}px))`
      : `max(${boundaryPct}%, calc(${handlePct}% - ${GRIP_HIT_PX}px))`,
    right: isStart
      ? `calc(100% - min(${boundaryPct}%, calc(${handlePct}% + ${GRIP_HIT_PX}px)))`
      : `max(0px, calc(100% - ${handlePct}% - ${GRIP_HIT_PX}px))`,
  });

  return (
    <section
      className="waveform-editor"
      aria-label={`${padLabel} waveform editor`}
      data-waveform-viewport
      data-viewport-start={viewport.startFrame}
      data-viewport-end={viewport.endFrame}
    >
      <div className="waveform-canvas" ref={canvasRef}>
        {envelopeIsValid && visibleBuckets.length > 0 ? (
          <svg
            viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
            role="img"
            aria-label={`${padLabel} mirrored waveform`}
            preserveAspectRatio="none"
          >
            <line data-zero-line x1="0" x2={SVG_WIDTH} y1={ZERO_LINE} y2={ZERO_LINE} />
            <path data-waveform d={waveformPath(visibleBuckets, viewport)} />
            <rect
              data-selection-mask="before"
              x="0"
              y="0"
              width={startX}
              height={SVG_HEIGHT}
            />
            <rect
              data-selection-mask="after"
              x={endX}
              y="0"
              width={SVG_WIDTH - endX}
              height={SVG_HEIGHT}
            />
            <line data-handle="start" x1={startX} x2={startX} y1="0" y2={SVG_HEIGHT} />
            <line data-handle="end" x1={endX} x2={endX} y1="0" y2={SVG_HEIGHT} />
            {playheadFrame === null ? null : (
              <line
                data-playhead
                aria-hidden="true"
                x1={frameToX(playheadFrame)}
                x2={frameToX(playheadFrame)}
                y1="0"
                y2={SVG_HEIGHT}
              />
            )}
          </svg>
        ) : <p className="waveform-unavailable">Waveform unavailable</p>}
        {envelopeIsValid && visibleBuckets.length > 0 ? (
          <>
            {gripsInteractive ? (
              <div
                className="waveform-grip-zone"
                data-grip-zone="start"
                aria-hidden="true"
                style={gripZone(startPct, midPct, true)}
                onPointerDown={(event) => gripPointerDown(event, "start")}
                onPointerMove={gripPointerMove}
                onPointerUp={commitGesture}
                onPointerCancel={cancelGesture}
              />
            ) : null}
            <span
              className="waveform-grip-bar"
              data-grip="start"
              aria-hidden="true"
              style={{left: `calc(${startPct}% - ${GRIP_BAR_PX / 2}px)`}}
            />
            {gripsInteractive ? (
              <div
                className="waveform-grip-zone"
                data-grip-zone="end"
                aria-hidden="true"
                style={gripZone(endPct, midPct, false)}
                onPointerDown={(event) => gripPointerDown(event, "end")}
                onPointerMove={gripPointerMove}
                onPointerUp={commitGesture}
                onPointerCancel={cancelGesture}
              />
            ) : null}
            <span
              className="waveform-grip-bar"
              data-grip="end"
              aria-hidden="true"
              style={{left: `calc(${endPct}% - ${GRIP_BAR_PX / 2}px)`}}
            />
          </>
        ) : null}
        <input
          className="waveform-handle waveform-start-handle"
          type="range"
          min="0"
          max={Math.max(0, resolvedEnd - 1)}
          step="1"
          value={effective.trimStartFrame}
          disabled={disabled || !envelopeIsValid}
          aria-label={`${padLabel} Start — ${seconds(effective.trimStartFrame, sampleRate)} s`}
          style={{left: `calc(${startPct}% - 22px)`}}
          onChange={(event) => preview("start", event.currentTarget.valueAsNumber)}
          onKeyDown={(event) => keyboardEdit(event, "start")}
          onKeyUp={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") commitGesture();
          }}
        />
        <input
          className="waveform-handle waveform-end-handle"
          type="range"
          min={Math.min(sourceFrames, effective.trimStartFrame + 1)}
          max={sourceFrames}
          step="1"
          value={resolvedEnd}
          disabled={disabled || !envelopeIsValid}
          aria-label={`${padLabel} End — ${seconds(resolvedEnd, sampleRate)} s`}
          style={{left: `calc(${endPct}% - 22px)`}}
          onChange={(event) => preview("end", event.currentTarget.valueAsNumber)}
          onKeyDown={(event) => keyboardEdit(event, "end")}
          onKeyUp={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") commitGesture();
          }}
        />
      </div>
      <div className="waveform-values">
        <label className="waveform-value-card">
          <span>START / TAP TO EDIT</span>
          <input
            className="sample-value-input"
            type="number"
            min="0"
            max={(resolvedEnd - 1) / sampleRate}
            step={1 / sampleRate}
            value={effective.trimStartFrame / sampleRate}
            disabled={disabled || !envelopeIsValid}
            aria-label={`${padLabel} Start time (seconds)`}
            onFocus={beginGesture}
            onChange={(event) => preview(
              "start",
              Math.round(event.currentTarget.valueAsNumber * sampleRate),
            )}
            onBlur={commitGesture}
            onKeyDown={(event) => keyboardEdit(event, "start")}
            onKeyUp={(event) => {
              if (event.key === "ArrowLeft" || event.key === "ArrowRight") commitGesture();
            }}
          />
          <small>s</small>
        </label>
        <label className="waveform-value-card">
          <span>END / TAP TO EDIT</span>
          <input
            className="sample-value-input"
            type="number"
            min={(effective.trimStartFrame + 1) / sampleRate}
            max={sourceFrames / sampleRate}
            step={1 / sampleRate}
            value={resolvedEnd / sampleRate}
            disabled={disabled || !envelopeIsValid}
            aria-label={`${padLabel} End time (seconds)`}
            onFocus={beginGesture}
            onChange={(event) => preview(
              "end",
              Math.round(event.currentTarget.valueAsNumber * sampleRate),
            )}
            onBlur={commitGesture}
            onKeyDown={(event) => keyboardEdit(event, "end")}
            onKeyUp={(event) => {
              if (event.key === "ArrowLeft" || event.key === "ArrowRight") commitGesture();
            }}
          />
          <small>s</small>
        </label>
      </div>
      <div className="waveform-viewport-actions" aria-label="Waveform viewport">
        <button
          type="button"
          disabled={disabled}
          onClick={() => applyViewport(zoomSampleViewport(
            viewport,
            2,
            Math.round((viewport.startFrame + viewport.endFrame) / 2),
          ))}
        >
          Zoom In
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => applyViewport(zoomSampleViewport(
            viewport,
            .5,
            Math.round((viewport.startFrame + viewport.endFrame) / 2),
          ))}
        >
          Zoom Out
        </button>
        <button
          type="button"
          disabled={disabled}
          aria-label="Fit waveform"
          onClick={() => applyViewport(fitSampleViewport(sourceFrames))}
        >
          Fit
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => applyViewport(panSampleViewport(
            viewport,
            -Math.max(1, Math.round((viewport.endFrame - viewport.startFrame) / 4)),
          ))}
        >
          Pan Left
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => applyViewport(panSampleViewport(
            viewport,
            Math.max(1, Math.round((viewport.endFrame - viewport.startFrame) / 4)),
          ))}
        >
          Pan Right
        </button>
      </div>
    </section>
  );
}
