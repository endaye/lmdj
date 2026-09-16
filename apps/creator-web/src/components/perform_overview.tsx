import type {CreatorState} from "../state/creator_state";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {transportStatusLabel} from "./sequence_transport";

const BANK_LABELS = ["A", "B", "C", "D"] as const;

interface PerformOverviewProps {
  state: CreatorState;
  transport?: PatternTransportState;
}

// D04's upper screen is read-only. It pictures output meters, a bar/beat
// counter and named sections; the Host projects none of those, so this shows
// only facts it already holds.
export function PerformOverview({state, transport}: PerformOverviewProps) {
  const project = state.project.current;
  const assigned = project === null
    ? null
    : project.patternSlots.filter((slot) => slot !== null).length;
  return (
    <div className="perform-overview" data-testid="perform-overview">
      <dl className="overview-facts">
        <div>
          <dt>Bank</dt>
          <dd>{BANK_LABELS[state.activeBank]}</dd>
        </div>
        <div>
          <dt>Transport</dt>
          <dd>{transport === undefined ? "—" : transportStatusLabel(transport)}</dd>
        </div>
        <div>
          <dt>Quantize</dt>
          <dd>{project?.sequenceSettings.quantizeEnabled === true ? "on" : "off"}</dd>
        </div>
        <div>
          <dt>Slots</dt>
          <dd>{assigned === null ? "—" : `${assigned} assigned`}</dd>
        </div>
      </dl>
      <p className="overview-grid-caption">
        Launch, HOLD, confirmed FX, performance record/save/discard and
        replay/resample live in the touch workspace. Pictured LP/HP/BP are
        not Host controls.
      </p>
    </div>
  );
}
