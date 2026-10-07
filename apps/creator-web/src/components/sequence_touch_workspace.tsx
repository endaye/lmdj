import {userMessage} from "../state/error_messages";
import {useEffect, useRef, useState} from "react";

import {ValueSlider} from "./value_slider";
import {createTapTempo, type TapTempo} from "../runtime/tap_tempo";
import type {ProjectView, SequenceRecoveryCandidate} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import type {SequenceState} from "../state/sequence_state";
import type {
  SequenceGridEdit,
  SequenceGridEditMode,
  SequenceGridEventKey,
  SequenceGridSnap,
  SequenceGridViewport,
} from "../state/sequence_grid_model";
import {
  selectTransportBusy,
  selectTransportPlaying,
  selectTransportRecording,
  type PatternTransportState,
} from "../state/pattern_transport_state";
import {SequenceGrid} from "./sequence_grid";
import {PatternStepper, TouchSegment, type TouchSegmentOption} from "./touch_kit";

const BAR_COUNTS = [1, 2, 4, 8] as const;
const BAR_OPTIONS: readonly TouchSegmentOption<1 | 2 | 4 | 8>[] = BAR_COUNTS.map((count) =>
  ({value: count, label: String(count), ariaLabel: `${count} bars`}));
type SequenceLayer = "edit" | "setup";
const LAYER_OPTIONS: readonly TouchSegmentOption<SequenceLayer>[] = [
  {value: "edit", label: "EDIT"},
  {value: "setup", label: "SETUP"},
];
const NOOP = () => {};

