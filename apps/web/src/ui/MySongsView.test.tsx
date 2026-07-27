import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobStatus, QueueCapacity } from "../api/client";
import type { StoredSubmission } from "../jobs/storage";
import {
  groupTrackedJobs,
  MySongsView,
  type TrackedJob,
} from "./MySongsView";
import { createVisualSignature } from "./generative/visualSignature";

const capacity: QueueCapacity = {
  max_concurrency: 1,
  processing: 1,
  waiting: 1,
};

function submission(
  submissionId: string,
  jobId: string | null,
  fileName: string,
  submittedAt = "2026-07-26T00:00:00.000Z",
): StoredSubmission {
  return {
    submissionId,
    jobId,
    controlToken: `control-${submissionId}-1234567890`,
    base: "http://localhost:8000",
    fileName,
    submittedAt,
  };
}

function status(
  jobId: string,
  state: string,
  overrides: Partial<JobStatus> = {},
): JobStatus {
  return {
    job_id: jobId,
    state,
    error: null,
    error_code: null,
    patch_id: null,
    package_dir: null,
    quality: null,
    submission_id: `submission-${jobId}`,
    original_filename: `${jobId}.wav`,
    pipeline: "materials-v1",
    created_at: "2026-07-26T00:00:00Z",
    updated_at: "2026-07-26T00:00:01Z",
    queue_position: null,
    capacity,
    ...overrides,
  };
}

function tracked(
  submissionId: string,
  jobId: string | null,
  fileName: string,
  state: string | null,
  overrides: Partial<TrackedJob> = {},
): TrackedJob {
  return {
    submission: submission(submissionId, jobId, fileName),
    status: state && jobId ? status(jobId, state) : null,
    clientState: jobId ? "accepted" : "preflight",
    clientError: null,
    lastNonterminalState: state ?? "preflight",
    ...overrides,
  };
}

const actions = {
  onOpenCompleted: vi.fn(),
  onViewProgress: vi.fn(),
  onNewUpload: vi.fn(),
  onDelete: vi.fn(),
  onRemoveLocal: vi.fn(),
};

