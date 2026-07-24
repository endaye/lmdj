import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ApiError, defaultApiClient, type ApiClient } from "../api/client";
import type { AudioEngine } from "../engine/AudioEngine";
import { loadMidiMapping, type MidiBank, type MidiMapping } from "../midi/mapping";
import { loadPatch, PatchValidationError, type PatchBundle } from "../patch/loader";
import { ErrorPanel } from "./ErrorPanel";
import { ContextInspector } from "./ContextInspector";
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
  | { phase: "loaded"; bundle: PatchBundle<unknown> };

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

  const failPatch = useCallback((error: unknown) => {
    const issues = error instanceof PatchValidationError ? error.issues : [String(error)];
    setState({
      phase: "source",
      issues,
      issueTitle: "patch.json 未通过 lmdj.patch.v1 校验",
    });
  }, []);

  const enterLoaded = useCallback(
    (bundle: PatchBundle<unknown>) => {
      engine.load(bundle);
      setState({ phase: "loaded", bundle });
    },
    [engine],
  );

  // 退出当前 patch，停掉播放，回到上传页换一首歌
  const backToUpload = useCallback(() => {
    if (engine.playing) engine.stop();
    setState({ phase: "source", issues: null, issueTitle: null });
  }, [engine]);

  const handleFiles = useCallback(
    async (files: Map<string, ArrayBuffer>) => {
      try {
        enterLoaded(await loadPatch(files, decode));
      } catch (error) {
        failPatch(error);
      }
    },
    [decode, enterLoaded, failPatch],
  );

  const handleUpload = useCallback(
    async (base: string, file: File) => {
      setState({
        phase: "processing",
        file,
        base,
        jobState: "preflight",
        lastNonterminalStage: "preflight",
      });
      try {
        const jobId = await apiClient.uploadSong(base, file);
        setState({
          phase: "processing",
          file,
          base,
          jobId,
          jobState: "queued",
          lastNonterminalStage: "queued",
        });
        await apiClient.pollJob(base, jobId, (job) =>
          setState((previous) => ({
            phase: "processing",
            file,
            base,
            jobId,
            jobState: job.state,
            lastNonterminalStage:
              job.state === "failed" && previous.phase === "processing"
                ? previous.lastNonterminalStage
                : job.state,
          })),
        );
        enterLoaded(await apiClient.fetchPatchBundle(base, jobId, decode));
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
      if (index >= 0) engine.triggerPad(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.phase, engine]);

  if (state.phase === "source") {
    return (
      <div className="app">
        <CreatorStateShell
          label="Source"
          appState="source"
          canvas={
            <>
              <SourcePanel
                onFiles={(files) => void handleFiles(files)}
                onExample={() => void fetchExample().then(handleFiles, failPatch)}
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
  const model = buildWorkbenchViewModel(bundle, selectedPadIndex);
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
        onModeChange={setMode}
        availableModes={["source", "performance", "export"]}
        appBar={
          <>
            <Wordmark />
            <div className="topbar-actions">
              <span className="workbench-project-meta">
                {model.bpm} · {model.durationSeconds}s
              </span>
              <button className="btn-eject" data-testid="back-to-upload" onClick={backToUpload}>
                ⏏ 上传新歌
              </button>
            </div>
          </>
        }
        instrumentCanvas={
          <>
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
              onTrigger={(index) => engine.triggerPad(index)}
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
          </>
        }
        contextInspector={<ContextInspector model={model} />}
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
                ? "Patch ready · no export blockers"
                : `${model.blockers.length} item(s) need review`}
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
