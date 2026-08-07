export interface LocalProjectSummary {
  projectId: string;
  patternId: string;
  revision: number;
  bpm: number;
  assetCount: number;
  assignedPadCount: number;
  bundleDigest: string;
}

export interface ProjectPadView {
  slot: number;
  assetId: string | null;
}

export interface ProjectView extends LocalProjectSummary {
  key: "—";
  pads: readonly ProjectPadView[];
}

export interface TransferProgress {
  completedBytes: number;
  totalBytes: number;
}

export interface ProjectInspectResult {
  project_revision: number;
  project: unknown;
}

export interface CreatorRuntimeSession {
  start(): Promise<boolean>;
  close(): Promise<boolean>;
  listLocalProjects(): Promise<readonly LocalProjectSummary[]>;
  importProject(
    file: File,
    options: {
      signal: AbortSignal;
      onProgress: (progress: TransferProgress) => void;
    },
  ): Promise<LocalProjectSummary>;
  openProject(
    projectId: string,
    patternId: string,
  ): Promise<unknown>;
  inspectProject(): Promise<ProjectInspectResult | unknown>;
  reloadSnapshot(patternId: string): Promise<unknown>;
}

export type RuntimeSessionFactory = () => CreatorRuntimeSession;

export interface TypedRuntimeError extends Error {
  code?: string;
}
