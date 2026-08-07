const futureModes = [
  {name: "Sample", stage: 8},
  {name: "Sequence", stage: 9},
  {name: "Perform", stage: 10},
] as const;

export function ModeRail() {
  return (
    <nav className="mode-rail" aria-label="Creator modes">
      <button className="mode-button is-active" type="button" aria-current="page">
        <span aria-hidden="true">P</span>
        <span className="mode-label">Project</span>
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
