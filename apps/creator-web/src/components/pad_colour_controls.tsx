import type {PadColour, ProjectPadView} from "../runtime/runtime_types";
import {
  PAD_PALETTE,
  padCategoryLabel,
  padColourAttribute,
} from "../state/pad_colour";
import {padAddress} from "../state/view_model";

interface PadColourControlsProps {
  // The selected Pad as Project Truth describes it, or null with no Pad.
  pad: ProjectPadView | null;
  // Why the controls cannot commit now, or null when they can.
  disabledReason: string | null;
  error: string | null;
  // A palette index sets the override; null restores the category default.
  onChoose(colour: PadColour | null): void;
}

// Five-colour choice and "Restore category default" for the selected Pad
// (#1207, Desktop Final T7). It reads `colour` and `colourOverride` from
// Truth; choosing the override already stored, or restoring a Pad with no
// override, makes no call because Core would refuse it as unchanged.
export function PadColourControls({
  pad,
  disabledReason,
  error,
  onChoose,
}: PadColourControlsProps) {
  const reason = pad === null
    ? "Select a Pad to choose its colour."
    : pad.assetId === null
      ? "Assign a sound to this Pad to choose its colour."
      : disabledReason;
  const disabled = reason !== null;
  const category = padCategoryLabel(pad?.category ?? null);
  const source = pad === null || pad.assetId === null
    ? "No colour"
    : pad.colourOverride !== null
      ? "Custom colour"
      : category !== null
        ? `${category} default`
        : "Neutral";
  return (
    <section className="pad-colour-controls" aria-label="Pad colour"
      data-pad-colour={padColourAttribute(pad?.colour ?? null)}>
      <header>
        <span>PAD COLOUR{pad === null ? "" : ` · ${padAddress(pad)}`}</span>
        <output data-testid="pad-colour-source">{source}</output>
      </header>
      <div className="pad-colour-swatches" role="group" aria-label="Pad colours">
        {PAD_PALETTE.map((entry) => (
          <button
            type="button"
            key={entry.index}
            className="pad-colour-swatch"
            data-pad-colour={padColourAttribute(entry.index)}
            aria-label={`${entry.label} colour`}
            aria-pressed={pad?.colour === entry.index}
            disabled={disabled}
            onClick={() => {
              if (pad === null || pad.colourOverride === entry.index) return;
              onChoose(entry.index);
            }}
          >
            {entry.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="touch-control pad-colour-restore"
        disabled={disabled || pad?.colourOverride === null}
        onClick={() => {
          if (pad === null || pad.colourOverride === null) return;
          onChoose(null);
        }}
      >
        Restore category default
      </button>
      {reason !== null ? <p className="pad-colour-reason">{reason}</p> : null}
      {error !== null ? <p role="alert" className="pad-colour-error">{error}</p> : null}
    </section>
  );
}
