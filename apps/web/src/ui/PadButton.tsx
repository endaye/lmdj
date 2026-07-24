import type { CSSProperties, MouseEvent } from "react";
import type { Pad } from "../patch/loader";

export type PadVisualState =
  | "idle"
  | "selected"
  | "playing"
  | "muted"
  | "missing"
  | "empty"
  | "reserved";

const STATE_PRESENTATION: Record<PadVisualState, { label: string; icon: string }> = {
  idle: { label: "READY", icon: "●" },
  selected: { label: "SELECTED", icon: "◎" },
  playing: { label: "PLAYING", icon: "▶" },
  muted: { label: "MUTED", icon: "⊘" },
  missing: { label: "ERROR", icon: "!" },
  empty: { label: "EMPTY", icon: "○" },
  reserved: { label: "RESERVED", icon: "◇" },
};

function hashSource(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function geometryFor(pad: Pad): {
  signature: string;
  shape: "circle" | "grid" | "slice" | "wave";
  style: CSSProperties;
} {
  const identity = pad.element_id ?? pad.slot;
  const hash = hashSource(identity);
  const shapes = ["circle", "grid", "slice", "wave"] as const;
  const shape = shapes[hash % shapes.length];
  const angle = (hash >>> 4) % 180;
  const offset = 18 + ((hash >>> 12) % 55);
  return {
    signature: `${shape}-${angle}-${offset}`,
    shape,
    style: {
      "--pad-geometry-angle": `${angle}deg`,
      "--pad-geometry-offset": `${offset}%`,
    } as CSSProperties,
  };
}

function roleFor(pad: Pad): string {
  if (pad.action === "empty") return "empty";
  if (pad.index === 0) return "drums";
  if (pad.index === 1) return "bass";
  if (pad.index === 2) return "harmony";
  if (pad.index === 3) return "lead";
  return "action";
}

function reducedMotionPreferred(): boolean {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function PadButton({
  pad,
  visualState,
  keyHint,
  onSelect,
  onTrigger,
  onToggleMute,
}: {
  pad: Pad;
  visualState: PadVisualState;
  keyHint: string;
  onSelect: (index: number) => void;
  onTrigger?: (index: number) => void;
  onToggleMute?: (index: number) => void;
}) {
  const state = STATE_PRESENTATION[visualState];
  const geometry = geometryFor(pad);
  const selected = visualState === "selected" || visualState === "playing";

  const handleContextMenu = (event: MouseEvent<HTMLButtonElement>) => {
    if (!onToggleMute) return;
    event.preventDefault();
    onToggleMute(pad.index);
  };

  return (
    <button
      type="button"
      className={`pad pad--role-${roleFor(pad)} pad--${visualState}`}
      data-testid={`pad-${pad.index}`}
      data-pad-index={pad.index}
      data-visual-state={visualState}
      data-geometry-signature={geometry.signature}
      data-geometry-shape={geometry.shape}
      data-reduced-motion={String(reducedMotionPreferred())}
      data-selected={String(selected)}
      aria-label={`Pad ${pad.index + 1}: ${pad.label}, ${visualState}`}
      aria-pressed={selected}
      style={geometry.style}
      onClick={() => {
        onSelect(pad.index);
        onTrigger?.(pad.index);
      }}
      onContextMenu={handleContextMenu}
    >
      <span className="pad-index">{String(pad.index + 1).padStart(2, "0")}</span>
      <kbd className="pad-key">{keyHint}</kbd>
      <span className="pad-geometry" aria-hidden="true" />
      <span className="pad-slot">{pad.slot}</span>
      <span className="pad-label">{pad.label}</span>
      <span className="pad-state" data-testid={`pad-state-${pad.index}`}>
        <span className="pad-state__icon" data-testid={`pad-state-icon-${pad.index}`}>
          {state.icon}
        </span>
        {state.label}
      </span>
    </button>
  );
}
