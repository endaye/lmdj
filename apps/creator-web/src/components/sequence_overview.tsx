import {useEffect, useState} from "react";

import {userMessage} from "../state/error_messages";
import type {ProjectView} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import type {SequenceState} from "../state/sequence_state";
import {
  createSequenceGridThumbnail,
  sequencePlayheadTick,
  type SequenceGridSnap,
  type SequenceGridViewport,
} from "../state/sequence_grid_model";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {transportStatusLabel} from "./transport_status";

interface SequenceOverviewProps {
  project: ProjectView | null;
  state: SequenceState;
  transport?: PatternTransportState;
  bank: Bank;
  snap: SequenceGridSnap;
  viewport: SequenceGridViewport | null;
}

// The Runtime advances 48 frames per millisecond at its fixed 48 kHz.
const FRAMES_PER_MILLISECOND = 48;

export function SequenceOverview({
  project,
  state,
  transport,
  bank,
  snap,
  viewport,
}: SequenceOverviewProps) {
  const selectedPatternId = state.selectedPatternId ?? project?.patternId ?? null;
  const pattern = selectedPatternId === null
    ? undefined
    : project?.patterns.find((item) => item.patternId === selectedPatternId);
  const pendingPatternId = state.status?.pendingPatternId ?? null;
  const phase = transport === undefined
    ? state.phase
    : transportStatusLabel(transport);
  const thumbnail = pattern === undefined ? null : createSequenceGridThumbnail(pattern);
  const bpm = project?.bpm ?? null;
  const status = transport?.status ?? null;
  const playing = status !== null && status.playing === true &&
    thumbnail !== null && bpm !== null;
  const originFrame = playing && status !== null ? status.originFrame : null;
  const lengthTicks = thumbnail?.lengthTicks ?? null;
  const [playheadTick, setPlayheadTick] = useState<number | null>(null);
  useEffect(() => {
    if (originFrame === null || lengthTicks === null || bpm === null) {
      setPlayheadTick(null);
      return;
    }
    const observedAt = performance.now();
    const tickAt = (now: number) => sequencePlayheadTick({
      originFrame,
      runtimeFrame: originFrame +
        Math.floor(Math.max(0, now - observedAt) * FRAMES_PER_MILLISECOND),
      bpm,
      lengthTicks,
    });
    setPlayheadTick(tickAt(observedAt));
    // A frame already dequeued when the cleanup runs escapes
    // cancelAnimationFrame; the flag is what stops it rescheduling.
    let cancelled = false;
    let animationFrame = window.requestAnimationFrame(function advance(now) {
      if (cancelled) return;
      setPlayheadTick(tickAt(now));
      animationFrame = window.requestAnimationFrame(advance);
    });
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(animationFrame);
    };
  }, [originFrame, lengthTicks, bpm]);
  return (
    <div className="sequence-overview" data-testid="sequence-overview">
      {thumbnail !== null ? (
        <svg
          className="sequence-overview-thumbnail"
          data-testid="sequence-pattern-overview"
          viewBox={`0 0 ${thumbnail.lengthTicks} ${thumbnail.rowCount}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Pattern overview"
        >
          {thumbnail.notes.map((note) => (
            <rect
              className="sequence-overview-note"
              data-testid="sequence-overview-note"
              data-row={note.row}
              data-onset-tick={note.onsetTick}
              data-duration-tick={note.durationTick}
              data-velocity={note.velocity}
              key={`${note.row}:${note.onsetTick}`}
              x={note.onsetTick}
              y={note.row}
              width={note.durationTick}
              height={1}
            />
          ))}
          {viewport === null ? null : (
            <rect
              className="sequence-overview-frame"
              data-testid="sequence-overview-frame"
              x={viewport.startTick}
              y={bank * 16}
              width={Math.max(1, viewport.endTick - viewport.startTick)}
              height={16}
            />
          )}
          {playheadTick === null ? null : (
            <line
              className="sequence-overview-playhead"
              data-testid="sequence-playhead"
              data-playhead
              x1={playheadTick}
              x2={playheadTick}
              y1={0}
              y2={thumbnail.rowCount}
            />
          )}
        </svg>
      ) : null}
      <dl className="overview-facts">
        <div>
          <dt>Quantize</dt>
          <dd>{project?.sequenceSettings.quantizeEnabled === true ? "on" : "off"}</dd>
        </div>
        <div>
          <dt>Swing</dt>
          <dd>{project ? `${project.sequenceSettings.swingPercent}%` : "—"}</dd>
        </div>
        <div>
          <dt>Pattern</dt>
          <dd>
            {pattern === undefined
              ? "—"
              : `${pattern.bars} ${pattern.bars === 1 ? "bar" : "bars"}`}
          </dd>
        </div>
        <div>
          <dt>Phase</dt>
          <dd>{phase}</dd>
        </div>
        <div>
          <dt>Selected</dt>
          <dd>0</dd>
        </div>
        <div>
          <dt>Snap</dt>
          <dd>{snap}</dd>
        </div>
        <div>
          <dt>Velocity</dt>
          <dd>—</dd>
        </div>
        {pendingPatternId !== null ? (
          <div>
            <dt>Pending</dt>
            <dd>{pendingPatternId.slice(0, 8)}</dd>
          </div>
        ) : null}
        {state.recovery.length > 0 ? (
          <div>
            <dt>Recovery</dt>
            <dd>{state.recovery.length}</dd>
          </div>
        ) : null}
      </dl>
      {transport?.status?.publicationPending === true ? (
        <p>Committed, publication pending</p>
      ) : null}
      {state.errorCode !== null ? (
        <p>{userMessage(state.errorCode).message}</p>
      ) : null}
      {transport?.errorCode !== null && transport?.errorCode !== undefined ? (
        <p>{userMessage(transport.errorCode).message}</p>
      ) : null}
    </div>
  );
}
