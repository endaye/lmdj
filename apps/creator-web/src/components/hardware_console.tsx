import {type ReactNode} from "react";

// The layout preference and `?layout=` query were retired with the workspace
// shell. A browser that stored `workspace` while the toggle existed would
// otherwise carry a dead value forever, so the key is removed once on boot.
export function retireCreatorLayoutPreference(): void {
  try {
    window.localStorage.removeItem("lmdj.creator.layout");
  } catch {
    // A blocked store has nothing to retire.
  }
}

export interface HardwareConsoleProps {
  physicalControls: ReactNode;
  overview: ReactNode;
  pads: ReactNode;
  touchWorkspace: ReactNode;
}

export function HardwareConsole(props: HardwareConsoleProps) {
  return (
    <div className="hardware-console" data-testid="hardware-console">
      <aside aria-label="Physical controls" data-testid="physical-controls">
        {props.physicalControls}
      </aside>
      <section aria-label="Overview display" data-testid="overview-display">
        {props.overview}
      </section>
      <section aria-label="Pad matrix" data-testid="pad-matrix">
        {props.pads}
      </section>
      <section aria-label="Touch workspace" data-testid="touch-workspace">
        {props.touchWorkspace}
      </section>
    </div>
  );
}
