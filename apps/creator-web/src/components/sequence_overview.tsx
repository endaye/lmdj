import {useMemo} from "react";

import {userMessage} from "../state/error_messages";
import type {ProjectView} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import type {SequenceState} from "../state/sequence_state";
import {
  createSequenceOverviewWindow,
  SEQUENCE_OVERVIEW_HEIGHT,
  SEQUENCE_OVERVIEW_ROW_HEIGHT,
  SEQUENCE_OVERVIEW_ROW_PITCH,
  SEQUENCE_ROW_COUNT,
  SEQUENCE_BANK_PADS,
  SEQUENCE_TICKS_PER_BEAT,
  sequenceBarBeat,
  sequenceGridSelectionVelocity,
  sequenceOverviewFrame,
  type SequenceGridEventKey,
  type SequenceGridSnap,
  type SequenceGridViewport,
} from "../state/sequence_grid_model";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {padColourAttribute, padColourOf} from "../state/pad_colour";
import {bankName, slotAddress} from "../state/view_model";
import {transportStatusLabel} from "./transport_status";
import {usePatternPlayheadTick} from "./use_pattern_playhead";

interface SequenceOverviewProps {
  project: ProjectView | null;
  state: SequenceState;
  transport?: PatternTransportState;
  bank: Bank;
  snap: SequenceGridSnap;
  viewport: SequenceGridViewport | null;
  selection: readonly SequenceGridEventKey[];
  // First of the eight overview rows (0–56); defaults to the Bank's first row.
  rowOffset?: number;
  currentPad?: number;
}


