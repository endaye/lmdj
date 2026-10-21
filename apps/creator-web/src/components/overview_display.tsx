import type {EncoderBinding, EncoderPosition} from "./physical_controls";
import {type MidiStatus} from "./midi_status";
import {selectCreatorPhase, type CreatorState} from "../state/creator_state";
import type {CreatorMode} from "./creator_mode";
import type {SequenceState} from "../state/sequence_state";
import type {
  SequenceGridEventKey,
  SequenceGridSnap,
  SequenceGridViewport,
} from "../state/sequence_grid_model";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {ProjectOverview} from "./project_overview";
import {PerformOverview} from "./perform_overview";
import {SampleOverview} from "./sample_overview";
import {SequenceOverview} from "./sequence_overview";
import {transportStatusLabel} from "./transport_status";
import {projectIdentity, projectStorageStatus, sampleIdentity} from "../state/overview_context";
import type {PerformController} from "../state/perform_state";
import {SEQUENCE_TICKS_PER_BAR, sequenceBarBeat} from "../state/sequence_grid_model";
import {usePatternPlayheadTick} from "./use_pattern_playhead";
import "./overview_display.css";

interface OverviewDisplayProps {
  encoders?: Partial<Record<EncoderPosition, EncoderBinding>>;
  systemOpen?: boolean;
  state: CreatorState;
  activeMode: CreatorMode;
  sequence: SequenceState;
  snap: SequenceGridSnap;
  viewport: SequenceGridViewport | null;
  selection: readonly SequenceGridEventKey[];
  // Sequence's eight-row window and the encoder turns' unsettled values.
  rowOffset?: number;
  currentPad?: number;
  tempoPreview?: number | null;
  swingPreview?: number | null;
  transport?: PatternTransportState;
  midi?: MidiStatus | null;
  performController?: PerformController | null;
}

function encoderLabel(label: string | undefined): string {
  switch (label) {
    case "Select Project": return "Project";
    case "Scroll Projects": return "List";
    case "scroll bars": return "Bars";
    case "scroll track rows": return "Rows";
    case "Output Volume": return "Output";
    case "Pad Volume": return "Pad Vol";
    default: return label ?? "Unassigned";
  }
}

function modeLabel(mode: CreatorMode): string {
  switch (mode) {
    case "project": return "PROJECT";
    case "sample": return "SAMPLE";
    case "sequence": return "SEQUENCE";
    case "perform": return "PERFORM";
    case "soundset": return "SOUND SETS";
    case "slice": return "SLICE";
  }
}

// Keep animation local to the readout instead of rerendering every mode body.
function TransportReadout({transport, bpm, bars, tempoPreview, swing}: {
  transport: PatternTransportState | undefined;
  bpm: number | null;
  bars: number | null;
  tempoPreview: number | null;
  swing: number | null;
}) {
  const tick = usePatternPlayheadTick(transport, bpm,
    bars === null ? null : bars * SEQUENCE_TICKS_PER_BAR);
  return <div className="overview-transport" aria-label="Pattern transport">
    <span>{transport === undefined ? "STOPPED" : transportStatusLabel(transport).toUpperCase()}</span>
    {tempoPreview === null ? null : <output className="overview-bpm">{tempoPreview} BPM</output>}
    {swing === null ? null : <output className="overview-swing">SWING {swing}%</output>}
    <output aria-label="Transport position" aria-live="off">{bars === null ? "—" : sequenceBarBeat(tick)}</output>
  </div>;
}

function AuxiliaryOverview({state, mode}: {state: CreatorState; mode: "slice" | "soundset"}) {
  // Source/job/catalog state belongs to the touch controllers. Until they
  // project it here, show workflow guidance rather than a made-up receipt.
  return <div className="overview-summary-columns" data-testid={`${mode}-overview`}>
    <dl><dt>PROJECT</dt><dd className="overview-value">{projectIdentity(state.project.current)}</dd>
      <dd>{projectStorageStatus(state)}</dd></dl>
    <dl><dt>{mode === "slice" ? "SOURCE" : "CATALOG"}</dt>
      <dd className="overview-value">{mode === "slice" ? "Select a source" : "Sound Sets"}</dd>
      <dd>{mode === "slice" ? "Source selection in touch workspace" : "Browse and audition on the touch screen"}</dd></dl>
    <dl><dt>{mode === "slice" ? "RESULT" : "INSTALL"}</dt>
      <dd className="overview-value">{mode === "slice" ? "Preview slices" : "Choose target"}</dd>
      <dd>{mode === "slice" ? "Adopt to save them to Pads" : "Choose a target Bank before installing"}</dd></dl>
  </div>;
}

