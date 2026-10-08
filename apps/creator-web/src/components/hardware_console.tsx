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

export interface StageFit {
  scale: number;
  // Translation of the workspace's top-left corner within the stage, applied
  // before rotation and scale (transform-origin 0 0).
  dx: number;
  dy: number;
  rotate: boolean;
}

// Desktop Final T2 (START HERE): the console scales proportionally to fit the
// stage and centres itself, keeping its internal 880×592 layout. A narrow
// portrait stage additionally turns it 90° counter-clockwise so the device
// still reads as landscape; that rotation never enlarges it.
export function fitConsoleToStage(stage: {width: number; height: number},
  natural: {width: number; height: number}, portrait: boolean): StageFit | null {
  if (natural.width <= 0 || natural.height <= 0 || stage.width <= 0 || stage.height <= 0) {
    return null;
  }
  if (portrait) {
    // rotate(-90deg) swaps the axes: the console's height spans the stage's
    // width and vice versa.
    const scale = Math.min(stage.width / natural.height, stage.height / natural.width, 1);
    return {
      scale,
      dx: (stage.width - natural.height * scale) / 2,
      dy: (stage.height + natural.width * scale) / 2,
      rotate: true,
    };
  }
  const scale = Math.min(stage.width / natural.width, stage.height / natural.height);
  return {
    scale,
    dx: (stage.width - natural.width * scale) / 2,
    dy: (stage.height - natural.height * scale) / 2,
    rotate: false,
  };
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