export function SequenceOverview({
  project,
  state,
  transport,
  bank,
  snap,
  viewport,
  selection,
  currentPad,
  rowOffset = bank * SEQUENCE_BANK_PADS,
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
  const overview = useMemo(() => pattern === undefined
    ? null
    : createSequenceOverviewWindow(pattern, {rowOffset, snap}), [pattern, rowOffset, snap]);
  const selectionVelocity = pattern === undefined
    ? null
    : sequenceGridSelectionVelocity(pattern, selection);
  const bpm = project?.bpm ?? null;
  const playheadTick = usePatternPlayheadTick(transport, bpm, overview?.lengthTicks ?? null);
  // Step cells change only with the window's geometry, so the playhead's
  // per-frame render reuses the same elements.
  const cells = useMemo(() => overview === null ? null : overview.rows.flatMap((_, windowRow) =>
    Array.from({length: overview.stepCount}, (_, step) => {
      const startTick = step * overview.stepTicks;
      const beat = Math.floor(startTick / SEQUENCE_TICKS_PER_BEAT) % 2 === 0 ? "even" : "odd";
      return (
        <rect
          className={`sequence-overview-cell is-${beat}`}
          key={`${windowRow}:${step}`}
          x={startTick}
          y={windowRow * SEQUENCE_OVERVIEW_ROW_PITCH}
          width={overview.stepTicks * 0.84}
          height={SEQUENCE_OVERVIEW_ROW_HEIGHT}
        />
      );
    })), [overview]);
  const frame = overview === null || viewport === null
    ? null
    : sequenceOverviewFrame(viewport, bank, overview.rowOffset);
  const firstRow = overview?.rowOffset ?? rowOffset;
  const lastRow = firstRow + (overview?.rows.length ?? 8) - 1;
  const transportLabel = transport === undefined ? "stopped" : transportStatusLabel(transport);
  const bars = pattern?.bars ?? null;
  return (
    <div className="sequence-overview" data-testid="sequence-overview">
      <p className="sequence-overview-position" data-testid="sequence-position">
        {transportLabel.toUpperCase()} / {sequenceBarBeat(playheadTick)}
      </p>
      {/* One context line: a status, when there is one, takes its place. */}
      {statusLine !== null ? (
        <p className="sequence-overview-status">{statusLine}</p>
      ) : (
      <dl className="sequence-overview-context">
        <div>
          <dt>Bars</dt>
          <dd>{bars === null ? "—" : `01–${String(bars).padStart(2, "0")}`}</dd>
        </div>
        <div>
          <dt>Steps</dt>
          <dd>{overview === null ? "—" : overview.stepCount}</dd>
        </div>
        <div>
          <dt>Snap</dt>
          <dd>{snap}</dd>
        </div>
        <div>
          <dt>Tracks</dt>
          <dd>{`${slotAddress(firstRow)}–${slotAddress(lastRow)} / ${SEQUENCE_ROW_COUNT}`}</dd>
        </div>
        <div>
          <dt>Bank</dt>
          <dd>{bankName(bank)}</dd>
        </div>
        {currentPad === undefined ? null : (
          <div><dt>Pad</dt><dd>{slotAddress(currentPad)}</dd></div>
        )}
        {selection.length > 0 ? (
          <>
            <div>
              <dt>Selected</dt>
              <dd>{selection.length}</dd>
            </div>
            <div>
              <dt>Velocity</dt>
              <dd>{selectionVelocity === null ? "—" : selectionVelocity}</dd>
            </div>
          </>
        ) : null}
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
      )}
      {overview !== null ? (
        <div className="sequence-overview-rows">
          <ol className="sequence-overview-names" aria-hidden="true">
            {overview.rows.map((row) => (
              <li key={row} data-row={row}
                data-current-pad={currentPad === row ? "true" : undefined}
                data-pad-colour={padColourAttribute(padColourOf(project, row))}>
                {slotAddress(row)}
              </li>
            ))}
          </ol>
          <svg
            className="sequence-overview-steps"
            data-testid="sequence-pattern-overview"
            viewBox={`0 0 ${overview.lengthTicks} ${SEQUENCE_OVERVIEW_HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`Pattern overview, ${slotAddress(firstRow)} to ${slotAddress(lastRow)}`}
          >
            {cells}
            {overview.notes.map((note) => (
              <g
                className="sequence-overview-note"
                data-testid="sequence-overview-note"
                data-row={note.row}
                data-pad-colour={padColourAttribute(padColourOf(project, note.row))}
                data-onset-tick={note.onsetTick}
                data-duration-tick={note.durationTick}
                data-velocity={note.velocity}
                key={`${note.row}:${note.onsetTick}`}
              >
                <rect
                  className="sequence-overview-onset"
                  x={note.onsetStepTick}
                  y={note.windowRow * SEQUENCE_OVERVIEW_ROW_PITCH}
                  width={overview.stepTicks * 0.84}
                  height={SEQUENCE_OVERVIEW_ROW_HEIGHT}
                />
                {note.tailEndTick > note.tailStartTick ? (
                  <rect
                    className="sequence-overview-tail"
                    x={note.tailStartTick}
                    y={note.windowRow * SEQUENCE_OVERVIEW_ROW_PITCH}
                    width={note.tailEndTick - note.tailStartTick - overview.stepTicks * 0.16}
                    height={SEQUENCE_OVERVIEW_ROW_HEIGHT}
                  />
                ) : null}
              </g>
            ))}
            {frame === null ? null : (
              <rect
                className="sequence-overview-frame"
                data-testid="sequence-overview-frame"
                x={frame.startTick}
                y={frame.firstWindowRow * SEQUENCE_OVERVIEW_ROW_PITCH}
                width={Math.max(1, frame.endTick - frame.startTick)}
                height={frame.rowCount * SEQUENCE_OVERVIEW_ROW_PITCH -
                  (SEQUENCE_OVERVIEW_ROW_PITCH - SEQUENCE_OVERVIEW_ROW_HEIGHT)}
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
                y2={SEQUENCE_OVERVIEW_HEIGHT}
              />
            )}
          </svg>
        </div>
      ) : null}
    </div>
  );
}
