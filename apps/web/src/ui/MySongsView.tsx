import { useState } from "react";
import type { JobStatus, QueueCapacity } from "../api/client";
import type { StoredSubmission } from "../jobs/storage";

export interface TrackedJob {
  submission: StoredSubmission;
  status: JobStatus | null;
  clientState: "preflight" | "accepted";
  clientError: string | null;
  lastNonterminalState: string;
}

const TERMINAL_STATES = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);

const PROCESSING_STATES = new Set([
  "generating",
  "separating",
  "extracting",
  "patchifying",
  "rendering",
]);

function stateLabel(job: TrackedJob): string {
  const state = job.status?.state;
  if (!state) return job.clientError ? "上传未完成" : "正在上传";
  if (state === "queued") {
    return job.status?.queue_position
      ? `等待中 · 第 ${job.status.queue_position} 位`
      : "等待执行槽";
  }
  if (state === "generating") return "正在生成";
  if (state === "separating") return "正在分离音轨";
  if (state === "extracting") return "正在提取素材";
  if (state === "patchifying") return "正在制作 Patch";
  if (state === "rendering") return "正在渲染";
  if (state === "completed") return "已完成";
  if (state === "interrupted") return "服务中断";
  if (state === "cancelled") return "已取消";
  if (state === "failed") return "处理失败";
  return state;
}

function submittedAt(job: TrackedJob): string {
  return job.status?.created_at || job.submission.submittedAt;
}

