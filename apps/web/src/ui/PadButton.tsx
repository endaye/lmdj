import type {
  CSSProperties,
  KeyboardEvent,
  MouseEvent,
  PointerEvent,
} from "react";
import type { Pad } from "../patch/loader";
import {
  createVisualSignature,
  roleForPad,
} from "./generative/visualSignature";

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

function reducedMotionPreferred(): boolean {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function PadButton({
  pad,
  visualState,
  pressed,
  keyHint,
  onSelect,
  onPress,
  onRelease,
  onToggleMute,
}: {
  pad: Pad;
  visualState: PadVisualState;
  pressed: boolean;
  keyHint: string;
  onSelect: (index: number) => void;
  onPress?: (index: number) => void;
  onRelease?: (index: number) => void;
  onToggleMute?: (index: number) => void;
}) {
  const state = STATE_PRESENTATION[visualState];
  const identity = pad.element_id ?? pad.slot;
  const geometry = createVisualSignature(identity);
  const geometryStyle = {
    "--pad-geometry-angle": `${geometry.angle}deg`,
    "--pad-geometry-offset": `${geometry.offset}%`,
    "--pad-geometry-density": String(geometry.density),
    "--pad-geometry-phase": `${geometry.phase}%`,
  } as CSSProperties;
  const selected = visualState === "selected" || visualState === "playing";

  const handleContextMenu = (event: MouseEvent<HTMLButtonElement>) => {
    if (!onToggleMute) return;
    event.preventDefault();
    onToggleMute(pad.index);
  };

  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (!onPress || event.isPrimary === false || event.button > 0) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    onPress(pad.index);
  };

  const handlePointerRelease = (event: PointerEvent<HTMLButtonElement>) => {
    if (!onRelease) return;
    onRelease(pad.index);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!onPress || event.repeat || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    onPress(pad.index);
  };

  const handleKeyUp = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!onRelease || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    onRelease(pad.index);
  };

  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    onSelect(pad.index);
    if (event.detail !== 0 || !onPress || !onRelease) return;
    onPress(pad.index);
    onRelease(pad.index);
  };

  return (
    <button
      type="button"
      className={`pad pad--role-${roleForPad(pad)} pad--${visualState}`}
      data-testid={`pad-${pad.index}`}
      data-pad-index={pad.index}
      data-visual-state={visualState}
      data-geometry-signature={geometry.id}
      data-geometry-shape={geometry.shape}
      data-reduced-motion={String(reducedMotionPreferred())}
      data-selected={String(selected)}
      data-pressed={String(pressed)}
      aria-label={`Pad ${pad.index + 1}: ${pad.label}, ${visualState}`}
      aria-pressed={selected}
      style={geometryStyle}
      onClick={handleClick}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerRelease}
      onPointerCancel={handlePointerRelease}
      onLostPointerCapture={handlePointerRelease}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
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
