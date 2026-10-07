import {useRef, type ReactNode, type MouseEvent, type Ref} from "react";

import type {CreatorMode} from "./creator_mode";
import type {Bank} from "../state/creator_state";
import {BANK_NAMES} from "../state/view_model";
import {
  EncoderIcon,
  LogoIcon,
  PerformIcon,
  PlayIcon,
  ProjectIcon,
  RecordIcon,
  SampleIcon,
  SequenceIcon,
} from "./hardware_icons";
import type {EncoderPosition} from "./hardware_icons";

const ENCODER_POSITIONS: readonly EncoderPosition[] = [1, 2, 3, 4];

// Session-history chord on the direction row, EP-133 style: SHIFT is the
// modifier, ← / → step back/forward through authoring history, and each key's
// lamp lights while its direction is available instead of greying a button.
export interface RailHistoryChord {
  shifted: boolean;
  onToggleShift: () => void;
  undoAvailable: boolean;
  redoAvailable: boolean;
  onUndo: () => void;
  onRedo: () => void;
  undoTitle: string;
  redoTitle: string;
}

// A page's binding for one encoder: what it adjusts, and a relative turn in
// detents (positive is clockwise).
export interface EncoderBinding {
  label: string;
  disabled?: boolean;
  onTurn(detents: number): void;
}

// The direction keys' page action without SHIFT (the Sequence page steps
// Patterns); SHIFT keeps them on Undo / Redo.
export interface DirectionStep {
  backLabel: string;
  forwardLabel: string;
  backAvailable: boolean;
  forwardAvailable: boolean;
  onBack(): void;
  onForward(): void;
}

interface PhysicalControlsProps {
  activeMode: CreatorMode;
  activeBank: Bank;
  sequenceEnabled?: boolean;
  performEnabled?: boolean;
  onSelectMode: (mode: CreatorMode) => void;
  onSelectBank: (bank: Bank) => void;
  onRecord?: (event: MouseEvent<HTMLButtonElement>) => void;
  recordEnabled?: boolean;
  recording?: boolean;
  onPlayStop?: (event: MouseEvent<HTMLButtonElement>) => void;
  playEnabled?: boolean;
  playing?: boolean;
  history?: RailHistoryChord;
  // The brand mark doubles as the System entry (Desktop Final START HERE).
  onOpenSystem?: () => void;
  systemOpen?: boolean;
  systemEntryRef?: Ref<HTMLButtonElement>;
  encoders?: Readonly<Partial<Record<EncoderPosition, EncoderBinding>>>;
  directionStep?: DirectionStep;
}

// Pixels of vertical drag per detent.
const ENCODER_DRAG_STEP = 8;
// Pixels of wheel travel per detent. Wheel deltas accumulate, so a trackpad's
// burst of small events turns a few detents, not one per event; a line or
// page delta counts as that many pixels.
const ENCODER_WHEEL_STEP = 50;

// An encoder on a web console: the wheel, a vertical drag or the arrow keys
// (while focused) each turn it one detent; up and right are clockwise.
function Encoder({position, binding}: {position: EncoderPosition; binding: EncoderBinding | undefined}) {
  const drag = useRef<{pointerId: number; lastY: number} | null>(null);
  const wheel = useRef(0);
  if (binding === undefined) {
    return (
      <button type="button" className="physical-encoder" disabled
        aria-label={`Encoder ${position} — unassigned until hardware mapping is approved`}>
        <EncoderIcon position={position} />
      </button>
    );
  }
  const turn = (detents: number) => {
    if (!binding.disabled && detents !== 0) binding.onTurn(detents);
  };
  return (
    <button
      type="button"
      className="physical-encoder is-bound"
      aria-label={`Encoder ${position} — ${binding.label}`}
      disabled={binding.disabled}
      onKeyDown={(event) => {
        const detents = {ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1}[event.key];
        if (detents === undefined) return;
        event.preventDefault();
        turn(detents);
      }}
      onWheel={(event) => {
        const pixels = event.deltaY *
          (event.deltaMode === 1 ? ENCODER_WHEEL_STEP : event.deltaMode === 2 ? 800 : 1);
        wheel.current -= pixels;
        const detents = Math.trunc(wheel.current / ENCODER_WHEEL_STEP);
        if (detents === 0) return;
        wheel.current -= detents * ENCODER_WHEEL_STEP;
        turn(detents);
      }}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture?.(event.pointerId);
        drag.current = {pointerId: event.pointerId, lastY: event.clientY};
      }}
      onPointerMove={(event) => {
        const active = drag.current;
        if (active === null || active.pointerId !== event.pointerId) return;
        const detents = Math.trunc((active.lastY - event.clientY) / ENCODER_DRAG_STEP);
        if (detents === 0) return;
        active.lastY -= detents * ENCODER_DRAG_STEP;
        turn(detents);
      }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
    >
      <EncoderIcon position={position} />
    </button>
  );
}

interface PhysicalKeyProps {
  label: string;
  ariaLabel?: string;
  className?: string;
  current?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  lit?: boolean;
  pressed?: boolean;
  title?: string;
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void;
}

function PhysicalKey({
  label,
  ariaLabel,
  className = "",
  current = false,
  disabled = false,
  icon,
  lit = false,
  pressed,
  title,
  onClick,
}: PhysicalKeyProps) {
  return (
    <button
      type="button"
      className={`physical-key${className}${current ? " is-active" : ""}${lit ? " is-lit" : ""}${icon === undefined ? "" : " has-icon"}`}
      aria-current={current ? "page" : undefined}
      {...(pressed === undefined ? {} : {"aria-pressed": pressed})}
      aria-label={ariaLabel ?? label}
      disabled={disabled}
      {...(title === undefined ? {} : {title})}
      {...(onClick === undefined ? {} : {onClick})}
    >
      {icon === undefined ? label : icon}
    </button>
  );
}

