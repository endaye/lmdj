import {useEffect, useRef} from "react";

import type {Bank} from "../state/creator_state";
import {bankName} from "../state/view_model";
import {
  createSequenceGridModel,
  SEQUENCE_GRID_SNAPS,
  sequenceGridViewportForWindow,
  type SequenceGridPattern,
  type SequenceGridSnap,
  type SequenceGridViewport,
} from "../state/sequence_grid_model";

interface SequenceGridProps {
  pattern: SequenceGridPattern;
  bank: Bank;
  snap: SequenceGridSnap;
  onSnapChange(snap: SequenceGridSnap): void;
  onViewportChange(viewport: SequenceGridViewport): void;
}

// The Sequence Pattern grid is a read-only projection of Project Truth in T2;
// the editing gestures land with the edit Task. Rows are the active Bank's
// sixteen Pads; the horizontal axis is the whole Pattern under a scroll port.
export function SequenceGrid(props: SequenceGridProps) {
  const {pattern, bank, snap} = props;
  const model = createSequenceGridModel(pattern, bank, snap);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const reportedRef = useRef<SequenceGridViewport | null>(null);
  const onViewportChange = props.onViewportChange;
  useEffect(() => {
    const report = () => {
      const scroller = scrollRef.current;
      const lane = scroller?.querySelector(".sequence-grid-lane") ?? null;
      if (scroller === null || lane === null) return;
      // The lane is the timeline: the scroll port also holds the Pad label
      // column, so scroller totals would shift the reported window.
      const window_ = scroller.getBoundingClientRect();
      const laneRect = lane.getBoundingClientRect();
      const viewport = sequenceGridViewportForWindow({
        windowStart: window_.left,
        windowEnd: window_.right,
        timelineStart: laneRect.left,
        timelineWidth: laneRect.width,
        lengthTicks: model.lengthTicks,
      });
      const last = reportedRef.current;
      if (last !== null && last.startTick === viewport.startTick &&
          last.endTick === viewport.endTick) {
        return;
      }
      reportedRef.current = viewport;
      onViewportChange(viewport);
    };
    report();
    const scroller = scrollRef.current;
    scroller?.addEventListener("scroll", report);
    return () => scroller?.removeEventListener("scroll", report);
  }, [model.lengthTicks, onViewportChange]);
  const columnPercent = model.columnCount === 0
    ? null
    : 100 / model.columnCount;
  const barPercent = 100 / model.bars;
  return (
    <section className="sequence-grid" aria-label="Sequence grid"
      data-testid="sequence-grid">
      <div className="sequence-segment" role="group" aria-label="Snap">
        <span>SNAP</span>
        {SEQUENCE_GRID_SNAPS.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={snap === option}
            aria-label={`Snap ${option}`}
            onClick={() => props.onSnapChange(option)}
          >
            {option}
          </button>
        ))}
      </div>
      <div className="sequence-grid-scroll" ref={scrollRef}>
        <div className="sequence-grid-body"
          style={{width: `${model.bars * 24}rem`, minWidth: "100%"}}>
          {model.rows.map((row) => (
            <div className="sequence-grid-row" data-pad={row.pad} key={row.pad}>
              <span className="sequence-grid-pad">{bankName(bank)}{row.pad + 1}</span>
              <div
                className="sequence-grid-lane"
                style={{
                  backgroundImage: columnPercent === null
                    ? `repeating-linear-gradient(to right, transparent 0, transparent calc(${barPercent}% - 1px), #3a4150 calc(${barPercent}% - 1px), #3a4150 ${barPercent}%)`
                    : `repeating-linear-gradient(to right, transparent 0, transparent calc(${columnPercent}% - 1px), #2c333f calc(${columnPercent}% - 1px), #2c333f ${columnPercent}%), repeating-linear-gradient(to right, transparent 0, transparent calc(${barPercent}% - 1px), #3a4150 calc(${barPercent}% - 1px), #3a4150 ${barPercent}%)`,
                }}
              >
                {row.notes.map((note, index) => (
                  <div
                    className="sequence-grid-note"
                    data-testid="sequence-grid-note"
                    data-onset-tick={note.onsetTick}
                    data-duration-tick={note.durationTick}
                    data-velocity={note.velocity}
                    role="img"
                    aria-label={`Pad ${bankName(bank)}${note.pad + 1} note · onset ${note.onsetTick} · length ${note.durationTick} · velocity ${note.velocity}`}
                    key={`${note.onsetTick}:${index}`}
                    style={{
                      left: `${note.onsetTick / model.lengthTicks * 100}%`,
                      width: `${note.durationTick / model.lengthTicks * 100}%`,
                      opacity: 0.45 + note.velocity / 127 * 0.55,
                    }}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
