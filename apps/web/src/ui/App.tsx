import { useCallback, useEffect, useState } from "react";
import { defaultApiClient, type ApiClient } from "../api/client";
import type { AudioEngine } from "../engine/AudioEngine";
import { loadPatch, PatchValidationError, type PatchBundle } from "../patch/loader";
import { DropZone } from "./DropZone";
import { ErrorPanel } from "./ErrorPanel";
import { Inspector } from "./Inspector";
import { PadGrid, PAD_KEYS } from "./PadGrid";
import { StepGrid } from "./StepGrid";
import { Transport } from "./Transport";
import { UploadPanel } from "./UploadPanel";
import { UploadingView } from "./UploadingView";

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
      const index = PAD_KEYS.indexOf(e.key.toUpperCase());
      if (index >= 0) engine.triggerPad(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.phase, engine]);

  if (state.phase === "uploading") {
    return (
      <div className="app">
        <h1>LMDJ PATCH VIEW</h1>
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
        <h1>LMDJ PATCH VIEW</h1>
        <DropZone
          onFiles={(f) => void handleFiles(f)}
          onExample={() => void fetchExample().then(handleFiles, fail)}
        />
        <UploadPanel onUpload={(base, file) => void handleUpload(base, file)} />
        {state.issues && <ErrorPanel issues={state.issues} />}
      </div>
    );
  }

  const { bundle } = state;
  const status = (bundle.patch.metadata as Record<string, unknown> | undefined)?.status;
  return (
    <div className="app">
      {status === "rejected" && (
        <div className="banner-rejected" data-testid="banner-rejected">
          质量分未过阈（status: rejected）——仍可播放，仅作提示
        </div>
      )}
      <Transport engine={engine} bundle={bundle} />
      <div className="workstation">
        <PadGrid engine={engine} bundle={bundle} />
        <Inspector bundle={bundle} />
        <div className="workstation-bottom">
          <StepGrid engine={engine} bundle={bundle} />
        </div>
      </div>
    </div>
  );
}
