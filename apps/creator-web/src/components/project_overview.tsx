import type {CreatorState} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";
import {midiLabel, type MidiStatus} from "./midi_status";
import {projectStorageStatus} from "../state/overview_context";

interface ProjectOverviewProps {
  state: CreatorState;
  midi?: MidiStatus | null;
  outputValue?: string | undefined;
}

// The open Project, Audio and MIDI stay visible in both Project and System.
// Storage is a qualified local fact, not an aggregate "everything saved" claim.
export function ProjectOverview({state, midi = null, outputValue}: ProjectOverviewProps) {
  const project = state.project.current;
  const patterns = project?.patterns.length ?? 0;
  return (
    <div className="project-overview" data-testid="project-overview">
      <div className="project-overview-columns overview-summary-columns">
        <dl aria-label="Project">
          <dt>{projectStorageStatus(state)}</dt>
          <dd className="overview-value">{project ? shortProjectId(project.projectId) : "none"}</dd>
          <dd>{project ? `${project.assignedPadCount} Pads · ${patterns} Patterns` : "No content open"}</dd>
          <dd>{project ? `${project.bpm} BPM · 4 Banks` : "—"}</dd>
        </dl>
        <dl aria-label="Audio">
          <dt>AUDIO</dt>
          <dd className="overview-value">{state.audio.phase}</dd>
          <dd>Device output {outputValue ?? "—"}</dd>
          {/* Full error and recovery action stay in the touch workspace; the
              short status replaces, rather than appends to, the ready row. */}
          <dd data-error-code={state.runtime.errorCode ?? undefined}>
            {state.runtime.errorCode !== null ? "Needs attention" : `Project ${state.project.phase}`}
          </dd>
        </dl>
        <dl aria-label="MIDI">
          <dt>MIDI</dt>
          <dd className="overview-value">{midiLabel(midi)}</dd>
          <dd>{midi?.permission === "granted" ? "Configure in System" : "Enable in System"}</dd>
        </dl>
      </div>
    </div>
  );
}