function modeIcon(mode: "project" | "sample" | "sequence" | "perform", current: boolean): ReactNode {
  switch (mode) {
    case "project": return <ProjectIcon />;
    case "sample": return <SampleIcon />;
    case "sequence": return <SequenceIcon active={current} />;
    case "perform": return <PerformIcon />;
  }
}

export function PhysicalControls({
  activeMode,
  activeBank,
  sequenceEnabled = false,
  performEnabled = false,
  onSelectMode,
  onSelectBank,
  onRecord,
  recordEnabled = false,
  recording = false,
  onPlayStop,
  playEnabled = false,
  playing = false,
  history,
  onOpenSystem,
  systemOpen = false,
  systemEntryRef,
  encoders,
  directionStep,
}: PhysicalControlsProps) {
  // Without SHIFT the arrows take the page's step; with SHIFT, or on a page
  // without one, they are Undo / Redo.
  const stepping = directionStep !== undefined && !(history?.shifted ?? false);
  return (
    <div className="physical-controls">
      {onOpenSystem === undefined ? (
        <div className="physical-brand" aria-hidden="true">
          <LogoIcon />
        </div>
      ) : (
        <button type="button" className="physical-brand" aria-label="System"
          aria-expanded={systemOpen} ref={systemEntryRef} onClick={onOpenSystem}>
          <LogoIcon />
        </button>
      )}
      <div className="physical-encoders" role="group" aria-label="Encoders" data-testid="physical-encoders">
        {ENCODER_POSITIONS.map((position) => (
          <Encoder key={position} position={position} binding={encoders?.[position]} />
        ))}
      </div>
      <div className="physical-keys" data-testid="physical-keys">
        <PhysicalKey
          label="Project"
          icon={modeIcon("project", activeMode === "project")}
          current={activeMode === "project"}
          onClick={() => onSelectMode("project")}
        />
        <PhysicalKey
          label="Sample"
          icon={modeIcon("sample", activeMode === "sample")}
          current={activeMode === "sample"}
          onClick={() => onSelectMode("sample")}
        />
        <PhysicalKey
          label="Sequence"
          icon={modeIcon("sequence", activeMode === "sequence")}
          ariaLabel={sequenceEnabled ? "Sequence" : "Sequence — open a playable Project first"}
          current={activeMode === "sequence"}
          disabled={!sequenceEnabled}
          onClick={() => onSelectMode("sequence")}
        />
        <PhysicalKey
          label="Perform"
          icon={modeIcon("perform", activeMode === "perform")}
          ariaLabel={performEnabled
            ? "Perform"
            : "Perform — requires a playable Project, running audio, and capture storage"}
          current={activeMode === "perform"}
          disabled={!performEnabled}
          onClick={() => onSelectMode("perform")}
        />
        {BANK_NAMES.map((name, bank) => (
          <PhysicalKey
            key={name}
            label={name}
            ariaLabel={`Bank ${name}`}
            current={bank === activeBank}
            onClick={() => onSelectBank(bank as Bank)}
          />
        ))}
        <PhysicalKey label="↑" ariaLabel="Up — unassigned until direction mapping is approved" disabled />
        <PhysicalKey label="↓" ariaLabel="Down — unassigned until direction mapping is approved" disabled />
        {stepping ? (
          <>
            <PhysicalKey
              label="←"
              ariaLabel={directionStep.backLabel}
              lit={directionStep.backAvailable}
              disabled={!directionStep.backAvailable}
              onClick={directionStep.onBack}
            />
            <PhysicalKey
              label="→"
              ariaLabel={directionStep.forwardLabel}
              lit={directionStep.forwardAvailable}
              disabled={!directionStep.forwardAvailable}
              onClick={directionStep.onForward}
            />
          </>
        ) : (
          <>
            <PhysicalKey
              label="←"
              ariaLabel="Undo — SHIFT + ←"
              lit={history?.undoAvailable ?? false}
              disabled={history === undefined || !(history.shifted && history.undoAvailable)}
              {...(history === undefined ? {} : {title: history.undoTitle, onClick: history.onUndo})}
            />
            <PhysicalKey
              label="→"
              ariaLabel="Redo — SHIFT + →"
              lit={history?.redoAvailable ?? false}
              disabled={history === undefined || !(history.shifted && history.redoAvailable)}
              {...(history === undefined ? {} : {title: history.redoTitle, onClick: history.onRedo})}
            />
          </>
        )}
        <PhysicalKey
          label="SHIFT"
          className=" is-shift"
          ariaLabel={history === undefined
            ? "SHIFT — history layer unavailable"
            : "SHIFT — engage the Undo/Redo layer"}
          pressed={history?.shifted ?? false}
          disabled={history === undefined}
          {...(history === undefined ? {} : {onClick: history.onToggleShift})}
        />
        <PhysicalKey
          label="●"
          icon={<RecordIcon />}
          ariaLabel={recording
            ? "Record — stop recording Pad events into the current Pattern"
            : "Record"}
          current={recording}
          disabled={!recordEnabled || onRecord === undefined}
          {...(onRecord === undefined ? {} : {onClick: onRecord})}
        />
        <PhysicalKey
          label="▶"
          icon={<PlayIcon />}
          ariaLabel={playEnabled
            ? (playing ? "Play/Stop — Pattern is playing" : "Play/Stop")
            : "Play/Stop — needs a playable Project and running audio"}
          current={playing}
          disabled={!playEnabled || onPlayStop === undefined}
          {...(onPlayStop === undefined ? {} : {onClick: onPlayStop})}
        />
      </div>
    </div>
  );
}
