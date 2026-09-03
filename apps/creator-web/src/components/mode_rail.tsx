const futureModes = [{name: "Perform", stage: 10, glyph: "▶"}] as const;

export type CreatorMode = "project" | "sample" | "sequence";

interface ModeRailProps {
  activeMode: CreatorMode;
  onSelect: (mode: CreatorMode) => void;
  sequenceEnabled?: boolean;
}

export function ModeRail({activeMode, onSelect, sequenceEnabled = false}: ModeRailProps) {
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
      {futureModes.map(({name, stage, glyph}) => (
        <button
          className="mode-button"
          type="button"
          disabled
          tabIndex={-1}
          aria-label={`${name} — available in Stage ${stage}`}
          key={name}
        >
          <span className="mode-glyph" aria-hidden="true">{glyph}</span>
          <span className="mode-label">{name}</span>
          <small aria-hidden="true">S{stage}</small>
        </button>
      ))}
    </nav>
  );
}
