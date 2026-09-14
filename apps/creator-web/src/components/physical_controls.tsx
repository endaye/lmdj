import type {CreatorMode} from "./mode_rail";
import type {Bank} from "../state/creator_state";
import {BANK_NAMES} from "../state/view_model";

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
}

interface PhysicalKeyProps {
  label: string;
  ariaLabel?: string;
  current?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

function PhysicalKey({
  label,
  ariaLabel,
  current = false,
  disabled = false,
  onClick,
}: PhysicalKeyProps) {
  return (
    <button
      type="button"
      className={`physical-key${current ? " is-active" : ""}`}
      aria-current={current ? "page" : undefined}
      aria-label={ariaLabel ?? label}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </button>
  );
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
}: PhysicalControlsProps) {
  return (
    <div className="physical-controls">
      <div className="physical-brand" aria-hidden="true">LMDJ</div>
      <div className="physical-encoders" aria-label="Encoders">
        {["1", "2", "3", "4"].map((index) => (
          <button
            key={index}
            type="button"
            className="physical-encoder"
            disabled
            aria-label={`Encoder ${index} — unassigned until hardware mapping is approved`}
          />
        ))}
      </div>
      <div className="physical-keys">
        <PhysicalKey
          label="Pj"
          ariaLabel="Project"
          current={activeMode === "project"}
          onClick={() => onSelectMode("project")}
        />
        <PhysicalKey
          label="Sm"
          ariaLabel="Sample"
          current={activeMode === "sample"}
          onClick={() => onSelectMode("sample")}
        />
        <PhysicalKey
          label="Sq"
          ariaLabel={sequenceEnabled ? "Sequence" : "Sequence — open a playable Project first"}
          current={activeMode === "sequence"}
          disabled={!sequenceEnabled}
          onClick={() => onSelectMode("sequence")}
        />
        <PhysicalKey
          label="Pf"
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
        <PhysicalKey label="−" ariaLabel="Decrease — unassigned until encoder mapping is approved" disabled />
        <PhysicalKey label="+" ariaLabel="Increase — unassigned until encoder mapping is approved" disabled />
        <PhysicalKey label="↑" ariaLabel="Up — unassigned until direction mapping is approved" disabled />
        <PhysicalKey label="↓" ariaLabel="Down — unassigned until direction mapping is approved" disabled />
        <PhysicalKey label="←" ariaLabel="Left — unassigned until direction mapping is approved" disabled />
        <PhysicalKey label="→" ariaLabel="Right — unassigned until direction mapping is approved" disabled />
        <PhysicalKey
          label="●"
          ariaLabel={recording
            ? "Record — recording Pad events into the current Pattern"
            : "Record"}
          disabled={!recordEnabled || recording || onRecord === undefined}
          {...(onRecord === undefined ? {} : {onClick: onRecord})}
        />
        <PhysicalKey
          label="▶"
          ariaLabel="Play — Pattern Play requires global Pattern transport"
          disabled
        />
      </div>
    </div>
  );
}
