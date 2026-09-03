import {
  selectCanActivateAudio,
  selectCreatorPhase,
  type CreatorState,
} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";
import {
  describeBuildIdentity,
  shortBuildLabel,
  type CreatorBuildIdentity,
} from "../runtime/build_identity";
import type {MouseEvent} from "react";

export interface MidiStatus {
  readonly permission: string;
  readonly connectedInputCount: number;
}

interface StatusBarProps {
  state: CreatorState;
  buildIdentity?: CreatorBuildIdentity;
  midi?: MidiStatus | null;
  audioActivationReady?: boolean;
  onActivateAudio?: (event: MouseEvent<HTMLButtonElement>) => void;
  onSuspendAudio?: () => void;
  onEnableMidi?: () => void;
  onExportReport?: () => void;
}

export function midiLabel(midi: MidiStatus | null | undefined): string {
  if (!midi) return "—";
  switch (midi.permission) {
    case "granted":
      return midi.connectedInputCount === 1
        ? "1 input"
        : `${midi.connectedInputCount} inputs`;
    case "requesting":
      return "requesting";
    case "denied":
      return "denied";
    default:
      return "off";
  }
}

export function StatusBar({
  state,
  buildIdentity,
  midi = null,
  audioActivationReady,
  onActivateAudio,
  onSuspendAudio,
  onEnableMidi,
  onExportReport,
}: StatusBarProps) {
  const project = state.project.current;
  return (
    <header className="status-bar">
      <div className="brand-block">
        <strong className="brand">LMDJ</strong>
        {buildIdentity ? (
          <span
            className="build-identity"
            data-testid="build-identity"
            title={describeBuildIdentity(buildIdentity)}
          >
            {shortBuildLabel(buildIdentity)}
          </span>
        ) : null}
      </div>
      <dl className="status-facts">
        <div>
          <dt>Project</dt>
          <dd>{project ? shortProjectId(project.projectId) : "—"}</dd>
        </div>
        <div>
          <dt>Rev</dt>
          <dd>{project?.revision ?? "—"}</dd>
        </div>
        <div>
          <dt>BPM</dt>
          <dd>{project?.bpm ?? "—"}</dd>
        </div>
        <div>
          <dt>Key</dt>
          <dd>{project?.key ?? "—"}</dd>
        </div>
        <div>
          <dt>MIDI</dt>
          <dd data-testid="midi-state">{midiLabel(midi)}</dd>
        </div>
      </dl>
      <div className="runtime-state" aria-live="polite">
        <span data-testid="creator-phase">{selectCreatorPhase(state)}</span>
        <span data-testid="audio-state">Audio {state.audio.phase}</span>
      </div>
      <div className="status-actions" role="group" aria-label="Runtime actions">
        <button
          type="button"
          disabled={!selectCanActivateAudio(state) || !onActivateAudio ||
            audioActivationReady !== true}
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
          disabled={state.runtime.phase !== "ready" || !onEnableMidi ||
            midi?.permission === "granted" || midi?.permission === "requesting"}
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
      </div>
    </header>
  );
}
