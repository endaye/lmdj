import {type ReactNode, useEffect, useRef} from "react";

import type {
  PerformanceFilterTypeName,
  PerformanceFx,
} from "@lmdj/web-runtime-platform/runtime_types";

import {
  cutoffHzToPosition,
  FILTER_TYPES,
  type FilterControlState,
} from "../state/perform_state";

const LABELS: Readonly<Record<PerformanceFx, string>> = Object.freeze({
  filter: "Filter",
  delay: "Delay",
  reverb: "Reverb",
  stutter: "Stutter",
  gate: "Gate",
  reverse: "Reverse",
  crush: "Crush",
  cutter: "Cutter",
});

// The three main FX mirror the approved rotary group; other existing FX
// remain available in the touch drawer. In the typed profile the first main
// slot is the independent Filter cutoff, not the legacy scalar.
const LIVE_FADERS: readonly PerformanceFx[] = Object.freeze(["filter", "delay", "reverb"]);

function isLive(fx: PerformanceFx): boolean {
  return LIVE_FADERS.includes(fx);
}

export function formatCutoffHz(hz: number): string {
  return hz >= 1000 ? `${(hz / 1000).toFixed(1)} kHz` : `${hz} Hz`;
}

export type FxGroup = "main" | "more" | "filter";

export interface MonitorVolumeControl {
  readonly value: number;
  readonly disabled: boolean;
  readonly onChange: (value: number) => void;
}

interface FxSliderBankProps {
  readonly active?: boolean;
  readonly action?: ReactNode;
  readonly onGestureActiveChange?: (active: boolean) => void;
  readonly order: readonly PerformanceFx[];
  readonly values: Readonly<Record<PerformanceFx, number>>;
  readonly onEngage: (fx: PerformanceFx, value: number) => string;
  readonly onMove: (gestureId: string, fx: PerformanceFx, value: number) => void;
  readonly onRelease: (gestureId: string, fx: PerformanceFx) => void;
  readonly filter: FilterControlState;
  // An open legacy scalar Filter gesture pins the legacy fader until it
  // closes; the typed Cutoff never replaces it mid-gesture.
  readonly legacyFilterGesture: boolean;
  readonly onFilterType: (type: PerformanceFilterTypeName) => void;
  readonly onFilterTouchEngage: (parameter: "cutoff" | "resonance") => string;
  readonly onFilterTouchMove: (token: string,
    parameter: "cutoff" | "resonance", value: number) => void;
  readonly onFilterTouchRelease: (token: string,
    parameter: "cutoff" | "resonance") => void;
  readonly group: FxGroup;
  readonly onGroupChange: (group: FxGroup) => void;
  readonly monitorVolume?: MonitorVolumeControl | undefined;
}

