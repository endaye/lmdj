import {useEffect, useRef} from "react";

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
  useEffect(() => () => {
    for (const [fx, gestureId] of gestures.current) {
      props.onRelease(gestureId, fx);
    }
    gestures.current.clear();
  }, []);
  return (
    <section className="perform-fx" aria-label="Performance FX">
      {props.order.map((fx) => (
        <label key={fx}>
          <span>{LABELS[fx]}</span>
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
        </label>
      ))}
    </section>
  );
}