export function OverviewDisplay({
  state,
  encoders,
  systemOpen = false,
  activeMode,
  sequence,
  snap,
  viewport,
  selection,
  rowOffset,
  currentPad,
  tempoPreview = null,
  swingPreview = null,
  transport,
  midi = null,
  performController,
}: OverviewDisplayProps) {
  const project = state.project.current;
  // #1958: while the transport plays, the upper screen names the Pattern the
  // engine actually plays rather than the selection, which follows only when
  // the queued switch applies.
  const playingPatternId = transport?.status?.playing === true
    ? transport.status.currentPatternId
    : null;
  const selectedPatternId = playingPatternId ?? sequence.selectedPatternId ?? project?.patternId ?? null;
  const pattern = selectedPatternId === null
    ? undefined
    : project?.patterns.find((item) => item.patternId === selectedPatternId);
  const patternIndex = pattern === undefined || project === null
    ? null
    : project.patterns.findIndex((item) => item.patternId === pattern.patternId) + 1;
  const sequenceMode = !systemOpen && activeMode === "sequence";
  const performMode = !systemOpen && activeMode === "perform";
  const showsProject = !systemOpen && activeMode === "project";
  const projectLabel = <span data-testid="opened-project" aria-label="Open Project">
    {projectIdentity(project)}
  </span>;
  const playingSlot = playingPatternId === null ? -1 : project?.patternSlots.indexOf(playingPatternId) ?? -1;
  const objectLabel = activeMode === "sequence"
    ? patternIndex === null ? "NO PATTERN" : String(patternIndex).padStart(2, "0")
    : activeMode === "perform"
      ? playingSlot >= 0 ? `SLOT ${String(playingSlot + 1).padStart(2, "0")}`
        : patternIndex === null ? "NO PATTERN" : `PATTERN ${String(patternIndex).padStart(2, "0")}`
      : activeMode === "sample" ? sampleIdentity(state.sample.selectedSlot) : null;
  return (
    <div className="overview-display interaction-overview" data-mode={systemOpen ? "system" : activeMode}>
      <div className="overview-primary">
        <output className="overview-context">
          {systemOpen ? "SYSTEM" : modeLabel(activeMode)}
          {systemOpen ? null : showsProject ? <> / {projectLabel}</>
            : objectLabel === null ? null : ` / ${objectLabel}`}
        </output>
        {!showsProject ? <span className="visually-hidden">Project {projectLabel}</span> : null}
        {!sequenceMode && !performMode ? <output className="overview-bpm visually-hidden">
          {project ? `${project.bpm} BPM` : "NO PROJECT"}
        </output> : null}
        <TransportReadout transport={transport} bpm={project?.bpm ?? null} bars={pattern?.bars ?? null}
          tempoPreview={sequenceMode || performMode ? tempoPreview ?? project?.bpm ?? null : null}
          swing={sequenceMode && project ? swingPreview ?? project.sequenceSettings.swingPercent : null} />
        <output className="overview-phase visually-hidden">
          <span data-testid="creator-phase">{selectCreatorPhase(state)}</span>
          {" / "}
          <span data-testid="audio-state">Audio {state.audio.phase}</span>
          {activeMode === "sequence"
            ? ` / ${transport === undefined
                ? sequence.phase
                : transportStatusLabel(transport)}`
            : activeMode === "perform" && transport !== undefined
              ? ` / ${transportStatusLabel(transport)}`
              : ""}
        </output>
      </div>
      <div className="overview-body">
      {systemOpen ? (
        <ProjectOverview state={state} midi={midi} outputValue={encoders?.[4]?.value} />
      ) : activeMode === "sequence" ? (
        <SequenceOverview
          hideContext={encoders !== undefined}
          hidePosition
          project={project}
          state={sequence}
          bank={state.activeBank}
          snap={snap}
          viewport={viewport}
          selection={selection}
          {...(currentPad === undefined ? {} : {currentPad})}
          {...(rowOffset === undefined ? {} : {rowOffset})}
          {...(transport === undefined ? {} : {transport})}
        />
      ) : activeMode === "project" ? (
        <ProjectOverview state={state} midi={midi} outputValue={encoders?.[4]?.value} />
      ) : activeMode === "sample" ? (
        <SampleOverview state={state} />
      ) : activeMode === "slice" || activeMode === "soundset" ? (
        <AuxiliaryOverview state={state} mode={activeMode} />
      ) : activeMode === "perform" ? (
        <PerformOverview
          state={state}
          hideState
          selectedPatternId={selectedPatternId}
          {...(performController === undefined ? {} : {controller: performController})}
          {...(transport === undefined ? {} : {transport})}
        />
      ) : (
        <p className="overview-grid-caption">
          Event grid is a live projection target; this overview does not edit it.
        </p>
      )}
      </div>
      {encoders === undefined ? null : (
        <dl className="encoder-readbacks" aria-label="Encoder functions and values">
          {([1, 2, 3, 4] as const).map((position) => (
            <div key={position} data-encoder={position}>
              <dt title={encoders[position]?.label}>ENC{position} {encoderLabel(encoders[position]?.label)}</dt>
              <dd>{encoders[position]?.value ?? "—"}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
