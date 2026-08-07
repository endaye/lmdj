import {
  selectCanActivateAudio,
  selectCreatorPhase,
  type CreatorState,
} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";
import type {MouseEvent} from "react";

interface StatusBarProps {
  state: CreatorState;
  onActivateAudio?: (event: MouseEvent<HTMLButtonElement>) => void;
  onSuspendAudio?: () => void;
  onEnableMidi?: () => void;
  onExportReport?: () => void;
}

export function StatusBar({
  state,
  onActivateAudio,
  onSuspendAudio,
  onEnableMidi,
  onExportReport,
}: StatusBarProps) {
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
      <button
        type="button"
        disabled={!selectCanActivateAudio(state)}
        onClick={onActivateAudio}
      >
        Activate audio
      </button>
      <button
        type="button"
        disabled={state.audio.phase !== "running" || !onSuspendAudio}
        onClick={onSuspendAudio}
      >
        Suspend audio
      </button>
      <button
        type="button"
        disabled={state.runtime.phase !== "ready" || !onEnableMidi}
        onClick={onEnableMidi}
      >
        Enable MIDI
      </button>
      <button
        type="button"
        disabled={state.runtime.phase !== "ready" || !onExportReport}
        onClick={onExportReport}
      >
        Export report
      </button>
    </header>
  );
}
