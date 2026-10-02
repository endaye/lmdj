import {useEffect, useRef, useState} from "react";

import type {
  PadEq,
  PadEqBell,
  PadEqShelf,
  PadPlayback,
} from "../runtime/runtime_types";

// The Pad's 3-band EQ (lmdj.project.v5 5.2.0) as three poles on one plot:
// frequency on a log axis, gain on a linear one. A gesture previews every
// move, commits once when it ends (pointer up, key release or blur) and
// cancels on Escape or pointercancel, as ValueSlider does.
//
// - Dragging a pole moves it by the pointer's travel, from wherever on its
//   hit circle it was grabbed; a press that does not travel changes nothing.
//   Dragging the low or high shelf below the gain floor, into the Cut strip,
//   makes it a cut. Escape anywhere cancels a drag.
// - A double tap on the mid pole and then a vertical drag sets its Q.
// - A band returned to 0 dB is bypassed (absent), so a flat EQ leaves the
//   Pad's playback neutral. The pole keeps its last frequency on screen.

export type EqBand = "low" | "mid" | "high";

const BANDS: readonly EqBand[] = ["low", "mid", "high"];
const BAND_NAMES: Readonly<Record<EqBand, string>> = {low: "Low", mid: "Mid", high: "High"};
const FREQ_RANGE: Readonly<Record<EqBand, readonly [number, number]>> = {
  low: [20, 2_000],
  mid: [100, 10_000],
  high: [1_000, 20_000],
};
const DEFAULT_FREQ: Readonly<Record<EqBand, number>> = {low: 100, mid: 1_000, high: 8_000};
const DEFAULT_Q_MILLI = 707;
const GAIN_LIMIT = 18_000;
const Q_RANGE = [100, 10_000] as const;
const DOUBLE_TAP_MS = 350;
// Pointer travel, in viewBox units, below which a press is still a tap.
const TAP_SLOP = 2;
// The keys a keyboard step uses; releasing one of them commits the run.
const STEP_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Delete", "Backspace"]);

// Plot geometry in viewBox units. The margins are wider than a pole's
// 22-unit hit radius, so a pole at any edge keeps its whole hit circle.
export const EQ_VIEW = Object.freeze({
  width: 320,
  height: 184,
  left: 24,
  right: 296,
  top: 24,
  floor: 136,
  // A pointer this far below the floor is in the Cut strip.
  cutThreshold: 10,
});
// Where a cut pole is drawn, below the Cut threshold.
const CUT_Y = EQ_VIEW.floor + EQ_VIEW.cutThreshold + 8;
const LOG_MIN = Math.log10(20);
const LOG_SPAN = Math.log10(20_000) - LOG_MIN;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function freqToX(freqHz: number): number {
  return EQ_VIEW.left +
    ((Math.log10(freqHz) - LOG_MIN) / LOG_SPAN) * (EQ_VIEW.right - EQ_VIEW.left);
}

function xToFreq(x: number, band: EqBand): number {
  const fraction = (x - EQ_VIEW.left) / (EQ_VIEW.right - EQ_VIEW.left);
  const [minimum, maximum] = FREQ_RANGE[band];
  return clamp(Math.round(10 ** (LOG_MIN + fraction * LOG_SPAN)), minimum, maximum);
}

export function gainToY(gainMillidb: number): number {
  return EQ_VIEW.top +
    ((GAIN_LIMIT - gainMillidb) / (2 * GAIN_LIMIT)) * (EQ_VIEW.floor - EQ_VIEW.top);
}

// Gain in 0.1 dB steps; within 0.5 dB of flat snaps to 0.
function yToGain(y: number): number {
  const fraction = (y - EQ_VIEW.top) / (EQ_VIEW.floor - EQ_VIEW.top);
  const gain = Math.round((GAIN_LIMIT - fraction * 2 * GAIN_LIMIT) / 100) * 100;
  const clamped = clamp(gain, -GAIN_LIMIT, GAIN_LIMIT);
  return Math.abs(clamped) <= 500 ? 0 : clamped;
}

interface Remembered {
  low: number;
  mid: {freqHz: number; qMilli: number};
  high: number;
}

