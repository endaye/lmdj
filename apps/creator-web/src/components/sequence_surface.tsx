import {useEffect, useState} from "react";

import type {ProjectView, SequenceRecoveryCandidate} from "../runtime/runtime_types";
import type {SequenceState} from "../state/sequence_state";
import {
  selectTransportBusy,
  selectTransportPlaying,
  selectTransportRecording,
  type PatternTransportState,
} from "../state/pattern_transport_state";
import {SequenceTransport} from "./sequence_transport";

interface SequenceSurfaceProps {
  project: ProjectView;
  state: SequenceState;
  transport: PatternTransportState;
  ready: boolean;
  onPlayStop(): void;
  onRecord(): void;
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

export function SequenceSurface(props: SequenceSurfaceProps) {
  const {project, state, transport} = props;
  const [bars, setBars] = useState<1 | 2 | 4 | 8>(1);
  const [bpm, setBpm] = useState(project.bpm);
  const [swing, setSwing] = useState(project.sequenceSettings.swingPercent);
  const [recoveryTargets, setRecoveryTargets] = useState<Readonly<Record<string, string>>>({});
  // Settings forms lock while a transport operation is in flight and while the
  // runtime rejects them (recording); a committed Pattern publication is not a
  // reason to reopen them early.
  const disabled = selectTransportBusy(transport) || selectTransportRecording(transport);
  // Committed settings can change outside these forms (another form, a
  // recovered Sequence, a reopened Project); the editable copies follow them
  // so a stale draft is never applied by accident.
  useEffect(() => { setBpm(project.bpm); }, [project.bpm]);
  useEffect(() => {
    setSwing(project.sequenceSettings.swingPercent);
  }, [project.sequenceSettings.swingPercent]);
  return (
    <main className="sequence-surface" aria-label="Sequence">
      <header>
        <h1>Sequence</h1>
        <p>
          Project revision {project.revision} · {project.patterns.length}{" "}
          {project.patterns.length === 1 ? "Pattern" : "Patterns"}
        </p>
      </header>
      <SequenceTransport transport={transport} ready={props.ready}
        onPlayStop={props.onPlayStop} onRecord={props.onRecord} onRefresh={props.onRefresh} />
      <section aria-label="Sequence settings" className="sequence-settings">
        <label>Pattern
          <select value={state.selectedPatternId ?? project.patternId}
            disabled={disabled}
            onChange={(event) => props.onSwitch(event.currentTarget.value)}>
            {project.patterns.map((pattern) => (
              <option value={pattern.patternId} key={pattern.patternId}>
                {pattern.patternId.slice(0, 8)} · {pattern.bars}{" "}
                {pattern.bars === 1 ? "bar" : "bars"}
              </option>
            ))}
          </select>
        </label>
        <label>Quantize
          <input type="checkbox" checked={project.sequenceSettings.quantizeEnabled}
            disabled={disabled} onChange={(event) => props.onSettingsChange({
              quantizeEnabled: event.currentTarget.checked,
            })} />
        </label>
        <form onSubmit={(event) => {
          event.preventDefault();
          props.onSettingsChange({swingPercent: swing});
        }}>
          <label><span>Swing</span> <output>{project.sequenceSettings.swingPercent}%</output>
            <input type="range" min={50} max={75} step={1} aria-label="Swing"
              value={swing} disabled={disabled}
              onChange={(event) => setSwing(event.currentTarget.valueAsNumber)} />
          </label>
          <button type="submit" disabled={disabled}>Apply Swing</button>
        </form>
        <form onSubmit={(event) => {
          event.preventDefault();
          props.onSettingsChange({bpm});
        }}>
          <label>BPM
            <input type="number" min={40} max={240} value={bpm} disabled={disabled}
              onChange={(event) => setBpm(event.currentTarget.valueAsNumber)} />
          </label>
          <button type="submit" disabled={disabled || !Number.isInteger(bpm) ||
            bpm < 40 || bpm > 240}>Apply BPM</button>
        </form>
        <form onSubmit={(event) => {
          event.preventDefault();
          props.onCreatePattern(bars);
        }}>
          <label>Bars
            <select value={bars} disabled={disabled}
              onChange={(event) => setBars(Number(event.currentTarget.value) as 1 | 2 | 4 | 8)}>
              {[1, 2, 4, 8].map((count) => <option key={count} value={count}>{count}</option>)}
            </select>
          </label>
          <button type="submit" disabled={disabled || selectTransportPlaying(transport)}>
            Create Pattern
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
    </main>
  );
}
