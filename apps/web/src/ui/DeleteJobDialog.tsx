import type { TrackedJob } from "./MySongsView";

export function DeleteJobDialog({
  job,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  job: TrackedJob | null;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!job) return null;
  const queued = job.status?.state === "queued";

  return (
    <div className="delete-dialog-backdrop">
      <section
        className="delete-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-dialog-title"
      >
        <header>
          <span>Manual delete</span>
          <h2 id="delete-dialog-title">
            永久删除《{job.submission.fileName}》？
          </h2>
        </header>
        <p>
          {queued
            ? "任务将从等待队列移除。"
            : "原始音频、生成素材、Patch 和导出文件将从服务器删除。"}
          此任务也会从本浏览器移除，操作无法撤销。
        </p>
        <small>已下载到设备的文件不会被删除。</small>
        {error && <p className="delete-dialog__error" role="alert">{error}</p>}
        <div className="delete-dialog__actions">
          <button type="button" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className="btn-danger"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "正在删除…" : queued ? "取消并删除" : "永久删除"}
          </button>
        </div>
      </section>
    </div>
  );
}
