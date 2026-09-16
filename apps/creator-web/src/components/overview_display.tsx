import {midiLabel, type MidiStatus} from "./status_bar";
import {selectCreatorPhase, type CreatorState} from "../state/creator_state";
import type {CreatorMode} from "./mode_rail";
import type {CreatorBuildIdentity} from "../runtime/build_identity";
import {describeBuildIdentity, shortBuildLabel} from "../runtime/build_identity";
import {shortProjectId} from "../state/view_model";
import type {SequenceState} from "../state/sequence_state";
import type {PatternTransportState} from "../state/pattern_transport_state";
import {SequenceOverview} from "./sequence_overview";
import {transportStatusLabel} from "./sequence_transport";

interface OverviewDisplayProps {
  state: CreatorState;
  activeMode: CreatorMode;
  sequence: SequenceState;
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
  return (
    <div className="overview-display">
      <div className="overview-primary">
        <output className="overview-context">
          {modeLabel(activeMode)}
          {patternIndex !== null ? ` / ${String(patternIndex).padStart(2, "0")}` : ""}
        </output>
        <output className="overview-bpm">
          {project ? `${project.bpm} BPM` : "NO PROJECT"}
        </output>
        <output className="overview-phase">
          <span data-testid="creator-phase">{selectCreatorPhase(state)}</span>
          {" / "}
          <span data-testid="audio-state">Audio {state.audio.phase}</span>
          {activeMode === "sequence"
            ? ` / ${transport === undefined
                ? sequence.phase
                : transportStatusLabel(transport)}`
            : ""}
        </output>
      </div>
      <dl className="overview-facts">
        <div>
          <dt>Project</dt>
          <dd>{project ? shortProjectId(project.projectId) : "—"}</dd>
        </div>
        <div>
          <dt>Rev</dt>
          <dd>{project?.revision ?? "—"}</dd>
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
        <p className="overview-build" title={describeBuildIdentity(buildIdentity)}>
          {shortBuildLabel(buildIdentity)}
        </p>
      ) : null}
      {activeMode === "sequence" ? (
        <SequenceOverview
          project={project}
          state={sequence}
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
