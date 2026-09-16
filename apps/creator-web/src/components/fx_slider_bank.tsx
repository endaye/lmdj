import {useEffect, useRef, useState} from "react";

import type {PerformanceFx} from "@lmdj/web-runtime-platform/runtime_types";

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

// D04 draws vertical live faders for the two FX it names and puts the rest
// behind FX / MORE. The pictured MASTER fader and the LP/HP/BP filter type
// have no Host action, so nothing here renders them.
const LIVE_FADERS: readonly PerformanceFx[] = Object.freeze(["filter", "delay"]);

function isLive(fx: PerformanceFx): boolean {
  return LIVE_FADERS.includes(fx);
}

interface FxSliderBankProps {
  readonly order: readonly PerformanceFx[];
  readonly values: Readonly<Record<PerformanceFx, number>>;
  readonly disabled?: boolean;
  readonly onEngage: (fx: PerformanceFx, value: number) => string;
  readonly onMove: (gestureId: string, fx: PerformanceFx, value: number) => void;
  readonly onRelease: (gestureId: string, fx: PerformanceFx) => void;
}

export function FxSliderBank(props: FxSliderBankProps) {
  const gestures = useRef(new Map<PerformanceFx, string>());
  const [expanded, setExpanded] = useState(false);
  const release = (fx: PerformanceFx) => {
    const gestureId = gestures.current.get(fx);
    if (gestureId === undefined) return;
    gestures.current.delete(fx);
    props.onRelease(gestureId, fx);
  };
  useEffect(() => {
    if (!props.disabled) return;
    for (const fx of [...gestures.current.keys()]) release(fx);
  }, [props.disabled]);
  // Collapsing FX / MORE unmounts those inputs, so their open gestures close
  // here; the unmount effect below only fires when the whole bank goes away.
  useEffect(() => {
    if (expanded) return;
    for (const fx of [...gestures.current.keys()]) {
      if (!isLive(fx)) release(fx);
    }
  }, [expanded]);
  useEffect(() => () => {
    for (const [fx, gestureId] of gestures.current) {
      props.onRelease(gestureId, fx);
    }
    gestures.current.clear();
  }, []);
  const slider = (fx: PerformanceFx) => (
    <input type="range" min={0} max={1000} step={1}
      aria-label={LABELS[fx]} value={props.values[fx]}
      disabled={props.disabled}
      onPointerDown={() => {
        if (!gestures.current.has(fx)) {
          gestures.current.set(fx, props.onEngage(fx, props.values[fx]));
        }
      }}
      onChange={(event) => {
        let gestureId = gestures.current.get(fx);
        if (gestureId === undefined) {
          gestureId = props.onEngage(fx, props.values[fx]);
          gestures.current.set(fx, gestureId);
        }
        props.onMove(gestureId, fx, event.currentTarget.valueAsNumber);
      }}
      onPointerUp={() => release(fx)}
      onPointerCancel={() => release(fx)}
      onBlur={() => release(fx)} />
  );
  const live = props.order.filter(isLive);
  const more = props.order.filter((fx) => !isLive(fx));
  return (
    <section className="perform-fx" aria-label="Performance FX">
      <div className="perform-live-faders">
        {live.map((fx) => (
          <label className="perform-fader" key={fx}>
            <span className="perform-fader-name">{LABELS[fx]}</span>
            {/* The engine value is normalised 0–1000; this reads back the same
                number as a percentage and claims no unit the Host never has. */}
            <span className="perform-fader-value">
              {Math.round(props.values[fx] / 10)}%
            </span>
            {slider(fx)}
          </label>
        ))}
      </div>
      {more.length === 0 ? null : (
        <>
          <button type="button" className="perform-fx-more"
            aria-expanded={expanded}
            onClick={() => setExpanded((open) => !open)}>FX / MORE</button>
          {expanded ? (
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
        </>
      )}
    </section>
  );
}
