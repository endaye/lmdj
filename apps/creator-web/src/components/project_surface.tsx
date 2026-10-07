import {userMessage} from "../state/error_messages";
import {useEffect, useRef, useState, type ChangeEvent} from "react";

import type {
  CreatorState,
  LocalProjectSummary,
} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";

interface ProjectSurfaceProps {
  state: CreatorState;
  canOpen?: boolean;
  canImport?: boolean;
  canCreate?: boolean;
  canDuplicate?: boolean;
  // The code of a Duplicate refused before any copy existed; the open
  // Project is untouched.
  duplicateRefusal?: string | null;
  showLocalProjects?: boolean;
  hideSummary?: boolean;
  onShowLocal?: () => void;
  onHideLocal?: () => void;
  onOpen?: (project: LocalProjectSummary) => void;
  onImport?: (file: File) => void;
  onCreate?: () => void;
  onDuplicate?: () => void;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export function duplicateRefusalMessage(code: string): string {
  switch (code) {
    case "PROJECT_BUSY":
      return "Duplicate refused: this Project is open in another tab or process.";
    case "HOST_STATE_INVALID":
      // The Host gives this one code for playback, a pending import and an
      // unfinished recording alike.
      return "Duplicate refused: stop playback and finish or recover any unfinished recording, then try again.";
    case "DUPLICATE_ID":
      return "Duplicate refused: the new identity is already in use. Try again.";
    case "IO_ERROR":
      return "Duplicate failed: local storage could not hold the copy.";
    default: {
      const {message, nextStep} = userMessage(code);
      return `Duplicate failed: ${message} ${nextStep}`;
    }
  }
}

export function ProjectSurface({
  state,
  canOpen = false,
  canImport = false,
  canCreate = false,
  canDuplicate = false,
  duplicateRefusal = null,
  showLocalProjects = false,
  hideSummary = false,
  onShowLocal,
  onHideLocal,
  onOpen,
  onImport,
  onCreate,
  onDuplicate,
}: ProjectSurfaceProps) {
  const project = state.project.current;
  const showChooser = project === null || showLocalProjects;
  const importing = state.transfer.phase === "importing";
  const fileInput = useRef<HTMLInputElement>(null);
  // D01: tapping a card selects it; only OPEN PROJECT opens the selection.
  // The selection defaults to the open Project, else the first listed one.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const projects = state.project.projects;
  // A selection that leaves the inventory is dropped, so a Project listed
  // again later is not selected without a tap.
  useEffect(() => {
    if (selectedId !== null && !projects.some((item) => item.projectId === selectedId)) {
      setSelectedId(null);
    }
  }, [projects, selectedId]);
  const showSummary = !showChooser && project !== null && !hideSummary;
  const selected = projects.find((item) => item.projectId === selectedId)
    ?? projects.find((item) => item.projectId === project?.projectId)
    ?? projects[0]
    ?? null;
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
          {/* D01 reads YOUR PROJECTS; the heading still names the open
              Project for assistive technology. */}
          {hideSummary ? <span className="project-your" aria-hidden="true">YOUR PROJECTS</span> : null}
          <h1 className={hideSummary ? "visually-hidden" : undefined}>
            {showChooser ? "Local Projects" : `Project ${shortProjectId(project.projectId)}`}
          </h1>
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
          {hideSummary ? null : (
            <>
              <button type="button" disabled={!canCreate} onClick={onCreate}>
                New Project
              </button>
              <button type="button" disabled={!canDuplicate} onClick={onDuplicate}>
                Duplicate Project
              </button>
            </>
          )}
          <button
            type="button"
            aria-controls="local-projects"
            disabled={!canOpen}
            onClick={onShowLocal}
          >
            Open local
          </button>
          {hideSummary ? null : (
            <button type="button" disabled={!canImport}
              onClick={() => fileInput.current?.click()}>
              Import .lmdj
            </button>
          )}
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
      {duplicateRefusal !== null ? (
        <p className="project-action-error" role="alert">
          {duplicateRefusalMessage(duplicateRefusal)}
        </p>
      ) : null}
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
      {showSummary && project !== null ? (
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
              <span className="empty-hint">Create a new Project or import a .lmdj bundle.</span>
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
                className={`${isCurrent ? "is-current" : ""}${
                  selected?.projectId === summary.projectId ? " is-selected" : ""}`}
                aria-current={isCurrent ? "true" : undefined}
              >
                <button
                  type="button"
                  className="project-card"
                  aria-label={`Select Project ${id}`}
                  aria-pressed={selected?.projectId === summary.projectId}
                  onClick={() => setSelectedId(summary.projectId)}
                >
                  <span className="project-card-index" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="project-card-text">
                    <strong>Project {id}</strong>
                    {isCurrent ? <span>Open now</span> : null}
                    <span>Revision {summary.revision}</span>
                    <span>{summary.bpm} BPM</span>
                    <span>
                      {summary.assignedPadCount} assigned {summary.assignedPadCount === 1 ? "Pad" : "Pads"}
                    </span>
                    <span>{summary.assetCount} {summary.assetCount === 1 ? "Asset" : "Assets"}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {showSummary || projects.length === 0 ? null : (
        <div className="project-open-row">
          <button
            type="button"
            className="project-open"
            aria-label={selected === null ? "Open Project" : `Open Project ${shortProjectId(selected.projectId)}`}
            disabled={!canOpen || selected === null}
            onClick={() => { if (selected !== null) onOpen?.(selected); }}
          >
            OPEN PROJECT
          </button>
          {hideSummary ? (
            <button type="button" aria-label="Duplicate Project" disabled={!canDuplicate}
              onClick={onDuplicate}>
              DUPLICATE
            </button>
          ) : null}
        </div>
      )}
      {hideSummary ? (
        <div className="project-create-row">
          <button type="button" aria-label="New Project" disabled={!canCreate} onClick={onCreate}>
            + NEW PROJECT
          </button>
          <button type="button" aria-label="Import .lmdj" disabled={!canImport}
            onClick={() => fileInput.current?.click()}>
            IMPORT
          </button>
        </div>
      ) : null}
      <p className="stage-note">
        Perform mode arrives in Stage 10.
      </p>
    </main>
  );
}
