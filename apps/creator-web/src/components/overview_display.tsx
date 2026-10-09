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
import {projectIdentity, sampleIdentity} from "../state/overview_context";
import type {PerformController} from "../state/perform_state";

interface OverviewDisplayProps {
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
  currentPad,
  tempoPreview = null,
  swingPreview = null,
  transport,
  midi = null,
  performController,
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
  // hardware UI decision), Project its summary and three columns (D01) and
  // Sample its Pad, format, selection and whole waveform (D03), and Perform
  // its transport, bar and beat (D04).
  // Keep lifecycle announcements available to assistive technology; technical
  // identities and counts live in System > Project and build details.
  const sequenceMode = activeMode === "sequence";
  const showsProject = activeMode === "project" || activeMode === "perform" || activeMode === "soundset";
  const projectLabel = <span data-testid="opened-project" aria-label="Open Project">
    {projectIdentity(project)}
  </span>;
  return (
    <div className={`overview-display${sequenceMode ? " is-sequence" : ""}${
      activeMode === "project" ? " is-project" : ""}${activeMode === "sample" ? " is-sample" : ""}${
      activeMode === "perform" ? " is-perform" : ""}`}>
      <div className="overview-primary">
        <output className="overview-context">
          {modeLabel(activeMode)}
          {activeMode === "sequence"
            ? patternIndex === null ? " / NO PATTERN" : ` / ${String(patternIndex).padStart(2, "0")}`
            : activeMode === "sample" ? ` / ${sampleIdentity(state.sample.selectedSlot)}`
            : showsProject ? <> / {projectLabel}</> : ` / ${sampleIdentity(state.sample.selectedSlot)}`}
        </output>
        {/* Object-focused modes still name their enclosing Project to a screen
            reader, without drawing unrelated technical facts above the editor. */}
        {!showsProject ? <span className="visually-hidden">Project {projectLabel}</span> : null}
        <output className={`overview-bpm${activeMode === "sequence" || activeMode === "perform" ? "" : " visually-hidden"}`}>
          {project ? `${tempoPreview ?? project.bpm} BPM` : "NO PROJECT"}
        </output>
        {sequenceMode && project ? (
          <output className="overview-swing">
            SWING {swingPreview ?? project.sequenceSettings.swingPercent}%
          </output>
        ) : null}
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
      {activeMode === "sequence" ? (
        <SequenceOverview
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
        <ProjectOverview state={state} midi={midi} />
      ) : activeMode === "sample" ? (
        <SampleOverview state={state} />
      ) : activeMode === "slice" || activeMode === "soundset" ? (
        <p className="overview-grid-caption">
          {activeMode === "slice"
            ? "Preview slices on the touch screen. Adopt to save them to Pads."
            : "Browse and audition on the touch screen. Choose a target Bank before installing."}
        </p>
      ) : activeMode === "perform" ? (
        <PerformOverview
          state={state}
          {...(performController === undefined ? {} : {controller: performController})}
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
