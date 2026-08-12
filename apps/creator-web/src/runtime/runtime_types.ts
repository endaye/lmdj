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

export type RuntimeTriggerSource = "pointer" | "keyboard" | "midi";

export interface TriggerAdmission {
  sequence: number;
  slot: number;
  velocity: number;
  source: RuntimeTriggerSource;
}

export interface RuntimeOutcome {
  sequence: number;
  outcome: "voice_started" | "voice_capacity";
  runtimeFrame: number;
}

export interface RuntimeHostState {
  state: string;
  errorCode: string | null;
  errorDetails: Readonly<Record<string, unknown>>;
}

export interface RuntimeIssue {
  code: string;
  details: Readonly<Record<string, unknown>>;
}

export interface RuntimeDiagnostics {
  state: string;
  error_code: string | null;
  error_details: Readonly<Record<string, unknown>>;
  product_build: string;
  host_id: string;
  host_version: string;
  platform_version: string;
  protocol_version: number;
  capabilities: {
    secureContext: boolean;
    crossOriginIsolated: boolean;
    sharedArrayBuffer: boolean;
    webAssembly: boolean;
    audioWorklet: boolean;
    opfs: boolean;
    opfsSyncAccessHandle: boolean;
    opfsWritableReplace: boolean;
    webMidi: boolean;
  };
  trigger_admitted_count: number;
  trigger_outcome_count: number;
  trigger_rejected_count: number;
  recovery_probe_ready?: boolean;
  [key: string]: unknown;
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
  activateAudio(token: unknown): Promise<boolean>;
  suspendAudio(): Promise<boolean>;
  trigger(
    slot: number,
    velocity: number,
    source: RuntimeTriggerSource,
  ): Promise<TriggerAdmission | false>;
  requestMidi(): Promise<boolean>;
  subscribeDiagnostics(listener: (value: RuntimeDiagnostics) => void): () => void;
  subscribeHostState(listener: (state: RuntimeHostState) => void): () => void;
  subscribeRuntimeOutcome(listener: (outcome: RuntimeOutcome) => void): () => void;
  diagnostics(): RuntimeDiagnostics;
}

export type RuntimeSessionFactory = () => CreatorRuntimeSession;

export interface TypedRuntimeError extends Error {
  code?: string;
  details?: Readonly<Record<string, unknown>>;
}
