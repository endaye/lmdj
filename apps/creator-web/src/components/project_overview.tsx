import {selectCreatorPhase, type CreatorState} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";
import {midiLabel, type MidiStatus} from "./midi_status";

interface ProjectOverviewProps {
  state: CreatorState;
  midi?: MidiStatus | null;
}

// D01's read-only upper screen: a summary line, then the PROJECT, CONTENT and
// WORKSPACE columns. It always shows the open Project, never the touch
// area's selected card.
export function ProjectOverview({state, midi = null}: ProjectOverviewProps) {
  const project = state.project.current;
  const phase = selectCreatorPhase(state);
  const patterns = project?.patterns.length ?? 0;
  return (
    <div className="project-overview" data-testid="project-overview">
      <p className="project-overview-summary">
        {project === null
          ? "NO PROJECT OPEN"
          : `${project.bpm} BPM · 4 BANKS · ${project.assignedPadCount} ASSIGNED PADS · ${
            String(patterns).padStart(2, "0")} PATTERNS`}
      </p>
      <div className="project-overview-columns">
        <dl aria-label="Project">
          <dt>PROJECT</dt>
          <dd>{project ? shortProjectId(project.projectId) : "none"}</dd>
          <dd>{project ? `Revision ${project.revision}` : "—"}</dd>
          <dd>Projects save automatically</dd>
        </dl>
        <dl aria-label="Content">
          <dt>CONTENT</dt>
          <dd>{String(patterns).padStart(2, "0")} patterns</dd>
          <dd>{project?.assignedPadCount ?? 0} / 64 Pads used</dd>
          <dd>{project?.assetCount ?? 0} sample assets</dd>
        </dl>
        <dl aria-label="Workspace">
          <dt>WORKSPACE</dt>
          <dd>{`Audio engine ${state.audio.phase}`}</dd>
          <dd>MIDI {midiLabel(midi)}</dd>
          <dd>{state.project.phase === "ready" && phase === "ready"
            ? "Project ready"
            : `Project ${state.project.phase} · Runtime ${state.runtime.phase}`}</dd>
          {state.runtime.errorCode !== null ? (
            // The alert carries the message and next step; the code is in
            // Developer diagnostics.
            <dd data-error-code={state.runtime.errorCode}>Needs attention</dd>
          ) : null}
        </dl>
      </div>
    </div>
  );
}
