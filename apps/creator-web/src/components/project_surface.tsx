import type {CreatorState} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";

interface ProjectSurfaceProps {
  state: CreatorState;
}

export function ProjectSurface({state}: ProjectSurfaceProps) {
  const project = state.project.current;
  return (
    <main className="project-surface">
      <div className="surface-heading">
        <div>
          <p className="eyebrow">Project surface</p>
          <h1>{project ? `Project ${shortProjectId(project.projectId)}` : "Local Projects"}</h1>
        </div>
        <div className="project-actions">
          <button type="button">Open local</button>
          <button type="button">Import .lmdj</button>
        </div>
      </div>
      {project ? (
        <dl className="project-summary">
          <div><dt>Project ID</dt><dd>{project.projectId}</dd></div>
          <div><dt>Revision</dt><dd>{project.revision}</dd></div>
          <div><dt>Assigned Pads</dt><dd>{project.assignedPadCount} / 64</dd></div>
          <div><dt>Assets</dt><dd>{project.assetCount}</dd></div>
        </dl>
      ) : (
        <p className="empty-state">No local Project is open.</p>
      )}
      <p className="stage-note">
        Sample, Sequence, and Perform editing arrive in Stages 8–10.
      </p>
    </main>
  );
}
