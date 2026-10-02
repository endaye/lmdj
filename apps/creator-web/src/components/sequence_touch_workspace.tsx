import {userMessage} from "../state/error_messages";
import {useEffect, useRef, useState} from "react";

import {ValueSlider} from "./value_slider";
import {createTapTempo, type TapTempo} from "../runtime/tap_tempo";
import type {ProjectView, SequenceRecoveryCandidate} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import type {SequenceState} from "../state/sequence_state";
import type {SequenceGridSnap, SequenceGridViewport} from "../state/sequence_grid_model";
import {
  selectTransportBusy,
  selectTransportPlaying,
  selectTransportRecording,
  type PatternTransportState,
} from "../state/pattern_transport_state";
import {SequenceGrid} from "./sequence_grid";

const BAR_COUNTS = [1, 2, 4, 8] as const;
const NOOP = () => {};

interface SequenceTouchWorkspaceProps {
  project: ProjectView;
  state: SequenceState;
  transport: PatternTransportState;
  bank: Bank;
  snap: SequenceGridSnap;
  showRefresh?: boolean;
  onRefresh(): void;
  onSwitch(patternId: string): void;
  onCreatePattern(bars: 1 | 2 | 4 | 8): void;
  onSnapChange(snap: SequenceGridSnap): void;
  onViewportChange(viewport: SequenceGridViewport): void;
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
  const [recoveryTargets, setRecoveryTargets] = useState<Readonly<Record<string, string>>>({});
  const tapTempoRef = useRef<TapTempo | null>(null);
  // Step/TAP commits round-trip through the Host before the committed props
  // catch up. Deriving each step from the last requested value instead of the
  // committed prop keeps rapid clicks from collapsing into one increment; a
  // failed commit resyncs the base to the committed truth.
  const requestedBpmRef = useRef<number | null>(null);
  const requestedSwingRef = useRef<number | null>(null);
  const disabled = selectTransportBusy(transport) || selectTransportRecording(transport);
  const selectedPatternId = state.selectedPatternId ?? project.patternId;
  const selectedPattern = project.patterns.find(
    (item) => item.patternId === selectedPatternId);
  const patternIndex = project.patterns.findIndex((item) => item.patternId === selectedPatternId) + 1;
  const bpm = project.bpm;
  const swing = project.sequenceSettings.swingPercent;
  useEffect(() => {
    if (requestedBpmRef.current === project.bpm) requestedBpmRef.current = null;
  }, [project.bpm]);
  useEffect(() => {
    if (requestedSwingRef.current === swing) requestedSwingRef.current = null;
  }, [swing]);
  useEffect(() => {
    if (state.errorCode !== null) {
      requestedBpmRef.current = null;
      requestedSwingRef.current = null;
    }
  }, [state.errorCode]);
  const requestBpm = (next: number) => {
    requestedBpmRef.current = next;
    props.onSettingsChange({bpm: next});
  };
  const requestSwing = (next: number) => {
    requestedSwingRef.current = next;
    props.onSettingsChange({swingPercent: next});
  };
  const tapTempo = () => {
    tapTempoRef.current ??= createTapTempo(() => performance.now());
    const tapped = tapTempoRef.current.tap();
    if (tapped !== null) requestBpm(tapped);
  };
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
          <div className="sequence-param-card sequence-param-tempo">
            <ValueSlider
              label="TEMPO"
              ariaLabel="BPM"
              className="sequence-param-slider"
              value={bpm}
              min={40}
              max={240}
              step={1}
              format={(value) => `${value} BPM`}
              disabled={disabled}
              onPreview={NOOP}
              onCommit={requestBpm}
              onCancel={NOOP}
            />
            <div className="sequence-param-actions" role="group" aria-label="Tempo actions">
              <button type="button" aria-label="Decrease BPM"
                disabled={disabled || (requestedBpmRef.current ?? bpm) <= 40}
                onClick={() => requestBpm((requestedBpmRef.current ?? bpm) - 1)}>−</button>
              <button type="button" aria-label="Tap Tempo"
                disabled={disabled}
                onClick={tapTempo}>TAP</button>
              <button type="button" aria-label="Increase BPM"
                disabled={disabled || (requestedBpmRef.current ?? bpm) >= 240}
                onClick={() => requestBpm((requestedBpmRef.current ?? bpm) + 1)}>+</button>
            </div>
          </div>
          <div className="sequence-param-card sequence-param-swing">
            <ValueSlider
              label="SWING"
              ariaLabel="Swing"
              className="sequence-param-slider"
              value={swing}
              min={50}
              max={75}
              step={1}
              format={(value) => `${value}%`}
              disabled={disabled}
              onPreview={NOOP}
              onCommit={requestSwing}
              onCancel={NOOP}
            />
            <div className="sequence-param-actions" role="group" aria-label="Swing actions">
              <button type="button" aria-label="Decrease Swing"
                disabled={disabled || (requestedSwingRef.current ?? swing) <= 50}
                onClick={() => requestSwing((requestedSwingRef.current ?? swing) - 1)}>−</button>
              <button type="button" aria-label="Increase Swing"
                disabled={disabled || (requestedSwingRef.current ?? swing) >= 75}
                onClick={() => requestSwing((requestedSwingRef.current ?? swing) + 1)}>+</button>
            </div>
          </div>
        </div>
        {selectTransportRecording(transport) ? (
          <p className="sequence-settings-hint">
            Tempo and Swing are locked while recording
          </p>
        ) : null}
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
      {selectedPattern === undefined ? null : (
        <SequenceGrid
          pattern={selectedPattern}
          bank={props.bank}
          snap={props.snap}
          onSnapChange={props.onSnapChange}
          onViewportChange={props.onViewportChange}
        />
      )}
      {state.recovery.length > 0 ? (
        <section aria-label="Sequence recovery">
          <h2>Recovery</h2>
          {state.recovery.map((candidate) => (
            <article key={candidate.sessionId}>
              <p>{candidate.reason} · {candidate.eventCount} events</p>
              <button type="button" onClick={() => props.onRecover(candidate, null)}>
                Recover original Pattern
              </button>
              {/* #1680: restoring into another Pattern is the uncommon choice. */}
              <details className="sequence-recovery-more">
                <summary>More</summary>
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
              </details>
              <button type="button" onClick={() => props.onDiscard(candidate)}>Discard</button>
            </article>
          ))}
        </section>
      ) : null}
      {state.errorCode !== null ? (
        <p role="alert" className="sequence-error">
          {userMessage(state.errorCode).message} {userMessage(state.errorCode).nextStep}
        </p>
      ) : null}
      {props.showRefresh === false || transport.errorCode === null ? null : (
        <p role="alert" className="sequence-error">
          {userMessage(transport.errorCode).message} {userMessage(transport.errorCode).nextStep}
        </p>
      )}
    </section>
  );
}
