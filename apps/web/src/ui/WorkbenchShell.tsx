import type { ReactNode } from "react";
import { CreatorToolRail } from "./CreatorToolRail";
import type { WorkbenchMode, WorkbenchViewModel } from "./workbench/model";

/** Structural shell only: audio, loading, and playback effects stay in App and its slots. */
export function WorkbenchShell({
  model,
  mode,
  onModeChange,
  availableModes,
  appBar,
  instrumentCanvas,
  contextInspector,
  statusBar,
}: {
  model: WorkbenchViewModel;
  mode: WorkbenchMode;
  onModeChange: (mode: WorkbenchMode) => void;
  availableModes: WorkbenchMode[];
  appBar: ReactNode;
  instrumentCanvas: ReactNode;
  contextInspector: ReactNode;
  statusBar: ReactNode;
}) {
  return (
    <section className="workbench-shell" data-testid="workbench-shell" aria-label={`Patch ${model.patchId}`}>
      <header className="workbench-app-bar" data-testid="app-bar">
        {appBar}
      </header>
      <div className="workbench-shell__content">
        <div data-testid="creator-tools">
          <CreatorToolRail
            mode={mode}
            onModeChange={onModeChange}
            availableModes={availableModes}
          />
        </div>
        <main className="workbench-instrument-canvas" data-testid="instrument-canvas">
          {instrumentCanvas}
        </main>
        <aside className="workbench-context-inspector" data-testid="context-inspector">
          {contextInspector}
        </aside>
      </div>
      <footer className="workbench-status-bar" data-testid="status-bar">
        {statusBar}
      </footer>
    </section>
  );
}