// A shelf or bell at 0 dB is bypassed; a cut never is (it ignores gain).
function shelfBand(kind: "shelf" | "cut", freqHz: number, gainMillidb: number): PadEqShelf | null {
  return kind === "shelf" && gainMillidb === 0 ? null : {kind, freqHz, gainMillidb};
}

function bellBand(freqHz: number, gainMillidb: number, qMilli: number): PadEqBell | null {
  return gainMillidb === 0 ? null : {freqHz, gainMillidb, qMilli};
}

function withBand(eq: PadEq, band: EqBand, value: PadEqShelf | PadEqBell | null): PadEq {
  return {...eq, [band]: value};
}

function eqEquals(left: PadEq, right: PadEq): boolean {
  return BANDS.every((band) => JSON.stringify(left[band]) === JSON.stringify(right[band]));
}

function isCut(eq: PadEq, band: EqBand): boolean {
  const value = eq[band];
  return value !== null && "kind" in value && value.kind === "cut";
}

function formatFreq(freqHz: number): string {
  return freqHz >= 1_000 ? `${(freqHz / 1_000).toFixed(freqHz >= 10_000 ? 1 : 2)} kHz` : `${freqHz} Hz`;
}

function formatGain(gainMillidb: number): string {
  const db = gainMillidb / 1_000;
  return `${db > 0 ? "+" : ""}${db.toFixed(1)} dB`;
}

export function describeBand(band: EqBand, eq: PadEq): string {
  const name = BAND_NAMES[band];
  if (band === "mid") {
    const mid = eq.mid;
    return mid === null
      ? `${name} off`
      : `${name} ${formatFreq(mid.freqHz)} ${formatGain(mid.gainMillidb)} Q ${(mid.qMilli / 1_000).toFixed(2)}`;
  }
  const shelf = eq[band];
  if (shelf === null) return `${name} off`;
  return shelf.kind === "cut"
    ? `${name} cut ${formatFreq(shelf.freqHz)}`
    : `${name} shelf ${formatFreq(shelf.freqHz)} ${formatGain(shelf.gainMillidb)}`;
}

interface Gesture {
  band: EqBand;
  pointerId: number | null;
  mode: "move" | "q";
  // The press point, and the pole's offset from it, in viewBox units.
  startX: number;
  startY: number;
  grabX: number;
  grabY: number;
  travelled: boolean;
  startQ: number;
  base: PadEq;
  latest: PadEq;
}

interface EqEditorProps {
  padLabel: string;
  playback: Readonly<PadPlayback>;
  disabled: boolean;
  audioSuspended: boolean;
  onPreview: (playback: Readonly<PadPlayback>) => void;
  onCommit: (playback: Readonly<PadPlayback>) => void;
  onCancel: () => void;
}

