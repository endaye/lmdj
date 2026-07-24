import type { WorkbenchMode } from "./workbench/model";

const MODE_LABELS: Record<WorkbenchMode, string> = {
  source: "Source",
  performance: "Performance",
  export: "Export",
};

export function CreatorToolRail({
  mode,
  onModeChange,
  availableModes,
}: {
  mode: WorkbenchMode;
  onModeChange: (mode: WorkbenchMode) => void;
  availableModes: WorkbenchMode[];
}) {
  return (
    <nav className="creator-tool-rail" aria-label="Creator tools">
      <span className="creator-tool-rail__label">Creator Tools</span>
      {availableModes.map((availableMode) => (
        <button
          key={availableMode}
          type="button"
          className="creator-tool-rail__mode"
          aria-pressed={mode === availableMode}
          onClick={() => onModeChange(availableMode)}
        >
          {MODE_LABELS[availableMode]}
        </button>
      ))}
    </nav>
  );
}
