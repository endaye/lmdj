import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  ApiError,
  defaultApiClient,
  normalizeBase,
  type ApiClient,
  type CreatorExportStatus,
} from "../api/client";
import type { AudioEngine } from "../engine/AudioEngine";
import { loadMidiMapping, type MidiBank, type MidiMapping } from "../midi/mapping";
import { loadPatch, PatchValidationError, type PatchBundle } from "../patch/loader";
import { ErrorPanel } from "./ErrorPanel";
import { ContextInspector } from "./ContextInspector";
import { ExportChecklist } from "./ExportChecklist";
import {
  LoadedSourceInspector,
  LoadedSourcePanel,
  type LoadedSourceSummary,
} from "./LoadedSourcePanel";
import { MidiPanel } from "./MidiPanel";
import { PAD_KEYS, PadMatrix16 } from "./PadMatrix16";
import { PatternSurface } from "./PatternSurface";
import { ProcessingPanel } from "./ProcessingPanel";
import { SourcePanel } from "./SourcePanel";
import { WorkbenchShell } from "./WorkbenchShell";
import {
  buildWorkbenchViewModel,
  type WorkbenchMode,
} from "./workbench/model";

/** 内置示例：fetch public/example-patch/（浏览器路径；测试注入替身） */
export async function fetchExampleFiles(): Promise<Map<string, ArrayBuffer>> {
  const res = await fetch("example-patch/patch.json");
  if (!res.ok) {
    throw new PatchValidationError(["示例 patch 不存在——先运行 npm run make-example"]);
  }
  const patchBytes = await res.arrayBuffer();
  const files = new Map<string, ArrayBuffer>([["patch.json", patchBytes]]);
  const patch = JSON.parse(new TextDecoder().decode(patchBytes)) as {
    elements?: { source_path: string }[];
  };
  for (const el of patch.elements ?? []) {
    const r = await fetch(`example-patch/${el.source_path}`);
    if (r.ok) files.set(el.source_path, await r.arrayBuffer());
  }
  return files;
}

type AppState =
  | {
      phase: "source";
      issues: string[] | null;
      issueTitle: string | null;
    }
  | {
      phase: "processing";
      file: File;
      base: string;
      jobId?: string;
      jobState: string;
      lastNonterminalStage: string;
    }
  | {
      phase: "failed";
      file: File;
      base: string;
      failedAt: string;
      issues: string[];
      issueTitle: string;
    }
  | {
      phase: "loaded";
      bundle: PatchBundle<unknown>;
      source: LoadedSource;
      exportState: ExportState;
    };

type LoadedSource =
  | { kind: "api"; base: string; jobId: string; fileName: string }
  | { kind: "local" | "example" };

type ApiLoadedSource = Extract<LoadedSource, { kind: "api" }>;

type ExportState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; status: CreatorExportStatus }
  | { kind: "error"; message: string };

function usePlayheadStep(engine: AudioEngine, active: boolean): number | null {
  const [step, setStep] = useState<number | null>(null);
  useEffect(() => {
    if (!active) {
      setStep(null);
      return;
    }
    const update = () => setStep(engine.playhead());
    update();
    const timer = setInterval(update, 50);
    return () => clearInterval(timer);
  }, [active, engine]);
  return step;
}

