const futureModes = [
  {name: "Sequence", stage: 9},
  {name: "Perform", stage: 10},
] as const;

export type CreatorMode = "project" | "sample";

interface ModeRailProps {
  activeMode: CreatorMode;
  onSelect: (mode: CreatorMode) => void;
}

export function ModeRail({activeMode, onSelect}: ModeRailProps) {
  return (
    <nav className="mode-rail" aria-label="Creator modes">
      <button
        className={`mode-button${activeMode === "project" ? " is-active" : ""}`}
        type="button"
        aria-current={activeMode === "project" ? "page" : undefined}
        onClick={() => onSelect("project")}
      >
        <span aria-hidden="true">P</span>
        <span className="mode-label">Project</span>
      </button>
      <button
        className={`mode-button${activeMode === "sample" ? " is-active" : ""}`}
        type="button"
        aria-current={activeMode === "sample" ? "page" : undefined}
        onClick={() => onSelect("sample")}
      >
        <span aria-hidden="true">S</span>
        <span className="mode-label">Sample</span>
      </button>
      {futureModes.map(({name, stage}) => (
        <button
          className="mode-button"
          type="button"
          disabled
          tabIndex={-1}
          aria-label={`${name} — available in Stage ${stage}`}
          key={name}
        >
          <span aria-hidden="true">{name.slice(0, 1)}</span>
          <span className="mode-label">{name}</span>
          <small aria-hidden="true">S{stage}</small>
        </button>
      ))}
    </nav>
  );
}