function submittedTime(job: TrackedJob): number {
  const parsed = Date.parse(submittedAt(job));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function formattedDate(job: TrackedJob): string {
  const value = submittedAt(job);
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function isRecent(job: TrackedJob): boolean {
  const state = job.status?.state;
  return state ? TERMINAL_STATES.has(state) : Boolean(job.clientError);
}

function activeRank(job: TrackedJob): number {
  const state = job.status?.state;
  if (state && PROCESSING_STATES.has(state)) return 0;
  if (state === "queued") return 1;
  return 2;
}

export function groupTrackedJobs(jobs: TrackedJob[]): {
  active: TrackedJob[];
  recent: TrackedJob[];
} {
  const active = jobs
    .filter((job) => !isRecent(job))
    .sort((left, right) => {
      const rank = activeRank(left) - activeRank(right);
      if (rank !== 0) return rank;
      if (left.status?.state === "queued" && right.status?.state === "queued") {
        return (
          (left.status.queue_position ?? Number.MAX_SAFE_INTEGER) -
          (right.status.queue_position ?? Number.MAX_SAFE_INTEGER)
        );
      }
      return submittedTime(left) - submittedTime(right);
    });
  const recent = jobs
    .filter(isRecent)
    .sort((left, right) => submittedTime(right) - submittedTime(left));
  return { active, recent };
}

function actionFor(job: TrackedJob): "progress" | "open" | "reason" | "retry" {
  if (job.status?.state === "completed") return "open";
  if (job.status?.state === "failed") return "reason";
  if (["interrupted", "cancelled"].includes(job.status?.state ?? "")) {
    return "retry";
  }
  if (job.clientError && !job.status) return "reason";
  return "progress";
}

function technicalState(job: TrackedJob): string {
  return job.status?.state ?? job.clientState;
}

function SongCard({
  job,
  onOpenCompleted,
  onViewProgress,
  onNewUpload,
  onDelete,
  onRemoveLocal,
}: {
  job: TrackedJob;
  onOpenCompleted: (job: TrackedJob) => void;
  onViewProgress: (job: TrackedJob) => void;
  onNewUpload: () => void;
  onDelete: (job: TrackedJob) => void;
  onRemoveLocal: (job: TrackedJob) => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const key = job.submission.jobId ?? job.submission.submissionId;
  const state = job.status?.state;
  const terminal = TERMINAL_STATES.has(state ?? "");
  const canDeleteServer =
    Boolean(job.submission.jobId && job.submission.controlToken) &&
    (state === "queued" || terminal);
  const shouldRemoveLocally =
    !canDeleteServer &&
    (
      (!job.status && Boolean(job.clientError)) ||
      terminal ||
      !job.submission.jobId
    );
  const action = actionFor(job);
  const detailsId = `song-details-${key}`;

  return (
    <li
      className={`song-card song-card--${state ?? (job.clientError ? "failed" : job.clientState)}`}
      data-testid={`song-card-${key}`}
    >
      <div className="song-card__identity">
        <strong>{job.submission.fileName}</strong>
        <span>{stateLabel(job)}</span>
        <time dateTime={submittedAt(job)}>{formattedDate(job)}</time>
      </div>
      <div className="song-card__actions">
        {action === "open" && (
          <button type="button" onClick={() => onOpenCompleted(job)}>
            继续创作
          </button>
        )}
        {action === "progress" && (
          <button type="button" onClick={() => onViewProgress(job)}>
            查看进度
          </button>
        )}
        {action === "reason" && (
          <button
            type="button"
            aria-controls={detailsId}
            aria-expanded={detailsOpen}
            onClick={() => setDetailsOpen((open) => !open)}
          >
            查看原因
          </button>
        )}
        {action === "retry" && (
          <button type="button" onClick={onNewUpload}>
            重新上传
          </button>
        )}
        <details className="song-card__menu">
          <summary
            role="button"
            aria-label={`更多操作：${job.submission.fileName}`}
          >
            ···
          </summary>
          <div className="song-card__menu-popover">
            <button
              type="button"
              aria-controls={detailsId}
              aria-expanded={detailsOpen}
              onClick={() => setDetailsOpen((open) => !open)}
            >
              技术详情
            </button>
            {canDeleteServer && (
              <button
                type="button"
                className="btn-danger"
                onClick={() => onDelete(job)}
              >
                {state === "queued" ? "取消并删除" : "永久删除"}
              </button>
            )}
            {!canDeleteServer && !shouldRemoveLocally && (
              <button type="button" disabled>
                处理完成后可删除
              </button>
            )}
            {shouldRemoveLocally && (
              <button
                type="button"
                className="btn-danger"
                onClick={() => onRemoveLocal(job)}
              >
                从此浏览器移除记录
              </button>
            )}
          </div>
        </details>
      </div>
      {detailsOpen && (
        <dl className="song-card__details" id={detailsId}>
          <div>
            <dt>Job</dt>
            <dd>{job.submission.jobId ?? "尚未被 API 接受"}</dd>
          </div>
          <div>
            <dt>技术状态</dt>
            <dd>{technicalState(job)}</dd>
          </div>
          <div>
            <dt>Pipeline</dt>
            <dd>{job.status?.pipeline ?? "—"}</dd>
          </div>
          <div>
            <dt>API</dt>
            <dd>{job.submission.base}</dd>
          </div>
          {(job.status?.error || job.clientError) && (
            <div className="song-card__details-error">
              <dt>原因</dt>
              <dd role="alert">{job.status?.error || job.clientError}</dd>
            </div>
          )}
        </dl>
      )}
    </li>
  );
}

function SongSection({
  title,
  testId,
  jobs,
  ...actions
}: {
  title: string;
  testId: string;
  jobs: TrackedJob[];
  onOpenCompleted: (job: TrackedJob) => void;
  onViewProgress: (job: TrackedJob) => void;
  onNewUpload: () => void;
  onDelete: (job: TrackedJob) => void;
  onRemoveLocal: (job: TrackedJob) => void;
}) {
  return (
    <section className="song-section" data-testid={testId}>
      <header>
        <h2>{title}</h2>
        <span>{jobs.length}</span>
      </header>
      <ol className="song-list">
        {jobs.map((job) => (
          <SongCard
            key={job.submission.submissionId}
            job={job}
            {...actions}
          />
        ))}
      </ol>
    </section>
  );
}

export function MySongsView({
  jobs,
  capacity,
  onOpenCompleted,
  onViewProgress,
  onNewUpload,
  onDelete,
  onRemoveLocal,
}: {
  jobs: TrackedJob[];
  capacity: QueueCapacity;
  onOpenCompleted: (job: TrackedJob) => void;
  onViewProgress: (job: TrackedJob) => void;
  onNewUpload: () => void;
  onDelete: (job: TrackedJob) => void;
  onRemoveLocal: (job: TrackedJob) => void;
}) {
  const { active, recent } = groupTrackedJobs(jobs);

  return (
    <section className="my-songs" data-testid="my-songs">
      <header className="my-songs__header">
        <div>
          <span>My Songs</span>
          <h1>我的歌曲</h1>
          <p>仅显示此浏览器提交的曲目</p>
        </div>
        <div
          className="queue-capacity"
          data-testid="queue-capacity"
          aria-label="处理容量"
        >
          <span>最大并发 {capacity.max_concurrency}</span>
          <span>正在处理 {capacity.processing}</span>
          <span>等待 {capacity.waiting}</span>
        </div>
      </header>

      {jobs.length === 0 ? (
        <div className="my-songs__empty" data-testid="my-songs-empty">
          <strong>还没有歌曲</strong>
          <p>上传一首 WAV 或 MP3，把它变成可演奏 Patch。</p>
          <button type="button" onClick={onNewUpload}>
            上传第一首歌
          </button>
        </div>
      ) : (
        <>
          {active.length > 0 && (
            <SongSection
              title="正在处理"
              testId="active-songs"
              jobs={active}
              onOpenCompleted={onOpenCompleted}
              onViewProgress={onViewProgress}
              onNewUpload={onNewUpload}
              onDelete={onDelete}
              onRemoveLocal={onRemoveLocal}
            />
          )}
          {recent.length > 0 && (
            <SongSection
              title="最近歌曲"
              testId="recent-songs"
              jobs={recent}
              onOpenCompleted={onOpenCompleted}
              onViewProgress={onViewProgress}
              onNewUpload={onNewUpload}
              onDelete={onDelete}
              onRemoveLocal={onRemoveLocal}
            />
          )}
        </>
      )}
    </section>
  );
}
