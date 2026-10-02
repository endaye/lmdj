import type {ReactNode} from "react";

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

interface PhysicalControlsProps {
  activeMode: CreatorMode;
  activeBank: Bank;
  sequenceEnabled?: boolean;
  performEnabled?: boolean;
  onSelectMode: (mode: CreatorMode) => void;
  onSelectBank: (bank: Bank) => void;
  onRecord?: () => void;
  recordEnabled?: boolean;
  recording?: boolean;
  onPlayStop?: () => void;
  playEnabled?: boolean;
  playing?: boolean;
  history?: RailHistoryChord;
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
  onClick?: () => void;
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
}: PhysicalControlsProps) {
  return (
    <div className="physical-controls">
      <div className="physical-brand" aria-hidden="true">
        <LogoIcon />
      </div>
      <div className="physical-encoders" role="group" aria-label="Encoders" data-testid="physical-encoders">
        {ENCODER_POSITIONS.map((position) => (
          <button
            key={position}
            type="button"
            className="physical-encoder"
            disabled
            aria-label={`Encoder ${position} — unassigned until hardware mapping is approved`}
          >
            <EncoderIcon position={position} />
          </button>
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
