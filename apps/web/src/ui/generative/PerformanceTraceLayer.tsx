import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type { Pad } from "../../patch/loader";
import {
  appendPerformanceTrace,
  beatDurationMs,
  type PadPressEvent,
  type PerformanceTrace,
} from "./performanceTrace";
import {
  createVisualSignature,
  roleForPad,
} from "./visualSignature";

function reducedMotionPreferred(): boolean {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function PerformanceTraceLayer({
  press,
  pads,
  bpm,
  playheadStep,
  projectSeed,
}: {
  press: PadPressEvent | null;
  pads: readonly Pad[];
  bpm: number;
  playheadStep: number | null;
  projectSeed: string;
}) {
  const reducedMotion = reducedMotionPreferred();
  const [traces, setTraces] = useState<PerformanceTrace[]>([]);
  const timerIds = useRef(new Set<number>());
  const lastSequence = useRef<number | null>(null);
  const lastBar = useRef<number | null>(null);
  const lastProjectSeed = useRef(projectSeed);
  const waitingForPressRelease = useRef(false);
  const padByIndex = useMemo(
    () => new Map(pads.map((pad) => [pad.index, pad])),
    [pads],
  );

  useEffect(() => () => {
    for (const timerId of timerIds.current) window.clearTimeout(timerId);
    timerIds.current.clear();
  }, []);

  useEffect(() => {
    if (projectSeed === lastProjectSeed.current) return;
    lastProjectSeed.current = projectSeed;
    lastSequence.current = press?.sequence ?? null;
    lastBar.current = playheadStep === null
      ? null
      : Math.floor(playheadStep / 16);
    waitingForPressRelease.current = press !== null;
    setTraces([]);
    for (const timerId of timerIds.current) window.clearTimeout(timerId);
    timerIds.current.clear();
  }, [playheadStep, press, projectSeed]);

  useEffect(() => {
    if (playheadStep === null) return;
    const bar = Math.floor(playheadStep / 16);
    if (lastBar.current !== null && bar !== lastBar.current) {
      setTraces([]);
      for (const timerId of timerIds.current) window.clearTimeout(timerId);
      timerIds.current.clear();
    }
    lastBar.current = bar;
  }, [playheadStep]);

  useEffect(() => {
    if (waitingForPressRelease.current) {
      if (!press) {
        waitingForPressRelease.current = false;
        lastSequence.current = null;
      }
      return;
    }
    if (!press || press.sequence === lastSequence.current) return;
    lastSequence.current = press.sequence;
    if (reducedMotion) return;
    const pad = padByIndex.get(press.padIndex);
    if (!pad) return;
    const now = Date.now();
    setTraces((current) =>
      appendPerformanceTrace(
        current,
        press,
        roleForPad(pad),
        projectSeed,
        bpm,
        now,
      )
    );
    const timerId = window.setTimeout(() => {
      setTraces((current) =>
        current.filter(
          (trace) =>
            trace.id !== `${projectSeed}:${press.sequence}:${press.padIndex}`,
        )
      );
      timerIds.current.delete(timerId);
    }, beatDurationMs(bpm));
    timerIds.current.add(timerId);
  }, [bpm, padByIndex, press, projectSeed, reducedMotion]);

  return (
    <div
      className="performance-trace-layer"
      data-testid="performance-trace-layer"
      data-reduced-motion={String(reducedMotion)}
      aria-hidden="true"
      style={{ pointerEvents: "none" }}
    >
      {!reducedMotion && traces.map((trace) => {
        const signature = createVisualSignature(trace.signatureSeed);
        const style = {
          "--trace-angle": `${signature.angle}deg`,
          "--trace-offset": `${signature.offset}%`,
          "--trace-duration": `${beatDurationMs(bpm)}ms`,
        } as CSSProperties;
        return (
          <span
            key={trace.id}
            className={`performance-trace performance-trace--${trace.role}`}
            data-testid="performance-trace"
            data-pad-index={trace.padIndex}
            data-signature={signature.id}
            style={style}
          >
            <i className="performance-trace__mark" />
          </span>
        );
      })}
    </div>
  );
}
