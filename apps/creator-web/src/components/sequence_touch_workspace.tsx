import {useEffect, useState} from "react";

import type {ProjectView, SequenceRecoveryCandidate} from "../runtime/runtime_types";
import type {SequenceState} from "../state/sequence_state";
import {
  selectTransportBusy,
  selectTransportPlaying,
  selectTransportRecording,
  type PatternTransportState,
} from "../state/pattern_transport_state";

const BAR_COUNTS = [1, 2, 4, 8] as const;

interface SequenceTouchWorkspaceProps {
  project: ProjectView;
  state: SequenceState;
  transport: PatternTransportState;
  showRefresh?: boolean;
  onRefresh(): void;
  onSwitch(patternId: string): void;
  onCreatePattern(bars: 1 | 2 | 4 | 8): void;
  onSettingsChange(changes: Readonly<{
    bpm?: number;
    quantizeEnabled?: boolean;
    swingPercent?: number;
  }>): void;
  onRecover(candidate: SequenceRecoveryCandidate, destinationPatternId: string | null): void;
  onDiscard(candidate: SequenceRecoveryCandidate): void;
}

export function SequenceTouchWorkspace(props: SequenceTouchWorkspaceProps) {
  const {project, state, transport} = props;
  const [bars, setBars] = useState<1 | 2 | 4 | 8>(1);
  const [bpm, setBpm] = useState(project.bpm);
  const [swing, setSwing] = useState(project.sequenceSettings.swingPercent);
  const [recoveryTargets, setRecoveryTargets] = useState<Readonly<Record<string, string>>>({});
  const disabled = selectTransportBusy(transport) || selectTransportRecording(transport);
  const selectedPatternId = state.selectedPatternId ?? project.patternId;
  const patternIndex = project.patterns.findIndex((item) => item.patternId === selectedPatternId) + 1;
  useEffect(() => { setBpm(project.bpm); }, [project.bpm]);
  useEffect(() => {
    setSwing(project.sequenceSettings.swingPercent);
  }, [project.sequenceSettings.swingPercent]);
  return (
    <section className="sequence-touch-workspace" aria-label="Sequence editor">
      <header className="sequence-editor-header">
        <h1>GROOVE / {String(Math.max(patternIndex, 1)).padStart(2, "0")}</h1>
        <p className="sequence-editor-mode">SEQUENCE</p>
      </header>
      {props.showRefresh === false || transport.status?.publicationPending !== true
        ? null
        : <p role="status">committed, publication pending</p>}
      {props.showRefresh === false ? null : (
        <>
          <button type="button" onClick={props.onRefresh}>Refresh authority</button>
          {transport.lastFailed !== null ? (
            <p className="transport-hint">
              Last {transport.lastFailed.intent === "record" ? "Record" : "Play/Stop"}
              {" "}command failed; retry reconciles the same command.
            </p>
          ) : null}
        </>
      )}
      <section aria-label="Sequence settings" className="sequence-settings">
        <label className="sequence-pattern-select">Pattern
          <select value={selectedPatternId}
            disabled={disabled}
            onChange={(event) => props.onSwitch(event.currentTarget.value)}>
            {project.patterns.map((pattern, index) => (
              <option value={pattern.patternId} key={pattern.patternId}>
                {String(index + 1).padStart(2, "0")} · {pattern.bars}{" "}
                {pattern.bars === 1 ? "bar" : "bars"}
              </option>
            ))}
          </select>
        </label>
        <div className="sequence-param-row">
          <form className="sequence-param-card sequence-param-tempo" onSubmit={(event) => {
            event.preventDefault();
            props.onSettingsChange({bpm});
          }}>
            <p>TEMPO</p>
            <output htmlFor="sequence-tempo">{bpm} BPM</output>
            <input id="sequence-tempo" type="range" min={40} max={240} step={1}
              aria-label="BPM" value={bpm} disabled={disabled}
              onChange={(event) => setBpm(event.currentTarget.valueAsNumber)} />
            <button type="submit" disabled={disabled || !Number.isInteger(bpm) ||
              bpm < 40 || bpm > 240}>Apply BPM</button>
          </form>
          <form className="sequence-param-card sequence-param-swing" onSubmit={(event) => {
            event.preventDefault();
            props.onSettingsChange({swingPercent: swing});
          }}>
            <p>SWING</p>
            <output htmlFor="sequence-swing">{swing}%</output>
            <input id="sequence-swing" type="range" min={50} max={75} step={1} aria-label="Swing"
              value={swing} disabled={disabled}
              onChange={(event) => setSwing(event.currentTarget.valueAsNumber)} />
            <button type="submit" disabled={disabled}>Apply Swing</button>
          </form>
        </div>
        <form className="sequence-bars-form" onSubmit={(event) => {
          event.preventDefault();
          props.onCreatePattern(bars);
        }}>
          <div className="sequence-segment" role="group" aria-label="Bars">
            <span>BARS</span>
            {BAR_COUNTS.map((count) => (
              <button
                key={count}
                type="button"
                aria-pressed={bars === count}
                aria-label={`${count} bars`}
                disabled={disabled}
                onClick={() => setBars(count)}
              >
                {count}
              </button>
            ))}
          </div>
          <label className="sequence-quantize">Quantize
            <input type="checkbox" checked={project.sequenceSettings.quantizeEnabled}
              disabled={disabled} onChange={(event) => props.onSettingsChange({
                quantizeEnabled: event.currentTarget.checked,
              })} />
          </label>
          <button type="submit" aria-label="Create Pattern"
            disabled={disabled || selectTransportPlaying(transport)}>
            + NEW
          </button>
        </form>
      </section>
      {state.recovery.length > 0 ? (
        <section aria-label="Sequence recovery">
          <h2>Recovery</h2>
          {state.recovery.map((candidate) => (
            <article key={candidate.sessionId}>
              <p>{candidate.reason} · {candidate.eventCount} events</p>
              <button type="button" onClick={() => props.onRecover(candidate, null)}>
                Recover original Pattern
              </button>
              <label>Recovery destination
                <select aria-label={`Recovery destination ${candidate.sessionId}`}
                  value={recoveryTargets[candidate.sessionId] ?? ""}
                  onChange={(event) => setRecoveryTargets((current) => ({
                    ...current,
                    [candidate.sessionId]: event.currentTarget.value,
                  }))}>
                  <option value="">Select another Pattern</option>
                  {project.patterns.filter(({patternId}) => patternId !== candidate.patternId)
                    .map(({patternId}) => (
                      <option key={patternId} value={patternId}>{patternId.slice(0, 8)}</option>
                    ))}
                </select>
              </label>
              <button type="button" disabled={!recoveryTargets[candidate.sessionId]}
                onClick={() => props.onRecover(
                  candidate,
                  recoveryTargets[candidate.sessionId] ?? null,
                )}>
                Recover to selected Pattern
              </button>
              <button type="button" onClick={() => props.onDiscard(candidate)}>Discard</button>
            </article>
          ))}
        </section>
      ) : null}
      {state.errorCode !== null ? (
        <p role="alert" className="sequence-error">{state.errorCode}</p>
      ) : null}
      {props.showRefresh === false || transport.errorCode === null ? null : (
        <p role="alert" className="sequence-error">{transport.errorCode}</p>
      )}
    </section>
  );
}
