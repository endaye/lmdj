import { useCallback, useEffect, useState } from "react";
import { defaultApiClient, type ApiClient } from "../api/client";
import type { AudioEngine } from "../engine/AudioEngine";
import { loadPatch, PatchValidationError, type PatchBundle } from "../patch/loader";
import { DropZone } from "./DropZone";
import { ErrorPanel } from "./ErrorPanel";
import { ContextInspector } from "./ContextInspector";
import { PAD_KEY_HINTS, PadMatrix16 } from "./PadMatrix16";
import { PatternSurface } from "./PatternSurface";
import { UploadPanel } from "./UploadPanel";
import { UploadingView } from "./UploadingView";
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
  | { phase: "landing"; issues: string[] | null }
  | { phase: "uploading"; state: string; error: string | null }
  | { phase: "loaded"; bundle: PatchBundle<unknown> };

// Task 5 replaces this temporary eight-key bridge with the final 16-key mapping.
const LEGACY_PAD_TRIGGER_KEYS = ["A", "S", "D", "F", "Z", "X", "C", "V"];

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
  const [state, setState] = useState<AppState>({ phase: "landing", issues: null });
  const [selectedPadIndex, setSelectedPadIndex] = useState<number>();
  const [mode, setMode] = useState<WorkbenchMode>("source");
  const playheadStep = usePlayheadStep(engine, state.phase === "loaded");

  const fail = useCallback((error: unknown) => {
    const issues = error instanceof PatchValidationError ? error.issues : [String(error)];
    setState({ phase: "landing", issues });
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
    setState({ phase: "landing", issues: null });
  }, [engine]);

  const handleFiles = useCallback(
    async (files: Map<string, ArrayBuffer>) => {
      try {
        enterLoaded(await loadPatch(files, decode));
      } catch (error) {
        fail(error);
      }
    },
    [decode, enterLoaded, fail],
  );

  const handleUpload = useCallback(
    async (base: string, file: File) => {
      setState({ phase: "uploading", state: "queued", error: null });
      try {
        const jobId = await apiClient.uploadSong(base, file);
        await apiClient.pollJob(base, jobId, (s) =>
          setState({ phase: "uploading", state: s.state, error: null }),
        );
        enterLoaded(await apiClient.fetchPatchBundle(base, jobId, decode));
      } catch (error) {
        // uploadSong 失败时 pollJob 尚未回调 → state 仍为 "queued" → 回 landing；
        // pollJob/fetch 阶段失败 → state 已被推进（≥separating）→ 停 uploading 显 error。
        setState((prev) =>
          prev.phase === "uploading" && prev.state !== "queued"
            ? { phase: "uploading", state: prev.state, error: String(error) }
            : { phase: "landing", issues: [String(error)] },
        );
      }
    },
    [apiClient, decode, enterLoaded],
  );

  // 键盘：A S D F / Z X C V → pad 0-7（仅 loaded 后生效）
  useEffect(() => {
    if (state.phase !== "loaded") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      const index = LEGACY_PAD_TRIGGER_KEYS.indexOf(e.key.toUpperCase());
      if (index >= 0) engine.triggerPad(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.phase, engine]);

  if (state.phase === "uploading") {
    return (
      <div className="app">
        <header className="topbar">
          <Wordmark />
          <span className="standby">working</span>
        </header>
        <UploadingView
          state={state.state}
          error={state.error}
          onBack={() => setState({ phase: "landing", issues: null })}
        />
      </div>
    );
  }

  if (state.phase === "landing") {
    return (
      <div className="app">
        <header className="topbar">
          <Wordmark />
          <span className="standby">standby</span>
        </header>
        <div className="landing">
          <div className="hero">
            <div>
              <h1 className="hero-title">
                把一首歌变成<em>十六个可演奏的 pad</em>
              </h1>
              <p className="hero-sub">
                载入一个 patch,唤醒这台乐器。四个 pad 按乐器角色配色,敲键、静音、跟着步进谱现场演奏。
              </p>
            </div>
            <div className="ghost-grid" aria-hidden="true">
              {GHOST_SLOTS.map((slot, i) => (
                <div key={slot} className="ghost-pad">
                  <span>{PAD_KEY_HINTS[i]}</span>
                  <span>{slot}</span>
                </div>
              ))}
            </div>
          </div>
          <DropZone
            onFiles={(f) => void handleFiles(f)}
            onExample={() => void fetchExample().then(handleFiles, fail)}
          />
          <UploadPanel onUpload={(base, file) => void handleUpload(base, file)} />
          {state.issues && <ErrorPanel issues={state.issues} />}
        </div>
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
            <section className="panel workbench-pad-slot">
              <PadMatrix16
                bundle={bundle}
                engine={engine}
                selectedPadIndex={selectedPadIndex}
                onSelect={setSelectedPadIndex}
                keyHints={PAD_KEY_HINTS}
              />
            </section>
          </>
        }
        contextInspector={<ContextInspector model={model} />}
        statusBar={
          <>
            <strong>Pads 01–16</strong>
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

/** 固定 8-pad Focus View 的槽位名 —— 待机态虚影乐器复用 */
const GHOST_SLOTS = ["Drums", "Bass", "Harmony", "Lead", "Fill", "Drop", "Mute", "FX"];

function Wordmark() {
  return (
    <div className="wordmark">
      LMDJ<span className="wordmark-sub">patch view</span>
    </div>
  );
}