export function EqEditor({
  padLabel,
  playback,
  disabled,
  audioSuspended,
  onPreview,
  onCommit,
  onCancel,
}: EqEditorProps) {
  const [draft, setDraft] = useState<PadEq | null>(null);
  const gesture = useRef<Gesture | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const lastTap = useRef<{band: EqBand; at: number} | null>(null);
  const remembered = useRef<Remembered>({
    low: DEFAULT_FREQ.low,
    mid: {freqHz: DEFAULT_FREQ.mid, qMilli: DEFAULT_Q_MILLI},
    high: DEFAULT_FREQ.high,
  });
  const shown = draft ?? playback.eq;
  if (shown.low !== null) remembered.current.low = shown.low.freqHz;
  if (shown.mid !== null) {
    remembered.current.mid = {freqHz: shown.mid.freqHz, qMilli: shown.mid.qMilli};
  }
  if (shown.high !== null) remembered.current.high = shown.high.freqHz;

  // A pole never takes focus from a pointer press, so Escape during a drag is
  // heard on the window rather than on the pole.
  const escapeListener = useRef((event: KeyboardEvent) => {
    if (event.key !== "Escape" || gesture.current?.pointerId == null) return;
    event.preventDefault();
    event.stopPropagation();
    cancelRef.current();
  });
  const listenForEscape = (listen: boolean) => {
    if (listen) window.addEventListener("keydown", escapeListener.current, true);
    else window.removeEventListener("keydown", escapeListener.current, true);
  };

  const cancel = () => {
    if (gesture.current === null) return;
    gesture.current = null;
    listenForEscape(false);
    setDraft(null);
    onCancel();
  };
  const cancelRef = useRef(cancel);
  cancelRef.current = cancel;
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  // A suspended audio graph cannot preview, so a live gesture is dropped.
  useEffect(() => {
    if (audioSuspended) cancelRef.current();
  }, [audioSuspended]);

  // Leaving mid-gesture (another Pad selected) clears the preview it started.
  useEffect(() => () => {
    window.removeEventListener("keydown", escapeListener.current, true);
    if (gesture.current !== null) {
      gesture.current = null;
      onCancelRef.current();
    }
  }, []);

  const move = (next: PadEq) => {
    const active = gesture.current;
    if (active === null || eqEquals(active.latest, next)) return;
    active.latest = next;
    setDraft(next);
    onPreview({...playback, eq: next});
  };

  const finish = () => {
    const active = gesture.current;
    if (active === null) return;
    gesture.current = null;
    listenForEscape(false);
    setDraft(null);
    if (!eqEquals(active.base, active.latest)) onCommit({...playback, eq: active.latest});
  };

  const begin = (
    band: EqBand,
    pointerId: number | null,
    mode: "move" | "q",
    start: {x: number; y: number} = {x: 0, y: 0},
  ) => {
    gesture.current = {
      band,
      pointerId,
      mode,
      startX: start.x,
      startY: start.y,
      grabX: freqToX(bandFreq(band)) - start.x,
      grabY: bandY(band) - start.y,
      travelled: false,
      startQ: playback.eq.mid?.qMilli ?? remembered.current.mid.qMilli,
      base: playback.eq,
      latest: playback.eq,
    };
  };

  const viewPoint = (clientX: number, clientY: number): {x: number; y: number} | null => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (rect === undefined || rect.width <= 0 || rect.height <= 0) return null;
    return {
      x: ((clientX - rect.left) / rect.width) * EQ_VIEW.width,
      y: ((clientY - rect.top) / rect.height) * EQ_VIEW.height,
    };
  };

  // The band a pointer at (x, y) describes.
  const bandAt = (band: EqBand, x: number, y: number, mode: "move" | "q"): PadEqShelf | PadEqBell | null => {
    if (band === "mid") {
      if (mode === "q") {
        const active = gesture.current!;
        const qMilli = clamp(
          Math.round(active.startQ * 2 ** ((active.startY - y) / 40)),
          Q_RANGE[0], Q_RANGE[1]);
        const current = active.latest.mid ?? {
          freqHz: remembered.current.mid.freqHz,
          gainMillidb: 0,
          qMilli,
        };
        // Q alone never brings a bypassed bell back.
        return current.gainMillidb === 0 ? null : {...current, qMilli};
      }
      return bellBand(xToFreq(x, band), yToGain(y), remembered.current.mid.qMilli);
    }
    const freqHz = xToFreq(x, band);
    if (y > EQ_VIEW.floor + EQ_VIEW.cutThreshold) {
      // A cut keeps the gain the band already carried (lmdj.project.v5 5.2.0
      // keeps it in Project Truth), so leaving the cut by keyboard restores it.
      const current = gesture.current!.latest[band] as PadEqShelf | null;
      return shelfBand("cut", freqHz, current?.gainMillidb ?? -GAIN_LIMIT);
    }
    return shelfBand("shelf", freqHz, yToGain(y));
  };

  const pointerDown = (event: React.PointerEvent<SVGGElement>, band: EqBand) => {
    if (disabled || event.button !== 0 || gesture.current !== null) return;
    event.preventDefault();
    const point = viewPoint(event.clientX, event.clientY);
    if (point === null) return;
    const now = event.timeStamp;
    const doubleTap = band === "mid" && lastTap.current?.band === "mid" &&
      now - lastTap.current.at <= DOUBLE_TAP_MS;
    lastTap.current = {band, at: now};
    begin(band, event.pointerId, doubleTap ? "q" : "move", point);
    listenForEscape(true);
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {
      // pointerup on the element still ends the gesture.
    }
  };

  const pointerMove = (event: React.PointerEvent<SVGGElement>) => {
    const active = gesture.current;
    if (active === null || active.pointerId !== event.pointerId) return;
    const point = viewPoint(event.clientX, event.clientY);
    if (point === null) return;
    if (!active.travelled) {
      if (Math.abs(point.x - active.startX) <= TAP_SLOP &&
        Math.abs(point.y - active.startY) <= TAP_SLOP) return;
      active.travelled = true;
    }
    // Q mode reads the pointer's own vertical travel; a move carries the pole
    // by the offset it was grabbed at.
    const x = active.mode === "q" ? point.x : point.x + active.grabX;
    const y = active.mode === "q" ? point.y : point.y + active.grabY;
    move(withBand(active.latest, active.band, bandAt(active.band, x, y, active.mode)));
  };

  const pointerUp = (event: React.PointerEvent<SVGGElement>) => {
    if (gesture.current?.pointerId === event.pointerId) finish();
  };

  // Keyboard: arrows move gain (Up/Down) and frequency (Left/Right) one step;
  // Shift with Up/Down sets the mid Q; Delete or Backspace bypasses the band.
  const keyStep = (band: EqBand, event: React.KeyboardEvent<SVGGElement>): PadEq | null => {
    const eq = gesture.current?.latest ?? playback.eq;
    const [minimum, maximum] = FREQ_RANGE[band];
    const freqStep = (freqHz: number, up: boolean) =>
      clamp(Math.round(freqHz * 2 ** ((up ? 1 : -1) / 12)), minimum, maximum);
    if (event.key === "Delete" || event.key === "Backspace") return withBand(eq, band, null);
    if (band === "mid") {
      const mid = eq.mid ?? {
        freqHz: remembered.current.mid.freqHz,
        gainMillidb: 0,
        qMilli: remembered.current.mid.qMilli,
      };
      switch (event.key) {
        case "ArrowUp":
        case "ArrowDown": {
          const up = event.key === "ArrowUp";
          if (event.shiftKey) {
            if (eq.mid === null) return eq;
            const qMilli = clamp(Math.round(mid.qMilli * 2 ** ((up ? 1 : -1) / 4)), Q_RANGE[0], Q_RANGE[1]);
            return withBand(eq, "mid", {...mid, qMilli});
          }
          const gain = clamp(mid.gainMillidb + (up ? 500 : -500), -GAIN_LIMIT, GAIN_LIMIT);
          return withBand(eq, "mid", bellBand(mid.freqHz, gain, mid.qMilli));
        }
        case "ArrowLeft":
        case "ArrowRight":
          if (eq.mid === null) return eq;
          return withBand(eq, "mid", {...mid, freqHz: freqStep(mid.freqHz, event.key === "ArrowRight")});
        default:
          return null;
      }
    }
    const shelf = eq[band] ?? {kind: "shelf" as const, freqHz: remembered.current[band], gainMillidb: 0};
    switch (event.key) {
      case "ArrowUp":
        // Leaving a cut restores the gain it kept.
        return withBand(eq, band, shelf.kind === "cut"
          ? shelfBand("shelf", shelf.freqHz, shelf.gainMillidb)
          : shelfBand("shelf", shelf.freqHz, clamp(shelf.gainMillidb + 500, -GAIN_LIMIT, GAIN_LIMIT)));
      case "ArrowDown":
        if (shelf.kind === "cut") return eq;
        // A step stops at the floor; one more from the floor makes a cut.
        return withBand(eq, band, shelf.gainMillidb <= -GAIN_LIMIT
          ? shelfBand("cut", shelf.freqHz, shelf.gainMillidb)
          : shelfBand("shelf", shelf.freqHz, Math.max(-GAIN_LIMIT, shelf.gainMillidb - 500)));
      case "ArrowLeft":
      case "ArrowRight":
        if (eq[band] === null) return eq;
        return withBand(eq, band, {...shelf, freqHz: freqStep(shelf.freqHz, event.key === "ArrowRight")});
      default:
        return null;
    }
  };

  const keyDown = (event: React.KeyboardEvent<SVGGElement>, band: EqBand) => {
    if (disabled) return;
    if (event.key === "Escape") {
      if (gesture.current !== null) {
        event.preventDefault();
        cancel();
      }
      return;
    }
    const next = keyStep(band, event);
    if (next === null) return;
    event.preventDefault();
    if (gesture.current === null) begin(band, null, "move");
    move(next);
  };

  const keyUp = (event: React.KeyboardEvent<SVGGElement>) => {
    if (gesture.current?.pointerId === null && STEP_KEYS.has(event.key)) finish();
  };

  const bandFreq = (band: EqBand): number =>
    band === "mid"
      ? shown.mid?.freqHz ?? remembered.current.mid.freqHz
      : shown[band]?.freqHz ?? remembered.current[band];
  const bandY = (band: EqBand): number => {
    const value = shown[band];
    if (value === null) return gainToY(0);
    if ("kind" in value && value.kind === "cut") return CUT_Y;
    return gainToY(value.gainMillidb);
  };

  return (
    <section className="eq-editor" aria-label={`${padLabel} EQ`}>
      <span className="eq-editor-title">EQ</span>
      <svg
        ref={svgRef}
        className="eq-plot"
        viewBox={`0 0 ${EQ_VIEW.width} ${EQ_VIEW.height}`}
        role="group"
        aria-label={`${padLabel} EQ bands`}
      >
        <rect
          className="eq-cut-zone"
          x={EQ_VIEW.left}
          y={EQ_VIEW.floor + EQ_VIEW.cutThreshold}
          width={EQ_VIEW.right - EQ_VIEW.left}
          height={EQ_VIEW.height - EQ_VIEW.floor - EQ_VIEW.cutThreshold}
        />
        <text className="eq-axis-label" x={EQ_VIEW.right - 2} y={EQ_VIEW.height - 6} textAnchor="end">Cut</text>
        <line className="eq-zero" x1={EQ_VIEW.left} x2={EQ_VIEW.right} y1={gainToY(0)} y2={gainToY(0)} />
        <line className="eq-floor" x1={EQ_VIEW.left} x2={EQ_VIEW.right} y1={EQ_VIEW.floor} y2={EQ_VIEW.floor} />
        {[100, 1_000, 10_000].map((freq) => (
          <g key={freq}>
            <line className="eq-grid" x1={freqToX(freq)} x2={freqToX(freq)} y1={EQ_VIEW.top} y2={EQ_VIEW.floor} />
            <text className="eq-axis-label" x={freqToX(freq)} y={EQ_VIEW.top - 2} textAnchor="middle">
              {freq >= 1_000 ? `${freq / 1_000}k` : freq}
            </text>
          </g>
        ))}
        {BANDS.map((band) => {
          const active = shown[band] !== null;
          const gain = shown[band]?.gainMillidb ?? 0;
          return (
            <g
              key={band}
              className={`eq-pole eq-pole-${band}${active ? " eq-pole-active" : ""}`}
              role="slider"
              tabIndex={disabled ? -1 : 0}
              aria-label={`${padLabel} EQ ${BAND_NAMES[band]}`}
              aria-valuemin={-18}
              aria-valuemax={18}
              aria-valuenow={isCut(shown, band) ? -18 : gain / 1_000}
              aria-valuetext={describeBand(band, shown)}
              aria-disabled={disabled}
              transform={`translate(${freqToX(bandFreq(band))} ${bandY(band)})`}
              onPointerDown={(event) => pointerDown(event, band)}
              onPointerMove={pointerMove}
              onPointerUp={pointerUp}
              onPointerCancel={cancel}
              onKeyDown={(event) => keyDown(event, band)}
              onKeyUp={keyUp}
              onBlur={finish}
            >
              <circle className="eq-pole-hit" r={22} />
              <circle className="eq-pole-dot" r={8} />
              <text className="eq-pole-label" y={4} textAnchor="middle">{BAND_NAMES[band][0]}</text>
            </g>
          );
        })}
      </svg>
      <output className="eq-readout" aria-live="off">
        {BANDS.map((band) => describeBand(band, shown)).join(" · ")}
      </output>
    </section>
  );
}
