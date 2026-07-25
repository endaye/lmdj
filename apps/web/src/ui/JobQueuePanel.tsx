import type { JobStatus, QueueCapacity } from "../api/client";
import type { StoredSubmission } from "../jobs/storage";

export interface TrackedJob {
  submission: StoredSubmission;
  status: JobStatus | null;
  clientState: "preflight" | "accepted";
  clientError: string | null;
  lastNonterminalState: string;
}

function stateLabel(job: TrackedJob): string {
  const state = job.status?.state;
  if (!state) return job.clientError ? "上传未完成" : "输入检查";
  if (state === "queued") {
    return job.status?.queue_position
      ? `等待 · 队列位置 ${job.status.queue_position}`
      : "等待执行槽";
  }
  if (["generating", "separating", "extracting", "patchifying", "rendering"].includes(state)) {
    return "正在处理";
  }
  if (state === "completed") return "处理完成";
  if (state === "interrupted") return "服务中断";
  if (state === "cancelled") return "已取消";
  if (state === "failed") return "处理失败";
  return state;
}

export function JobQueuePanel({
  jobs,
  capacity,
  onOpenCompleted,
}: {
  jobs: TrackedJob[];
  capacity: QueueCapacity;
  onOpenCompleted: (job: TrackedJob) => void;
}) {
  if (jobs.length === 0) return null;

  return (
    <section className="job-queue" data-testid="job-queue">
      <header className="job-queue__header">
        <div>
          <span>Browser-owned tasks</span>
          <h2>Upload Queue</h2>
        </div>
        <div
          className="queue-capacity"
          data-testid="queue-capacity"
          aria-label="Queue capacity"
        >
          <span>最大并发 {capacity.max_concurrency}</span>
          <span>正在处理 {capacity.processing}</span>
          <span>等待 {capacity.waiting}</span>
        </div>
      </header>
      <ol className="job-list">
        {jobs.map((job) => {
          const key = job.submission.jobId ?? job.submission.submissionId;
          const state = job.status?.state;
          return (
            <li
              className={`job-card job-card--${state ?? job.clientState}`}
              data-testid={`job-card-${key}`}
              key={job.submission.submissionId}
            >
              <div className="job-card__identity">
                <strong>{job.submission.fileName}</strong>
                <span>{stateLabel(job)}</span>
              </div>
              <dl>
                <div>
                  <dt>Job</dt>
                  <dd>{job.submission.jobId ?? "等待 API 接受"}</dd>
                </div>
                <div>
                  <dt>提交时间</dt>
                  <dd>{job.status?.created_at || job.submission.submittedAt}</dd>
                </div>
                <div>
                  <dt>状态</dt>
                  <dd>{state ?? job.clientState}</dd>
                </div>
                {job.status?.queue_position !== null &&
                  job.status?.queue_position !== undefined && (
                    <div>
                      <dt>队列</dt>
                      <dd>队列位置 {job.status.queue_position}</dd>
                    </div>
                  )}
              </dl>
              {state === "interrupted" && (
                <p className="job-card__terminal">
                  服务在任务完成前重启；请重新选择源文件提交。
                </p>
              )}
              {job.status?.error && (
                <p className="job-card__error">{job.status.error}</p>
              )}
              {job.clientError && (
                <p className="job-card__error" role="alert">
                  {job.clientError}
                </p>
              )}
              {state === "completed" && (
                <button
                  type="button"
                  onClick={() => onOpenCompleted(job)}
                >
                  Open Patch
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
