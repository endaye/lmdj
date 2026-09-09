export type CreatorMode =
  | "project"
  | "sample"
  | "sequence"
  | "perform"
  | "soundset"
  | "slice";

interface ModeRailProps {
  activeMode: CreatorMode;
  onSelect: (mode: CreatorMode) => void;
  sequenceEnabled?: boolean;
  performEnabled?: boolean;
  soundSetEnabled?: boolean;
  sliceEnabled?: boolean;
}

export function ModeRail({
  activeMode,
  onSelect,
  sequenceEnabled = false,
  performEnabled = false,
  soundSetEnabled = false,
  sliceEnabled = false,
}: ModeRailProps) {
  return (
    <nav className="mode-rail" aria-label="Creator modes">
      <button
        className={`mode-button${activeMode === "project" ? " is-active" : ""}`}
        type="button"
        aria-current={activeMode === "project" ? "page" : undefined}
        onClick={() => onSelect("project")}
      >
        <span className="mode-glyph" aria-hidden="true">▣</span>
        <span className="mode-label">Project</span>
      </button>
      <button
        className={`mode-button${activeMode === "sequence" ? " is-active" : ""}`}
        type="button"
        disabled={!sequenceEnabled}
        aria-current={activeMode === "sequence" ? "page" : undefined}
        aria-label={sequenceEnabled ? "Sequence" : "Sequence — open a playable Project first"}
        onClick={() => onSelect("sequence")}
      >
        <span className="mode-glyph" aria-hidden="true">▤</span>
        <span className="mode-label">Sequence</span>
      </button>
      <button
        className={`mode-button${activeMode === "sample" ? " is-active" : ""}`}
        type="button"
        aria-current={activeMode === "sample" ? "page" : undefined}
        onClick={() => onSelect("sample")}
      >
        <span className="mode-glyph" aria-hidden="true">∿</span>
        <span className="mode-label">Sample</span>
      </button>
      <button
        className={`mode-button${activeMode === "slice" ? " is-active" : ""}`}
        type="button"
        disabled={!sliceEnabled}
        aria-current={activeMode === "slice" ? "page" : undefined}
        aria-label={sliceEnabled ? "Slice" : "Slice — open a Project with candidate support"}
        onClick={() => onSelect("slice")}
      >
        <span className="mode-glyph" aria-hidden="true">⋮</span>
        <span className="mode-label">Slice</span>
      </button>
      <button
        className={`mode-button${activeMode === "soundset" ? " is-active" : ""}`}
        type="button"
        disabled={!soundSetEnabled}
        aria-current={activeMode === "soundset" ? "page" : undefined}
        aria-label={soundSetEnabled
          ? "Sound Sets"
          : "Sound Sets — wait for the Runtime to start"}
        onClick={() => onSelect("soundset")}
      >
        <span className="mode-glyph" aria-hidden="true">◈</span>
        <span className="mode-label">Sound Sets</span>
      </button>
      <button
        className={`mode-button${activeMode === "perform" ? " is-active" : ""}`}
        type="button"
        disabled={!performEnabled}
        tabIndex={performEnabled ? undefined : -1}
        aria-current={activeMode === "perform" ? "page" : undefined}
        aria-label={performEnabled
          ? "Perform"
          : "Perform — requires a playable Project, running audio, and capture storage"}
        onClick={() => onSelect("perform")}
      >
        <span className="mode-glyph" aria-hidden="true">▶</span>
        <span className="mode-label">Perform</span>
        {!performEnabled ? <small aria-hidden="true">S10</small> : null}
      </button>
    </nav>
  );
}
