import {type ReactNode} from "react";

export const LAYOUT_STORAGE_KEY = "lmdj.creator.layout";
export type CreatorLayout = "workspace" | "hardware";

export function readCreatorLayout(): CreatorLayout {
  if (typeof window === "undefined") return "workspace";
  try {
    const query = new URLSearchParams(window.location.search).get("layout");
    if (query === "hardware" || query === "workspace") {
      window.localStorage.setItem(LAYOUT_STORAGE_KEY, query);
      return query;
    }
    const stored = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (stored === "hardware" || stored === "workspace") return stored;
  } catch {
    // Host presentation preference is best-effort and never Project Truth.
  }
  return "workspace";
}

export function writeCreatorLayout(layout: CreatorLayout): void {
  try {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, layout);
  } catch {
    // A blocked store must not prevent in-memory layout switching.
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
