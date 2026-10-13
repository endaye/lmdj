import {userMessage} from "../state/error_messages";
import {useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent} from "react";
import type {ContextualEncoders, ContextualNavigation} from "./physical_controls";

import type {
  CreatorState,
  LocalProjectSummary,
} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";
import "./project_surface.css";

interface ProjectSurfaceProps {
  state: CreatorState;
  canOpen?: boolean;
  canImport?: boolean;
  canCreate?: boolean;
  canDuplicate?: boolean;
  canSoundSets?: boolean;
  onSoundSets?: () => void;
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
  encodersActive?: boolean;
  onEncodersReady?: (encoders: ContextualEncoders | null) => void;
  onNavigationReady?: (navigation: ContextualNavigation | null) => void;
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
  canSoundSets = false,
  onSoundSets,
  duplicateRefusal = null,
  showLocalProjects = false,
  hideSummary = false,
  onShowLocal,
  onHideLocal,
  onOpen,
  onImport,
  onCreate,
  onDuplicate,
  encodersActive = true,
  onEncodersReady,
  onNavigationReady,
}: ProjectSurfaceProps) {
  const project = state.project.current;
  const showChooser = project === null || showLocalProjects;
  const importing = state.transfer.phase === "importing";
  const fileInput = useRef<HTMLInputElement>(null);
  const surface = useRef<HTMLElement>(null);
  const [listPosition, setListPosition] = useState(0);
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
  const selectedIndex = selected === null ? -1 : projects.indexOf(selected);
  const selectProjectBy = useCallback((steps: number) => {
    if (!encodersActive || importing || projects.length === 0 || !Number.isFinite(steps)) return;
    setSelectedId((current) => {
      const index = projects.findIndex((item) => item.projectId === current);
      const next = projects[Math.max(0, Math.min(projects.length - 1,
        (index < 0 ? selectedIndex : index) + Math.trunc(steps)))];
      return next?.projectId ?? current;
    });
  }, [encodersActive, importing, projects, selectedIndex]);
  const encoders = useMemo<ContextualEncoders>(() => ({bindings: {
    1: {label: "Select Project", value: selectedIndex < 0 ? "—" : String(selectedIndex + 1).padStart(2, "0"),
      disabled: projects.length === 0 || importing,
      onTurn: selectProjectBy},
    2: {label: "Scroll Projects", value: `${Math.round(listPosition)} px`, disabled: projects.length === 0,
      onTurn: (detents) => {
        if (!encodersActive) return;
        const viewport = surface.current?.closest<HTMLElement>('[aria-label="Touch workspace"]');
        if (viewport === null || viewport === undefined) return;
        const first = surface.current?.querySelector<HTMLElement>(".local-projects > li");
        const row = (first?.offsetHeight ?? 0) + 8;
        viewport.scrollTop = Math.max(0, Math.min(viewport.scrollHeight - viewport.clientHeight,
          viewport.scrollTop + detents * row));
        setListPosition(viewport.scrollTop);
      }},
  }}), [encodersActive, importing, projects, selectedIndex, listPosition, selectProjectBy]);
  useEffect(() => {
    onEncodersReady?.(encodersActive ? encoders : null);
    return () => onEncodersReady?.(null);
  }, [onEncodersReady, encodersActive, encoders]);
  const navigation = useMemo<ContextualNavigation>(() => ({
    padStep: {
      backLabel: "Previous Project — ↑", forwardLabel: "Next Project — ↓",
      backAvailable: !importing && selectedIndex > 0,
      forwardAvailable: !importing && selectedIndex >= 0 && selectedIndex < projects.length - 1,
      onBack: () => selectProjectBy(-1), onForward: () => selectProjectBy(1),
    },
  }), [importing, selectedIndex, projects.length, selectProjectBy]);
  useEffect(() => {
    onNavigationReady?.(encodersActive ? navigation : null);
    return () => onNavigationReady?.(null);
  }, [onNavigationReady, encodersActive, navigation]);
  useEffect(() => {
    const viewport = surface.current?.closest<HTMLElement>('[aria-label="Touch workspace"]');
    if (viewport === null || viewport === undefined) return;
    const read = () => setListPosition(viewport.scrollTop);
    read();
    viewport.addEventListener("scroll", read);
    return () => viewport.removeEventListener("scroll", read);
  }, []);
  useEffect(() => {
    const card = surface.current?.querySelector<HTMLElement>(".local-projects .is-selected");
    const viewport = surface.current?.closest<HTMLElement>('[aria-label="Touch workspace"]');
    if (!card || !viewport) return;
    // Layout coordinates remain valid when the whole console scales or rotates.
    // Scroll only the touch panel, never its stage or the document.
    const layoutTop = (element: HTMLElement) => {
      let top = 0;
      for (let current: HTMLElement | null = element; current !== null;
        current = current.offsetParent as HTMLElement | null) top += current.offsetTop;
      return top;
    };
    const top = layoutTop(card) - layoutTop(viewport) - viewport.clientTop;
    const bottom = top + card.offsetHeight;
    if (top < viewport.scrollTop) viewport.scrollTop = top;
    else if (bottom > viewport.scrollTop + viewport.clientHeight) {
      viewport.scrollTop = bottom - viewport.clientHeight;
    }
    setListPosition(viewport.scrollTop);
  }, [selected?.projectId]);
  const onImportFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.item(0);
    event.currentTarget.value = "";
    if (file) onImport?.(file);
  };
  return (
    <main ref={surface} className={`project-surface${hideSummary ? " project-touch-list" : ""}`}>
      <div className="surface-heading">
        <div className="project-chooser-header">
          <p className="eyebrow">Project surface</p>
          {/* The accessible heading keeps naming the open Project. */}
          {hideSummary ? <span className="project-your" aria-hidden="true">PROJECT</span> : null}
          <h1 className={hideSummary ? "visually-hidden" : undefined}>
            {showChooser ? "Local Projects" : `Project ${shortProjectId(project.projectId)}`}
          </h1>
          {hideSummary ? (
            <p className="project-local-count">
              LOCAL
            </p>
          ) : null}
        </div>
        <div className={hideSummary ? "project-actions project-create-row" : "project-actions"}>
          {!hideSummary && project !== null && showLocalProjects && onHideLocal ? (
            <button type="button" onClick={onHideLocal}>
              Back to Project
            </button>
          ) : null}
          {hideSummary ? (
            <button type="button" className="is-primary" aria-label="New Project"
              disabled={!canCreate} onClick={onCreate}>+ New Project</button>
          ) : (
            <>
              <button type="button" disabled={!canCreate} onClick={onCreate}>
                New Project
              </button>
              <button type="button" disabled={!canDuplicate} onClick={onDuplicate}>
                Duplicate Project
              </button>
            </>
          )}
          {hideSummary ? null : <button
            type="button"
            aria-controls="local-projects"
            disabled={!canOpen}
            onClick={onShowLocal}
          >
            Open local
          </button>}
          {hideSummary ? (
            <button type="button" aria-label="Import .lmdj" disabled={!canImport}
              onClick={() => fileInput.current?.click()}>Import</button>
          ) : (
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
                  title={summary.projectId}
                  disabled={importing}
                  onClick={() => setSelectedId(summary.projectId)}
                >
                  <span className="project-card-index" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="project-card-text">
                    <strong>Project {id}</strong>
                    {hideSummary ? <>
                      <span className="project-card-facts">
                        {isCurrent ? <span className="project-card-current">CURRENT PROJECT · </span> : null}
                        {summary.assignedPadCount} {summary.assignedPadCount === 1 ? "Pad" : "Pads"}
                        {" · "}{summary.assetCount} {summary.assetCount === 1 ? "Asset" : "Assets"}
                      </span>
                      <span>{summary.bpm} BPM · Revision {summary.revision}</span>
                    </> : <>
                      {isCurrent ? <span>Open now</span> : null}
                      <span>Revision {summary.revision}</span>
                      <span>{summary.bpm} BPM</span>
                      <span>{summary.assignedPadCount} assigned {summary.assignedPadCount === 1 ? "Pad" : "Pads"}</span>
                      <span>{summary.assetCount} {summary.assetCount === 1 ? "Asset" : "Assets"}</span>
                    </>}
                  </span>
                </button>
                {hideSummary && selected?.projectId === summary.projectId ? (
                  <button type="button" className="project-open"
                    aria-label={`Open Project ${id}`} disabled={!canOpen}
                    onClick={() => onOpen?.(summary)}>Open Project</button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {hideSummary || showSummary || projects.length === 0 ? null : (
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

        </div>
      )}
      {hideSummary ? <>
        <div className="project-open-row">
          <button type="button" aria-label="Duplicate Project" title="Duplicate the open Project"
            disabled={!canDuplicate} onClick={onDuplicate}>Duplicate</button>
          <button type="button" disabled={!canSoundSets} onClick={onSoundSets}>Sound Sets</button>
        </div>
        <p className="project-browse-hint">Select a card to browse. Open to change sounds.</p>
      </> : null}
    </main>
  );
}
