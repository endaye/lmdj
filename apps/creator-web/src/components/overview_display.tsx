import {midiLabel, type MidiStatus} from "./midi_status";
import {selectCreatorPhase, type CreatorState} from "../state/creator_state";
import type {CreatorMode} from "./creator_mode";
import type {CreatorBuildIdentity} from "../runtime/build_identity";
import {describeBuildIdentity, shortBuildLabel} from "../runtime/build_identity";
import {shortProjectId} from "../state/view_model";
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

interface OverviewDisplayProps {
  state: CreatorState;
  activeMode: CreatorMode;
  sequence: SequenceState;
  snap: SequenceGridSnap;
  viewport: SequenceGridViewport | null;
  selection: readonly SequenceGridEventKey[];
  // Sequence's eight-row window and the encoder turns' unsettled values.
  rowOffset?: number;
  tempoPreview?: number | null;
  swingPreview?: number | null;
  transport?: PatternTransportState;
  midi?: MidiStatus | null;
  buildIdentity?: CreatorBuildIdentity;
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

export function OverviewDisplay({
  state,
  activeMode,
  sequence,
  snap,
  viewport,
  selection,
  rowOffset,
  tempoPreview = null,
  swingPreview = null,
  transport,
  midi = null,
  buildIdentity,
}: OverviewDisplayProps) {
  const project = state.project.current;
  const selectedPatternId = sequence.selectedPatternId ?? project?.patternId ?? null;
  const pattern = selectedPatternId === null
    ? undefined
    : project?.patterns.find((item) => item.patternId === selectedPatternId);
  const patternIndex = pattern === undefined || project === null
    ? null
    : project.patterns.findIndex((item) => item.patternId === pattern.patternId) + 1;
  // Sequence shows only its own status and track rows (2026-10-04 Sequence
  // hardware UI decision). The Creator and audio phase, the Project facts and
  // the build label stay readable by assistive technology but are not drawn.
  const sequenceMode = activeMode === "sequence";
  const hiddenInSequence = sequenceMode ? " visually-hidden" : "";
  return (
    <div className={`overview-display${sequenceMode ? " is-sequence" : ""}`}>
      <div className="overview-primary">
        <output className="overview-context">
          {modeLabel(activeMode)}
          {patternIndex !== null ? ` / ${String(patternIndex).padStart(2, "0")}` : ""}
        </output>
        <output className="overview-bpm">
          {project ? `${tempoPreview ?? project.bpm} BPM` : "NO PROJECT"}
        </output>
        {sequenceMode && project ? (
          <output className="overview-swing">
            SWING {swingPreview ?? project.sequenceSettings.swingPercent}%
          </output>
        ) : null}
        <output className={`overview-phase${hiddenInSequence}`}>
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
      <dl className={`overview-facts${hiddenInSequence}`}>
        <div>
          <dt>Project</dt>
          <dd>{project ? shortProjectId(project.projectId) : "—"}</dd>
        </div>
        <div>
          <dt>Rev</dt>
          <dd>{project?.revision ?? "—"}</dd>
        </div>
        <div>
          <dt>Pads</dt>
          <dd>{project ? `${project.assignedPadCount} / 64` : "—"}</dd>
        </div>
        <div>
          <dt>Assets</dt>
          <dd>{project?.assetCount ?? "—"}</dd>
        </div>
        <div>
          <dt>Key</dt>
          <dd>{project?.key ?? "—"}</dd>
        </div>
        <div>
          <dt>MIDI</dt>
          <dd data-testid="midi-state">{midiLabel(midi)}</dd>
        </div>
        {pattern !== undefined ? (
          <div>
            <dt>Pattern</dt>
            <dd>{pattern.bars} {pattern.bars === 1 ? "bar" : "bars"}</dd>
          </div>
        ) : null}
      </dl>
      {buildIdentity ? (
        <p className={`overview-build${hiddenInSequence}`} data-testid="build-identity"
          title={describeBuildIdentity(buildIdentity)}>
          {shortBuildLabel(buildIdentity)}
        </p>
      ) : null}
      {activeMode === "sequence" ? (
        <SequenceOverview
          project={project}
          state={sequence}
          bank={state.activeBank}
          snap={snap}
          viewport={viewport}
          selection={selection}
          {...(rowOffset === undefined ? {} : {rowOffset})}
          {...(transport === undefined ? {} : {transport})}
        />
      ) : activeMode === "project" ? (
        <ProjectOverview state={state} />
      ) : activeMode === "sample" ? (
        <SampleOverview state={state} />
      ) : activeMode === "slice" || activeMode === "soundset" ? (
        <p className="overview-grid-caption">
          {activeMode === "slice"
            ? "Slice preview does not write Project Truth until Adopt."
            : "Sound Set install writes only after an explicit Keep or Replace."}
        </p>
      ) : activeMode === "perform" ? (
        <PerformOverview
          state={state}
          {...(transport === undefined ? {} : {transport})}
        />
      ) : (
        <p className="overview-grid-caption">
          Event grid is a live projection target; this overview does not edit it.
        </p>
      )}
    </div>
  );
}
