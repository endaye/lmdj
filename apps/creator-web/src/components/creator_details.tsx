import type {CreatorState} from "../state/creator_state";
import type {CreatorBuildIdentity} from "../runtime/build_identity";
import {describeBuildIdentity, shortBuildLabel} from "../runtime/build_identity";
import {shortProjectId} from "../state/view_model";
import {midiLabel, type MidiStatus} from "./midi_status";

// Pure readback: retaining the details while System is closed preserves its
// disclosure state without mounting Provider settings or their subscriptions.
export function CreatorDetails({state, midi, buildIdentity}: {
  state: CreatorState;
  midi: MidiStatus | null;
  buildIdentity?: CreatorBuildIdentity;
}) {
  const project = state.project.current;
  const pattern = project?.patterns.find(item => item.patternId === project.patternId);
  return <details className="creator-details">
    <summary>Project and build details</summary>
    <dl className="creator-details-facts">
      <div><dt>Project</dt><dd>{project ? shortProjectId(project.projectId) : "—"}</dd></div>
      <div><dt>Project ID</dt><dd>{project?.projectId ?? "—"}</dd></div>
      <div><dt>Rev</dt><dd>{project?.revision ?? "—"}</dd></div>
      <div><dt>Pads</dt><dd>{project ? `${project.assignedPadCount} / 64` : "—"}</dd></div>
      <div><dt>Assets</dt><dd>{project?.assetCount ?? "—"}</dd></div>
      <div><dt>Key</dt><dd>{project?.key ?? "—"}</dd></div>
      <div><dt>MIDI</dt><dd data-testid="midi-state">{midiLabel(midi)}</dd></div>
      {pattern ? <div><dt>Pattern</dt><dd>{pattern.bars} {pattern.bars === 1 ? "bar" : "bars"}</dd></div> : null}
    </dl>
    {buildIdentity ? <p data-testid="build-identity" title={describeBuildIdentity(buildIdentity)}>
      {shortBuildLabel(buildIdentity)}
    </p> : null}
  </details>;
}
