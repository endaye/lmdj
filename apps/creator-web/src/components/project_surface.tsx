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
  hideSummary?: boolean;
  onShowLocal?: () => void;
  onHideLocal?: () => void;
  onOpen?: (project: LocalProjectSummary) => void;
  onImport?: (file: File) => void;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export function ProjectSurface({
  state,
  canOpen = false,
  canImport = false,
  showLocalProjects = false,
  hideSummary = false,
  onShowLocal,
  onHideLocal,
  onOpen,
  onImport,
}: ProjectSurfaceProps) {
  const project = state.project.current;
  const showChooser = project === null || showLocalProjects;
  const importing = state.transfer.phase === "importing";
  const fileInput = useRef<HTMLInputElement>(null);
  const onImportFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.item(0);
    event.currentTarget.value = "";
    if (file) onImport?.(file);
  };
  return (
    <main className="project-surface">
      <div className="surface-heading">
        <div className="project-chooser-header">
          <p className="eyebrow">Project surface</p>
          <h1>{showChooser ? "Local Projects" : `Project ${shortProjectId(project.projectId)}`}</h1>
          {hideSummary ? (
            <p className="project-local-count">
              {String(state.project.projects.length).padStart(2, "0")} LOCAL
            </p>
          ) : null}
        </div>
        <div className="project-actions">
          {project !== null && showLocalProjects && onHideLocal ? (
            <button type="button" onClick={onHideLocal}>
              Back to Project
            </button>
          ) : null}
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
      {importing ? (
        <section className="import-progress" aria-label="Import progress">
          <p role="status">
            Importing… {formatBytes(state.transfer.completedBytes)} of{" "}
            {formatBytes(state.transfer.totalBytes)}
          </p>
          <progress
            max={Math.max(state.transfer.totalBytes, 1)}
            value={Math.min(state.transfer.completedBytes, state.transfer.totalBytes)}
          />
        </section>
      ) : null}
      {!showChooser && project && !hideSummary ? (
        <dl className="project-summary">
          <div><dt>Project ID</dt><dd>{project.projectId}</dd></div>
          <div><dt>Revision</dt><dd>{project.revision}</dd></div>
          <div><dt>BPM</dt><dd>{project.bpm}</dd></div>
          <div><dt>Assigned Pads</dt><dd>{project.assignedPadCount} / 64</dd></div>
          <div><dt>Assets</dt><dd>{project.assetCount}</dd></div>
          <div><dt>Patterns</dt><dd>{project.patterns.length}</dd></div>
          <div>
            <dt>Quantize</dt>
            <dd>{project.sequenceSettings.quantizeEnabled ? "On" : "Off"}</dd>
          </div>
          <div><dt>Swing</dt><dd>{project.sequenceSettings.swingPercent}%</dd></div>
        </dl>
      ) : state.project.projects.length === 0 ? (
        <p className="empty-state">
          {project === null ? (
            <>
              <span>No local Project is open.</span>{" "}
              <span className="empty-hint">Import a .lmdj bundle to begin.</span>
            </>
          ) : (
            <span>No other local Project is stored on this device.</span>
          )}
        </p>
      ) : (
        <ul className="local-projects" id="local-projects">
          {state.project.projects.map((summary, index) => {
            const id = shortProjectId(summary.projectId);
            const isCurrent = project?.projectId === summary.projectId;
            return (
              <li
                key={summary.projectId}
                className={isCurrent ? "is-current" : ""}
                aria-current={isCurrent ? "true" : undefined}
              >
                <span className="project-card-index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <strong>Project {id}</strong>
                  {isCurrent ? <span>Open now</span> : null}
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
        Perform mode arrives in Stage 10.
      </p>
    </main>
  );
}