export function FxSliderBank(props: FxSliderBankProps) {
  const gestures = useRef(new Map<PerformanceFx, string>());
  const filterGestures = useRef(new Map<"cutoff" | "resonance", string>());
  const typedFilter = props.filter.provenance !== "unavailable" &&
    !props.legacyFilterGesture;
  const gestureIdle = () => {
    if (gestures.current.size === 0 && filterGestures.current.size === 0) {
      props.onGestureActiveChange?.(false);
    }
  };
  const release = (fx: PerformanceFx) => {
    const gestureId = gestures.current.get(fx);
    if (gestureId === undefined) return;
    gestures.current.delete(fx);
    props.onRelease(gestureId, fx);
    gestureIdle();
  };
  const releaseFilter = (parameter: "cutoff" | "resonance") => {
    const token = filterGestures.current.get(parameter);
    if (token === undefined) return;
    filterGestures.current.delete(parameter);
    props.onFilterTouchRelease(token, parameter);
    gestureIdle();
  };
  // Switching groups unmounts the other groups' inputs, so their open touch
  // gestures close here; the unmount effect below only fires when the whole
  // bank goes away. Rotary gestures are not held here and survive (D04).
  useEffect(() => {
    if (props.group === "more") return;
    for (const fx of [...gestures.current.keys()]) {
      if (!isLive(fx)) release(fx);
    }
  }, [props.group]);
  useEffect(() => {
    if (props.group === "filter") return;
    releaseFilter("cutoff");
    releaseFilter("resonance");
  }, [props.group]);
  useEffect(() => () => {
    for (const [fx, gestureId] of gestures.current) {
      props.onRelease(gestureId, fx);
    }
    gestures.current.clear();
    for (const [parameter, token] of filterGestures.current) {
      props.onFilterTouchRelease(token, parameter);
    }
    filterGestures.current.clear();
  }, []);
  const slider = (fx: PerformanceFx) => (
    <input type="range" min={0} max={1000} step={1}
      aria-label={LABELS[fx]} value={props.values[fx]}
      onPointerDown={(event) => {
        if (!gestures.current.has(fx)) {
          gestures.current.set(fx, props.onEngage(fx, props.values[fx]));
          props.onGestureActiveChange?.(true);
        }
        try { event.currentTarget.setPointerCapture(event.pointerId); } catch {
          // Synthetic component events do not own a native pointer.
        }
      }}
      onChange={(event) => {
        let gestureId = gestures.current.get(fx);
        if (gestureId === undefined) {
          gestureId = props.onEngage(fx, props.values[fx]);
          gestures.current.set(fx, gestureId);
          props.onGestureActiveChange?.(true);
        }
        props.onMove(gestureId, fx, event.currentTarget.valueAsNumber);
      }}
      onPointerUp={() => release(fx)}
      onPointerCancel={() => release(fx)}
      onLostPointerCapture={() => release(fx)}
      onBlur={() => release(fx)} />
  );
  const filterSlider = (parameter: "cutoff" | "resonance", label: string,
    value: number) => (
    <input type="range" min={0} max={1000} step={1} aria-label={label}
      value={value} disabled={!typedFilter}
      onPointerDown={(event) => {
        if (!filterGestures.current.has(parameter)) {
          filterGestures.current.set(parameter,
            props.onFilterTouchEngage(parameter));
          props.onGestureActiveChange?.(true);
        }
        try { event.currentTarget.setPointerCapture(event.pointerId); } catch {
          // Synthetic component events do not own a native pointer.
        }
      }}
      onChange={(event) => {
        let token = filterGestures.current.get(parameter);
        if (token === undefined) {
          token = props.onFilterTouchEngage(parameter);
          filterGestures.current.set(parameter, token);
          props.onGestureActiveChange?.(true);
        }
        props.onFilterTouchMove(token, parameter,
          event.currentTarget.valueAsNumber);
      }}
      onPointerUp={() => releaseFilter(parameter)}
      onPointerCancel={() => releaseFilter(parameter)}
      onLostPointerCapture={() => releaseFilter(parameter)}
      onBlur={() => releaseFilter(parameter)} />
  );
  if (props.active === false) return null;
  const live = props.order.filter(isLive);
  const more = props.order.filter((fx) => !isLive(fx));
  return (
    <section className="perform-fx" aria-label="Performance FX">
      <div className={`perform-live-faders${props.monitorVolume === undefined ? "" : " has-master"}`}>
        {live.map((fx) => {
          if (fx === "filter" && typedFilter) {
            // The typed Filter keeps the legacy slot and accessible name —
            // the change is the readback: Core Hz, never a guessed percentage.
            return (
              <label className="perform-fader" key={fx}>
                <span className="perform-fader-name">{LABELS[fx]}</span>
                <span className="perform-fader-value">
                  {formatCutoffHz(props.filter.cutoffHz)}
                </span>
                {filterSlider("cutoff", "Filter",
                  cutoffHzToPosition(props.filter.cutoffHz))}
              </label>
            );
          }
          return (
            <label className="perform-fader" key={fx}>
              <span className="perform-fader-name">{LABELS[fx]}</span>
              {/* The engine value is normalised 0–1000; this reads back the same
                  number as a percentage and claims no unit the Host never has. */}
              <span className="perform-fader-value">
                {Math.round(props.values[fx] / 10)}%
              </span>
              {slider(fx)}
            </label>
          );
        })}
        {props.monitorVolume === undefined ? null : (
          <label className="perform-fader perform-master-fader">
            <span className="perform-fader-name">MASTER</span>
            <span className="perform-fader-value">{props.monitorVolume.value}%</span>
            <input type="range" min={0} max={100} step={1} aria-label="MASTER"
              value={props.monitorVolume.value} disabled={props.monitorVolume.disabled}
              onChange={(event) => {
                const monitor = props.monitorVolume;
                if (monitor === undefined || monitor.disabled) return;
                monitor.onChange(event.currentTarget.valueAsNumber);
              }} />
          </label>
        )}
      </div>
      <div className="perform-fx-actions">
        {props.action}
        {more.length === 0 ? null : (
          <button type="button" className="perform-fx-more"
            aria-expanded={props.group === "more"}
            onClick={() => props.onGroupChange(
              props.group === "more" ? "main" : "more")}>FX / MORE</button>
        )}
        <button type="button" className="perform-fx-filter"
          aria-expanded={props.group === "filter"}
          onClick={() => props.onGroupChange(
            props.group === "filter" ? "main" : "filter")}>FILTER</button>
      </div>
      {props.group === "more" && more.length > 0 ? (
        <div className="perform-fx-more-bank" role="group"
          aria-label="More Performance FX">
          {more.map((fx) => (
            <label key={fx}>
              <span>{LABELS[fx]}</span>
              {slider(fx)}
            </label>
          ))}
        </div>
      ) : null}
      {props.group === "filter" ? (
        <div className="perform-filter-panel" role="group" aria-label="Filter">
          <div className="perform-filter-types" role="group"
            aria-label="Filter type">
            {FILTER_TYPES.map((type) => (
              <button type="button" key={type} disabled={!typedFilter}
                aria-pressed={props.filter.type === type}
                onClick={() => props.onFilterType(type)}>
                {type.toUpperCase()}
              </button>
            ))}
          </div>
          <label className="perform-fader">
            <span className="perform-fader-name">Cutoff</span>
            <span className="perform-fader-value">
              {formatCutoffHz(props.filter.cutoffHz)}
            </span>
            {filterSlider("cutoff", "Cutoff",
              cutoffHzToPosition(props.filter.cutoffHz))}
          </label>
          <label className="perform-fader">
            <span className="perform-fader-name">Resonance</span>
            <span className="perform-fader-value">
              {Math.round(props.filter.resonanceMilli / 10)}%
            </span>
            {filterSlider("resonance", "Resonance",
              props.filter.resonanceMilli)}
          </label>
          <output role="status" aria-label="Filter status">
            {props.filter.engaged ? "engaged" : "OFF"}
            {props.filter.frozen ? " · frozen" : ""}
            {` · ${props.filter.provenance}`}
          </output>
        </div>
      ) : null}
    </section>
  );
}
