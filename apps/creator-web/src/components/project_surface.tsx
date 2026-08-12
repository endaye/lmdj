import {useRef, type ChangeEvent} from "react";

import type {
  CreatorState,
  LocalProjectSummary,
} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";

interface ProjectSurfaceProps {
  state: CreatorState;
  canOpen?: boolean;
  canImport?: boolean;
  showLocalProjects?: boolean;
  onShowLocal?: () => void;
  onOpen?: (project: LocalProjectSummary) => void;
  onImport?: (file: File) => void;
}

export function ProjectSurface({
  state,
  canOpen = false,
  canImport = false,
  showLocalProjects = false,
  onShowLocal,
  onOpen,
  onImport,
}: ProjectSurfaceProps) {
  const project = state.project.current;
  const showChooser = project === null || showLocalProjects;
  const fileInput = useRef<HTMLInputElement>(null);
  const onImportFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.item(0);
    event.currentTarget.value = "";
    if (file) onImport?.(file);
  };
  return (
    <main className="project-surface">
      <div className="surface-heading">
        <div>
          <p className="eyebrow">Project surface</p>
          <h1>{showChooser ? "Local Projects" : `Project ${shortProjectId(project.projectId)}`}</h1>
        </div>
        <div className="project-actions">
          <button
            type="button"
            aria-controls="local-projects"
            disabled={!canOpen}
            onClick={onShowLocal}
          >
            Open local
          </button>
          <button
            type="button"
            disabled={!canImport}
            onClick={() => fileInput.current?.click()}
          >
            Import .lmdj
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".lmdj,application/vnd.lmdj.project-bundle"
            onChange={onImportFile}
            disabled={!canImport}
            tabIndex={-1}
            aria-hidden="true"
          />
        </div>
      </div>
      {!showChooser && project ? (
        <dl className="project-summary">
          <div><dt>Project ID</dt><dd>{project.projectId}</dd></div>
          <div><dt>Revision</dt><dd>{project.revision}</dd></div>
          <div><dt>BPM</dt><dd>{project.bpm}</dd></div>
          <div><dt>Assigned Pads</dt><dd>{project.assignedPadCount} / 64</dd></div>
          <div><dt>Assets</dt><dd>{project.assetCount}</dd></div>
        </dl>
      ) : state.project.projects.length === 0 ? (
        <p className="empty-state">No local Project is open.</p>
      ) : (
        <ul className="local-projects" id="local-projects">
          {state.project.projects.map((summary) => {
            const id = shortProjectId(summary.projectId);
            return (
              <li key={summary.projectId}>
                <div>
                  <strong>Project {id}</strong>
                  <span>Revision {summary.revision}</span>
                  <span>{summary.bpm} BPM</span>
                  <span>
                    {summary.assignedPadCount} assigned {summary.assignedPadCount === 1 ? "Pad" : "Pads"}
                  </span>
                  <span>{summary.assetCount} {summary.assetCount === 1 ? "Asset" : "Assets"}</span>
                </div>
                <button
                  type="button"
                  aria-label={`Open Project ${id}`}
                  disabled={!canOpen}
                  onClick={() => onOpen?.(summary)}
                >
                  Open
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <p className="stage-note">
        Sample, Sequence, and Perform editing arrive in Stages 8–10.
      </p>
    </main>
  );
}
