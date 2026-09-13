import {midiLabel, type MidiStatus} from "./status_bar";
import {selectCreatorPhase, type CreatorState} from "../state/creator_state";
import type {CreatorMode} from "./mode_rail";
import type {CreatorBuildIdentity} from "../runtime/build_identity";
import {describeBuildIdentity, shortBuildLabel} from "../runtime/build_identity";
import {shortProjectId} from "../state/view_model";
import type {SequenceState} from "../state/sequence_state";

interface OverviewDisplayProps {
  state: CreatorState;
  activeMode: CreatorMode;
  sequence: SequenceState;
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
  midi = null,
  buildIdentity,
}: OverviewDisplayProps) {
  const project = state.project.current;
  const pattern = project?.patterns.find((item) =>
    item.patternId === (sequence.selectedPatternId ?? project.patternId),
  ) ?? project?.patterns[0];
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
          {activeMode === "sequence" ? ` / ${sequence.phase}` : ""}
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
      <p className="overview-grid-caption">
        Event grid is a live projection target; this overview does not edit it.
      </p>
    </div>
  );
}
