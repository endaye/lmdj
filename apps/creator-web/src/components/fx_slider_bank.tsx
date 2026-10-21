import {type ReactNode, useLayoutEffect, useRef} from "react";

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
// remain available in the MORE group. In the typed profile the first main
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
  readonly gestureOwner?: object;
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
  // Each DOM input owns its token and the callback that admitted it. A late
  // lost-capture/blur from a removed input cannot close its replacement.
  type Touch = {token: string; node: HTMLInputElement; pointerId?: number; release: () => void};
  const gestures = useRef(new Map<PerformanceFx, Touch>());
  const filterGestures = useRef(new Map<"cutoff" | "resonance", Touch>());
  const typedFilter = props.filter.provenance !== "unavailable" &&
    !props.legacyFilterGesture;
  const gestureIdle = () => {
    if (gestures.current.size === 0 && filterGestures.current.size === 0) {
      props.onGestureActiveChange?.(false);
    }
  };
  const release = <Key,>(map: Map<Key, Touch>, key: Key,
    node: HTMLInputElement, pointerId?: number) => {
    const touch = map.get(key);
    if (touch === undefined || touch.node !== node ||
      (pointerId !== undefined && touch.pointerId !== undefined && pointerId !== touch.pointerId)) return;
    map.delete(key);
    touch.release();
    gestureIdle();
  };
  useLayoutEffect(() => () => {
    // Only UI touch tokens live here. Rotary/HOLD belong to the controller.
    const touches = [...gestures.current.values(), ...filterGestures.current.values()];
    gestures.current.clear();
    filterGestures.current.clear();
    for (const touch of touches) touch.release();
    if (touches.length > 0) props.onGestureActiveChange?.(false);
  }, [props.group, props.active, props.gestureOwner]);
  const slider = (fx: PerformanceFx) => (
    <input type="range" min={0} max={1000} step={1}
      aria-label={LABELS[fx]} value={props.values[fx]}
      onPointerDown={(event) => {
        if (!gestures.current.has(fx)) {
          const token = props.onEngage(fx, props.values[fx]);
          gestures.current.set(fx, {token, node: event.currentTarget, pointerId: event.pointerId,
            release: () => props.onRelease(token, fx)});
          props.onGestureActiveChange?.(true);
        }
        try { event.currentTarget.setPointerCapture(event.pointerId); } catch {
          // Synthetic component events do not own a native pointer.
        }
      }}
      onChange={(event) => {
        let touch = gestures.current.get(fx);
        if (touch === undefined) {
          const token = props.onEngage(fx, props.values[fx]);
          touch = {token, node: event.currentTarget, release: () => props.onRelease(token, fx)};
          gestures.current.set(fx, touch);
          props.onGestureActiveChange?.(true);
        }
        props.onMove(touch.token, fx, event.currentTarget.valueAsNumber);
      }}
      onPointerUp={(event) => release(gestures.current, fx, event.currentTarget, event.pointerId)}
      onPointerCancel={(event) => release(gestures.current, fx, event.currentTarget, event.pointerId)}
      onLostPointerCapture={(event) => release(gestures.current, fx, event.currentTarget, event.pointerId)}
      onBlur={(event) => release(gestures.current, fx, event.currentTarget)} />
  );
  const filterSlider = (parameter: "cutoff" | "resonance", label: string,
    value: number) => (
    <input type="range" min={0} max={1000} step={1} aria-label={label}
      value={value} disabled={!typedFilter}
      onPointerDown={(event) => {
        if (!filterGestures.current.has(parameter)) {
          const token = props.onFilterTouchEngage(parameter);
          filterGestures.current.set(parameter, {token, node: event.currentTarget, pointerId: event.pointerId,
            release: () => props.onFilterTouchRelease(token, parameter)});
          props.onGestureActiveChange?.(true);
        }
        try { event.currentTarget.setPointerCapture(event.pointerId); } catch {
          // Synthetic component events do not own a native pointer.
        }
      }}
      onChange={(event) => {
        let touch = filterGestures.current.get(parameter);
        if (touch === undefined) {
          const token = props.onFilterTouchEngage(parameter);
          touch = {token, node: event.currentTarget,
            release: () => props.onFilterTouchRelease(token, parameter)};
          filterGestures.current.set(parameter, touch);
          props.onGestureActiveChange?.(true);
        }
        props.onFilterTouchMove(touch.token, parameter,
          event.currentTarget.valueAsNumber);
      }}
      onPointerUp={(event) => release(filterGestures.current, parameter, event.currentTarget, event.pointerId)}
      onPointerCancel={(event) => release(filterGestures.current, parameter, event.currentTarget, event.pointerId)}
      onLostPointerCapture={(event) => release(filterGestures.current, parameter, event.currentTarget, event.pointerId)}
      onBlur={(event) => release(filterGestures.current, parameter, event.currentTarget)} />
  );
  if (props.active === false) return null;
  const live = props.order.filter(isLive);
  const more = props.order.filter((fx) => !isLive(fx));
  return (
    <section className="perform-fx" aria-label="Performance FX" data-group={props.group}>
      <nav className="perform-fx-actions" aria-label="Performance parameter groups">
        <button type="button" aria-pressed={props.group === "main"}
          onClick={() => props.onGroupChange("main")}>PRIMARY</button>
        <button type="button" aria-pressed={props.group === "filter"}
          aria-expanded={props.group === "filter"}
          onClick={() => props.onGroupChange(props.group === "filter" ? "main" : "filter")}>FILTER</button>
        <button type="button" aria-pressed={props.group === "more"}
          aria-expanded={props.group === "more"}
          onClick={() => props.onGroupChange(props.group === "more" ? "main" : "more")}>MORE</button>
        {props.action}
      </nav>
      <output role="status" aria-label="Filter status" data-provenance={props.filter.provenance}>
        Filter · {props.filter.provenance === "pending" ? "Pending" :
          props.filter.provenance === "unavailable" ? "Unavailable" :
          props.filter.frozen ? "Frozen" : props.filter.engaged ? "Engaged" : "Off"}
      </output>
      {props.group === "main" ? <div className="perform-live-faders">
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
      </div> : null}
      {props.group === "more" && more.length > 0 ? (
        <div className="perform-fx-more-bank" role="group"
          aria-label="More Performance FX">
          {more.map((fx) => (
            <label className="perform-fader" key={fx}>
              <span className="perform-fader-name">{LABELS[fx]}</span>
              <span className="perform-fader-value">{Math.round(props.values[fx] / 10)}%</span>
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
                aria-pressed={typedFilter && props.filter.type === type}
                onClick={() => props.onFilterType(type)}>
                {type.toUpperCase()}
              </button>
            ))}
          </div>
          <label className="perform-fader">
            <span className="perform-fader-name">Cutoff</span>
            <span className="perform-fader-value">
              {typedFilter ? formatCutoffHz(props.filter.cutoffHz) : "—"}
            </span>
            {filterSlider("cutoff", "Cutoff",
              cutoffHzToPosition(props.filter.cutoffHz))}
          </label>
          <label className="perform-fader">
            <span className="perform-fader-name">Resonance</span>
            <span className="perform-fader-value">
              {typedFilter ? `${Math.round(props.filter.resonanceMilli / 10)}%` : "—"}
            </span>
            {filterSlider("resonance", "Resonance",
              props.filter.resonanceMilli)}
          </label>

        </div>
      ) : null}
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
    </section>
  );
}
