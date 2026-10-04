import {useEffect, useState} from "react";

import {userMessage} from "../state/error_messages";
import type {ProjectView} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import type {SequenceState} from "../state/sequence_state";
import {
  createSequenceGridThumbnail,
  sequenceGridSelectionVelocity,
  sequencePlayheadTick,
  type SequenceGridEventKey,
  type SequenceGridSnap,
  type SequenceGridViewport,
} from "../state/sequence_grid_model";
import type {PatternTransportState} from "../state/pattern_transport_state";

interface SequenceOverviewProps {
  project: ProjectView | null;
  state: SequenceState;
  transport?: PatternTransportState;
  bank: Bank;
  snap: SequenceGridSnap;
  viewport: SequenceGridViewport | null;
  selection: readonly SequenceGridEventKey[];
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
  selection,
}: SequenceOverviewProps) {
  const selectedPatternId = state.selectedPatternId ?? project?.patternId ?? null;
  const pattern = selectedPatternId === null
    ? undefined
    : project?.patterns.find((item) => item.patternId === selectedPatternId);
  const pendingPatternId = state.status?.pendingPatternId ?? null;
  // The 176 px display holds one status line: the most severe of the
  // transport error, the Sequence error and a pending publication.
  const statusLine = transport?.errorCode !== null && transport?.errorCode !== undefined
    ? userMessage(transport.errorCode).message
    : state.errorCode !== null
      ? userMessage(state.errorCode).message
      : transport?.status?.publicationPending === true
        ? "Committed, publication pending"
        : null;
  const thumbnail = pattern === undefined ? null : createSequenceGridThumbnail(pattern);
  const selectionVelocity = pattern === undefined
    ? null
    : sequenceGridSelectionVelocity(pattern, selection);
  const bpm = project?.bpm ?? null;
  const status = transport?.status ?? null;
  const playing = status !== null && status.playing === true &&
    thumbnail !== null && bpm !== null;
  const originFrame = playing && status !== null ? status.originFrame : null;
  // The last observed Runtime frame anchors the playhead, so remounting the
  // overview mid-playback (leaving Sequence and coming back) resumes at the
  // playing position instead of restarting at the origin.
  const anchorFrame = playing && status !== null ? status.runtimeFrame : null;
  const anchorObservedAt = playing && status !== null
    ? status.observedAtMilliseconds
    : null;
  const lengthTicks = thumbnail?.lengthTicks ?? null;
  const [playheadTick, setPlayheadTick] = useState<number | null>(null);
  useEffect(() => {
    if (originFrame === null || anchorFrame === null || anchorObservedAt === null ||
        lengthTicks === null || bpm === null) {
      setPlayheadTick(null);
      return;
    }
    const tickAt = (now: number) => sequencePlayheadTick({
      originFrame,
      runtimeFrame: anchorFrame +
        Math.floor(Math.max(0, now - anchorObservedAt) * FRAMES_PER_MILLISECOND),
      bpm,
      lengthTicks,
    });
    setPlayheadTick(tickAt(performance.now()));
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
  }, [originFrame, anchorFrame, anchorObservedAt, lengthTicks, bpm]);
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
      <div className="sequence-overview-side">
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
          <dt>Selected</dt>
          <dd>{selection.length}</dd>
        </div>
        <div>
          <dt>Snap</dt>
          <dd>{snap}</dd>
        </div>
        <div>
          <dt>Velocity</dt>
          <dd>{selectionVelocity === null ? "—" : selectionVelocity}</dd>
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
      {statusLine === null ? null : (
        <p className="sequence-overview-status">{statusLine}</p>
      )}
      </div>
    </div>
  );
}
