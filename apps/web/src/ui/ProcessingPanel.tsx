import { UploadingView } from "./UploadingView";
import type { QueueCapacity } from "../api/client";
import { JobQueuePanel, type TrackedJob } from "./JobQueuePanel";
import { UploadPanel } from "./UploadPanel";

export function ProcessingPanel({
  fileName,
  state,
  lastNonterminalState,
  jobs,
  capacity,
  onUpload,
  onOpenCompleted,
  onDelete,
}: {
  fileName: string;
  state: string;
  lastNonterminalState: string;
  jobs: TrackedJob[];
  capacity: QueueCapacity;
  onUpload: (base: string, file: File) => void;
  onOpenCompleted: (job: TrackedJob) => void;
  onDelete: (job: TrackedJob) => void;
}) {
  return (
    <section className="processing-panel" data-testid="processing-panel">
      <header className="state-heading">
        <span>Processing · live evidence</span>
        <h1>Building your Patch</h1>
        <p>
          Source retained · <strong>{fileName}</strong>
        </p>
      </header>
      <UploadingView
        state={state}
        lastNonterminalState={lastNonterminalState}
      />
      <UploadPanel onUpload={onUpload} />
      <JobQueuePanel
        jobs={jobs}
        capacity={capacity}
        onOpenCompleted={onOpenCompleted}
        onDelete={onDelete}
      />
    </section>
  );
}
