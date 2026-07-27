import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  defaultApiClient,
  normalizeBase,
  type ApiClient,
  type CreatorExportStatus,
  type JobStatus,
  type QueueCapacity,
} from "../api/client";
import type { AudioEngine } from "../engine/AudioEngine";
import {
  loadSubmissions,
  removeSubmission,
  upsertSubmission,
  type StoredSubmission,
} from "../jobs/storage";
import { loadMidiMapping, type MidiBank, type MidiMapping } from "../midi/mapping";
import { loadPatch, PatchValidationError, type PatchBundle } from "../patch/loader";
import { ErrorPanel } from "./ErrorPanel";
import { DeleteJobDialog } from "./DeleteJobDialog";
import { ContextInspector } from "./ContextInspector";
import { ExportChecklist } from "./ExportChecklist";
import {
  LoadedSourceInspector,
  LoadedSourcePanel,
  type LoadedSourceSummary,
} from "./LoadedSourcePanel";
import { MidiPanel, type MidiPanelStatus } from "./MidiPanel";
import {
  MySongsView,
  type TrackedJob,
} from "./MySongsView";
import { PAD_KEYS, PadMatrix16 } from "./PadMatrix16";
import { PatternSurface } from "./PatternSurface";
import { ProcessingPanel } from "./ProcessingPanel";
import { NewSongView } from "./NewSongView";
import { WorkbenchShell } from "./WorkbenchShell";
import {
  buildWorkbenchViewModel,
  type WorkbenchMode,
} from "./workbench/model";
import { PRODUCT_VERSION } from "../version";

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
      phase: "library";
    }
  | {
      phase: "new-upload";
      issues: string[] | null;
      issueTitle: string | null;
    }
  | {
      phase: "processing";
      fileName: string;
      sourceFile?: File;
      base: string;
      submissionId: string;
      jobId?: string;
      jobState: string;
      lastNonterminalStage: string;
    }
  | {
      phase: "failed";
      fileName: string;
      sourceFile?: File;
      base: string;
      submissionId: string;
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

const EMPTY_CAPACITY: QueueCapacity = {
  max_concurrency: 1,
  processing: 0,
  waiting: 0,
};

const HEADER_NUMBER = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  useGrouping: false,
});

const TERMINAL_JOB_STATES = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);

function trackedFromSubmission(submission: StoredSubmission): TrackedJob {
  return {
    submission,
    status: null,
    clientState: submission.jobId ? "accepted" : "preflight",
    clientError: null,
    lastNonterminalState: submission.jobId ? "queued" : "preflight",
  };
}

