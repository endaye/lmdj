import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { JobStatus, QueueCapacity } from "../api/client";
import type { StoredSubmission } from "../jobs/storage";
import { JobQueuePanel, type TrackedJob } from "./JobQueuePanel";

const capacity: QueueCapacity = {
  max_concurrency: 1,
  processing: 1,
  waiting: 1,
};

function submission(
  submissionId: string,
  jobId: string,
  fileName: string,
): StoredSubmission {
  return {
    submissionId,
    jobId,
    base: "http://localhost:8000",
    fileName,
    submittedAt: "2026-07-26T00:00:00.000Z",
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
    created_at: "2026-07-26T00:00:00Z",
    updated_at: "2026-07-26T00:00:01Z",
    queue_position: null,
    capacity,
    ...overrides,
  };
}

describe("JobQueuePanel", () => {
  it("shows capacity, identity, active work, and FIFO position", () => {
    const jobs: TrackedJob[] = [
      {
        submission: submission("submission-a", "job-a", "song-a.wav"),
        status: status("job-a", "separating"),
        clientState: "accepted",
        clientError: null,
        lastNonterminalState: "separating",
      },
      {
        submission: submission("submission-b", "job-b", "song-b.wav"),
        status: status("job-b", "queued", { queue_position: 1 }),
        clientState: "accepted",
        clientError: null,
        lastNonterminalState: "queued",
      },
    ];

    render(
      <JobQueuePanel
        jobs={jobs}
        capacity={capacity}
        onOpenCompleted={vi.fn()}
      />,
    );

    expect(screen.getByTestId("queue-capacity")).toHaveTextContent("最大并发 1");
    expect(screen.getByTestId("queue-capacity")).toHaveTextContent("正在处理 1");
    expect(screen.getByTestId("queue-capacity")).toHaveTextContent("等待 1");
    expect(screen.getByTestId("job-card-job-a")).toHaveTextContent("song-a.wav");
    expect(screen.getByTestId("job-card-job-a")).toHaveTextContent("job-a");
    expect(screen.getByTestId("job-card-job-a")).toHaveTextContent("正在处理");
    expect(screen.getByTestId("job-card-job-b")).toHaveTextContent("song-b.wav");
    expect(screen.getByTestId("job-card-job-b")).toHaveTextContent("队列位置 1");
  });

  it("explains an interrupted terminal job and permits explicit resubmission", () => {
    const jobs: TrackedJob[] = [
      {
        submission: submission("submission-old", "job-old", "old.wav"),
        status: status("job-old", "interrupted", {
          error: "API service restarted before this Job completed.",
          error_code: "service_interrupted",
        }),
        clientState: "accepted",
        clientError: null,
        lastNonterminalState: "separating",
      },
    ];

    render(
      <JobQueuePanel
        jobs={jobs}
        capacity={{ ...capacity, processing: 0, waiting: 0 }}
        onOpenCompleted={vi.fn()}
      />,
    );

    expect(screen.getByTestId("job-card-job-old")).toHaveTextContent("服务中断");
    expect(screen.getByTestId("job-card-job-old")).toHaveTextContent(
      "请重新选择源文件提交",
    );
    expect(screen.getByTestId("job-card-job-old")).not.toHaveTextContent(
      "Failed to fetch",
    );
  });
});
