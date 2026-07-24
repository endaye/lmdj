import type { WorkbenchMode } from "./workbench/model";

const MODE_LABELS: Record<WorkbenchMode, string> = {
  source: "Source",
  performance: "Performance",
  export: "Export",
};

const MODE_ICONS: Record<WorkbenchMode, string> = {
  source: "◉",
  performance: "▦",
  export: "⇩",
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
          aria-label={MODE_LABELS[availableMode]}
          aria-pressed={mode === availableMode}
          onClick={() => onModeChange(availableMode)}
        >
          <span
            className="creator-tool-rail__icon"
            data-icon={MODE_ICONS[availableMode]}
            aria-hidden="true"
          />
          <span className="creator-tool-rail__text">
            {MODE_LABELS[availableMode]}
          </span>
        </button>
      ))}
    </nav>
  );
}
