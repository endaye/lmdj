import {
  selectCanActivateAudio,
  selectCreatorPhase,
  type CreatorState,
} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";

interface StatusBarProps {
  state: CreatorState;
}

export function StatusBar({state}: StatusBarProps) {
  const project = state.project.current;
  return (
    <header className="status-bar">
      <strong className="brand">LMDJ</strong>
      <dl className="status-facts">
        <div>
          <dt>Project</dt>
          <dd>{project ? shortProjectId(project.projectId) : "—"}</dd>
        </div>
        <div>
          <dt>BPM</dt>
          <dd>{project?.bpm ?? "—"}</dd>
        </div>
        <div>
          <dt>Key</dt>
          <dd>{project?.key ?? "—"}</dd>
        </div>
      </dl>
      <div className="runtime-state" aria-live="polite">
        <span data-testid="creator-phase">{selectCreatorPhase(state)}</span>
        <span data-testid="audio-state">Audio {state.audio.phase}</span>
      </div>
      <button type="button" disabled={!selectCanActivateAudio(state)}>
        Activate audio
      </button>
    </header>
  );
}