export function App({
  engine,
  decode,
  fetchExample = fetchExampleFiles,
  apiClient = defaultApiClient,
}: {
  engine: AudioEngine;
  decode: (b: ArrayBuffer) => Promise<unknown>;
  fetchExample?: () => Promise<Map<string, ArrayBuffer>>;
  apiClient?: ApiClient;
}) {
  const [state, setState] = useState<AppState>({
    phase: "source",
    issues: null,
    issueTitle: null,
  });
  const [selectedPadIndex, setSelectedPadIndex] = useState<number>();
  const [mode, setMode] = useState<WorkbenchMode>("source");
  const [midiBank, setMidiBank] = useState<MidiBank>("A");
  const [midiMappingMode, setMidiMappingMode] = useState<MidiMapping["mode"]>(
    () => loadMidiMapping(localStorage).mode,
  );
  const playheadStep = usePlayheadStep(engine, state.phase === "loaded");
  const triggerPad = useCallback(
    (index: number) => {
      setSelectedPadIndex(index);
      engine.triggerPad(index);
    },
    [engine],
  );

  const failPatch = useCallback((error: unknown) => {
    const issues = error instanceof PatchValidationError ? error.issues : [String(error)];
    setState({
      phase: "source",
      issues,
      issueTitle: "patch.json 未通过 lmdj.patch.v1 校验",
    });
  }, []);

  const enterLoaded = useCallback(
    (bundle: PatchBundle<unknown>, source: LoadedSource) => {
      engine.load(bundle);
      setMode("performance");
      setState({
        phase: "loaded",
        bundle,
        source,
        exportState: { kind: "idle" },
      });
    },
    [engine],
  );

  // 退出当前 patch，停掉播放，回到上传页换一首歌
  const backToUpload = useCallback(() => {
    if (engine.playing) engine.stop();
    setMode("source");
    setState({ phase: "source", issues: null, issueTitle: null });
  }, [engine]);

  const handleFiles = useCallback(
    async (
      files: Map<string, ArrayBuffer>,
      source: Extract<LoadedSource, { kind: "local" | "example" }>,
    ) => {
      try {
        enterLoaded(await loadPatch(files, decode), source);
      } catch (error) {
        failPatch(error);
      }
    },
    [decode, enterLoaded, failPatch],
  );

  const handleUpload = useCallback(
    async (base: string, file: File) => {
      const root = normalizeBase(base);
      setState({
        phase: "processing",
        file,
        base: root,
        jobState: "preflight",
        lastNonterminalStage: "preflight",
      });
      try {
        const jobId = await apiClient.uploadSong(root, file);
        setState({
          phase: "processing",
          file,
          base: root,
          jobId,
          jobState: "queued",
          lastNonterminalStage: "queued",
        });
        await apiClient.pollJob(root, jobId, (job) =>
          setState((previous) => ({
            phase: "processing",
            file,
            base: root,
            jobId,
            jobState: job.state,
            lastNonterminalStage:
              job.state === "failed" && previous.phase === "processing"
                ? previous.lastNonterminalStage
                : job.state,
          })),
        );
        enterLoaded(
          await apiClient.fetchPatchBundle(root, jobId, decode),
          { kind: "api", base: root, jobId, fileName: file.name },
        );
      } catch (error) {
        const preflight = isPreflightRejection(error);
        setState((previous) => ({
          phase: "failed",
          file,
          base,
          failedAt:
            preflight
              ? "preflight"
              : previous.phase === "processing"
                ? previous.lastNonterminalStage
                : "upload",
          issues:
            error instanceof PatchValidationError
              ? error.issues
              : [errorMessage(error)],
          issueTitle:
            preflight
              ? "上传未通过检查"
              : error instanceof PatchValidationError
                ? "patch.json 未通过 lmdj.patch.v1 校验"
                : "处理未完成",
        }));
      }
    },
    [apiClient, decode, enterLoaded],
  );

  const requestExportStatus = useCallback(
    async (source: ApiLoadedSource) => {
      const matchesSource = (candidate: AppState) =>
        candidate.phase === "loaded" &&
        candidate.source.kind === "api" &&
        candidate.source.base === source.base &&
        candidate.source.jobId === source.jobId;
      setState((previous) =>
        matchesSource(previous)
          ? { ...previous, exportState: { kind: "loading" } }
          : previous,
      );
      try {
        const status = await apiClient.fetchCreatorExportStatus(
          source.base,
          source.jobId,
        );
        setState((previous) =>
          matchesSource(previous)
            ? { ...previous, exportState: { kind: "ready", status } }
            : previous,
        );
      } catch (error) {
        setState((previous) =>
          matchesSource(previous)
            ? {
                ...previous,
                exportState: { kind: "error", message: errorMessage(error) },
              }
            : previous,
        );
      }
    },
    [apiClient],
  );

  const handleModeChange = useCallback(
    (nextMode: WorkbenchMode) => {
      setMode(nextMode);
      if (
        nextMode === "export" &&
        state.phase === "loaded" &&
        state.source.kind === "api" &&
        state.exportState.kind === "idle"
      ) {
        void requestExportStatus(state.source);
      }
    },
    [requestExportStatus, state],
  );

  // 键盘固定覆盖 16 个逻辑 Pad；MIDI Bank 只影响 8-pad Controller。
  useEffect(() => {
    if (state.phase !== "loaded") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target;
      if (
        target instanceof HTMLElement &&
        (
          target.matches("input, textarea, select") ||
          target.isContentEditable ||
          target.closest('[contenteditable]:not([contenteditable="false"])')
        )
      ) {
        return;
      }
      const index = PAD_KEYS.indexOf(
        e.key.toUpperCase() as (typeof PAD_KEYS)[number],
      );
      if (index >= 0) triggerPad(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.phase, triggerPad]);

  if (state.phase === "source") {
    return (
      <div className="app">
        <CreatorStateShell
          label="Source"
          appState="source"
          canvas={
            <>
              <SourcePanel
                onFiles={(files) =>
                  void handleFiles(files, { kind: "local" })
                }
                onExample={() =>
                  void fetchExample().then(
                    (files) => handleFiles(files, { kind: "example" }),
                    failPatch,
                  )
                }
                onUpload={(base, file) => void handleUpload(base, file)}
              />
              {state.issues && (
                <ErrorPanel
                  title={
                    state.issueTitle ??
                    "patch.json 未通过 lmdj.patch.v1 校验"
                  }
                  issues={state.issues}
                />
              )}
            </>
          }
          inspector={
            <div className="state-inspector">
              <strong>Source rules</strong>
              <p>Preflight must pass before a Job exists.</p>
              <p>Supported input: WAV or MP3.</p>
            </div>
          }
          status={
            <>
              <strong>Source</strong>
              <span>WAV / MP3</span>
              <span>200 MiB · 600 秒</span>
              <span>Local draft</span>
            </>
          }
        />
      </div>
    );
  }

  if (state.phase === "processing") {
    return (
      <div className="app">
        <CreatorStateShell
          label="Processing"
          appState={state.jobState}
          canvas={
            <ProcessingPanel
              fileName={state.file.name}
              state={state.jobState}
            />
          }
          inspector={
            <div className="state-inspector">
              <strong>Source retained</strong>
              <p>{state.file.name}</p>
              <p>Job {state.jobId ?? "pending preflight"}</p>
              <p>Worker state: {state.jobState}</p>
            </div>
          }
          status={
            <>
              <strong>Processing</strong>
              <span>{state.file.name}</span>
              <span>{state.jobState}</span>
              <span>{state.jobId ?? "validating input"}</span>
            </>
          }
        />
      </div>
    );
  }

  if (state.phase === "failed") {
    return (
      <div className="app">
        <CreatorStateShell
          label="Failed"
          appState="failed"
          canvas={
            <section className="failed-state" data-testid="failed-state">
              <header className="state-heading">
                <span>Failed · truthful outcome</span>
                <h1>Source needs attention</h1>
                <p>{state.file.name}</p>
              </header>
              <ErrorPanel title={state.issueTitle} issues={state.issues} />
              <dl className="failed-context">
                <div>
                  <dt>File</dt>
                  <dd>{state.file.name}</dd>
                </div>
                <div>
                  <dt>Failed at</dt>
                  <dd>{state.failedAt}</dd>
                </div>
              </dl>
              <div className="failed-actions">
                <button onClick={() => void handleUpload(state.base, state.file)}>
                  Retry
                </button>
                <button onClick={backToUpload}>Back</button>
              </div>
            </section>
          }
          inspector={
            <div className="state-inspector">
              <strong>Source retained</strong>
              <p>Retry starts a new upload and preflight.</p>
              <p>No failed Job is reused.</p>
            </div>
          }
          status={
            <>
              <strong>Failed</strong>
              <span>{state.file.name}</span>
              <span>{state.failedAt}</span>
              <span>Source retained</span>
            </>
          }
        />
      </div>
    );
  }

  const { bundle } = state;
  const status = (bundle.patch.metadata as Record<string, unknown> | undefined)?.status;
  const exportStatus =
    state.exportState.kind === "ready" ? state.exportState.status : null;
  const baseModel = buildWorkbenchViewModel(
    bundle,
    selectedPadIndex,
    exportStatus
      ? {
          status: exportStatus.status,
          missing: exportStatus.missing,
          key: exportStatus.music.key?.value ?? null,
        }
      : undefined,
  );
  const exportNeedsReview =
    exportStatus !== null &&
    (
      exportStatus.warnings.length > 0 ||
      Object.values(exportStatus.items).some(
        (item) => item.status === "review",
      )
    );
  const exportBlockers = exportStatus?.warnings.map(
    (warning) => `export warning: ${warning}`,
  ) ?? [];
  const model = {
    ...baseModel,
    blockers: [...baseModel.blockers, ...exportBlockers],
    readiness:
      exportStatus?.status === "partial"
        ? "partial" as const
        : baseModel.readiness !== "ready" || exportNeedsReview
          ? "needs-review" as const
          : "ready" as const,
  };
  const updateExportStatus = (
    source: ApiLoadedSource,
    nextStatus: CreatorExportStatus,
  ) => {
    setState((previous) =>
      previous.phase === "loaded" &&
      previous.source.kind === "api" &&
      previous.source.base === source.base &&
      previous.source.jobId === source.jobId
        ? {
            ...previous,
            exportState: { kind: "ready", status: nextStatus },
          }
        : previous,
    );
  };
  const apiSource = state.source.kind === "api" ? state.source : null;
  const nonApiSource = state.source.kind === "api" ? null : state.source;
  const loadedSource: LoadedSourceSummary =
    state.source.kind === "api"
      ? {
          kind: "API Job",
          name: state.source.fileName,
          detail: `Job ${state.source.jobId} · ${state.source.base}`,
        }
      : state.source.kind === "example"
        ? {
            kind: "Example package",
            name: "Bundled example",
            detail: "Included lmdj.patch.v1 package",
          }
        : {
            kind: "Local package",
            name: "Browser-selected package",
            detail: "Loaded from the dropped patch package",
          };
  const loadedSourceFacts = {
    patchId: bundle.patch.patch_id,
    padCount: bundle.patch.pads.length,
    elementCount: bundle.patch.elements.length,
    playableElementCount: bundle.playableElementIds.size,
    missingElementCount: bundle.missingElementIds.size,
  };
  const exportInspector =
    mode === "export"
      ? apiSource === null
        ? (
            <ExportUnavailable source={nonApiSource!.kind} />
          )
        : state.exportState.kind === "ready"
          ? (
              <ExportChecklist
                apiBase={apiSource.base}
                jobId={apiSource.jobId}
                patchId={bundle.patch.patch_id}
                status={state.exportState.status}
                apiClient={apiClient}
                onStatusChange={(nextStatus) =>
                  updateExportStatus(apiSource, nextStatus)
                }
              />
            )
          : state.exportState.kind === "error"
            ? (
                <div className="export-status-error">
                  <header>
                    <span>Export</span>
                    <h2>导出 Creator Pack</h2>
                  </header>
                  <p role="alert">{state.exportState.message}</p>
                  <button
                    type="button"
                    onClick={() => void requestExportStatus(apiSource)}
                  >
                    Retry Export Status
                  </button>
                </div>
              )
            : (
                <div className="export-status-loading" role="status">
                  正在读取服务端 Creator Pack 状态…
                </div>
              )
      : undefined;
  return (
    <div className="app">
      {status === "rejected" && (
        <div className="banner-rejected" data-testid="banner-rejected">
          质量分未过阈（status: rejected）——仍可播放，仅作提示
        </div>
      )}
      <WorkbenchShell
        model={model}
        mode={mode}
        onModeChange={handleModeChange}
        availableModes={["source", "performance", "export"]}
        appBar={
          <>
            <Wordmark />
            <div className="topbar-actions">
              <span className="workbench-project-meta">
                {model.bpm} · {model.durationSeconds}s · Key {model.key ?? "—"}
              </span>
              <button className="btn-eject" data-testid="back-to-upload" onClick={backToUpload}>
                ⏏ 上传新歌
              </button>
            </div>
          </>
        }
        instrumentCanvas={
          <>
            {mode === "source" && (
              <LoadedSourcePanel
                source={loadedSource}
                facts={loadedSourceFacts}
                onReplace={backToUpload}
              />
            )}
            <div
              className="workbench-performance-view"
              hidden={mode === "source"}
            >
                <div className="workbench-canvas-heading">
                  <div>
                    <span>Performance</span>
                    <small>{model.padCount} live slots</small>
                  </div>
                  <span className="workbench-readiness">{model.readiness}</span>
                </div>
                <PatternSurface
                  bundle={bundle}
                  engine={engine}
                  playheadStep={playheadStep}
                />
                <MidiPanel
                  onTrigger={triggerPad}
                  bank={midiBank}
                  onBankChange={setMidiBank}
                  onMappingModeChange={setMidiMappingMode}
                />
                <section className="panel workbench-pad-slot">
                  <PadMatrix16
                    bundle={bundle}
                    engine={engine}
                    selectedPadIndex={selectedPadIndex}
                    onSelect={setSelectedPadIndex}
                  />
                </section>
            </div>
          </>
        }
        contextInspector={
          mode === "source"
            ? (
                <LoadedSourceInspector
                  source={loadedSource}
                  facts={loadedSourceFacts}
                />
              )
            : (
                <ContextInspector model={model} exportContent={exportInspector} />
              )
        }
        statusBar={
          <>
            <strong>Pads 01–16</strong>
            <span>
              {midiMappingMode === "direct-16"
                ? "MIDI Bank 不适用"
                : `MIDI Bank ${midiBank}`}
            </span>
            <span>
              {model.readiness === "ready"
                ? "ready · Patch ready · no export blockers"
                : `${model.readiness} · ${model.blockers.length} item(s) need review`}
            </span>
            <span>{model.patchId}</span>
          </>
        }
      />
    </div>
  );
}

function isPreflightRejection(error: unknown): boolean {
  if (!(error instanceof ApiError) || !error.detail || typeof error.detail !== "object") {
    return false;
  }
  const code = (error.detail as Record<string, unknown>).code;
  return (
    code === "file_too_large" ||
    code === "unsupported_audio" ||
    code === "duration_too_long"
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function ExportUnavailable({
  source,
}: {
  source: "local" | "example";
}) {
  return (
    <section className="export-unavailable" data-testid="export-unavailable">
      <header>
        <span>Export</span>
        <h2>导出 Creator Pack</h2>
      </header>
      <p>仅远端 Job 可导出。</p>
      <small>当前来源：{source === "example" ? "Example" : "Local"} package</small>
    </section>
  );
}

function CreatorStateShell({
  label,
  appState,
  canvas,
  inspector,
  status,
}: {
  label: string;
  appState: string;
  canvas: ReactNode;
  inspector: ReactNode;
  status: ReactNode;
}) {
  return (
    <WorkbenchShell
      shellLabel={`LMDJ ${label}`}
      mode="source"
      onModeChange={() => {}}
      availableModes={["source"]}
      appBar={
        <>
          <Wordmark />
          <span className="workbench-state-key">{appState}</span>
        </>
      }
      instrumentCanvas={canvas}
      contextInspector={inspector}
      statusBar={status}
    />
  );
}

function Wordmark() {
  return (
    <div className="wordmark">
      LMDJ<span className="wordmark-sub">patch view</span>
    </div>
  );
}
