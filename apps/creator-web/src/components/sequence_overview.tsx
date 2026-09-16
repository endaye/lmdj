import type {ProjectView} from "../runtime/runtime_types";
import type {SequenceState} from "../state/sequence_state";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {transportStatusLabel} from "./transport_status";

interface SequenceOverviewProps {
  project: ProjectView | null;
  state: SequenceState;
  transport?: PatternTransportState;
}

export function SequenceOverview({
  project,
  state,
  transport,
}: SequenceOverviewProps) {
  const selectedPatternId = state.selectedPatternId ?? project?.patternId ?? null;
  const pattern = selectedPatternId === null
    ? undefined
    : project?.patterns.find((item) => item.patternId === selectedPatternId);
  const pendingPatternId = state.status?.pendingPatternId ?? null;
  const phase = transport === undefined
    ? state.phase
    : transportStatusLabel(transport);
  return (
    <div className="sequence-overview" data-testid="sequence-overview">
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
        <p>{state.errorCode}</p>
      ) : null}
      {transport?.errorCode !== null && transport?.errorCode !== undefined ? (
        <p>{transport.errorCode}</p>
      ) : null}
      <p className="overview-grid-caption">
        Event grid is a live projection target; this overview does not edit it.
      </p>
    </div>
  );
}