describe("MySongsView", () => {
  it("groups active work above recent songs and preserves queue order", () => {
    const processing = tracked(
      "submission-processing",
      "job-processing",
      "processing.wav",
      "extracting",
    );
    const queuedSecond = tracked(
      "submission-queued-2",
      "job-queued-2",
      "queued-2.wav",
      "queued",
    );
    queuedSecond.status = status("job-queued-2", "queued", {
      queue_position: 2,
    });
    const queuedFirst = tracked(
      "submission-queued-1",
      "job-queued-1",
      "queued-1.wav",
      "queued",
    );
    queuedFirst.status = status("job-queued-1", "queued", {
      queue_position: 1,
    });
    const completed = tracked(
      "submission-completed",
      "job-completed",
      "finished.wav",
      "completed",
    );

    const grouped = groupTrackedJobs([
      completed,
      queuedSecond,
      queuedFirst,
      processing,
    ]);

    expect(grouped.active).toEqual([processing, queuedFirst, queuedSecond]);
    expect(grouped.recent).toEqual([completed]);
  });

  it("shows browser scope, capacity, truthful sections, and product actions", async () => {
    const processing = tracked(
      "submission-a",
      "job-a",
      "song-a.wav",
      "separating",
    );
    const queued = tracked(
      "submission-b",
      "job-b",
      "song-b.wav",
      "queued",
    );
    queued.status = status("job-b", "queued", { queue_position: 1 });
    const completed = tracked(
      "submission-c",
      "job-c",
      "song-c.wav",
      "completed",
    );

    render(
      <MySongsView
        jobs={[completed, queued, processing]}
        capacity={capacity}
        {...actions}
      />,
    );

    expect(screen.getByRole("heading", { name: "我的歌曲" })).toBeInTheDocument();
    expect(screen.getByText("仅显示此浏览器提交的曲目")).toBeInTheDocument();
    expect(screen.getByTestId("queue-capacity")).toHaveTextContent("最大并发 1");
    expect(screen.getByTestId("active-songs")).toHaveTextContent("正在处理");
    expect(screen.getByTestId("recent-songs")).toHaveTextContent("最近歌曲");
    expect(screen.queryByText("Upload Queue")).not.toBeInTheDocument();
    expect(screen.getByTestId("song-card-job-a")).toHaveTextContent(
      "正在分离音轨",
    );
    expect(screen.getByTestId("song-card-job-b")).toHaveTextContent(
      "等待中 · 第 1 位",
    );
    expect(
      within(screen.getByTestId("song-card-job-a")).getByTestId(
        "song-signature-submission-a",
      ),
    ).toHaveAttribute("data-phase", "separating");
    expect(
      within(screen.getByTestId("song-card-job-a")).getByTestId(
        "song-signature-submission-a",
      ),
    ).toHaveAttribute(
      "data-signature",
      createVisualSignature(processing.submission.submissionId).id,
    );
    expect(
      within(screen.getByTestId("song-card-job-b")).getByTestId(
        "song-signature-submission-b",
      ),
    ).toHaveAttribute("data-phase", "queued");
    expect(
      within(screen.getByTestId("song-card-job-c")).getByTestId(
        "song-signature-submission-c",
      ),
    ).toHaveAttribute("data-phase", "ready");
    expect(
      within(screen.getByTestId("song-card-job-c")).getByRole("button", {
        name: "继续创作",
      }),
    ).toBeEnabled();
    expect(screen.queryByText("job-c")).not.toBeInTheDocument();

    await userEvent.click(
      within(screen.getByTestId("song-card-job-c")).getByRole("button", {
        name: "继续创作",
      }),
    );
    expect(actions.onOpenCompleted).toHaveBeenCalledWith(completed);
  });

  it("keeps Job, API, pipeline, and errors behind details", async () => {
    const failed = tracked(
      "submission-failed",
      "job-failed",
      "broken.wav",
      "failed",
    );
    failed.status = status("job-failed", "failed", {
      error: "decoder stopped",
    });

    render(
      <MySongsView jobs={[failed]} capacity={capacity} {...actions} />,
    );

    expect(screen.queryByText("job-failed")).not.toBeInTheDocument();
    expect(screen.queryByText("decoder stopped")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "查看原因" }));
    expect(screen.getByText("job-failed")).toBeInTheDocument();
    expect(screen.getByText("materials-v1")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("decoder stopped");
  });

  it("puts destructive actions in the overflow menu", async () => {
    const queued = tracked(
      "submission-b",
      "job-b",
      "song-b.wav",
      "queued",
    );
    queued.status = status("job-b", "queued", { queue_position: 1 });
    const onDelete = vi.fn();

    render(
      <MySongsView
        jobs={[queued]}
        capacity={capacity}
        {...actions}
        onDelete={onDelete}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "更多操作：song-b.wav" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "取消并删除" }));
    expect(onDelete).toHaveBeenCalledWith(queued);
  });

  it("offers a truthful local-only removal for an unrecoverable record", async () => {
    const stale = tracked(
      "submission-stale",
      "job-stale",
      "stale.wav",
      null,
      { clientError: "服务器未找到这次提交" },
    );
    const onRemoveLocal = vi.fn();

    render(
      <MySongsView
        jobs={[stale]}
        capacity={capacity}
        {...actions}
        onRemoveLocal={onRemoveLocal}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "更多操作：stale.wav" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "从此浏览器移除记录" }),
    );
    expect(onRemoveLocal).toHaveBeenCalledWith(stale);
  });

  it("renders a useful empty state without empty song sections", async () => {
    const onNewUpload = vi.fn();
    render(
      <MySongsView
        jobs={[]}
        capacity={{ max_concurrency: 1, processing: 0, waiting: 0 }}
        {...actions}
        onNewUpload={onNewUpload}
      />,
    );

    expect(screen.getByTestId("my-songs-empty")).toHaveTextContent(
      "还没有歌曲",
    );
    expect(screen.queryByTestId("active-songs")).not.toBeInTheDocument();
    expect(screen.queryByTestId("recent-songs")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "上传第一首歌" }),
    );
    expect(onNewUpload).toHaveBeenCalledOnce();
  });
});
