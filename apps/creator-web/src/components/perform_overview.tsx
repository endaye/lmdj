import type {CreatorState} from "../state/creator_state";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {SEQUENCE_TICKS_PER_BAR, SEQUENCE_TICKS_PER_BEAT} from "../state/sequence_grid_model";
import {transportStatusLabel} from "./transport_status";
import {usePatternPlayheadTick} from "./use_pattern_playhead";

const BANK_LABELS = ["A", "B", "C", "D"] as const;

interface PerformOverviewProps {
  state: CreatorState;
  transport?: PatternTransportState;
}

const two = (value: number) => String(value).padStart(2, "0");

// D04's upper screen is read-only: the transport's BPM and state, the
// playing Pattern's bar and beat with a progress strip, and the Bank,
// Quantize and assigned-slot facts. The bar and beat come from the transport
// frames, as on Sequence. The pictured output meters have no projection and
// are not drawn.
// The playhead's tick within the playing Pattern. A tick observed before a
// Pattern length change can outlast it by one render, so it is held inside
// the new length rather than overrunning the counter and the progress strip.
export function performPosition(tick: number | null, lengthTicks: number | null): number {
  if (tick === null || lengthTicks === null) return 0;
  return Math.min(Math.max(tick, 0), lengthTicks - 1);
}

export function PerformOverview({state, transport}: PerformOverviewProps) {
  const project = state.project.current;
  const assigned = project === null
    ? null
    : project.patternSlots.filter((slot) => slot !== null).length;
  const pattern = project?.patterns.find((item) => item.patternId === project.patternId);
  const bars = pattern?.bars ?? 1;
  const lengthTicks = pattern === undefined ? null : bars * SEQUENCE_TICKS_PER_BAR;
  const tick = usePatternPlayheadTick(transport, project?.bpm ?? null, lengthTicks);
  const at = performPosition(tick, lengthTicks);
  const bar = Math.floor(at / SEQUENCE_TICKS_PER_BAR) + 1;
  const beat = Math.floor((at % SEQUENCE_TICKS_PER_BAR) / SEQUENCE_TICKS_PER_BEAT) + 1;
  const label = transport === undefined ? "stopped" : transportStatusLabel(transport);
  return (
    <div className="perform-overview" data-testid="perform-overview">
      <p className="perform-overview-state">
        {label.toUpperCase()}
      </p>
      <p className="perform-overview-counter" data-testid="perform-counter">
        BAR {two(bar)} / {two(bars)} · BEAT {two(beat)} / 04
      </p>
      <div className="perform-overview-progress" role="progressbar" aria-label="Pattern position"
        aria-valuemin={0} aria-valuemax={lengthTicks ?? 1} aria-valuenow={at}>
        <span style={{width: `${lengthTicks === null ? 0 : at / lengthTicks * 100}%`}} />
      </div>
      <dl className="overview-facts perform-overview-facts">
        <div>
          <dt>Bank</dt>
          <dd>{BANK_LABELS[state.activeBank]}</dd>
        </div>
        <div>
          <dt>Transport</dt>
          <dd>{label}</dd>
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
    </div>
  );
}