function jobStatusFromError(error: unknown): JobStatus | null {
  if (
    error instanceof ApiError &&
    error.detail &&
    typeof error.detail === "object" &&
    typeof (error.detail as { state?: unknown }).state === "string"
  ) {
    return error.detail as JobStatus;
  }
  return null;
}

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
  const [initialSubmissions] = useState(() => loadSubmissions(localStorage));
  const [state, setState] = useState<AppState>(() =>
    initialSubmissions.length > 0
      ? { phase: "library" }
      : {
          phase: "new-upload",
          issues: null,
          issueTitle: null,
        }
  );
  const [trackedJobs, setTrackedJobs] = useState<TrackedJob[]>(() =>
    initialSubmissions.map(trackedFromSubmission)
  );
  const trackedJobsRef = useRef(trackedJobs);
  const foregroundSubmissionRef = useRef<string | null>(null);
  const pollingJobsRef = useRef(new Set<string>());
  const deletedJobIdsRef = useRef(new Set<string>());
  const inflightUploadsRef = useRef(new Map<string, string>());
  const [queueCapacity, setQueueCapacity] =
    useState<QueueCapacity>(EMPTY_CAPACITY);
  const [selectedPadIndex, setSelectedPadIndex] = useState<number>();
  const [mode, setMode] = useState<WorkbenchMode>("source");
  const [midiBank, setMidiBank] = useState<MidiBank>("A");
  const [midiMappingMode, setMidiMappingMode] = useState<MidiMapping["mode"]>(
    () => loadMidiMapping(localStorage).mode,
  );
  const [midiStatus, setMidiStatus] = useState<MidiPanelStatus>({
    connection: "Not connected",
    devices: [],
  });
  const [deleteTarget, setDeleteTarget] = useState<TrackedJob | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteNotice, setDeleteNotice] = useState<string | null>(null);
  const [completionNotice, setCompletionNotice] = useState<string | null>(null);
  const playheadStep = usePlayheadStep(engine, state.phase === "loaded");
  const triggerPad = useCallback(
    (index: number) => {
      setSelectedPadIndex(index);
      engine.triggerPad(index);
    },
    [engine],
  );

  const updateTrackedJobs = useCallback(
    (update: (current: TrackedJob[]) => TrackedJob[]) => {
      const next = update(trackedJobsRef.current);
      trackedJobsRef.current = next;
      setTrackedJobs(next);
    },
    [],
  );

  const updateTrackedJob = useCallback(
    (
      submissionId: string,
      update: (current: TrackedJob) => TrackedJob,
    ) => {
      updateTrackedJobs((current) =>
        current.map((job) =>
          job.submission.submissionId === submissionId
            ? update(job)
            : job
        )
      );
    },
    [updateTrackedJobs],
  );

  const applyJobStatus = useCallback(
    (submissionId: string, status: JobStatus) => {
      if (status.capacity) setQueueCapacity(status.capacity);
      updateTrackedJob(submissionId, (current) => ({
        ...current,
        status,
        clientState: "accepted",
        clientError: null,
        lastNonterminalState: TERMINAL_JOB_STATES.has(status.state)
          ? current.lastNonterminalState
          : status.state,
      }));
    },
    [updateTrackedJob],
  );

  const failPatch = useCallback((error: unknown) => {
    const issues = error instanceof PatchValidationError ? error.issues : [String(error)];
    foregroundSubmissionRef.current = null;
    setState({
      phase: "new-upload",
      issues,
      issueTitle: "patch.json 未通过 lmdj.patch.v1 校验",
    });
  }, []);

  const enterLoaded = useCallback(
    (bundle: PatchBundle<unknown>, source: LoadedSource) => {
      engine.load(bundle);
      foregroundSubmissionRef.current = null;
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

  const showLibrary = useCallback(() => {
    engine.stop();
    foregroundSubmissionRef.current = null;
    setMode("source");
    setState({ phase: "library" });
  }, [engine]);

  const showNewUpload = useCallback(() => {
    engine.stop();
    foregroundSubmissionRef.current = null;
    setMode("source");
    setState({
      phase: "new-upload",
      issues: null,
      issueTitle: null,
    });
  }, [engine]);

  const requestDelete = useCallback((job: TrackedJob) => {
    setDeleteTarget(job);
    setDeleteError(null);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    const {
      submissionId,
      jobId,
      controlToken,
      base,
    } = deleteTarget.submission;
    if (!jobId || !controlToken) {
      setDeleteError("这个旧任务没有安全删除凭证，无法删除服务器文件。");
      return;
    }

    deletedJobIdsRef.current.add(jobId);
    setDeleting(true);
    setDeleteError(null);
    try {
      await apiClient.deleteJob(base, jobId, controlToken);
      removeSubmission(localStorage, submissionId);
      updateTrackedJobs((current) =>
        current.filter(
          (job) => job.submission.submissionId !== submissionId,
        )
      );
      setDeleteTarget(null);
      setDeleteNotice(`《${deleteTarget.submission.fileName}》已从服务器和本浏览器删除。`);
      const deletingCurrent =
        (state.phase === "processing" || state.phase === "failed") &&
        state.submissionId === submissionId;
      const deletingLoaded =
        state.phase === "loaded" &&
        state.source.kind === "api" &&
        state.source.jobId === jobId;
      if (deletingCurrent || deletingLoaded) showLibrary();
      void apiClient.fetchQueueCapacity(base).then(
        setQueueCapacity,
        () => undefined,
      );
    } catch (error) {
      deletedJobIdsRef.current.delete(jobId);
      setDeleteError(errorMessage(error));
    } finally {
      setDeleting(false);
    }
  }, [
    apiClient,
    deleteTarget,
    showLibrary,
    state,
    updateTrackedJobs,
  ]);

  const removeLocalRecord = useCallback(
    (job: TrackedJob) => {
      const { submissionId, jobId, fileName } = job.submission;
      removeSubmission(localStorage, submissionId);
      updateTrackedJobs((current) =>
        current.filter(
          (candidate) =>
            candidate.submission.submissionId !== submissionId,
        )
      );
      setDeleteNotice(
        `《${fileName}》已从此浏览器移除；服务器文件未更改。`,
      );
      const viewingSubmission =
        (state.phase === "processing" || state.phase === "failed") &&
        state.submissionId === submissionId;
      const viewingLoadedJob =
        state.phase === "loaded" &&
        state.source.kind === "api" &&
        state.source.jobId === jobId;
      if (viewingSubmission || viewingLoadedJob) showLibrary();
    },
    [showLibrary, state, updateTrackedJobs],
  );

  const viewProgress = useCallback((job: TrackedJob) => {
    foregroundSubmissionRef.current = job.submission.submissionId;
    setState({
      phase: "processing",
      fileName: job.submission.fileName,
      base: job.submission.base,
      submissionId: job.submission.submissionId,
      jobId: job.submission.jobId ?? undefined,
      jobState: job.status?.state ?? job.clientState,
      lastNonterminalStage: job.lastNonterminalState,
    });
  }, []);

  useEffect(() => {
    if (!deleteNotice) return;
    const timer = setTimeout(() => setDeleteNotice(null), 4_000);
    return () => clearTimeout(timer);
  }, [deleteNotice]);

  useEffect(() => {
    if (!completionNotice) return;
    const timer = setTimeout(() => setCompletionNotice(null), 6_000);
    return () => clearTimeout(timer);
  }, [completionNotice]);

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

  const openCompletedJob = useCallback(
    async (job: TrackedJob) => {
      const { jobId, base, fileName } = job.submission;
      if (!jobId) return;
      try {
        enterLoaded(
          await apiClient.fetchPatchBundle(base, jobId, decode),
          { kind: "api", base, jobId, fileName },
        );
      } catch (error) {
        updateTrackedJob(job.submission.submissionId, (current) => ({
          ...current,
          clientError: errorMessage(error),
        }));
      }
    },
    [apiClient, decode, enterLoaded, updateTrackedJob],
  );

  const pollTrackedJob = useCallback(
    async (
      submission: StoredSubmission,
      { sourceFile }: { sourceFile?: File } = {},
    ) => {
      const { submissionId, jobId, base } = submission;
      if (!jobId || pollingJobsRef.current.has(jobId)) return;
      pollingJobsRef.current.add(jobId);
      let lastNonterminal = "queued";
      try {
        const final = await apiClient.pollJob(base, jobId, (job) => {
          if (deletedJobIdsRef.current.has(jobId)) return;
          applyJobStatus(submissionId, job);
          if (!TERMINAL_JOB_STATES.has(job.state)) {
            lastNonterminal = job.state;
          }
          setState((previous) =>
            previous.phase === "processing" &&
            previous.submissionId === submissionId
              ? {
                  ...previous,
                  jobId,
                  jobState: job.state,
                  lastNonterminalStage: TERMINAL_JOB_STATES.has(job.state)
                    ? previous.lastNonterminalStage
                    : job.state,
                }
              : previous
          );
        });
        if (deletedJobIdsRef.current.has(jobId)) return;
        applyJobStatus(submissionId, final);
        if (
          foregroundSubmissionRef.current === submissionId &&
          final.state === "completed"
        ) {
          const current = trackedJobsRef.current.find(
            (job) => job.submission.submissionId === submissionId,
          );
          if (current) await openCompletedJob(current);
        } else if (final.state === "completed") {
          setCompletionNotice(
            `《${submission.fileName}》已准备好，可以继续创作。`,
          );
        }
      } catch (error) {
        if (deletedJobIdsRef.current.has(jobId)) return;
        const terminal = jobStatusFromError(error);
        if (terminal) applyJobStatus(submissionId, terminal);
        updateTrackedJob(submissionId, (current) => ({
          ...current,
          clientError: terminal ? null : errorMessage(error),
        }));
        if (
          foregroundSubmissionRef.current === submissionId
        ) {
          setState({
            phase: "failed",
            fileName: submission.fileName,
            sourceFile,
            base,
            submissionId,
            failedAt: lastNonterminal,
            issues: [errorMessage(error)],
            issueTitle: "处理未完成",
          });
        }
      } finally {
        pollingJobsRef.current.delete(jobId);
      }
    },
    [apiClient, applyJobStatus, openCompletedJob, updateTrackedJob],
  );

  const submitUpload = useCallback(
    async (
      base: string,
      file: File,
      existing?: StoredSubmission,
    ) => {
      const root = normalizeBase(base);
      const signature = `${root}\0${file.name}\0${file.size}\0${file.lastModified}`;
      if (inflightUploadsRef.current.has(signature)) return;

      const submission: StoredSubmission = existing ?? {
        submissionId: crypto.randomUUID(),
        jobId: null,
        controlToken: crypto.randomUUID(),
        base: root,
        fileName: file.name,
        submittedAt: new Date().toISOString(),
      };
      inflightUploadsRef.current.set(signature, submission.submissionId);
      foregroundSubmissionRef.current = submission.submissionId;
      upsertSubmission(localStorage, submission);
      updateTrackedJobs((current) => {
        const retained = current.filter(
          (job) =>
            job.submission.submissionId !== submission.submissionId,
        );
        return [...retained, trackedFromSubmission(submission)];
      });
      setState({
        phase: "processing",
        fileName: file.name,
        sourceFile: file,
        base: root,
        submissionId: submission.submissionId,
        jobState: "preflight",
        lastNonterminalStage: "preflight",
      });

      try {
        const accepted = await apiClient.uploadSong(
          root,
          file,
          submission.submissionId,
          submission.controlToken ?? crypto.randomUUID(),
        );
        if (!accepted.job_id) {
          throw new ApiError("upload response did not include a Job ID");
        }
        const acceptedSubmission = {
          ...submission,
          jobId: accepted.job_id,
        };
        upsertSubmission(localStorage, acceptedSubmission);
        updateTrackedJob(submission.submissionId, (current) => ({
          ...current,
          submission: acceptedSubmission,
          status: accepted,
          clientState: "accepted",
          clientError: null,
          lastNonterminalState: TERMINAL_JOB_STATES.has(accepted.state)
            ? current.lastNonterminalState
            : accepted.state,
        }));
        if (accepted.capacity) setQueueCapacity(accepted.capacity);
        setState((previous) =>
          previous.phase === "processing" &&
          previous.submissionId === submission.submissionId
            ? {
                ...previous,
                jobId: accepted.job_id,
                jobState: accepted.state,
                lastNonterminalStage: TERMINAL_JOB_STATES.has(accepted.state)
                  ? previous.lastNonterminalStage
                  : accepted.state,
              }
            : previous
        );
        await pollTrackedJob(acceptedSubmission, { sourceFile: file });
      } catch (error) {
        const preflight = isPreflightRejection(error);
        updateTrackedJob(submission.submissionId, (current) => ({
          ...current,
          clientError: errorMessage(error),
        }));
        if (foregroundSubmissionRef.current === submission.submissionId) {
          setState({
            phase: "failed",
            fileName: file.name,
            sourceFile: file,
            base: root,
            submissionId: submission.submissionId,
            failedAt: preflight ? "preflight" : "upload",
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
          });
        }
      } finally {
        inflightUploadsRef.current.delete(signature);
      }
    },
    [apiClient, pollTrackedJob, updateTrackedJob, updateTrackedJobs],
  );

  const handleUpload = useCallback(
    (base: string, file: File) => submitUpload(base, file),
    [submitUpload],
  );

  useEffect(() => {
    let cancelled = false;
    const restored = [...trackedJobsRef.current];
    if (restored.length === 0) return;

    for (const base of new Set(
      restored.map((job) => job.submission.base),
    )) {
      void apiClient.fetchQueueCapacity(base).then(
        (capacity) => {
          if (!cancelled) setQueueCapacity(capacity);
        },
        () => undefined,
      );
    }

    for (const tracked of restored) {
      const { submission } = tracked;
      void (
        submission.jobId
          ? apiClient.fetchJob(submission.base, submission.jobId)
          : apiClient.resolveSubmission(
              submission.base,
              submission.submissionId,
            )
      ).then(
        (status) => {
          if (cancelled || !status.job_id) return;
          const recovered = {
            ...submission,
            jobId: status.job_id,
          };
          upsertSubmission(localStorage, recovered);
          updateTrackedJob(submission.submissionId, (current) => ({
            ...current,
            submission: recovered,
          }));
          applyJobStatus(submission.submissionId, status);
          if (!TERMINAL_JOB_STATES.has(status.state)) {
            void pollTrackedJob(recovered);
          }
        },
        (error) => {
          if (cancelled) return;
          updateTrackedJob(submission.submissionId, (current) => ({
            ...current,
            clientError:
              error instanceof ApiError && error.status === 404
                ? "服务器未找到这次提交；可移除此浏览器记录后重新上传。"
                : errorMessage(error),
          }));
        },
      );
    }

    return () => {
      cancelled = true;
    };
  }, [
    apiClient,
    applyJobStatus,
    pollTrackedJob,
    updateTrackedJob,
  ]);

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

  const deleteFeedback = (
    <>
      <DeleteJobDialog
        job={deleteTarget}
        busy={deleting}
        error={deleteError}
        onCancel={() => {
          if (deleting) return;
          setDeleteTarget(null);
          setDeleteError(null);
        }}
        onConfirm={() => void confirmDelete()}
      />
      {deleteNotice && (
        <div className="delete-notice" role="status">
          {deleteNotice}
        </div>
      )}
      {completionNotice && (
        <div className="completion-notice" role="status">
          {completionNotice}
        </div>
      )}
    </>
  );

  if (state.phase === "library") {
    return (
      <AppFrame>
        {deleteFeedback}
        <CreatorStateShell
          label="My Songs"
          appState="library"
          activeView="library"
          onShowLibrary={showLibrary}
          onShowNewUpload={showNewUpload}
          canvas={
            <MySongsView
              jobs={trackedJobs}
              capacity={queueCapacity}
              onOpenCompleted={(job) => void openCompletedJob(job)}
              onViewProgress={viewProgress}
              onNewUpload={showNewUpload}
              onDelete={requestDelete}
              onRemoveLocal={removeLocalRecord}
            />
          }
          inspector={
            <div className="state-inspector">
              <strong>Browser scope</strong>
              <p>仅显示此浏览器保存的提交记录。</p>
              <p>账号级历史与跨设备同步尚未启用。</p>
            </div>
          }
          status={
            <>
              <strong>我的歌曲</strong>
              <span>{trackedJobs.length} 首</span>
              <span>正在处理 {queueCapacity.processing}</span>
              <span>等待 {queueCapacity.waiting}</span>
            </>
          }
        />
      </AppFrame>
    );
  }

  if (state.phase === "new-upload") {
    return (
      <AppFrame>
        {deleteFeedback}
        <CreatorStateShell
          label="New Song"
          appState="new-upload"
          activeView="new-upload"
          onShowLibrary={showLibrary}
          onShowNewUpload={showNewUpload}
          canvas={
            <>
              <NewSongView
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
              <strong>Upload rules</strong>
              <p>Preflight 通过后才会创建 Job。</p>
              <p>支持 WAV / MP3，最大 200 MiB、最长 600 秒。</p>
            </div>
          }
          status={
            <>
              <strong>上传新歌</strong>
              <span>WAV / MP3</span>
              <span>200 MiB · 600 秒</span>
              <span>New submission</span>
            </>
          }
        />
      </AppFrame>
    );
  }

  if (state.phase === "processing") {
    return (
      <AppFrame>
        {deleteFeedback}
        <CreatorStateShell
          label="Processing"
          appState={state.jobState}
          activeView="processing"
          onShowLibrary={showLibrary}
          onShowNewUpload={showNewUpload}
          canvas={
            <ProcessingPanel
              fileName={state.fileName}
              state={state.jobState}
              lastNonterminalState={state.lastNonterminalStage}
            />
          }
          inspector={
            <div className="state-inspector">
              <strong>Source retained</strong>
              <p>{state.fileName}</p>
              <p>Job {state.jobId ?? "pending preflight"}</p>
              <p>Worker state: {state.jobState}</p>
            </div>
          }
          status={
            <>
              <strong>Processing</strong>
              <span>{state.fileName}</span>
              <span>{state.jobState}</span>
              <span>{state.jobId ?? "validating input"}</span>
            </>
          }
        />
      </AppFrame>
    );
  }

  if (state.phase === "failed") {
    return (
      <AppFrame>
        {deleteFeedback}
        <CreatorStateShell
          label="Failed"
          appState="failed"
          activeView="failed"
          onShowLibrary={showLibrary}
          onShowNewUpload={showNewUpload}
          canvas={
            <section className="failed-state" data-testid="failed-state">
              <header className="state-heading">
                <span>Failed · truthful outcome</span>
                <h1>这首歌曲需要处理</h1>
                <p>{state.fileName}</p>
              </header>
              <ErrorPanel title={state.issueTitle} issues={state.issues} />
              <dl className="failed-context">
                <div>
                  <dt>File</dt>
                  <dd>{state.fileName}</dd>
                </div>
                <div>
                  <dt>Failed at</dt>
                  <dd>{state.failedAt}</dd>
                </div>
              </dl>
              <div className="failed-actions">
                <button
                  onClick={() => {
                    if (!state.sourceFile) {
                      showNewUpload();
                      return;
                    }
                    const tracked = trackedJobsRef.current.find(
                      (job) =>
                        job.submission.submissionId === state.submissionId,
                    );
                    void submitUpload(
                      state.base,
                      state.sourceFile,
                      tracked?.submission,
                    );
                  }}
                >
                  重新上传
                </button>
                <button onClick={showLibrary}>我的歌曲</button>
              </div>
            </section>
          }
          inspector={
            <div className="state-inspector">
              <strong>Source retained</strong>
              <p>Retry reuses the same submission identity.</p>
              <p>The API returns the existing Job if it already accepted it.</p>
            </div>
          }
          status={
            <>
              <strong>Failed</strong>
              <span>{state.fileName}</span>
              <span>{state.failedAt}</span>
              <span>Source retained</span>
            </>
          }
        />
      </AppFrame>
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
  const loadedTrackedJob =
    apiSource === null
      ? null
      : trackedJobs.find(
          (job) => job.submission.jobId === apiSource.jobId,
        ) ?? null;
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
  const exportView =
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
    <AppFrame>
      {deleteFeedback}
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
            <GlobalNavigation
              activeView="workbench"
              libraryLabel="← 我的歌曲"
              onShowLibrary={showLibrary}
              onShowNewUpload={showNewUpload}
            />
            <div className="topbar-actions">
              <div className="workbench-project-summary">
                <strong
                  className="workbench-project-name"
                  data-testid="workbench-project-name"
                  title={loadedSource.name}
                >
                  {loadedSource.name}
                </strong>
                <div className="workbench-project-facts" aria-label="曲目参数">
                  <span>
                    <small>BPM</small>
                    <b data-testid="header-bpm">{HEADER_NUMBER.format(model.bpm)}</b>
                  </span>
                  <span>
                    <small>Loop</small>
                    <b data-testid="header-loop">
                      {HEADER_NUMBER.format(model.durationSeconds)}s
                    </b>
                  </span>
                  <span>
                    <small>Key</small>
                    <b>{model.key ?? "—"}</b>
                  </span>
                </div>
              </div>
              {loadedTrackedJob?.submission.controlToken && (
                <button
                  className="btn-delete-track"
                  type="button"
                  aria-label="删除曲目"
                  title="删除当前曲目"
                  onClick={() => requestDelete(loadedTrackedJob)}
                >
                  <span aria-hidden="true">×</span>
                  <span className="btn-delete-track__label">删除</span>
                </button>
              )}
            </div>
          </>
        }
        instrumentCanvas={
          <>
            {mode === "source" && (
              <LoadedSourcePanel
                source={loadedSource}
                facts={loadedSourceFacts}
                onReplace={showNewUpload}
              />
            )}
            <div
              className="workbench-performance-view"
              hidden={mode !== "performance"}
            >
              <PatternSurface
                bundle={bundle}
                engine={engine}
                padCount={model.padCount}
                playheadStep={playheadStep}
                readiness={model.readiness}
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
            {mode === "export" && (
              <div className="workbench-export-view">
                {exportView}
              </div>
            )}
          </>
        }
        contextInspector={
          <>
            <div className="workbench-inspector-view" hidden={mode !== "source"}>
              <LoadedSourceInspector
                source={loadedSource}
                facts={loadedSourceFacts}
              />
            </div>
            <div className="workbench-inspector-view" hidden={mode !== "performance"}>
              <ContextInspector
                model={model}
                midiContent={
                  <MidiPanel
                    onTrigger={triggerPad}
                    bank={midiBank}
                    onBankChange={setMidiBank}
                    onMappingModeChange={setMidiMappingMode}
                    onStatusChange={setMidiStatus}
                  />
                }
              />
            </div>
            <div className="workbench-inspector-view" hidden={mode !== "export"}>
              <LoadedSourceInspector
                source={loadedSource}
                facts={loadedSourceFacts}
              />
            </div>
          </>
        }
        statusBar={
          <>
            <strong>MIDI {midiStatus.connection}</strong>
            <span>
              {midiStatus.devices.length > 0
                ? midiStatus.devices.join(", ")
                : "No MIDI input"}
            </span>
            <span>
              {midiMappingMode === "direct-16"
                ? "Direct 16 · Bank 不适用"
                : `8-pad Controller · Bank ${midiBank}`}
            </span>
            <span>{model.readiness} · {model.patchId}</span>
          </>
        }
      />
    </AppFrame>
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
    code === "duration_too_long" ||
    code === "audio_probe_timeout"
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
  activeView,
  onShowLibrary,
  onShowNewUpload,
  canvas,
  inspector,
  status,
}: {
  label: string;
  appState: string;
  activeView: "library" | "new-upload" | "processing" | "failed";
  onShowLibrary: () => void;
  onShowNewUpload: () => void;
  canvas: ReactNode;
  inspector: ReactNode;
  status: ReactNode;
}) {
  return (
    <WorkbenchShell
      shellLabel={`LMDJ ${label}`}
      mode="source"
      onModeChange={() => {}}
      availableModes={[]}
      appBar={
        <>
          <Wordmark />
          <GlobalNavigation
            activeView={activeView}
            onShowLibrary={onShowLibrary}
            onShowNewUpload={onShowNewUpload}
          />
          <span className="workbench-state-key">{appState}</span>
        </>
      }
      instrumentCanvas={canvas}
      contextInspector={inspector}
      statusBar={status}
    />
  );
}

function GlobalNavigation({
  activeView,
  libraryLabel = "我的歌曲",
  onShowLibrary,
  onShowNewUpload,
}: {
  activeView:
    | "library"
    | "new-upload"
    | "processing"
    | "failed"
    | "workbench";
  libraryLabel?: string;
  onShowLibrary: () => void;
  onShowNewUpload: () => void;
}) {
  return (
    <nav className="global-navigation" aria-label="主要导航">
      <button
        type="button"
        data-testid="my-songs-nav"
        aria-current={activeView === "library" ? "page" : undefined}
        onClick={onShowLibrary}
      >
        {libraryLabel}
      </button>
      <button
        type="button"
        className="global-navigation__new"
        data-testid="new-song-nav"
        aria-label="上传新歌"
        aria-current={activeView === "new-upload" ? "page" : undefined}
        onClick={onShowNewUpload}
      >
        <span className="global-navigation__new-icon" aria-hidden="true">＋</span>
        <span className="global-navigation__new-label">上传新歌</span>
      </button>
    </nav>
  );
}

function Wordmark() {
  return (
    <div className="wordmark">
      LMDJ<span className="wordmark-sub">patch view</span>
    </div>
  );
}

function AppFrame({ children }: { children: ReactNode }) {
  return (
    <div className="app">
      {children}
      <small
        className="app-version"
        data-testid="app-version"
        title="当前版本"
      >
        {PRODUCT_VERSION}
      </small>
    </div>
  );
}