interface SequenceTouchWorkspaceProps {
  project: ProjectView;
  state: SequenceState;
  transport: PatternTransportState;
  bank: Bank;
  snap: SequenceGridSnap;
  editMode: SequenceGridEditMode;
  selection: readonly SequenceGridEventKey[];
  defaultVelocity: number;
  // True while the projection is being re-read from Truth after a commit; the
  // grid's model can be behind Truth in that window, so no gesture starts.
  projectionRefreshing: boolean;
  metronomeOn: boolean;
  onToggleMetronome(): void;
  showRefresh?: boolean;
  onRefresh(): void;
  onSwitch(patternId: string): void;
  onCreatePattern(bars: 1 | 2 | 4 | 8): void;
  onSnapChange(snap: SequenceGridSnap): void;
  onEditModeChange(mode: SequenceGridEditMode): void;
  onViewportChange(viewport: SequenceGridViewport): void;
  onEdit(edit: SequenceGridEdit): void;
  onSelectionChange(selection: readonly SequenceGridEventKey[]): void;
  onVelocityChange(velocity: number): void;
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
  // EDIT (the grid) is the default layer; SETUP holds the settings that are
  // set once and rarely touched (2026-10-04 decision, item 7). View state only.
  const [layer, setLayer] = useState<SequenceLayer>("edit");
  const [choosingLength, setChoosingLength] = useState(false);
  const [recoveryTargets, setRecoveryTargets] = useState<Readonly<Record<string, string>>>({});
  const tapTempoRef = useRef<TapTempo | null>(null);
  // Step/TAP commits round-trip through the Host before the committed props
  // catch up. Deriving each step from the last requested value instead of the
  // committed prop keeps rapid clicks from collapsing into one increment; a
  // failed commit resyncs the base to the committed truth.
  const requestedBpmRef = useRef<number | null>(null);
  const requestedSwingRef = useRef<number | null>(null);
  const disabled = selectTransportBusy(transport) || selectTransportRecording(transport);
  // Grid editing is refused while the transport records (the Core refuses it
  // too); a busy transport holds the commit instead, and the app retries it.
  const editReason = selectTransportRecording(transport)
    ? "Recording — stop recording to edit the grid."
    : null;
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
  const playing = selectTransportPlaying(transport);
  const stepPattern = (offset: -1 | 1) => {
    const next = project.patterns[patternIndex - 1 + offset];
    if (next !== undefined) props.onSwitch(next.patternId);
  };
  return (
    <section className="sequence-touch-workspace" aria-label="Sequence editor"
      data-layer={layer}>
      <header className="sequence-editor-header">
        {/* Switching Pattern waits for Stop, as the ← → keys do. */}
        <PatternStepper index={patternIndex} count={project.patterns.length}
          patternId={selectedPatternId} disabled={disabled || playing}
          onStep={stepPattern} />
        <TouchSegment<SequenceLayer> label="Layer" className="sequence-layer" options={LAYER_OPTIONS}
          value={layer} onChange={setLayer} />
      </header>
      {props.showRefresh === false || transport.status?.publicationPending !== true
        ? null
        : <p role="status">committed, publication pending</p>}
      {layer === "edit" ? (selectedPattern === undefined ? null : (
        <SequenceGrid
          pattern={selectedPattern}
          bank={props.bank}
          snap={props.snap}
          editMode={props.editMode}
          editing={{
            enabled: editReason === null && !props.projectionRefreshing,
            reason: editReason,
          }}
          selection={props.selection}
          defaultVelocity={props.defaultVelocity}
          onSnapChange={props.onSnapChange}
          onEditModeChange={props.onEditModeChange}
          onViewportChange={props.onViewportChange}
          onEdit={props.onEdit}
          onSelectionChange={props.onSelectionChange}
          onVelocityChange={props.onVelocityChange}
        />
      )) : (
      <section aria-label="Sequence settings" className="sequence-settings">
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
              <span className="sequence-param-encoder">ENC 3</span>
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
              <span className="sequence-param-encoder">ENC 4</span>
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
        {/* BARS is the current Pattern's length. Changing an existing
            Pattern's length waits for #1823, so it is read here only. */}
        <div className="sequence-setup-row" role="group" aria-label="Pattern length">
          <span>BARS</span>
          <output className="sequence-bars-value">
            {selectedPattern === undefined ? "—" : selectedPattern.bars}
          </output>
        </div>
        <div className="sequence-setup-row sequence-setup-toggles">
          <button type="button" className="touch-control" aria-label="Quantize"
            aria-pressed={project.sequenceSettings.quantizeEnabled}
            disabled={disabled} onClick={() => props.onSettingsChange({
              quantizeEnabled: !project.sequenceSettings.quantizeEnabled,
            })}>
            QUANTIZE
          </button>
          {/* The metronome is a monitoring switch, not a Transport setting:
              it must stay toggleable while recording. */}
          <button type="button" className="touch-control sequence-metronome"
            aria-label="Metronome"
            aria-pressed={props.metronomeOn}
            onClick={props.onToggleMetronome}>
            METRONOME
          </button>
        </div>
        {choosingLength ? (
          <form className="sequence-bars-form" onSubmit={(event) => {
            event.preventDefault();
            setChoosingLength(false);
            props.onCreatePattern(bars);
          }}>
            <TouchSegment<1 | 2 | 4 | 8> label="Bars" options={BAR_OPTIONS} value={bars}
              disabled={disabled} onChange={setBars} />
            <div className="sequence-setup-row sequence-setup-actions">
              <button type="button" className="touch-control"
                onClick={() => setChoosingLength(false)}>CANCEL</button>
              <button type="submit" className="touch-control is-primary" aria-label="Create Pattern"
                disabled={disabled || playing}>
                CREATE
              </button>
            </div>
          </form>
        ) : (
          <div className="sequence-setup-row sequence-setup-actions">
            <button type="button" className="touch-control" aria-label="New Pattern"
              aria-expanded={false} disabled={disabled || playing}
              onClick={() => setChoosingLength(true)}>
              + NEW
            </button>
            <button type="button" className="touch-control" aria-label="Tap Tempo"
              disabled={disabled}
              onClick={tapTempo}>TAP</button>
          </div>
        )}
        {props.showRefresh === false ? null : (
          <>
            <button type="button" className="touch-control" onClick={props.onRefresh}>
              Refresh authority
            </button>
            {transport.lastFailed !== null ? (
              <p className="transport-hint">
                Last {transport.lastFailed.intent === "record" ? "Record" : "Play/Stop"}
                {" "}command failed; retry reconciles the same command.
              </p>
            ) : null}
          </>
        )}
      </section>
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
