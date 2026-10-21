import {useSyncExternalStore} from "react";
import type {CreatorState} from "../state/creator_state";
import type {PerformController} from "../state/perform_state";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {SEQUENCE_TICKS_PER_BAR, SEQUENCE_TICKS_PER_BEAT} from "../state/sequence_grid_model";
import {transportStatusLabel} from "./transport_status";
import {usePatternPlayheadTick} from "./use_pattern_playhead";
import {StereoOutputMeter, type OutputMeterSource} from "./stereo_output_meter";

const BANK_LABELS = ["A", "B", "C", "D"] as const;

interface PerformOverviewProps {
  state: CreatorState;
  hideState?: boolean;
  selectedPatternId?: string | null;
  transport?: PatternTransportState;
  controller?: Pick<PerformController, "subscribe" | "getState"> | null;
  outputMeterSource?: OutputMeterSource | null;
}

const noSubscription = () => () => {};
const noPerformance = () => null;

const two = (value: number) => String(value).padStart(2, "0");

// D04's upper screen is read-only: the transport's BPM and state, the
// playing Pattern's bar and beat with a progress strip, and the Bank,
// Quantize and assigned-slot facts. The bar and beat come from the transport
// frames, as on Sequence. The output meter reads the separate measured SDK
// projection; neither Pattern nor Performance transport supplies its values.
// The playhead's tick within the playing Pattern. A tick observed before a
// Pattern length change can outlast it by one render, so it is held inside
// the new length rather than overrunning the counter and the progress strip.
export function performPosition(tick: number | null, lengthTicks: number | null): number {
  if (tick === null || lengthTicks === null) return 0;
  return Math.min(Math.max(tick, 0), lengthTicks - 1);
}

export function PerformOverview({state, hideState = false, selectedPatternId, transport, controller,
  outputMeterSource}: PerformOverviewProps) {
  // Observes the same producer as the touch surface. Read-only displays never
  // connect, stop or leave a Performance session.
  const performance = useSyncExternalStore(controller?.subscribe ?? noSubscription,
    controller?.getState ?? noPerformance, controller?.getState ?? noPerformance);
  const project = state.project.current;
  const assigned = project === null
    ? null
    : project.patternSlots.filter((slot) => slot !== null).length;
  const playingPatternId = transport?.status?.playing === true
    ? transport.status.currentPatternId : null;
  const patternId = playingPatternId ?? selectedPatternId ?? project?.patternId;
  const pattern = project?.patterns.find((item) => item.patternId === patternId);
  const bars = pattern?.bars ?? 1;
  const lengthTicks = pattern === undefined ? null : bars * SEQUENCE_TICKS_PER_BAR;
  const tick = usePatternPlayheadTick(transport, project?.bpm ?? null, lengthTicks);
  const at = performPosition(tick, lengthTicks);
  const bar = Math.floor(at / SEQUENCE_TICKS_PER_BAR) + 1;
  const beat = Math.floor((at % SEQUENCE_TICKS_PER_BAR) / SEQUENCE_TICKS_PER_BEAT) + 1;
  const label = transport === undefined ? "stopped" : transportStatusLabel(transport);
  // These columns share the global Pattern transport domain. Performance
  // launch acknowledgements are historical receipts, not a playback clock.
  const queuedTransportPatternId = transport?.status?.pendingSwitch?.patternId ?? null;
  const queuedTransportSlot = queuedTransportPatternId === null
    ? -1 : project?.patternSlots.indexOf(queuedTransportPatternId) ?? -1;
  const queuedTransportPattern = queuedTransportPatternId === null
    ? -1 : project?.patterns.findIndex((item) =>
      item.patternId === queuedTransportPatternId) ?? -1;
  const playingSlot = playingPatternId === null ? -1 : project?.patternSlots.indexOf(playingPatternId) ?? -1;
  const playingIndex = playingPatternId === null ? -1 : project?.patterns.findIndex(
    item => item.patternId === playingPatternId) ?? -1;
  const playingLabel = playingPatternId === null ? "—"
    : playingSlot >= 0 ? `SLOT ${two(playingSlot + 1)}`
      : playingIndex >= 0 ? `PATTERN ${two(playingIndex + 1)}` : "UNAVAILABLE";
  const queuedLabel = queuedTransportSlot >= 0 ? `SLOT ${two(queuedTransportSlot + 1)}`
      : queuedTransportPatternId !== null
        ? `PATTERN ${queuedTransportPattern < 0 ? "—" : two(queuedTransportPattern + 1)}` : "—";
  return (
    <div className="perform-overview" data-testid="perform-overview">
      <p className={`perform-overview-state${hideState ? " visually-hidden" : ""}`}>
        {label.toUpperCase()}
      </p>
      <dl className="perform-overview-columns">
        <div><dt>PATTERN PLAYING</dt><dd data-testid="perform-playing">{playingLabel}</dd></div>
        <div><dt>PATTERN QUEUED</dt><dd data-testid="perform-queued">{queuedLabel}</dd></div>
        <div><dt>PATTERN POSITION</dt><dd data-testid="perform-counter" className="perform-overview-counter">
          {pattern === undefined ? "—" : <><span>BAR {two(bar)} / {two(bars)} · </span>
            <span>BEAT {two(beat)} / 04</span></>}
        </dd></div>
        <div><dt>BANK / QUANTIZE</dt><dd>
          <output aria-label="Bank">{BANK_LABELS[state.activeBank]}</output> / {""}
          <output aria-label="Quantize">{project === null ? "—"
            : project.sequenceSettings.quantizeEnabled ? "ON" : "OFF"}</output>
        </dd></div>
      </dl>
      <StereoOutputMeter source={outputMeterSource ?? null} projectId={project?.projectId ?? null}
        running={state.audio.phase === "running" && state.project.phase === "ready"} />
      <output className="perform-overview-launch" aria-label="Pattern launch cue" aria-live="polite">
        {performance?.lastLaunchAck == null ? "LAST LAUNCH —" :
          `ACKNOWLEDGED SLOT ${two(performance.lastLaunchAck.patternSlot + 1)}`}
        {performance?.pendingLaunch != null
          ? ` → QUEUED SLOT ${two(performance.pendingLaunch.patternSlot + 1)}`
          : queuedTransportSlot >= 0
            ? ` → QUEUED SLOT ${two(queuedTransportSlot + 1)}`
            : queuedTransportPatternId !== null
              ? ` → QUEUED PATTERN ${queuedTransportPattern < 0
                ? "—" : two(queuedTransportPattern + 1)}`
              : " · NOTHING QUEUED"}
      </output>
      <div className="perform-overview-progress" role="progressbar" aria-label="Pattern position"
        aria-valuemin={0} aria-valuemax={lengthTicks ?? 1} aria-valuenow={at}>
        <span style={{width: `${lengthTicks === null ? 0 : at / lengthTicks * 100}%`}} />
      </div>
      <dl className="overview-facts perform-overview-facts">
        <div>
          <dt>Performance</dt>
          <dd>{performance?.recording.phase ?? "unavailable"}</dd>
        </div>
        <div>
          <dt>Slots</dt>
          <dd>{assigned === null ? "—" : `${assigned} assigned`}</dd>
        </div>
      </dl>
    </div>
  );
}
