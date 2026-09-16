import type {CreatorMode} from "./creator_mode";
import type {Bank} from "../state/creator_state";
import {BANK_NAMES} from "../state/view_model";
import encoder1Url from "../assets/hardware/encoder-1.svg";
import encoder2Url from "../assets/hardware/encoder-2.svg";
import encoder3Url from "../assets/hardware/encoder-3.svg";
import encoder4Url from "../assets/hardware/encoder-4.svg";
import logoUrl from "../assets/hardware/logo.svg";
import performUrl from "../assets/hardware/perform.svg";
import playUrl from "../assets/hardware/play.svg";
import projectUrl from "../assets/hardware/project.svg";
import recordUrl from "../assets/hardware/record.svg";
import sampleUrl from "../assets/hardware/sample.svg";
import sequenceOnUrl from "../assets/hardware/sequence-on.svg";
import sequenceUrl from "../assets/hardware/sequence.svg";

const ENCODER_URLS = [encoder1Url, encoder2Url, encoder3Url, encoder4Url] as const;

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
}

interface PhysicalKeyProps {
  label: string;
  ariaLabel?: string;
  current?: boolean;
  disabled?: boolean;
  icon?: string;
  onClick?: () => void;
}

function PhysicalKey({
  label,
  ariaLabel,
  current = false,
  disabled = false,
  icon,
  onClick,
}: PhysicalKeyProps) {
  return (
    <button
      type="button"
      className={`physical-key${current ? " is-active" : ""}${icon === undefined ? "" : " has-icon"}`}
      aria-current={current ? "page" : undefined}
      aria-label={ariaLabel ?? label}
      disabled={disabled}
      {...(onClick === undefined ? {} : {onClick})}
    >
      {icon === undefined ? label : (
        <img src={icon} alt="" width={24} height={24} draggable={false} />
      )}
    </button>
  );
}

function modeIcon(mode: "project" | "sample" | "sequence" | "perform", current: boolean): string {
  switch (mode) {
    case "project": return projectUrl;
    case "sample": return sampleUrl;
    case "sequence": return current ? sequenceOnUrl : sequenceUrl;
    case "perform": return performUrl;
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
}: PhysicalControlsProps) {
  return (
    <div className="physical-controls">
      <div className="physical-brand" aria-hidden="true">
        <img src={logoUrl} alt="" width={80} height={80} draggable={false} />
      </div>
      <div className="physical-encoders" role="group" aria-label="Encoders" data-testid="physical-encoders">
        {ENCODER_URLS.map((src, index) => (
          <button
            key={index + 1}
            type="button"
            className="physical-encoder"
            disabled
            aria-label={`Encoder ${index + 1} — unassigned until hardware mapping is approved`}
          >
            <img src={src} alt="" width={32} height={32} draggable={false} />
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
        <PhysicalKey label="−" ariaLabel="Decrease — unassigned until encoder mapping is approved" disabled />
        <PhysicalKey label="+" ariaLabel="Increase — unassigned until encoder mapping is approved" disabled />
        <PhysicalKey label="↑" ariaLabel="Up — unassigned until direction mapping is approved" disabled />
        <PhysicalKey label="↓" ariaLabel="Down — unassigned until direction mapping is approved" disabled />
        <PhysicalKey label="←" ariaLabel="Left — unassigned until direction mapping is approved" disabled />
        <PhysicalKey label="→" ariaLabel="Right — unassigned until direction mapping is approved" disabled />
        <PhysicalKey
          label="●"
          icon={recordUrl}
          ariaLabel={recording
            ? "Record — stop recording Pad events into the current Pattern"
            : "Record"}
          current={recording}
          disabled={!recordEnabled || onRecord === undefined}
          {...(onRecord === undefined ? {} : {onClick: onRecord})}
        />
        <PhysicalKey
          label="▶"
          icon={playUrl}
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
